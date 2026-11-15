"""Terrain metrics and resampling against analytic surfaces."""

import math

import numpy as np
import pytest

from backend.science.resample import to_analysis_grid
from backend.science.terrain import (
    TerrainError,
    ruggedness_index,
    slope_degrees,
    terrain_metrics,
)


def plane(n=40, cell=500.0, slope_deg=10.0):
    gradient = math.tan(math.radians(slope_deg))
    x = np.arange(n) * cell
    return np.tile(x * gradient, (n, 1))


def test_plane_slope_is_exact():
    z = plane(slope_deg=10.0)
    s = slope_degrees(z, 500.0)
    assert np.allclose(s, 10.0, atol=1e-9)


def test_flat_surface_metrics_are_zero():
    m = terrain_metrics(np.full((20, 20), 123.0), 500.0)
    assert m["slope_mean_deg"] == 0
    assert m["tri_mean_m"] == 0
    assert m["relief_p95_p5_m"] == 0
    assert m["steep_slope_fraction"] == 0


def test_tri_of_plane_matches_neighbour_geometry():
    # For a plane rising d per cell in x, neighbour |dz| are d (x6) and 0 (x2) -> mean 0.75 d.
    z = plane(n=10, slope_deg=45.0)  # d = 500 m per cell
    tri = ruggedness_index(z)
    assert np.isnan(tri[0, 0])
    assert np.allclose(tri[1:-1, 1:-1], 0.75 * 500.0)


def test_steep_fraction_threshold():
    z = np.zeros((30, 30))
    z[:, 15:] = plane(n=30, slope_deg=20.0)[:, :15]  # right half 20 deg
    m = terrain_metrics(z, 500.0)
    assert 0.4 < m["steep_slope_fraction"] < 0.6


def test_insufficient_data_raises():
    z = np.full((20, 20), np.nan)
    z[:5] = 1.0
    with pytest.raises(TerrainError):
        terrain_metrics(z, 500.0)


def test_block_mean_resampling_preserves_plane_slope():
    # Native 30 m projected grid of a 5 deg plane -> 500 m analysis grid.
    n, cell = 1100, 30.0
    g = math.tan(math.radians(5.0))
    x = (np.arange(n) - n / 2) * cell
    native = np.tile(x * g, (n, 1)).astype("float32")
    half = n * cell / 2
    georef = {"kind": "projected", "transform": [cell, 0, -half, 0, -cell, half],
              "center_xy": [0.0, 0.0]}
    grid, info = to_analysis_grid(native, georef)
    assert info["method"] == "block_mean"
    assert grid.shape == (60, 60)
    assert info["valid_fraction"] == 1.0
    assert abs(terrain_metrics(grid, 500.0)["slope_mean_deg"] - 5.0) < 0.05


def test_bilinear_resampling_on_geographic_grid():
    # ~474 m lunar grid of a north-south plane; bilinear path must keep the slope.
    r, ppd, lat0 = 1_737_400.0, 64, 0.0
    rows, cols = 140, 140  # +/-15 km is +/-0.49 deg on the Moon
    lat = 1.0 - (np.arange(rows) + 0.5) / ppd
    dy = np.radians(lat - lat0) * r
    native = np.repeat((dy * math.tan(math.radians(3.0)))[:, None], cols, axis=1)
    georef = {"kind": "geographic", "transform": [1 / ppd, 0, -1.1, 0, -1 / ppd, 1.0],
              "radius_m": r, "center": [lat0, 0.0]}
    grid, info = to_analysis_grid(native.astype("float32"), georef)
    assert info["method"] == "bilinear"
    assert info["valid_fraction"] == 1.0
    assert abs(terrain_metrics(grid, 500.0)["slope_mean_deg"] - 3.0) < 0.05
