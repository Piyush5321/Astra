"""Readers that extract small, georeferenced elevation subsets from real DEMs.

Sources (all verified reachable when this module was written):
- Earth: NASADEM (NASA/JPL, 1 arcsec, 60 N - 56 S) as Cloud-Optimized GeoTIFFs on
  Microsoft Planetary Computer. Outside NASADEM coverage, Copernicus DEM GLO-30
  (ESA / Airbus, non-NASA) from the same host is used and labelled as a fallback.
- Moon: LRO LOLA GDR LDEM_64 (64 px/deg, ~474 m) simple-cylindrical grid, and
  LDEM_75S_240M (240 m polar stereographic) for the south pole, from the PDS
  Geosciences Node, read with HTTP Range requests (no full-file download).
- Mars: MGS MOLA MEGDR 128 px/deg (~463 m) topography tiles from the PDS
  Geosciences Node, read with HTTP Range requests.
"""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import requests

from backend.config import settings

WINDOW_KM = 30.0
MARGIN_KM = 1.5
EARTH_RADIUS_M = 6_371_008.8
MOON_RADIUS_M = 1_737_400.0
MARS_RADIUS_M = 3_396_000.0  # MEGDR label A_AXIS_RADIUS

PC_STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
PDS_GEO = "https://pds-geosciences.wustl.edu"
LOLA_CYL_URL = f"{PDS_GEO}/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_64.img"
LOLA_SP_URL = f"{PDS_GEO}/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_75s_240m.img"
MOLA_DIR = f"{PDS_GEO}/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128"

LOLA_ATTRIBUTION = (
    "LRO LOLA Gridded Data Record, NASA Goddard Space Flight Center / LOLA Science Team; "
    "distributed by the NASA PDS Geosciences Node."
)
MOLA_ATTRIBUTION = (
    "MGS MOLA Mission Experiment Gridded Data Record (MEGDR), NASA Goddard Space Flight "
    "Center / MOLA Science Team; distributed by the NASA PDS Geosciences Node."
)
NASADEM_ATTRIBUTION = (
    "NASADEM, NASA JPL (2020), distributed by NASA LP DAAC; accessed as COGs via "
    "Microsoft Planetary Computer."
)
COPDEM_ATTRIBUTION = (
    "Copernicus DEM GLO-30, (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH "
    "2014-2018 provided under COPERNICUS by the European Union and ESA; accessed via "
    "Microsoft Planetary Computer. Not a NASA product."
)


class ElevationError(RuntimeError):
    """Raised when an elevation subset cannot be acquired."""


@dataclass
class ElevationSubset:
    site_id: str
    body: str
    product: str
    provider: str
    source_url: str
    array: np.ndarray  # float32 metres, NaN = nodata
    georef: dict  # see module docstring of science.resample
    native_resolution_m: float
    attribution: str
    vertical_reference: str
    notes: list[str] = field(default_factory=list)
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _get(url: str, *, byte_range: tuple[int, int] | None = None, params=None,
         json_body=None, attempts: int = 3) -> requests.Response:
    headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            if json_body is not None:
                resp = requests.post(url, json=json_body, timeout=settings.http_timeout_seconds)
            else:
                resp = requests.get(url, headers=headers, params=params,
                                    timeout=settings.http_timeout_seconds)
            if resp.status_code in (200, 206):
                if byte_range and resp.status_code != 206:
                    raise ElevationError(f"Server ignored Range request for {url}.")
                return resp
            last = ElevationError(f"HTTP {resp.status_code} from {url}")
        except requests.RequestException as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise ElevationError(f"Request failed for {url}: {last}")


def window_degrees(lat: float, radius_m: float, half_km: float) -> tuple[float, float]:
    """Half-window size in degrees latitude and longitude at ``lat``."""
    dlat = math.degrees(half_km * 1000.0 / radius_m)
    dlon = math.degrees(half_km * 1000.0 / (radius_m * max(math.cos(math.radians(lat)), 1e-6)))
    return dlat, dlon


# --- Earth ----------------------------------------------------------------------

_pc_tokens: dict[str, tuple[str, float]] = {}


def _pc_token(collection: str) -> str:
    cached = _pc_tokens.get(collection)
    if cached and cached[1] > time.time() + 300:
        return cached[0]
    data = _get(PC_SAS_TOKEN.format(collection=collection)).json()
    token = data["token"]
    expiry = datetime.fromisoformat(data["msft:expiry"].replace("Z", "+00:00")).timestamp()
    _pc_tokens[collection] = (token, expiry)
    return token


def read_earth(site_id: str, lat: float, lon: float) -> ElevationSubset:
    import rasterio
    from rasterio.merge import merge

    half = WINDOW_KM / 2 + MARGIN_KM
    dlat, dlon = window_degrees(lat, EARTH_RADIUS_M, half)
    bbox = [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
    in_nasadem = bbox[1] >= -56.0 and bbox[3] <= 60.0
    collection, asset_key = ("nasadem", "elevation") if in_nasadem else ("cop-dem-glo-30", "data")
    items = _get(PC_STAC_SEARCH, json_body={
        "collections": [collection], "bbox": bbox, "limit": 20}).json().get("features", [])
    if not items:
        raise ElevationError(f"No {collection} tiles intersect {bbox}.")
    token = _pc_token(collection)
    hrefs = [it["assets"][asset_key]["href"] for it in items]
    sources = [rasterio.open(f"{h}?{token}") for h in hrefs]
    try:
        nodata = sources[0].nodata
        mosaic, transform = merge(sources, bounds=tuple(bbox), nodata=nodata)
    finally:
        for src in sources:
            src.close()
    arr = mosaic[0].astype("float32")
    if nodata is not None:
        arr[arr == nodata] = np.nan
    res_deg = abs(transform.e)
    notes = []
    if in_nasadem:
        product, provider, attribution = "NASADEM_HGT v001", "NASA JPL / LP DAAC", NASADEM_ATTRIBUTION
        vref = "EGM96 geoid (NASADEM heights)"
    else:
        product, provider, attribution = "Copernicus DEM GLO-30", "ESA / Airbus (Copernicus)", COPDEM_ATTRIBUTION
        vref = "EGM2008 geoid (Copernicus DEM heights)"
        notes.append("NASADEM does not cover this latitude (60 N - 56 S); Copernicus "
                     "GLO-30 used as a documented non-NASA fallback.")
    return ElevationSubset(
        site_id=site_id, body="earth", product=product, provider=provider,
        source_url="; ".join(hrefs), array=arr,
        georef={"kind": "geographic", "transform": list(transform)[:6],
                "radius_m": EARTH_RADIUS_M, "center": [lat, lon],
                "crs": "EPSG:4326"},
        native_resolution_m=round(math.radians(res_deg) * EARTH_RADIUS_M, 1),
        attribution=attribution, vertical_reference=vref, notes=notes,
    )


# --- PDS raw grids ----------------------------------------------------------------

def _read_rows(url: str, row0: int, row1: int, record_bytes: int, dtype: str) -> np.ndarray:
    """Read rows [row0, row1) of a fixed-record raw PDS image via one Range request."""
    start, end = row0 * record_bytes, row1 * record_bytes - 1
    data = _get(url, byte_range=(start, end)).content
    expected = (row1 - row0) * record_bytes
    if len(data) != expected:
        raise ElevationError(f"Expected {expected} bytes from {url}, got {len(data)}.")
    return np.frombuffer(data, dtype=dtype).reshape(row1 - row0, -1)


def _cylindrical_window(lat: float, lon360: float, radius_m: float, ppd: int,
                        north_edge: float, west_edge: float, n_rows: int, n_cols: int):
    half = WINDOW_KM / 2 + MARGIN_KM
    dlat, dlon = window_degrees(lat, radius_m, half)
    r0 = max(0, math.floor((north_edge - (lat + dlat)) * ppd))
    r1 = min(n_rows, math.ceil((north_edge - (lat - dlat)) * ppd))
    c0 = math.floor((lon360 - dlon - west_edge) * ppd)
    c1 = math.ceil((lon360 + dlon - west_edge) * ppd)
    if c0 < 0 or c1 > n_cols:
        raise ElevationError("Window crosses the product's longitude edge; not supported.")
    transform = [1.0 / ppd, 0.0, west_edge + c0 / ppd, 0.0, -1.0 / ppd, north_edge - r0 / ppd]
    return r0, r1, c0, c1, transform


def read_moon(site_id: str, lat: float, lon: float) -> ElevationSubset:
    lon360 = lon % 360.0
    if lat <= -85.0:
        # LDEM_75S_240M: 3812 x 3812 LSB int16, DN * 0.5 m, pole at pixel offset 1905.5.
        size, scale_m, offset = 3812, 240.0, 1905.0
        half_px = math.ceil((WINDOW_KM / 2 + MARGIN_KM) * 1000 / scale_m)
        if lat != -90.0:
            raise ElevationError("Polar reader supports windows centred on the pole only.")
        r0, r1 = int(offset) - half_px, int(offset) + half_px
        rows = _read_rows(LOLA_SP_URL, r0, r1, size * 2, "<i2")
        arr = rows[:, r0:r1].astype("float32") * 0.5
        transform = [scale_m, 0.0, (r0 - offset) * scale_m, 0.0, -scale_m, (offset - r0) * scale_m]
        return ElevationSubset(
            site_id=site_id, body="moon", product="LOLA LDEM_75S_240M (V2.1)",
            provider="NASA GSFC LOLA team / PDS Geosciences Node", source_url=LOLA_SP_URL,
            array=arr,
            georef={"kind": "projected", "transform": transform, "radius_m": MOON_RADIUS_M,
                    "center_xy": [0.0, 0.0],
                    "crs": "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 "
                           "+R=1737400 +units=m +no_defs"},
            native_resolution_m=scale_m, attribution=LOLA_ATTRIBUTION,
            vertical_reference="Height above 1737.4 km reference sphere",
            notes=["Polar stereographic product; window centred on the south pole."],
        )
    r0, r1, c0, c1, transform = _cylindrical_window(lat, lon360, MOON_RADIUS_M, 64,
                                                    90.0, 0.0, 11520, 23040)
    rows = _read_rows(LOLA_CYL_URL, r0, r1, 23040 * 2, "<i2")
    arr = rows[:, c0:c1].astype("float32") * 0.5
    return ElevationSubset(
        site_id=site_id, body="moon", product="LOLA LDEM_64 (V3.1)",
        provider="NASA GSFC LOLA team / PDS Geosciences Node", source_url=LOLA_CYL_URL,
        array=arr,
        georef={"kind": "geographic", "transform": transform, "radius_m": MOON_RADIUS_M,
                "center": [lat, lon360], "crs": "+proj=longlat +R=1737400 +no_defs"},
        native_resolution_m=473.8, attribution=LOLA_ATTRIBUTION,
        vertical_reference="Height above 1737.4 km reference sphere",
        notes=["LDEM_64 cells without LOLA shots are interpolated by the producer "
               "(GMT surface), which smooths terrain between tracks."],
    )


def mola_tile(lat: float, lon360: float) -> tuple[str, float, float]:
    """Return (tile URL, north edge, west edge) of the MEGDR 128 ppd topography tile."""
    if not -88.0 <= lat <= 88.0:
        raise ElevationError("MEGDR 128 ppd tiles cover 88 S - 88 N only.")
    north = next(t for t in (88.0, 44.0, 0.0, -44.0) if lat <= t and lat > t - 44.0)
    west = math.floor(lon360 / 90.0) * 90.0
    hemi = "n" if north >= 0 else "s"
    name = f"megt{int(abs(north)):02d}{hemi}{int(west):03d}hb.img"
    return f"{MOLA_DIR}/{name}", north, west


def read_mars(site_id: str, lat: float, lon: float) -> ElevationSubset:
    lon360 = lon % 360.0
    url, north, west = mola_tile(lat, lon360)
    r0, r1, c0, c1, transform = _cylindrical_window(lat, lon360, MARS_RADIUS_M, 128,
                                                    north, west, 5632, 11520)
    rows = _read_rows(url, r0, r1, 11520 * 2, ">i2")
    arr = rows[:, c0:c1].astype("float32")
    return ElevationSubset(
        site_id=site_id, body="mars", product="MOLA MEGDR 128 ppd topography (v2.0)",
        provider="NASA GSFC MOLA team / PDS Geosciences Node", source_url=url, array=arr,
        georef={"kind": "geographic", "transform": transform, "radius_m": MARS_RADIUS_M,
                "center": [lat, lon360], "crs": "+proj=longlat +R=3396000 +no_defs"},
        native_resolution_m=463.1, attribution=MOLA_ATTRIBUTION,
        vertical_reference="Planetary radius minus GMM3 areoid",
        notes=["MEGDR bins without MOLA shots are interpolated by the producer; the PDS "
               "label reports gaps of up to ~12 km between MOLA profiles near the "
               "equator, so many 128 px/deg bins are interpolated."],
    )


def read_subset(site_id: str, body: str, lat: float, lon: float) -> ElevationSubset:
    readers = {"earth": read_earth, "moon": read_moon, "mars": read_mars}
    if body not in readers:
        raise ElevationError(f"Unsupported body {body!r}.")
    return readers[body](site_id, lat, lon)
