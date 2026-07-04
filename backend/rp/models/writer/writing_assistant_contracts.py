"""Contracts for the writing-assistant agent generation path (S6-4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from rp.models.memory.contract_registry import MemoryRuntimeIdentity


class WritingAssistantGenerateRequest(BaseModel):
    """One assistant generation call (rewrite/continue), mirroring brainstorm.

    Carries the runtime identity plus the per-call control fields. Optional
    fields select the resume target (assistant_session_id/session_title) and
    the framed selection; the service owns mode/selection semantics
    (REV-024 use-and-discard selection, REV-027 one-way isolation).
    """

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    chapter_workspace_id: str
    mode: str
    user_requirements: str = ""
    selection_text: str | None = None
    assistant_session_id: str | None = None
    session_title: str | None = None
    model_id: str
    provider_id: str | None = None

    @field_validator("chapter_workspace_id", "mode", "model_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("provider_id")
    @classmethod
    def _normalize_provider_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="provider_id")


class WritingAssistantGenerationResult(BaseModel):
    """One assistant generation outcome: display text plus candidate reference.

    The generated text is NOT persisted as story truth (REV-028): rewrite
    output is recorded as a non-truth candidate referenced by candidate_ref;
    adoption stays with the S6-3 accept gate.
    """

    model_config = ConfigDict(extra="forbid")

    assistant_session_id: str
    mode: Literal["rewrite", "continue"]
    generated_text: str
    candidate_ref: str | None = None
    request_id: str
    packet_id: str


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
