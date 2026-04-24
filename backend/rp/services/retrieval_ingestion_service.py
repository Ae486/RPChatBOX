"""Retrieval-core ingestion pipeline and backfill entrypoints."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import EmbeddingRecordRecord, IndexJobRecord, KnowledgeChunkRecord
from rp.models.retrieval_records import IndexJob
from rp.retrieval.chunker import Chunker
from rp.retrieval.embedder import Embedder
from rp.retrieval.ingestion_warning_taxonomy import ingestion_warning, normalize_component_warnings
from rp.retrieval.indexer import Indexer
from rp.retrieval.parser import Parser
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_index_job_service import RetrievalIndexJobService
from .retrieval_runtime_config_service import RetrievalRuntimeConfigService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class _AssetProcessingError(Exception):
    def __init__(
        self,
        message: str,
        *,
        warnings: list[str],
        parse_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.warnings = _dedupe_preserve_order(warnings)
        self.parse_status = parse_status


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
        retrieval_runtime_config_service: RetrievalRuntimeConfigService | None = None,
    ) -> None:
        self._session = session
        self._document_service = document_service or RetrievalDocumentService(session)
        self._collection_service = collection_service or RetrievalCollectionService(session)
        self._index_job_service = index_job_service or RetrievalIndexJobService(session)
        self._parser = parser or Parser()
        self._chunker = chunker or Chunker()
        self._embedder = embedder
        self._indexer = indexer or Indexer(session)
        self._retrieval_runtime_config_service = (
            retrieval_runtime_config_service or RetrievalRuntimeConfigService(session)
        )

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
                try:
                    with self._session.begin_nested():
                        asset_warnings = self._process_asset(record=record, asset_id=asset_id)
                except _AssetProcessingError as exc:
                    warnings.extend(exc.warnings)
                    self._mark_asset_failed(
                        asset_id=asset_id,
                        parse_status=exc.parse_status,
                    )
                    raise ValueError(str(exc)) from exc
                warnings.extend(asset_warnings)

            completed_at = _utcnow()
            model = self._index_job_service.update_job_state(
                job_id=job_id,
                state="completed",
                warnings=_dedupe_preserve_order(warnings),
                completed_at=completed_at,
            )
            self._session.flush()
            return model
        except Exception as exc:
            failed = self._index_job_service.update_job_state(
                job_id=job_id,
                state="failed",
                warnings=_dedupe_preserve_order(warnings),
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

    def reindex_asset(self, *, story_id: str, asset_id: str) -> IndexJob:
        return self.reindex_targets(story_id=story_id, target_refs=[f"asset:{asset_id}"])

    def retry_failed_job(self, *, job_id: str) -> IndexJob:
        record = self._session.get(IndexJobRecord, job_id)
        if record is None:
            raise ValueError(f"IndexJob not found: {job_id}")
        if record.job_state != "failed":
            raise ValueError(f"IndexJob is not retryable: {job_id}")

        if record.job_kind == "ingest":
            if not record.asset_id:
                raise ValueError(f"Retryable ingest job missing asset_id: {job_id}")
            return self.ingest_asset(
                story_id=record.story_id,
                asset_id=record.asset_id,
                collection_id=record.collection_id,
            )

        if record.job_kind == "reindex":
            return self.reindex_targets(
                story_id=record.story_id,
                target_refs=list(record.target_refs_json or []),
            )

        raise ValueError(f"Unsupported retry job kind: {record.job_kind}")

    def list_backfill_candidate_asset_ids(self, *, story_id: str) -> list[str]:
        stmt = (
            select(KnowledgeChunkRecord.asset_id)
            .join(EmbeddingRecordRecord, EmbeddingRecordRecord.chunk_id == KnowledgeChunkRecord.chunk_id)
            .where(KnowledgeChunkRecord.story_id == story_id)
            .where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
            .where(
                (EmbeddingRecordRecord.vector_dim == 0)
                | (EmbeddingRecordRecord.embedding_model == self._STUB_EMBEDDING_MODEL)
            )
        )
        return sorted(set(self._session.exec(stmt).all()))

    def backfill_stub_embeddings(self, *, story_id: str) -> list[IndexJob]:
        asset_ids = self.list_backfill_candidate_asset_ids(story_id=story_id)
        jobs = []
        for asset_id in asset_ids:
            jobs.append(self.reindex_asset(story_id=story_id, asset_id=asset_id))
        return jobs

    def _process_asset(self, *, record: IndexJobRecord, asset_id: str) -> list[str]:
        warnings: list[str] = []
        source_asset = self._document_service.get_source_asset(asset_id)
        if source_asset is None:
            raise _AssetProcessingError(
                f"SourceAsset not found: {asset_id}",
                warnings=warnings,
            )

        parse_status = source_asset.parse_status
        try:
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
            if document.parser_kind in {"raw_file", "fallback"}:
                warnings.append(ingestion_warning("parsing", "parser_kind", document.parser_kind))
            warnings.extend(normalize_component_warnings("parsing", document.parse_warnings))
            self._document_service.save_parsed_document(document)
            parse_status = "parsed"
            self._index_job_service.update_job_state(job_id=record.job_id, state="chunking")
            self._session.flush()

            chunks = self._chunker.chunk(
                document,
                story_id=source_asset.story_id,
                asset_id=source_asset.asset_id,
                collection_id=collection_id,
                source_ref=source_asset.source_ref,
                commit_id=source_asset.commit_id,
                asset_title=source_asset.title,
                asset_summary=source_asset.raw_excerpt,
            )
            if not chunks:
                warnings.append(ingestion_warning("chunking", "no_chunks_generated", asset_id))
                raise _AssetProcessingError(
                    f"No chunks generated for asset: {asset_id}",
                    warnings=warnings,
                    parse_status=parse_status,
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
            self._index_job_service.update_job_state(job_id=record.job_id, state="embedding")
            self._session.flush()

            embedder = self._embedder or self._build_story_embedder(story_id=source_asset.story_id)
            embeddings = embedder.embed(chunks)
            warnings.extend(normalize_component_warnings("embedding", embedder.last_warnings))
            if not embeddings or any(item.vector_dim <= 0 or not item.embedding_vector for item in embeddings):
                warnings.append(ingestion_warning("embedding", "invalid_embedding_output", asset_id))
                raise _AssetProcessingError(
                    f"Invalid embedding output for asset: {asset_id}",
                    warnings=warnings,
                    parse_status=parse_status,
                )

            self._index_job_service.update_job_state(job_id=record.job_id, state="indexing")
            self._indexer.deactivate_asset_records(asset_id=asset_id)
            self._indexer.upsert_chunks(chunks)
            self._indexer.upsert_embeddings(embeddings)
            source_asset = source_asset.model_copy(
                update={
                    "parse_status": parse_status,
                    "ingestion_status": "completed",
                    "raw_excerpt": document.document_structure[0].text[:280] if document.document_structure else source_asset.raw_excerpt,
                    "updated_at": _utcnow(),
                }
            )
            self._document_service.upsert_source_asset(source_asset)
            self._session.flush()
            return _dedupe_preserve_order(warnings)
        except _AssetProcessingError:
            raise
        except Exception as exc:
            raise _AssetProcessingError(
                str(exc),
                warnings=warnings,
                parse_status=parse_status,
            ) from exc

    def _mark_asset_failed(self, *, asset_id: str, parse_status: str | None = None) -> None:
        source_asset = self._document_service.get_source_asset(asset_id)
        if source_asset is None:
            return
        update = {
            "ingestion_status": "failed",
            "updated_at": _utcnow(),
        }
        if parse_status is not None:
            update["parse_status"] = parse_status
        self._document_service.upsert_source_asset(source_asset.model_copy(update=update))

    def _build_story_embedder(self, *, story_id: str) -> Embedder:
        config = self._retrieval_runtime_config_service.resolve_story_config(story_id=story_id)
        return Embedder(
            model_id=config.embedding_model_id,
            provider_id=config.embedding_provider_id,
        )

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
