"""Structured WritingWorker request/result contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.models.writing_runtime import WritingPacket


WritingOperationMode = Literal["writing", "rewrite", "discussion"]
WritingResultStatus = Literal["completed", "failed"]


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


class WritingWorkerExecutionRequest(BaseModel):
    """Canonical request contract for one WritingWorker execution."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    identity: MemoryRuntimeIdentity | None = None
    operation_mode: WritingOperationMode = "writing"
    packet_ref: str | None = None
    packet: WritingPacket
    writer_model_id: str
    writer_provider_id: str | None = None
    streaming: bool = False
    retrieval_allowed: bool = False
    max_retrieval_attempts: int = Field(default=0, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", "writer_model_id")
    @classmethod
    def _validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("packet_ref", "writer_provider_id", mode="before")
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class WritingWorkerExecutionResult(BaseModel):
    """Structured WritingWorker runtime result consumed by turn-domain finalize."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    packet_id: str
    turn_id: str | None = None
    operation_mode: WritingOperationMode = "writing"
    output_text: str = ""
    output_kind: str
    usage_metadata: dict[str, Any] = Field(default_factory=dict)
    visible_output_ref: str | None = None
    candidate_output_ref: str | None = None
    selected_output_ref: str | None = None
    writer_output_material_id: str | None = None
    token_usage_material_id: str | None = None
    trace_refs: list[str] = Field(default_factory=list)
    writer_tool_trace_refs: list[str] = Field(default_factory=list)
    retrieval_source_ref_bundle: WorkerSourceRefBundle = Field(
        default_factory=WorkerSourceRefBundle
    )
    result_status: WritingResultStatus = "completed"
    failure_reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", "packet_id", "output_kind")
    @classmethod
    def _validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "turn_id",
        "visible_output_ref",
        "candidate_output_ref",
        "selected_output_ref",
        "writer_output_material_id",
        "token_usage_material_id",
        "failure_reason",
        mode="before",
    )
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)
