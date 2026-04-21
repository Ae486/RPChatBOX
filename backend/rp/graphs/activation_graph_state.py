"""State schema for the phase-1 ActivationGraph shell."""
from __future__ import annotations

from typing import Any, TypedDict


class ActivationGraphState(TypedDict, total=False):
    workspace_id: str
    status: str
    handoff_payload: dict[str, Any]
    session_id: str
    story_id: str
    source_workspace_id: str
    current_chapter_index: int
    current_phase: str
    chapter_goal: str | None
    builder_snapshot_json: dict[str, Any]
    activation_result: dict[str, Any]
    error: dict[str, str]
