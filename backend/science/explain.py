"""Deterministic, template-based explanations of similarity results.

Explanations are generated from FeatureScore records only, so every statement
corresponds to a computed number.
"""

from backend.science.similarity import CandidateScore, FeatureScore

STRONG = 0.8
WEAK = 0.5

_DIRECTION_WORDS = {
    "slope_mean_deg": ("steeper", "gentler"),
    "tri_mean_m": ("more rugged", "smoother"),
    "relief_p95_p5_m": ("higher in relief", "lower in relief"),
    "surface_temp_max_k": ("warmer at its maximum", "cooler at its maximum"),
    "surface_temp_min_k": ("warmer at its minimum", "colder at its minimum"),
    "surface_temp_diurnal_range_k": ("more variable day-to-night",
                                     "less variable day-to-night"),
    "annual_precipitation_mm": ("wetter", "drier"),
    "steep_slope_fraction": ("steeper overall", "less steep overall"),
}


def fmt_value(value: float | None, unit: str, key: str = "") -> str:
    if value is None:
        return "n/a"
    if unit == "fraction":
        return f"{value * 100:.1f}%"
    if unit == "K" and "range" in key:  # a temperature difference has no Celsius offset
        return f"{value:.0f} K"
    if unit == "K":
        return f"{value:.0f} K ({value - 273.15:.0f} C)"
    if abs(value) >= 100:
        return f"{value:,.0f} {unit}"
    return f"{value:.2f} {unit}"


def _continuous_sentence(f: FeatureScore) -> str:
    more, less = _DIRECTION_WORDS.get(f.key, ("higher", "lower"))
    if f.similarity >= STRONG:
        verdict = "close match"
    else:
        verdict = "candidate is " + (more if (f.difference or 0) > 0 else less)
    return (f"{f.label}: candidate {fmt_value(f.candidate_value, f.unit, f.key)} vs target "
            f"{fmt_value(f.target_value, f.unit, f.key)} - {verdict} "
            f"(similarity {f.similarity:.2f}).")


def _categorical_sentence(f: FeatureScore) -> str:
    cand, targ = set(f.candidate_tags or []), set(f.target_tags or [])
    shared = sorted(cand & targ)
    lacking = sorted(targ - cand)
    extra = sorted(cand - targ)
    parts = [f"{f.label} (Jaccard {f.similarity:.2f}):"]
    parts.append(f"shared [{', '.join(shared) or 'none'}]")
    if lacking:
        parts.append(f"target-only [{', '.join(lacking)}]")
    if extra:
        parts.append(f"candidate-only [{', '.join(extra)}]")
    return " ".join(parts) + "."


def explain(result: CandidateScore) -> dict:
    """Return strengths, mismatches and missing-data notes for a candidate score."""
    strengths, mismatches, partial, missing = [], [], [], []
    for f in result.features:
        if f.weight <= 0:
            continue
        if f.status != "scored":
            missing.append(f"{f.label} not scored - {f.missing_reason.rstrip('.')}.")
            continue
        sentence = (_categorical_sentence(f) if f.kind == "categorical"
                    else _continuous_sentence(f))
        if f.similarity >= STRONG:
            strengths.append(sentence)
        elif f.similarity < WEAK:
            mismatches.append(sentence)
        else:
            partial.append(sentence)
    summary = (
        "Not scorable: no feature has data for both sites." if result.score is None else
        f"Score {result.score:.1f}/100 over {result.coverage:.0%} of weighted features "
        f"(measurement range {result.score_low:.1f}-{result.score_high:.1f}; "
        f"bounds including missing data {result.bound_low:.1f}-{result.bound_high:.1f}; "
        f"confidence {result.confidence})."
    )
    return {"summary": summary, "strengths": strengths, "partial": partial,
            "mismatches": mismatches, "missing": missing}
