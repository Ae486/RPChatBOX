"""Story-scoped retrieval runtime model selections."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RetrievalRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model_id: str | None = None
    embedding_provider_id: str | None = None
    rerank_model_id: str | None = None
    rerank_provider_id: str | None = None

    def overlay(self, *, override: "RetrievalRuntimeConfig | None") -> "RetrievalRuntimeConfig":
        if override is None:
            return self
        return self.model_copy(
            update={
                "embedding_model_id": override.embedding_model_id or self.embedding_model_id,
                "embedding_provider_id": override.embedding_provider_id or self.embedding_provider_id,
                "rerank_model_id": override.rerank_model_id or self.rerank_model_id,
                "rerank_provider_id": override.rerank_provider_id or self.rerank_provider_id,
            }
        )
