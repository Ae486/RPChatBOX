"""Shared RP test fixtures."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from config import get_settings
from services.database import create_db_and_tables, get_engine


@pytest.fixture
def retrieval_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBOX_BACKEND_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'rp-test.db').as_posix()}",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_db_and_tables()
    with Session(get_engine()) as session:
        yield session
    get_engine.cache_clear()
    get_settings.cache_clear()
