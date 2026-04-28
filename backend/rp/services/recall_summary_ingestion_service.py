"""Write chapter summaries into retrieval recall collection."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from rp.models.memory_materialization import (
    CHAPTER_SUMMARY_KIND,
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


class RecallSummaryIngestionService:
    """Persist internal recall summaries through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def ingest_chapter_summary(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_text: str,
    ) -> str:
        collection = self._collection_service.ensure_story_collection(
            story_id=story_id,
            scope="story",
            collection_kind="recall",
        )
        asset_id = uuid4().hex
        now = _utcnow()
        domain_path = f"recall.chapter.{chapter_index}"
        metadata = build_recall_materialization_metadata(
            materialization_kind=CHAPTER_SUMMARY_KIND,
            materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
            session_id=session_id,
            chapter_index=chapter_index,
            domain_path=domain_path,
        )
        asset = SourceAsset(
            asset_id=asset_id,
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            workspace_id=source_workspace_id,
            step_id="active_story",
            commit_id=None,
            asset_kind="chapter_summary",
            source_ref=f"story_session:{session_id}:chapter:{chapter_index}",
            title=f"Chapter {chapter_index} Summary",
            raw_excerpt=summary_text[:280],
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["recall"],
            metadata={
                **metadata,
                "seed_sections": [
                    build_recall_seed_section(
                        section_id=f"chapter_summary:{chapter_index}",
                        title=f"Chapter {chapter_index} Summary",
                        path=domain_path,
                        text=summary_text,
                        metadata=metadata,
                        tags=[CHAPTER_SUMMARY_KIND, "recall"],
                    )
                ],
            },
            created_at=now,
            updated_at=now,
        )
        self._document_service.upsert_source_asset(asset)
        job = self._ingestion_service.ingest_asset(
            story_id=story_id,
            asset_id=asset_id,
            collection_id=collection.collection_id,
        )
        self._raise_if_job_failed(job=job, asset_id=asset_id)
        return asset_id

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(f"recall_summary_ingestion_failed:{asset_id}:{error_detail}")
