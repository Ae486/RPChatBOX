"""Langfuse service wrapper with graceful no-op fallback."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from threading import RLock
from typing import Any

from config import Settings, get_settings
from services.langfuse_config_service import get_langfuse_config_service

logger = logging.getLogger(__name__)
_SERVICE_LOCK = RLock()
_cached_langfuse_service: "LangfuseService | None" = None

try:  # pragma: no cover - optional dependency path
    from langfuse import Langfuse, propagate_attributes as langfuse_propagate_attributes
except ImportError:  # pragma: no cover - optional dependency path
    Langfuse = None
    langfuse_propagate_attributes = None


class _NoopObservation:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, **kwargs) -> None:
        return None

    def score(self, *args, **kwargs) -> None:
        return None

    def score_trace(self, *args, **kwargs) -> None:
        return None

    def start_as_current_observation(self, *args, **kwargs):
        return _NoopObservation()


class LangfuseService:
    """Thin wrapper over Langfuse SDK with disabled/no-op behavior."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = self._build_client()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def start_as_current_observation(self, **kwargs):
        if self._client is None:
            return _NoopObservation()
        try:
            return self._client.start_as_current_observation(**kwargs)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Langfuse start_as_current_observation failed")
            return _NoopObservation()

    def propagate_attributes(self, **kwargs):
        if self._client is None:
            return nullcontext()
        try:
            client_propagate = getattr(self._client, "propagate_attributes", None)
            if callable(client_propagate):
                return client_propagate(**kwargs)
            if callable(langfuse_propagate_attributes):
                return langfuse_propagate_attributes(**kwargs)
            logger.warning("Langfuse propagate_attributes API is unavailable")
            return nullcontext()
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Langfuse propagate_attributes failed")
            return nullcontext()

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Langfuse flush failed")

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            self._client.shutdown()
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Langfuse shutdown failed")

    def _build_client(self):
        runtime_config = get_langfuse_config_service().get_effective_config()
        if not runtime_config.enabled:
            return None
        if Langfuse is None:
            logger.warning("Langfuse is enabled but python package is not installed")
            return None
        if not (runtime_config.public_key and runtime_config.secret_key):
            logger.warning("Langfuse is enabled but public/secret key is missing")
            return None

        kwargs: dict[str, Any] = {
            "public_key": runtime_config.public_key,
            "secret_key": runtime_config.secret_key,
            "debug": runtime_config.debug,
        }
        if runtime_config.base_url:
            # Langfuse v2 Python SDK expects `host`; the backend settings/API
            # continue to expose `base_url` as the user-facing field.
            kwargs["host"] = runtime_config.base_url
        if runtime_config.environment:
            kwargs["environment"] = runtime_config.environment
        if runtime_config.release:
            kwargs["release"] = runtime_config.release
        if runtime_config.sample_rate is not None:
            kwargs["sample_rate"] = runtime_config.sample_rate

        try:
            client = Langfuse(**kwargs)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Failed to initialize Langfuse client")
            return None
        if not _langfuse_client_is_compatible(client):
            logger.warning(
                "Langfuse SDK is installed but missing required tracing methods; "
                "please use a compatible v4 SDK."
            )
            return None
        logger.info(
            "[OBS] Langfuse enabled base_url=%s environment=%s release=%s",
            runtime_config.base_url or "default",
            runtime_config.environment or "default",
            runtime_config.release or "default",
        )
        return client


def get_langfuse_service() -> LangfuseService:
    global _cached_langfuse_service
    with _SERVICE_LOCK:
        if _cached_langfuse_service is None:
            _cached_langfuse_service = LangfuseService()
        return _cached_langfuse_service


def reset_langfuse_service() -> None:
    global _cached_langfuse_service
    with _SERVICE_LOCK:
        service = _cached_langfuse_service
        _cached_langfuse_service = None
    if service is not None:
        service.shutdown()


def is_langfuse_sdk_available() -> bool:
    return Langfuse is not None


def is_langfuse_sdk_compatible() -> bool:
    if Langfuse is None:
        return False
    required_methods = (
        "start_as_current_observation",
        "flush",
        "shutdown",
    )
    has_client_methods = all(hasattr(Langfuse, method) for method in required_methods)
    has_propagation_api = hasattr(Langfuse, "propagate_attributes") or callable(
        langfuse_propagate_attributes
    )
    return has_client_methods and has_propagation_api


def _langfuse_client_is_compatible(client: Any) -> bool:
    required_methods = (
        "start_as_current_observation",
        "flush",
        "shutdown",
    )
    has_client_methods = all(hasattr(client, method) for method in required_methods)
    has_propagation_api = hasattr(client, "propagate_attributes") or callable(
        langfuse_propagate_attributes
    )
    return has_client_methods and has_propagation_api
