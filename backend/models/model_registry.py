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


class ModelRegistryEntry(BaseModel):
    """Persistent model record stored by the backend registry."""

    id: str
    provider_id: str
    model_name: str
    display_name: str
    capabilities: list[str] = Field(default_factory=lambda: ["text"])
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
            default_params=entry.default_params,
            is_enabled=entry.is_enabled,
            description=entry.description,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
