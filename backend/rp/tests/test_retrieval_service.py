"""Tests for retrieval-core search service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import (
    RetrievalHit,
    RetrievalQuery,
    RetrievalSearchResult,
    RetrievalTrace,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.retrieval.query_preprocessor import DefaultQueryPreprocessor
from rp.retrieval.rag_context_builder import RagContextBuilder
from rp.retrieval.reranker import SimpleMetadataReranker
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_service import RetrievalService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_default_query_preprocessor_normalizes_recall_filter_values():
    query = RetrievalQuery(
        query_id="rq-filter-normalize",
        query_kind="recall",
        story_id=" story-filter ",
        domains=[Domain.CHAPTER, Domain.CHAPTER],
        text_query=" filter text ",
        filters={
            "materialization_kinds": [
                " chapter_summary ",
                "",
                "chapter_summary",
                "continuity_note",
            ],
            "source_families": [
                " longform_story_runtime ",
                "longform_story_runtime",
                "alternate_source_family",
            ],
            "chapter_indices": [1, "2", " 2 ", "bad", None, True, "  "],
        },
        top_k=0,
    )

    normalized = DefaultQueryPreprocessor().preprocess(query)

    assert normalized.filters["materialization_kinds"] == [
        "chapter_summary",
        "continuity_note",
    ]
    assert normalized.filters["source_families"] == [
        "longform_story_runtime",
        "alternate_source_family",
    ]
    assert normalized.filters["chapter_indices"] == [1, 2]
    assert normalized.story_id == "story-filter"
    assert normalized.text_query == "filter text"
    assert normalized.domains == [Domain.CHAPTER]
    assert normalized.top_k == 1


def test_default_query_preprocessor_normalizes_narrative_and_archival_filters():
    query = RetrievalQuery(
        query_id="rq-narrative-filter-normalize",
        query_kind="recall",
        story_id="story-filter",
        text_query="filter text",
        filters={
            "scene_refs": [
                " chapter:1:scene:1 ",
                "",
                "chapter:1:scene:1",
                None,
            ],
            "character_refs": [" hero ", "villain", "hero", True],
            "pov_character_refs": [" hero "],
            "foreshadow_refs": [" clue-a "],
            "foreshadow_statuses": [" open ", "open"],
            "branch_ids": [" main "],
            "canon_statuses": [" canonical ", "draft"],
            "source_types": [" foundation_entry ", "foundation_entry"],
            "source_origins": [" setup_workspace "],
            "workspace_ids": [" workspace-1 "],
            "commit_ids": [" commit-1 "],
            "search_policy": {"profile": " LongForm ", "rerank": " ON "},
        },
    )

    normalized = DefaultQueryPreprocessor().preprocess(query)

    assert normalized.filters["scene_refs"] == ["chapter:1:scene:1"]
    assert normalized.filters["character_refs"] == ["hero", "villain"]
    assert normalized.filters["pov_character_refs"] == ["hero"]
    assert normalized.filters["foreshadow_refs"] == ["clue-a"]
    assert normalized.filters["foreshadow_statuses"] == ["open"]
    assert normalized.filters["branch_ids"] == ["main"]
    assert normalized.filters["canon_statuses"] == ["canonical", "draft"]
    assert normalized.filters["source_types"] == ["foundation_entry"]
    assert normalized.filters["source_origins"] == ["setup_workspace"]
    assert normalized.filters["workspace_ids"] == ["workspace-1"]
    assert normalized.filters["commit_ids"] == ["commit-1"]
    assert normalized.filters["search_policy"] == {
        "profile": "longform",
        "rerank": "on",
    }


class _FakeLangfuseObservation:
    def __init__(self, *, sink: list[dict], name: str) -> None:
        self._sink = sink
        self._name = name

    def __enter__(self):
        self._sink.append({"kind": "observation_enter", "name": self._name})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "observation_exit", "name": self._name})
        return False

    def update(self, **kwargs):
        self._sink.append(
            {"kind": "observation_update", "name": self._name, "payload": kwargs}
        )

    def score(self, **kwargs):
        self._sink.append({"kind": "score", "name": self._name, "payload": kwargs})

    def score_trace(self, **kwargs):
        self._sink.append(
            {"kind": "score_trace", "name": self._name, "payload": kwargs}
        )

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self._sink,
            name=str(kwargs.get("name") or "unknown"),
        )


class _FakeLangfuseService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self.events,
            name=str(kwargs.get("name") or "unknown"),
        )


@pytest.mark.asyncio
async def test_search_chunks_and_documents_use_real_store(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-search",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-search",
            story_id="story-search",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            commit_id="commit-search",
            asset_kind="worldbook",
            source_ref="memory://asset-search",
            title="Archive Ledger",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "rule-1",
                        "title": "Archive Rule",
                        "path": "foundation.world.archive_rule",
                        "level": 1,
                        "page_no": 7,
                        "page_label": "VII",
                        "image_caption": "Diagram of the archive ledger seal.",
                        "text": "Archive keepers seal the ledger room before sunrise.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.archive_rule",
                            "tags": ["archive"],
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id="story-search",
        asset_id="asset-search",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    service = RetrievalService(retrieval_session)
    query = RetrievalQuery(
        query_id="rq-search",
        query_kind="archival",
        story_id="story-search",
        domains=[Domain.WORLD_RULE],
        text_query="ledger room sunrise",
        filters={"knowledge_collections": [collection.collection_id]},
        top_k=3,
    )

    chunk_result = await service.search_chunks(query)
    document_result = await service.search_documents(query)
    rag_result = await service.rag_context(query)

    assert chunk_result.hits
    assert chunk_result.trace is not None
    assert chunk_result.trace.route.startswith("retrieval.")
    assert chunk_result.trace.result_kind == "chunk"
    assert chunk_result.trace.retriever_routes
    assert "chunk_result_builder" in chunk_result.trace.pipeline_stages
    assert chunk_result.trace.filters_applied["rerank"] is False
    assert chunk_result.hits[0].metadata["asset_id"] == "asset-search"
    assert chunk_result.hits[0].metadata["collection_id"] == collection.collection_id
    assert chunk_result.hits[0].metadata["source_ref"] == "memory://asset-search"
    assert chunk_result.hits[0].metadata["commit_id"] == "commit-search"
    assert chunk_result.hits[0].metadata["section_id"] == "rule-1"
    assert chunk_result.hits[0].metadata["section_part"] == 0
    assert chunk_result.hits[0].metadata["domain"] == "world_rule"
    assert (
        chunk_result.hits[0].metadata["domain_path"] == "foundation.world.archive_rule"
    )
    assert chunk_result.hits[0].metadata["document_title"] == "Archive Ledger"
    assert chunk_result.hits[0].metadata["document_summary"]
    assert chunk_result.hits[0].metadata["page_no"] == 7
    assert chunk_result.hits[0].metadata["page_label"] == "VII"
    assert chunk_result.hits[0].metadata["page_ref"] == "VII (7)"
    assert (
        chunk_result.hits[0].metadata["image_caption"]
        == "Diagram of the archive ledger seal."
    )
    assert chunk_result.hits[0].metadata["context_header"]
    assert chunk_result.hits[0].metadata["contextual_text_version"] == "v2"
    assert "Page: VII (7)" in chunk_result.hits[0].metadata["contextual_text"]
    assert (
        "Image: Diagram of the archive ledger seal."
        in chunk_result.hits[0].metadata["contextual_text"]
    )
    assert chunk_result.hits[0].hit_id.startswith("chunk_")
    assert document_result.hits
    assert document_result.hits[0].metadata["result_kind"] == "document"
    assert document_result.hits[0].hit_id == "doc:asset-search"
    assert document_result.trace is not None
    assert document_result.trace.result_kind == "document"
    assert document_result.trace.retriever_routes
    assert "document_result_builder" in document_result.trace.pipeline_stages
    assert rag_result.hits
    assert rag_result.hits[0].metadata["result_kind"] == "rag"
    assert rag_result.hits[0].metadata["rag_context_header"]
    assert rag_result.hits[0].metadata["rag_document_summary"]
    assert rag_result.hits[0].excerpt_text.startswith("Context:")
    assert "Page: VII (7)" in rag_result.hits[0].excerpt_text
    assert (
        "Image: Diagram of the archive ledger seal." in rag_result.hits[0].excerpt_text
    )
    assert rag_result.trace is not None
    assert rag_result.trace.result_kind == "rag"
    assert "rag_context_builder" in rag_result.trace.pipeline_stages


@pytest.mark.asyncio
async def test_retrieval_service_uses_explicit_pipeline_slots(retrieval_session):
    class StubPreprocessor:
        def __init__(self) -> None:
            self.seen_queries: list[RetrievalQuery] = []

        def preprocess(self, query: RetrievalQuery) -> RetrievalQuery:
            self.seen_queries.append(query)
            return query.model_copy(update={"text_query": "normalized slot query"})

    class StubRetriever:
        def __init__(self, *, route: str, score: float) -> None:
            self.route = route
            self.score = score
            self.seen_queries: list[RetrievalQuery] = []

        async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
            self.seen_queries.append(query)
            return RetrievalSearchResult(
                query=query.text_query or "",
                hits=[
                    RetrievalHit(
                        hit_id=f"{self.route}:hit",
                        query_id=query.query_id,
                        layer="archival",
                        domain=Domain.WORLD_RULE,
                        domain_path="foundation.world.slot",
                        excerpt_text=f"excerpt from {self.route}",
                        score=self.score,
                        rank=1,
                        metadata={
                            "asset_id": "asset-slot",
                            "collection_id": "story-slot:archival",
                            "title": "Slot Rule",
                            "section_id": "slot-1",
                            "section_part": 0,
                            "source_ref": "memory://slot",
                            "commit_id": "commit-slot",
                        },
                    )
                ],
                trace=RetrievalTrace(
                    trace_id=f"trace-{self.route}",
                    query_id=query.query_id,
                    route=self.route,
                    candidate_count=1,
                    returned_count=1,
                    timings={f"{self.route}_ms": 1.0},
                ),
            )

    class StubFusionStrategy:
        def __init__(self) -> None:
            self.received_query: RetrievalQuery | None = None
            self.received_results: list[RetrievalSearchResult] = []

        def fuse(
            self,
            *,
            query: RetrievalQuery,
            retrieved_results: list[RetrievalSearchResult],
        ) -> RetrievalSearchResult:
            self.received_query = query
            self.received_results = list(retrieved_results)
            return retrieved_results[0].model_copy(
                update={
                    "query": query.text_query or "",
                    "trace": RetrievalTrace(
                        trace_id="trace-fused",
                        query_id=query.query_id,
                        route="fusion.stub",
                        candidate_count=2,
                        returned_count=1,
                        timings={"fusion_stub_ms": 1.0},
                    ),
                    "warnings": ["fused"],
                }
            )

    class StubReranker:
        def __init__(self) -> None:
            self.seen_query: RetrievalQuery | None = None
            self.seen_result: RetrievalSearchResult | None = None

        async def rerank(
            self,
            *,
            query: RetrievalQuery,
            result: RetrievalSearchResult,
        ) -> RetrievalSearchResult:
            self.seen_query = query
            self.seen_result = result
            return result.model_copy(
                update={"warnings": [*result.warnings, "reranked"]}
            )

    class StubChunkResultBuilder:
        def __init__(self) -> None:
            self.seen_query: RetrievalQuery | None = None
            self.seen_result: RetrievalSearchResult | None = None

        def build(
            self,
            *,
            query: RetrievalQuery,
            result: RetrievalSearchResult,
        ) -> RetrievalSearchResult:
            self.seen_query = query
            self.seen_result = result
            return result.model_copy(
                update={
                    "query": query.text_query or "",
                    "warnings": [*result.warnings, "built"],
                }
            )

    preprocessor = StubPreprocessor()
    retriever_a = StubRetriever(route="keyword.stub", score=0.8)
    retriever_b = StubRetriever(route="semantic.stub", score=0.7)
    fusion_strategy = StubFusionStrategy()
    reranker = StubReranker()
    chunk_builder = StubChunkResultBuilder()

    service = RetrievalService(
        retrieval_session,
        query_preprocessor=preprocessor,
        retrievers=[retriever_a, retriever_b],
        fusion_strategy=fusion_strategy,
        reranker=reranker,
        chunk_result_builder=chunk_builder,
    )
    query = RetrievalQuery(
        query_id="rq-slot",
        query_kind="archival",
        story_id="story-slot",
        domains=[Domain.WORLD_RULE],
        text_query=" raw slot query ",
        filters={},
        top_k=2,
    )

    result = await service.search_chunks(query)

    assert preprocessor.seen_queries[0].text_query == " raw slot query "
    assert retriever_a.seen_queries[0].text_query == "normalized slot query"
    assert retriever_b.seen_queries[0].text_query == "normalized slot query"
    assert fusion_strategy.received_query is not None
    assert fusion_strategy.received_query.text_query == "normalized slot query"
    assert len(fusion_strategy.received_results) == 2
    assert reranker.seen_query is not None
    assert reranker.seen_query.text_query == "normalized slot query"
    assert chunk_builder.seen_query is not None
    assert chunk_builder.seen_query.text_query == "normalized slot query"
    assert result.query == "normalized slot query"
    assert result.warnings == ["fused", "reranked", "built"]


@pytest.mark.asyncio
async def test_retrieval_service_emits_langfuse_observation(retrieval_session):
    class StubRetriever:
        async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
            return RetrievalSearchResult(
                query=query.text_query or "",
                hits=[
                    RetrievalHit(
                        hit_id="chunk-observation",
                        query_id=query.query_id,
                        layer="archival",
                        domain=Domain.WORLD_RULE,
                        domain_path="foundation.world.obs",
                        excerpt_text="Observation friendly excerpt",
                        score=0.77,
                        rank=1,
                        metadata={
                            "asset_id": "asset-observation",
                            "title": "Observation Rule",
                            "section_id": "obs-1",
                            "section_part": 0,
                            "page_label": "IV",
                            "contextual_text_version": "v2",
                        },
                    )
                ],
                trace=RetrievalTrace(
                    trace_id="trace-observation",
                    query_id=query.query_id,
                    route="retrieval.keyword.stub",
                    result_kind="chunk",
                    retriever_routes=["retrieval.keyword.stub"],
                    pipeline_stages=["retrieve", "chunk_result_builder"],
                    candidate_count=1,
                    returned_count=1,
                    timings={"keyword_ms": 1.0},
                ),
            )

    class StubReranker:
        async def rerank(
            self, *, query: RetrievalQuery, result: RetrievalSearchResult
        ) -> RetrievalSearchResult:
            return result

    fake_langfuse = _FakeLangfuseService()
    service = RetrievalService(
        retrieval_session,
        retrievers=[StubRetriever()],
        reranker=StubReranker(),
        langfuse_service=fake_langfuse,
    )
    query = RetrievalQuery(
        query_id="rq-observation",
        query_kind="archival",
        story_id="story-observation",
        domains=[Domain.WORLD_RULE],
        text_query="observation query",
        filters={},
        top_k=1,
    )

    result = await service.search_chunks(query)

    assert result.hits[0].hit_id == "chunk-observation"
    observation_names = [
        item["name"]
        for item in fake_langfuse.events
        if item["kind"] == "observation_enter"
    ]
    assert "rp.retrieval.search_chunks" in observation_names
    updates = [
        item["payload"]["output"]
        for item in fake_langfuse.events
        if item["kind"] == "observation_update"
        and item["name"] == "rp.retrieval.search_chunks"
    ]
    assert updates
    observability = updates[-1]["observability"]
    assert updates[-1]["status"] == "ok"
    assert updates[-1]["search_kind"] == "chunks"
    assert observability["route"].startswith("retrieval.keyword.stub")
    assert observability["returned_count"] == 1
    assert observability["top_hits"][0]["asset_id"] == "asset-observation"
    assert observability["top_hits"][0]["block_view"]["source"] == "retrieval_store"
    assert observability["top_hits"][0]["block_view"]["block_id"].startswith(
        "retrieval.archival.rq-observation."
    )
    assert observability["top_hits"][0]["block_view"]["block_id"].endswith(
        ".chunk-observation"
    )


@pytest.mark.asyncio
async def test_simple_metadata_reranker_can_promote_metadata_aligned_hit(
    retrieval_session,
):
    class StubRetriever:
        async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
            return RetrievalSearchResult(
                query=query.text_query or "",
                hits=[
                    RetrievalHit(
                        hit_id="chunk-a",
                        query_id=query.query_id,
                        layer="archival",
                        domain=Domain.WORLD_RULE,
                        domain_path="foundation.world.misc",
                        excerpt_text="A generic rule.",
                        score=0.61,
                        rank=1,
                        metadata={
                            "asset_id": "asset-a",
                            "title": "Generic Rule",
                            "domain_path": "foundation.world.misc",
                            "section_id": "a",
                            "section_part": 0,
                        },
                    ),
                    RetrievalHit(
                        hit_id="chunk-b",
                        query_id=query.query_id,
                        layer="archival",
                        domain=Domain.WORLD_RULE,
                        domain_path="foundation.world.moon_gate",
                        excerpt_text="Moon gate rituals must be witnessed at dawn.",
                        score=0.58,
                        rank=2,
                        metadata={
                            "asset_id": "asset-b",
                            "title": "Moon Gate Ritual",
                            "domain_path": "foundation.world.moon_gate",
                            "tags": ["moon", "ritual"],
                            "section_id": "b",
                            "section_part": 0,
                        },
                    ),
                ],
                trace=RetrievalTrace(
                    trace_id="trace-keyword",
                    query_id=query.query_id,
                    route="keyword.stub",
                    result_kind="chunk",
                    retriever_routes=["keyword.stub"],
                    pipeline_stages=["retrieve"],
                    candidate_count=2,
                    returned_count=2,
                    timings={"keyword_ms": 1.0},
                ),
            )

    service = RetrievalService(retrieval_session, retrievers=[StubRetriever()])
    result = await service.search_chunks(
        RetrievalQuery(
            query_id="rq-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            filters={},
            top_k=2,
            rerank=True,
        )
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert result.hits[0].score > result.hits[1].score
    assert result.trace is not None
    assert result.trace.reranker_name == "simple_metadata"
    assert "rerank" in result.trace.pipeline_stages


@pytest.mark.asyncio
async def test_simple_metadata_reranker_records_narrative_scoring_trace():
    result = RetrievalSearchResult(
        query="scene continuity",
        hits=[
            RetrievalHit(
                hit_id="chunk-generic",
                query_id="rq-narrative-rerank",
                layer="recall",
                domain=Domain.CHAPTER,
                domain_path="recall.chapter.1.generic",
                excerpt_text="Generic continuity note.",
                score=0.7,
                rank=1,
                metadata={
                    "asset_id": "asset-generic",
                    "canon_status": "superseded",
                    "chapter_index": 8,
                },
            ),
            RetrievalHit(
                hit_id="chunk-scene",
                query_id="rq-narrative-rerank",
                layer="recall",
                domain=Domain.CHAPTER,
                domain_path="recall.chapter.1.scene",
                excerpt_text="Current scene continuity note.",
                score=0.62,
                rank=2,
                metadata={
                    "asset_id": "asset-scene",
                    "scene_ref": "chapter:1:scene:1",
                    "character_refs": ["hero"],
                    "canon_status": "canonical",
                    "chapter_index": 2,
                },
            ),
        ],
        trace=RetrievalTrace(
            trace_id="trace-narrative-rerank",
            query_id="rq-narrative-rerank",
            route="retrieval.hybrid.stub",
            result_kind="chunk",
            pipeline_stages=["retrieve", "fusion"],
            candidate_count=2,
            returned_count=2,
        ),
    )

    reranked = await SimpleMetadataReranker().rerank(
        query=RetrievalQuery(
            query_id="rq-narrative-rerank",
            query_kind="recall",
            story_id="story-narrative-rerank",
            domains=[Domain.CHAPTER],
            text_query="scene continuity",
            filters={
                "scene_refs": ["chapter:1:scene:1"],
                "character_refs": ["hero"],
                "search_policy": {
                    "profile": "longform",
                    "rerank": "on",
                    "context": {"current_chapter_index": 2},
                },
            },
            top_k=2,
            rerank=True,
        ),
        result=result,
    )

    assert reranked.hits[0].hit_id == "chunk-scene"
    assert reranked.trace is not None
    scoring = reranked.trace.details["narrative_scoring"]
    assert scoring["profile"] == "longform"
    rules = {item["hit_id"]: item for item in scoring["rules"]}
    assert rules["chunk-scene"]["boosts"]["scene_match"] == 0.2
    assert rules["chunk-scene"]["boosts"]["character_match"] == 0.12
    assert rules["chunk-scene"]["boosts"]["chapter_distance"] == 0.08
    assert rules["chunk-generic"]["penalties"]["non_canonical_status"] == -0.25


def test_rag_context_builder_records_budget_selected_and_excluded_hits():
    result = RetrievalSearchResult(
        query="budget",
        hits=[
            RetrievalHit(
                hit_id="chunk-a",
                query_id="rq-budget",
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.a",
                excerpt_text="First selected section.",
                score=0.9,
                rank=1,
                metadata={
                    "asset_id": "asset-a",
                    "source_family": "setup_source",
                    "domain": "world_rule",
                    "token_count": 3,
                },
            ),
            RetrievalHit(
                hit_id="chunk-a-dup",
                query_id="rq-budget",
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.a.dup",
                excerpt_text="Duplicate section.",
                score=0.8,
                rank=2,
                metadata={
                    "asset_id": "asset-a",
                    "source_family": "setup_source",
                    "domain": "world_rule",
                    "token_count": 2,
                },
            ),
            RetrievalHit(
                hit_id="chunk-b",
                query_id="rq-budget",
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.b",
                excerpt_text="Over budget section.",
                score=0.7,
                rank=3,
                metadata={
                    "asset_id": "asset-b",
                    "source_family": "setup_source",
                    "domain": "world_rule",
                    "token_count": 10,
                },
            ),
        ],
        trace=RetrievalTrace(
            trace_id="trace-budget",
            query_id="rq-budget",
            route="retrieval.hybrid.stub",
            result_kind="chunk",
            filters_applied={
                "filters": {
                    "search_policy": {
                        "context_budget": {
                            "max_tokens": 6,
                            "per_source_family": {"setup_source": 6},
                            "per_domain": {"world_rule": 6},
                        }
                    }
                }
            },
        ),
    )

    built = RagContextBuilder().build(result)

    assert [hit.hit_id for hit in built.hits] == ["chunk-a"]
    assert built.trace is not None
    budget = built.trace.details["context_budget"]
    assert budget["selected"][0]["hit_id"] == "chunk-a"
    excluded = {item["hit_id"]: item["reason"] for item in budget["excluded"]}
    assert excluded["chunk-a-dup"] == "duplicate_asset"
    assert excluded["chunk-b"] == "token_budget"


@pytest.mark.asyncio
async def test_search_chunks_short_circuits_empty_query_even_with_active_embeddings(
    retrieval_session,
):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-empty-query",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-empty-query",
            story_id="story-empty-query",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            commit_id="commit-empty-query",
            asset_kind="worldbook",
            source_ref="memory://asset-empty-query",
            title="Empty Query Asset",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "empty-1",
                        "title": "Rule",
                        "path": "foundation.world.empty_query_rule",
                        "level": 1,
                        "text": "Empty queries should not retrieve semantic neighbors.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.empty_query_rule",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id="story-empty-query",
        asset_id="asset-empty-query",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    result = await RetrievalService(retrieval_session).search_chunks(
        RetrievalQuery(
            query_id="rq-empty-query",
            query_kind="archival",
            story_id="story-empty-query",
            domains=[Domain.WORLD_RULE],
            text_query="   ",
            filters={"knowledge_collections": [collection.collection_id]},
            top_k=3,
        )
    )

    assert result.hits == []
    assert "keyword_unavailable:empty_query" in result.warnings
    assert "dense_unavailable:empty_query" in result.warnings
    assert result.trace is not None
    assert result.trace.route == "retrieval.hybrid.empty"
