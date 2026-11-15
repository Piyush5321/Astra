"""Mission configuration, discovery runs and comparisons."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.schemas import CompareRequest, DiscoveryRunRequest, MissionCreate
from backend.database.models import DiscoveryRun, Mission, Site
from backend.database.session import get_db
from backend.science.profiles import PROFILES, normalize_weights, profile_weights
from backend.services.discovery import NotFound, compare_sites, run_discovery, serialize_run

router = APIRouter(prefix="/api", tags=["missions"])


def mission_dict(m: Mission) -> dict:
    return {"id": m.id, "name": m.name, "body": m.body, "target_site_id": m.target_site_id,
            "target_name": m.target.name, "profile_key": m.profile_key,
            "profile_label": PROFILES.get(m.profile_key, {}).get("label", "Custom"),
            "weights": m.weights, "objectives": m.objectives, "is_preset": m.is_preset,
            "created_at": m.created_at.isoformat()}


@router.get("/missions")
def list_missions(db: Session = Depends(get_db)) -> list[dict]:
    return [mission_dict(m) for m in db.scalars(select(Mission).order_by(Mission.id))]


@router.get("/missions/{mission_id}")
def get_mission(mission_id: int, db: Session = Depends(get_db)) -> dict:
    m = db.get(Mission, mission_id)
    if m is None:
        raise HTTPException(404, f"Mission {mission_id} not found.")
    return mission_dict(m)


@router.post("/missions", status_code=201)
def create_mission(body: MissionCreate, db: Session = Depends(get_db)) -> dict:
    target = db.get(Site, body.target_site_id)
    if target is None or target.role != "target":
        raise HTTPException(422, f"{body.target_site_id!r} is not a Moon/Mars target.")
    if body.weights:
        weights, profile = normalize_weights(body.weights), (
            body.profile_key if body.profile_key != "general_analog" else "custom")
    elif body.profile_key == "custom":
        raise HTTPException(422, "profile_key 'custom' requires weights.")
    else:
        weights, profile = profile_weights(body.profile_key), body.profile_key
    m = Mission(name=body.name, body=target.body, target_site_id=target.id,
                profile_key=profile, weights=weights, objectives=body.objectives)
    db.add(m)
    db.commit()
    db.refresh(m)
    return mission_dict(m)


@router.post("/discovery/run", status_code=201)
def discovery_run(body: DiscoveryRunRequest, db: Session = Depends(get_db)) -> dict:
    mission = db.get(Mission, body.mission_id)
    if mission is None:
        raise HTTPException(404, f"Mission {body.mission_id} not found.")
    try:
        run = run_discovery(db, mission, body.weights, body.candidate_ids, body.rank_by)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return serialize_run(db, run)


@router.get("/discovery/runs")
def list_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(min(limit, 100)))
    return [{"id": r.id, "mission_id": r.mission_id, "mission_name": r.mission.name,
             "target_site_id": r.target_site_id, "created_at": r.created_at.isoformat(),
             "candidate_count": r.candidate_count, "top_site_id":
             r.results[0].site_id if r.results else None,
             "top_score": r.results[0].score if r.results else None} for r in runs]


@router.get("/discovery/results/{run_id}")
def discovery_results(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(DiscoveryRun, run_id)
    if run is None:
        raise HTTPException(404, f"Discovery run {run_id} not found.")
    return serialize_run(db, run)


@router.post("/analysis/compare")
def compare(body: CompareRequest, db: Session = Depends(get_db)) -> dict:
    weights = body.weights or profile_weights(body.profile_key)
    try:
        return compare_sites(db, body.candidate_id, body.target_id, weights)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
