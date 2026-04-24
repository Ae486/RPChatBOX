"""Tests for retrieval parser/chunker/hybrid component behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from rp.models.retrieval_records import KnowledgeChunk
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.retrieval.chunker import Chunker
from rp.retrieval.embedder import Embedder, _EmbeddingTarget
from rp.retrieval.hybrid_retriever import HybridRetriever
from rp.retrieval.parser import Parser


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _source_asset(
    *,
    asset_id: str = "asset-1",
    source_ref: str = "memory://asset-1",
    storage_path: str | None = None,
    raw_excerpt: str | None = None,
    metadata: dict[str, object] | None = None,
) -> SourceAsset:
    return SourceAsset(
        asset_id=asset_id,
        story_id="story-components",
        mode=StoryMode.LONGFORM,
        asset_kind="worldbook",
        source_ref=source_ref,
        title="Component Asset",
        storage_path=storage_path,
        raw_excerpt=raw_excerpt,
        parse_status="queued",
        ingestion_status="queued",
        metadata=metadata or {},
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def test_parser_prefers_seed_sections_over_other_sources(tmp_path):
    raw_file = tmp_path / "asset.txt"
    raw_file.write_text("raw file fallback text", encoding="utf-8")
    asset = _source_asset(
        storage_path=str(raw_file),
        raw_excerpt="excerpt fallback",
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-1",
                    "title": "Seed Section",
                    "path": "foundation.seed",
                    "level": 1,
                    "text": "seed section text",
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.seed"},
                }
            ],
            "parsed_payload": {
                "sections": [
                    {
                        "section_id": "payload-1",
                        "title": "Payload Section",
                        "path": "foundation.payload",
                        "level": 1,
                        "text": "payload section text",
                        "metadata": {"domain": "world_rule", "domain_path": "foundation.payload"},
                    }
                ]
            },
        },
    )

    document = Parser().parse(asset)

    assert document.parser_kind == "seed_sections"
    assert document.document_structure[0].section_id == "seed-1"
    assert document.document_structure[0].text == "seed section text"


def test_parser_uses_structured_payload_before_raw_file(tmp_path):
    raw_file = tmp_path / "asset.txt"
    raw_file.write_text("raw file fallback text", encoding="utf-8")
    asset = _source_asset(
        storage_path=str(raw_file),
        metadata={
            "parsed_payload": {
                "sections": [
                    {
                        "section_id": "payload-1",
                        "title": "Payload Section",
                        "path": "foundation.payload",
                        "level": 1,
                        "text": "payload section text",
                        "metadata": {"domain": "world_rule", "domain_path": "foundation.payload"},
                    }
                ]
            }
        },
    )

    document = Parser().parse(asset)

    assert document.parser_kind == "structured_payload"
    assert document.document_structure[0].section_id == "payload-1"


def test_parser_promotes_page_and_image_fields_into_section_metadata():
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-page-1",
                    "title": "Illustrated Section",
                    "path": "foundation.page.1",
                    "level": 1,
                    "page_no": 7,
                    "page_label": "7",
                    "image_caption": "A moon gate diagram.",
                    "text": "Illustrated moon gate rule text.",
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.page.1"},
                }
            ]
        },
    )

    document = Parser().parse(asset)

    assert document.document_structure[0].metadata["page_no"] == 7
    assert document.document_structure[0].metadata["page_label"] == "7"
    assert document.document_structure[0].metadata["image_caption"] == "A moon gate diagram."


def test_parser_enriches_page_and_image_metadata_from_nested_structures():
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-rich-1",
                    "title": "Rich Section",
                    "path": "foundation.page.rich",
                    "level": 1,
                    "text": "Nested page and image metadata should be normalized.",
                    "metadata": {
                        "domain": "world_rule",
                        "domain_path": "foundation.page.rich",
                        "page": {"no": 14, "label": "XIV"},
                        "images": [
                            {"caption": "Moon gate overview."},
                            {"caption": "Seal placement close-up."},
                        ],
                    },
                }
            ]
        },
    )

    document = Parser().parse(asset)

    assert document.document_structure[0].metadata["page_no"] == 14
    assert document.document_structure[0].metadata["page_label"] == "XIV"
    assert document.document_structure[0].metadata["image_caption"] == (
        "Moon gate overview. | Seal placement close-up."
    )


def test_parser_falls_back_to_raw_file_before_excerpt(tmp_path):
    raw_file = tmp_path / "asset.txt"
    raw_file.write_text("raw file fallback text", encoding="utf-8")
    asset = _source_asset(
        storage_path=str(raw_file),
        raw_excerpt="excerpt fallback",
    )

    document = Parser().parse(asset)

    assert document.parser_kind == "raw_file"
    assert document.document_structure[0].text == "raw file fallback text"


def test_chunker_keeps_short_section_whole_and_inherits_metadata():
    parser = Parser()
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-1",
                    "title": "Seed Section",
                    "path": "foundation.seed",
                    "level": 1,
                    "text": "short section text",
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.seed"},
                }
            ]
        },
    )
    document = parser.parse(asset)

    chunks = Chunker(max_chars=200).chunk(
        document,
        story_id=asset.story_id,
        asset_id=asset.asset_id,
        collection_id="story-components:archival",
        source_ref=asset.source_ref,
        commit_id="commit-components",
        asset_title=asset.title,
        asset_summary="Document summary for the component asset.",
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["section_id"] == "seed-1"
    assert chunks[0].metadata["section_part"] == 0
    assert chunks[0].metadata["chunk_view"] == "primary"
    assert chunks[0].metadata["chunk_size"] == "default"
    assert chunks[0].metadata["chunk_pass"] == 0
    assert chunks[0].metadata["source_ref"] == "memory://asset-1"
    assert chunks[0].metadata["commit_id"] == "commit-components"
    assert chunks[0].metadata["document_title"] == "Component Asset"
    assert chunks[0].metadata["document_summary"] == "Document summary for the component asset."
    assert "Component Asset" in chunks[0].metadata["context_header"]
    assert chunks[0].metadata["contextual_text"].startswith("Context:")


def test_chunker_falls_back_to_fixed_primary_slices_for_single_long_paragraph():
    parser = Parser()
    long_text = "alpha" * 160
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-fixed-slice",
                    "title": "Single Paragraph",
                    "path": "foundation.fixed.slice",
                    "level": 1,
                    "text": long_text,
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.fixed.slice"},
                }
            ]
        },
    )
    document = parser.parse(asset)

    chunks = Chunker(max_chars=120).chunk(
        document,
        story_id=asset.story_id,
        asset_id=asset.asset_id,
        collection_id="story-components:archival",
    )

    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 120 for chunk in chunks)
    assert all(chunk.metadata["chunk_view"] == "primary" for chunk in chunks)
    assert all(chunk.metadata["chunking_strategy"] == "fixed_slice" for chunk in chunks)


def test_chunker_splits_long_section_into_multiple_parts():
    parser = Parser()
    long_text = "alpha paragraph\nbeta paragraph\n" * 40
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-long",
                    "title": "Long Section",
                    "path": "foundation.long",
                    "level": 1,
                    "text": long_text,
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.long"},
                }
            ]
        },
    )
    document = parser.parse(asset)

    chunks = Chunker(max_chars=80).chunk(
        document,
        story_id=asset.story_id,
        asset_id=asset.asset_id,
        collection_id="story-components:archival",
    )

    assert len(chunks) > 1
    assert chunks[0].metadata["section_part"] == 0
    assert chunks[1].metadata["section_part"] == 1


def test_chunker_generates_secondary_windows_for_large_primary_chunks():
    parser = Parser()
    long_text = ("alpha paragraph " * 15) + "\n" + ("beta paragraph " * 15) + "\n" + ("gamma paragraph " * 15)
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-multipass",
                    "title": "Multi Pass Section",
                    "path": "foundation.multi.pass",
                    "level": 1,
                    "text": long_text,
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.multi.pass"},
                }
            ]
        },
    )
    document = parser.parse(asset)

    chunks = Chunker(
        max_chars=900,
        secondary_max_chars=320,
        secondary_overlap_chars=80,
        secondary_trigger_chars=500,
    ).chunk(
        document,
        story_id=asset.story_id,
        asset_id=asset.asset_id,
        collection_id="story-components:archival",
    )

    primary_chunks = [chunk for chunk in chunks if chunk.metadata["chunk_view"] == "primary"]
    secondary_chunks = [chunk for chunk in chunks if chunk.metadata["chunk_view"] == "secondary"]

    assert len(primary_chunks) == 1
    assert len(secondary_chunks) >= 2
    assert primary_chunks[0].metadata["chunk_pass"] == 0
    assert primary_chunks[0].metadata["chunk_size"] == "default"
    assert primary_chunks[0].metadata["chunk_family_id"] == "seed-multipass:0"
    assert secondary_chunks[0].metadata["chunk_pass"] == 1
    assert secondary_chunks[0].metadata["chunk_size"] == "small"
    assert secondary_chunks[0].metadata["parent_section_part"] == 0
    assert secondary_chunks[0].metadata["chunk_family_id"] == "seed-multipass:0"
    assert all(len(chunk.text) <= 320 for chunk in secondary_chunks)
    assert all(chunk.metadata["char_start"] < chunk.metadata["char_end"] for chunk in chunks)


def test_chunker_preserves_page_and_image_metadata_fields():
    parser = Parser()
    asset = _source_asset(
        metadata={
            "seed_sections": [
                {
                    "section_id": "seed-page-aware",
                    "title": "Page Aware Section",
                    "path": "foundation.page.aware",
                    "level": 1,
                    "page_no": 12,
                    "page_label": "XII",
                    "image_caption": "Illustration of the gate mechanism.",
                    "text": "Page aware section text",
                    "metadata": {"domain": "world_rule", "domain_path": "foundation.page.aware"},
                }
            ]
        },
    )
    document = parser.parse(asset)

    chunks = Chunker(max_chars=200).chunk(
        document,
        story_id=asset.story_id,
        asset_id=asset.asset_id,
        collection_id="story-components:archival",
    )

    assert chunks[0].metadata["page_no"] == 12
    assert chunks[0].metadata["page_label"] == "XII"
    assert chunks[0].metadata["page_ref"] == "XII (12)"
    assert chunks[0].metadata["image_caption"] == "Illustration of the gate mechanism."
    assert chunks[0].metadata["contextual_text_version"] == "v2"
    assert "Page: XII (12)" in chunks[0].metadata["contextual_text"]
    assert "Image: Illustration of the gate mechanism." in chunks[0].metadata["contextual_text"]


def test_embedder_prefers_contextual_text_when_present():
    class CapturingEmbedder(Embedder):
        def __init__(self) -> None:
            super().__init__(fallback_dim=8)
            self.captured_texts: list[str] = []

        def _resolve_target(self) -> _EmbeddingTarget:
            return _EmbeddingTarget(
                provider_id="capture",
                model_name="capture-model",
                runtime_provider=None,
            )

        def _embed_texts(self, texts, *, target):
            self.captured_texts = list(texts)
            return [[0.1] * 8 for _ in texts]

    chunk = KnowledgeChunk(
        chunk_id="chunk-context",
        story_id="story-components",
        asset_id="asset-1",
        parsed_document_id="pd-1",
        chunk_index=0,
        domain="world_rule",
        text="raw chunk body",
        metadata={
            "contextual_text": "Context: Component Asset :: Seed Section :: foundation.seed\nSummary: summary\nraw chunk body"
        },
        provenance_refs=[],
        created_at=_utcnow(),
    )

    embedder = CapturingEmbedder()
    embeddings = embedder.embed([chunk])

    assert embeddings[0].embedding_model == "capture-model"
    assert embedder.captured_texts == [
        "Context: Component Asset :: Seed Section :: foundation.seed\nSummary: summary\nraw chunk body"
    ]


@pytest.mark.asyncio
async def test_hybrid_retriever_degrades_to_single_available_source():
    class StubRetriever:
        def __init__(self, result: RetrievalSearchResult) -> None:
            self._result = result

        async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
            return self._result

    query = RetrievalQuery(
        query_id="rq-hybrid-degraded",
        query_kind="archival",
        story_id="story-components",
        domains=[Domain.WORLD_RULE],
        text_query="moon gate",
        top_k=2,
    )
    keyword_result = RetrievalSearchResult(
        query=query.text_query or "",
        hits=[
            RetrievalHit(
                hit_id="chunk-keyword",
                query_id=query.query_id,
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.moon_gate",
                excerpt_text="moon gate rule",
                score=0.7,
                rank=1,
                metadata={"asset_id": "asset-keyword"},
            )
        ],
        trace=RetrievalTrace(
            trace_id="trace-keyword",
            query_id=query.query_id,
            route="retrieval.keyword.lexical",
            retriever_routes=["retrieval.keyword.lexical"],
            pipeline_stages=["retrieve"],
        ),
    )
    semantic_result = RetrievalSearchResult(
        query=query.text_query or "",
        hits=[],
        trace=RetrievalTrace(
            trace_id="trace-semantic",
            query_id=query.query_id,
            route="retrieval.semantic.empty",
            retriever_routes=["retrieval.semantic.empty"],
            pipeline_stages=["retrieve"],
        ),
    )

    result = await HybridRetriever(
        keyword_retriever=StubRetriever(keyword_result),
        semantic_retriever=StubRetriever(semantic_result),
    ).search(query)

    assert result.hits[0].hit_id == "chunk-keyword"
    assert result.trace is not None
    assert result.trace.route == "retrieval.keyword.lexical.degraded"


@pytest.mark.asyncio
async def test_hybrid_retriever_uses_rrf_when_both_sources_return_hits():
    class StubRetriever:
        def __init__(self, result: RetrievalSearchResult) -> None:
            self._result = result

        async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
            return self._result

    query = RetrievalQuery(
        query_id="rq-hybrid-rrf",
        query_kind="archival",
        story_id="story-components",
        domains=[Domain.WORLD_RULE],
        text_query="moon gate",
        top_k=3,
    )
    keyword_result = RetrievalSearchResult(
        query=query.text_query or "",
        hits=[
            RetrievalHit(
                hit_id="chunk-shared",
                query_id=query.query_id,
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.moon_gate",
                excerpt_text="shared keyword hit",
                score=0.9,
                rank=1,
                metadata={"asset_id": "asset-shared"},
            )
        ],
        trace=RetrievalTrace(
            trace_id="trace-keyword",
            query_id=query.query_id,
            route="retrieval.keyword.lexical",
            retriever_routes=["retrieval.keyword.lexical"],
            pipeline_stages=["retrieve"],
        ),
    )
    semantic_result = RetrievalSearchResult(
        query=query.text_query or "",
        hits=[
            RetrievalHit(
                hit_id="chunk-shared",
                query_id=query.query_id,
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.moon_gate",
                excerpt_text="shared semantic hit",
                score=0.8,
                rank=1,
                metadata={"asset_id": "asset-shared"},
            ),
            RetrievalHit(
                hit_id="chunk-semantic-only",
                query_id=query.query_id,
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.semantic",
                excerpt_text="semantic only hit",
                score=0.6,
                rank=2,
                metadata={"asset_id": "asset-semantic"},
            ),
        ],
        trace=RetrievalTrace(
            trace_id="trace-semantic",
            query_id=query.query_id,
            route="retrieval.semantic.python",
            retriever_routes=["retrieval.semantic.python"],
            pipeline_stages=["retrieve"],
        ),
    )

    result = await HybridRetriever(
        keyword_retriever=StubRetriever(keyword_result),
        semantic_retriever=StubRetriever(semantic_result),
    ).search(query)

    assert result.trace is not None
    assert result.trace.route == "retrieval.hybrid.rrf"
    assert result.trace.retriever_routes == [
        "retrieval.keyword.lexical",
        "retrieval.semantic.python",
    ]
    assert result.hits[0].hit_id == "chunk-shared"
