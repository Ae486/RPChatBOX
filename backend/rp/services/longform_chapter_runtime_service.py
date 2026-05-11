"""Longform chapter lifecycle adapter over adopted draft and legacy chapter state."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import asc
from sqlmodel import Session, select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from rp.models.longform_chapter_contracts import (
    ChapterBridgeMaterial,
    LONGFORM_OUTLINE_SCHEMA_VERSION,
    LongformOutlineBeat,
    LongformChapterTransitionReceipt,
    LongformOutlineProgress,
    LongformStructuredOutline,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.story_runtime import (
    ChapterWorkspace,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySession,
)
from rp.services.chapter_bridge_provider import ChapterBridgeProvider
from rp.services.draft_selection_service import DraftSelectionService
from rp.services.rewrite_candidate_service import RewriteCandidateService
from rp.services.runtime_read_manifest_service import (
    BranchVisibilityResolver,
    RuntimeReadManifestServiceError,
)
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


CHAPTER_BRIDGE_PAYLOAD_VERSION = "longform-chapter-bridge.v1"
CHAPTER_TRANSITION_PAYLOAD_VERSION = "longform-chapter-transition.v1"
OUTLINE_PROGRESS_PAYLOAD_VERSION = "longform-outline-progress.v1"
_CHAPTER_DOMAIN = "chapter"


class LongformChapterRuntimeServiceError(ValueError):
    """Stable longform chapter runtime error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class PreparedChapterTransition:
    """Prepared chapter transition plus any adapter-owned artifact updates."""

    chapter: ChapterWorkspace
    bridge: ChapterBridgeMaterial | None
    receipt: LongformChapterTransitionReceipt | None


class LongformChapterRuntimeService:
    """Prepare branch-scoped chapter transition state without redefining story truth."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        workspace_material_service: RuntimeWorkspaceMaterialService | None = None,
        draft_selection_service: DraftSelectionService | None = None,
        rewrite_candidate_service: RewriteCandidateService | None = None,
        chapter_bridge_provider: ChapterBridgeProvider | None = None,
        session: Session | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._session = session
        self._workspace_material_service = (
            workspace_material_service
            if workspace_material_service is not None
            else RuntimeWorkspaceMaterialService(session=session)
        )
        self._draft_selection_service = (
            draft_selection_service
            if draft_selection_service is not None
            else DraftSelectionService(
                session=session,
                workspace_material_service=self._workspace_material_service,
            )
        )
        self._rewrite_candidate_service = (
            rewrite_candidate_service
            if rewrite_candidate_service is not None
            else RewriteCandidateService(
                session=session,
                workspace_material_service=self._workspace_material_service,
            )
        )
        self._chapter_bridge_provider = (
            chapter_bridge_provider or ChapterBridgeProvider()
        )
        self._branch_visibility_resolver = (
            BranchVisibilityResolver(session) if session is not None else None
        )
        self._runtime_identity_service = (
            StoryRuntimeIdentityService(session) if session is not None else None
        )

    def normalize_outline_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
        artifact: StoryArtifact,
    ) -> tuple[str, dict[str, Any], list[str]]:
        outline, warnings, normalization_source = _normalize_structured_outline(
            chapter_index=chapter.chapter_index,
            chapter_goal=chapter.chapter_goal,
            content_text=artifact.content_text,
            metadata=artifact.metadata,
        )
        display_text = _render_outline_display_text(outline)
        metadata = {
            **dict(artifact.metadata or {}),
            "structured_outline": outline.model_dump(mode="json"),
            "outline_schema_version": LONGFORM_OUTLINE_SCHEMA_VERSION,
            "outline_normalization_source": normalization_source,
            "outline_normalization_warnings": list(warnings),
        }
        return display_text, metadata, warnings

    def build_outline_payload(
        self,
        *,
        artifact: StoryArtifact,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        structured_outline = _structured_outline_from_metadata(metadata)
        payload = {
            "artifact_id": artifact.artifact_id,
            "content_text": artifact.content_text,
            "metadata": dict(metadata),
        }
        if structured_outline is not None:
            payload["structured_outline"] = structured_outline.model_dump(mode="json")
        return payload

    def initialize_outline_progress(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        chapter: ChapterWorkspace,
        accepted_outline_json: dict[str, Any],
    ) -> LongformOutlineProgress | None:
        outline = _structured_outline_from_outline_payload(accepted_outline_json)
        if outline is None:
            return None
        outline_artifact_id = str(accepted_outline_json.get("artifact_id") or "").strip()
        if not outline_artifact_id:
            return None
        progress = LongformOutlineProgress.initialize(
            outline_artifact_id=outline_artifact_id,
            outline=outline,
            metadata_json={
                "payload_version": OUTLINE_PROGRESS_PAYLOAD_VERSION,
                "chapter_workspace_id": chapter.chapter_workspace_id,
                "source": "accept_outline",
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
        )
        if identity is not None:
            self._record_outline_progress(
                identity=identity,
                progress=progress,
                source_refs=[outline_artifact_id],
            )
        return progress

    def effective_outline_progress(
        self,
        *,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity | None = None,
        exclude_artifact_ids: set[str] | None = None,
    ) -> LongformOutlineProgress | None:
        outline_payload = chapter.accepted_outline_json or {}
        outline = _structured_outline_from_outline_payload(outline_payload)
        if outline is None:
            return None
        outline_artifact_id = str(outline_payload.get("artifact_id") or "").strip()
        if not outline_artifact_id:
            return None
        progress = LongformOutlineProgress.initialize(
            outline_artifact_id=outline_artifact_id,
            outline=outline,
            metadata_json={
                "payload_version": OUTLINE_PROGRESS_PAYLOAD_VERSION,
                "chapter_workspace_id": chapter.chapter_workspace_id,
                "source": "effective_rebuild",
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
        )
        accepted_segments = self._accepted_segments_for_progress(
            chapter=chapter,
            identity=identity,
            exclude_artifact_ids=exclude_artifact_ids,
        )
        covered_beat_ids: list[str] = []
        segment_by_beat_id: dict[str, str] = {}
        for segment in accepted_segments:
            target_beat_id = _artifact_target_beat_id(segment)
            if not target_beat_id:
                target_beat_id = progress.current_beat_id
            if not target_beat_id or outline.beat_by_id(target_beat_id) is None:
                continue
            if target_beat_id not in covered_beat_ids:
                covered_beat_ids.append(target_beat_id)
            segment_by_beat_id[target_beat_id] = segment.artifact_id
        status_by_beat_id: dict[str, str] = {}
        current_beat_id: str | None = None
        for beat in outline.beats:
            if beat.beat_id in covered_beat_ids:
                status_by_beat_id[beat.beat_id] = "accepted"
                continue
            if current_beat_id is None:
                current_beat_id = beat.beat_id
                status_by_beat_id[beat.beat_id] = "current"
                continue
            status_by_beat_id[beat.beat_id] = "pending"
        if current_beat_id is None and outline.beats:
            for beat in outline.beats:
                status_by_beat_id.setdefault(beat.beat_id, "accepted")
        return progress.model_copy(
            update={
                "current_beat_id": current_beat_id,
                "covered_beat_ids": covered_beat_ids,
                "segment_by_beat_id": segment_by_beat_id,
                "status_by_beat_id": status_by_beat_id,
            }
        )

    def advance_outline_progress_for_adoption(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        chapter_before_accept: ChapterWorkspace,
        chapter_after_accept: ChapterWorkspace,
        accepted_artifact: StoryArtifact,
    ) -> LongformOutlineProgress | None:
        progress_before = self.effective_outline_progress(
            chapter=chapter_before_accept,
            identity=identity,
            exclude_artifact_ids={accepted_artifact.artifact_id},
        )
        if progress_before is None:
            return None
        outline = _structured_outline_from_outline_payload(
            chapter_before_accept.accepted_outline_json or {}
        )
        if outline is None:
            return None
        target_beat_id = _artifact_target_beat_id(accepted_artifact) or progress_before.current_beat_id
        if not target_beat_id or outline.beat_by_id(target_beat_id) is None:
            return progress_before
        current_beat_id = progress_before.current_beat_id
        if current_beat_id and current_beat_id != target_beat_id:
            raise LongformChapterRuntimeServiceError(
                "longform_outline_progress_target_beat_mismatch",
                f"{current_beat_id}:{target_beat_id}",
            )
        covered_beat_ids = list(progress_before.covered_beat_ids)
        if target_beat_id not in covered_beat_ids:
            covered_beat_ids.append(target_beat_id)
        segment_by_beat_id = {
            **dict(progress_before.segment_by_beat_id),
            target_beat_id: accepted_artifact.artifact_id,
        }
        next_current_beat_id: str | None = None
        status_by_beat_id: dict[str, str] = {}
        for beat in outline.beats:
            if beat.beat_id in covered_beat_ids:
                status_by_beat_id[beat.beat_id] = "accepted"
                continue
            if next_current_beat_id is None:
                next_current_beat_id = beat.beat_id
                status_by_beat_id[beat.beat_id] = "current"
                continue
            status_by_beat_id[beat.beat_id] = "pending"
        updated_progress = progress_before.model_copy(
            update={
                "current_beat_id": next_current_beat_id,
                "covered_beat_ids": covered_beat_ids,
                "segment_by_beat_id": segment_by_beat_id,
                "status_by_beat_id": status_by_beat_id,
                "metadata_json": {
                    **dict(progress_before.metadata_json),
                    "source": "accept_pending_segment",
                    "chapter_workspace_id": chapter_after_accept.chapter_workspace_id,
                    "last_adopted_segment_id": accepted_artifact.artifact_id,
                    "chapter_ready_for_completion": next_current_beat_id is None,
                },
            }
        )
        if identity is not None:
            self._record_outline_progress(
                identity=identity,
                progress=updated_progress,
                source_refs=[
                    progress_before.outline_artifact_id,
                    accepted_artifact.artifact_id,
                ],
            )
        return updated_progress

    def prepare_chapter_transition(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        session: StorySession,
        chapter: ChapterWorkspace,
    ) -> PreparedChapterTransition:
        if identity is None:
            return PreparedChapterTransition(chapter=chapter, bridge=None, receipt=None)
        transition = self._resolve_transition_state(
            identity=identity,
            chapter=chapter,
        )
        bridge = self._chapter_bridge_provider.build_bridge_material(
            identity=identity,
            from_chapter_index=transition["chapter"].chapter_index,
            to_chapter_index=transition["chapter"].chapter_index + 1,
            adopted_output_ref=transition["adopted_output_ref"],
            accepted_outline_ref=transition["accepted_outline_ref"],
            chapter_goal_ref=transition["chapter_goal_ref"],
            adopted_output_text=transition["adopted_output_text"],
            source_refs=transition["source_refs"],
            covered_beat_ids=transition["covered_beat_ids"],
            continuity_notes=transition["continuity_notes"],
            metadata_json={
                "payload_version": CHAPTER_BRIDGE_PAYLOAD_VERSION,
                "bridge_source": transition["adoption_source"],
                "chapter_goal": transition["chapter"].chapter_goal,
                "accepted_outline_present": transition["accepted_outline_ref"] is not None,
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
        )
        bridge_material_id = self._record_bridge_material(
            identity=identity,
            bridge=bridge,
            source_refs=transition["source_refs"],
        )
        receipt = LongformChapterTransitionReceipt(
            receipt_id=f"chapter_transition_{uuid4().hex}",
            identity=identity,
            from_chapter_index=transition["chapter"].chapter_index,
            to_chapter_index=transition["chapter"].chapter_index + 1,
            adopted_output_ref=transition["adopted_output_ref"],
            bridge_material_ref=bridge_material_id,
            status="prepared",
            metadata_json={
                "payload_version": CHAPTER_TRANSITION_PAYLOAD_VERSION,
                "bridge_source": transition["adoption_source"],
                "chapter_workspace_id": transition["chapter"].chapter_workspace_id,
                "accepted_outline_ref": transition["accepted_outline_ref"],
                "chapter_goal_ref": transition["chapter_goal_ref"],
                "covered_beat_ids": transition["covered_beat_ids"],
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
            created_at=_utcnow(),
        )
        self._record_transition_receipt(
            identity=identity,
            receipt=receipt,
            source_refs=[
                *transition["source_refs"],
                bridge_material_id,
            ],
        )
        return PreparedChapterTransition(
            chapter=transition["chapter"],
            bridge=bridge,
            receipt=receipt,
        )

    async def prepare_chapter_transition_with_summary(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        session: StorySession,
        chapter: ChapterWorkspace,
        model_id: str,
        provider_id: str | None,
    ) -> PreparedChapterTransition:
        if identity is None:
            return PreparedChapterTransition(chapter=chapter, bridge=None, receipt=None)
        transition = self._resolve_transition_state(
            identity=identity,
            chapter=chapter,
        )
        bridge = await self._chapter_bridge_provider.build_bridge_material_with_summary(
            identity=identity,
            from_chapter_index=transition["chapter"].chapter_index,
            to_chapter_index=transition["chapter"].chapter_index + 1,
            adopted_output_ref=transition["adopted_output_ref"],
            accepted_outline_ref=transition["accepted_outline_ref"],
            chapter_goal_ref=transition["chapter_goal_ref"],
            chapter_goal=transition["chapter"].chapter_goal,
            adopted_output_text=transition["adopted_output_text"],
            accepted_segment_texts=transition["accepted_segment_texts"],
            covered_beat_ids=transition["covered_beat_ids"],
            covered_beats=transition["covered_beats"],
            source_refs=transition["source_refs"],
            model_id=model_id,
            provider_id=provider_id,
            metadata_json={
                "payload_version": CHAPTER_BRIDGE_PAYLOAD_VERSION,
                "bridge_source": transition["adoption_source"],
                "chapter_goal": transition["chapter"].chapter_goal,
                "accepted_outline_present": transition["accepted_outline_ref"] is not None,
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
        )
        bridge_material_id = self._record_bridge_material(
            identity=identity,
            bridge=bridge,
            source_refs=transition["source_refs"],
        )
        receipt = LongformChapterTransitionReceipt(
            receipt_id=f"chapter_transition_{uuid4().hex}",
            identity=identity,
            from_chapter_index=transition["chapter"].chapter_index,
            to_chapter_index=transition["chapter"].chapter_index + 1,
            adopted_output_ref=transition["adopted_output_ref"],
            bridge_material_ref=bridge_material_id,
            status="prepared",
            metadata_json={
                "payload_version": CHAPTER_TRANSITION_PAYLOAD_VERSION,
                "bridge_source": transition["adoption_source"],
                "chapter_workspace_id": transition["chapter"].chapter_workspace_id,
                "accepted_outline_ref": transition["accepted_outline_ref"],
                "chapter_goal_ref": transition["chapter_goal_ref"],
                "covered_beat_ids": transition["covered_beat_ids"],
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
            created_at=_utcnow(),
        )
        self._record_transition_receipt(
            identity=identity,
            receipt=receipt,
            source_refs=[
                *transition["source_refs"],
                bridge_material_id,
            ],
        )
        return PreparedChapterTransition(
            chapter=transition["chapter"],
            bridge=bridge,
            receipt=receipt,
        )

    def _bind_and_settle_accepted_artifact_origin_turn(
        self,
        *,
        session_id: str,
        accepted_artifact: StoryArtifact,
    ) -> None:
        if self._runtime_identity_service is None:
            return
        metadata = dict(accepted_artifact.metadata or {})
        turn_id = str(metadata.get("runtime_turn_id") or "").strip()
        branch_head_id = str(metadata.get("runtime_branch_head_id") or "").strip()
        if not turn_id or not branch_head_id:
            return
        self._runtime_identity_service.bind_turn_output_refs_if_visible(
            session_id=session_id,
            turn_id=turn_id,
            artifact_id=accepted_artifact.artifact_id,
            branch_head_id=branch_head_id,
        )
        self._runtime_identity_service.settle_adopted_output_turn_if_visible(
            session_id=session_id,
            turn_id=turn_id,
            reason="chapter_transition_adopted_visible_output",
        )

    def _resolve_transition_state(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        chapter: ChapterWorkspace,
    ) -> dict[str, Any]:
        active_chapter = self._active_branch_chapter_view(chapter)
        updated_chapter = active_chapter
        adopted_output_ref: str | None = None
        adopted_output_text: str | None = None
        adoption_source = "empty_chapter_adapter"
        source_refs: list[str] = []
        pending_artifact = self._pending_segment_artifact(chapter=active_chapter)
        accepted_segment_texts: list[str] = []
        if pending_artifact is not None:
            adoption = self._draft_selection_service.get_latest_adoption_receipt_for_branch(
                story_id=identity.story_id,
                session_id=identity.session_id,
                branch_head_id=identity.branch_head_id,
                draft_ref=f"artifact:{pending_artifact.artifact_id}",
            )
            if adoption is None:
                raise LongformChapterRuntimeServiceError(
                    "longform_chapter_adoption_required",
                    pending_artifact.artifact_id,
                )
            adopted_output_ref = adoption.adopted_output_ref
            adopted_output_text = self._resolve_adopted_output_text(
                story_id=identity.story_id,
                session_id=identity.session_id,
                branch_head_id=identity.branch_head_id,
                draft_ref=adoption.draft_ref,
                adopted_output_ref=adoption.adopted_output_ref,
            )
            acceptance_artifact = self._story_session_service.update_artifact(
                artifact_id=pending_artifact.artifact_id,
                content_text=adopted_output_text,
                status=StoryArtifactStatus.ACCEPTED,
                metadata={
                    **dict(pending_artifact.metadata or {}),
                    "chapter_transition_adopted_output_ref": adopted_output_ref,
                    "chapter_transition_adoption_receipt_id": adoption.receipt_id,
                    "chapter_transition_adapter_source": "draft_adoption_receipt",
                },
            )
            self._bind_and_settle_accepted_artifact_origin_turn(
                session_id=identity.session_id,
                accepted_artifact=acceptance_artifact,
            )
            self._supersede_other_draft_segments(
                chapter_workspace_id=chapter.chapter_workspace_id,
                accepted_artifact_id=acceptance_artifact.artifact_id,
            )
            updated_chapter = self._story_session_service.update_chapter_workspace(
                chapter_workspace_id=active_chapter.chapter_workspace_id,
                pending_segment_artifact_id=None,
            )
            self.advance_outline_progress_for_adoption(
                identity=identity,
                chapter_before_accept=active_chapter,
                chapter_after_accept=updated_chapter,
                accepted_artifact=acceptance_artifact,
            )
            adoption_source = "draft_adoption_receipt"
            source_refs = [
                adoption.receipt_id,
                adoption.adopted_output_ref,
                acceptance_artifact.artifact_id,
            ]
        else:
            latest_accepted = self._latest_accepted_segment(
                chapter=active_chapter,
                identity=identity,
            )
            if latest_accepted is not None:
                adopted_output_ref = latest_accepted.artifact_id
                adopted_output_text = latest_accepted.content_text
                adoption_source = "accepted_segment_adapter"
                source_refs = [latest_accepted.artifact_id]
        progress = self.effective_outline_progress(
            chapter=updated_chapter,
            identity=identity,
        )
        accepted_outline_ref = _artifact_ref_from_outline(updated_chapter)
        chapter_goal_ref = _chapter_goal_ref(updated_chapter)
        covered_beat_ids = [] if progress is None else list(progress.covered_beat_ids)
        accepted_segments = self._accepted_segments_for_progress(
            chapter=updated_chapter,
            identity=identity,
        )
        accepted_segment_texts = [segment.content_text for segment in accepted_segments]
        updated_chapter = updated_chapter.model_copy(
            update={
                "accepted_segment_ids": [
                    segment.artifact_id for segment in accepted_segments
                ]
            }
        )
        covered_beats = self._covered_beats_for_progress(
            chapter=updated_chapter,
            progress=progress,
        )
        continuity_notes = [
            note
            for beat in covered_beats
            for note in list(beat.get("continuity_notes") or [])
            if isinstance(note, str) and note.strip()
        ]
        return {
            "chapter": updated_chapter,
            "adopted_output_ref": adopted_output_ref,
            "adopted_output_text": adopted_output_text,
            "adoption_source": adoption_source,
            "accepted_outline_ref": accepted_outline_ref,
            "chapter_goal_ref": chapter_goal_ref,
            "covered_beat_ids": covered_beat_ids,
            "covered_beats": covered_beats,
            "continuity_notes": continuity_notes,
            "source_refs": source_refs,
            "accepted_segment_texts": accepted_segment_texts,
        }

    def get_latest_bridge_material_for_branch(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        source_chapter_index: int,
        identity: MemoryRuntimeIdentity | None = None,
    ) -> ChapterBridgeMaterial | None:
        records = self._list_branch_material_records(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            payload_kind="chapter_bridge_material",
        )
        branch_read_scope = self._branch_read_scope(identity=identity)
        matches = [
            ChapterBridgeMaterial.model_validate(record.payload_json.get("record"))
            for record in records
            if (
                self._workspace_record_visible(
                    record=record,
                    branch_read_scope=branch_read_scope,
                )
                and (
                isinstance(record.payload_json.get("record"), dict)
                and record.payload_json.get("record", {}).get("source_chapter_index")
                == source_chapter_index
                )
            )
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.target_chapter_index)

    def get_latest_bridge_material_for_target_chapter(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        target_chapter_index: int,
        identity: MemoryRuntimeIdentity | None = None,
    ) -> tuple[str, ChapterBridgeMaterial] | None:
        records = self._list_branch_material_records(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            payload_kind="chapter_bridge_material",
        )
        branch_read_scope = self._branch_read_scope(identity=identity)
        matches: list[tuple[RuntimeWorkspaceMaterialRecord, ChapterBridgeMaterial]] = []
        for record in records:
            if not self._workspace_record_visible(
                record=record,
                branch_read_scope=branch_read_scope,
            ):
                continue
            payload_record = record.payload_json.get("record")
            if not isinstance(payload_record, dict):
                continue
            if payload_record.get("target_chapter_index") != target_chapter_index:
                continue
            matches.append(
                (
                    record,
                    ChapterBridgeMaterial.model_validate(payload_record),
                )
            )
        if not matches:
            return None
        latest_record, latest_bridge = max(
            matches,
            key=lambda item: (
                item[1].source_chapter_index,
                item[1].target_chapter_index,
                item[0].created_at,
                item[0].material_id,
            ),
        )
        return latest_record.material_id, latest_bridge

    def get_latest_outline_progress_for_chapter(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        chapter_index: int,
        identity: MemoryRuntimeIdentity | None = None,
    ) -> tuple[str, LongformOutlineProgress] | None:
        records = self._list_branch_material_records(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            payload_kind="longform_outline_progress",
        )
        branch_read_scope = self._branch_read_scope(identity=identity)
        matches: list[tuple[RuntimeWorkspaceMaterialRecord, LongformOutlineProgress]] = []
        for record in records:
            if not self._workspace_record_visible(
                record=record,
                branch_read_scope=branch_read_scope,
            ):
                continue
            payload_record = record.payload_json.get("record")
            if not isinstance(payload_record, dict):
                continue
            if int(payload_record.get("chapter_index") or -1) != chapter_index:
                continue
            try:
                progress = LongformOutlineProgress.model_validate(payload_record)
            except ValidationError:
                continue
            matches.append((record, progress))
        if not matches:
            return None
        latest_record, latest_progress = max(
            matches,
            key=lambda item: (
                item[1].chapter_index,
                item[0].created_at,
                item[0].material_id,
            ),
        )
        return latest_record.material_id, latest_progress

    def _pending_segment_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
    ) -> StoryArtifact | None:
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=chapter.session_id,
            chapter_index=chapter.chapter_index,
        )
        visible_artifacts = {
            artifact.artifact_id: artifact for artifact in snapshot.artifacts
        }
        artifact_id = str(chapter.pending_segment_artifact_id or "").strip()
        if not artifact_id:
            return None
        if snapshot.chapter.pending_segment_artifact_id != artifact_id:
            return None
        artifact = visible_artifacts.get(artifact_id)
        if artifact is None:
            return None
        if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
            return None
        if artifact.status != StoryArtifactStatus.DRAFT:
            return None
        return artifact

    def _active_branch_chapter_view(self, chapter: ChapterWorkspace) -> ChapterWorkspace:
        return self._story_session_service.build_chapter_snapshot(
            session_id=chapter.session_id,
            chapter_index=chapter.chapter_index,
        ).chapter

    def _accepted_segments_for_progress(
        self,
        *,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity | None,
        exclude_artifact_ids: set[str] | None = None,
    ) -> list[StoryArtifact]:
        excluded_ids = {str(item) for item in (exclude_artifact_ids or set()) if item}
        session_id = identity.session_id if identity is not None else chapter.session_id
        return [
            artifact
            for artifact in self._story_session_service.active_branch_accepted_story_segments(
                session_id=session_id,
                chapter_index=chapter.chapter_index,
            )
            if artifact.artifact_id not in excluded_ids
        ]

    def _resolve_adopted_output_text(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        draft_ref: str,
        adopted_output_ref: str,
    ) -> str:
        artifact = self._story_session_service.get_artifact(adopted_output_ref)
        if artifact is not None:
            return artifact.content_text
        candidate = self._rewrite_candidate_service.get_candidate_by_output_ref_for_branch(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            candidate_output_ref=adopted_output_ref,
            draft_ref=draft_ref,
        )
        if candidate is not None:
            text = str(
                candidate.candidate_draft_text or candidate.full_output_text or ""
            ).strip()
            if text:
                return text
        raise LongformChapterRuntimeServiceError(
            "longform_chapter_adopted_output_not_found",
            adopted_output_ref,
        )

    def _latest_accepted_segment(
        self,
        *,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity | None = None,
    ) -> StoryArtifact | None:
        accepted = self._accepted_segments_for_progress(
            chapter=chapter,
            identity=identity,
        )
        if not accepted:
            return None
        return accepted[-1]

    def _covered_beats_for_progress(
        self,
        *,
        chapter: ChapterWorkspace,
        progress: LongformOutlineProgress | None,
    ) -> list[dict[str, Any]]:
        outline = _structured_outline_from_outline_payload(chapter.accepted_outline_json or {})
        if outline is None or progress is None:
            return []
        beats: list[dict[str, Any]] = []
        covered_set = set(progress.covered_beat_ids)
        for beat in outline.beats:
            if beat.beat_id not in covered_set:
                continue
            beats.append(beat.model_dump(mode="json"))
        return beats

    def _supersede_other_draft_segments(
        self,
        *,
        chapter_workspace_id: str,
        accepted_artifact_id: str,
    ) -> None:
        for artifact in self._story_session_service.list_artifacts(
            chapter_workspace_id=chapter_workspace_id
        ):
            if artifact.artifact_id == accepted_artifact_id:
                continue
            if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
                continue
            if artifact.status != StoryArtifactStatus.DRAFT:
                continue
            self._story_session_service.update_artifact(
                artifact_id=artifact.artifact_id,
                status=StoryArtifactStatus.SUPERSEDED,
            )

    def _record_bridge_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        bridge: ChapterBridgeMaterial,
        source_refs: list[str],
    ) -> str:
        material_id = f"chapter-bridge:{identity.turn_id}:{bridge.bridge_id}"
        self._workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=material_id,
                material_kind=RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE,
                identity=identity,
                domain=_CHAPTER_DOMAIN,
                domain_path="chapter.longform_chapter.bridge_material",
                source_refs=_source_refs(source_refs, entry_id=bridge.bridge_id),
                payload={
                    "payload_version": CHAPTER_BRIDGE_PAYLOAD_VERSION,
                    "payload_kind": "chapter_bridge_material",
                    "record_id": bridge.bridge_id,
                    "record": bridge.model_dump(mode="json"),
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                },
                visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
                created_by="longform_chapter_runtime.prepare_transition",
                metadata={
                    "chapter_bridge_material": True,
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                    "source_of_truth": False,
                },
            )
        )
        return material_id

    def _record_outline_progress(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        progress: LongformOutlineProgress,
        source_refs: list[str],
    ) -> str:
        material_id = (
            f"outline-progress:{identity.turn_id}:"
            f"{progress.chapter_index}:{progress.outline_artifact_id}"
        )
        self._workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=material_id,
                material_kind=RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE,
                identity=identity,
                domain=_CHAPTER_DOMAIN,
                domain_path="chapter.longform_outline.progress",
                source_refs=_source_refs(
                    source_refs,
                    entry_id=material_id,
                ),
                payload={
                    "payload_version": OUTLINE_PROGRESS_PAYLOAD_VERSION,
                    "payload_kind": "longform_outline_progress",
                    "record_id": material_id,
                    "record": progress.model_dump(mode="json"),
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                },
                visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
                created_by="longform_outline_progress",
                metadata={
                    "outline_progress": True,
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                    "source_of_truth": False,
                },
            )
        )
        return material_id

    def _record_transition_receipt(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        receipt: LongformChapterTransitionReceipt,
        source_refs: list[str],
    ) -> None:
        self._workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=f"chapter-transition:{identity.turn_id}:{receipt.receipt_id}",
                material_kind=RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE,
                identity=identity,
                domain=_CHAPTER_DOMAIN,
                domain_path="chapter.longform_chapter.transition_receipt",
                source_refs=_source_refs(source_refs, entry_id=receipt.receipt_id),
                payload={
                    "payload_version": CHAPTER_TRANSITION_PAYLOAD_VERSION,
                    "payload_kind": "chapter_transition_receipt",
                    "record_id": receipt.receipt_id,
                    "record": receipt.model_dump(mode="json"),
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                },
                visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
                created_by="longform_chapter_runtime.prepare_transition",
                metadata={
                    "chapter_transition_receipt": True,
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                    "source_of_truth": False,
                },
            )
        )

    def _list_branch_material_records(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        payload_kind: str,
    ) -> list[RuntimeWorkspaceMaterialRecord]:
        if self._session is None:
            return []
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(RuntimeWorkspaceMaterialRecord.story_id == story_id)
            .where(RuntimeWorkspaceMaterialRecord.session_id == session_id)
            .where(RuntimeWorkspaceMaterialRecord.branch_head_id == branch_head_id)
            .where(
                RuntimeWorkspaceMaterialRecord.material_kind
                == RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE.value
            )
            .order_by(asc(cast(Any, RuntimeWorkspaceMaterialRecord.created_at)))
            .order_by(asc(cast(Any, RuntimeWorkspaceMaterialRecord.material_id)))
        )
        records = list(self._session.exec(stmt).all())
        return [
            record
            for record in records
            if record.payload_json.get("payload_kind") == payload_kind
        ]

    def _branch_read_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
    ):
        if identity is None or self._branch_visibility_resolver is None:
            return None
        try:
            return self._branch_visibility_resolver.build_runtime_scope(identity=identity)
        except RuntimeReadManifestServiceError:
            return None

    def _workspace_record_visible(
        self,
        *,
        record: RuntimeWorkspaceMaterialRecord,
        branch_read_scope,
    ) -> bool:
        if branch_read_scope is None or self._branch_visibility_resolver is None:
            return True
        lifecycle = str(record.lifecycle or "").strip().lower()
        visibility_state = (
            "hidden"
            if lifecycle
            in {
                "invalidated",
                "expired",
                "discarded",
            }
            else "active"
        )
        return self._branch_visibility_resolver.is_visible(
            scope=branch_read_scope,
            visibility_scope="branch_scoped",
            visibility_state=visibility_state,
            owning_branch_head_id=record.branch_head_id,
            origin_turn_id=record.turn_id,
        )


def _artifact_ref_from_outline(chapter: ChapterWorkspace) -> str | None:
    accepted_outline = chapter.accepted_outline_json or {}
    artifact_id = str(accepted_outline.get("artifact_id") or "").strip()
    return artifact_id or None


def _structured_outline_from_metadata(
    metadata: dict[str, Any] | None,
) -> LongformStructuredOutline | None:
    if not isinstance(metadata, dict):
        return None
    payload = metadata.get("structured_outline")
    if not isinstance(payload, dict):
        return None
    try:
        return LongformStructuredOutline.model_validate(payload)
    except ValidationError:
        return None


def _structured_outline_from_outline_payload(
    payload: dict[str, Any] | None,
) -> LongformStructuredOutline | None:
    if not isinstance(payload, dict):
        return None
    structured_payload = payload.get("structured_outline")
    if isinstance(structured_payload, dict):
        try:
            return LongformStructuredOutline.model_validate(structured_payload)
        except ValidationError:
            pass
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _structured_outline_from_metadata(metadata)
    return None


def _normalize_structured_outline(
    *,
    chapter_index: int,
    chapter_goal: str | None,
    content_text: str,
    metadata: dict[str, Any] | None,
) -> tuple[LongformStructuredOutline, list[str], str]:
    structured_from_metadata = _structured_outline_from_metadata(metadata)
    if structured_from_metadata is not None:
        return structured_from_metadata, [], "artifact_metadata"
    try:
        payload = _extract_json_object(content_text)
        outline = LongformStructuredOutline.model_validate(payload)
        return outline, [], "writer_json"
    except (ValueError, ValidationError, json.JSONDecodeError):
        pass
    beat_lines = _extract_outline_lines(content_text)
    if not beat_lines:
        fallback_line = str(content_text or "").strip()
        if not fallback_line:
            fallback_line = "Draft outline beat"
        beat_lines = [fallback_line]
    normalized_goal = str(chapter_goal or "").strip() or "Advance the chapter."
    outline = LongformStructuredOutline(
        chapter_index=chapter_index,
        chapter_goal=normalized_goal,
        beats=[
            LongformOutlineBeat(
                beat_id=f"beat_{index + 1:03d}",
                order=index + 1,
                title=line,
                goal=line,
            )
            for index, line in enumerate(beat_lines)
        ],
    )
    return outline, ["outline_normalized_from_non_json_output"], "deterministic_line_normalizer"


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty outline text")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def _extract_outline_lines(text: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        normalized = raw_line.strip()
        if not normalized:
            continue
        normalized = re.sub(r"^\s*[-*]\s*", "", normalized)
        normalized = re.sub(r"^\s*\d+[.)\s-]*", "", normalized)
        normalized = normalized.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


def _render_outline_display_text(outline: LongformStructuredOutline) -> str:
    lines: list[str] = []
    if outline.chapter_title:
        lines.append(f"# {outline.chapter_title}")
        lines.append("")
    lines.append(f"Chapter goal: {outline.chapter_goal}")
    lines.append("")
    for beat in outline.beats:
        lines.append(f"{beat.order}. {beat.title}")
        lines.append(f"   Goal: {beat.goal}")
        if beat.must_include:
            lines.append("   Must include: " + "; ".join(beat.must_include))
        if beat.avoid:
            lines.append("   Avoid: " + "; ".join(beat.avoid))
        if beat.continuity_notes:
            lines.append("   Continuity: " + "; ".join(beat.continuity_notes))
    return "\n".join(lines).strip()


def _artifact_target_beat_id(artifact: StoryArtifact) -> str | None:
    metadata = dict(artifact.metadata or {})
    normalized = str(metadata.get("target_beat_id") or "").strip()
    return normalized or None


def _chapter_goal_ref(chapter: ChapterWorkspace) -> str | None:
    goal = str(chapter.chapter_goal or "").strip()
    if not goal:
        return None
    return f"chapter_goal:{chapter.chapter_workspace_id}"


def _source_refs(source_ids: list[str], *, entry_id: str) -> list[MemorySourceRef]:
    refs: list[MemorySourceRef] = []
    seen: set[str] = set()
    for source_id in source_ids:
        normalized = str(source_id or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            MemorySourceRef(
                source_type="longform_chapter_transition_source",
                source_id=normalized,
                layer="runtime_workspace",
                domain=_CHAPTER_DOMAIN,
                block_id="chapter.runtime_workspace",
                entry_id=entry_id,
            )
        )
    return refs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
