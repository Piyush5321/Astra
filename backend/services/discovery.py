"""Discovery runs and comparisons: database <-> deterministic scoring engine."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import DiscoveryResult, DiscoveryRun, Measurement, Mission, Site
from backend.science.explain import explain
from backend.science.features import FEATURES_BY_KEY
from backend.science.limitations import ENVIRONMENT, limitations_for
from backend.science.normalization import FeatureValue
from backend.science.profiles import normalize_weights
from backend.science.similarity import ENGINE_VERSION, rank_candidates, score_candidate


class NotFound(LookupError):
    pass


def site_features(db: Session, site_id: str) -> dict[str, FeatureValue]:
    """Scored features of a site as FeatureValues (missing rows stay missing)."""
    rows = db.scalars(select(Measurement).where(Measurement.site_id == site_id))
    out = {}
    for m in rows:
        if m.feature_key not in FEATURES_BY_KEY:
            continue
        ok = m.quality_flag != "missing"
        out[m.feature_key] = FeatureValue(
            key=m.feature_key,
            value=m.value if ok else None,
            tags=tuple(m.value_tags) if ok and m.value_tags is not None else None,
            uncertainty=m.uncertainty, source_type=m.source_type,
            missing_reason=m.missing_reason)
    return out


def get_site(db: Session, site_id: str) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise NotFound(f"Site {site_id!r} not found.")
    return site


def compare_sites(db: Session, candidate_id: str, target_id: str,
                  weights: dict[str, float]) -> dict:
    """Score one candidate against one target without persisting anything."""
    cand, target = get_site(db, candidate_id), get_site(db, target_id)
    if cand.role != "candidate" or target.role != "target":
        raise ValueError("Comparison requires an Earth candidate and a Moon/Mars target.")
    result = score_candidate(site_features(db, cand.id), site_features(db, target.id),
                             normalize_weights(weights))
    return {
        "candidate_id": cand.id, "target_id": target.id, "engine_version": ENGINE_VERSION,
        "weights": normalize_weights(weights), **result.to_dict(),
        "explanation": explain(result),
        "limitations": limitations_for(target.body),
        "environment": {"earth": ENVIRONMENT["earth"], target.body: ENVIRONMENT[target.body]},
    }


def run_discovery(db: Session, mission: Mission, weights: dict[str, float] | None = None,
                  candidate_ids: list[str] | None = None, rank_by: str = "score") -> DiscoveryRun:
    """Score every (or selected) Earth candidate against the mission target and persist."""
    w = normalize_weights(weights or mission.weights)
    target = get_site(db, mission.target_site_id)
    query = select(Site).where(Site.role == "candidate")
    if candidate_ids:
        query = query.where(Site.id.in_(candidate_ids))
    candidates = list(db.scalars(query))
    if not candidates:
        raise NotFound("No candidate locations matched.")
    target_feats = site_features(db, target.id)
    scores = {c.id: score_candidate(site_features(db, c.id), target_feats, w) for c in candidates}
    order = rank_candidates(scores, rank_by)

    run = DiscoveryRun(mission_id=mission.id, target_site_id=target.id, weights=w,
                       engine_version=ENGINE_VERSION, candidate_count=len(candidates))
    db.add(run)
    db.flush()
    for rank, cid in enumerate(order, start=1):
        cs = scores[cid]
        detail = cs.to_dict()
        detail["explanation"] = explain(cs)
        detail["rank_by"] = rank_by
        db.add(DiscoveryResult(run_id=run.id, site_id=cid, rank=rank, score=cs.score,
                               detail=detail))
    db.commit()
    db.refresh(run)
    return run


def serialize_run(db: Session, run: DiscoveryRun, include_features: bool = True) -> dict:
    target = db.get(Site, run.target_site_id)
    results = []
    for r in run.results:
        d = dict(r.detail)
        if not include_features:
            d.pop("features", None)
        results.append({
            "rank": r.rank, "site_id": r.site_id, "name": r.site.name,
            "region": r.site.region, "latitude": r.site.latitude,
            "longitude": r.site.longitude, **d,
        })
    return {
        "id": run.id, "mission_id": run.mission_id, "mission_name": run.mission.name,
        "profile_key": run.mission.profile_key,
        "target": {"id": target.id, "name": target.name, "body": target.body,
                   "latitude": target.latitude, "longitude": target.longitude},
        "weights": run.weights, "engine_version": run.engine_version,
        "created_at": run.created_at.isoformat(), "candidate_count": run.candidate_count,
        "limitations": limitations_for(target.body),
        "environment": {"earth": ENVIRONMENT["earth"], target.body: ENVIRONMENT[target.body]},
        "results": results,
    }
