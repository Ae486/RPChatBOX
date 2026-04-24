"""Dense retrieval over chunk embeddings."""

from __future__ import annotations

import time
import uuid

from sqlalchemy import text
from sqlmodel import select

from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    KnowledgeChunkRecord,
    KnowledgeCollectionRecord,
    SourceAssetRecord,
)
from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from .embedder import Embedder
from .search_utils import (
    build_chunk_hit,
    build_filters_applied,
    chunk_view_priority,
    cosine_similarity,
    query_vector_literal,
    row_matches_common_filters,
)


class SemanticRetriever:
    """Use pgvector when available and fall back to in-process cosine search."""

    def __init__(self, session, *, embedder: Embedder | None = None) -> None:
        self._session = session
        self._embedder = embedder or Embedder()

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
        started = time.perf_counter()
        if not (query.text_query or "").strip():
            warning = "dense_unavailable:empty_query"
            return RetrievalSearchResult(
                query="",
                hits=[],
                trace=RetrievalTrace(
                    trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                    query_id=query.query_id,
                    route="retrieval.semantic.empty",
                    result_kind="chunk",
                    filters_applied=build_filters_applied(query),
                    retriever_routes=["retrieval.semantic.empty"],
                    pipeline_stages=["retrieve"],
                    candidate_count=0,
                    returned_count=0,
                    timings={"semantic_ms": round((time.perf_counter() - started) * 1000, 3)},
                    warnings=[warning],
                ),
                warnings=[warning],
            )
        vector, warnings, embedding_model = self._embedder.embed_query(query.text_query or "")
        rows, extra_warnings, route = self._load_ranked_rows(query, vector=vector)
        warnings = [*warnings, *extra_warnings]
        hits = []
        for index, (chunk, asset, collection, score) in enumerate(rows[: query.top_k], start=1):
            hit = build_chunk_hit(
                query=query,
                chunk=chunk,
                asset=asset,
                collection=collection,
                score=score,
                rank=index,
            )
            hits.append(
                hit.model_copy(
                    update={"metadata": {"embedding_model": embedding_model, **dict(hit.metadata)}}
                )
            )
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=hits,
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route=route,
                result_kind="chunk",
                filters_applied=build_filters_applied(query),
                retriever_routes=[route],
                pipeline_stages=["retrieve"],
                candidate_count=len(rows),
                returned_count=len(hits),
                timings={"semantic_ms": round((time.perf_counter() - started) * 1000, 3)},
                warnings=warnings,
            ),
            warnings=warnings,
        )

    def _load_ranked_rows(
        self,
        query: RetrievalQuery,
        *,
        vector: list[float],
    ) -> tuple[list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]], list[str], str]:
        if not vector:
            return [], ["dense_unavailable:no_query_vector"], "retrieval.semantic.empty"

        if self._session.get_bind().dialect.name == "postgresql":
            try:
                rows = self._load_with_pgvector(query, vector=vector)
                if rows:
                    return rows, [], "retrieval.semantic.pgvector"
            except Exception as exc:  # pragma: no cover - postgres only
                return self._load_with_python_scoring(query, vector=vector), [f"pgvector_unavailable:{type(exc).__name__}"], "retrieval.semantic.python"

        rows = self._load_with_python_scoring(query, vector=vector)
        if not rows:
            return [], ["dense_unavailable:no_active_embeddings"], "retrieval.semantic.empty"
        return rows, [], "retrieval.semantic.python"

    def _load_with_pgvector(
        self,
        query: RetrievalQuery,
        *,
        vector: list[float],
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]]:
        vector_dim = len(vector)
        conditions = [
            "e.is_active = true",
            "e.embedding_vector IS NOT NULL",
            "e.vector_dim = :vector_dim",
            "c.is_active = true",
        ]
        params: dict[str, object] = {
            "vector_dim": vector_dim,
            "query_vector": query_vector_literal(vector),
            "limit": max(query.top_k * 5, query.top_k),
        }
        if query.story_id not in {"", "*"}:
            conditions.append("c.story_id = :story_id")
            params["story_id"] = query.story_id
        if query.domains:
            conditions.append("c.domain = ANY(:domains)")
            params["domains"] = [domain.value for domain in query.domains]
        collection_ids = list(query.filters.get("knowledge_collections") or [])
        if collection_ids:
            conditions.append("c.collection_id = ANY(:collection_ids)")
            params["collection_ids"] = collection_ids
        elif query.query_kind == "archival":
            conditions.append("k.collection_kind = 'archival'")
        elif query.query_kind == "recall":
            conditions.append("k.collection_kind = 'recall'")

        sql = text(
            "SELECT c.chunk_id, "
            f"(1 - (e.embedding_vector::vector({vector_dim}) <=> CAST(:query_vector AS vector({vector_dim})))) AS score "
            "FROM rp_embedding_records e "
            "JOIN rp_knowledge_chunks c ON c.chunk_id = e.chunk_id "
            "JOIN rp_source_assets a ON a.asset_id = c.asset_id "
            "LEFT JOIN rp_knowledge_collections k ON k.collection_id = c.collection_id "
            f"WHERE {' AND '.join(conditions)} "
            f"ORDER BY e.embedding_vector::vector({vector_dim}) <=> CAST(:query_vector AS vector({vector_dim})) "
            "LIMIT :limit"
        )
        ranked_ids = list(self._session.exec(sql, params).all())
        score_map = {row[0]: float(row[1]) for row in ranked_ids if float(row[1]) > 0.0}
        return self._load_joined_rows(query, score_map)

    def _load_with_python_scoring(
        self,
        query: RetrievalQuery,
        *,
        vector: list[float],
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]]:
        score_map: dict[str, float] = {}
        stmt = (
            select(
                EmbeddingRecordRecord,
                KnowledgeChunkRecord,
                SourceAssetRecord,
                KnowledgeCollectionRecord,
            )
            .join(KnowledgeChunkRecord, KnowledgeChunkRecord.chunk_id == EmbeddingRecordRecord.chunk_id)
            .join(SourceAssetRecord, SourceAssetRecord.asset_id == KnowledgeChunkRecord.asset_id)
            .join(
                KnowledgeCollectionRecord,
                KnowledgeCollectionRecord.collection_id == KnowledgeChunkRecord.collection_id,
                isouter=True,
            )
            .where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
            .where(EmbeddingRecordRecord.embedding_vector.is_not(None))
        )
        for embedding, chunk, asset, collection in self._session.exec(stmt).all():
            if not row_matches_common_filters(chunk=chunk, asset=asset, collection=collection, query=query):
                continue
            score = cosine_similarity(vector, embedding.embedding_vector or [])
            if score > 0.0:
                score_map[chunk.chunk_id] = score
        return self._load_joined_rows(query, score_map)

    def _load_joined_rows(
        self,
        query: RetrievalQuery,
        score_map: dict[str, float],
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]]:
        if not score_map:
            return []
        stmt = (
            select(KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord)
            .join(SourceAssetRecord, SourceAssetRecord.asset_id == KnowledgeChunkRecord.asset_id)
            .join(
                KnowledgeCollectionRecord,
                KnowledgeCollectionRecord.collection_id == KnowledgeChunkRecord.collection_id,
                isouter=True,
            )
            .where(KnowledgeChunkRecord.chunk_id.in_(list(score_map.keys())))
        )
        rows = []
        for chunk, asset, collection in self._session.exec(stmt).all():
            if not row_matches_common_filters(chunk=chunk, asset=asset, collection=collection, query=query):
                continue
            score = float(score_map.get(chunk.chunk_id) or 0.0)
            if score <= 0.0:
                continue
            rows.append((chunk, asset, collection, score))
        rows.sort(
            key=lambda item: (
                -item[3],
                chunk_view_priority(item[0].metadata_json or {}),
                item[0].chunk_index,
            )
        )
        return rows
