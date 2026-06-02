"""Helpers for seeding story segments that product branch reads can see."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from models.rp_story_store import BranchHeadRecord
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime.identity import (
    BranchHeadStatus,
    BranchVisibilityState,
    StoryTurnStatus,
)
from rp.models.story.runtime import (
    ChapterWorkspace,
    LongformChapterPhase,
    LongformTurnCommandKind,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySession,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService


def seed_runtime_visible_story_segment(
    retrieval_session,
    story_session_service: StorySessionService,
    *,
    session: StorySession,
    chapter: ChapterWorkspace,
    branch_head_id: str,
    scene_ref: str | None,
    content_text: str,
    status: StoryArtifactStatus,
    command_kind: LongformTurnCommandKind = LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
    revision: int = 1,
    metadata: Mapping[str, Any] | None = None,
    set_pending_on_chapter: bool = False,
    created_from: str = "test.runtime_visible_segment.seed",
    actor: str = "test.runtime_visible_segment.seed",
) -> tuple[StoryArtifact, MemoryRuntimeIdentity, StoryRuntimeIdentityService]:
    """Create a branch-visible segment through the runtime identity services.

    Story snapshots intentionally hide `story_segment` artifacts unless they carry
    canonical runtime ownership metadata that matches a real visible turn. This
    helper keeps tests on that product path: it ensures a real branch row exists,
    pins a runtime profile snapshot, asks `StoryRuntimeIdentityService` to create
    the turn, writes the artifact with canonical runtime metadata, then binds the
    turn output refs using the status expected by product visibility predicates.
    """

    normalized_branch_head_id = str(branch_head_id or "").strip()
    if not normalized_branch_head_id:
        raise ValueError("branch_head_id must be explicit for visible segment seeds")

    _ensure_active_test_branch(
        retrieval_session,
        story_session_service,
        session=session,
        branch_head_id=normalized_branch_head_id,
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from=created_from,
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=command_kind.value,
        actor=actor,
        requested_branch_head_id=normalized_branch_head_id,
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=status,
        content_text=content_text,
        metadata={
            **dict(metadata or {}),
            "command_kind": command_kind.value,
            "runtime_story_id": identity.story_id,
            "runtime_session_id": identity.session_id,
            "runtime_branch_head_id": identity.branch_head_id,
            "runtime_turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
        },
        revision=revision,
        scene_ref=scene_ref,
    )
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=_turn_status_for_artifact_status(status),
        visible_output_ref=artifact.artifact_id,
        selected_output_ref=artifact.artifact_id,
        settlement_reason=(
            "test_runtime_visible_story_segment"
            if status == StoryArtifactStatus.ACCEPTED
            else None
        ),
    )
    if set_pending_on_chapter:
        story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=LongformChapterPhase.SEGMENT_REVIEW,
            pending_segment_artifact_id=artifact.artifact_id,
        )
    return artifact, identity, identity_service


def _turn_status_for_artifact_status(status: StoryArtifactStatus) -> StoryTurnStatus:
    if status == StoryArtifactStatus.ACCEPTED:
        return StoryTurnStatus.SETTLED
    return StoryTurnStatus.POST_WRITE_PENDING


def _ensure_active_test_branch(
    retrieval_session,
    story_session_service: StorySessionService,
    *,
    session: StorySession,
    branch_head_id: str,
) -> BranchHeadRecord:
    branch = retrieval_session.get(BranchHeadRecord, branch_head_id)
    if branch is None:
        now = datetime.now(timezone.utc)
        branch = BranchHeadRecord(
            branch_head_id=branch_head_id,
            story_id=session.story_id,
            session_id=session.session_id,
            branch_name=branch_head_id,
            parent_branch_head_id=None,
            forked_from_turn_id=None,
            fork_origin_turn_id=None,
            fork_base_turn_id=None,
            head_turn_id=None,
            last_settled_turn_id=None,
            status=BranchHeadStatus.ACTIVE.value,
            visibility_scope="active_lineage",
            visibility_state=BranchVisibilityState.VISIBLE.value,
            metadata_json={"seed_source": "runtime_visible_segment_test_helper"},
            created_at=now,
            updated_at=now,
        )
        retrieval_session.add(branch)
        retrieval_session.flush()
    elif branch.session_id != session.session_id or branch.story_id != session.story_id:
        raise ValueError(f"branch does not belong to test session: {branch_head_id}")

    story_session_service.update_session(
        session_id=session.session_id,
        active_branch_head_id=branch.branch_head_id,
    )
    return branch

