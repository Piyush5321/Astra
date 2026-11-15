"""Similarity engine: kernels, weights, missing data, uncertainty, ranking."""

import math

import pytest

from backend.science.explain import explain
from backend.science.features import FEATURES
from backend.science.normalization import FeatureValue, min_max_normalize
from backend.science.profiles import PROFILES, normalize_weights, profile_weights
from backend.science.similarity import (
    gaussian_interval,
    gaussian_similarity,
    jaccard,
    rank_candidates,
    score_candidate,
)

EQUAL = {"geology": 1, "terrain": 1, "thermal": 1, "resources": 1, "hazards": 1}


def full_site(**overrides):
    base = {
        "geology_tags": FeatureValue("geology_tags", tags=("basaltic_volcanic",)),
        "resource_tags": FeatureValue("resource_tags", tags=("water_ice",)),
        "hazard_tags": FeatureValue("hazard_tags", tags=("fine_dust",)),
        "slope_mean_deg": FeatureValue("slope_mean_deg", 5.0),
        "tri_mean_m": FeatureValue("tri_mean_m", 20.0),
        "relief_p95_p5_m": FeatureValue("relief_p95_p5_m", 500.0),
        "surface_temp_max_k": FeatureValue("surface_temp_max_k", 300.0),
        "surface_temp_min_k": FeatureValue("surface_temp_min_k", 200.0),
        "surface_temp_diurnal_range_k": FeatureValue("surface_temp_diurnal_range_k", 50.0),
        "annual_precipitation_mm": FeatureValue("annual_precipitation_mm", 0.0),
        "steep_slope_fraction": FeatureValue("steep_slope_fraction", 0.05),
    }
    base.update(overrides)
    return base


def test_gaussian_kernel_reference_points():
    assert gaussian_similarity(0, 3) == 1.0
    assert math.isclose(gaussian_similarity(3, 3), math.exp(-0.5))
    assert gaussian_similarity(-3, 3) == gaussian_similarity(3, 3)
    with pytest.raises(ValueError):
        gaussian_similarity(1, 0)


def test_gaussian_interval_contains_point_value():
    lo, hi = gaussian_interval(4.0, 1.0, 3.0)
    assert lo < gaussian_similarity(4.0, 3.0) < hi
    assert gaussian_interval(0.5, 1.0, 3.0)[1] == 1.0  # interval includes d = 0


def test_jaccard():
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a"}, set()) == 0.0


def test_identical_sites_score_100():
    s = full_site()
    r = score_candidate(s, s, EQUAL)
    assert r.score == pytest.approx(100.0)
    assert r.coverage == pytest.approx(1.0)
    assert r.bound_low == pytest.approx(100.0) and r.bound_high == pytest.approx(100.0)
    assert r.confidence == "high"


def test_score_formula_matches_manual_weighted_mean():
    cand = full_site(slope_mean_deg=FeatureValue("slope_mean_deg", 8.0))
    r = score_candidate(cand, full_site(), EQUAL)
    # Only slope differs: s = exp(-0.5), feature weight 0.2 * 0.4 = 0.08.
    expected = 100 * (1 - 0.08 + 0.08 * math.exp(-0.5))
    assert r.score == pytest.approx(expected)


def test_missing_data_is_not_a_match():
    target = full_site(surface_temp_max_k=FeatureValue("surface_temp_max_k", None,
                                                       missing_reason="no reference"))
    cand = full_site(slope_mean_deg=FeatureValue("slope_mean_deg", 20.0))
    r = score_candidate(cand, target, EQUAL)
    missing_w = 0.2 * 0.3
    assert r.coverage == pytest.approx(1 - missing_w)
    assert r.bound_low < r.score < r.bound_high
    # Upper bound treats the missing feature as a perfect match, lower bound as zero.
    assert r.bound_high - r.bound_low == pytest.approx(100 * missing_w)
    feat = next(f for f in r.features if f.key == "surface_temp_max_k")
    assert feat.status == "missing_target" and "no reference" in feat.missing_reason
    assert any("not scored" in m for m in explain(r)["missing"])


def test_no_overlap_gives_no_score():
    empty = {f.key: FeatureValue(f.key) for f in FEATURES}
    r = score_candidate(empty, full_site(), EQUAL)
    assert r.score is None and r.coverage == 0 and r.confidence == "low"
    assert r.bound_low == 0 and r.bound_high == pytest.approx(100)


def test_uncertainty_widens_interval():
    cand = full_site(surface_temp_max_k=FeatureValue("surface_temp_max_k", 340.0, uncertainty=10))
    r = score_candidate(cand, full_site(), EQUAL)
    assert r.score_low < r.score < r.score_high


def test_zero_weight_dimension_is_ignored():
    w = dict(EQUAL, thermal=0)
    cand = full_site(surface_temp_max_k=FeatureValue("surface_temp_max_k", 1000.0 - 600))
    r = score_candidate(cand, full_site(), w)
    assert r.score == pytest.approx(100.0)


def test_weights_validation_and_profiles():
    assert sum(normalize_weights({"geology": 2, "terrain": 2}).values()) == pytest.approx(1)
    with pytest.raises(ValueError):
        normalize_weights({"gravity": 1})
    with pytest.raises(ValueError):
        normalize_weights({"geology": -1, "terrain": 2})
    with pytest.raises(ValueError):
        normalize_weights({})
    for key in PROFILES:
        assert sum(profile_weights(key).values()) == pytest.approx(1)


def test_scoring_is_deterministic():
    cand = full_site(tri_mean_m=FeatureValue("tri_mean_m", 7.3))
    a = score_candidate(cand, full_site(), EQUAL).to_dict()
    b = score_candidate(cand, full_site(), EQUAL).to_dict()
    assert a == b


def test_ranking_orders_and_puts_unscorable_last():
    good = score_candidate(full_site(), full_site(), EQUAL)
    worse = score_candidate(full_site(slope_mean_deg=FeatureValue("slope_mean_deg", 30.0)),
                            full_site(), EQUAL)
    none = score_candidate({f.key: FeatureValue(f.key) for f in FEATURES}, full_site(), EQUAL)
    assert rank_candidates({"n": none, "w": worse, "g": good}) == ["g", "w", "n"]


def test_log_transform_is_scale_invariant():
    a = score_candidate(full_site(tri_mean_m=FeatureValue("tri_mean_m", 40.0)),
                        full_site(tri_mean_m=FeatureValue("tri_mean_m", 20.0)), EQUAL)
    b = score_candidate(full_site(tri_mean_m=FeatureValue("tri_mean_m", 400.0)),
                        full_site(tri_mean_m=FeatureValue("tri_mean_m", 200.0)), EQUAL)
    assert a.score == pytest.approx(b.score)


def test_min_max_normalize_display_only():
    assert min_max_normalize({"a": 1.0, "b": 3.0, "c": None}) == {"a": 0.0, "b": 1.0, "c": None}
    assert min_max_normalize({"a": 2.0, "b": 2.0}) == {"a": 0.5, "b": 0.5}
