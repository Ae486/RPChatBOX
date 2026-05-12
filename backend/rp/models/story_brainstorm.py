"""Writer brainstorm Runtime Workspace contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


class BrainstormSessionStatus(StrEnum):
    OPEN = "open"
    SUMMARIZED = "summarized"
    REVIEWING = "reviewing"
    DISPATCHED = "dispatched"
    CLOSED = "closed"


class BrainstormItemStatus(StrEnum):
    PROPOSED = "proposed"
    EDITED = "edited"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"
    DISPATCHED = "dispatched"
    APPLIED = "applied"
    PENDING_REVIEW = "pending_review"
    CONFLICT = "conflict"
    FAILED = "failed"


class BrainstormItem(BaseModel):
    """User-editable intent item; routing fields are intentionally forbidden."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    summary_text: str
    evidence_text_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    user_edited: bool = False
    status: BrainstormItemStatus = BrainstormItemStatus.PROPOSED

    @field_validator("item_id", "summary_text")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("uncertainty")
    @classmethod
    def _normalize_uncertainty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="uncertainty")

    @field_validator("evidence_text_refs")
    @classmethod
    def _normalize_evidence_refs(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="evidence_text_refs")


class BrainstormSession(BaseModel):
    """Branch/turn-scoped brainstorm scratch persisted as Runtime Workspace material."""

    model_config = ConfigDict(extra="forbid")

    brainstorm_id: str
    identity: MemoryRuntimeIdentity
    status: BrainstormSessionStatus = BrainstormSessionStatus.OPEN
    prompt: str
    items: list[BrainstormItem] = Field(default_factory=list)
    source_entry_ids: list[str] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    created_by: str
    updated_by: str
    close_reason: str | None = None
    summary_trace: dict[str, Any] = Field(default_factory=dict)
    apply_receipts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("brainstorm_id", "prompt", "created_by", "updated_by")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("close_reason")
    @classmethod
    def _normalize_close_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="close_reason")

    @field_validator("source_entry_ids")
    @classmethod
    def _normalize_source_entry_ids(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="source_entry_ids")


class BrainstormSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    prompt: str
    source_entry_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("actor", "prompt")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("source_entry_ids")
    @classmethod
    def _normalize_source_entry_ids(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="source_entry_ids")


class BrainstormStructuredItem(BaseModel):
    """Strict LLM output item for the dedicated brainstorm_summarize prompt."""

    model_config = ConfigDict(extra="forbid")

    summary_text: str
    evidence_text_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None

    @field_validator("summary_text")
    @classmethod
    def _require_summary(cls, value: str) -> str:
        return _require_non_blank(value, field_name="summary_text")

    @field_validator("uncertainty")
    @classmethod
    def _normalize_uncertainty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="uncertainty")

    @field_validator("evidence_text_refs")
    @classmethod
    def _normalize_evidence_refs(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="evidence_text_refs")


class BrainstormStructuredSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BrainstormStructuredItem] = Field(default_factory=list, max_length=12)


class BrainstormSummarizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    model_id: str | None = None
    provider_id: str | None = None
    max_items: int = Field(default=8, ge=1, le=12)
    dry_run_items: list[BrainstormStructuredItem] | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("model_id", "provider_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class BrainstormItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    summary_text: str | None = None
    evidence_text_refs: list[str] | None = None
    uncertainty: str | None = None
    status: Literal["edited", "rejected", "confirmed"] | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("summary_text", "uncertainty")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("evidence_text_refs")
    @classmethod
    def _normalize_optional_refs(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return _normalize_text_list(values, field_name="evidence_text_refs")


class BrainstormCoreFieldChange(BaseModel):
    """Executable Core worker output; backend fills old_value before mutation."""

    model_config = ConfigDict(extra="forbid")

    source_item_id: str
    target_ref: str
    base_revision: str
    operation: Literal["replace_field", "set_field", "delete_field"]
    field_path: str
    new_value: Any = Field(...)
    reason: str | None = None
    source_refs: list[MemorySourceRef] = Field(default_factory=list)

    @field_validator("source_item_id", "target_ref", "base_revision", "field_path")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="reason")


class BrainstormApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    item_ids: list[str] = Field(default_factory=list)
    core_field_changes: list[BrainstormCoreFieldChange] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("item_ids")
    @classmethod
    def _normalize_item_ids(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="item_ids")

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="reason")


class BrainstormDispatchReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str
    status: Literal[
        "applied",
        "pending_review",
        "redirect",
        "conflict",
        "failed",
        "skipped",
    ]
    target_ref: str | None = None
    proposal_id: str | None = None
    operation: str | None = None
    field_path: str | None = None
    base_revision: str | None = None
    old_value: Any = None
    new_value: Any = None
    reason_codes: list[str] = Field(default_factory=list)
    message: str | None = None
    review_entrypoint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrainstormApplyReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brainstorm_id: str
    identity: MemoryRuntimeIdentity
    status: Literal["applied", "pending_review", "redirect", "conflict", "failed"]
    dispatch_receipts: list[BrainstormDispatchReceipt] = Field(default_factory=list)
    refresh: dict[str, Any] = Field(default_factory=dict)


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


def _normalize_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_non_blank(value, field_name=field_name)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized
