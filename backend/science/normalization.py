"""Feature transforms, validation, missing-data handling and display normalisation.

Scoring never imputes missing values. ``FeatureValue.is_missing`` features are
excluded from the weighted score and reported through coverage and bounds.
"""

import math
from dataclasses import dataclass

from backend.science.features import FEATURES_BY_KEY, FeatureSpec


@dataclass(frozen=True)
class FeatureValue:
    """A feature value as used by the scoring engine."""

    key: str
    value: float | None = None
    tags: tuple[str, ...] | None = None
    uncertainty: float | None = None
    source_type: str = ""
    missing_reason: str = ""

    @property
    def is_missing(self) -> bool:
        spec = FEATURES_BY_KEY.get(self.key)
        if spec is not None and spec.kind == "categorical":
            return self.tags is None
        return self.value is None or (isinstance(self.value, float) and math.isnan(self.value))


def transform(spec: FeatureSpec, x: float) -> float:
    if spec.transform == "identity":
        return x
    if spec.transform == "log10":
        # Floor at 0.1 unit so tiny or zero ruggedness does not diverge.
        return math.log10(max(x, 0.1))
    if spec.transform == "log10_1p":
        return math.log10(1.0 + max(x, 0.0))
    raise ValueError(f"Unknown transform {spec.transform!r}.")


def validate_value(spec: FeatureSpec, value: float) -> None:
    """Raise ValueError if a continuous value is non-finite or out of range."""
    if not math.isfinite(value):
        raise ValueError(f"{spec.key}: value must be finite, got {value!r}.")
    lo, hi = spec.valid_range
    if not lo <= value <= hi:
        raise ValueError(f"{spec.key}: value {value} outside valid range [{lo}, {hi}].")


def min_max_normalize(values: dict[str, float | None]) -> dict[str, float | None]:
    """Scale values to [0, 1] for display (charts). Missing values stay None.

    Used only for visual comparison across sites, never for scoring, because it
    depends on which sites are included.
    """
    present = [v for v in values.values() if v is not None]
    if not present:
        return {k: None for k in values}
    lo, hi = min(present), max(present)
    span = hi - lo
    return {k: (None if v is None else (0.5 if span == 0 else (v - lo) / span))
            for k, v in values.items()}
