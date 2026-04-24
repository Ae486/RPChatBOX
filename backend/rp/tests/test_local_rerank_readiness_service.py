"""Tests for local rerank readiness inspection."""

from __future__ import annotations

from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.models.retrieval_local_rerank import LocalRerankDependencyStatus
from rp.services.local_rerank_readiness_service import LocalRerankReadinessService


class _FakeModelRegistryService:
    def __init__(self, entries: list[ModelRegistryEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def get_entry(self, model_id: str):
        return self._entries.get(model_id)

    def list_entries(self, *, provider_id: str | None = None):
        entries = list(self._entries.values())
        if provider_id is not None:
            entries = [entry for entry in entries if entry.provider_id == provider_id]
        return entries


class _FakeProviderRegistryService:
    def __init__(self, entries: list[ProviderRegistryEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def get_entry(self, provider_id: str):
        return self._entries.get(provider_id)


def _provider_entry() -> ProviderRegistryEntry:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return ProviderRegistryEntry(
        id="provider-local-rerank",
        name="Local Rerank",
        type="local",
        api_key="unused",
        api_url="local://cross-encoder",
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _model_entry() -> ModelRegistryEntry:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return ModelRegistryEntry(
        id="model-local-rerank",
        provider_id="provider-local-rerank",
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
        display_name="MS MARCO Cross Encoder",
        capabilities=["cross_encoder_rerank"],
        capability_source="user_declared",
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _deps(*, installed: bool) -> list[LocalRerankDependencyStatus]:
    return [
        LocalRerankDependencyStatus(
            package=name,
            module=name.replace("-", "_"),
            installed=installed,
            version="1.0.0" if installed else None,
        )
        for name in ("sentence-transformers", "torch", "transformers")
    ]


def test_local_rerank_readiness_reports_unconfigured_when_no_target():
    service = LocalRerankReadinessService(
        model_registry_service=_FakeModelRegistryService([]),
        provider_registry_service=_FakeProviderRegistryService([]),
        dependency_inspector=lambda: _deps(installed=True),
    )

    readiness = service.get_readiness()

    assert readiness.status == "unconfigured"
    assert readiness.configured is False
    assert "local_rerank_unconfigured:no_local_cross_encoder_model" in readiness.warnings


def test_local_rerank_readiness_reports_missing_dependencies():
    service = LocalRerankReadinessService(
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        dependency_inspector=lambda: _deps(installed=False),
    )

    readiness = service.get_readiness()

    assert readiness.status == "dependency_missing"
    assert readiness.configured is True
    assert readiness.model_id == "model-local-rerank"
    assert "local_rerank_dependency_missing:sentence-transformers,torch,transformers" in readiness.warnings


def test_local_rerank_readiness_can_attempt_model_load():
    loaded: list[str] = []
    service = LocalRerankReadinessService(
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        dependency_inspector=lambda: _deps(installed=True),
        model_loader=lambda model_name: loaded.append(model_name) or object(),
    )

    readiness = service.get_readiness(include_model_load=True)

    assert readiness.status == "ready"
    assert readiness.model_load_attempted is True
    assert readiness.model_load_ok is True
    assert loaded == ["cross-encoder/ms-marco-MiniLM-L-6-v2"]


def test_local_rerank_readiness_reports_load_failed():
    service = LocalRerankReadinessService(
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        dependency_inspector=lambda: _deps(installed=True),
        model_loader=lambda model_name: (_ for _ in ()).throw(RuntimeError("download blocked")),
    )

    readiness = service.get_readiness(include_model_load=True)

    assert readiness.status == "load_failed"
    assert readiness.model_load_attempted is True
    assert readiness.model_load_ok is False
    assert readiness.load_error == "RuntimeError: download blocked"
