"""Longform chapter lifecycle adapter over adopted draft and legacy chapter state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from rp.models.longform_chapter_contracts import (
    ChapterBridgeMaterial,
    LongformChapterTransitionReceipt,
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
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story_session_service import StorySessionService


CHAPTER_BRIDGE_PAYLOAD_VERSION = "longform-chapter-bridge.v1"
CHAPTER_TRANSITION_PAYLOAD_VERSION = "longform-chapter-transition.v1"
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

    def prepare_chapter_transition(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        session: StorySession,
        chapter: ChapterWorkspace,
    ) -> PreparedChapterTransition:
        if identity is None:
            return PreparedChapterTransition(chapter=chapter, bridge=None, receipt=None)

        updated_chapter = chapter
        adopted_output_ref: str | None = None
        adopted_output_text: str | None = None
        adoption_source = "empty_chapter_adapter"
        source_refs: list[str] = []
        pending_artifact = self._pending_segment_artifact(chapter=chapter)
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
            self._supersede_other_draft_segments(
                chapter_workspace_id=chapter.chapter_workspace_id,
                accepted_artifact_id=acceptance_artifact.artifact_id,
            )
            updated_chapter = self._story_session_service.update_chapter_workspace(
                chapter_workspace_id=chapter.chapter_workspace_id,
                accepted_segment_ids=[
                    *chapter.accepted_segment_ids,
                    *(
                        []
                        if acceptance_artifact.artifact_id in chapter.accepted_segment_ids
                        else [acceptance_artifact.artifact_id]
                    ),
                ],
                pending_segment_artifact_id=None,
            )
            adoption_source = "draft_adoption_receipt"
            source_refs = [
                adoption.receipt_id,
                adoption.adopted_output_ref,
                acceptance_artifact.artifact_id,
            ]
        else:
            latest_accepted = self._latest_accepted_segment(chapter=chapter)
            if latest_accepted is not None:
                adopted_output_ref = latest_accepted.artifact_id
                adopted_output_text = latest_accepted.content_text
                adoption_source = "accepted_segment_adapter"
                source_refs = [latest_accepted.artifact_id]

        accepted_outline_ref = _artifact_ref_from_outline(updated_chapter)
        chapter_goal_ref = _chapter_goal_ref(updated_chapter)
        bridge = self._chapter_bridge_provider.build_bridge_material(
            identity=identity,
            from_chapter_index=updated_chapter.chapter_index,
            to_chapter_index=updated_chapter.chapter_index + 1,
            adopted_output_ref=adopted_output_ref,
            accepted_outline_ref=accepted_outline_ref,
            chapter_goal_ref=chapter_goal_ref,
            adopted_output_text=adopted_output_text,
            source_refs=source_refs,
            metadata_json={
                "payload_version": CHAPTER_BRIDGE_PAYLOAD_VERSION,
                "bridge_source": adoption_source,
                "chapter_goal": updated_chapter.chapter_goal,
                "accepted_outline_present": accepted_outline_ref is not None,
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
        )
        bridge_material_id = self._record_bridge_material(
            identity=identity,
            bridge=bridge,
            source_refs=source_refs,
        )
        receipt = LongformChapterTransitionReceipt(
            receipt_id=f"chapter_transition_{uuid4().hex}",
            identity=identity,
            from_chapter_index=updated_chapter.chapter_index,
            to_chapter_index=updated_chapter.chapter_index + 1,
            adopted_output_ref=adopted_output_ref,
            bridge_material_ref=bridge_material_id,
            status="prepared",
            metadata_json={
                "payload_version": CHAPTER_TRANSITION_PAYLOAD_VERSION,
                "bridge_source": adoption_source,
                "chapter_workspace_id": updated_chapter.chapter_workspace_id,
                "accepted_outline_ref": accepted_outline_ref,
                "chapter_goal_ref": chapter_goal_ref,
                "runtime_truth_owner": "rp_runtime",
                "canonical_truth": False,
            },
            created_at=_utcnow(),
        )
        self._record_transition_receipt(
            identity=identity,
            receipt=receipt,
            source_refs=[
                *source_refs,
                bridge_material_id,
            ],
        )
        return PreparedChapterTransition(
            chapter=updated_chapter,
            bridge=bridge,
            receipt=receipt,
        )

    def get_latest_bridge_material_for_branch(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        source_chapter_index: int,
    ) -> ChapterBridgeMaterial | None:
        records = self._list_branch_material_records(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            payload_kind="chapter_bridge_material",
        )
        matches = [
            ChapterBridgeMaterial.model_validate(record.payload_json.get("record"))
            for record in records
            if (
                isinstance(record.payload_json.get("record"), dict)
                and record.payload_json.get("record", {}).get("source_chapter_index")
                == source_chapter_index
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
    ) -> tuple[str, ChapterBridgeMaterial] | None:
        records = self._list_branch_material_records(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            payload_kind="chapter_bridge_material",
        )
        matches: list[tuple[RuntimeWorkspaceMaterialRecord, ChapterBridgeMaterial]] = []
        for record in records:
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

    def _pending_segment_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
    ) -> StoryArtifact | None:
        artifact_id = str(chapter.pending_segment_artifact_id or "").strip()
        if not artifact_id:
            return None
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            return None
        if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
            return None
        if artifact.status != StoryArtifactStatus.DRAFT:
            return None
        return artifact

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
    ) -> StoryArtifact | None:
        accepted = [
            artifact
            for artifact in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and artifact.status == StoryArtifactStatus.ACCEPTED
        ]
        if not accepted:
            return None
        return max(
            accepted,
            key=lambda artifact: (
                artifact.created_at,
                artifact.updated_at,
                artifact.artifact_id,
            ),
        )

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
            .order_by(RuntimeWorkspaceMaterialRecord.created_at.asc())
            .order_by(RuntimeWorkspaceMaterialRecord.material_id.asc())
        )
        records = list(self._session.exec(stmt).all())
        return [
            record
            for record in records
            if record.payload_json.get("payload_kind") == payload_kind
        ]


def _artifact_ref_from_outline(chapter: ChapterWorkspace) -> str | None:
    accepted_outline = chapter.accepted_outline_json or {}
    artifact_id = str(accepted_outline.get("artifact_id") or "").strip()
    return artifact_id or None


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
