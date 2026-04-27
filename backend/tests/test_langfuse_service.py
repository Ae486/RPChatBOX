from __future__ import annotations

from config import Settings
from models.langfuse_config import LangfuseRuntimeConfig
import services.langfuse_service as langfuse_service_module
from services.langfuse_service import LangfuseService


def test_langfuse_service_is_noop_when_disabled():
    service = LangfuseService(Settings())

    assert service.enabled is False
    with service.propagate_attributes(session_id="session-1"):
        with service.start_as_current_observation(name="noop") as observation:
            observation.update(output={"ok": True})
            child = observation.start_as_current_observation(name="child")
            child.update(output={"child": True})

    service.flush()
    service.shutdown()


class _StubConfigService:
    def __init__(self, config: LangfuseRuntimeConfig) -> None:
        self._config = config

    def get_effective_config(self) -> LangfuseRuntimeConfig:
        return self._config


class _CountingLangfuseClient:
    shutdown_calls = 0

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def start_as_current_observation(self, **kwargs):
        return self

    def propagate_attributes(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, **kwargs) -> None:
        return None

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        type(self).shutdown_calls += 1


def test_reset_langfuse_service_shuts_down_cached_client(monkeypatch):
    _CountingLangfuseClient.shutdown_calls = 0
    monkeypatch.setattr(
        langfuse_service_module,
        "Langfuse",
        _CountingLangfuseClient,
    )
    monkeypatch.setattr(
        langfuse_service_module,
        "get_langfuse_config_service",
        lambda: _StubConfigService(
            LangfuseRuntimeConfig(
                enabled=True,
                public_key="pk-live",
                secret_key="sk-live",
            )
        ),
    )

    langfuse_service_module.reset_langfuse_service()
    service = langfuse_service_module.get_langfuse_service()

    assert service.enabled is True

    langfuse_service_module.reset_langfuse_service()

    assert _CountingLangfuseClient.shutdown_calls == 1


def test_langfuse_service_maps_base_url_to_sdk_host(monkeypatch):
    captured_kwargs: dict[str, object] = {}

    class _CapturingLangfuseClient:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

        def start_as_current_observation(self, **kwargs):
            return self

        def propagate_attributes(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, **kwargs) -> None:
            return None

        def flush(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(
        langfuse_service_module,
        "Langfuse",
        _CapturingLangfuseClient,
    )
    monkeypatch.setattr(
        langfuse_service_module,
        "get_langfuse_config_service",
        lambda: _StubConfigService(
            LangfuseRuntimeConfig(
                enabled=True,
                public_key="pk-live",
                secret_key="sk-live",
                base_url="https://us.cloud.langfuse.com",
            )
        ),
    )

    service = LangfuseService(Settings())

    assert service.enabled is True
    assert captured_kwargs["host"] == "https://us.cloud.langfuse.com"
    assert "base_url" not in captured_kwargs


def test_langfuse_service_accepts_module_level_propagate_attributes(monkeypatch):
    class _V4StyleLangfuseClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def start_as_current_observation(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, **kwargs) -> None:
            return None

        def flush(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    class _ModulePropagationContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        langfuse_service_module,
        "Langfuse",
        _V4StyleLangfuseClient,
    )
    monkeypatch.setattr(
        langfuse_service_module,
        "langfuse_propagate_attributes",
        lambda **kwargs: _ModulePropagationContext(),
    )
    monkeypatch.setattr(
        langfuse_service_module,
        "get_langfuse_config_service",
        lambda: _StubConfigService(
            LangfuseRuntimeConfig(
                enabled=True,
                public_key="pk-live",
                secret_key="sk-live",
            )
        ),
    )

    service = LangfuseService(Settings())

    assert service.enabled is True
    with service.propagate_attributes(session_id="session-1"):
        with service.start_as_current_observation(name="smoke") as observation:
            observation.update(output={"ok": True})
