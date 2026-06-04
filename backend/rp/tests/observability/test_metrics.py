from __future__ import annotations

from typing import Mapping

from config import Settings
from rp.observability.metrics import (
    MetricsService,
    get_metrics_service,
    reset_metrics_service,
)


class FakeSink:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | float, Mapping[str, str] | None]] = []

    def counter(
        self,
        name: str,
        value: int = 1,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("counter", name, value, labels))

    def timing(
        self,
        name: str,
        ms: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("timing", name, ms, labels))

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("gauge", name, value, labels))


class RaisingSink:
    def counter(
        self,
        name: str,
        value: int = 1,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        raise RuntimeError("counter failed")

    def timing(
        self,
        name: str,
        ms: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        raise RuntimeError("timing failed")

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        raise RuntimeError("gauge failed")


def test_get_metrics_service_caches_until_reset() -> None:
    reset_metrics_service()
    first = get_metrics_service()
    second = get_metrics_service()

    assert first is second

    reset_metrics_service()
    third = get_metrics_service()

    assert third is not first
    reset_metrics_service()


def test_default_service_is_disabled_noop() -> None:
    service = MetricsService(Settings(metrics_enabled=False))

    assert service.enabled is False
    assert service.counter("tool.calls", labels={"status": "ok"}) is None
    assert service.timing("retrieval.latency", 12.5) is None
    assert service.gauge("runtime.active", 3) is None


def test_enabled_service_forwards_metrics_to_sink() -> None:
    sink = FakeSink()
    service = MetricsService(Settings(metrics_enabled=True), sink=sink)

    assert service.enabled is True

    service.counter("tool.calls", labels={"status": "ok"})
    service.timing("retrieval.latency", 12.5)
    service.gauge("runtime.active", 3)

    assert sink.calls == [
        ("counter", "tool.calls", 1, {"status": "ok"}),
        ("timing", "retrieval.latency", 12.5, None),
        ("gauge", "runtime.active", 3, None),
    ]


def test_disabled_toggle_suppresses_real_sink() -> None:
    sink = FakeSink()
    service = MetricsService(Settings(metrics_enabled=False), sink=sink)

    assert service.enabled is False

    service.counter("tool.calls")
    service.timing("retrieval.latency", 12.5)
    service.gauge("runtime.active", 3)

    assert sink.calls == []


def test_raising_sink_is_swallowed_when_enabled() -> None:
    service = MetricsService(Settings(metrics_enabled=True), sink=RaisingSink())

    assert service.enabled is True

    service.counter("tool.calls")
    service.timing("retrieval.latency", 12.5)
    service.gauge("runtime.active", 3)
