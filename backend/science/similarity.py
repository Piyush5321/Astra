"""Deterministic, transparent similarity scoring.

Score (0-100) for a candidate against a target with dimension weights W_d:

    w_f   = W_d(f) * subweight_f                     (effective feature weight)
    score = 100 * sum_{f valid} w_f * s_f / sum_{f valid} w_f

A feature is *valid* only if both candidate and target values exist. Missing
features are never counted as matches; instead ASTRA reports:

- coverage = sum_{valid} w_f / sum_{all} w_f
- measurement interval: score recomputed with each s_f at the lowest / highest
  value compatible with the stated uncertainties
- full bounds: the score over *all* features if every missing feature had
  similarity 0 (lower) or 1 (upper), combined with the measurement interval.

Uncertainty for continuous features: u = u_candidate + u_target (linear, worst
case), propagated to log space by first-order derivatives. The difference |d| is
then bounded by [max(0, |d| - u), |d| + u].
"""

import math
from dataclasses import asdict, dataclass, field

from backend.science.features import DIMENSIONS, FEATURES, FeatureSpec
from backend.science.normalization import FeatureValue, transform

ENGINE_VERSION = "1.0.0"


def gaussian_similarity(d: float, scale: float) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive.")
    return math.exp(-0.5 * (d / scale) ** 2)


def gaussian_interval(d: float, u: float, scale: float) -> tuple[float, float]:
    """(lowest, highest) similarity for differences within [|d|-u, |d|+u]."""
    ad = abs(d)
    return gaussian_similarity(ad + u, scale), gaussian_similarity(max(0.0, ad - u), scale)


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard index; two empty tag sets are defined as identical (1.0)."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _transformed_uncertainty(spec: FeatureSpec, x: float, u: float | None) -> float:
    if not u:
        return 0.0
    if spec.transform == "identity":
        return u
    if spec.transform == "log10":
        return u / (max(x, 0.1) * math.log(10))
    if spec.transform == "log10_1p":
        return u / ((1.0 + max(x, 0.0)) * math.log(10))
    raise ValueError(spec.transform)


@dataclass
class FeatureScore:
    key: str
    dimension: str
    label: str
    unit: str
    kind: str
    weight: float
    status: str  # scored | missing_candidate | missing_target | missing_both
    similarity: float | None = None
    similarity_low: float | None = None
    similarity_high: float | None = None
    candidate_value: float | None = None
    target_value: float | None = None
    candidate_tags: list[str] | None = None
    target_tags: list[str] | None = None
    difference: float | None = None
    combined_uncertainty: float | None = None
    scale: float | None = None
    transform: str | None = None
    missing_reason: str = ""


def feature_similarity(spec: FeatureSpec, cand: FeatureValue | None,
                       target: FeatureValue | None, weight: float) -> FeatureScore:
    fs = FeatureScore(key=spec.key, dimension=spec.dimension, label=spec.label,
                      unit=spec.unit, kind=spec.kind, weight=weight, status="scored")
    c_missing = cand is None or cand.is_missing
    t_missing = target is None or target.is_missing
    if spec.kind == "categorical":
        fs.candidate_tags = None if c_missing else sorted(cand.tags)
        fs.target_tags = None if t_missing else sorted(target.tags)
    else:
        fs.candidate_value = None if c_missing else cand.value
        fs.target_value = None if t_missing else target.value
        fs.scale, fs.transform = spec.scale, spec.transform
    if c_missing or t_missing:
        fs.status = ("missing_both" if c_missing and t_missing
                     else "missing_candidate" if c_missing else "missing_target")
        reasons = []
        if c_missing:
            reasons.append("candidate: " + ((cand.missing_reason if cand else "") or "no value"))
        if t_missing:
            reasons.append("target: " + ((target.missing_reason if target else "") or "no value"))
        fs.missing_reason = "; ".join(reasons)
        return fs

    if spec.kind == "categorical":
        s = jaccard(set(cand.tags), set(target.tags))
        fs.similarity = fs.similarity_low = fs.similarity_high = s
        return fs

    tc, tt = transform(spec, cand.value), transform(spec, target.value)
    d = tc - tt
    u = (_transformed_uncertainty(spec, cand.value, cand.uncertainty)
         + _transformed_uncertainty(spec, target.value, target.uncertainty))
    fs.difference = cand.value - target.value
    fs.combined_uncertainty = (cand.uncertainty or 0.0) + (target.uncertainty or 0.0)
    fs.similarity = gaussian_similarity(d, spec.scale)
    fs.similarity_low, fs.similarity_high = gaussian_interval(d, u, spec.scale)
    return fs


@dataclass
class DimensionScore:
    dimension: str
    label: str
    weight: float
    score: float | None
    coverage: float


@dataclass
class CandidateScore:
    score: float | None
    score_low: float | None
    score_high: float | None
    bound_low: float
    bound_high: float
    coverage: float
    confidence: str
    dimensions: list[DimensionScore]
    features: list[FeatureScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def confidence_label(coverage: float, bound_low: float, bound_high: float) -> str:
    width = bound_high - bound_low
    if coverage >= 0.85 and width <= 20:
        return "high"
    if coverage >= 0.6 and width <= 40:
        return "medium"
    return "low"


def score_candidate(candidate: dict[str, FeatureValue], target: dict[str, FeatureValue],
                    weights: dict[str, float]) -> CandidateScore:
    """Score one candidate. ``weights`` are dimension weights (any positive scale)."""
    total_w = sum(weights.get(d, 0.0) for d in DIMENSIONS)
    if total_w <= 0:
        raise ValueError("Dimension weights must have a positive sum.")
    norm = {d: weights.get(d, 0.0) / total_w for d in DIMENSIONS}

    features = [feature_similarity(spec, candidate.get(spec.key), target.get(spec.key),
                                   norm[spec.dimension] * spec.subweight)
                for spec in FEATURES]
    active = [f for f in features if f.weight > 0]
    valid = [f for f in active if f.status == "scored"]
    w_all = sum(f.weight for f in active)
    w_valid = sum(f.weight for f in valid)
    w_missing = w_all - w_valid

    if w_valid > 0:
        score = 100 * sum(f.weight * f.similarity for f in valid) / w_valid
        score_low = 100 * sum(f.weight * f.similarity_low for f in valid) / w_valid
        score_high = 100 * sum(f.weight * f.similarity_high for f in valid) / w_valid
    else:
        score = score_low = score_high = None
    bound_low = 100 * sum(f.weight * f.similarity_low for f in valid) / w_all
    bound_high = 100 * (sum(f.weight * f.similarity_high for f in valid) + w_missing) / w_all
    coverage = w_valid / w_all

    dims = []
    for d, label in DIMENSIONS.items():
        d_feats = [f for f in features if f.dimension == d]
        d_valid = [f for f in d_feats if f.status == "scored"]
        sub_all = sum(FEATURES_SUBWEIGHT[f.key] for f in d_feats)
        sub_valid = sum(FEATURES_SUBWEIGHT[f.key] for f in d_valid)
        d_score = (100 * sum(FEATURES_SUBWEIGHT[f.key] * f.similarity for f in d_valid)
                   / sub_valid) if sub_valid > 0 else None
        dims.append(DimensionScore(d, label, norm[d], d_score,
                                   sub_valid / sub_all if sub_all else 0.0))

    return CandidateScore(
        score=score, score_low=score_low, score_high=score_high,
        bound_low=bound_low, bound_high=bound_high, coverage=coverage,
        confidence=confidence_label(coverage, bound_low, bound_high),
        dimensions=dims, features=features,
    )


FEATURES_SUBWEIGHT = {f.key: f.subweight for f in FEATURES}


def rank_candidates(scores: dict[str, CandidateScore], rank_by: str = "score") -> list[str]:
    """Return candidate ids ordered best-first. Unscorable candidates go last."""
    if rank_by not in {"score", "bound_low"}:
        raise ValueError("rank_by must be 'score' or 'bound_low'.")

    def key(item):
        cid, cs = item
        primary = cs.score if rank_by == "score" else cs.bound_low
        return (primary is None, -(primary or 0.0), -cs.coverage, cid)

    return [cid for cid, _ in sorted(scores.items(), key=key)]
