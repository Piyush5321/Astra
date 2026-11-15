"""SQLAlchemy ORM models for sites, datasets, measurements, missions and results."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchemaVersion(Base):
    """Single-row table recording the applied schema version."""

    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Site(Base):
    """An Earth candidate location or a Moon/Mars target region."""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    scientific_context: Mapped[str] = mapped_column(Text, default="")
    site_notes: Mapped[list] = mapped_column(JSON, default=list)
    references: Mapped[list] = mapped_column(JSON, default=list)
    coordinate_source: Mapped[str] = mapped_column(Text, default="")
    is_user_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class Dataset(Base):
    """Provenance record for an acquired data product or subset."""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    product_id: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    native_resolution_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieved_at: Mapped[str] = mapped_column(String(40), default="")
    attribution: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class Measurement(Base):
    """One feature value for one site, with units, uncertainty and provenance."""

    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("site_id", "feature_key", name="uq_site_feature"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), nullable=False, index=True)
    feature_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), default="")
    uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_note: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    method: Mapped[str] = mapped_column(Text, default="")
    citation: Mapped[str] = mapped_column(Text, default="")
    observed_period: Mapped[str] = mapped_column(String(80), default="")
    quality_flag: Mapped[str] = mapped_column(String(20), default="ok")
    missing_reason: Mapped[str] = mapped_column(Text, default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    site: Mapped[Site] = relationship(back_populates="measurements")
    dataset: Mapped[Dataset | None] = relationship()


class Mission(Base):
    """A mission configuration: target region, weight profile and objectives."""

    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(10), nullable=False)
    target_site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(60), nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, nullable=False)
    objectives: Mapped[str] = mapped_column(Text, default="")
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    target: Mapped[Site] = relationship()


class DiscoveryRun(Base):
    """One execution of the scoring engine for a mission."""

    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("missions.id"), nullable=False)
    target_site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    mission: Mapped[Mission] = relationship()
    results: Mapped[list["DiscoveryResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="DiscoveryResult.rank"
    )


class DiscoveryResult(Base):
    """Score of one candidate within a discovery run."""

    __tablename__ = "discovery_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id"), nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False)

    run: Mapped[DiscoveryRun] = relationship(back_populates="results")
    site: Mapped[Site] = relationship()


class Report(Base):
    """A generated PDF scientific report."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id"), nullable=False)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiCache(Base):
    """Cached external API responses (e.g. NASA POWER)."""

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
