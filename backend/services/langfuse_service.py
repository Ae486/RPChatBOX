"""Langfuse service wrapper with graceful no-op fallback."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

from config import Settings, get_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency path
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - optional dependency path
    Langfuse = None


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
            return self._client.propagate_attributes(**kwargs)
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
        if not self._settings.langfuse_enabled:
            return None
        if Langfuse is None:
            logger.warning("Langfuse is enabled but python package is not installed")
            return None
        if not (
            self._settings.langfuse_public_key and self._settings.langfuse_secret_key
        ):
            logger.warning("Langfuse is enabled but public/secret key is missing")
            return None

        kwargs: dict[str, Any] = {
            "public_key": self._settings.langfuse_public_key,
            "secret_key": self._settings.langfuse_secret_key,
            "debug": self._settings.langfuse_debug,
        }
        if self._settings.langfuse_base_url:
            kwargs["base_url"] = self._settings.langfuse_base_url
        if self._settings.langfuse_environment:
            kwargs["environment"] = self._settings.langfuse_environment
        if self._settings.langfuse_release:
            kwargs["release"] = self._settings.langfuse_release
        if self._settings.langfuse_sample_rate is not None:
            kwargs["sample_rate"] = self._settings.langfuse_sample_rate

        try:
            client = Langfuse(**kwargs)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Failed to initialize Langfuse client")
            return None
        logger.info(
            "[OBS] Langfuse enabled base_url=%s environment=%s release=%s",
            self._settings.langfuse_base_url or "default",
            self._settings.langfuse_environment or "default",
            self._settings.langfuse_release or "default",
        )
        return client


@lru_cache
def get_langfuse_service() -> LangfuseService:
    return LangfuseService()


def reset_langfuse_service() -> None:
    get_langfuse_service.cache_clear()
