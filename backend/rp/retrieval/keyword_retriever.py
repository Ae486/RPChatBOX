"""Sparse retrieval over persisted knowledge chunks."""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from models.rp_retrieval_store import KnowledgeChunkRecord, KnowledgeCollectionRecord, SourceAssetRecord
from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from .search_utils import build_chunk_hit, build_filters_applied, chunk_view_priority, row_matches_common_filters

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


class KeywordRetriever:
    """Prefer PostgreSQL FTS and fall back to lexical overlap elsewhere."""

    def __init__(self, session) -> None:
        self._session = session

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
        started = time.perf_counter()
        if not (query.text_query or "").strip():
            warning = "keyword_unavailable:empty_query"
            return RetrievalSearchResult(
                query="",
                hits=[],
                trace=RetrievalTrace(
                    trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                    query_id=query.query_id,
                    route="retrieval.keyword.empty",
                    result_kind="chunk",
                    filters_applied=build_filters_applied(query),
                    retriever_routes=["retrieval.keyword.empty"],
                    pipeline_stages=["retrieve"],
                    candidate_count=0,
                    returned_count=0,
                    timings={"keyword_ms": round((time.perf_counter() - started) * 1000, 3)},
                    warnings=[warning],
                ),
                warnings=[warning],
            )
        rows, warnings, route = self._load_ranked_rows(query)
        hits = [
            build_chunk_hit(
                query=query,
                chunk=chunk,
                asset=asset,
                collection=collection,
                score=score,
                rank=index,
            )
            for index, (chunk, asset, collection, score) in enumerate(rows[: query.top_k], start=1)
        ]
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
                timings={"keyword_ms": round((time.perf_counter() - started) * 1000, 3)},
                warnings=warnings,
            ),
            warnings=warnings,
        )

    def _load_ranked_rows(
        self,
        query: RetrievalQuery,
    ) -> tuple[list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]], list[str], str]:
        if self._session.get_bind().dialect.name == "postgresql" and (query.text_query or "").strip():
            try:
                postgres_rows = self._load_with_postgres_fts(query)
                if postgres_rows:
                    return postgres_rows, [], "retrieval.keyword.fts"
            except Exception as exc:  # pragma: no cover - postgres only
                return self._load_with_python_scoring(query), [f"fts_unavailable:{type(exc).__name__}"], "retrieval.keyword.lexical"
        return self._load_with_python_scoring(query), [], "retrieval.keyword.lexical"

    def _load_with_postgres_fts(
        self,
        query: RetrievalQuery,
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]]:
        conditions = ["c.is_active = true"]
        params: dict[str, Any] = {
            "query": query.text_query,
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
            "ts_rank_cd(to_tsvector('simple', coalesce(c.title, '') || ' ' || coalesce(c.\"text\", '')), "
            "plainto_tsquery('simple', :query)) AS score "
            "FROM rp_knowledge_chunks c "
            "JOIN rp_source_assets a ON a.asset_id = c.asset_id "
            "LEFT JOIN rp_knowledge_collections k ON k.collection_id = c.collection_id "
            f"WHERE {' AND '.join(conditions)} "
            "AND to_tsvector('simple', coalesce(c.title, '') || ' ' || coalesce(c.\"text\", '')) @@ plainto_tsquery('simple', :query) "
            "ORDER BY score DESC "
            "LIMIT :limit"
        )
        ranked_ids = list(self._session.exec(sql, params).all())
        score_map = {row[0]: float(row[1]) for row in ranked_ids}
        if not score_map:
            return []
        return self._load_joined_rows(query, score_map)

    def _load_with_python_scoring(
        self,
        query: RetrievalQuery,
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None, float]]:
        tokens = [token for token in _TOKEN_RE.findall((query.text_query or "").lower()) if token]
        if not tokens:
            return []

        score_map: dict[str, float] = defaultdict(float)
        for chunk, asset, collection in self._iter_joined_rows(query):
            haystack = f"{chunk.title or ''}\n{chunk.text}".lower()
            for token in tokens:
                if token in haystack:
                    score_map[chunk.chunk_id] += haystack.count(token)
            if score_map.get(chunk.chunk_id):
                score_map[chunk.chunk_id] += min(len(tokens), 4) * 0.05
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

    def _iter_joined_rows(
        self,
        query: RetrievalQuery,
    ) -> list[tuple[KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord | None]]:
        stmt = (
            select(KnowledgeChunkRecord, SourceAssetRecord, KnowledgeCollectionRecord)
            .join(SourceAssetRecord, SourceAssetRecord.asset_id == KnowledgeChunkRecord.asset_id)
            .join(
                KnowledgeCollectionRecord,
                KnowledgeCollectionRecord.collection_id == KnowledgeChunkRecord.collection_id,
                isouter=True,
            )
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        )
        if query.story_id not in {"", "*"}:
            stmt = stmt.where(KnowledgeChunkRecord.story_id == query.story_id)
        if query.domains:
            stmt = stmt.where(KnowledgeChunkRecord.domain.in_([domain.value for domain in query.domains]))
        collection_ids = list(query.filters.get("knowledge_collections") or [])
        if collection_ids:
            stmt = stmt.where(KnowledgeChunkRecord.collection_id.in_(collection_ids))
        rows = []
        for chunk, asset, collection in self._session.exec(stmt).all():
            if row_matches_common_filters(chunk=chunk, asset=asset, collection=collection, query=query):
                rows.append((chunk, asset, collection))
        return rows
