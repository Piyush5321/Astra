"""Schema initialization and safe, versioned schema updates.

ASTRA uses SQLite with ``create_all`` for new tables. Changes to existing tables
are applied as ordered, additive migrations recorded in ``schema_version``.
Derived tables (measurements, results) can always be rebuilt from ``datasets/``.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.database import models  # noqa: F401 - registers models on Base
from backend.database.models import SchemaVersion
from backend.database.session import Base

SCHEMA_VERSION = 1

# version -> list of (table, column, DDL type) additive column migrations.
MIGRATIONS: dict[int, list[tuple[str, str, str]]] = {}


def init_schema(engine: Engine) -> int:
    """Create missing tables, apply pending additive migrations, return the version."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT version FROM schema_version WHERE id = 1")).first()
        current = row[0] if row else 0
        inspector = inspect(conn)
        for version in sorted(v for v in MIGRATIONS if v > current):
            for table, column, ddl in MIGRATIONS[version]:
                existing = {c["name"] for c in inspector.get_columns(table)}
                if column not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{column}" {ddl}'))
        if row is None:
            conn.execute(
                SchemaVersion.__table__.insert().values(id=1, version=SCHEMA_VERSION)
            )
        elif current < SCHEMA_VERSION:
            conn.execute(
                text("UPDATE schema_version SET version = :v WHERE id = 1"),
                {"v": SCHEMA_VERSION},
            )
    return SCHEMA_VERSION
