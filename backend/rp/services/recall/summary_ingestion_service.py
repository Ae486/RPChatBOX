"""Write chapter summaries into retrieval recall collection."""

from __future__ import annotations

from hashlib import sha256

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import (
    CHAPTER_SUMMARY_KIND,
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


class RecallSummaryIngestionService:
    """Persist internal recall summaries through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)
        self._lifecycle_service = RecallLifecycleService(session)

    def ingest_chapter_summary(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_text: str,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        source_refs: list[MemorySourceRef] | None = None,
    ) -> str:
        collection = ensure_recall_collection(
            self._collection_service,
            story_id=story_id,
        )
        branch_id = branch_head_id(runtime_identity)
        asset_id = self._build_asset_id(
            session_id=session_id,
            chapter_index=chapter_index,
            branch_head_id=branch_id,
        )
        domain_path = f"recall.chapter.{chapter_index}"
        metadata = build_recall_materialization_metadata(
            materialization_kind=CHAPTER_SUMMARY_KIND,
            materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
            session_id=session_id,
            chapter_index=chapter_index,
            domain_path=domain_path,
            identity=runtime_identity,
            source_refs=source_refs,
        )
        title = f"Chapter {chapter_index} Summary"
        return persist_recall_seed_asset(
            document_service=self._document_service,
            ingestion_service=self._ingestion_service,
            lifecycle_service=self._lifecycle_service,
            spec=RecallSeedAssetSpec(
                asset_id=asset_id,
                story_id=story_id,
                collection_id=collection.collection_id,
                source_workspace_id=source_workspace_id,
                asset_kind="chapter_summary",
                source_ref=self._build_source_ref(
                    session_id=session_id,
                    chapter_index=chapter_index,
                    branch_head_id=branch_id,
                ),
                title=title,
                raw_text=summary_text,
                metadata=metadata,
                section_id=f"chapter_summary:{chapter_index}",
                section_title=title,
                section_path=domain_path,
                section_text=summary_text,
                section_tags=[CHAPTER_SUMMARY_KIND, "recall"],
                error_prefix="recall_summary_ingestion_failed",
            ),
        )

    @classmethod
    def _build_asset_id(
        cls,
        *,
        session_id: str,
        chapter_index: int,
        branch_head_id: str | None,
    ) -> str:
        return (
            "recall_summary_"
            + sha256(
                f"{session_id}\n{chapter_index}\n{(branch_head_id or '').strip()}".encode(
                    "utf-8"
                )
            ).hexdigest()[:24]
        )

    @staticmethod
    def _build_source_ref(
        *,
        session_id: str,
        chapter_index: int,
        branch_head_id: str | None,
    ) -> str:
        branch_suffix = (
            f":branch:{branch_head_id.strip()}"
            if isinstance(branch_head_id, str) and branch_head_id.strip()
            else ""
        )
        return f"story_session:{session_id}{branch_suffix}:chapter:{chapter_index}"

