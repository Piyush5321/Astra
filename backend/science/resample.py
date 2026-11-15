"""Resample native DEM subsets onto ASTRA's common local metric analysis grid.

Slope and roughness depend strongly on horizontal resolution, so every body is
compared on the same grid: a square window of ``WINDOW_M`` metres with
``CELL_M`` metre cells centred on the site.

``georef`` dictionaries describe a native array:
- ``{"kind": "geographic", "transform": [a, b, c, d, e, f], "radius_m": R,
   "center": [lat0, lon0]}`` - regular lon/lat grid (affine as in rasterio:
   lon = c + a*col, lat = f + e*row at pixel corners). Local coordinates use a
   spherical local tangent approximation: x = R cos(lat) dlon, y = R dlat.
- ``{"kind": "projected", "transform": [...], "center_xy": [x0, y0]}`` - grid
   already in metres (polar stereographic, scale ~1 near the pole).

Method: if the native spacing is <= CELL_M / 2, each analysis cell is the mean
of native pixel centres falling inside it (block averaging). Otherwise (native
spacing close to the cell size) bilinear interpolation at cell centres is used.
"""

import math

import numpy as np

CELL_M = 500.0
WINDOW_M = 30_000.0


def _native_spacing(georef: dict, shape: tuple[int, int]) -> float:
    a, _, _, _, e, _ = georef["transform"]
    if georef["kind"] == "projected":
        return min(abs(a), abs(e))
    lat0 = georef["center"][0]
    r = georef["radius_m"]
    dy = math.radians(abs(e)) * r
    dx = math.radians(abs(a)) * r * math.cos(math.radians(lat0))
    return min(dx, dy)


def native_to_local(georef: dict, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Local metric (x east, y north) of native pixel centres."""
    a, _, c, _, e, f = georef["transform"]
    u = c + a * (cols + 0.5)
    v = f + e * (rows + 0.5)
    if georef["kind"] == "projected":
        x0, y0 = georef["center_xy"]
        return u - x0, v - y0
    lat0, lon0 = georef["center"]
    r = georef["radius_m"]
    x = r * np.cos(np.radians(v)) * np.radians(u - lon0)
    y = r * np.radians(v - lat0)
    return x, y


def local_to_native(georef: dict, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fractional native (row, col) index, relative to pixel centres, of local points."""
    a, _, c, _, e, f = georef["transform"]
    if georef["kind"] == "projected":
        x0, y0 = georef["center_xy"]
        u, v = x + x0, y + y0
    else:
        lat0, lon0 = georef["center"]
        r = georef["radius_m"]
        v = lat0 + np.degrees(y / r)
        u = lon0 + np.degrees(x / (r * np.cos(np.radians(v))))
    return (v - f) / e - 0.5, (u - c) / a - 0.5


def _bilinear(arr: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    h, w = arr.shape
    r0 = np.floor(rows).astype(int)
    c0 = np.floor(cols).astype(int)
    fr, fc = rows - r0, cols - c0
    out = np.full(rows.shape, np.nan, dtype="float64")
    ok = (r0 >= 0) & (c0 >= 0) & (r0 + 1 < h) & (c0 + 1 < w)
    r0o, c0o, fro, fco = r0[ok], c0[ok], fr[ok], fc[ok]
    v00, v01 = arr[r0o, c0o], arr[r0o, c0o + 1]
    v10, v11 = arr[r0o + 1, c0o], arr[r0o + 1, c0o + 1]
    out[ok] = (v00 * (1 - fro) * (1 - fco) + v01 * (1 - fro) * fco
               + v10 * fro * (1 - fco) + v11 * fro * fco)
    return out


def to_analysis_grid(arr: np.ndarray, georef: dict, cell_m: float = CELL_M,
                     window_m: float = WINDOW_M) -> tuple[np.ndarray, dict]:
    """Return (grid, info). ``grid[0]`` is the northern row; NaN marks no data."""
    n = int(round(window_m / cell_m))
    spacing = _native_spacing(georef, arr.shape)
    half = n * cell_m / 2
    if spacing <= cell_m / 2:
        rows, cols = np.indices(arr.shape)
        x, y = native_to_local(georef, rows.ravel(), cols.ravel())
        vals = arr.ravel().astype("float64")
        ix = np.floor((x + half) / cell_m).astype(int)
        iy = np.floor((half - y) / cell_m).astype(int)
        ok = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n) & ~np.isnan(vals)
        flat = iy[ok] * n + ix[ok]
        sums = np.bincount(flat, weights=vals[ok], minlength=n * n)
        counts = np.bincount(flat, minlength=n * n)
        with np.errstate(invalid="ignore", divide="ignore"):
            grid = np.where(counts > 0, sums / counts, np.nan).reshape(n, n)
        method = "block_mean"
        per_cell = float(np.median(counts[counts > 0])) if counts.any() else 0.0
    else:
        centres = (np.arange(n) + 0.5) * cell_m - half
        gx, gy = np.meshgrid(centres, centres[::-1])
        rows, cols = local_to_native(georef, gx, gy)
        grid = _bilinear(arr.astype("float64"), rows, cols)
        method = "bilinear"
        per_cell = (cell_m / spacing) ** 2
    info = {
        "cell_m": cell_m, "window_m": n * cell_m, "size": n, "method": method,
        "native_spacing_m": round(spacing, 1),
        "native_pixels_per_cell": round(per_cell, 2),
        "valid_fraction": float(np.mean(~np.isnan(grid))),
    }
    return grid, info
