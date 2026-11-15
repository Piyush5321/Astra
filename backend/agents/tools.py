"""Validated tools for the ASTRA research agent.

Every tool:
- validates its input with a Pydantic model (unknown fields rejected),
- runs only deterministic ASTRA functions over stored datasets,
- returns a ``ToolResult`` envelope (validated) with the data and its sources.
Tool outputs are data. Retrieved text must never be treated as instructions.
"""

import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data import nasa_power
from backend.database.models import DiscoveryRun, Measurement, Site
from backend.science.features import DIMENSIONS
from backend.science.limitations import limitations_for
from backend.science.profiles import PROFILES, profile_weights
from backend.services.discovery import NotFound, compare_sites, serialize_run
from backend.services.sites import measurement_dict, site_detail, site_summary

MAX_OUTPUT_CHARS = 24_000
SITE_ID = r"^[a-z0-9-]{3,80}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetInput(Strict):
    target_id: str = Field(pattern=SITE_ID, description="Target region id, e.g. mars-jezero")


class SearchInput(Strict):
    query: str = Field(default="", max_length=100, description="Free text over name/region/description")
    tag: str = Field(default="", max_length=60, description="Optional geology/resource/hazard tag")


class SiteInput(Strict):
    site_id: str = Field(pattern=SITE_ID)


class ClimateInput(Strict):
    site_id: str | None = Field(default=None, pattern=SITE_ID)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    start_year: int = Field(default=2020, ge=1981, le=2024)
    end_year: int = Field(default=2023, ge=1981, le=2024)

    @field_validator("end_year")
    @classmethod
    def _years(cls, v, info):
        start = info.data.get("start_year", 2020)
        if v < start or v - start > 4:
            raise ValueError("end_year must be >= start_year and span at most 5 years")
        return v


class CompareInput(Strict):
    candidate_id: str = Field(pattern=SITE_ID)
    target_id: str = Field(pattern=SITE_ID)
    profile_key: str = Field(default="general_analog")
    weights: dict[str, float] | None = None

    @field_validator("profile_key")
    @classmethod
    def _profile(cls, v):
        if v not in PROFILES:
            raise ValueError(f"profile_key must be one of {sorted(PROFILES)}")
        return v


class RunInput(Strict):
    run_id: int = Field(ge=1)
    top_n: int = Field(default=8, ge=1, le=50)


class ReportInput(Strict):
    run_id: int = Field(ge=1)
    site_id: str | None = Field(default=None, pattern=SITE_ID)


class ToolResult(BaseModel):
    ok: bool
    tool: str
    data: dict | list | None = None
    error: str | None = None
    sources: list[str] = []


def _sources_from_measurements(rows: list[dict]) -> list[str]:
    out = set()
    for m in rows:
        if m.get("dataset_id"):
            out.add(f"dataset:{m['dataset_id']}")
        if m.get("citation"):
            out.add(m["citation"][:160])
    return sorted(out)


def get_target_planetary_data(db: Session, args: TargetInput) -> ToolResult:
    detail = site_detail(db, args.target_id)
    if detail["role"] != "target":
        raise ValueError(f"{args.target_id} is not a Moon/Mars target.")
    detail["limitations"] = limitations_for(detail["body"])
    return ToolResult(ok=True, tool="get_target_planetary_data", data=detail,
                      sources=_sources_from_measurements(detail["measurements"]))


def search_candidate_locations(db: Session, args: SearchInput) -> ToolResult:
    q = args.query.lower().strip()
    out = []
    for site in db.scalars(select(Site).where(Site.role == "candidate").order_by(Site.name)):
        text = f"{site.id} {site.name} {site.region} {site.description} {site.scientific_context}".lower()
        if q and not all(tok in text for tok in q.split()):
            continue
        tags = {m.feature_key: m.value_tags for m in db.scalars(
            select(Measurement).where(Measurement.site_id == site.id,
                                      Measurement.feature_key.like("%_tags")))}
        if args.tag and not any(args.tag in (t or []) for t in tags.values()):
            continue
        out.append({**site_summary(site), **tags})
    return ToolResult(ok=True, tool="search_candidate_locations",
                      data={"count": len(out), "candidates": out},
                      sources=["ASTRA curated catalog (backend/data/catalog.py)"])


def get_climate_data(db: Session, args: ClimateInput) -> ToolResult:
    if args.site_id:
        rows = [measurement_dict(m) for m in db.scalars(select(Measurement).where(
            Measurement.site_id == args.site_id, Measurement.dimension == "thermal"))]
        if not rows:
            raise NotFound(f"No thermal/climate data stored for {args.site_id}.")
        return ToolResult(ok=True, tool="get_climate_data",
                          data={"site_id": args.site_id, "measurements": rows},
                          sources=_sources_from_measurements(rows))
    if args.latitude is None or args.longitude is None:
        raise ValueError("Provide site_id, or both latitude and longitude.")
    daily = nasa_power.fetch_daily(args.latitude, args.longitude, f"{args.start_year}0101",
                                   f"{args.end_year}1231", db=db)
    summary = nasa_power.summarize_climate(daily)
    return ToolResult(ok=True, tool="get_climate_data", data={
        "latitude": args.latitude, "longitude": args.longitude, "period": f"{daily.start}-{daily.end}",
        "features": summary, "sources_reported_by_power": daily.sources,
        "from_cache": daily.from_cache,
        "note": "Live NASA POWER request (reanalysis-based grid-cell estimates)."},
        sources=[f"NASA POWER {daily.request_url.split('?')[0]}"])


def analyze_terrain(db: Session, args: SiteInput) -> ToolResult:
    rows = [measurement_dict(m) for m in db.scalars(select(Measurement).where(
        Measurement.site_id == args.site_id, Measurement.dimension == "terrain"))]
    if not rows:
        raise NotFound(f"No terrain data stored for {args.site_id}.")
    return ToolResult(ok=True, tool="analyze_terrain",
                      data={"site_id": args.site_id, "grid": "60 x 60 cells of 500 m (30 km)",
                            "measurements": rows},
                      sources=_sources_from_measurements(rows))


def _weights(args: CompareInput) -> dict:
    if args.weights:
        unknown = set(args.weights) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"Unknown weight dimensions: {sorted(unknown)}")
        return args.weights
    return profile_weights(args.profile_key)


def calculate_similarity(db: Session, args: CompareInput) -> ToolResult:
    r = compare_sites(db, args.candidate_id, args.target_id, _weights(args))
    compact = {k: r[k] for k in ("candidate_id", "target_id", "engine_version", "weights",
                                 "score", "score_low", "score_high", "bound_low",
                                 "bound_high", "coverage", "confidence", "dimensions")}
    compact["features"] = [
        {k: f[k] for k in ("key", "label", "status", "similarity", "candidate_value",
                           "target_value", "candidate_tags", "target_tags", "unit",
                           "missing_reason")} for f in r["features"]]
    return ToolResult(ok=True, tool="calculate_similarity", data=compact,
                      sources=[f"ASTRA scoring engine v{r['engine_version']}",
                               f"dataset:dem:{args.candidate_id}", f"dataset:dem:{args.target_id}"])


def explain_scientific_evidence(db: Session, args: CompareInput) -> ToolResult:
    r = compare_sites(db, args.candidate_id, args.target_id, _weights(args))
    cand = site_detail(db, args.candidate_id)
    targ = site_detail(db, args.target_id)
    provenance = sorted(set(_sources_from_measurements(cand["measurements"]) +
                            _sources_from_measurements(targ["measurements"])))
    return ToolResult(ok=True, tool="explain_scientific_evidence", data={
        "explanation": r["explanation"], "limitations": r["limitations"],
        "environment": r["environment"],
        "candidate_notes": cand["site_notes"], "target_notes": targ["site_notes"],
        "datasets": [{"id": d["id"], "product": d["product_id"], "provider": d["provider"],
                      "notes": d["notes"]} for d in cand["datasets"] + targ["datasets"]],
    }, sources=provenance)


def get_discovery_results(db: Session, args: RunInput) -> ToolResult:
    run = db.get(DiscoveryRun, args.run_id)
    if run is None:
        raise NotFound(f"Discovery run {args.run_id} not found.")
    data = serialize_run(db, run, include_features=False)
    data["results"] = [{k: r[k] for k in ("rank", "site_id", "name", "score", "score_low",
                                          "score_high", "bound_low", "bound_high", "coverage",
                                          "confidence", "dimensions")}
                       for r in data["results"][:args.top_n]]
    return ToolResult(ok=True, tool="get_discovery_results", data=data,
                      sources=[f"discovery_run:{run.id}"])


def generate_report(db: Session, args: ReportInput) -> ToolResult:
    from backend.reports.pdf import build_report

    report = build_report(db, args.run_id, args.site_id)
    return ToolResult(ok=True, tool="generate_report", data={
        "report_id": report.id, "title": report.title,
        "download_url": f"/api/reports/{report.id}/pdf"}, sources=[f"report:{report.id}"])


TOOLS: dict[str, tuple[type[Strict], Callable, str]] = {
    "get_target_planetary_data": (TargetInput, get_target_planetary_data,
        "Retrieve a Moon/Mars target region's stored measurements (LOLA/MOLA terrain, "
        "literature thermal values, curated tags), provenance and fundamental limitations."),
    "search_candidate_locations": (SearchInput, search_candidate_locations,
        "Search the Earth candidate catalog by free text and/or a curated tag "
        "(e.g. 'evaporite', 'water_ice'). Returns ids, coordinates and tags."),
    "get_climate_data": (ClimateInput, get_climate_data,
        "Get NASA POWER-derived thermal/climate measurements for a stored site (site_id), or "
        "fetch live POWER daily data for arbitrary Earth coordinates (latitude, longitude)."),
    "analyze_terrain": (SiteInput, analyze_terrain,
        "Get terrain metrics (slope, TRI, relief, steep fraction) computed from the site's DEM "
        "on the common 500 m grid, with dataset provenance."),
    "calculate_similarity": (CompareInput, calculate_similarity,
        "Deterministically score an Earth candidate against a target with a mission profile "
        "or custom dimension weights. Returns score, bounds, coverage and per-feature values."),
    "explain_scientific_evidence": (CompareInput, explain_scientific_evidence,
        "Get the deterministic explanation (strengths, mismatches, missing data), limitations "
        "and dataset provenance for a candidate-target comparison."),
    "get_discovery_results": (RunInput, get_discovery_results,
        "Get the ranked results of a saved discovery run."),
    "generate_report": (ReportInput, generate_report,
        "Generate a PDF scientific report for a discovery run (optionally focused on a site)."),
}


def tool_schemas() -> list[dict]:
    out = []
    for name, (model, _, description) in TOOLS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        out.append({"name": name, "description": description, "input_schema": schema})
    return out


def run_tool(db: Session, name: str, raw_input: dict) -> ToolResult:
    """Validate input, execute, validate output. Never raises for tool-level errors."""
    if name not in TOOLS:
        return ToolResult(ok=False, tool=name, error=f"Unknown tool {name!r}.")
    model, fn, _ = TOOLS[name]
    try:
        args = model.model_validate(raw_input or {})
    except ValidationError as exc:
        return ToolResult(ok=False, tool=name, error=f"Invalid input: {exc.errors(include_url=False)}")
    try:
        result = fn(db, args)
        return ToolResult.model_validate(result.model_dump())
    except (NotFound, ValueError, nasa_power.PowerError, FileNotFoundError) as exc:
        db.rollback()
        return ToolResult(ok=False, tool=name, error=str(exc))


def serialize_for_model(result: ToolResult) -> str:
    text = json.dumps(result.model_dump(), default=str)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + '..."[truncated]"'
    return text
