"""NASA POWER daily point API client with validation, caching and provenance.

API documentation: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
POWER meteorology is derived from the MERRA-2 reanalysis (and CERES/GEWEX for
radiation): values are modelled grid-cell estimates (~0.5 x 0.625 deg), not
in-situ station observations.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.models import ApiCache

POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_ATTRIBUTION = (
    "Data obtained from the NASA Langley Research Center (LaRC) POWER Project funded "
    "through the NASA Earth Science/Applied Science Program."
)
DEFAULT_PARAMETERS = ("TS", "TS_MAX", "TS_MIN", "T2M", "PRECTOTCORR", "RH2M",
                      "ALLSKY_SFC_SW_DWN", "WS2M")
DEFAULT_PERIOD = ("20200101", "20231231")
FILL_VALUE = -999.0

# Plausibility bounds; values outside are treated as invalid (set to None).
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "TS": (-100.0, 90.0), "TS_MAX": (-100.0, 95.0), "TS_MIN": (-100.0, 90.0),
    "T2M": (-95.0, 65.0), "PRECTOTCORR": (0.0, 2000.0), "RH2M": (0.0, 100.0),
    # Community AG reports irradiance in MJ/m^2/day (top-of-atmosphere max ~45).
    "ALLSKY_SFC_SW_DWN": (0.0, 46.0), "WS2M": (0.0, 80.0),
}
MJ_PER_KWH = 3.6
_PARAM_RE = re.compile(r"^[A-Z0-9_]{2,30}$")
_DATE_RE = re.compile(r"^\d{8}$")


class PowerError(RuntimeError):
    """Raised when the POWER API request fails or returns invalid data."""


@dataclass
class PowerDaily:
    latitude: float
    longitude: float
    start: str
    end: str
    values: dict[str, dict[str, float | None]]  # param -> YYYYMMDD -> value
    units: dict[str, str]
    longnames: dict[str, str]
    sources: list[str]
    api_version: str
    request_url: str
    fetched_at: str
    from_cache: bool = False

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def validate_request(lat: float, lon: float, start: str, end: str,
                     parameters: tuple[str, ...]) -> None:
    if not (isinstance(lat, (int, float)) and -90 <= lat <= 90):
        raise ValueError(f"Latitude {lat!r} must be between -90 and 90.")
    if not (isinstance(lon, (int, float)) and -180 <= lon <= 180):
        raise ValueError(f"Longitude {lon!r} must be between -180 and 180.")
    for label, d in (("start", start), ("end", end)):
        if not _DATE_RE.match(d):
            raise ValueError(f"{label} date {d!r} must be YYYYMMDD.")
        datetime.strptime(d, "%Y%m%d")
    if start > end:
        raise ValueError("start date must not be after end date.")
    if start < "19810101":
        raise ValueError("POWER daily data begins on 1981-01-01.")
    if not parameters or len(parameters) > 20:
        raise ValueError("Request between 1 and 20 POWER parameters.")
    for p in parameters:
        if not _PARAM_RE.match(p):
            raise ValueError(f"Invalid POWER parameter name {p!r}.")


def parse_response(payload: dict, parameters: tuple[str, ...]) -> tuple[dict, dict, dict, list, str]:
    """Validate a POWER JSON payload; return values, units, longnames, sources, version."""
    try:
        param_block = payload["properties"]["parameter"]
        header = payload.get("header", {})
    except (KeyError, TypeError) as exc:
        raise PowerError("POWER response is missing properties.parameter.") from exc
    fill = header.get("fill_value", FILL_VALUE)
    meta = payload.get("parameters", {})
    values: dict[str, dict[str, float | None]] = {}
    for p in parameters:
        series = param_block.get(p)
        if not isinstance(series, dict) or not series:
            raise PowerError(f"POWER response has no data for parameter {p}.")
        lo, hi = PLAUSIBLE_RANGES.get(p, (-math.inf, math.inf))
        clean: dict[str, float | None] = {}
        for day, raw in series.items():
            if not _DATE_RE.match(str(day)):
                raise PowerError(f"Unexpected date key {day!r} in POWER response.")
            if raw is None or not isinstance(raw, (int, float)) or raw == fill:
                clean[day] = None
            elif not (lo <= raw <= hi) or math.isnan(raw):
                clean[day] = None
            else:
                clean[day] = float(raw)
        values[p] = clean
    units = {p: str(meta.get(p, {}).get("units", "")) for p in parameters}
    longnames = {p: str(meta.get(p, {}).get("longname", "")) for p in parameters}
    sources = [str(s) for s in header.get("sources", [])]
    version = str(header.get("api", {}).get("version", ""))
    return values, units, longnames, sources, version


def _cache_key(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


def fetch_daily(lat: float, lon: float, start: str = DEFAULT_PERIOD[0],
                end: str = DEFAULT_PERIOD[1],
                parameters: tuple[str, ...] = DEFAULT_PARAMETERS,
                db: Session | None = None, timeout: float | None = None,
                http: requests.Session | None = None) -> PowerDaily:
    """Fetch (or load from cache) validated POWER daily data for one point."""
    validate_request(lat, lon, start, end, parameters)
    query = {
        "parameters": ",".join(parameters), "community": "AG",
        "longitude": round(float(lon), 4), "latitude": round(float(lat), 4),
        "start": start, "end": end, "format": "JSON",
    }
    key = _cache_key(query)
    if db is not None:
        cached = db.get(ApiCache, key)
        if cached is not None:
            fetched = cached.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - fetched
            if age < timedelta(hours=settings.power_cache_ttl_hours):
                result = PowerDaily(**cached.response)
                result.from_cache = True
                return result

    client = http or requests
    try:
        resp = client.get(POWER_DAILY_URL, params=query,
                          timeout=timeout or settings.http_timeout_seconds)
    except requests.RequestException as exc:
        raise PowerError(f"POWER request failed: {exc}") from exc
    if resp.status_code != 200:
        raise PowerError(f"POWER returned HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise PowerError("POWER returned a non-JSON response.") from exc
    values, units, longnames, sources, version = parse_response(payload, parameters)
    result = PowerDaily(
        latitude=float(lat), longitude=float(lon), start=start, end=end, values=values,
        units=units, longnames=longnames, sources=sources, api_version=version,
        request_url=resp.url if hasattr(resp, "url") else POWER_DAILY_URL,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if db is not None:
        db.merge(ApiCache(key=key, source="nasa_power", request=query,
                          response=result.to_dict(), fetched_at=datetime.now(timezone.utc)))
        db.commit()
    return result


def _series(values: dict[str, float | None]) -> tuple[list[str], np.ndarray]:
    days = sorted(values)
    arr = np.array([np.nan if values[d] is None else values[d] for d in days], dtype=float)
    return days, arr


def summarize_climate(data: PowerDaily, min_valid_fraction: float = 0.9) -> dict:
    """Derive annual climate features from daily POWER data.

    For each calendar year with >= ``min_valid_fraction`` valid days, compute:
      surface_temp_max_k  95th percentile of daily TS_MAX (K)
      surface_temp_min_k  5th percentile of daily TS_MIN (K)
      surface_temp_diurnal_range_k  mean of (TS_MAX - TS_MIN) (K)
      annual_precipitation_mm  sum of PRECTOTCORR (mm/yr)
    Feature value = mean over valid years; uncertainty = interannual standard
    deviation (sample, ddof=1), or None with a single year.
    """
    required = ("TS_MAX", "TS_MIN", "PRECTOTCORR")
    for p in required:
        if p not in data.values:
            raise PowerError(f"POWER data lacks required parameter {p}.")
    days, tmax = _series(data.values["TS_MAX"])
    _, tmin = _series(data.values["TS_MIN"])
    _, prec = _series(data.values["PRECTOTCORR"])
    years = np.array([int(d[:4]) for d in days])
    per_year: dict[str, list[float]] = {
        "surface_temp_max_k": [], "surface_temp_min_k": [],
        "surface_temp_diurnal_range_k": [], "annual_precipitation_mm": [],
    }
    used_years = []
    for year in sorted(set(years.tolist())):
        mask = years == year
        n = int(mask.sum())
        ok = ~np.isnan(tmax[mask]) & ~np.isnan(tmin[mask]) & ~np.isnan(prec[mask])
        if n < 365 or ok.sum() < min_valid_fraction * n:
            continue
        ymax, ymin, yprec = tmax[mask][ok], tmin[mask][ok], prec[mask][ok]
        per_year["surface_temp_max_k"].append(float(np.percentile(ymax, 95)) + 273.15)
        per_year["surface_temp_min_k"].append(float(np.percentile(ymin, 5)) + 273.15)
        per_year["surface_temp_diurnal_range_k"].append(float(np.mean(ymax - ymin)))
        # Scale to a full year when a few days are invalid.
        per_year["annual_precipitation_mm"].append(float(yprec.sum() * n / ok.sum()))
        used_years.append(year)

    features = {}
    for key, vals in per_year.items():
        if not vals:
            features[key] = None
            continue
        features[key] = {
            "value": float(np.mean(vals)),
            "uncertainty": float(np.std(vals, ddof=1)) if len(vals) > 1 else None,
            "years": used_years,
        }
    return features
