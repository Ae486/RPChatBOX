"""State schema for the phase-1 StoryGraph shell."""

from __future__ import annotations

from typing import Any, TypedDict


class StoryGraphState(TypedDict, total=False):
    session_id: str
    graph_thread_id: str
    graph_thread_binding: dict[str, Any]
    runtime_identity: dict[str, Any]
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
    chapter_workspace_id: str
    chapter_phase: str
    current_chapter_index: int
    command_kind: str
    model_id: str
    provider_id: str | None
    user_prompt: str | None
    target_artifact_id: str | None
    story_segment_metadata_patch: dict[str, Any] | None
    stream_mode: bool
    status: str
    pending_artifact_id: str | None
    accepted_segment_ids: list[str]
    plan: dict[str, Any]
    specialist_bundle: dict[str, Any]
    writing_packet: dict[str, Any]
    writing_result: dict[str, Any]
    post_write_trigger: dict[str, Any]
    artifact_id: str | None
    artifact_kind: str | None
    warnings: list[str]
    assistant_text: str
    stream_usage_metadata: dict[str, Any]
    response_payload: dict[str, Any]
    error: dict[str, str] | None
