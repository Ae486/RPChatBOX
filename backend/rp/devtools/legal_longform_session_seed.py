"""Direct database materialization for legal longform runtime test sessions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete
from sqlmodel import Session, select

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
    CoreStateProjectionSlotRecord,
    CoreStateProjectionSlotRevisionRecord,
    CoreStateSnapshotManifestRecord,
)
from models.rp_memory_store import (
    MemoryApplyReceiptRecord,
    MemoryApplyTargetLinkRecord,
    MemoryChangeEventRecord,
    MemoryProposalRecord,
    RuntimeWorkspaceMaterialRecord,
)
from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    IndexJobRecord,
    KnowledgeChunkRecord,
    ParsedDocumentRecord,
    SourceAssetRecord,
)
from models.rp_setup_store import SetupWorkspaceRecord
from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    ChapterWorkspaceRecord,
    RuntimeConfigControlReceiptRecord,
    RuntimeProfileSnapshotRecord,
    RuntimeWorkflowJobRecord,
    StoryArtifactRecord,
    StoryBlockConsumerStateRecord,
    StoryDiscussionEntryRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.dsl import Domain
from rp.models.longform_chapter_contracts import LongformStructuredOutline
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_materialization import (
    FOUNDATION_ENTRY_SOURCE_TYPE,
    SETUP_COMMIT_IMPORT_EVENT,
    build_archival_seed_section,
    build_archival_source_metadata,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.recall_detail_ingestion_service import RecallDetailIngestionService
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "legal_longform_session_template.v1.json"
)
_SEED_TOOL_NAME = "legal_longform_session_seed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _require_text(value: Any, *, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _seed_marker(*, label: str) -> str:
    return f"{_SEED_TOOL_NAME}:{label}"


def _seed_marker_payload(*, label: str) -> dict[str, str]:
    return {
        "seed_tool": _SEED_TOOL_NAME,
        "seed_label": label,
        "seed_marker": _seed_marker(label=label),
    }


def _with_seed_marker(metadata: dict[str, Any], *, label: str) -> dict[str, Any]:
    marked = dict(metadata)
    marked.update(_seed_marker_payload(label=label))
    return marked


def _with_seed_marker_on_sections(
    metadata: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    marked = _with_seed_marker(metadata, label=label)
    seed_sections = marked.get("seed_sections")
    if not isinstance(seed_sections, list):
        return marked

    marked_sections: list[Any] = []
    for section in seed_sections:
        if not isinstance(section, dict):
            marked_sections.append(section)
            continue
        next_section = dict(section)
        section_metadata = next_section.get("metadata")
        if isinstance(section_metadata, dict):
            next_section["metadata"] = _with_seed_marker(
                dict(section_metadata),
                label=label,
            )
        marked_sections.append(next_section)
    marked["seed_sections"] = marked_sections
    return marked


def _normalize_text_list(values: list[str]) -> list[str]:
    return [item.strip() for item in values if item and item.strip()]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _render_outline_text(outline: LongformStructuredOutline) -> str:
    lines: list[str] = []
    if outline.chapter_title:
        lines.append(f"# {outline.chapter_title}")
    lines.append(f"Chapter goal: {outline.chapter_goal}")
    for beat in outline.beats:
        lines.append(f"{beat.order}. {beat.title}: {beat.goal}")
        if beat.must_include:
            lines.append("   Must include: " + "; ".join(beat.must_include))
        if beat.avoid:
            lines.append("   Avoid: " + "; ".join(beat.avoid))
        if beat.continuity_notes:
            lines.append("   Continuity: " + "; ".join(beat.continuity_notes))
    return "\n".join(lines)


def _artifact_runtime_metadata(*, identity: MemoryRuntimeIdentity) -> dict[str, str]:
    return {
        "runtime_story_id": identity.story_id,
        "runtime_session_id": identity.session_id,
        "runtime_branch_head_id": identity.branch_head_id,
        "runtime_turn_id": identity.turn_id,
        "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
    }


class LegalLongformSessionSeedError(ValueError):
    """Stable dev-seed error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class SeedSessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_story_config: dict[str, Any] = Field(default_factory=dict)
    writer_contract: dict[str, Any] = Field(default_factory=dict)
    current_state_overrides: dict[str, Any] = Field(default_factory=dict)


class SeedChapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_index: int = Field(default=1, ge=1)
    chapter_title: str | None = None
    chapter_goal: str
    phase: LongformChapterPhase = LongformChapterPhase.SEGMENT_DRAFTING
    foundation_digest: list[str] = Field(default_factory=list)
    blueprint_digest: list[str] = Field(default_factory=list)
    current_state_digest: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_fields(self) -> "SeedChapterConfig":
        self.chapter_title = _optional_text(self.chapter_title)
        self.chapter_goal = _require_text(self.chapter_goal, field_name="chapter_goal")
        self.foundation_digest = _normalize_text_list(self.foundation_digest)
        self.blueprint_digest = _normalize_text_list(self.blueprint_digest)
        self.current_state_digest = _normalize_text_list(self.current_state_digest)
        return self


class SeedOutlineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_text: str | None = None
    structured_outline: LongformStructuredOutline

    @model_validator(mode="after")
    def _normalize_fields(self) -> "SeedOutlineConfig":
        if _optional_text(self.content_text) is None:
            self.content_text = _render_outline_text(self.structured_outline)
        else:
            self.content_text = _require_text(
                self.content_text,
                field_name="outline.content_text",
            )
        return self


class SeedSegmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_text: str
    target_beat_id: str
    scene_ref: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_fields(self) -> "SeedSegmentConfig":
        self.content_text = _require_text(
            self.content_text,
            field_name="segment.content_text",
        )
        self.target_beat_id = _require_text(
            self.target_beat_id,
            field_name="segment.target_beat_id",
        )
        self.scene_ref = _optional_text(self.scene_ref)
        return self


class SeedArchivalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = "legal_longform_archival_seed"
    title: str
    text: str
    domain: str = Domain.WORLD_RULE.value
    domain_path: str = "foundation.world.legal_longform_session_seed"
    tags: list[str] = Field(default_factory=lambda: ["archival", "world_rule"])
    source_type: str = FOUNDATION_ENTRY_SOURCE_TYPE
    step_id: str = "foundation"

    @model_validator(mode="after")
    def _normalize_fields(self) -> "SeedArchivalConfig":
        self.asset_id = _require_text(self.asset_id, field_name="archival.asset_id")
        self.title = _require_text(self.title, field_name="archival.title")
        self.text = _require_text(self.text, field_name="archival.text")
        self.domain = _require_text(self.domain, field_name="archival.domain")
        self.domain_path = _require_text(
            self.domain_path,
            field_name="archival.domain_path",
        )
        self.tags = _normalize_text_list(self.tags)
        self.source_type = _require_text(
            self.source_type,
            field_name="archival.source_type",
        )
        self.step_id = _require_text(self.step_id, field_name="archival.step_id")
        return self


class LegalLongformSessionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_version: Literal["legal_longform_session.v1"]
    mode: Literal["longform"] = "longform"
    session: SeedSessionConfig = Field(default_factory=SeedSessionConfig)
    chapter: SeedChapterConfig
    outline: SeedOutlineConfig
    segments: list[SeedSegmentConfig]
    archival_seed: SeedArchivalConfig

    @model_validator(mode="after")
    def _validate_consistency(self) -> "LegalLongformSessionTemplate":
        outline = self.outline.structured_outline
        if outline.chapter_index != self.chapter.chapter_index:
            raise ValueError("outline.chapter_index must match chapter.chapter_index")
        if self.chapter.chapter_title is None and outline.chapter_title:
            self.chapter.chapter_title = outline.chapter_title
        if outline.chapter_title is None and self.chapter.chapter_title:
            outline.chapter_title = self.chapter.chapter_title
        if self.chapter.chapter_goal != outline.chapter_goal:
            raise ValueError(
                "chapter.chapter_goal must match outline.structured_outline.chapter_goal"
            )
        if not self.segments:
            raise ValueError("segments must contain at least one accepted segment")
        seen_beats: set[str] = set()
        for segment in self.segments:
            if outline.beat_by_id(segment.target_beat_id) is None:
                raise ValueError(
                    f"segment target beat missing from outline: {segment.target_beat_id}"
                )
            if segment.target_beat_id in seen_beats:
                raise ValueError(
                    f"duplicate segment target beat: {segment.target_beat_id}"
                )
            seen_beats.add(segment.target_beat_id)
        return self


@dataclass(frozen=True)
class SeededSegmentRecord:
    turn_id: str
    artifact_id: str
    target_beat_id: str


@dataclass(frozen=True)
class SeededLegalLongformSession:
    story_id: str
    session_id: str
    label: str
    source_workspace_id: str
    active_branch_head_id: str
    active_runtime_profile_snapshot_id: str
    chapter_workspace_id: str
    outline_turn_id: str
    outline_artifact_id: str
    latest_turn_id: str
    accepted_segment_ids: list[str]
    segment_turn_records: list[SeededSegmentRecord]
    recall_asset_ids: list[str]
    archival_asset_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "session_id": self.session_id,
            "label": self.label,
            "source_workspace_id": self.source_workspace_id,
            "active_branch_head_id": self.active_branch_head_id,
            "active_runtime_profile_snapshot_id": (
                self.active_runtime_profile_snapshot_id
            ),
            "chapter_workspace_id": self.chapter_workspace_id,
            "outline_turn_id": self.outline_turn_id,
            "outline_artifact_id": self.outline_artifact_id,
            "latest_turn_id": self.latest_turn_id,
            "accepted_segment_ids": list(self.accepted_segment_ids),
            "segment_turn_records": [
                {
                    "turn_id": item.turn_id,
                    "artifact_id": item.artifact_id,
                    "target_beat_id": item.target_beat_id,
                }
                for item in self.segment_turn_records
            ],
            "recall_asset_ids": list(self.recall_asset_ids),
            "archival_asset_id": self.archival_asset_id,
        }


class LegalLongformSessionSeeder:
    """Materialize one branchable longform runtime session without setup activation."""

    def __init__(self, session: Session):
        self._session = session
        self._story_session_service = StorySessionService(session)
        self._identity_service = StoryRuntimeIdentityService(session)
        self._snapshot_service = RuntimeProfileSnapshotService(session)
        self._core_repository = CoreStateStoreRepository(session)
        self._core_dual_write_service = CoreStateDualWriteService(
            repository=self._core_repository
        )
        self._projection_state_service = ProjectionStateService(
            story_session_service=self._story_session_service,
            adapter=ChapterWorkspaceProjectionAdapter(self._story_session_service),
            core_state_dual_write_service=self._core_dual_write_service,
        )
        self._longform_service = LongformChapterRuntimeService(
            story_session_service=self._story_session_service,
            session=session,
        )
        self._recall_detail_ingestion_service = RecallDetailIngestionService(session)
        self._retrieval_collection_service = RetrievalCollectionService(session)
        self._retrieval_document_service = RetrievalDocumentService(session)
        self._retrieval_ingestion_service = RetrievalIngestionService(session)

    @staticmethod
    def load_template_from_path(
        template_path: str | Path,
    ) -> LegalLongformSessionTemplate:
        raw = json.loads(Path(template_path).read_text(encoding="utf-8"))
        return LegalLongformSessionTemplate.model_validate(raw)

    def seed_from_template_path(
        self,
        *,
        template_path: str | Path,
        story_id: str,
        label: str,
        replace: bool = False,
    ) -> SeededLegalLongformSession:
        template = self.load_template_from_path(template_path)
        return self.seed(
            template=template,
            story_id=story_id,
            label=label,
            replace=replace,
        )

    def seed(
        self,
        *,
        template: LegalLongformSessionTemplate,
        story_id: str,
        label: str,
        replace: bool = False,
    ) -> SeededLegalLongformSession:
        normalized_story_id = _require_text(story_id, field_name="story_id")
        normalized_label = _require_text(label, field_name="label")
        self._guard_or_replace_existing_seed(
            story_id=normalized_story_id,
            label=normalized_label,
            replace=replace,
        )
        source_workspace_id = self._ensure_source_workspace(
            story_id=normalized_story_id,
            mode=StoryMode.LONGFORM,
        )
        initial_session_state = self._build_current_state_payload(
            template=template,
            accepted_segments=0,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
        )
        session_runtime_story_config = _deep_merge(
            dict(template.session.runtime_story_config),
            {
                "dev_seed": {
                    "tool": _SEED_TOOL_NAME,
                    "label": normalized_label,
                    "marker": _seed_marker(label=normalized_label),
                    "template_version": template.template_version,
                    "created_at": _utcnow().isoformat(),
                }
            },
        )
        story_session = self._story_session_service.create_session(
            story_id=normalized_story_id,
            source_workspace_id=source_workspace_id,
            mode=template.mode,
            runtime_story_config=session_runtime_story_config,
            writer_contract=dict(template.session.writer_contract),
            current_state_json=initial_session_state,
            initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
        )
        chapter = self._story_session_service.create_chapter_workspace(
            session_id=story_session.session_id,
            chapter_index=template.chapter.chapter_index,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
            chapter_goal=template.chapter.chapter_goal,
            builder_snapshot_json={
                "chapter_index": template.chapter.chapter_index,
                "phase": LongformChapterPhase.OUTLINE_DRAFTING.value,
                "foundation_digest": list(template.chapter.foundation_digest),
                "blueprint_digest": list(template.chapter.blueprint_digest),
                "current_outline_digest": [],
                "recent_segment_digest": [],
                "current_state_digest": list(template.chapter.current_state_digest),
            },
        )
        self._core_dual_write_service.seed_activation_state(
            session=story_session,
            chapter=chapter,
        )
        self._identity_service.ensure_default_branch(
            session_id=story_session.session_id,
            story_id=story_session.story_id,
        )
        active_snapshot = self._snapshot_service.ensure_active_snapshot(
            session_id=story_session.session_id,
            created_from=f"{_SEED_TOOL_NAME}.bootstrap",
        )

        outline_identity = self._identity_service.resolve_runtime_entry_identity(
            session_id=story_session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE.value,
            actor=f"{_SEED_TOOL_NAME}:{normalized_label}:accept_outline",
            requested_runtime_profile_snapshot_id=(
                active_snapshot.runtime_profile_snapshot_id
            ),
        )
        outline_artifact = self._story_session_service.create_artifact(
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
            status=StoryArtifactStatus.DRAFT,
            content_text=template.outline.content_text or "",
            metadata={
                **_artifact_runtime_metadata(identity=outline_identity),
                "structured_outline": template.outline.structured_outline.model_dump(
                    mode="json"
                ),
            },
        )
        normalized_text, normalized_metadata, _warnings = (
            self._longform_service.normalize_outline_artifact(
                chapter=chapter,
                artifact=outline_artifact,
            )
        )
        accepted_outline_artifact = self._story_session_service.update_artifact(
            artifact_id=outline_artifact.artifact_id,
            status=StoryArtifactStatus.ACCEPTED,
            content_text=normalized_text,
            metadata=normalized_metadata,
        )
        accepted_outline_payload = self._longform_service.build_outline_payload(
            artifact=accepted_outline_artifact,
            metadata=accepted_outline_artifact.metadata,
        )
        chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=template.chapter.phase,
            outline_draft_json=accepted_outline_payload,
            accepted_outline_json=accepted_outline_payload,
        )
        story_session = self._story_session_service.update_session(
            session_id=story_session.session_id,
            current_phase=template.chapter.phase,
            current_state_json=self._build_current_state_payload(
                template=template,
                accepted_segments=0,
                phase=template.chapter.phase,
            ),
        )
        self._projection_state_service.set_current_outline(
            chapter_workspace_id=chapter.chapter_workspace_id,
            outline_text=accepted_outline_artifact.content_text,
        )
        chapter = self._require_current_chapter(story_session.session_id)
        self._longform_service.initialize_outline_progress(
            identity=outline_identity,
            chapter=chapter,
            accepted_outline_json=accepted_outline_payload,
        )
        self._identity_service.update_turn_status(
            turn_id=outline_identity.turn_id,
            status=self._settled_status(),
            visible_output_ref=accepted_outline_artifact.artifact_id,
            selected_output_ref=accepted_outline_artifact.artifact_id,
            settlement_reason="legal_longform_seed_outline_accepted",
        )

        segment_turn_records: list[SeededSegmentRecord] = []
        accepted_segment_ids: list[str] = []
        recall_asset_ids: list[str] = []
        latest_identity: MemoryRuntimeIdentity = outline_identity
        for index, segment in enumerate(template.segments, start=1):
            chapter_before_accept = self._require_current_chapter(
                story_session.session_id
            )
            latest_identity = self._identity_service.resolve_runtime_entry_identity(
                session_id=story_session.session_id,
                command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
                actor=f"{_SEED_TOOL_NAME}:{normalized_label}:segment:{index}",
                requested_runtime_profile_snapshot_id=(
                    active_snapshot.runtime_profile_snapshot_id
                ),
            )
            create_segment_kwargs: dict[str, Any] = {
                "session_id": story_session.session_id,
                "chapter_workspace_id": chapter.chapter_workspace_id,
                "artifact_kind": StoryArtifactKind.STORY_SEGMENT,
                "status": StoryArtifactStatus.ACCEPTED,
                "content_text": segment.content_text,
                "metadata": {
                    **_artifact_runtime_metadata(identity=latest_identity),
                    "target_beat_id": segment.target_beat_id,
                    **dict(segment.metadata_json),
                },
            }
            if segment.scene_ref is not None:
                create_segment_kwargs["scene_ref"] = segment.scene_ref
            accepted_segment = self._story_session_service.create_artifact(
                **create_segment_kwargs,
            )
            self._identity_service.update_turn_status(
                turn_id=latest_identity.turn_id,
                status=self._settled_status(),
                visible_output_ref=accepted_segment.artifact_id,
                selected_output_ref=accepted_segment.artifact_id,
                settlement_reason="legal_longform_seed_segment_accepted",
            )
            accepted_segment_ids = [
                item.artifact_id
                for item in self._story_session_service.active_branch_accepted_story_segments(
                    session_id=story_session.session_id,
                    chapter_index=chapter.chapter_index,
                )
            ]
            chapter_after_accept = self._story_session_service.update_chapter_workspace(
                chapter_workspace_id=chapter.chapter_workspace_id,
                phase=template.chapter.phase,
                pending_segment_artifact_id=None,
                accepted_segment_ids=accepted_segment_ids,
            )
            self._longform_service.advance_outline_progress_for_adoption(
                identity=latest_identity,
                chapter_before_accept=chapter_before_accept,
                chapter_after_accept=chapter_after_accept,
                accepted_artifact=accepted_segment,
            )
            self._projection_state_service.append_recent_segment(
                chapter_workspace_id=chapter.chapter_workspace_id,
                excerpt=accepted_segment.content_text,
            )
            segment_recall_asset_ids = (
                self._recall_detail_ingestion_service.ingest_accepted_story_segments(
                    session_id=story_session.session_id,
                    story_id=story_session.story_id,
                    chapter_index=chapter.chapter_index,
                    source_workspace_id=source_workspace_id,
                    accepted_segments=[accepted_segment],
                    runtime_identity=latest_identity,
                )
            )
            self._mark_retrieval_assets_as_seed(
                asset_ids=segment_recall_asset_ids,
                label=normalized_label,
            )
            recall_asset_ids.extend(segment_recall_asset_ids)
            segment_turn_records.append(
                SeededSegmentRecord(
                    turn_id=latest_identity.turn_id,
                    artifact_id=accepted_segment.artifact_id,
                    target_beat_id=segment.target_beat_id,
                )
            )

        final_session_state = self._build_current_state_payload(
            template=template,
            accepted_segments=len(accepted_segment_ids),
            phase=template.chapter.phase,
        )
        story_session = self._story_session_service.update_session(
            session_id=story_session.session_id,
            current_phase=template.chapter.phase,
            current_state_json=final_session_state,
        )
        chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=template.chapter.phase,
            accepted_segment_ids=accepted_segment_ids,
            pending_segment_artifact_id=None,
        )
        self._core_dual_write_service.ensure_authoritative_seed(
            session=story_session,
            snapshot=dict(story_session.current_state_json or {}),
            source_kind="legal_longform_seed",
        )
        self._core_dual_write_service.sync_projection_snapshot(
            session=story_session,
            chapter=chapter,
            snapshot=dict(chapter.builder_snapshot_json or {}),
            refresh_source_kind="legal_longform_seed",
        )
        self._mark_core_state_rows_as_seed(
            session_id=story_session.session_id,
            label=normalized_label,
        )
        self._record_final_core_state_manifest(identity=latest_identity)
        self._mark_runtime_workspace_materials_as_seed(
            session_id=story_session.session_id,
            label=normalized_label,
        )
        archival_asset_id = self._seed_archival_asset(
            template=template,
            story_id=story_session.story_id,
            source_workspace_id=source_workspace_id,
            label=normalized_label,
        )
        self._session.commit()

        refreshed_session = self._story_session_service.get_session(
            story_session.session_id
        )
        refreshed_chapter = self._story_session_service.get_chapter_workspace(
            chapter.chapter_workspace_id
        )
        if refreshed_session is None or refreshed_chapter is None:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_refresh_failed",
                story_session.session_id,
            )
        active_branch_head_id = _optional_text(refreshed_session.active_branch_head_id)
        active_snapshot_id = _optional_text(
            refreshed_session.active_runtime_profile_snapshot_id
        )
        if active_branch_head_id is None or active_snapshot_id is None:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_missing_active_anchor",
                refreshed_session.session_id,
            )
        latest_turn_id = (
            segment_turn_records[-1].turn_id
            if segment_turn_records
            else outline_identity.turn_id
        )
        return SeededLegalLongformSession(
            story_id=refreshed_session.story_id,
            session_id=refreshed_session.session_id,
            label=normalized_label,
            source_workspace_id=refreshed_session.source_workspace_id,
            active_branch_head_id=active_branch_head_id,
            active_runtime_profile_snapshot_id=active_snapshot_id,
            chapter_workspace_id=refreshed_chapter.chapter_workspace_id,
            outline_turn_id=outline_identity.turn_id,
            outline_artifact_id=accepted_outline_artifact.artifact_id,
            latest_turn_id=latest_turn_id,
            accepted_segment_ids=list(accepted_segment_ids),
            segment_turn_records=list(segment_turn_records),
            recall_asset_ids=list(recall_asset_ids),
            archival_asset_id=archival_asset_id,
        )

    def _build_current_state_payload(
        self,
        *,
        template: LegalLongformSessionTemplate,
        accepted_segments: int,
        phase: LongformChapterPhase,
    ) -> dict[str, Any]:
        base_payload = {
            "chapter_digest": {
                "current_chapter": template.chapter.chapter_index,
                "title": template.chapter.chapter_title,
            },
            "narrative_progress": {
                "current_phase": phase.value,
                "accepted_segments": accepted_segments,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        }
        payload = _deep_merge(
            base_payload,
            dict(template.session.current_state_overrides),
        )
        payload.setdefault("chapter_digest", {})
        payload["chapter_digest"]["current_chapter"] = template.chapter.chapter_index
        payload["chapter_digest"]["title"] = template.chapter.chapter_title
        payload.setdefault("narrative_progress", {})
        payload["narrative_progress"]["current_phase"] = phase.value
        payload["narrative_progress"]["accepted_segments"] = accepted_segments
        payload.setdefault("timeline_spine", [])
        payload.setdefault("active_threads", [])
        payload.setdefault("foreshadow_registry", [])
        payload.setdefault("character_state_digest", {})
        return payload

    def _record_final_core_state_manifest(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> None:
        rows = self._core_repository.list_authoritative_objects_for_session(
            session_id=identity.session_id
        )
        changed_revisions: list[CoreStateAuthoritativeRevisionRecord] = []
        for row in rows:
            revision = self._core_repository.get_authoritative_revision(
                session_id=identity.session_id,
                layer=row.layer,
                scope=row.scope,
                object_id=row.object_id,
                revision=int(row.current_revision or 1),
            )
            if revision is not None:
                changed_revisions.append(revision)
        if not changed_revisions:
            return
        CoreStateAsOfResolver(
            session=self._session,
            repository=self._core_repository,
        ).record_core_mutation(
            identity=identity,
            changed_revisions=changed_revisions,
            source_event_ids=[f"{_SEED_TOOL_NAME}:{identity.turn_id}:core_manifest"],
        )

    def _seed_archival_asset(
        self,
        *,
        template: LegalLongformSessionTemplate,
        story_id: str,
        source_workspace_id: str,
        label: str,
    ) -> str:
        archival = template.archival_seed
        collection = self._retrieval_collection_service.ensure_story_collection(
            story_id=story_id,
            scope="story",
            collection_kind="archival",
        )
        asset_id = f"{story_id}:{_seed_marker(label=label)}:{archival.asset_id}"
        metadata = build_archival_source_metadata(
            source_type=archival.source_type,
            import_event=SETUP_COMMIT_IMPORT_EVENT,
            workspace_id=source_workspace_id,
            commit_id=_seed_marker(label=label),
            step_id=archival.step_id,
            source_ref=f"seed:{story_id}:{label}:{archival.asset_id}",
            domain=archival.domain,
            domain_path=archival.domain_path,
            extra={
                "title": archival.title,
                **_seed_marker_payload(label=label),
            },
        )
        metadata["seed_sections"] = [
            build_archival_seed_section(
                section_id=f"{archival.asset_id}:section:1",
                title=archival.title,
                path=archival.domain_path,
                text=archival.text,
                metadata=metadata,
                tags=list(archival.tags),
            )
        ]
        asset = SourceAsset(
            asset_id=asset_id,
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            workspace_id=source_workspace_id,
            step_id=archival.step_id,
            commit_id=_seed_marker(label=label),
            asset_kind=archival.source_type,
            source_ref=f"memory://{asset_id}",
            title=archival.title,
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata=metadata,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self._retrieval_document_service.upsert_source_asset(asset)
        self._session.flush()
        job = self._retrieval_ingestion_service.ingest_asset(
            story_id=story_id,
            asset_id=asset_id,
            collection_id=collection.collection_id,
        )
        if job.job_state != "completed":
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_archival_ingestion_failed",
                job.error_message or job.job_state,
            )
        self._mark_retrieval_assets_as_seed(asset_ids=[asset_id], label=label)
        return asset_id

    def _mark_retrieval_assets_as_seed(
        self,
        *,
        asset_ids: list[str],
        label: str,
    ) -> None:
        if not asset_ids:
            return
        records = list(
            self._session.exec(
                select(SourceAssetRecord).where(
                    SourceAssetRecord.asset_id.in_(asset_ids)
                )
            ).all()
        )
        for record in records:
            record.metadata_json = _with_seed_marker_on_sections(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)

        chunks = list(
            self._session.exec(
                select(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.asset_id.in_(asset_ids)
                )
            ).all()
        )
        for chunk in chunks:
            chunk.metadata_json = _with_seed_marker(
                dict(chunk.metadata_json or {}),
                label=label,
            )
            self._session.add(chunk)

    def _mark_core_state_rows_as_seed(self, *, session_id: str, label: str) -> None:
        for record in self._session.exec(
            select(CoreStateAuthoritativeObjectRecord).where(
                CoreStateAuthoritativeObjectRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)
        for record in self._session.exec(
            select(CoreStateAuthoritativeRevisionRecord).where(
                CoreStateAuthoritativeRevisionRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)
        for record in self._session.exec(
            select(CoreStateProjectionSlotRecord).where(
                CoreStateProjectionSlotRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)
        for record in self._session.exec(
            select(CoreStateProjectionSlotRevisionRecord).where(
                CoreStateProjectionSlotRevisionRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)
        for record in self._session.exec(
            select(CoreStateSnapshotManifestRecord).where(
                CoreStateSnapshotManifestRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)

    def _mark_runtime_workspace_materials_as_seed(
        self,
        *,
        session_id: str,
        label: str,
    ) -> None:
        for record in self._session.exec(
            select(RuntimeWorkspaceMaterialRecord).where(
                RuntimeWorkspaceMaterialRecord.session_id == session_id
            )
        ).all():
            record.metadata_json = _with_seed_marker(
                dict(record.metadata_json or {}),
                label=label,
            )
            self._session.add(record)

    def _guard_or_replace_existing_seed(
        self,
        *,
        story_id: str,
        label: str,
        replace: bool,
    ) -> None:
        existing_sessions = list(
            self._session.exec(
                select(StorySessionRecord).where(
                    StorySessionRecord.story_id == story_id
                )
            ).all()
        )
        if not existing_sessions:
            return
        matching_seed_sessions = [
            record
            for record in existing_sessions
            if self._seed_marker_matches(record=record, label=label)
        ]
        if not replace:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_story_exists",
                story_id,
            )
        non_matching_sessions = [
            record
            for record in existing_sessions
            if record not in matching_seed_sessions
        ]
        if non_matching_sessions:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_replace_conflict",
                story_id,
            )
        if not matching_seed_sessions:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_replace_missing_match",
                f"{story_id}:{label}",
            )
        self._delete_story_scope(
            story_id=story_id,
            label=label,
            session_ids=[record.session_id for record in matching_seed_sessions],
        )

    @staticmethod
    def _seed_marker_matches(*, record: StorySessionRecord, label: str) -> bool:
        runtime_story_config = dict(record.runtime_story_config_json or {})
        dev_seed = runtime_story_config.get("dev_seed")
        if not isinstance(dev_seed, dict):
            return False
        marker = _optional_text(dev_seed.get("marker"))
        if marker is not None:
            return marker == _seed_marker(label=label)
        return (
            _optional_text(dev_seed.get("tool")) == _SEED_TOOL_NAME
            and _optional_text(dev_seed.get("label")) == label
        )

    @staticmethod
    def _source_asset_belongs_to_seed(
        *,
        record: SourceAssetRecord,
        story_id: str,
        label: str,
        session_ids: set[str],
        artifact_ids: set[str],
    ) -> bool:
        metadata = dict(record.metadata_json or {})
        marker = _optional_text(metadata.get("seed_marker"))
        if marker is not None:
            return marker == _seed_marker(label=label)

        if (
            _optional_text(metadata.get("seed_tool")) == _SEED_TOOL_NAME
            and _optional_text(metadata.get("seed_label")) == label
        ):
            return True

        if _optional_text(metadata.get("session_id")) in session_ids:
            return True

        runtime_identity = metadata.get("runtime_identity")
        if isinstance(runtime_identity, dict):
            if _optional_text(runtime_identity.get("session_id")) in session_ids:
                return True

        if any(
            record.asset_id == f"recall_detail_{artifact_id}"
            for artifact_id in artifact_ids
        ):
            return True

        source_ref = _optional_text(record.source_ref)
        if source_ref is not None and any(
            source_ref.startswith(f"story_session:{session_id}:")
            for session_id in session_ids
        ):
            return True

        metadata_source_ref = _optional_text(metadata.get("source_ref"))
        return (
            record.commit_id == _seed_marker(label=label)
            and _optional_text(metadata.get("seed_label")) == label
            and metadata_source_ref is not None
            and metadata_source_ref.startswith(f"seed:{story_id}:{label}:")
        )

    def _seed_index_job_ids(
        self,
        *,
        story_id: str,
        source_asset_ids: set[str],
    ) -> list[str]:
        if not source_asset_ids:
            return []
        job_ids: list[str] = []
        for record in self._session.exec(
            select(IndexJobRecord).where(IndexJobRecord.story_id == story_id)
        ).all():
            if _optional_text(record.asset_id) in source_asset_ids:
                job_ids.append(record.job_id)
                continue
            target_refs = list(record.target_refs_json or [])
            if any(
                target_ref in source_asset_ids
                or (
                    isinstance(target_ref, str)
                    and target_ref.startswith("asset:")
                    and target_ref.split("asset:", 1)[1] in source_asset_ids
                )
                for target_ref in target_refs
            ):
                job_ids.append(record.job_id)
        return job_ids

    def _delete_story_scope(
        self,
        *,
        story_id: str,
        label: str,
        session_ids: list[str],
    ) -> None:
        session_id_set = set(session_ids)
        workspace = self._session.exec(
            select(SetupWorkspaceRecord).where(
                SetupWorkspaceRecord.story_id == story_id
            )
        ).first()
        if (
            workspace is not None
            and _optional_text(workspace.activated_story_session_id) in session_id_set
        ):
            workspace.activated_story_session_id = None
            workspace.updated_at = _utcnow()
            self._session.add(workspace)

        chapter_ids = [
            chapter_workspace_id
            for chapter_workspace_id in self._session.exec(
                select(ChapterWorkspaceRecord.chapter_workspace_id).where(
                    ChapterWorkspaceRecord.session_id.in_(session_ids)
                )
            ).all()
        ]
        artifact_ids = [
            artifact_id
            for artifact_id in self._session.exec(
                select(StoryArtifactRecord.artifact_id).where(
                    StoryArtifactRecord.session_id.in_(session_ids)
                )
            ).all()
        ]
        artifact_id_set = set(artifact_ids)
        source_asset_ids = [
            record.asset_id
            for record in self._session.exec(
                select(SourceAssetRecord).where(SourceAssetRecord.story_id == story_id)
            ).all()
            if self._source_asset_belongs_to_seed(
                record=record,
                story_id=story_id,
                label=label,
                session_ids=session_id_set,
                artifact_ids=artifact_id_set,
            )
        ]
        parsed_document_ids = (
            []
            if not source_asset_ids
            else [
                parsed_document_id
                for parsed_document_id in self._session.exec(
                    select(ParsedDocumentRecord.parsed_document_id).where(
                        ParsedDocumentRecord.asset_id.in_(source_asset_ids)
                    )
                ).all()
            ]
        )
        chunk_ids = (
            []
            if not source_asset_ids
            else [
                chunk_id
                for chunk_id in self._session.exec(
                    select(KnowledgeChunkRecord.chunk_id).where(
                        KnowledgeChunkRecord.asset_id.in_(source_asset_ids)
                    )
                ).all()
            ]
        )
        self._delete_where_in(
            EmbeddingRecordRecord,
            EmbeddingRecordRecord.chunk_id,
            chunk_ids,
        )
        self._delete_where_in(
            KnowledgeChunkRecord, KnowledgeChunkRecord.chunk_id, chunk_ids
        )
        self._delete_where_in(
            ParsedDocumentRecord,
            ParsedDocumentRecord.parsed_document_id,
            parsed_document_ids,
        )
        self._delete_where_in(
            SourceAssetRecord,
            SourceAssetRecord.asset_id,
            source_asset_ids,
        )
        index_job_ids = self._seed_index_job_ids(
            story_id=story_id,
            source_asset_ids=set(source_asset_ids),
        )
        self._delete_where_in(IndexJobRecord, IndexJobRecord.job_id, index_job_ids)

        proposal_ids = [
            proposal_id
            for proposal_id in self._session.exec(
                select(MemoryProposalRecord.proposal_id).where(
                    MemoryProposalRecord.session_id.in_(session_ids)
                )
            ).all()
        ]
        apply_ids = [
            apply_id
            for apply_id in self._session.exec(
                select(MemoryApplyReceiptRecord.apply_id).where(
                    MemoryApplyReceiptRecord.session_id.in_(session_ids)
                )
            ).all()
        ]
        self._delete_where_in(
            MemoryApplyTargetLinkRecord,
            MemoryApplyTargetLinkRecord.apply_id,
            apply_ids,
        )
        self._delete_where_in(
            MemoryApplyTargetLinkRecord,
            MemoryApplyTargetLinkRecord.proposal_id,
            proposal_ids,
        )
        self._session.exec(
            delete(MemoryApplyTargetLinkRecord).where(
                MemoryApplyTargetLinkRecord.session_id.in_(session_ids)
            )
        )
        self._delete_where_in(
            MemoryApplyReceiptRecord,
            MemoryApplyReceiptRecord.apply_id,
            apply_ids,
        )
        self._delete_where_in(
            MemoryProposalRecord,
            MemoryProposalRecord.proposal_id,
            proposal_ids,
        )
        self._session.exec(
            delete(MemoryChangeEventRecord).where(
                MemoryChangeEventRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(RuntimeWorkspaceMaterialRecord).where(
                RuntimeWorkspaceMaterialRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(CoreStateSnapshotManifestRecord).where(
                CoreStateSnapshotManifestRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(CoreStateProjectionSlotRevisionRecord).where(
                CoreStateProjectionSlotRevisionRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(CoreStateProjectionSlotRecord).where(
                CoreStateProjectionSlotRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(CoreStateAuthoritativeRevisionRecord).where(
                CoreStateAuthoritativeRevisionRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(CoreStateAuthoritativeObjectRecord).where(
                CoreStateAuthoritativeObjectRecord.session_id.in_(session_ids)
            )
        )

        self._session.exec(
            delete(RuntimeWorkflowJobRecord).where(
                RuntimeWorkflowJobRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(StoryTurnRecord).where(StoryTurnRecord.session_id.in_(session_ids))
        )
        self._session.exec(
            delete(RuntimeConfigControlReceiptRecord).where(
                RuntimeConfigControlReceiptRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(BranchControlReceiptRecord).where(
                BranchControlReceiptRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(StoryArtifactRecord).where(
                StoryArtifactRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(StoryDiscussionEntryRecord).where(
                StoryDiscussionEntryRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(StoryBlockConsumerStateRecord).where(
                StoryBlockConsumerStateRecord.session_id.in_(session_ids)
            )
        )
        self._delete_where_in(
            ChapterWorkspaceRecord,
            ChapterWorkspaceRecord.chapter_workspace_id,
            chapter_ids,
        )
        self._session.exec(
            delete(BranchHeadRecord).where(BranchHeadRecord.session_id.in_(session_ids))
        )
        self._session.exec(
            delete(RuntimeProfileSnapshotRecord).where(
                RuntimeProfileSnapshotRecord.session_id.in_(session_ids)
            )
        )
        self._session.exec(
            delete(StorySessionRecord).where(
                StorySessionRecord.session_id.in_(session_ids)
            )
        )
        self._session.commit()

    def _ensure_source_workspace(self, *, story_id: str, mode: StoryMode) -> str:
        existing = self._session.exec(
            select(SetupWorkspaceRecord).where(
                SetupWorkspaceRecord.story_id == story_id
            )
        ).first()
        if existing is not None:
            return existing.workspace_id
        workspace = SetupWorkspaceService(self._session).create_workspace(
            story_id=story_id,
            mode=mode,
        )
        return workspace.workspace_id

    def _require_current_chapter(self, session_id: str):
        chapter = self._story_session_service.get_current_chapter(session_id)
        if chapter is None:
            raise LegalLongformSessionSeedError(
                "legal_longform_seed_current_chapter_missing",
                session_id,
            )
        return chapter

    def _delete_where_in(self, model, column, values: list[str]) -> None:
        if not values:
            return
        self._session.exec(delete(model).where(column.in_(values)))

    @staticmethod
    def _settled_status():
        from rp.models.runtime_identity import StoryTurnStatus

        return StoryTurnStatus.SETTLED


def load_default_template() -> LegalLongformSessionTemplate:
    """Load the bundled reusable seed template."""

    return LegalLongformSessionSeeder.load_template_from_path(DEFAULT_TEMPLATE_PATH)
