"""Writer brainstorm Runtime Workspace contracts for Stage W."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrainstormSessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class BrainstormContextWindowStatus(StrEnum):
    ACTIVE = "active"
    FLUSHED = "flushed"


class BrainstormContextFlushReason(StrEnum):
    SUMMARIZE = "summarize"
    CONTINUE_WRITING = "continue_writing"


class BrainstormBatchStatus(StrEnum):
    DRAFT = "draft"
    PENDING_PROCESSING = "pending_processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class BrainstormItemStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"
    PENDING_PROCESSING = "pending_processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class BrainstormItemSourceKind(StrEnum):
    SUMMARIZED = "summarized"
    USER_ADDED = "user_added"


class BrainstormMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    role: Literal["user", "assistant"]
    content_text: str
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("message_id", "content_text")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class BrainstormContextWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_id: str
    brainstorm_id: str
    session_id: str
    branch_head_id: str
    turn_id: str | None
    runtime_profile_snapshot_id: str | None
    status: BrainstormContextWindowStatus = BrainstormContextWindowStatus.ACTIVE
    flush_reason: BrainstormContextFlushReason | None = None
    flushed_at: datetime | None = None
    source_message_refs: list[str] = Field(default_factory=list)
    messages: list[BrainstormMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator(
        "window_id",
        "brainstorm_id",
        "session_id",
        "branch_head_id",
    )
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("turn_id", "runtime_profile_snapshot_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("source_message_refs")
    @classmethod
    def _normalize_refs(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="source_message_refs")


class BrainstormBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    batch_id: str
    brainstorm_id: str
    session_id: str
    branch_head_id: str
    turn_id: str | None
    runtime_profile_snapshot_id: str | None
    text: str
    source_kind: BrainstormItemSourceKind = BrainstormItemSourceKind.SUMMARIZED
    status: BrainstormItemStatus = BrainstormItemStatus.ACTIVE
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator(
        "item_id",
        "batch_id",
        "brainstorm_id",
        "session_id",
        "branch_head_id",
        "text",
    )
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("turn_id", "runtime_profile_snapshot_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class BrainstormBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    brainstorm_id: str
    session_id: str
    branch_head_id: str
    turn_id: str | None
    runtime_profile_snapshot_id: str | None
    source_window_id: str | None = None
    status: BrainstormBatchStatus = BrainstormBatchStatus.DRAFT
    frozen: bool = False
    items: list[BrainstormBatchItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    submitted_at: datetime | None = None

    @field_validator("batch_id", "brainstorm_id", "session_id", "branch_head_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("turn_id", "runtime_profile_snapshot_id", "source_window_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @property
    def active_items(self) -> list[BrainstormBatchItem]:
        return [item for item in self.items if item.status == BrainstormItemStatus.ACTIVE]


class BrainstormSession(BaseModel):
    """Branch/turn-scoped brainstorm scratch persisted as Runtime Workspace material."""

    model_config = ConfigDict(extra="forbid")

    brainstorm_id: str
    identity: MemoryRuntimeIdentity
    status: BrainstormSessionStatus = BrainstormSessionStatus.ACTIVE
    created_by: str
    updated_by: str
    revision: int = Field(default=1, ge=1)
    windows: list[BrainstormContextWindow] = Field(default_factory=list)
    batches: list[BrainstormBatch] = Field(default_factory=list)
    close_reason: str | None = None
    summary_trace: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("brainstorm_id", "created_by", "updated_by")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("close_reason")
    @classmethod
    def _normalize_close_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="close_reason")


class BrainstormSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("actor")
    @classmethod
    def _require_text(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")


class BrainstormDiscussionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    prompt: str
    model_id: str
    provider_id: str | None = None

    @field_validator("actor", "prompt", "model_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("provider_id")
    @classmethod
    def _normalize_provider_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="provider_id")


class BrainstormSummarizeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("items")
    @classmethod
    def _normalize_items(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="items")


class BrainstormSummarizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    model_id: str | None = None
    provider_id: str | None = None
    max_items: int = Field(default=8, ge=1, le=12)
    dry_run_items: list[str] | None = None

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

    @field_validator("dry_run_items")
    @classmethod
    def _normalize_dry_run_items(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return _normalize_text_list(values, field_name="dry_run_items")


class BrainstormContinueWritingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")


class BrainstormItemCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    text: str

    @field_validator("actor", "text")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class BrainstormItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    text: str | None = None
    status: Literal["active", "deleted"] | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("text")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="text")


class BrainstormBatchSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")


class BrainstormBatchSubmitReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brainstorm_id: str
    batch_id: str
    identity: MemoryRuntimeIdentity
    status: Literal["pending_processing"]
    submitted_item_ids: list[str] = Field(default_factory=list)
    deleted_item_ids: list[str] = Field(default_factory=list)

    @field_validator("brainstorm_id", "batch_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("submitted_item_ids", "deleted_item_ids")
    @classmethod
    def _normalize_refs(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _normalize_text_list(values, field_name=info.field_name or "value")


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
