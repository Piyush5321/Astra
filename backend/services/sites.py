"""Site, measurement and provenance serialisation shared by the API and the agent."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data.ingest import analysis_grid
from backend.database.models import Dataset, Measurement, Site
from backend.science.features import DESCRIPTIVE_FEATURES, FEATURES_BY_KEY
from backend.science.terrain import hillshade
from backend.services.discovery import get_site


def site_summary(site: Site) -> dict:
    return {
        "id": site.id, "name": site.name, "body": site.body, "role": site.role,
        "latitude": site.latitude, "longitude": site.longitude, "region": site.region,
        "description": site.description,
    }


def measurement_dict(m: Measurement) -> dict:
    spec = FEATURES_BY_KEY.get(m.feature_key)
    label = spec.label if spec else DESCRIPTIVE_FEATURES.get(m.feature_key, ("", m.feature_key))[1]
    return {
        "feature_key": m.feature_key, "label": label, "dimension": m.dimension,
        "scored": spec is not None, "value": m.value, "tags": m.value_tags, "unit": m.unit,
        "uncertainty": m.uncertainty, "uncertainty_note": m.uncertainty_note,
        "source_type": m.source_type, "dataset_id": m.dataset_id, "method": m.method,
        "citation": m.citation, "observed_period": m.observed_period,
        "quality_flag": m.quality_flag, "missing_reason": m.missing_reason,
        "is_sample": m.is_sample,
    }


def dataset_dict(d: Dataset) -> dict:
    return {
        "id": d.id, "site_id": d.site_id, "kind": d.kind, "name": d.name,
        "provider": d.provider, "product_id": d.product_id, "source_url": d.source_url,
        "file_path": d.file_path, "sha256": d.sha256,
        "native_resolution_m": d.native_resolution_m, "retrieved_at": d.retrieved_at,
        "attribution": d.attribution, "notes": d.notes, "extra": d.extra,
        "is_sample": d.is_sample,
    }


def site_detail(db: Session, site_id: str) -> dict:
    site = get_site(db, site_id)
    measurements = db.scalars(select(Measurement).where(Measurement.site_id == site_id)
                              .order_by(Measurement.dimension, Measurement.feature_key))
    datasets = db.scalars(select(Dataset).where(Dataset.site_id == site_id))
    return {
        **site_summary(site),
        "scientific_context": site.scientific_context, "site_notes": site.site_notes,
        "references": site.references, "coordinate_source": site.coordinate_source,
        "measurements": [measurement_dict(m) for m in measurements],
        "datasets": [dataset_dict(d) for d in datasets],
    }


def terrain_grid(site_id: str) -> dict:
    """500 m analysis grid plus hillshade, rounded for transport (visualisation)."""
    grid, info, meta = analysis_grid(site_id)
    shade = hillshade(grid, info["cell_m"])

    def rows(a, nd):
        return [[None if v != v else round(float(v), nd) for v in row] for row in a]

    return {
        "site_id": site_id, "info": info, "product": meta["product"],
        "vertical_reference": meta.get("vertical_reference", ""),
        "elevation": rows(grid, 1), "hillshade": rows(shade, 3),
        "orientation": "row 0 = north edge, column 0 = west edge (polar grids: map "
                       "projection axes)",
    }
