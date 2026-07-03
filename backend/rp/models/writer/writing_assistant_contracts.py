"""Contracts for the writing-assistant agent generation path (S6-4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


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
