"""Acquire real dataset subsets for every catalog site (network required).

Usage::

    python -m backend.data.acquire                 # all sites, skip existing files
    python -m backend.data.acquire --force         # re-download everything
    python -m backend.data.acquire --sites mars-gale,lonar-crater

Outputs, per site:
- ``datasets/<body>/<site>_dem.tif``  native-resolution elevation subset (float32 m)
- ``datasets/<body>/<site>_dem.json`` provenance sidecar (source URL, product,
  georeferencing, SHA-256, retrieval time)
- ``datasets/earth/power/<site>.json`` NASA POWER daily data 2020-2023 (Earth only)

Failures are recorded in ``datasets/acquisition_log.json``; they are never
replaced by synthetic data.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.data import elevation, nasa_power
from backend.data.catalog import ALL_SITES, SiteSpec


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dem_paths(site: SiteSpec, root: Path | None = None) -> tuple[Path, Path]:
    base = (root or settings.datasets_dir) / site.body
    return base / f"{site.id}_dem.tif", base / f"{site.id}_dem.json"


def power_path(site: SiteSpec, root: Path | None = None) -> Path:
    return (root or settings.datasets_dir) / "earth" / "power" / f"{site.id}.json"


def write_geotiff(path: Path, subset: elevation.ElevationSubset) -> None:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import Affine

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        crs = CRS.from_user_input(subset.georef["crs"])
    except Exception:  # noqa: BLE001 - planetary CRS may be unsupported by local PROJ
        crs = None
    profile = {
        "driver": "GTiff", "width": subset.array.shape[1], "height": subset.array.shape[0],
        "count": 1, "dtype": "float32", "nodata": float("nan"),
        "transform": Affine(*subset.georef["transform"]), "compress": "deflate",
        "predictor": 3, "tiled": False,
    }
    if crs is not None:
        profile["crs"] = crs
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(subset.array.astype("float32"), 1)
        dst.update_tags(product=subset.product, site_id=subset.site_id, body=subset.body)


def acquire_dem(site: SiteSpec, force: bool = False) -> dict:
    tif, meta = dem_paths(site)
    if tif.exists() and meta.exists() and not force:
        return {"site": site.id, "dem": "exists"}
    subset = elevation.read_subset(site.id, site.body, site.latitude, site.longitude)
    write_geotiff(tif, subset)
    valid = float(np.mean(~np.isnan(subset.array)))
    sidecar = {
        "site_id": site.id, "body": site.body, "product": subset.product,
        "provider": subset.provider, "source_url": subset.source_url,
        "attribution": subset.attribution, "vertical_reference": subset.vertical_reference,
        "native_resolution_m": subset.native_resolution_m, "georef": subset.georef,
        "shape": list(subset.array.shape), "valid_fraction": valid,
        "retrieved_at": subset.retrieved_at, "notes": subset.notes,
        "file": tif.name, "sha256": sha256_file(tif), "is_sample": False,
    }
    meta.write_text(json.dumps(sidecar, indent=2))
    return {"site": site.id, "dem": "downloaded", "shape": sidecar["shape"],
            "valid_fraction": round(valid, 4)}


def acquire_power(site: SiteSpec, force: bool = False) -> dict:
    path = power_path(site)
    if path.exists() and not force:
        return {"site": site.id, "power": "exists"}
    data = nasa_power.fetch_daily(site.latitude, site.longitude)
    record = data.to_dict()
    record["attribution"] = nasa_power.POWER_ATTRIBUTION
    record["is_sample"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
    return {"site": site.id, "power": "downloaded"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sites", help="Comma-separated site ids (default: all).")
    parser.add_argument("--force", action="store_true", help="Re-download existing files.")
    parser.add_argument("--skip-power", action="store_true")
    parser.add_argument("--skip-dem", action="store_true")
    args = parser.parse_args(argv)

    wanted = set(args.sites.split(",")) if args.sites else None
    sites = [s for s in ALL_SITES if wanted is None or s.id in wanted]
    log = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "results": [], "failures": []}
    for site in sites:
        steps = []
        if not args.skip_dem:
            steps.append(("dem", acquire_dem))
        if site.body == "earth" and not args.skip_power:
            steps.append(("power", acquire_power))
        for label, fn in steps:
            try:
                result = fn(site, args.force)
                log["results"].append(result)
                print(f"[ok]   {site.id:32s} {label}: {result}")
            except Exception as exc:  # noqa: BLE001 - record and continue
                log["failures"].append({"site": site.id, "step": label, "error": str(exc)})
                print(f"[FAIL] {site.id:32s} {label}: {exc}", file=sys.stderr)
    log_path = settings.datasets_dir / "acquisition_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2))
    return 1 if log["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
