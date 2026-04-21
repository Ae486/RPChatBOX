"""Retrieval-core ingestion pipeline and backfill entrypoints."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import EmbeddingRecordRecord, IndexJobRecord, KnowledgeChunkRecord
from rp.models.retrieval_records import IndexJob
from rp.retrieval.chunker import Chunker
from rp.retrieval.embedder import Embedder
from rp.retrieval.indexer import Indexer
from rp.retrieval.parser import Parser
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_index_job_service import RetrievalIndexJobService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetrievalIngestionService:
    """Execute parse -> chunk -> embed -> index for retrieval-core."""

    _STUB_EMBEDDING_MODEL = "phase_b_minimal_embedding_stub"

    def __init__(
        self,
        session,
        *,
        document_service: RetrievalDocumentService | None = None,
        collection_service: RetrievalCollectionService | None = None,
        index_job_service: RetrievalIndexJobService | None = None,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        embedder: Embedder | None = None,
        indexer: Indexer | None = None,
    ) -> None:
        self._session = session
        self._document_service = document_service or RetrievalDocumentService(session)
        self._collection_service = collection_service or RetrievalCollectionService(session)
        self._index_job_service = index_job_service or RetrievalIndexJobService(session)
        self._parser = parser or Parser()
        self._chunker = chunker or Chunker()
        self._embedder = embedder or Embedder()
        self._indexer = indexer or Indexer(session)

    def ingest_asset(
        self,
        *,
        story_id: str,
        asset_id: str,
        collection_id: str | None = None,
    ) -> IndexJob:
        job = self._index_job_service.submit_ingest_job(
            story_id=story_id,
            asset_id=asset_id,
            collection_id=collection_id,
        )
        self._session.flush()
        return self.process_job(job.job_id)

    def process_job(self, job_id: str) -> IndexJob:
        record = self._session.get(IndexJobRecord, job_id)
        if record is None:
            raise ValueError(f"IndexJob not found: {job_id}")

        started_at = record.started_at or _utcnow()
        warnings: list[str] = []
        self._index_job_service.update_job_state(
            job_id=job_id,
            state="parsing",
            warnings=[],
            started_at=started_at,
        )
        self._session.flush()

        try:
            asset_ids = self._resolve_target_asset_ids(record)
            if not asset_ids:
                raise ValueError(f"No asset targets resolved for job: {job_id}")

            for asset_id in asset_ids:
                asset_warnings = self._process_asset(record=record, asset_id=asset_id)
                warnings.extend(asset_warnings)

            completed_at = _utcnow()
            model = self._index_job_service.update_job_state(
                job_id=job_id,
                state="completed",
                warnings=sorted(set(warnings)),
                completed_at=completed_at,
            )
            self._session.flush()
            return model
        except Exception as exc:
            failed = self._index_job_service.update_job_state(
                job_id=job_id,
                state="failed",
                warnings=sorted(set(warnings)),
                error_message=str(exc),
                completed_at=_utcnow(),
            )
            self._session.flush()
            return failed

    def reindex_targets(self, *, story_id: str, target_refs: list[str]) -> IndexJob:
        job = self._index_job_service.submit_reindex_job(
            story_id=story_id,
            target_refs=target_refs,
        )
        self._session.flush()
        return self.process_job(job.job_id)

    def backfill_stub_embeddings(self, *, story_id: str) -> list[IndexJob]:
        stmt = (
            select(KnowledgeChunkRecord.asset_id)
            .join(EmbeddingRecordRecord, EmbeddingRecordRecord.chunk_id == KnowledgeChunkRecord.chunk_id)
            .where(KnowledgeChunkRecord.story_id == story_id)
            .where(
                (EmbeddingRecordRecord.vector_dim == 0)
                | (EmbeddingRecordRecord.embedding_model == self._STUB_EMBEDDING_MODEL)
            )
        )
        asset_ids = sorted(set(self._session.exec(stmt).all()))
        jobs = []
        for asset_id in asset_ids:
            jobs.append(self.reindex_targets(story_id=story_id, target_refs=[f"asset:{asset_id}"]))
        return jobs

    def _process_asset(self, *, record: IndexJobRecord, asset_id: str) -> list[str]:
        warnings: list[str] = []
        source_asset = self._document_service.get_source_asset(asset_id)
        if source_asset is None:
            raise ValueError(f"SourceAsset not found: {asset_id}")

        collection_id = (
            record.collection_id
            or source_asset.collection_id
            or self._collection_service.ensure_story_collection(
                story_id=source_asset.story_id,
                scope="story",
                collection_kind="archival",
            ).collection_id
        )
        source_asset = source_asset.model_copy(
            update={
                "collection_id": collection_id,
                "ingestion_status": "processing",
                "updated_at": _utcnow(),
            }
        )
        self._document_service.upsert_source_asset(source_asset)
        self._session.flush()

        document = self._parser.parse(source_asset)
        self._document_service.save_parsed_document(document)
        self._index_job_service.update_job_state(job_id=record.job_id, state="chunking")
        self._session.flush()

        self._indexer.deactivate_asset_records(asset_id=asset_id)
        chunks = self._chunker.chunk(
            document,
            story_id=source_asset.story_id,
            asset_id=source_asset.asset_id,
            collection_id=collection_id,
        )
        for chunk in chunks:
            chunk.provenance_refs.extend(
                [
                    f"asset:{source_asset.asset_id}",
                    f"index_job:{record.job_id}",
                ]
            )
            if source_asset.commit_id:
                chunk.provenance_refs.append(f"commit:{source_asset.commit_id}")
        self._indexer.upsert_chunks(chunks)
        self._index_job_service.update_job_state(job_id=record.job_id, state="embedding")
        self._session.flush()

        embeddings = self._embedder.embed(chunks)
        warnings.extend(self._embedder.last_warnings)
        self._indexer.upsert_embeddings(embeddings)
        self._index_job_service.update_job_state(job_id=record.job_id, state="indexing")
        source_asset = source_asset.model_copy(
            update={
                "parse_status": "parsed",
                "ingestion_status": "completed",
                "raw_excerpt": document.document_structure[0].text[:280] if document.document_structure else source_asset.raw_excerpt,
                "updated_at": _utcnow(),
            }
        )
        self._document_service.upsert_source_asset(source_asset)
        self._session.flush()
        return warnings

    @staticmethod
    def _resolve_target_asset_ids(record: IndexJobRecord) -> list[str]:
        if record.job_kind == "ingest" and record.asset_id:
            return [record.asset_id]

        asset_ids: list[str] = []
        for target_ref in record.target_refs_json or []:
            if target_ref.startswith("asset:"):
                asset_ids.append(target_ref.split("asset:", 1)[1])
            elif target_ref:
                asset_ids.append(target_ref)
        return list(dict.fromkeys(asset_ids))
