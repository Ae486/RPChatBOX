"""Persistence helpers for retrieval chunks and embeddings."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    KnowledgeChunkRecord,
    ensure_pgvector_hnsw_index,
)
from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Indexer:
    """Persist active retrieval chunks and embeddings."""

    def __init__(self, session) -> None:
        self._session = session

    def deactivate_asset_records(self, *, asset_id: str) -> None:
        now = _utcnow()
        chunks = self._session.exec(
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.asset_id == asset_id)
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        ).all()
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        for chunk in chunks:
            chunk.is_active = False
            self._session.add(chunk)

        if not chunk_ids:
            return

        embeddings = self._session.exec(
            select(EmbeddingRecordRecord)
            .where(EmbeddingRecordRecord.chunk_id.in_(chunk_ids))
            .where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
        ).all()
        for embedding in embeddings:
            embedding.is_active = False
            embedding.updated_at = now
            self._session.add(embedding)

    def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        for chunk in chunks:
            self._session.add(
                KnowledgeChunkRecord(
                    chunk_id=chunk.chunk_id,
                    story_id=chunk.story_id,
                    collection_id=chunk.collection_id,
                    asset_id=chunk.asset_id,
                    parsed_document_id=chunk.parsed_document_id,
                    chunk_index=chunk.chunk_index,
                    domain=chunk.domain,
                    domain_path=chunk.domain_path,
                    title=chunk.title,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    is_active=chunk.is_active,
                    metadata_json=chunk.metadata,
                    provenance_refs_json=chunk.provenance_refs,
                    created_at=chunk.created_at,
                )
            )

    def upsert_embeddings(self, embeddings: list[EmbeddingRecord]) -> None:
        max_dim = 0
        for embedding in embeddings:
            max_dim = max(max_dim, embedding.vector_dim)
            self._session.add(
                EmbeddingRecordRecord(
                    embedding_id=embedding.embedding_id,
                    chunk_id=embedding.chunk_id,
                    embedding_model=embedding.embedding_model,
                    provider_id=embedding.provider_id,
                    vector_dim=embedding.vector_dim,
                    status=embedding.status,
                    is_active=embedding.is_active,
                    embedding_vector=embedding.embedding_vector,
                    created_at=embedding.created_at,
                    updated_at=embedding.updated_at,
                )
            )
        if max_dim > 0:
            ensure_pgvector_hnsw_index(self._session.get_bind(), vector_dim=max_dim)
