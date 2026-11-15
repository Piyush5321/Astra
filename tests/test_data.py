"""POWER parsing/validation (offline), catalog integrity and ingestion of real datasets."""

import json

import pytest
from sqlalchemy import select

from backend.data import catalog, nasa_power
from backend.data.elevation import mola_tile
from backend.data.vocabulary import validate_tags
from backend.database.models import Dataset, Measurement


def power_payload(values):
    return {
        "properties": {"parameter": {"TS_MAX": values, "TS_MIN": values, "PRECTOTCORR": values}},
        "header": {"fill_value": -999.0, "sources": ["MERRA2"], "api": {"version": "x"}},
        "parameters": {"TS_MAX": {"units": "C"}, "TS_MIN": {"units": "C"},
                       "PRECTOTCORR": {"units": "mm/day"}},
    }


def test_power_request_validation():
    with pytest.raises(ValueError):
        nasa_power.validate_request(91, 0, "20200101", "20201231", ("TS",))
    with pytest.raises(ValueError):
        nasa_power.validate_request(0, 0, "20201231", "20200101", ("TS",))
    with pytest.raises(ValueError):
        nasa_power.validate_request(0, 0, "19700101", "19701231", ("TS",))
    with pytest.raises(ValueError):
        nasa_power.validate_request(0, 0, "20200101", "20200102", ("bad;name",))


def test_power_fill_values_and_implausible_values_become_none():
    values, *_ = nasa_power.parse_response(
        power_payload({"20200101": 1.0, "20200102": -999.0, "20200103": 500.0}),
        ("TS_MAX", "TS_MIN", "PRECTOTCORR"))
    assert values["TS_MAX"] == {"20200101": 1.0, "20200102": None, "20200103": None}


def test_power_missing_parameter_raises():
    with pytest.raises(nasa_power.PowerError):
        nasa_power.parse_response(power_payload({"20200101": 1.0}), ("T2M",))


def test_summarize_climate_skips_incomplete_years():
    days = {f"2021{m:02d}{d:02d}": None for m in range(1, 13) for d in range(1, 29)}
    data = nasa_power.PowerDaily(0, 0, "20210101", "20211231",
                                 {"TS_MAX": days, "TS_MIN": days, "PRECTOTCORR": days},
                                 {}, {}, [], "", "", "")
    assert all(v is None for v in nasa_power.summarize_climate(data).values())


def test_catalog_integrity():
    ids = [s.id for s in catalog.ALL_SITES]
    assert len(ids) == len(set(ids))
    assert sum(s.role == "candidate" for s in catalog.ALL_SITES) == 8
    assert {s.body for s in catalog.TARGETS} == {"moon", "mars"}
    for s in catalog.ALL_SITES:
        assert -90 <= s.latitude <= 90 and -180 <= s.longitude <= 180
        validate_tags("geology_tags", list(s.geology_tags))
        validate_tags("resource_tags", list(s.resource_tags))
        validate_tags("hazard_tags", list(s.hazard_tags))
    with pytest.raises(ValueError):
        validate_tags("geology_tags", ["unobtainium"])


def test_mola_tile_selection():
    assert mola_tile(18.44, 77.45)[0].endswith("megt44n000hb.img")
    assert mola_tile(-4.59, 137.44)[0].endswith("megt00n090hb.img")
    assert mola_tile(-1.95, 354.47)[0].endswith("megt00n270hb.img")


def test_ingestion_records_provenance_and_missing(db):
    rows = list(db.scalars(select(Measurement)))
    assert rows, "ingestion produced no measurements"
    for m in rows:
        assert m.source_type in {"measured_dataset", "derived", "literature_reference",
                                 "curated_classification", "physical_constraint", "none"}
        if m.quality_flag == "missing":
            assert m.value is None and m.missing_reason
        elif m.source_type in {"measured_dataset", "derived"}:
            assert m.dataset_id, f"{m.site_id}/{m.feature_key} lacks dataset provenance"
        elif m.source_type == "literature_reference":
            assert m.citation and m.uncertainty is not None
        assert not m.is_sample
    jezero_tmax = db.scalar(select(Measurement).where(
        Measurement.site_id == "mars-jezero", Measurement.feature_key == "surface_temp_max_k"))
    assert jezero_tmax.quality_flag == "missing"


def test_datasets_are_real_and_checksummed(db):
    datasets = list(db.scalars(select(Dataset)))
    assert len(datasets) == 14 + 8  # one DEM per site + POWER per Earth site
    assert all(d.sha256 and not d.is_sample for d in datasets)
    products = {d.product_id for d in datasets if d.kind == "elevation"}
    assert {"NASADEM_HGT v001", "Copernicus DEM GLO-30", "LOLA LDEM_64 (V3.1)",
            "LOLA LDEM_75S_240M (V2.1)", "MOLA MEGDR 128 ppd topography (v2.0)"} <= products


def test_known_elevations_sanity(db):
    """Check subsets against well-known site elevations (tolerances generous)."""
    expected = {"death-valley-badwater": (-86, 60), "mars-gale": (-4500, 150),
                "mars-jezero": (-2570, 200), "moon-apollo11-tranquillitatis": (-1920, 200)}
    from backend.data.ingest import load_dem

    for site_id, (elev, tol) in expected.items():
        arr, _ = load_dem(site_id)
        h, w = arr.shape
        centre = float(arr[h // 2 - 1:h // 2 + 1, w // 2 - 1:w // 2 + 1].mean())
        assert abs(centre - elev) < tol, (site_id, centre)


def test_power_files_have_full_coverage():
    for spec in catalog.EARTH_CANDIDATES:
        from backend.data.acquire import power_path

        record = json.loads(power_path(spec).read_text())
        assert len(record["values"]["TS_MAX"]) == 1461
