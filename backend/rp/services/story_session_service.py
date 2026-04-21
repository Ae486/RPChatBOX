"""Persistence service for active-story runtime state."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_story_store import (
    ChapterWorkspaceRecord,
    StoryArtifactRecord,
    StoryDiscussionEntryRecord,
    StorySessionRecord,
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


_UNSET = object()


class StorySessionService:
    """Database-backed true source for longform active-story MVP."""

    def __init__(self, session: Session):
        self._session = session

    def list_sessions(self) -> list[StorySession]:
        stmt = select(StorySessionRecord).order_by(StorySessionRecord.updated_at.desc())
        return [self._record_to_story_session(record) for record in self._session.exec(stmt).all()]

    def commit(self) -> None:
        self._session.commit()

    def get_session(self, session_id: str) -> StorySession | None:
        record = self._session.get(StorySessionRecord, session_id)
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
        record = StorySessionRecord(
            session_id=uuid4().hex,
            story_id=story_id,
            source_workspace_id=source_workspace_id,
            mode=mode,
            session_state=StorySessionState.ACTIVE.value,
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
        current_state_json: dict | None = None,
    ) -> StorySession:
        record = self._require_session_record(session_id)
        if session_state is not None:
            record.session_state = session_state.value
        if current_chapter_index is not None:
            record.current_chapter_index = current_chapter_index
        if current_phase is not None:
            record.current_phase = current_phase.value
        if current_state_json is not None:
            record.current_state_json = dict(current_state_json)
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._record_to_story_session(record)

    def get_current_chapter(self, session_id: str) -> ChapterWorkspace | None:
        session = self._require_session_record(session_id)
        return self.get_chapter_by_index(session_id=session_id, chapter_index=session.current_chapter_index)

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
            record.pending_segment_artifact_id = pending_segment_artifact_id
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
    ) -> StoryArtifact:
        now = _utcnow()
        record = StoryArtifactRecord(
            artifact_id=uuid4().hex,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            artifact_kind=artifact_kind.value,
            status=status.value,
            revision=revision,
            content_text=content_text,
            metadata_json=dict(metadata or {}),
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
            .order_by(StoryArtifactRecord.created_at.asc())
        )
        return [self._record_to_artifact(record) for record in self._session.exec(stmt).all()]

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
    ) -> StoryDiscussionEntry:
        record = StoryDiscussionEntryRecord(
            entry_id=uuid4().hex,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            role=role,
            content_text=content_text,
            linked_artifact_id=linked_artifact_id,
            created_at=_utcnow(),
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_discussion_entry(record)

    def list_discussion_entries(self, *, chapter_workspace_id: str) -> list[StoryDiscussionEntry]:
        stmt = (
            select(StoryDiscussionEntryRecord)
            .where(StoryDiscussionEntryRecord.chapter_workspace_id == chapter_workspace_id)
            .order_by(StoryDiscussionEntryRecord.created_at.asc())
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
        chapter = self.get_chapter_by_index(session_id=session_id, chapter_index=chapter_index)
        if chapter is None:
            raise ValueError(
                f"ChapterWorkspace not found: session={session_id} chapter={chapter_index}"
            )
        return ChapterWorkspaceSnapshot(
            session=session,
            chapter=chapter,
            artifacts=self.list_artifacts(chapter_workspace_id=chapter.chapter_workspace_id),
            discussion_entries=self.list_discussion_entries(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
        )

    def _require_session_record(self, session_id: str) -> StorySessionRecord:
        record = self._session.get(StorySessionRecord, session_id)
        if record is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return record

    def _require_chapter_record(self, chapter_workspace_id: str) -> ChapterWorkspaceRecord:
        record = self._session.get(ChapterWorkspaceRecord, chapter_workspace_id)
        if record is None:
            raise ValueError(f"ChapterWorkspace not found: {chapter_workspace_id}")
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
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_discussion_entry(record: StoryDiscussionEntryRecord) -> StoryDiscussionEntry:
        return StoryDiscussionEntry.model_validate(
            {
                "entry_id": record.entry_id,
                "session_id": record.session_id,
                "chapter_workspace_id": record.chapter_workspace_id,
                "role": record.role,
                "content_text": record.content_text,
                "linked_artifact_id": record.linked_artifact_id,
                "created_at": record.created_at,
            }
        )
