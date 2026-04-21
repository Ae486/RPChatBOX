"""Tests for backend database engine configuration."""
from __future__ import annotations

from sqlalchemy.pool import NullPool

from config import get_settings
from services.database import get_engine


def test_sqlite_engine_uses_null_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBOX_BACKEND_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'database-test.db').as_posix()}",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()

    engine = get_engine()

    assert isinstance(engine.pool, NullPool)

    get_engine.cache_clear()
    get_settings.cache_clear()

