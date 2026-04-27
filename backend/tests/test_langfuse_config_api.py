from __future__ import annotations

from config import get_settings
from services.langfuse_config_service import (
    get_langfuse_config_service,
    reset_langfuse_config_service,
)
from services.langfuse_service import reset_langfuse_service


class _FakeLangfuseClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def propagate_attributes(self, **kwargs):
        class _Context:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Context()

    def start_as_current_observation(self, **kwargs):
        class _Observation:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

            def update(self_inner, **kwargs) -> None:
                return None

            def score_trace(self_inner, **kwargs) -> None:
                return None

        return _Observation()


def test_get_langfuse_settings_returns_disabled_summary(client):
    response = client.get("/api/observability/langfuse")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["configured"] is False
    assert data["service_enabled"] is False
    assert data["status_reason"] == "disabled"
    assert data["source"] == "env"
    assert data["has_secret_key"] is False
    assert data["dashboard_url"] == "https://cloud.langfuse.com"


def test_put_langfuse_settings_persists_and_activates_runtime(client, monkeypatch):
    monkeypatch.setattr("services.langfuse_service.Langfuse", _FakeLangfuseClient)
    reset_langfuse_config_service()
    reset_langfuse_service()

    response = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-langfuse-1234",
            "secret_key": "sk-langfuse-9876",
            "base_url": "https://cloud.langfuse.com",
            "environment": "setup-eval",
            "release": "local-dev",
            "sample_rate": 1.0,
            "debug": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["configured"] is True
    assert data["service_enabled"] is True
    assert data["sdk_available"] is True
    assert data["status_reason"] == "active"
    assert data["source"] == "storage"
    assert data["public_key"] == "pk-langfuse-1234"
    assert data["has_secret_key"] is True
    assert data["base_url"] == "https://cloud.langfuse.com"
    assert data["dashboard_url"] == "https://cloud.langfuse.com"
    assert data["config_path"].endswith("langfuse_settings.json")

    stored = get_langfuse_config_service().get_effective_config()
    assert stored.secret_key == "sk-langfuse-9876"


def test_put_langfuse_settings_preserves_existing_secret_when_blank(client, monkeypatch):
    monkeypatch.setattr("services.langfuse_service.Langfuse", _FakeLangfuseClient)
    reset_langfuse_config_service()
    reset_langfuse_service()

    first = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-first",
            "secret_key": "sk-first",
            "base_url": "https://cloud.langfuse.com",
        },
    )
    assert first.status_code == 200

    second = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-second",
            "base_url": "https://cloud.langfuse.com",
        },
    )

    assert second.status_code == 200
    data = second.json()
    assert data["public_key"] == "pk-second"
    assert data["has_secret_key"] is True
    stored = get_langfuse_config_service().get_effective_config()
    assert stored.secret_key == "sk-first"


def test_put_langfuse_settings_can_clear_secret_key(client, monkeypatch):
    monkeypatch.setattr("services.langfuse_service.Langfuse", _FakeLangfuseClient)
    reset_langfuse_config_service()
    reset_langfuse_service()

    assert client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-first",
            "secret_key": "sk-first",
            "base_url": "https://cloud.langfuse.com",
        },
    ).status_code == 200

    response = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-first",
            "base_url": "https://cloud.langfuse.com",
            "clear_secret_key": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["has_secret_key"] is False
    assert data["status_reason"] == "missing_api_keys"


def test_put_langfuse_settings_reports_sdk_unavailable(client, monkeypatch):
    monkeypatch.setattr("services.langfuse_service.Langfuse", None)
    reset_langfuse_config_service()
    reset_langfuse_service()

    response = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-langfuse-1234",
            "secret_key": "sk-langfuse-9876",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["configured"] is True
    assert data["service_enabled"] is False
    assert data["sdk_available"] is False
    assert data["status_reason"] == "sdk_unavailable"


def test_put_langfuse_settings_reports_sdk_incompatible(client, monkeypatch):
    class _IncompatibleLangfuseClient:
        def __init__(self, **kwargs) -> None:
            return None

        def flush(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(
        "services.langfuse_service.Langfuse",
        _IncompatibleLangfuseClient,
    )
    reset_langfuse_config_service()
    reset_langfuse_service()

    response = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-langfuse-1234",
            "secret_key": "sk-langfuse-9876",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["configured"] is True
    assert data["service_enabled"] is False
    assert data["sdk_available"] is True
    assert data["status_reason"] == "sdk_incompatible"


def test_put_langfuse_settings_reports_client_init_failure(client, monkeypatch):
    class _FailingLangfuseClient:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("boom")

        def start_as_current_observation(self, **kwargs):
            return self

        def propagate_attributes(self, **kwargs):
            return self

        def flush(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(
        "services.langfuse_service.Langfuse",
        _FailingLangfuseClient,
    )
    reset_langfuse_config_service()
    reset_langfuse_service()

    response = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-langfuse-1234",
            "secret_key": "sk-langfuse-9876",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["configured"] is True
    assert data["service_enabled"] is False
    assert data["sdk_available"] is True
    assert data["status_reason"] == "client_init_failed"


def test_storage_config_takes_precedence_over_env(client, monkeypatch):
    monkeypatch.setattr("services.langfuse_service.Langfuse", _FakeLangfuseClient)
    reset_langfuse_config_service()
    reset_langfuse_service()

    persisted = client.put(
        "/api/observability/langfuse",
        json={
            "enabled": True,
            "public_key": "pk-storage",
            "secret_key": "sk-storage",
            "base_url": "https://storage.langfuse.local",
        },
    )
    assert persisted.status_code == 200

    monkeypatch.setenv("CHATBOX_BACKEND_LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("CHATBOX_BACKEND_LANGFUSE_PUBLIC_KEY", "pk-env")
    monkeypatch.setenv("CHATBOX_BACKEND_LANGFUSE_SECRET_KEY", "sk-env")
    monkeypatch.setenv(
        "CHATBOX_BACKEND_LANGFUSE_BASE_URL",
        "https://env.langfuse.local",
    )
    get_settings.cache_clear()
    reset_langfuse_config_service()
    reset_langfuse_service()

    response = client.get("/api/observability/langfuse")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "storage"
    assert data["public_key"] == "pk-storage"
    assert data["base_url"] == "https://storage.langfuse.local"
