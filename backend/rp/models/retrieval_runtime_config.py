"""Story-scoped retrieval runtime model selections."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphExtractionRetryPolicy(BaseModel):
    """Retry policy for asynchronous graph extraction maintenance jobs."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3


class RetrievalRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model_id: str | None = None
    embedding_provider_id: str | None = None
    rerank_model_id: str | None = None
    rerank_provider_id: str | None = None
    graph_extraction_provider_id: str | None = None
    graph_extraction_model_id: str | None = None
    graph_extraction_structured_output_mode: str = "json_schema"
    graph_extraction_temperature: float = 0.0
    graph_extraction_max_output_tokens: int = 2048
    graph_extraction_timeout_ms: int = 60000
    graph_extraction_retry_policy: GraphExtractionRetryPolicy = Field(
        default_factory=GraphExtractionRetryPolicy
    )
    graph_extraction_fallback_model_ref: str | None = None
    graph_extraction_enabled: bool = True

    def overlay(
        self, *, override: "RetrievalRuntimeConfig | None"
    ) -> "RetrievalRuntimeConfig":
        if override is None:
            return self
        updates: dict[str, Any] = {}
        for field_name in type(self).model_fields:
            if field_name not in override.model_fields_set:
                updates[field_name] = getattr(self, field_name)
                continue

            override_value = getattr(override, field_name)
            if override_value is None:
                updates[field_name] = getattr(self, field_name)
            elif isinstance(override_value, str) and not override_value.strip():
                updates[field_name] = getattr(self, field_name)
            else:
                updates[field_name] = override_value
        return self.model_copy(
            update=updates,
        )

    @property
    def graph_extraction_configured(self) -> bool:
        return bool(
            self.graph_extraction_provider_id and self.graph_extraction_model_id
        )
