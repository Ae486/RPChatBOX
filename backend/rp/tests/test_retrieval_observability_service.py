"""Tests for retrieval observability view generation."""

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
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_observability_service import RetrievalObservabilityService
from rp.services.retrieval_service import RetrievalService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_story_and_search(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-observability",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-observability",
            story_id="story-observability",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            commit_id="commit-observability",
            asset_kind="worldbook",
            source_ref="memory://asset-observability",
            title="Observability Ledger",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "obs-1",
                        "title": "Observability Rule",
                        "path": "foundation.world.observability_rule",
                        "level": 1,
                        "page_no": 11,
                        "page_label": "XI",
                        "image_caption": "Observability diagram.",
                        "text": "Observability requires route, timing, and rerank visibility.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.observability_rule",
                            "tags": ["observability"],
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
        story_id="story-observability",
        asset_id="asset-observability",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    query = RetrievalQuery(
        query_id="rq-observability",
        query_kind="archival",
        story_id="story-observability",
        domains=[Domain.WORLD_RULE],
        text_query="observability rerank timing",
        filters={"knowledge_collections": [collection.collection_id]},
        top_k=3,
        rerank=True,
    )
    result = await RetrievalService(retrieval_session).search_chunks(query)
    return query, result


@pytest.mark.asyncio
async def test_observability_view_includes_trace_hits_and_maintenance(
    retrieval_session,
):
    query, result = await _seed_story_and_search(retrieval_session)

    view = RetrievalObservabilityService(retrieval_session).build_view(
        query=query,
        result=result,
    )

    assert view.query_id == "rq-observability"
    assert view.story_id == "story-observability"
    assert view.route is not None and view.route.startswith("retrieval.")
    assert view.pipeline_stages
    assert view.candidate_count >= 1
    assert view.returned_count >= 1
    assert view.top_hits[0].asset_id == "asset-observability"
    assert view.top_hits[0].page_no == 11
    assert view.top_hits[0].page_label == "XI"
    assert view.top_hits[0].page_ref == "XI (11)"
    assert view.top_hits[0].image_caption == "Observability diagram."
    assert view.top_hits[0].contextual_text_version == "v2"
    assert view.top_hits[0].block_view is not None
    assert view.top_hits[0].block_view.source == "retrieval_store"
    assert view.top_hits[0].block_view.label == view.top_hits[0].hit_id
    assert (
        view.top_hits[0].block_view.data_json["excerpt_text"]
        == "Observability requires route, timing, and rerank visibility."
    )
    assert view.maintenance is not None
    assert view.maintenance.story_id == "story-observability"
    assert view.maintenance.collection_count == 1
    assert view.maintenance.asset_count == 1
    assert view.maintenance.active_chunk_count >= 1
    rerank_details = view.details.get("rerank")
    if rerank_details is not None:
        assert rerank_details["backend_name"] in {
            "hosted",
            "local_cross_encoder",
            "chain",
        }


def test_observability_view_buckets_warnings_and_preserves_rerank_details():
    query = RetrievalQuery(
        query_id="rq-warning-view",
        query_kind="archival",
        story_id="story-warning-view",
        domains=[Domain.WORLD_RULE],
        text_query="warning view",
        filters={},
        top_k=2,
        rerank=True,
    )
    result = RetrievalSearchResult(
        query="warning view",
        hits=[
            RetrievalHit(
                hit_id="chunk-warning",
                query_id=query.query_id,
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.warning",
                excerpt_text="warning excerpt",
                score=0.81,
                rank=1,
                metadata={
                    "asset_id": "asset-warning",
                    "title": "Warning Rule",
                    "page_label": "V",
                    "contextual_text_version": "v2",
                },
            )
        ],
        trace=RetrievalTrace(
            trace_id="trace-warning-view",
            query_id=query.query_id,
            route="retrieval.hybrid.rrf",
            result_kind="chunk",
            retriever_routes=["retrieval.keyword.lexical", "retrieval.semantic.python"],
            pipeline_stages=["retrieve", "fusion", "rerank"],
            reranker_name="cross_encoder_hosted",
            candidate_count=4,
            returned_count=1,
            timings={"keyword_ms": 1.0, "semantic_ms": 2.0, "rerank_ms": 3.0},
            warnings=[
                "dense_unavailable:empty_query",
                "rerank_backend_failed:TimeoutError",
            ],
            details={
                "rerank": {
                    "backend_name": "hosted",
                    "model_id": "model-rerank",
                    "provider_id": "provider-rerank",
                    "used_backend_result": False,
                }
            },
        ),
        warnings=[
            "dense_unavailable:empty_query",
            "rerank_backend_failed:TimeoutError",
        ],
    )

    view = RetrievalObservabilityService().build_view(
        query=query,
        result=result,
        include_story_snapshot=False,
    )

    assert view.maintenance is None
    assert view.warning_buckets[0].category == "dense_unavailable"
    assert view.warning_buckets[0].count == 1
    assert view.warning_buckets[1].category == "rerank_backend_failed"
    assert view.warning_buckets[1].count == 1
    assert view.details["rerank"]["backend_name"] == "hosted"
    assert view.details["rerank"]["used_backend_result"] is False
    assert view.top_hits[0].page_label == "V"
    assert view.top_hits[0].block_view is not None
    assert view.top_hits[0].block_view.source == "retrieval_store"
    assert view.top_hits[0].block_view.label == "chunk-warning"
