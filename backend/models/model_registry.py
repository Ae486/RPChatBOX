"""Model registry models."""
from __future__ import annotations
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ModelRegistryDefaultParams(BaseModel):
    """Default generation parameters persisted with the model."""

    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stream_output: bool = True


class ModelCapabilityProfile(BaseModel):
    """Structured capability profile resolved from LiteLLM or project overrides."""

    known: bool = False
    provider_supported: bool = False
    capability_source: str = "default_unmapped"
    resolution_strategy: str | None = None
    transport_provider_type: str | None = None
    semantic_provider_type: str | None = None
    semantic_lookup_model: str | None = None
    mode: str | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    output_vector_size: int | None = None
    supports_function_calling: bool | None = None
    supports_parallel_function_calling: bool | None = None
    supports_vision: bool | None = None
    supports_response_schema: bool | None = None
    supports_tool_choice: bool | None = None
    supports_reasoning: bool | None = None
    supports_pdf_input: bool | None = None
    supports_web_search: bool | None = None
    supports_audio_input: bool | None = None
    supports_audio_output: bool | None = None
    supports_system_messages: bool | None = None
    supported_openai_params: list[str] = Field(default_factory=list)
    recommended_capabilities: list[str] = Field(default_factory=list)


class ModelRegistryEntry(BaseModel):
    """Persistent model record stored by the backend registry."""

    id: str
    provider_id: str
    model_name: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    capability_source: str | None = None
    capability_profile: ModelCapabilityProfile | None = None
    default_params: ModelRegistryDefaultParams = Field(
        default_factory=ModelRegistryDefaultParams
    )
    is_enabled: bool = True
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def with_timestamps(self, *, existing: "ModelRegistryEntry" | None = None) -> "ModelRegistryEntry":
        """Fill created/updated timestamps consistently."""
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={
                "created_at": existing.created_at if existing and existing.created_at else now,
                "updated_at": now,
            }
        )


class ModelRegistrySummary(BaseModel):
    """Safe model metadata returned by registry endpoints."""

    id: str
    provider_id: str
    model_name: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    capability_source: str | None = None
    capability_profile: ModelCapabilityProfile | None = None
    default_params: ModelRegistryDefaultParams = Field(
        default_factory=ModelRegistryDefaultParams
    )
    is_enabled: bool = True
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_entry(cls, entry: ModelRegistryEntry) -> "ModelRegistrySummary":
        return cls(
            id=entry.id,
            provider_id=entry.provider_id,
            model_name=entry.model_name,
            display_name=entry.display_name,
            capabilities=entry.capabilities,
            capability_source=entry.capability_source,
            capability_profile=entry.capability_profile,
            default_params=entry.default_params,
            is_enabled=entry.is_enabled,
            description=entry.description,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
