"""Locations, targets, datasets, vocabularies, profiles and live climate endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data import nasa_power
from backend.data.catalog import LIMITATION_NOT_VERIFIED
from backend.data.vocabulary import VOCABULARIES
from backend.database.models import Dataset, Measurement, Site
from backend.database.session import get_db
from backend.science.features import DIMENSIONS, FEATURES
from backend.science.limitations import ENVIRONMENT
from backend.science.profiles import PROFILES
from backend.services.discovery import NotFound
from backend.services.sites import dataset_dict, site_detail, site_summary, terrain_grid

router = APIRouter(prefix="/api", tags=["locations"])


def _with_tags(db: Session, site: Site) -> dict:
    out = site_summary(site)
    for m in db.scalars(select(Measurement).where(Measurement.site_id == site.id,
                                                  Measurement.feature_key.like("%_tags"))):
        out[m.feature_key] = m.value_tags
    return out


@router.get("/locations")
def list_locations(q: str = Query("", max_length=100), tag: str = Query("", max_length=60),
                   db: Session = Depends(get_db)) -> list[dict]:
    """Earth candidate locations (optionally filtered by text or curated tag)."""
    out = []
    for site in db.scalars(select(Site).where(Site.role == "candidate").order_by(Site.name)):
        item = _with_tags(db, site)
        text = f"{site.name} {site.region} {site.description}".lower()
        if q and q.lower() not in text:
            continue
        if tag and not any(tag in (item.get(k) or []) for k in VOCABULARIES):
            continue
        out.append(item)
    return out


@router.get("/targets")
def list_targets(body: str | None = Query(None, pattern="^(moon|mars)$"),
                 db: Session = Depends(get_db)) -> list[dict]:
    query = select(Site).where(Site.role == "target").order_by(Site.body, Site.name)
    if body:
        query = query.where(Site.body == body)
    return [_with_tags(db, s) for s in db.scalars(query)]


@router.get("/location/{site_id}")
def get_location(site_id: str, db: Session = Depends(get_db)) -> dict:
    """Full detail for any site: measurements with provenance and datasets."""
    try:
        return site_detail(db, site_id)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/location/{site_id}/terrain")
def get_terrain(site_id: str, db: Session = Depends(get_db)) -> dict:
    """500 m analysis grid and hillshade for visualisation."""
    if db.get(Site, site_id) is None:
        raise HTTPException(404, f"Site {site_id!r} not found.")
    try:
        return terrain_grid(site_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)) -> list[dict]:
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id))]


@router.get("/reference")
def reference() -> dict:
    """Feature registry, vocabularies, mission profiles and environment constants."""
    return {
        "dimensions": DIMENSIONS,
        "features": [f.__dict__ for f in FEATURES],
        "vocabularies": VOCABULARIES,
        "vocabulary_note": LIMITATION_NOT_VERIFIED,
        "profiles": PROFILES,
        "environment": ENVIRONMENT,
    }


@router.get("/climate")
def live_climate(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                 start: str = Query("20230101", pattern=r"^\d{8}$"),
                 end: str = Query("20231231", pattern=r"^\d{8}$"),
                 db: Session = Depends(get_db)) -> dict:
    """Live NASA POWER daily data for any Earth point, summarised (cached in SQLite)."""
    try:
        data = nasa_power.fetch_daily(lat, lon, start, end, db=db)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except nasa_power.PowerError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"latitude": lat, "longitude": lon, "start": data.start, "end": data.end,
            "summary": nasa_power.summarize_climate(data), "units": data.units,
            "sources": data.sources, "api_version": data.api_version,
            "from_cache": data.from_cache, "fetched_at": data.fetched_at,
            "attribution": nasa_power.POWER_ATTRIBUTION}
