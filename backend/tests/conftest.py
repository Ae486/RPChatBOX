"""Shared pytest fixtures for backend API tests."""
from fastapi.testclient import TestClient
import pytest

from config import get_settings
from main import create_app
from services.database import get_engine
from services.provider_registry import get_provider_registry_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBOX_BACKEND_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'chatbox-test.db').as_posix()}",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_provider_registry_service.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_provider_registry_service.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
