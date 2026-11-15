"""Test configuration: isolated temporary SQLite database, LLM disabled."""

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="astra-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["REPORTS_DIR"] = str(_TMP / "reports")
os.environ["LLM_PROVIDER"] = "none"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def db():
    from backend.data.ingest import ingest_all
    from backend.database import session
    from backend.database.schema import init_schema

    init_schema(session.engine)
    s = session.SessionLocal()
    ingest_all(s)
    yield s
    s.close()


@pytest.fixture(scope="session")
def client(db):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c
