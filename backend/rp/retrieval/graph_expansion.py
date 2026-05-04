"""Evidence-backed graph candidate expansion for retrieval queries."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import select

from models.rp_retrieval_store import (
    KnowledgeChunkRecord,
    KnowledgeCollectionRecord,
    MemoryGraphEdgeRecord,
    MemoryGraphEvidenceRecord,
    MemoryGraphNodeRecord,
    SourceAssetRecord,
)
from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from rp.models.memory_graph_projection import (
    GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
    GRAPH_SOURCE_LAYER_ARCHIVAL,
    GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
)

from .search_utils import (
    build_chunk_hit,
    build_filters_applied,
    row_matches_common_filters,
)

GRAPH_POLICY_MODE_TEXT_FIRST = "text_first"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_GRAPH_TRACE_DETAIL_KEYS = (
    "graph_enabled",
    "graph_backend",
    "graph_policy_mode",
    "graph_candidate_count",
    "graph_expanded_hit_count",
    "graph_warning_codes",
    "graph_ms",
)
_GRAPH_EXPANSION_SCORE_BASE = 0.05
_GRAPH_EXPANSION_SCORE_STEP = 0.001


@dataclass(frozen=True)
class _GraphSummary:
    enabled: bool = False
    backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    policy_mode: str = GRAPH_POLICY_MODE_TEXT_FIRST
    candidate_count: int = 0
    expanded_hit_count: int = 0
    warning_codes: tuple[str, ...] = ()
    graph_ms: float = 0.0

    def as_details(self) -> dict[str, object]:
        return {
            "graph_enabled": self.enabled,
            "graph_backend": self.backend,
            "graph_policy_mode": self.policy_mode,
            "graph_candidate_count": self.candidate_count,
            "graph_expanded_hit_count": self.expanded_hit_count,
            "graph_warning_codes": list(self.warning_codes),
            "graph_ms": self.graph_ms,
        }


def graph_expansion_summary_from_trace(
    trace: RetrievalTrace | None,
) -> dict[str, object]:
    """Return the normal retrieval graph summary fields from trace details."""

    if trace is None or not isinstance(trace.details, dict):
        return _GraphSummary().as_details()
    return {
        key: trace.details.get(key, _GraphSummary().as_details()[key])
        for key in _GRAPH_TRACE_DETAIL_KEYS
    }


def graph_expansion_should_run(query: RetrievalQuery) -> bool:
    """Decide whether this internal graph expansion should participate."""

    if query.query_kind != "archival":
        return False
    filters = dict(query.filters or {})
    intent = str(filters.get("intent") or "").strip().lower()
    return intent == "relation_lookup"


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _tokens(text: str | None) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "") if token]


def _normalize_alias(value: str | None) -> str:
    return " ".join(_tokens(value))


def _query_terms(query: RetrievalQuery) -> set[str]:
    terms = set(_tokens(query.text_query))
    text = _normalize_alias(query.text_query)
    if text:
        terms.add(text)
    return terms


def _node_alias_terms(node: MemoryGraphNodeRecord) -> set[str]:
    aliases = [node.canonical_name, *(node.aliases_json or [])]
    return {_normalize_alias(alias) for alias in aliases if _normalize_alias(alias)}


def _node_matches_query(node: MemoryGraphNodeRecord, query_terms: set[str]) -> bool:
    for alias in _node_alias_terms(node):
        if alias in query_terms:
            return True
        alias_tokens = set(alias.split())
        if alias_tokens and alias_tokens.issubset(query_terms):
            return True
    return False


class GraphExpansionRetriever:
    """Internal graph expansion slot that returns evidence chunk candidates only."""

    def __init__(self, session) -> None:
        self._session = session

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
        started = time.perf_counter()
        if not graph_expansion_should_run(query):
            return self._empty_result(
                query=query,
                summary=_GraphSummary(
                    graph_ms=self._elapsed_ms(started),
                ),
                route="retrieval.graph.skipped",
            )

        try:
            rows = self._load_graph_evidence_rows(query)
            hits = self._build_hits(query=query, rows=rows)
            summary = _GraphSummary(
                enabled=True,
                candidate_count=len(rows),
                expanded_hit_count=len(hits),
                warning_codes=(() if hits else ("graph_expansion_no_evidence_hits",)),
                graph_ms=self._elapsed_ms(started),
            )
            return self._result_from_hits(query=query, hits=hits, summary=summary)
        except Exception as exc:
            summary = _GraphSummary(
                enabled=True,
                warning_codes=(f"graph_expansion_unavailable:{type(exc).__name__}",),
                graph_ms=self._elapsed_ms(started),
            )
            return self._empty_result(
                query=query,
                summary=summary,
                route="retrieval.graph.unavailable",
            )

    def _load_graph_evidence_rows(
        self,
        query: RetrievalQuery,
    ) -> list[
        tuple[
            MemoryGraphEvidenceRecord,
            MemoryGraphEdgeRecord,
            KnowledgeChunkRecord,
            SourceAssetRecord,
            KnowledgeCollectionRecord | None,
        ]
    ]:
        nodes = self._matched_nodes(query)
        node_ids = {node.node_id for node in nodes}
        edge_stmt = (
            select(MemoryGraphEdgeRecord)
            .where(MemoryGraphEdgeRecord.story_id == query.story_id)
            .where(MemoryGraphEdgeRecord.source_layer == GRAPH_SOURCE_LAYER_ARCHIVAL)
            .where(
                MemoryGraphEdgeRecord.source_status
                == GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
            )
        )
        if node_ids:
            edge_stmt = edge_stmt.where(
                (MemoryGraphEdgeRecord.source_node_id.in_(node_ids))
                | (MemoryGraphEdgeRecord.target_node_id.in_(node_ids))
            )
        edge_stmt = edge_stmt.order_by(
            MemoryGraphEdgeRecord.confidence.desc(),
            MemoryGraphEdgeRecord.edge_id.asc(),
        )
        edges = [
            edge
            for edge in self._session.exec(edge_stmt).all()
            if node_ids or self._edge_matches_query(edge=edge, query=query)
        ]
        if not edges:
            return []

        evidence_stmt = (
            select(
                MemoryGraphEvidenceRecord,
                MemoryGraphEdgeRecord,
                KnowledgeChunkRecord,
                SourceAssetRecord,
                KnowledgeCollectionRecord,
            )
            .join(
                MemoryGraphEdgeRecord,
                MemoryGraphEdgeRecord.edge_id == MemoryGraphEvidenceRecord.edge_id,
            )
            .join(
                KnowledgeChunkRecord,
                KnowledgeChunkRecord.chunk_id == MemoryGraphEvidenceRecord.chunk_id,
            )
            .join(
                SourceAssetRecord,
                SourceAssetRecord.asset_id == KnowledgeChunkRecord.asset_id,
            )
            .join(
                KnowledgeCollectionRecord,
                KnowledgeCollectionRecord.collection_id
                == KnowledgeChunkRecord.collection_id,
                isouter=True,
            )
            .where(MemoryGraphEvidenceRecord.story_id == query.story_id)
            .where(
                MemoryGraphEvidenceRecord.edge_id.in_([edge.edge_id for edge in edges])
            )
            .where(MemoryGraphEvidenceRecord.chunk_id.is_not(None))
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
            .order_by(
                MemoryGraphEdgeRecord.confidence.desc(),
                MemoryGraphEvidenceRecord.evidence_id.asc(),
            )
        )
        rows = []
        for evidence, edge, chunk, asset, collection in self._session.exec(
            evidence_stmt
        ).all():
            if not row_matches_common_filters(
                chunk=chunk,
                asset=asset,
                collection=collection,
                query=query,
            ):
                continue
            rows.append((evidence, edge, chunk, asset, collection))
        return rows

    def _matched_nodes(self, query: RetrievalQuery) -> list[MemoryGraphNodeRecord]:
        query_terms = _query_terms(query)
        if not query_terms:
            return []
        stmt = (
            select(MemoryGraphNodeRecord)
            .where(MemoryGraphNodeRecord.story_id == query.story_id)
            .where(MemoryGraphNodeRecord.source_layer == GRAPH_SOURCE_LAYER_ARCHIVAL)
            .where(
                MemoryGraphNodeRecord.source_status
                == GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
            )
            .order_by(
                MemoryGraphNodeRecord.confidence.desc(),
                MemoryGraphNodeRecord.canonical_name.asc(),
            )
        )
        return [
            node
            for node in self._session.exec(stmt).all()
            if _node_matches_query(node, query_terms)
        ]

    @staticmethod
    def _edge_matches_query(
        *,
        edge: MemoryGraphEdgeRecord,
        query: RetrievalQuery,
    ) -> bool:
        query_terms = _query_terms(query)
        if not query_terms:
            return False
        edge_text_terms = _query_terms(
            query.model_copy(
                update={
                    "text_query": " ".join(
                        str(item or "")
                        for item in (
                            edge.source_entity_name,
                            edge.target_entity_name,
                            edge.raw_relation_text,
                            edge.relation_type,
                        )
                    )
                }
            )
        )
        if query_terms.intersection(edge_text_terms):
            return True
        normalized_query_text = _normalize_alias(query.text_query)
        edge_aliases = [
            _normalize_alias(edge.source_entity_name),
            _normalize_alias(edge.target_entity_name),
            _normalize_alias(edge.raw_relation_text),
        ]
        return any(
            alias and (alias in normalized_query_text or normalized_query_text in alias)
            for alias in edge_aliases
        )

    def _build_hits(
        self,
        *,
        query: RetrievalQuery,
        rows: list[
            tuple[
                MemoryGraphEvidenceRecord,
                MemoryGraphEdgeRecord,
                KnowledgeChunkRecord,
                SourceAssetRecord,
                KnowledgeCollectionRecord | None,
            ]
        ],
    ):
        hits = []
        seen_chunk_ids: set[str] = set()
        for index, (evidence, edge, chunk, asset, collection) in enumerate(
            rows, start=1
        ):
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            base_score = _GRAPH_EXPANSION_SCORE_BASE
            if edge.confidence is not None:
                base_score += max(float(edge.confidence), 0.0) * 0.01
            score = max(base_score - (index * _GRAPH_EXPANSION_SCORE_STEP), 0.001)
            hit = build_chunk_hit(
                query=query,
                chunk=chunk,
                asset=asset,
                collection=collection,
                score=score,
                rank=len(hits) + 1,
            )
            metadata = {
                **dict(hit.metadata),
                "graph_expanded": True,
                "graph_edge_id": edge.edge_id,
                "graph_relation_type": edge.relation_type,
                "graph_evidence_id": evidence.evidence_id,
            }
            hits.append(hit.model_copy(update={"metadata": metadata}))
        return hits

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)

    def _empty_result(
        self,
        *,
        query: RetrievalQuery,
        summary: _GraphSummary,
        route: str,
    ) -> RetrievalSearchResult:
        return self._result_from_hits(
            query=query, hits=[], summary=summary, route=route
        )

    def _result_from_hits(
        self,
        *,
        query: RetrievalQuery,
        hits,
        summary: _GraphSummary,
        route: str = "retrieval.graph.expansion",
    ) -> RetrievalSearchResult:
        warning_codes = _dedupe_preserve_order(summary.warning_codes)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=list(hits),
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route=route,
                result_kind="chunk",
                filters_applied=build_filters_applied(query),
                retriever_routes=[route],
                pipeline_stages=["retrieve", "graph_expansion"],
                candidate_count=summary.candidate_count,
                returned_count=len(hits),
                timings={"graph_ms": summary.graph_ms},
                warnings=warning_codes,
                details=summary.as_details(),
            ),
            warnings=warning_codes,
        )


def merge_graph_expansion_result(
    *,
    query: RetrievalQuery,
    result: RetrievalSearchResult,
    graph_result: RetrievalSearchResult,
) -> RetrievalSearchResult:
    """Append graph-expanded evidence hits without changing base hit ordering."""

    if result.trace is None:
        return result

    graph_summary = graph_expansion_summary_from_trace(graph_result.trace)
    graph_hit_ids = {hit.hit_id for hit in graph_result.hits}
    graph_hit_by_id = {hit.hit_id: hit for hit in graph_result.hits}
    base_hits = []
    for hit in result.hits:
        graph_hit = graph_hit_by_id.get(hit.hit_id)
        if graph_hit is not None:
            hit = hit.model_copy(
                update={
                    "metadata": {
                        **dict(hit.metadata),
                        **{
                            key: value
                            for key, value in dict(graph_hit.metadata).items()
                            if key.startswith("graph_")
                        },
                    }
                }
            )
        base_hits.append(hit)

    existing_ids = {hit.hit_id for hit in base_hits}
    supplemental_hits = []
    for hit in graph_result.hits:
        if hit.hit_id in existing_ids:
            continue
        existing_ids.add(hit.hit_id)
        supplemental_hits.append(
            hit.model_copy(
                update={
                    "rank": len(base_hits) + len(supplemental_hits) + 1,
                }
            )
        )
    supplemental_hits = supplemental_hits[: query.top_k]
    reserved_base_count = max(query.top_k - len(supplemental_hits), 0)
    merged_hits = [
        *base_hits[:reserved_base_count],
        *supplemental_hits,
    ][: query.top_k]
    merged_hits = [
        hit.model_copy(update={"rank": index})
        for index, hit in enumerate(merged_hits, start=1)
    ]

    graph_summary["graph_expanded_hit_count"] = sum(
        1 for hit in merged_hits if hit.hit_id in graph_hit_ids
    )
    warnings = _dedupe_preserve_order(
        [*result.warnings, *list(graph_summary["graph_warning_codes"])]
    )
    details = {**dict(result.trace.details or {}), **graph_summary}
    trace = result.trace.model_copy(
        update={
            "retriever_routes": _dedupe_preserve_order(
                [
                    *(result.trace.retriever_routes or []),
                    *(
                        graph_result.trace.retriever_routes
                        if graph_result.trace
                        else []
                    ),
                ]
            ),
            "pipeline_stages": _dedupe_preserve_order(
                [
                    *(result.trace.pipeline_stages or []),
                    "graph_expansion",
                ]
            ),
            "candidate_count": result.trace.candidate_count
            + int(graph_summary["graph_candidate_count"]),
            "returned_count": min(len(merged_hits), query.top_k),
            "timings": {
                **dict(result.trace.timings or {}),
                "graph_ms": float(graph_summary["graph_ms"]),
            },
            "warnings": warnings,
            "details": details,
        }
    )
    return result.model_copy(
        update={"hits": merged_hits, "trace": trace, "warnings": warnings}
    )


def attach_skipped_graph_summary(
    *,
    query: RetrievalQuery,
    result: RetrievalSearchResult,
) -> RetrievalSearchResult:
    """Make graph policy absence explicit in normal retrieval traces."""

    if result.trace is None:
        return result
    filters = dict(query.filters or {})
    summary = _GraphSummary()
    if query.query_kind == "archival" and filters.get("need_relationship_view") is True:
        summary = _GraphSummary(
            enabled=True,
            warning_codes=("graph_relationship_view_inspection_available",),
        )
    details = dict(result.trace.details or {})
    for key, value in summary.as_details().items():
        details.setdefault(key, value)
    return result.model_copy(
        update={"trace": result.trace.model_copy(update={"details": details})}
    )
