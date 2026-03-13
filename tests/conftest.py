"""
Shared fixtures for all tests.
Uses SQLite (file-based, per-test) instead of PostgreSQL,
and mocks Redis cache to avoid external dependencies.

Key fix: SQLite :memory: loses data between connections, so we use a
named temp file per test instead, which lets multiple sessions share
the same database.
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys

# ── patch redis BEFORE app is imported ──────────────────────────────────────
redis_mock = MagicMock()
redis_mock.get.return_value = None
redis_mock.set.return_value = True
redis_mock.delete.return_value = 1

redis_module_mock = MagicMock()
redis_module_mock.Redis.return_value = redis_mock
sys.modules["redis"] = redis_module_mock

# ── now import app internals ─────────────────────────────────────────────────
from app.database import Base, get_db  # noqa: E402
from app.main import app               # noqa: E402


# ── per-test SQLite file fixture ─────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    """
    Create a fresh SQLite database file for each test.
    File-based SQLite (vs :memory:) ensures all sessions
    within a test share the same data.
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    session = TestingSessionLocal()
    session._test_engine = test_engine  # stash for client fixture

    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()
        os.unlink(db_path)


@pytest.fixture(scope="function")
def client(db):
    """TestClient with overridden DB dependency and mocked cache."""

    test_engine = db._test_engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # reset redis mock state between tests
    redis_mock.get.return_value = None
    redis_mock.reset_mock()

    with patch("app.main.get_cache", side_effect=lambda k: redis_mock.get(k)), \
         patch("app.main.set_cache", side_effect=lambda k, v: redis_mock.set(k, v)), \
         patch("app.main.delete_cache", side_effect=lambda k: redis_mock.delete(k)):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()
