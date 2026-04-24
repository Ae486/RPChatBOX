"""Embedding generation for retrieval-core."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk
from services.litellm_service import LiteLLMService, get_litellm_service
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class _EmbeddingTarget:
    provider_id: str | None
    model_name: str
    runtime_provider: object | None


class Embedder:
    """Use LiteLLM embeddings when available and deterministic vectors as fallback."""

    _DEFAULT_MODELS = {
        "openai": "text-embedding-3-small",
        "deepseek": "text-embedding-3-small",
        "gemini": "text-embedding-004",
    }

    def __init__(
        self,
        *,
        litellm_service: LiteLLMService | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        fallback_dim: int = 64,
    ) -> None:
        self._litellm_service = litellm_service or get_litellm_service()
        self._provider_id = provider_id
        self._model_id = model_id
        self._fallback_dim = fallback_dim
        self.last_warnings: list[str] = []

    def embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddingRecord]:
        texts = [self._text_for_chunk(chunk) for chunk in chunks]
        target = self._resolve_target()
        vectors = self._embed_texts(texts, target=target)
        now = _utcnow()
        return [
            EmbeddingRecord(
                embedding_id=f"emb_{uuid4().hex}",
                chunk_id=chunk.chunk_id,
                embedding_model=target.model_name,
                provider_id=target.provider_id,
                vector_dim=len(vector),
                status="completed",
                is_active=True,
                embedding_vector=vector,
                created_at=now,
                updated_at=now,
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]

    @staticmethod
    def _text_for_chunk(chunk: KnowledgeChunk) -> str:
        contextual_text = chunk.metadata.get("contextual_text")
        if isinstance(contextual_text, str) and contextual_text.strip():
            return contextual_text
        return chunk.text

    def embed_query(self, text: str) -> tuple[list[float], list[str], str]:
        target = self._resolve_target()
        warnings_before = list(self.last_warnings)
        vector = self._embed_texts([text], target=target)[0]
        warnings = [item for item in self.last_warnings if item not in warnings_before]
        return vector, warnings, target.model_name

    def _embed_texts(self, texts: Sequence[str], *, target: _EmbeddingTarget) -> list[list[float]]:
        self.last_warnings = []
        if target.runtime_provider is not None:
            try:
                response = self._litellm_service.embedding(
                    provider=target.runtime_provider,
                    model=target.model_name,
                    input_texts=list(texts),
                )
                data = response.get("data") or []
                vectors = [list(item.get("embedding") or []) for item in data if isinstance(item, dict)]
                if len(vectors) == len(texts) and all(vector for vector in vectors):
                    return [[float(item) for item in vector] for vector in vectors]
                self.last_warnings.append("embedding_response_incomplete:fallback_local")
            except Exception as exc:  # pragma: no cover - network/provider dependent
                self.last_warnings.append(f"embedding_provider_failed:{type(exc).__name__}")

        self.last_warnings.append("embedding_fallback:deterministic_local_v1")
        return [self._deterministic_vector(text) for text in texts]

    def _resolve_target(self) -> _EmbeddingTarget:
        model_registry = get_model_registry_service()
        provider_registry = get_provider_registry_service()

        if self._model_id:
            model_entry = model_registry.get_entry(self._model_id)
            if model_entry is not None and model_entry.is_enabled:
                provider_entry = provider_registry.get_entry(model_entry.provider_id)
                if provider_entry is not None and provider_entry.is_enabled:
                    return _EmbeddingTarget(
                        provider_id=provider_entry.id,
                        model_name=model_entry.model_name,
                        runtime_provider=provider_entry.to_runtime_provider(),
                    )

        preferred_model = self._find_embedding_capable_model(model_registry.list_entries())
        if preferred_model is not None:
            provider_entry = provider_registry.get_entry(preferred_model.provider_id)
            if provider_entry is not None and provider_entry.is_enabled:
                return _EmbeddingTarget(
                    provider_id=provider_entry.id,
                    model_name=preferred_model.model_name,
                    runtime_provider=provider_entry.to_runtime_provider(),
                )

        providers = provider_registry.list_entries()
        if self._provider_id:
            providers = [item for item in providers if item.id == self._provider_id]

        for provider_entry in providers:
            if not provider_entry.is_enabled:
                continue
            default_model = self._DEFAULT_MODELS.get(provider_entry.type)
            if default_model is None:
                continue
            return _EmbeddingTarget(
                provider_id=provider_entry.id,
                model_name=default_model,
                runtime_provider=provider_entry.to_runtime_provider(),
            )

        self.last_warnings = ["embedding_provider_unconfigured:fallback_local"]
        return _EmbeddingTarget(
            provider_id="local_fallback",
            model_name="deterministic_local_v1",
            runtime_provider=None,
        )

    @staticmethod
    def _find_embedding_capable_model(entries: list[ModelRegistryEntry]) -> ModelRegistryEntry | None:
        for entry in entries:
            if not entry.is_enabled:
                continue
            profile = entry.capability_profile
            if profile is not None and profile.mode == "embedding":
                return entry
            if "embedding" in entry.capabilities or "embedding" in entry.model_name.lower():
                return entry
        return None

    def _deterministic_vector(self, text: str) -> list[float]:
        vector = [0.0] * self._fallback_dim
        tokens = _TOKEN_RE.findall(text.lower()) or [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(8):
                index = digest[offset] % self._fallback_dim
                sign = 1.0 if digest[8 + offset] % 2 == 0 else -1.0
                weight = 1.0 + (digest[16 + offset] / 255.0)
                vector[index] += sign * weight
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]
