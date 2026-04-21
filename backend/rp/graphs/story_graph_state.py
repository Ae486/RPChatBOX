"""State schema for the phase-1 StoryGraph shell."""
from __future__ import annotations

from typing import Any, TypedDict


class StoryGraphState(TypedDict, total=False):
    session_id: str
    chapter_workspace_id: str
    chapter_phase: str
    current_chapter_index: int
    command_kind: str
    model_id: str
    provider_id: str | None
    user_prompt: str | None
    target_artifact_id: str | None
    stream_mode: bool
    status: str
    pending_artifact_id: str | None
    accepted_segment_ids: list[str]
    plan: dict[str, Any]
    specialist_bundle: dict[str, Any]
    writing_packet: dict[str, Any]
    artifact_id: str | None
    artifact_kind: str | None
    warnings: list[str]
    assistant_text: str
    response_payload: dict[str, Any]
    error: dict[str, str] | None
