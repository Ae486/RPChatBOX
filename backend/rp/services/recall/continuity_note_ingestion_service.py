"""Persist heavy-regression continuity notes into retrieval recall collections."""

from __future__ import annotations

from hashlib import sha256

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import (
    CONTINUITY_NOTE_KIND,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    build_recall_materialization_metadata,
)
from ._ingestion_pipeline import (
    RecallSeedAssetSpec,
    branch_head_id,
    ensure_recall_collection,
    persist_recall_seed_asset,
)
from .lifecycle_service import RecallLifecycleService
from ..retrieval.collection_service import RetrievalCollectionService
from ..retrieval.document_service import RetrievalDocumentService
from ..retrieval.ingestion_service import RetrievalIngestionService


class RecallContinuityNoteIngestionService:
    """Persist chapter-close continuity notes through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)
        self._lifecycle_service = RecallLifecycleService(session)

    def ingest_continuity_notes(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_updates: list[str],
        runtime_identity: MemoryRuntimeIdentity | None = None,
        source_refs: list[MemorySourceRef] | None = None,
    ) -> list[str]:
        notes = self._dedupe_notes(summary_updates)
        if not notes:
            return []

        collection = ensure_recall_collection(
            self._collection_service,
            story_id=story_id,
        )
        persisted_asset_ids: list[str] = []
        branch_id = branch_head_id(runtime_identity)

        for note_index, note_text in notes:
            asset_id = self._build_asset_id(
                session_id=session_id,
                chapter_index=chapter_index,
                note_text=note_text,
                branch_head_id=branch_id,
            )
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
                identity=runtime_identity,
                source_refs=source_refs,
                extra={"note_index": note_index},
            )
            title = f"Chapter {chapter_index} Continuity Note {note_index + 1}"
            persist_recall_seed_asset(
                document_service=self._document_service,
                ingestion_service=self._ingestion_service,
                lifecycle_service=self._lifecycle_service,
                spec=RecallSeedAssetSpec(
                    asset_id=asset_id,
                    story_id=story_id,
                    collection_id=collection.collection_id,
                    source_workspace_id=source_workspace_id,
                    asset_kind="continuity_note",
                    source_ref=source_ref,
                    title=title,
                    raw_text=note_text,
                    metadata=metadata,
                    section_id=f"continuity_note:{note_digest}",
                    section_title=title,
                    section_path=section_path,
                    section_text=note_text,
                    section_tags=[CONTINUITY_NOTE_KIND, "recall"],
                    error_prefix="recall_continuity_note_ingestion_failed",
                ),
            )
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
        branch_head_id: str | None = None,
    ) -> str:
        return (
            "recall_continuity_note_"
            + cls._note_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                note_text=note_text,
                branch_head_id=branch_head_id,
            )[:24]
        )

    @staticmethod
    def _normalize_note_text(note_text: str) -> str:
        return " ".join(note_text.split())

    @staticmethod
    def _note_digest(
        *,
        session_id: str,
        chapter_index: int,
        note_text: str,
        branch_head_id: str | None = None,
    ) -> str:
        identity = (
            f"{session_id}\n{chapter_index}\n{note_text}\n"
            f"{(branch_head_id or '').strip()}"
        )
        return sha256(identity.encode("utf-8")).hexdigest()

