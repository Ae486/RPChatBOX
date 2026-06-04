"""No-op service metrics seam for RP observability."""

from __future__ import annotations

import logging
from threading import RLock
from typing import Mapping, Protocol, runtime_checkable

from config import Settings, get_settings

logger = logging.getLogger(__name__)
_SERVICE_LOCK = RLock()
_cached_metrics_service: MetricsService | None = None


@runtime_checkable
class MetricsSink(Protocol):
    """Backend-agnostic sink contract for objective service metrics."""

    def counter(
        self,
        name: str,
        value: int = 1,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record a counter increment."""

    def timing(
        self,
        name: str,
        ms: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record a duration in milliseconds."""

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record an instantaneous value."""


class _NoopMetricsSink:
    """Default sink that intentionally drops every metric emission."""

    def counter(
        self,
        name: str,
        value: int = 1,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        return None

    def timing(
        self,
        name: str,
        ms: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        return None

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        return None


class MetricsService:
    """Thin metrics facade with disabled/no-op behavior by default."""

    def __init__(
        self,
        settings: Settings | None = None,
        sink: MetricsSink | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._sink = sink or _NoopMetricsSink()

    @property
    def enabled(self) -> bool:
        return bool(self._settings.metrics_enabled) and not isinstance(
            self._sink,
            _NoopMetricsSink,
        )

    def counter(
        self,
        name: str,
        value: int = 1,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            self._sink.counter(name, value, labels=labels)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Metrics counter emission failed")

    def timing(
        self,
        name: str,
        ms: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            self._sink.timing(name, ms, labels=labels)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Metrics timing emission failed")

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            self._sink.gauge(name, value, labels=labels)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Metrics gauge emission failed")


def get_metrics_service() -> MetricsService:
    global _cached_metrics_service
    with _SERVICE_LOCK:
        if _cached_metrics_service is None:
            _cached_metrics_service = MetricsService()
        return _cached_metrics_service


def reset_metrics_service() -> None:
    global _cached_metrics_service
    with _SERVICE_LOCK:
        _cached_metrics_service = None
