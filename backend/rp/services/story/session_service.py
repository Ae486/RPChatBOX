"""Persistence service for active-story runtime state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from sqlalchemy import asc, desc
from sqlmodel import Session, select

from models.rp_story_store import (
    BranchHeadRecord,
    ChapterWorkspaceRecord,
    StoryArtifactRecord,
    StoryDiscussionEntryRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.story_runtime import (
    ChapterWorkspace,
    ChapterWorkspaceSnapshot,
    LongformChapterPhase,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StoryDiscussionEntry,
    StorySession,
    StorySessionState,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_scene_ref(*, chapter_index: int, scene_index: int) -> str:
    return f"chapter:{chapter_index}:scene:{scene_index}"


_UNSET = object()


class StorySessionService:
    """Database-backed true source for longform active-story MVP."""

    _HIDDEN_TURN_VISIBILITY_STATES = {
        "hidden",
        "invalidated",
        "hidden_by_rollback",
        "discarded",
        "deleted",
    }
    _STORY_SEGMENT_TURN_COMMAND_KINDS = {
        "write_next_segment",
        "rewrite_pending_segment",
    }

    def __init__(self, session: Session):
        self._session = session

    def list_sessions(self) -> list[StorySession]:
        stmt = select(StorySessionRecord).order_by(desc(StorySessionRecord.updated_at))
        return [
            self._record_to_story_session(record)
            for record in self._session.exec(stmt).all()
        ]

    def commit(self) -> None:
        self._session.commit()

    def get_session(self, session_id: str) -> StorySession | None:
        record = self._session.get(StorySessionRecord, session_id)
        return self._record_to_story_session(record) if record is not None else None

    def get_latest_session_for_story(
        self,
        story_id: str,
        *,
        session_state: StorySessionState | None = StorySessionState.ACTIVE,
    ) -> StorySession | None:
        stmt = select(StorySessionRecord).where(StorySessionRecord.story_id == story_id)
        if session_state is not None:
            stmt = stmt.where(StorySessionRecord.session_state == session_state.value)
        stmt = stmt.order_by(
            desc(StorySessionRecord.updated_at),
            desc(StorySessionRecord.created_at),
        )
        record = self._session.exec(stmt).first()
        return self._record_to_story_session(record) if record is not None else None

    def create_session(
        self,
        *,
        story_id: str,
        source_workspace_id: str,
        mode: str,
        runtime_story_config: dict,
        writer_contract: dict,
        current_state_json: dict,
        initial_phase: LongformChapterPhase,
    ) -> StorySession:
        now = _utcnow()
        session_id = uuid4().hex
        record = StorySessionRecord(
            session_id=session_id,
            story_id=story_id,
            source_workspace_id=source_workspace_id,
            mode=mode,
            session_state=StorySessionState.ACTIVE.value,
            active_branch_head_id=f"branch:{session_id}:main",
            active_runtime_profile_snapshot_id=None,
            current_chapter_index=1,
            current_phase=initial_phase.value,
            runtime_story_config_json=dict(runtime_story_config),
            writer_contract_json=dict(writer_contract),
            current_state_json=dict(current_state_json),
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_story_session(record)

    def update_session(
        self,
        *,
        session_id: str,
        session_state: StorySessionState | None = None,
        current_chapter_index: int | None = None,
        current_phase: LongformChapterPhase | None = None,
        runtime_story_config_patch: dict | None = None,
        current_state_json: dict | None = None,
        active_branch_head_id: str | None | object = _UNSET,
        active_runtime_profile_snapshot_id: str | None | object = _UNSET,
    ) -> StorySession:
        record = self._require_session_record(session_id)
        if session_state is not None:
            record.session_state = session_state.value
        if current_chapter_index is not None:
            record.current_chapter_index = current_chapter_index
        if current_phase is not None:
            record.current_phase = current_phase.value
        if runtime_story_config_patch is not None:
            next_runtime_story_config = dict(record.runtime_story_config_json or {})
            next_runtime_story_config.update(dict(runtime_story_config_patch))
            record.runtime_story_config_json = next_runtime_story_config
        if current_state_json is not None:
            record.current_state_json = dict(current_state_json)
        if active_branch_head_id is not _UNSET:
            record.active_branch_head_id = cast(str | None, active_branch_head_id)
        if active_runtime_profile_snapshot_id is not _UNSET:
            record.active_runtime_profile_snapshot_id = cast(
                str | None,
                active_runtime_profile_snapshot_id,
            )
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._record_to_story_session(record)

    def get_current_chapter(self, session_id: str) -> ChapterWorkspace | None:
        session = self._require_session_record(session_id)
        return self.get_chapter_by_index(
            session_id=session_id, chapter_index=session.current_chapter_index
        )

    def get_active_branch_current_chapter(
        self,
        session_id: str,
    ) -> ChapterWorkspace | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        return self.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=session.current_chapter_index,
        ).chapter

    def get_current_chapter_for_story(self, story_id: str) -> ChapterWorkspace | None:
        session = self.get_latest_session_for_story(story_id)
        if session is None:
            return None
        return self.get_current_chapter(session.session_id)

    def get_chapter_by_index(
        self,
        *,
        session_id: str,
        chapter_index: int,
    ) -> ChapterWorkspace | None:
        stmt = (
            select(ChapterWorkspaceRecord)
            .where(ChapterWorkspaceRecord.session_id == session_id)
            .where(ChapterWorkspaceRecord.chapter_index == chapter_index)
        )
        record = self._session.exec(stmt).first()
        return self._record_to_chapter(record) if record is not None else None

    def get_chapter_workspace(
        self, chapter_workspace_id: str
    ) -> ChapterWorkspace | None:
        record = self._session.get(ChapterWorkspaceRecord, chapter_workspace_id)
        return self._record_to_chapter(record) if record is not None else None

    def list_chapter_workspaces(self, *, session_id: str) -> list[ChapterWorkspace]:
        stmt = (
            select(ChapterWorkspaceRecord)
            .where(ChapterWorkspaceRecord.session_id == session_id)
            .order_by(asc(ChapterWorkspaceRecord.chapter_index))
        )
        return [
            self._record_to_chapter(record) for record in self._session.exec(stmt).all()
        ]

    def create_chapter_workspace(
        self,
        *,
        session_id: str,
        chapter_index: int,
        phase: LongformChapterPhase,
        chapter_goal: str | None = None,
        builder_snapshot_json: dict | None = None,
    ) -> ChapterWorkspace:
        now = _utcnow()
        record = ChapterWorkspaceRecord(
            chapter_workspace_id=uuid4().hex,
            session_id=session_id,
            chapter_index=chapter_index,
            phase=phase.value,
            chapter_goal=chapter_goal,
            outline_draft_json=None,
            accepted_outline_json=None,
            builder_snapshot_json=dict(builder_snapshot_json or {}),
            review_notes_json=[],
            accepted_segment_ids_json=[],
            pending_segment_artifact_id=None,
            current_scene_ref=_build_scene_ref(
                chapter_index=chapter_index,
                scene_index=1,
            ),
            next_scene_index=2,
            last_closed_scene_ref=None,
            closed_scene_refs_json=[],
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_chapter(record)

    def update_chapter_workspace(
        self,
        *,
        chapter_workspace_id: str,
        phase: LongformChapterPhase | None = None,
        chapter_goal: str | None = None,
        outline_draft_json: dict | None = None,
        accepted_outline_json: dict | None = None,
        builder_snapshot_json: dict | None = None,
        review_notes: list[str] | None = None,
        accepted_segment_ids: list[str] | None = None,
        pending_segment_artifact_id: str | None | object = _UNSET,
        current_scene_ref: str | None | object = _UNSET,
        next_scene_index: int | None = None,
        last_closed_scene_ref: str | None | object = _UNSET,
        closed_scene_refs: list[str] | None = None,
    ) -> ChapterWorkspace:
        record = self._require_chapter_record(chapter_workspace_id)
        if phase is not None:
            record.phase = phase.value
        if chapter_goal is not None:
            record.chapter_goal = chapter_goal
        if outline_draft_json is not None:
            record.outline_draft_json = dict(outline_draft_json)
        if accepted_outline_json is not None:
            record.accepted_outline_json = dict(accepted_outline_json)
        if builder_snapshot_json is not None:
            record.builder_snapshot_json = dict(builder_snapshot_json)
        if review_notes is not None:
            record.review_notes_json = list(review_notes)
        if accepted_segment_ids is not None:
            record.accepted_segment_ids_json = list(accepted_segment_ids)
        if pending_segment_artifact_id is not _UNSET:
            record.pending_segment_artifact_id = cast(
                str | None, pending_segment_artifact_id
            )
        if current_scene_ref is not _UNSET:
            record.current_scene_ref = cast(str | None, current_scene_ref)
        if next_scene_index is not None:
            record.next_scene_index = next_scene_index
        if last_closed_scene_ref is not _UNSET:
            record.last_closed_scene_ref = cast(str | None, last_closed_scene_ref)
        if closed_scene_refs is not None:
            record.closed_scene_refs_json = list(closed_scene_refs)
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._record_to_chapter(record)

    def create_artifact(
        self,
        *,
        session_id: str,
        chapter_workspace_id: str,
        artifact_kind: StoryArtifactKind,
        status: StoryArtifactStatus,
        content_text: str,
        metadata: dict | None = None,
        revision: int = 1,
        scene_ref: str | None | object = _UNSET,
    ) -> StoryArtifact:
        now = _utcnow()
        resolved_scene_ref: str | None
        if scene_ref is _UNSET:
            resolved_scene_ref = None
            if artifact_kind == StoryArtifactKind.STORY_SEGMENT:
                chapter_record = self._require_chapter_record(chapter_workspace_id)
                resolved_scene_ref = chapter_record.current_scene_ref
        else:
            resolved_scene_ref = cast(str | None, scene_ref)
        record = StoryArtifactRecord(
            artifact_id=uuid4().hex,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            artifact_kind=artifact_kind.value,
            status=status.value,
            revision=revision,
            content_text=content_text,
            metadata_json=dict(metadata or {}),
            scene_ref=resolved_scene_ref,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_artifact(record)

    def get_artifact(self, artifact_id: str) -> StoryArtifact | None:
        record = self._session.get(StoryArtifactRecord, artifact_id)
        return self._record_to_artifact(record) if record is not None else None

    def list_artifacts(self, *, chapter_workspace_id: str) -> list[StoryArtifact]:
        stmt = (
            select(StoryArtifactRecord)
            .where(StoryArtifactRecord.chapter_workspace_id == chapter_workspace_id)
            .order_by(asc(StoryArtifactRecord.created_at))
        )
        return [
            self._record_to_artifact(record)
            for record in self._session.exec(stmt).all()
        ]

    def update_artifact(
        self,
        *,
        artifact_id: str,
        status: StoryArtifactStatus | None = None,
        content_text: str | None = None,
        metadata: dict | None = None,
        revision: int | None = None,
    ) -> StoryArtifact:
        record = self._require_artifact_record(artifact_id)
        if status is not None:
            record.status = status.value
        if content_text is not None:
            record.content_text = content_text
        if metadata is not None:
            record.metadata_json = dict(metadata)
        if revision is not None:
            record.revision = revision
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._record_to_artifact(record)

    def create_discussion_entry(
        self,
        *,
        session_id: str,
        chapter_workspace_id: str,
        role: str,
        content_text: str,
        linked_artifact_id: str | None = None,
        scene_ref: str | None | object = _UNSET,
    ) -> StoryDiscussionEntry:
        resolved_scene_ref: str | None
        if scene_ref is _UNSET:
            chapter_record = self._require_chapter_record(chapter_workspace_id)
            resolved_scene_ref = chapter_record.current_scene_ref
        else:
            resolved_scene_ref = cast(str | None, scene_ref)
        record = StoryDiscussionEntryRecord(
            entry_id=uuid4().hex,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            role=role,
            content_text=content_text,
            linked_artifact_id=linked_artifact_id,
            scene_ref=resolved_scene_ref,
            created_at=_utcnow(),
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_discussion_entry(record)

    def close_current_scene(self, *, session_id: str) -> ChapterWorkspace:
        record = self._require_current_chapter_record(session_id)
        current_scene_ref = (record.current_scene_ref or "").strip()
        if not current_scene_ref:
            raise ValueError(f"No current scene to close: {session_id}")
        closed_scene_refs = list(record.closed_scene_refs_json or [])
        if current_scene_ref not in closed_scene_refs:
            closed_scene_refs.append(current_scene_ref)
        next_scene_index = int(record.next_scene_index or 2)
        if next_scene_index < 1:
            next_scene_index = 1
        record.closed_scene_refs_json = closed_scene_refs
        record.last_closed_scene_ref = current_scene_ref
        record.current_scene_ref = _build_scene_ref(
            chapter_index=record.chapter_index,
            scene_index=next_scene_index,
        )
        record.next_scene_index = next_scene_index + 1
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._record_to_chapter(record)

    def list_discussion_entries(
        self, *, chapter_workspace_id: str
    ) -> list[StoryDiscussionEntry]:
        stmt = (
            select(StoryDiscussionEntryRecord)
            .where(
                StoryDiscussionEntryRecord.chapter_workspace_id == chapter_workspace_id
            )
            .order_by(asc(StoryDiscussionEntryRecord.created_at))
        )
        return [
            self._record_to_discussion_entry(record)
            for record in self._session.exec(stmt).all()
        ]

    def build_chapter_snapshot(
        self,
        *,
        session_id: str,
        chapter_index: int,
    ) -> ChapterWorkspaceSnapshot:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        chapter = self.get_chapter_by_index(
            session_id=session_id, chapter_index=chapter_index
        )
        if chapter is None:
            raise ValueError(
                f"ChapterWorkspace not found: session={session_id} chapter={chapter_index}"
            )
        artifacts = self.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        discussion_entries = self.list_discussion_entries(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        (
            artifacts,
            discussion_entries,
            hidden_artifact_ids,
        ) = self._filter_active_branch_snapshot_items(
            session_record=self._require_session_record(session_id),
            artifacts=artifacts,
            discussion_entries=discussion_entries,
        )
        visible_accepted_segment_ids = [
            artifact.artifact_id
            for artifact in self.active_branch_accepted_segment_artifacts(
                session_id=session_id,
                chapter_index=chapter_index,
                chapter=chapter,
                artifacts=artifacts,
                session_record=session,
            )
        ]
        pending_hidden = chapter.pending_segment_artifact_id in hidden_artifact_ids
        effective_phase = self._active_branch_effective_phase(
            chapter=chapter,
            pending_hidden=pending_hidden,
        )
        chapter_updates: dict[str, object] = {
            "accepted_segment_ids": visible_accepted_segment_ids,
        }
        if pending_hidden:
            chapter_updates["pending_segment_artifact_id"] = None
        if effective_phase != chapter.phase:
            chapter_updates["phase"] = effective_phase
        chapter = chapter.model_copy(update=chapter_updates)
        if (
            chapter_index == session.current_chapter_index
            and session.current_phase != effective_phase
        ):
            session = session.model_copy(update={"current_phase": effective_phase})
        return ChapterWorkspaceSnapshot(
            session=session,
            chapter=chapter,
            artifacts=artifacts,
            discussion_entries=discussion_entries,
        )

    @staticmethod
    def _active_branch_effective_phase(
        *,
        chapter: ChapterWorkspace,
        pending_hidden: bool,
    ) -> LongformChapterPhase:
        if not pending_hidden:
            return chapter.phase
        if (
            chapter.phase == LongformChapterPhase.SEGMENT_REVIEW
            and chapter.accepted_outline_json is not None
        ):
            return LongformChapterPhase.SEGMENT_DRAFTING
        return chapter.phase

    def _filter_active_branch_snapshot_items(
        self,
        *,
        session_record: StorySessionRecord,
        artifacts: list[StoryArtifact],
        discussion_entries: list[StoryDiscussionEntry],
    ) -> tuple[list[StoryArtifact], list[StoryDiscussionEntry], set[str]]:
        visible_turns = {
            turn.turn_id: turn
            for turn in self._active_branch_visible_turn_records(
                session_record=session_record
            )
        }
        visible_artifacts: list[StoryArtifact] = []
        hidden_artifact_ids: set[str] = set()
        for artifact in artifacts:
            if self._artifact_visible_in_active_branch(
                artifact=artifact,
                visible_turns=visible_turns,
            ):
                visible_artifacts.append(artifact)
                continue
            hidden_artifact_ids.add(artifact.artifact_id)

        visible_discussion_entries = [
            entry
            for entry in discussion_entries
            if not (
                entry.linked_artifact_id is not None
                and entry.linked_artifact_id in hidden_artifact_ids
            )
        ]
        return visible_artifacts, visible_discussion_entries, hidden_artifact_ids

    def active_branch_accepted_story_segments(
        self,
        *,
        session_id: str,
        chapter_index: int,
        chapter: ChapterWorkspace | None = None,
        artifacts: list[StoryArtifact] | None = None,
        session_record: StorySession | StorySessionRecord | None = None,
    ) -> list[StoryArtifact]:
        resolved_chapter = chapter or self.get_chapter_by_index(
            session_id=session_id,
            chapter_index=chapter_index,
        )
        if resolved_chapter is None:
            return []
        resolved_artifacts = artifacts
        resolved_session_record = self._coerce_session_record(
            session_id=session_id,
            session=session_record,
        )
        if resolved_artifacts is None:
            all_artifacts = self.list_artifacts(
                chapter_workspace_id=resolved_chapter.chapter_workspace_id
            )
            resolved_artifacts, _, _ = self._filter_active_branch_snapshot_items(
                session_record=resolved_session_record,
                artifacts=all_artifacts,
                discussion_entries=[],
            )
        artifact_by_id = {artifact.artifact_id: artifact for artifact in resolved_artifacts}
        accepted_segments: list[StoryArtifact] = []
        for turn in self._active_branch_visible_turn_records(
            session_record=resolved_session_record
        ):
            if turn.status != "settled":
                continue
            if (
                str(turn.command_kind or "").strip()
                not in self._STORY_SEGMENT_TURN_COMMAND_KINDS
            ):
                continue
            for artifact_id in self._turn_output_artifact_ids(turn):
                artifact = artifact_by_id.get(artifact_id)
                if artifact is None:
                    continue
                if artifact.chapter_workspace_id != resolved_chapter.chapter_workspace_id:
                    continue
                if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
                    continue
                if artifact.status != StoryArtifactStatus.ACCEPTED:
                    continue
                if not self._story_segment_artifact_matches_turn(
                    artifact=artifact,
                    turn=turn,
                ):
                    continue
                accepted_segments.append(artifact)
                break
        return accepted_segments

    def active_branch_accepted_segment_artifacts(
        self,
        *,
        session_id: str,
        chapter_index: int,
        chapter: ChapterWorkspace | None = None,
        artifacts: list[StoryArtifact] | None = None,
        session_record: StorySession | StorySessionRecord | None = None,
    ) -> list[StoryArtifact]:
        return self.active_branch_accepted_story_segments(
            session_id=session_id,
            chapter_index=chapter_index,
            chapter=chapter,
            artifacts=artifacts,
            session_record=session_record,
        )

    def _artifact_visible_in_active_branch(
        self,
        *,
        artifact: StoryArtifact,
        visible_turns: dict[str, StoryTurnRecord],
    ) -> bool:
        if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT:
            turn_id = self._artifact_runtime_turn_id(artifact)
            branch_head_id = self._artifact_runtime_branch_head_id(artifact)
            if turn_id is None or branch_head_id is None:
                return False
            turn = visible_turns.get(turn_id)
            return (
                turn is not None
                and turn.branch_head_id == branch_head_id
                and self._story_segment_artifact_matches_turn(
                    artifact=artifact,
                    turn=turn,
                    require_output_ref=False,
                )
            )

        turn_id = self._artifact_runtime_turn_id(artifact)
        if turn_id is None:
            return True
        turn = visible_turns.get(turn_id)
        if turn is None:
            return False
        branch_head_id = self._artifact_runtime_branch_head_id(artifact)
        return branch_head_id is None or branch_head_id == turn.branch_head_id

    def _active_branch_visible_turn_ids(
        self,
        *,
        session_record: StorySessionRecord,
    ) -> set[str]:
        return {
            turn.turn_id
            for turn in self._active_branch_visible_turn_records(
                session_record=session_record
            )
        }

    def _active_branch_visible_turn_id_order(
        self,
        *,
        session_record: StorySessionRecord,
    ) -> list[str]:
        return [
            turn.turn_id
            for turn in self._active_branch_visible_turn_records(
                session_record=session_record
            )
        ]

    def _active_branch_visible_turn_records(
        self,
        *,
        session_record: StorySessionRecord,
    ) -> list[StoryTurnRecord]:
        branch_id = str(session_record.active_branch_head_id or "").strip()
        if not branch_id:
            return []
        cutoff_turn_id: str | None = None
        seen_branch_ids: set[str] = set()
        branch_cutoffs: list[tuple[str, str | None]] = []
        branch = self._session.get(BranchHeadRecord, branch_id)
        while branch is not None and branch.branch_head_id not in seen_branch_ids:
            seen_branch_ids.add(branch.branch_head_id)
            branch_cutoff = cutoff_turn_id or branch.head_turn_id
            branch_cutoffs.append((branch.branch_head_id, branch_cutoff))
            cutoff_turn_id = branch.forked_from_turn_id
            parent_branch_id = str(branch.parent_branch_head_id or "").strip()
            branch = (
                self._session.get(BranchHeadRecord, parent_branch_id)
                if parent_branch_id
                else None
            )
        visible_turns: list[StoryTurnRecord] = []
        seen_turn_ids: set[str] = set()
        for branch_head_id, cutoff in reversed(branch_cutoffs):
            for turn in self._visible_turns_through_cutoff(
                session_id=session_record.session_id,
                branch_head_id=branch_head_id,
                cutoff_turn_id=cutoff,
            ):
                turn_id = turn.turn_id
                if turn_id in seen_turn_ids:
                    continue
                seen_turn_ids.add(turn_id)
                visible_turns.append(turn)
        return visible_turns

    def _visible_turns_through_cutoff(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        cutoff_turn_id: str | None,
    ) -> list[StoryTurnRecord]:
        normalized_cutoff = str(cutoff_turn_id or "").strip()
        if not normalized_cutoff:
            return []
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == session_id)
            .where(StoryTurnRecord.branch_head_id == branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        visible_turns: list[StoryTurnRecord] = []
        for turn in self._session.exec(stmt).all():
            if (
                str(turn.visibility_state or "").strip()
                not in self._HIDDEN_TURN_VISIBILITY_STATES
            ):
                visible_turns.append(turn)
            if turn.turn_id == normalized_cutoff:
                break
        return visible_turns

    @staticmethod
    def _artifact_runtime_turn_id(artifact: StoryArtifact) -> str | None:
        metadata = dict(artifact.metadata or {})
        turn_id = str(metadata.get("runtime_turn_id") or "").strip()
        return turn_id or None

    @staticmethod
    def _artifact_runtime_branch_head_id(artifact: StoryArtifact) -> str | None:
        metadata = dict(artifact.metadata or {})
        branch_head_id = str(metadata.get("runtime_branch_head_id") or "").strip()
        return branch_head_id or None

    @staticmethod
    def _turn_output_artifact_ids(turn: StoryTurnRecord) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for output_ref in (turn.selected_output_ref, turn.visible_output_ref):
            normalized = str(output_ref or "").strip()
            if not normalized:
                continue
            candidates = [normalized]
            if normalized.startswith("artifact:"):
                stripped = normalized.removeprefix("artifact:").strip()
                if stripped:
                    candidates.append(stripped)
            for candidate in candidates:
                if candidate not in seen:
                    seen.add(candidate)
                    result.append(candidate)
        return result

    def _story_segment_artifact_matches_turn(
        self,
        *,
        artifact: StoryArtifact,
        turn: StoryTurnRecord,
        require_output_ref: bool = True,
    ) -> bool:
        if self._artifact_runtime_turn_id(artifact) != turn.turn_id:
            return False
        if self._artifact_runtime_branch_head_id(artifact) != turn.branch_head_id:
            return False
        return (
            not require_output_ref
            or artifact.artifact_id in self._turn_output_artifact_ids(turn)
        )

    def _require_session_record(self, session_id: str) -> StorySessionRecord:
        record = self._session.get(StorySessionRecord, session_id)
        if record is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return record

    def _coerce_session_record(
        self,
        *,
        session_id: str,
        session: StorySession | StorySessionRecord | None,
    ) -> StorySessionRecord:
        if isinstance(session, StorySessionRecord):
            return session
        record = self._require_session_record(session_id)
        if session is not None and session.session_id != record.session_id:
            raise ValueError(f"StorySession mismatch: {session.session_id}")
        return record

    def _require_chapter_record(
        self, chapter_workspace_id: str
    ) -> ChapterWorkspaceRecord:
        record = self._session.get(ChapterWorkspaceRecord, chapter_workspace_id)
        if record is None:
            raise ValueError(f"ChapterWorkspace not found: {chapter_workspace_id}")
        return record

    def _require_current_chapter_record(
        self, session_id: str
    ) -> ChapterWorkspaceRecord:
        session = self._require_session_record(session_id)
        stmt = (
            select(ChapterWorkspaceRecord)
            .where(ChapterWorkspaceRecord.session_id == session_id)
            .where(
                ChapterWorkspaceRecord.chapter_index == session.current_chapter_index
            )
        )
        record = self._session.exec(stmt).first()
        if record is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        return record

    def _require_artifact_record(self, artifact_id: str) -> StoryArtifactRecord:
        record = self._session.get(StoryArtifactRecord, artifact_id)
        if record is None:
            raise ValueError(f"StoryArtifact not found: {artifact_id}")
        return record

    @staticmethod
    def _record_to_story_session(record: StorySessionRecord | None) -> StorySession:
        if record is None:
            raise ValueError("StorySessionRecord is required")
        return StorySession.model_validate(
            {
                "session_id": record.session_id,
                "story_id": record.story_id,
                "source_workspace_id": record.source_workspace_id,
                "mode": record.mode,
                "session_state": record.session_state,
                "active_branch_head_id": record.active_branch_head_id,
                "active_runtime_profile_snapshot_id": (
                    record.active_runtime_profile_snapshot_id
                ),
                "current_chapter_index": record.current_chapter_index,
                "current_phase": record.current_phase,
                "runtime_story_config": record.runtime_story_config_json,
                "writer_contract": record.writer_contract_json,
                "current_state_json": record.current_state_json,
                "activated_at": record.activated_at,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_chapter(record: ChapterWorkspaceRecord | None) -> ChapterWorkspace:
        if record is None:
            raise ValueError("ChapterWorkspaceRecord is required")
        return ChapterWorkspace.model_validate(
            {
                "chapter_workspace_id": record.chapter_workspace_id,
                "session_id": record.session_id,
                "chapter_index": record.chapter_index,
                "phase": record.phase,
                "chapter_goal": record.chapter_goal,
                "outline_draft_json": record.outline_draft_json,
                "accepted_outline_json": record.accepted_outline_json,
                "builder_snapshot_json": record.builder_snapshot_json,
                "review_notes": record.review_notes_json,
                "accepted_segment_ids": record.accepted_segment_ids_json,
                "pending_segment_artifact_id": record.pending_segment_artifact_id,
                "current_scene_ref": record.current_scene_ref,
                "next_scene_index": record.next_scene_index,
                "last_closed_scene_ref": record.last_closed_scene_ref,
                "closed_scene_refs": record.closed_scene_refs_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_artifact(record: StoryArtifactRecord | None) -> StoryArtifact:
        if record is None:
            raise ValueError("StoryArtifactRecord is required")
        return StoryArtifact.model_validate(
            {
                "artifact_id": record.artifact_id,
                "session_id": record.session_id,
                "chapter_workspace_id": record.chapter_workspace_id,
                "artifact_kind": record.artifact_kind,
                "status": record.status,
                "revision": record.revision,
                "content_text": record.content_text,
                "metadata": record.metadata_json,
                "scene_ref": record.scene_ref,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_discussion_entry(
        record: StoryDiscussionEntryRecord,
    ) -> StoryDiscussionEntry:
        return StoryDiscussionEntry.model_validate(
            {
                "entry_id": record.entry_id,
                "session_id": record.session_id,
                "chapter_workspace_id": record.chapter_workspace_id,
                "role": record.role,
                "content_text": record.content_text,
                "linked_artifact_id": record.linked_artifact_id,
                "scene_ref": record.scene_ref,
                "created_at": record.created_at,
            }
        )
