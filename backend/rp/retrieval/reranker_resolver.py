"""Resolution helpers for hosted or local retrieval rerank models."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from models.model_registry import ModelRegistryEntry
from services.model_capability_service import query_model_capabilities
from services.model_registry import ModelRegistryService, get_model_registry_service
from services.provider_registry import ProviderRegistryService, get_provider_registry_service


@dataclass(frozen=True, slots=True)
class HostedRerankerTarget:
    provider_id: str
    model_id: str
    model_name: str
    provider: object
    resolution_source: str


@dataclass(frozen=True, slots=True)
class LocalCrossEncoderTarget:
    provider_id: str
    model_id: str
    model_name: str
    resolution_source: str


class _BaseRerankerResolver:
    """Shared model/provider resolution helpers for rerank-capable models."""

    _RERANK_CAPABILITIES = {"rerank", "cross_encoder_rerank"}

    def __init__(
        self,
        *,
        model_registry_service: ModelRegistryService | None = None,
        provider_registry_service: ProviderRegistryService | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
    ) -> None:
        self._model_registry_service = model_registry_service or get_model_registry_service()
        self._provider_registry_service = provider_registry_service or get_provider_registry_service()
        self._model_id = model_id
        self._provider_id = provider_id

    def _iter_candidate_entries(self) -> Iterable[ModelRegistryEntry]:
        if self._model_id:
            entry = self._model_registry_service.get_entry(self._model_id)
            if entry is None or not entry.is_enabled:
                return ()
            if self._provider_id and entry.provider_id != self._provider_id:
                return ()
            return (entry,)

        return (
            entry
            for entry in self._model_registry_service.list_entries(provider_id=self._provider_id)
            if entry.is_enabled
        )

    def _has_declared_rerank_capability(self, entry: ModelRegistryEntry) -> bool:
        profile = entry.capability_profile
        if profile is not None and profile.mode in {"rerank", "cross_encoder_rerank"}:
            return True
        capabilities = {item.strip().lower() for item in entry.capabilities}
        return bool(capabilities.intersection(self._RERANK_CAPABILITIES))


class HostedRerankerResolver(_BaseRerankerResolver):
    """Resolve a hosted rerank-capable model/provider pair from registries."""

    _SUPPORTED_PROVIDER_TYPES = {
        "openai": "openai",
        "cohere": "cohere",
        "voyage": "voyage",
        "together_ai": "together_ai",
        "deepinfra": "deepinfra",
        "fireworks_ai": "fireworks_ai",
    }

    def __init__(
        self,
        *,
        model_registry_service: ModelRegistryService | None = None,
        provider_registry_service: ProviderRegistryService | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
        capability_probe: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            model_registry_service=model_registry_service,
            provider_registry_service=provider_registry_service,
            model_id=model_id,
            provider_id=provider_id,
        )
        self._capability_probe = capability_probe or query_model_capabilities

    def resolve_target(self) -> HostedRerankerTarget | None:
        for model_entry in self._iter_candidate_entries():
            provider_entry = self._provider_registry_service.get_entry(model_entry.provider_id)
            if provider_entry is None or not provider_entry.is_enabled:
                continue
            if provider_entry.type not in self._SUPPORTED_PROVIDER_TYPES:
                continue
            if not self._supports_hosted_rerank(model_entry, provider_type=provider_entry.type):
                continue

            return HostedRerankerTarget(
                provider_id=provider_entry.id,
                model_id=model_entry.id,
                model_name=model_entry.model_name,
                provider=provider_entry.to_runtime_provider(),
                resolution_source=self._resolution_source(model_entry, provider_type=provider_entry.type),
            )
        return None

    def _supports_hosted_rerank(
        self,
        entry: ModelRegistryEntry,
        *,
        provider_type: str,
    ) -> bool:
        if self._has_declared_rerank_capability(entry):
            return True
        try:
            capabilities = self._capability_probe(provider_type, entry.model_name)
        except Exception:
            return False
        return bool(capabilities.get("rerank") or capabilities.get("mode") == "rerank")

    def _resolution_source(self, entry: ModelRegistryEntry, *, provider_type: str) -> str:
        if self._has_declared_rerank_capability(entry):
            return "registry_capability"
        try:
            capabilities = self._capability_probe(provider_type, entry.model_name)
        except Exception:
            return "unknown"
        if capabilities.get("rerank") or capabilities.get("mode") == "rerank":
            return "litellm_capability"
        return "unknown"


class LocalCrossEncoderResolver(_BaseRerankerResolver):
    """Resolve a local cross-encoder rerank model from registries."""

    _SUPPORTED_PROVIDER_TYPES = {
        "local": "local",
        "huggingface": "huggingface",
        "sentence_transformers": "sentence_transformers",
    }

    def resolve_target(self) -> LocalCrossEncoderTarget | None:
        for model_entry in self._iter_candidate_entries():
            provider_entry = self._provider_registry_service.get_entry(model_entry.provider_id)
            if provider_entry is None or not provider_entry.is_enabled:
                continue
            if provider_entry.type not in self._SUPPORTED_PROVIDER_TYPES:
                continue
            if not self._has_declared_rerank_capability(model_entry):
                continue

            return LocalCrossEncoderTarget(
                provider_id=provider_entry.id,
                model_id=model_entry.id,
                model_name=model_entry.model_name,
                resolution_source="registry_capability",
            )
        return None
