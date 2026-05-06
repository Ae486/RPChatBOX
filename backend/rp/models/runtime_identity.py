"""Runtime identity and compiled profile contracts for boot-bar memory slices."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class BranchHeadStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class StoryTurnStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeProfileSnapshotStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class RuntimeProfileModeProfile(BaseModel):
    """Pinned mode-level runtime contract frozen into one snapshot."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    registry_version: str
    mode_profile_ref: str | None = None
    mode_profile_version: int | None = None
    model_profile_ref: str | None = None
    worker_profile_ref: str | None = None

    @field_validator("mode", "registry_version")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class RuntimeWorkerActivation(BaseModel):
    """Minimal worker activation descriptor compiled at snapshot publish time."""

    model_config = ConfigDict(extra="forbid")

    active: bool = True
    profile_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeProfileSnapshotCompiledProfile(BaseModel):
    """Typed top-level compiled profile stored immutably on each snapshot row."""

    model_config = ConfigDict(extra="forbid")

    mode_profile: RuntimeProfileModeProfile
    domain_activation: dict[str, dict[str, Any]] = Field(default_factory=dict)
    block_activation: dict[str, dict[str, Any]] = Field(default_factory=dict)
    worker_activation: dict[str, RuntimeWorkerActivation] = Field(default_factory=dict)
    permission_profile: dict[str, Any] = Field(default_factory=dict)
    retrieval_policy: RetrievalRuntimeConfig = Field(
        default_factory=RetrievalRuntimeConfig
    )
    context_policy: dict[str, Any] = Field(default_factory=dict)
    packet_policy: dict[str, Any] = Field(default_factory=dict)
    writer_model_profile: dict[str, Any] = Field(default_factory=dict)
    worker_model_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mode_specific_settings: dict[str, Any] = Field(default_factory=dict)
