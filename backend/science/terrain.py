"""Deterministic terrain metrics computed from an elevation grid.

All metrics are computed on a regular metric grid (see ``science.resample``) so
values from different DEMs and bodies are directly comparable *at that scale*.

- Slope: arctan(|grad z|) using central differences (``numpy.gradient``),
  one-sided at the window edge. Degrees.
- Terrain Ruggedness Index (TRI): mean absolute elevation difference between a
  cell and its 8 neighbours (the "Wilson" variant used by GDAL's gdaldem TRI).
  Metres; edge cells are excluded.
- Local relief: 95th minus 5th percentile of elevation in the window. Metres.
- Steep-slope fraction: fraction of cells with slope > 15 degrees (a commonly used
  landing/traverse hazard threshold).
"""

import numpy as np

STEEP_SLOPE_DEG = 15.0
MIN_VALID_FRACTION = 0.9


class TerrainError(ValueError):
    """Raised when a grid has too little valid data for terrain analysis."""


def slope_degrees(z: np.ndarray, cell_m: float) -> np.ndarray:
    if cell_m <= 0:
        raise ValueError("cell_m must be positive.")
    dzdy, dzdx = np.gradient(z.astype("float64"), cell_m)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def ruggedness_index(z: np.ndarray) -> np.ndarray:
    """TRI per interior cell (NaN on the border)."""
    z = z.astype("float64")
    out = np.full(z.shape, np.nan)
    if min(z.shape) < 3:
        return out
    centre = z[1:-1, 1:-1]
    diffs = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neighbour = z[1 + dr:z.shape[0] - 1 + dr, 1 + dc:z.shape[1] - 1 + dc]
            diffs.append(np.abs(neighbour - centre))
    out[1:-1, 1:-1] = np.mean(diffs, axis=0)
    return out


def terrain_metrics(z: np.ndarray, cell_m: float,
                    min_valid_fraction: float = MIN_VALID_FRACTION) -> dict:
    """Compute summary terrain metrics; raise TerrainError if data are insufficient."""
    if z.ndim != 2 or min(z.shape) < 5:
        raise TerrainError("Elevation grid must be 2-D and at least 5 x 5 cells.")
    valid = float(np.mean(~np.isnan(z)))
    if valid < min_valid_fraction:
        raise TerrainError(
            f"Only {valid:.0%} of cells have elevation data "
            f"(minimum {min_valid_fraction:.0%}).")
    slope = slope_degrees(z, cell_m)
    tri = ruggedness_index(z)
    s = slope[~np.isnan(slope)]
    t = tri[~np.isnan(tri)]
    e = z[~np.isnan(z)]
    return {
        "slope_mean_deg": float(np.mean(s)),
        "slope_median_deg": float(np.median(s)),
        "slope_p90_deg": float(np.percentile(s, 90)),
        "tri_mean_m": float(np.mean(t)),
        "relief_p95_p5_m": float(np.percentile(e, 95) - np.percentile(e, 5)),
        "steep_slope_fraction": float(np.mean(s > STEEP_SLOPE_DEG)),
        "elevation_min_m": float(e.min()),
        "elevation_max_m": float(e.max()),
        "elevation_mean_m": float(e.mean()),
        "valid_fraction": valid,
        "cell_m": cell_m,
    }


def native_slope_mean(arr: np.ndarray, dy_m: float, dx_m: float) -> float | None:
    """Mean slope at native resolution (display only; not comparable across DEMs)."""
    dzdy, dzdx = np.gradient(arr.astype("float64"), dy_m, dx_m)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    slope = slope[~np.isnan(slope)]
    return float(np.mean(slope)) if slope.size else None


def hillshade(z: np.ndarray, cell_m: float, azimuth_deg: float = 315.0,
              altitude_deg: float = 45.0) -> np.ndarray:
    """Standard Lambertian hillshade in [0, 1] (visualisation only)."""
    dzdy, dzdx = np.gradient(z.astype("float64"), cell_m)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az, alt = np.radians(azimuth_deg), np.radians(altitude_deg)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)
