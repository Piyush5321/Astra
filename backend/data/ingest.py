"""Ingest acquired datasets and curated catalog entries into the measurements table.

Every Measurement row carries unit, uncertainty, provenance (dataset or
citation), method and a ``source_type``. Features that cannot be computed are
stored with ``quality_flag='missing'`` and an explicit ``missing_reason`` so the
UI and the scoring engine can report them; they are never filled with guesses.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.data import catalog, nasa_power
from backend.data.acquire import dem_paths, power_path, sha256_file
from backend.data.vocabulary import validate_tags
from backend.database.models import Dataset, Measurement, Mission, Site
from backend.science import features as F
from backend.science.normalization import validate_value
from backend.science.profiles import profile_weights
from backend.science.resample import to_analysis_grid
from backend.science.terrain import TerrainError, native_slope_mean, terrain_metrics

TERRAIN_METHOD = ("Resampled to a 60 x 60 grid of 500 m cells (30 km window) "
                  "centred on the site ({method}); metrics per science.terrain.")
CURATED_NOTE = catalog.LIMITATION_NOT_VERIFIED


class IngestError(RuntimeError):
    pass


# --- file loading ---------------------------------------------------------------

def load_dem(site_id: str, root: Path | None = None) -> tuple[np.ndarray, dict]:
    """Load a DEM subset and its sidecar, verifying the SHA-256 checksum.

    Reads the .npz copy (NumPy only) when present; falls back to the GeoTIFF,
    which requires rasterio/GDAL.
    """
    spec = catalog.SITES_BY_ID[site_id]
    tif, meta_path = dem_paths(spec, root)
    if not meta_path.exists():
        raise FileNotFoundError(f"No DEM subset for {site_id}; run python -m backend.data.acquire")
    meta = json.loads(meta_path.read_text())
    npz = tif.with_suffix(".npz")
    if meta.get("npz_sha256") and npz.exists():
        if sha256_file(npz) != meta["npz_sha256"]:
            raise IngestError(f"Checksum mismatch for {npz.name}: file differs from provenance record.")
        with np.load(npz) as data:
            arr = data["elevation"].astype("float32")
    elif tif.exists():
        if sha256_file(tif) != meta.get("sha256"):
            raise IngestError(f"Checksum mismatch for {tif.name}: file differs from provenance record.")
        import rasterio

        with rasterio.open(tif) as src:
            arr = src.read(1).astype("float32")
    else:
        raise FileNotFoundError(f"No DEM file for {site_id}; run python -m backend.data.acquire")
    if list(arr.shape) != meta["shape"]:
        raise IngestError(f"Shape mismatch for DEM of {site_id}.")
    return arr, meta


@lru_cache(maxsize=64)
def analysis_grid(site_id: str) -> tuple[np.ndarray, dict, dict]:
    """(500 m grid, resample info, sidecar) for a site; cached per process."""
    arr, meta = load_dem(site_id)
    grid, info = to_analysis_grid(arr, meta["georef"])
    return grid, info, meta


def load_power(site_id: str, root: Path | None = None) -> nasa_power.PowerDaily:
    spec = catalog.SITES_BY_ID[site_id]
    path = power_path(spec, root)
    if not path.exists():
        raise FileNotFoundError(f"No POWER data for {site_id}.")
    record = json.loads(path.read_text())
    fields = nasa_power.PowerDaily.__dataclass_fields__
    return nasa_power.PowerDaily(**{k: v for k, v in record.items() if k in fields})


# --- measurement helpers ------------------------------------------------------------

def _dimension(key: str) -> str:
    if key in F.FEATURES_BY_KEY:
        return F.FEATURES_BY_KEY[key].dimension
    return F.DESCRIPTIVE_FEATURES[key][0]


def _unit(key: str) -> str:
    if key in F.FEATURES_BY_KEY:
        return F.FEATURES_BY_KEY[key].unit
    return F.DESCRIPTIVE_FEATURES[key][2]


def measured(site_id: str, key: str, value: float, *, source_type: str,
             dataset_id: str | None = None, method: str = "", citation: str = "",
             uncertainty: float | None = None, uncertainty_note: str = "",
             observed_period: str = "") -> Measurement:
    if not math.isfinite(value):
        raise IngestError(f"{site_id}/{key}: non-finite value.")
    if key in F.FEATURES_BY_KEY:
        validate_value(F.FEATURES_BY_KEY[key], value)
    return Measurement(
        site_id=site_id, feature_key=key, dimension=_dimension(key), value=float(value),
        unit=_unit(key), uncertainty=uncertainty, uncertainty_note=uncertainty_note,
        source_type=source_type, dataset_id=dataset_id, method=method, citation=citation,
        observed_period=observed_period, quality_flag="ok")


def tagged(site_id: str, key: str, tags: tuple[str, ...], citation: str = "") -> Measurement:
    return Measurement(
        site_id=site_id, feature_key=key, dimension=_dimension(key),
        value_tags=validate_tags(key, list(tags)), unit="tags",
        source_type="curated_classification", method=CURATED_NOTE, citation=citation,
        quality_flag="ok")


def missing(site_id: str, key: str, reason: str, source_type: str = "none") -> Measurement:
    return Measurement(
        site_id=site_id, feature_key=key, dimension=_dimension(key), unit=_unit(key),
        source_type=source_type, quality_flag="missing", missing_reason=reason)


# --- per-site ingestion ---------------------------------------------------------------

def _dem_dataset(spec: catalog.SiteSpec, meta: dict) -> Dataset:
    return Dataset(
        id=f"dem:{spec.id}", site_id=spec.id, kind="elevation",
        name=f"{meta['product']} subset - {spec.name}", provider=meta["provider"],
        product_id=meta["product"], source_url=meta["source_url"],
        file_path=f"datasets/{spec.body}/{meta['file']}", sha256=meta["sha256"],
        native_resolution_m=meta["native_resolution_m"], retrieved_at=meta["retrieved_at"],
        attribution=meta["attribution"], notes=meta.get("notes", []),
        extra={"vertical_reference": meta.get("vertical_reference", ""),
               "shape": meta["shape"], "valid_fraction": meta.get("valid_fraction")},
        is_sample=bool(meta.get("is_sample", False)))


def terrain_measurements(spec: catalog.SiteSpec, db: Session) -> list[Measurement]:
    keys = ["slope_mean_deg", "tri_mean_m", "relief_p95_p5_m", "steep_slope_fraction",
            "slope_p90_deg", "slope_median_deg", "elevation_mean_m", "elevation_min_m",
            "elevation_max_m"]
    try:
        arr, meta = load_dem(spec.id)
    except (FileNotFoundError, IngestError) as exc:
        return [missing(spec.id, k, str(exc)) for k in keys]
    ds = _dem_dataset(spec, meta)
    db.merge(ds)
    try:
        grid, info = to_analysis_grid(arr, meta["georef"])
        t = terrain_metrics(grid, info["cell_m"])
    except TerrainError as exc:
        return [missing(spec.id, k, str(exc), "derived") for k in keys]
    method = TERRAIN_METHOD.format(method=info["method"])
    note = (f"Resolution-dependent; native DEM spacing {info['native_spacing_m']} m. "
            "Measurement uncertainty not quantified.")
    rows = [measured(spec.id, k, t[k], source_type="derived", dataset_id=ds.id,
                     method=method, uncertainty_note=note) for k in keys]
    if spec.body == "earth" and meta["georef"]["kind"] == "geographic":
        a, _, _, _, e, _ = meta["georef"]["transform"]
        r = meta["georef"]["radius_m"]
        dy = math.radians(abs(e)) * r
        dx = math.radians(abs(a)) * r * math.cos(math.radians(spec.latitude))
        native = native_slope_mean(arr, dy, dx)
        if native is not None:
            rows.append(measured(spec.id, "slope_mean_native_deg", native,
                                 source_type="derived", dataset_id=ds.id,
                                 method="Mean slope at native ~30 m spacing (display only)."))
    return rows


def thermal_measurements(spec: catalog.SiteSpec, db: Session) -> list[Measurement]:
    thermal_keys = ["surface_temp_max_k", "surface_temp_min_k", "surface_temp_diurnal_range_k"]
    rows: list[Measurement] = []
    if spec.body != "earth":
        for key in thermal_keys:
            lit = spec.thermal.get(key)
            if lit is None:
                rows.append(missing(spec.id, key, spec.thermal_missing_reason
                                    or "No vetted literature value.", "literature_reference"))
            else:
                rows.append(measured(spec.id, key, lit.value, source_type="literature_reference",
                                     citation=lit.citation, method=lit.note,
                                     uncertainty=lit.uncertainty,
                                     uncertainty_note="Approximate reference value; "
                                     "uncertainty assigned by ASTRA curators."))
        rows.append(measured(spec.id, "annual_precipitation_mm", 0.0,
                             source_type="physical_constraint",
                             method=catalog.TARGET_PRECIPITATION_NOTE[spec.body]))
        return rows

    all_keys = thermal_keys + ["annual_precipitation_mm"]
    try:
        data = load_power(spec.id)
        summary = nasa_power.summarize_climate(data)
    except (FileNotFoundError, nasa_power.PowerError, ValueError) as exc:
        return [missing(spec.id, k, f"NASA POWER data unavailable: {exc}") for k in all_keys]
    ds = Dataset(
        id=f"power:{spec.id}", site_id=spec.id, kind="climate",
        name=f"NASA POWER daily point data - {spec.name}", provider="NASA LaRC POWER",
        product_id=f"POWER Daily API {data.api_version}", source_url=data.request_url,
        file_path=f"datasets/earth/power/{spec.id}.json",
        sha256=sha256_file(power_path(spec)), native_resolution_m=None,
        retrieved_at=data.fetched_at, attribution=nasa_power.POWER_ATTRIBUTION,
        notes=["Reanalysis-based grid-cell estimates (MERRA-2 ~0.5 x 0.625 deg), not "
               "station observations.", f"Sources: {', '.join(data.sources)}."],
        extra={"start": data.start, "end": data.end, "units": data.units})
    db.merge(ds)
    period = f"{data.start}-{data.end}"
    methods = {
        "surface_temp_max_k": "95th percentile of daily TS_MAX (Earth skin temperature "
        "maximum) per year, averaged over years.",
        "surface_temp_min_k": "5th percentile of daily TS_MIN per year, averaged over years.",
        "surface_temp_diurnal_range_k": "Mean daily TS_MAX - TS_MIN, averaged over years.",
        "annual_precipitation_mm": "Annual sum of PRECTOTCORR, averaged over years.",
    }
    for key in all_keys:
        item = summary.get(key)
        if item is None:
            rows.append(missing(spec.id, key, "Fewer than 90% valid POWER days in every year."))
            continue
        rows.append(measured(
            spec.id, key, item["value"], source_type="measured_dataset", dataset_id=ds.id,
            method=methods[key], uncertainty=item["uncertainty"],
            uncertainty_note="Interannual standard deviation over "
            f"{len(item['years'])} years (excludes model/reanalysis error).",
            observed_period=period))
    irradiance_factor = {"MJ/m^2/day": 1 / nasa_power.MJ_PER_KWH, "kW-hr/m^2/day": 1.0}
    descriptive = (("mean_skin_temp_k", "TS", {"C": 1.0}, 273.15),
                   ("mean_relative_humidity_pct", "RH2M", {"%": 1.0}, 0.0),
                   ("mean_solar_irradiance_kwh_m2_day", "ALLSKY_SFC_SW_DWN",
                    irradiance_factor, 0.0),
                   ("mean_wind_speed_ms", "WS2M", {"m/s": 1.0}, 0.0))
    for key, param, factors, offset in descriptive:
        unit = data.units.get(param, "")
        if unit not in factors:
            rows.append(missing(spec.id, key, f"Unexpected POWER unit {unit!r} for {param}."))
            continue
        vals = [v for v in data.values.get(param, {}).values() if v is not None]
        if vals:
            rows.append(measured(spec.id, key, float(np.mean(vals)) * factors[unit] + offset,
                                 source_type="measured_dataset", dataset_id=ds.id,
                                 method=f"Mean of {len(vals)} valid daily {param} values "
                                 f"(source unit {unit}).", observed_period=period))
    return rows


def categorical_measurements(spec: catalog.SiteSpec) -> list[Measurement]:
    cite = "; ".join(r.citation for r in spec.references)
    return [tagged(spec.id, "geology_tags", spec.geology_tags, cite),
            tagged(spec.id, "resource_tags", spec.resource_tags, cite),
            tagged(spec.id, "hazard_tags", spec.hazard_tags, cite)]


def upsert_site(db: Session, spec: catalog.SiteSpec) -> Site:
    site = db.get(Site, spec.id) or Site(id=spec.id)
    site.name, site.body, site.role = spec.name, spec.body, spec.role
    site.latitude, site.longitude, site.region = spec.latitude, spec.longitude, spec.region
    site.description, site.scientific_context = spec.description, spec.scientific_context
    site.site_notes = list(spec.site_notes)
    site.references = [r.as_dict() for r in spec.references]
    site.coordinate_source = spec.coordinate_source
    db.merge(site)
    return site


def ingest_site(db: Session, spec: catalog.SiteSpec) -> int:
    upsert_site(db, spec)
    db.flush()
    db.execute(delete(Measurement).where(Measurement.site_id == spec.id))
    rows = (terrain_measurements(spec, db) + thermal_measurements(spec, db)
            + categorical_measurements(spec))
    db.add_all(rows)
    return len(rows)


def seed_missions(db: Session) -> None:
    existing = {m.name for m in db.scalars(select(Mission).where(Mission.is_preset))}
    for preset in catalog.PRESET_MISSIONS:
        if preset["name"] in existing:
            continue
        target = catalog.SITES_BY_ID[preset["target_site_id"]]
        db.add(Mission(name=preset["name"], body=target.body,
                       target_site_id=target.id, profile_key=preset["profile_key"],
                       weights=profile_weights(preset["profile_key"]),
                       objectives=preset["objectives"], is_preset=True))


def ingest_all(db: Session, force: bool = False) -> dict:
    """Seed sites/missions and (re)build measurements. Skips sites already ingested
    unless ``force`` or their dataset checksums changed."""
    counts = {}
    for spec in catalog.ALL_SITES:
        current = db.scalar(select(Measurement.id).where(Measurement.site_id == spec.id).limit(1))
        stale = force or current is None or _checksums_changed(db, spec)
        if stale:
            counts[spec.id] = ingest_site(db, spec)
        else:
            upsert_site(db, spec)
    seed_missions(db)
    db.commit()
    analysis_grid.cache_clear()
    return counts


def _checksums_changed(db: Session, spec: catalog.SiteSpec) -> bool:
    tif, _ = dem_paths(spec)
    ds = db.get(Dataset, f"dem:{spec.id}")
    if tif.exists() != (ds is not None):
        return True
    if ds is not None and ds.sha256 != sha256_file(tif):
        return True
    if spec.body == "earth":
        p = power_path(spec)
        pds = db.get(Dataset, f"power:{spec.id}")
        if p.exists() != (pds is not None):
            return True
        if pds is not None and pds.sha256 != sha256_file(p):
            return True
    return False


if __name__ == "__main__":
    from backend.database import session as db_session
    from backend.database.schema import init_schema

    init_schema(db_session.engine)
    with db_session.SessionLocal() as s:
        print(json.dumps(ingest_all(s, force=True), indent=2))
    print(f"Datasets dir: {settings.datasets_dir}")
