"""Registry of scored features: dimension, unit, similarity function and scale.

Each continuous feature uses a Gaussian kernel on the (optionally log-transformed)
difference between candidate and target:

    s = exp(-0.5 * (d / scale)^2),  d = T(candidate) - T(target)

``scale`` is a fixed, documented tolerance (independent of which candidates are
in the database), so scores are reproducible and comparable between runs.
At d = scale, s = 0.61; at d = 2*scale, s = 0.14.

Categorical features use the Jaccard index of curated tag sets.
``subweight`` splits a dimension's mission weight among its features (sums to 1
within each dimension).
"""

from dataclasses import dataclass

DIMENSIONS: dict[str, str] = {
    "geology": "Geology",
    "terrain": "Terrain",
    "thermal": "Thermal & climate",
    "resources": "Resources",
    "hazards": "Hazards",
}


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    dimension: str
    label: str
    unit: str
    kind: str  # continuous | categorical
    subweight: float
    transform: str = "identity"  # identity | log10 | log10_1p
    scale: float = 1.0  # in transformed units
    valid_range: tuple[float, float] = (float("-inf"), float("inf"))
    description: str = ""
    rationale: str = ""


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        "geology_tags", "geology", "Geological setting", "tags", "categorical", 1.0,
        description="Curated qualitative geology descriptors.",
        rationale="Jaccard index |A n B| / |A u B| of curated tag sets."),
    FeatureSpec(
        "slope_mean_deg", "terrain", "Mean slope", "deg", "continuous", 0.4,
        scale=3.0, valid_range=(0, 90),
        description="Mean slope on the 500 m analysis grid over a 30 km window.",
        rationale="3 deg tolerance: separates flat plains (<2 deg) from rolling (~5 deg) "
        "and mountainous (>10 deg) terrain at 500 m scale."),
    FeatureSpec(
        "tri_mean_m", "terrain", "Terrain ruggedness (TRI)", "m", "continuous", 0.3,
        transform="log10", scale=0.3, valid_range=(0, 5000),
        description="Mean absolute elevation difference to 8 neighbours (500 m cells).",
        rationale="Compared in log10 space; 0.3 = a factor of ~2 difference in ruggedness."),
    FeatureSpec(
        "relief_p95_p5_m", "terrain", "Local relief (p95 - p5)", "m", "continuous", 0.3,
        transform="log10", scale=0.3, valid_range=(0, 20000),
        description="Robust elevation range within the 30 km window.",
        rationale="Compared in log10 space; 0.3 = a factor of ~2 difference in relief."),
    FeatureSpec(
        "surface_temp_max_k", "thermal", "Surface temperature maximum", "K", "continuous",
        0.3, scale=30.0, valid_range=(20, 450),
        description="Earth: 95th percentile of daily POWER skin-temperature maxima. "
        "Targets: literature typical daytime maximum.",
        rationale="30 K tolerance, comparable to reference-value uncertainties."),
    FeatureSpec(
        "surface_temp_min_k", "thermal", "Surface temperature minimum", "K", "continuous",
        0.3, scale=30.0, valid_range=(20, 400),
        description="Earth: 5th percentile of daily POWER skin-temperature minima. "
        "Targets: literature typical night-time minimum.",
        rationale="30 K tolerance."),
    FeatureSpec(
        "surface_temp_diurnal_range_k", "thermal", "Diurnal temperature range", "K",
        "continuous", 0.2, scale=30.0, valid_range=(0, 400),
        description="Earth: mean daily (TS_MAX - TS_MIN). Targets: literature range.",
        rationale="30 K tolerance."),
    FeatureSpec(
        "annual_precipitation_mm", "thermal", "Liquid precipitation (aridity)", "mm/yr",
        "continuous", 0.2, transform="log10_1p", scale=1.0, valid_range=(0, 20000),
        description="Earth: mean annual POWER PRECTOTCORR. Targets: 0 by physical "
        "constraint (no liquid precipitation).",
        rationale="log10(1+P) with a tolerance of one order of magnitude: against 0 mm/yr, "
        "5 mm/yr scores 0.72, 30 mm/yr 0.33, 100 mm/yr 0.13, 1000 mm/yr 0.01."),
    FeatureSpec(
        "resource_tags", "resources", "In-situ resources", "tags", "categorical", 1.0,
        description="Curated resource descriptors.",
        rationale="Jaccard index of curated tag sets."),
    FeatureSpec(
        "steep_slope_fraction", "hazards", "Steep-slope fraction (>15 deg)", "fraction",
        "continuous", 0.5, scale=0.1, valid_range=(0, 1),
        description="Fraction of 500 m cells steeper than 15 deg.",
        rationale="0.1 tolerance (10 percentage points of the window)."),
    FeatureSpec(
        "hazard_tags", "hazards", "Environmental hazards", "tags", "categorical", 0.5,
        description="Curated hazard descriptors with Earth analogs.",
        rationale="Jaccard index of curated tag sets."),
)

FEATURES_BY_KEY: dict[str, FeatureSpec] = {f.key: f for f in FEATURES}

# Descriptive (not scored) features recorded in the measurements table.
DESCRIPTIVE_FEATURES: dict[str, tuple[str, str, str]] = {
    "slope_p90_deg": ("terrain", "Slope 90th percentile", "deg"),
    "slope_median_deg": ("terrain", "Median slope", "deg"),
    "elevation_mean_m": ("terrain", "Mean elevation (body datum; not compared)", "m"),
    "elevation_min_m": ("terrain", "Minimum elevation (body datum; not compared)", "m"),
    "elevation_max_m": ("terrain", "Maximum elevation (body datum; not compared)", "m"),
    "slope_mean_native_deg": ("terrain", "Mean slope at native DEM resolution", "deg"),
    "mean_skin_temp_k": ("thermal", "Mean skin temperature", "K"),
    "mean_relative_humidity_pct": ("thermal", "Mean relative humidity at 2 m", "%"),
    "mean_solar_irradiance_kwh_m2_day": ("thermal", "Mean all-sky surface shortwave", "kWh/m2/day"),
    "mean_wind_speed_ms": ("thermal", "Mean wind speed at 2 m", "m/s"),
}


def _check_subweights() -> None:
    for dim in DIMENSIONS:
        total = sum(f.subweight for f in FEATURES if f.dimension == dim)
        if abs(total - 1.0) > 1e-9:
            raise AssertionError(f"Subweights for {dim} sum to {total}, expected 1.")


_check_subweights()
