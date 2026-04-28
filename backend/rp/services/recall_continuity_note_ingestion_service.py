"""Persist heavy-regression continuity notes into retrieval recall collections."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from rp.models.memory_materialization import (
    CONTINUITY_NOTE_KIND,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    build_recall_materialization_metadata,
    build_recall_seed_section,
)
from rp.models.retrieval_records import IndexJob, SourceAsset
from rp.models.setup_workspace import StoryMode
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecallContinuityNoteIngestionService:
    """Persist chapter-close continuity notes through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def ingest_continuity_notes(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_updates: list[str],
    ) -> list[str]:
        notes = self._dedupe_notes(summary_updates)
        if not notes:
            return []

        collection = self._collection_service.ensure_story_collection(
            story_id=story_id,
            scope="story",
            collection_kind="recall",
        )
        persisted_asset_ids: list[str] = []

        for note_index, note_text in notes:
            asset_id = self._build_asset_id(
                session_id=session_id,
                chapter_index=chapter_index,
                note_text=note_text,
            )
            now = _utcnow()
            existing_asset = self._document_service.get_source_asset(asset_id)
            note_digest = self._note_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                note_text=note_text,
            )[:16]
            section_path = (
                f"recall.chapter.{chapter_index}.continuity_note.{note_digest}"
            )
            source_ref = (
                f"story_session:{session_id}:chapter:{chapter_index}:"
                f"continuity_note:{note_digest}"
            )
            metadata = build_recall_materialization_metadata(
                materialization_kind=CONTINUITY_NOTE_KIND,
                materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
                session_id=session_id,
                chapter_index=chapter_index,
                domain_path=section_path,
                extra={"note_index": note_index},
            )
            asset = SourceAsset(
                asset_id=asset_id,
                story_id=story_id,
                mode=StoryMode.LONGFORM,
                collection_id=collection.collection_id,
                workspace_id=source_workspace_id,
                step_id="active_story",
                commit_id=None,
                asset_kind="continuity_note",
                source_ref=source_ref,
                title=f"Chapter {chapter_index} Continuity Note {note_index + 1}",
                raw_excerpt=note_text[:280],
                parse_status="queued",
                ingestion_status="queued",
                mapped_targets=["recall"],
                metadata={
                    **metadata,
                    "seed_sections": [
                        build_recall_seed_section(
                            section_id=f"continuity_note:{note_digest}",
                            title=(
                                f"Chapter {chapter_index} Continuity Note "
                                f"{note_index + 1}"
                            ),
                            path=section_path,
                            text=note_text,
                            metadata=metadata,
                            tags=[CONTINUITY_NOTE_KIND, "recall"],
                        )
                    ],
                },
                created_at=existing_asset.created_at
                if existing_asset is not None
                else now,
                updated_at=now,
            )
            self._document_service.upsert_source_asset(asset)
            if existing_asset is None:
                job = self._ingestion_service.ingest_asset(
                    story_id=story_id,
                    asset_id=asset_id,
                    collection_id=collection.collection_id,
                )
            else:
                job = self._ingestion_service.reindex_asset(
                    story_id=story_id,
                    asset_id=asset_id,
                )
            self._raise_if_job_failed(job=job, asset_id=asset_id)
            persisted_asset_ids.append(asset_id)

        return persisted_asset_ids

    @classmethod
    def _dedupe_notes(cls, summary_updates: list[str]) -> list[tuple[int, str]]:
        seen: set[str] = set()
        notes: list[tuple[int, str]] = []
        for note_index, raw_note in enumerate(summary_updates):
            note_text = cls._normalize_note_text(raw_note)
            if not note_text or note_text in seen:
                continue
            seen.add(note_text)
            notes.append((note_index, note_text))
        return notes

    @classmethod
    def _build_asset_id(
        cls,
        *,
        session_id: str,
        chapter_index: int,
        note_text: str,
    ) -> str:
        return (
            "recall_continuity_note_"
            + cls._note_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                note_text=note_text,
            )[:24]
        )

    @staticmethod
    def _normalize_note_text(note_text: str) -> str:
        return " ".join(note_text.split())

    @staticmethod
    def _note_digest(*, session_id: str, chapter_index: int, note_text: str) -> str:
        identity = f"{session_id}\n{chapter_index}\n{note_text}"
        return sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(
            f"recall_continuity_note_ingestion_failed:{asset_id}:{error_detail}"
        )
