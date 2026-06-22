"""S3 memory maintenance candidate DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from rp.models.memory.contract_registry import MemorySourceRef


SUPPORTED_MEMORY_MAINTENANCE_OPERATION_KINDS: tuple[str, ...] = (
    "append_item",
    "update_item",
    "remove_item",
)
FORBIDDEN_MEMORY_SCHEMA_OPERATION_KINDS: tuple[str, ...] = (
    "create_domain",
    "delete_domain",
    "create_block",
    "delete_block",
    "create_field",
    "delete_field",
    "schema_change",
    "change_schema",
)


class MemoryMaintenanceOperation(BaseModel):
    """One candidate operation against the declared facts field."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    field_id: str = "facts"
    target_fact_id: str | None = None
    target_fact_handle: str | None = None
    group_key: str | None = None
    subject_label: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", "field_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "target_fact_id",
        "target_fact_handle",
        "group_key",
        "subject_label",
        "content",
    )
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _validate_target_identity(self) -> "MemoryMaintenanceOperation":
        if self.target_fact_id is not None and self.target_fact_handle is not None:
            raise ValueError("target_fact_id and target_fact_handle are mutually exclusive")
        return self

    def target_key(self) -> str | None:
        """Return the stable or run-scoped target key for duplicate detection."""

        if self.target_fact_id is not None:
            return f"id:{self.target_fact_id}"
        if self.target_fact_handle is not None:
            return f"handle:{self.target_fact_handle}"
        return None


class MemoryMaintenanceCandidate(BaseModel):
    """Candidate field operations for one target domain/block."""

    model_config = ConfigDict(extra="forbid")

    target_domain: str
    target_block_id: str
    base_block_revision_id: str | None = None
    operations: list[MemoryMaintenanceOperation]
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    change_summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_domain", "target_block_id", "change_summary")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("base_block_revision_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="base_block_revision_id")

    @model_validator(mode="after")
    def _require_operations(self) -> "MemoryMaintenanceCandidate":
        if not self.operations:
            raise ValueError("candidate requires at least one operation")
        return self


class MemoryMaintenanceCandidateBatch(BaseModel):
    """Worker-emitted batch of non-truth memory maintenance candidates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    worker_id: str
    phase: str
    candidates: list[MemoryMaintenanceCandidate]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version", "worker_id", "phase")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _require_candidates(self) -> "MemoryMaintenanceCandidateBatch":
        if not self.candidates:
            raise ValueError("candidate batch requires at least one candidate")
        return self


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized
