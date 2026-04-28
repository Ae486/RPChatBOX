"""Active-story runtime models for longform MVP."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)


class StorySessionState(StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class LongformChapterPhase(StrEnum):
    OUTLINE_DRAFTING = "outline_drafting"
    OUTLINE_REVIEW = "outline_review"
    SEGMENT_DRAFTING = "segment_drafting"
    SEGMENT_REVIEW = "segment_review"
    CHAPTER_REVIEW = "chapter_review"
    CHAPTER_COMPLETED = "chapter_completed"


class StoryArtifactKind(StrEnum):
    CHAPTER_OUTLINE = "chapter_outline"
    STORY_SEGMENT = "story_segment"
    DISCUSSION_MESSAGE = "discussion_message"
    SYSTEM_NOTE = "system_note"


class StoryArtifactStatus(StrEnum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class LongformTurnCommandKind(StrEnum):
    GENERATE_OUTLINE = "generate_outline"
    DISCUSS_OUTLINE = "discuss_outline"
    ACCEPT_OUTLINE = "accept_outline"
    WRITE_NEXT_SEGMENT = "write_next_segment"
    REWRITE_PENDING_SEGMENT = "rewrite_pending_segment"
    ACCEPT_PENDING_SEGMENT = "accept_pending_segment"
    COMPLETE_CHAPTER = "complete_chapter"


class StorySession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    story_id: str
    source_workspace_id: str
    mode: str
    session_state: StorySessionState
    current_chapter_index: int
    current_phase: LongformChapterPhase
    runtime_story_config: dict[str, Any] = Field(default_factory=dict)
    writer_contract: dict[str, Any] = Field(default_factory=dict)
    current_state_json: dict[str, Any] = Field(default_factory=dict)
    activated_at: datetime
    created_at: datetime
    updated_at: datetime


class ChapterWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_workspace_id: str
    session_id: str
    chapter_index: int
    phase: LongformChapterPhase
    chapter_goal: str | None = None
    outline_draft_json: dict[str, Any] | None = None
    accepted_outline_json: dict[str, Any] | None = None
    builder_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    review_notes: list[str] = Field(default_factory=list)
    accepted_segment_ids: list[str] = Field(default_factory=list)
    pending_segment_artifact_id: str | None = None
    current_scene_ref: str | None = None
    next_scene_index: int = 1
    last_closed_scene_ref: str | None = None
    closed_scene_refs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StoryArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    session_id: str
    chapter_workspace_id: str
    artifact_kind: StoryArtifactKind
    status: StoryArtifactStatus
    revision: int
    content_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    scene_ref: str | None = None
    created_at: datetime
    updated_at: datetime


class StoryDiscussionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    session_id: str
    chapter_workspace_id: str
    role: Literal["user", "assistant", "system"]
    content_text: str
    linked_artifact_id: str | None = None
    scene_ref: str | None = None
    created_at: datetime


class StoryActivationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    story_id: str
    source_workspace_id: str
    current_chapter_index: int
    current_phase: LongformChapterPhase
    initial_outline_required: bool = True


class StoryRuntimeConfigPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_story_config: dict[str, Any] = Field(default_factory=dict)


class LongformTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    command_kind: LongformTurnCommandKind
    model_id: str
    provider_id: str | None = None
    user_prompt: str | None = None
    target_artifact_id: str | None = None
    story_segment_metadata_patch: StorySegmentStructuredMetadata | None = None


class LongformTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    chapter_workspace_id: str
    command_kind: LongformTurnCommandKind
    current_chapter_index: int
    current_phase: LongformChapterPhase
    assistant_text: str | None = None
    artifact_id: str | None = None
    artifact_kind: StoryArtifactKind | None = None
    warnings: list[str] = Field(default_factory=list)


class ChapterWorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: StorySession
    chapter: ChapterWorkspace
    artifacts: list[StoryArtifact] = Field(default_factory=list)
    discussion_entries: list[StoryDiscussionEntry] = Field(default_factory=list)


class OrchestratorPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_kind: StoryArtifactKind
    needs_retrieval: bool = False
    archival_queries: list[str] = Field(default_factory=list)
    recall_queries: list[str] = Field(default_factory=list)
    specialist_focus: list[str] = Field(default_factory=list)
    writer_instruction: str
    notes: list[str] = Field(default_factory=list)


class ForeshadowStatusUpdateMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    foreshadow_id: str | None = None
    status: str | None = None
    state: str | None = None
    summary: str | None = None
    title: str | None = None
    description: str | None = None
    resolution: str | None = None

    def to_metadata_item(self) -> dict[str, Any] | None:
        normalized: dict[str, Any] = {}
        for key, value in self.model_dump(mode="json", exclude_none=True).items():
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    continue
                normalized[key] = stripped
                continue
            normalized[key] = value
        foreshadow_id = normalized.get("foreshadow_id")
        if not isinstance(foreshadow_id, str) or not foreshadow_id:
            return None
        if len(normalized) == 1:
            return None
        return normalized


class StorySegmentStructuredMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    foreshadow_status_updates: list[ForeshadowStatusUpdateMetadata] = Field(
        default_factory=list
    )

    @field_validator("foreshadow_status_updates", mode="before")
    @classmethod
    def _normalize_foreshadow_status_updates(
        cls,
        value: Any,
    ) -> list[ForeshadowStatusUpdateMetadata]:
        if not isinstance(value, list):
            return []
        normalized: list[ForeshadowStatusUpdateMetadata] = []
        for item in value:
            if not isinstance(item, (dict, ForeshadowStatusUpdateMetadata)):
                continue
            try:
                normalized.append(ForeshadowStatusUpdateMetadata.model_validate(item))
            except ValidationError:
                continue
        return normalized

    def to_artifact_metadata(self) -> dict[str, Any]:
        latest_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
        sequence = 0
        for item in self.foreshadow_status_updates:
            normalized_item = item.to_metadata_item()
            if normalized_item is None:
                continue
            latest_by_id[str(normalized_item["foreshadow_id"])] = (
                sequence,
                normalized_item,
            )
            sequence += 1
        if not latest_by_id:
            return {}
        return {
            "foreshadow_status_updates": [
                update
                for _, update in sorted(
                    latest_by_id.values(),
                    key=lambda item: item[0],
                )
            ]
        }


class SpecialistResultBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    foundation_digest: list[str] = Field(default_factory=list)
    blueprint_digest: list[str] = Field(default_factory=list)
    current_outline_digest: list[str] = Field(default_factory=list)
    recent_segment_digest: list[str] = Field(default_factory=list)
    current_state_digest: list[str] = Field(default_factory=list)
    writer_hints: list[str] = Field(default_factory=list)
    validation_findings: list[str] = Field(default_factory=list)
    state_patch_proposals: dict[str, Any] = Field(default_factory=dict)
    summary_updates: list[str] = Field(default_factory=list)
    recall_summary_text: str | None = None
    story_segment_metadata: StorySegmentStructuredMetadata = Field(
        default_factory=StorySegmentStructuredMetadata
    )
