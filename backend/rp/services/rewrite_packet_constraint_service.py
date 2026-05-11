"""Assemble fail-closed rewrite packet constraints from active review sidecars."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.story_runtime import (
    ChapterWorkspace,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySession,
)

from .revision_overlay_service import RevisionOverlayService
from .rewrite_request_builder_service import RewriteRequestBuilderService
from .story_session_service import StorySessionService


class RewritePacketConstraintServiceError(ValueError):
    """Stable rewrite constraint error for real rewrite packet assembly."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class RewritePacketConstraintResult:
    """Resolved writer-visible rewrite constraints for a target pending draft."""

    target_artifact_id: str
    draft_ref: str
    source_identity: MemoryRuntimeIdentity
    review_overlay_sections: list[dict[str, object]]
    active_comment_refs: list[str]
    active_tracked_change_refs: list[str]
    rewrite_scope: str = "full"


class RewritePacketConstraintService:
    """Read active review overlay state and map it into writer packet sections."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        revision_overlay_service: RevisionOverlayService | None = None,
        rewrite_request_builder_service: RewriteRequestBuilderService | None = None,
        session: Session | None = None,
    ) -> None:
        shared_overlay_service = revision_overlay_service or RevisionOverlayService(
            session=session
        )
        self._story_session_service = story_session_service
        self._revision_overlay_service = shared_overlay_service
        self._rewrite_request_builder_service = (
            rewrite_request_builder_service
            if rewrite_request_builder_service is not None
            else RewriteRequestBuilderService(
                revision_overlay_service=shared_overlay_service,
            )
        )

    def build_review_overlay_sections(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session: StorySession,
        chapter: ChapterWorkspace,
        target_artifact_id: str | None,
    ) -> RewritePacketConstraintResult:
        target_artifact = self._require_target_artifact(
            session=session,
            chapter=chapter,
            target_artifact_id=target_artifact_id,
        )
        source_identity = self._resolve_target_identity(
            identity=identity,
            target_artifact=target_artifact,
        )
        draft_ref = f"artifact:{target_artifact.artifact_id}"
        overlay = self._revision_overlay_service.find_overlay_for_draft_ref(
            identity=source_identity,
            draft_ref=draft_ref,
        )
        if overlay is None:
            return RewritePacketConstraintResult(
                target_artifact_id=target_artifact.artifact_id,
                draft_ref=draft_ref,
                source_identity=source_identity,
                review_overlay_sections=[],
                active_comment_refs=[],
                active_tracked_change_refs=[],
            )
        inspection = self._revision_overlay_service.inspect_overlay(
            identity=source_identity,
            overlay_id=overlay.overlay_id,
        )
        active_comment_refs = list(inspection.active_comment_refs)
        active_tracked_change_refs = list(inspection.active_tracked_change_refs)
        if not active_comment_refs and not active_tracked_change_refs:
            return RewritePacketConstraintResult(
                target_artifact_id=target_artifact.artifact_id,
                draft_ref=draft_ref,
                source_identity=source_identity,
                review_overlay_sections=[],
                active_comment_refs=[],
                active_tracked_change_refs=[],
            )
        rewrite_request = self._rewrite_request_builder_service.build_full_rewrite_request(
            identity=source_identity,
            draft_ref=draft_ref,
            global_instruction=None,
            comment_refs=active_comment_refs,
            tracked_change_refs=active_tracked_change_refs,
        )
        sections = self._rewrite_request_builder_service.build_review_overlay_sections(
            identity=source_identity,
            rewrite_request=rewrite_request,
        )
        return RewritePacketConstraintResult(
            target_artifact_id=target_artifact.artifact_id,
            draft_ref=draft_ref,
            source_identity=source_identity,
            review_overlay_sections=sections,
            active_comment_refs=active_comment_refs,
            active_tracked_change_refs=active_tracked_change_refs,
            rewrite_scope=rewrite_request.rewrite_scope,
        )

    def _require_target_artifact(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        target_artifact_id: str | None,
    ) -> StoryArtifact:
        artifact_id = str(
            target_artifact_id or chapter.pending_segment_artifact_id or ""
        ).strip()
        if not artifact_id:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_target_artifact_required",
                session.session_id,
            )
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_target_artifact_not_found",
                artifact_id,
            )
        if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_target_artifact_kind_invalid",
                artifact_id,
            )
        if artifact.status != StoryArtifactStatus.DRAFT:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_target_artifact_not_draft",
                artifact_id,
            )
        return artifact

    @staticmethod
    def _resolve_target_identity(
        *,
        identity: MemoryRuntimeIdentity,
        target_artifact: StoryArtifact,
    ) -> MemoryRuntimeIdentity:
        metadata = dict(target_artifact.metadata or {})
        source_identity = MemoryRuntimeIdentity(
            story_id=_require_metadata_text(
                metadata,
                field_name="runtime_story_id",
                artifact_id=target_artifact.artifact_id,
            ),
            session_id=_require_metadata_text(
                metadata,
                field_name="runtime_session_id",
                artifact_id=target_artifact.artifact_id,
            ),
            branch_head_id=_require_metadata_text(
                metadata,
                field_name="runtime_branch_head_id",
                artifact_id=target_artifact.artifact_id,
            ),
            turn_id=_require_metadata_text(
                metadata,
                field_name="runtime_turn_id",
                artifact_id=target_artifact.artifact_id,
            ),
            runtime_profile_snapshot_id=_require_metadata_text(
                metadata,
                field_name="runtime_profile_snapshot_id",
                artifact_id=target_artifact.artifact_id,
            ),
        )
        if source_identity.story_id != identity.story_id:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_story_mismatch",
                target_artifact.artifact_id,
            )
        if source_identity.session_id != identity.session_id:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_session_mismatch",
                target_artifact.artifact_id,
            )
        if source_identity.branch_head_id != identity.branch_head_id:
            raise RewritePacketConstraintServiceError(
                "rewrite_constraint_branch_mismatch",
                target_artifact.artifact_id,
            )
        return source_identity


def _require_metadata_text(
    metadata: dict[str, object],
    *,
    field_name: str,
    artifact_id: str,
) -> str:
    normalized = str(metadata.get(field_name) or "").strip()
    if normalized:
        return normalized
    raise RewritePacketConstraintServiceError(
        "rewrite_constraint_source_identity_missing",
        f"{artifact_id}:{field_name}",
    )
