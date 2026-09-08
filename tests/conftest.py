"""Test configuration.

Forces DEMO_MODE and an isolated temp SQLite database BEFORE any app module
is imported, so the test suite never makes a real external API call and
never touches the developer's own data/financial_research_agent.db.
"""
import os
import tempfile

_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"
os.environ["DEMO_MODE"] = "true"

import pytest  # noqa: E402

from app.storage.database import get_session, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    init_db()
    yield


@pytest.fixture()
def db_session():
    session = get_session()
    try:
        yield session
    finally:
        session.close()
