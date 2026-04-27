"""Tests for the DB-backed retrieval broker."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config import get_settings
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalHit,
    RetrievalSearchResult,
    RetrievalTrace,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_os_service import MemoryOsService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.story_session_service import StorySessionService
from rp.models.story_runtime import LongformChapterPhase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _seed_story_runtime(retrieval_session) -> None:
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={"style_rules": ["Keep continuity"]},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [{"event": "opening"}],
            "active_threads": [{"thread_id": "t-1", "summary": "Open thread"}],
            "foreshadow_registry": [{"foreshadow_id": "f-1", "summary": "Hidden clue"}],
            "character_state_digest": {"hero": {"mood": "alert"}},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Open strong",
        builder_snapshot_json={
            "foundation_digest": ["Found A", "Found B"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A", "State B"],
            "writer_hints": ["Hint A"],
        },
    )
    service.commit()


@pytest.mark.asyncio
async def test_get_state_reads_materialized_authoritative_domain(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")
    result = await broker.get_state(MemoryGetStateInput(domain=Domain.CHAPTER))

    assert result.items[0].object_ref.object_id == "chapter.current"
    assert result.items[0].data["current_chapter"] == 1
    assert result.items[0].data["title"] == "Chapter One"
    assert result.items[0].warnings == []


@pytest.mark.asyncio
async def test_get_state_returns_warning_for_unmaterialized_domain(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")

    result = await broker.get_state(MemoryGetStateInput(domain=Domain.SCENE))

    assert result.items[0].object_ref.object_id == "scene.current"
    assert result.items[0].data == {}
    assert (
        "phase_e_authoritative_ref_not_materialized:scene.current"
        in result.items[0].warnings
    )


@pytest.mark.asyncio
async def test_get_state_reads_explicit_unmapped_authoritative_ref_from_block_store(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    story_session = StorySessionService(retrieval_session).get_latest_session_for_story(
        "story-1"
    )
    assert story_session is not None
    core_repo = CoreStateStoreRepository(retrieval_session)
    core_repo.upsert_authoritative_object(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.WORLD_RULE.value,
        domain_path="world_rule.archive_policy",
        object_id="world_rule.archive_policy",
        scope="story",
        current_revision=7,
        data_json={"rule": "archive doors seal at dawn"},
        metadata_json={"test_marker": "retrieval_broker_unmapped_state"},
        latest_apply_id="apply-unmapped-state",
        payload_schema_ref="schema://core-state/world-rule",
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id="story-1")
    result = await broker.get_state(
        MemoryGetStateInput(
            refs=[
                ObjectRef(
                    object_id="world_rule.archive_policy",
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=Domain.WORLD_RULE,
                    domain_path="world_rule.archive_policy",
                    scope="story",
                )
            ]
        )
    )

    assert result.warnings == []
    assert result.items[0].object_ref.object_id == "world_rule.archive_policy"
    assert result.items[0].object_ref.revision == 7
    assert result.items[0].data == {"rule": "archive doors seal at dawn"}
    assert result.items[0].warnings == []
    assert result.version_refs == ["world_rule.archive_policy@7"]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_get_summary_reads_projection_slots_and_aliases(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")

    result = await broker.get_summary(
        MemoryGetSummaryInput(
            summary_ids=["foundation_digest", "projection.current_state_digest"]
        )
    )

    assert [item.summary_id for item in result.items] == [
        "projection.foundation_digest",
        "projection.current_state_digest",
    ]
    assert result.items[0].summary_text == "Found A\nFound B"
    assert result.items[1].summary_text == "State A\nState B"
    assert (
        result.items[0]
        .metadata["block_id"]
        .startswith("compatibility_mirror:core_state.projection:")
    )
    assert result.items[0].metadata["source"] == "compatibility_mirror"
    assert result.items[0].metadata["revision"] == 1
    assert result.items[0].metadata["block_route"] == (
        "chapter_workspace.builder_snapshot_json"
    )


@pytest.mark.asyncio
async def test_get_summary_domain_fallback_excludes_writer_hints(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")

    result = await broker.get_summary(
        MemoryGetSummaryInput(domains=[Domain.CHAPTER, Domain.NARRATIVE_PROGRESS])
    )

    assert {item.summary_id for item in result.items} == {
        "projection.current_outline_digest",
        "projection.recent_segment_digest",
        "projection.current_state_digest",
    }
    assert all(item.summary_id != "writer_hints" for item in result.items)


@pytest.mark.asyncio
async def test_get_summary_reads_unmapped_projection_slot_from_block_store(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)
    story_session = story_session_service.get_latest_session_for_story("story-1")
    assert story_session is not None
    chapter = story_session_service.get_current_chapter(story_session.session_id)
    assert chapter is not None
    core_repo = CoreStateStoreRepository(retrieval_session)
    projection_row = core_repo.upsert_projection_slot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.side_notes_digest",
        summary_id="projection.side_notes_digest",
        slot_name="side_notes_digest",
        scope="chapter",
        current_revision=5,
        items_json=["Side A", "Side B"],
        metadata_json={"test_marker": "retrieval_broker_unmapped_summary"},
        last_refresh_kind="test_refresh",
        payload_schema_ref="schema://core-state/projection-slot",
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id="story-1")
    result = await broker.get_summary(
        MemoryGetSummaryInput(summary_ids=["projection.side_notes_digest"])
    )

    assert result.warnings == []
    assert [item.summary_id for item in result.items] == [
        "projection.side_notes_digest"
    ]
    assert result.items[0].summary_text == "Side A\nSide B"
    assert result.items[0].metadata["block_id"] == projection_row.projection_slot_id
    assert result.items[0].metadata["source"] == "core_state_store"
    assert (
        result.items[0].metadata["source_row_id"] == projection_row.projection_slot_id
    )
    assert result.items[0].metadata["revision"] == 5
    assert result.items[0].metadata["payload_schema_ref"] == (
        "schema://core-state/projection-slot"
    )
    assert result.items[0].metadata["block_route"] == "core_state_store"
    assert result.items[0].metadata["slot_name"] == "side_notes_digest"
    assert result.items[0].metadata["chapter_workspace_id"] == (
        chapter.chapter_workspace_id
    )
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_memory_os_service_is_a_pure_facade(monkeypatch):
    captured = {}

    async def fake_get_summary(input_model):
        captured["input"] = input_model
        return "ok"

    broker = RetrievalBroker()
    monkeypatch.setattr(broker, "get_summary", fake_get_summary)
    service = MemoryOsService(retrieval_broker=broker)
    input_model = MemoryGetSummaryInput(summary_ids=["scene.current"])

    result = await service.get_summary(input_model)

    assert result == "ok"
    assert captured["input"] is input_model


@pytest.mark.asyncio
async def test_search_and_provenance_surfaces_are_stable(retrieval_session):
    _seed_story_runtime(retrieval_session)
    collection_service = RetrievalCollectionService(retrieval_session)
    document_service = RetrievalDocumentService(retrieval_session)
    ingestion_service = RetrievalIngestionService(retrieval_session)
    collection = collection_service.ensure_story_collection(
        story_id="story-1",
        scope="story",
        collection_kind="archival",
    )
    document_service.upsert_source_asset(
        SourceAsset(
            asset_id="asset-worldbook",
            story_id="story-1",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://worldbook",
            title="Worldbook",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "sec-1",
                        "title": "River District",
                        "path": "foundation.world.river_district",
                        "level": 1,
                        "text": "River District forbids open spell rituals after dusk.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.river_district",
                            "tags": ["district"],
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    ingestion_service.ingest_asset(
        story_id="story-1",
        asset_id="asset-worldbook",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id="story-1")

    recall = await broker.search_recall(
        MemorySearchRecallInput(
            query="market square",
            domains=[Domain.SCENE],
            scope="story",
            top_k=1,
        )
    )
    archival = await broker.search_archival(
        MemorySearchArchivalInput(
            query="spell rituals after dusk",
            domains=[Domain.WORLD_RULE],
            knowledge_collections=[collection.collection_id],
            top_k=1,
        )
    )
    provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(
            target_ref=ObjectRef(
                object_id="scene.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.SCENE,
            )
        )
    )
    versions = await broker.list_versions(
        MemoryListVersionsInput(
            target_ref=ObjectRef(
                object_id="scene.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.SCENE,
            )
        )
    )

    assert recall.hits == []
    assert recall.trace is not None
    assert recall.trace.route.startswith("retrieval.")
    assert archival.hits[0].layer == "archival"
    assert archival.hits[0].query_id == archival.trace.query_id
    assert archival.hits[0].rank == 1
    assert archival.hits[0].knowledge_ref is not None
    assert "forbids open spell rituals" in archival.hits[0].excerpt_text
    assert archival.trace.route.startswith("retrieval.")
    assert provenance.source_refs == [
        "compatibility_mirror:story_session.current_state_json"
    ]
    assert versions.current_ref == "scene.current@1"


@pytest.mark.asyncio
async def test_retrieval_broker_emits_langfuse_observation(retrieval_session):
    class StubRetrievalService:
        async def search_chunks(self, query):
            return RetrievalSearchResult(
                query=query.text_query or "",
                hits=[
                    RetrievalHit(
                        hit_id="chunk-broker",
                        query_id=query.query_id,
                        layer="archival",
                        domain=Domain.WORLD_RULE,
                        domain_path="foundation.world.broker",
                        excerpt_text="Broker observation excerpt",
                        score=0.81,
                        rank=1,
                        metadata={
                            "asset_id": "asset-broker",
                            "title": "Broker Rule",
                            "section_id": "broker-1",
                            "section_part": 0,
                            "contextual_text_version": "v2",
                        },
                    )
                ],
                trace=RetrievalTrace(
                    trace_id="trace-broker",
                    query_id=query.query_id,
                    route="retrieval.hybrid.stub",
                    result_kind="chunk",
                    retriever_routes=[
                        "retrieval.keyword.stub",
                        "retrieval.semantic.stub",
                    ],
                    pipeline_stages=["retrieve", "fusion", "chunk_result_builder"],
                    candidate_count=2,
                    returned_count=1,
                    timings={"keyword_ms": 1.0, "semantic_ms": 2.0},
                    warnings=["rerank_backend_failed:TimeoutError"],
                ),
                warnings=["rerank_backend_failed:TimeoutError"],
            )

    fake_langfuse = _FakeLangfuseService()
    broker = RetrievalBroker(
        default_story_id="story-1",
        retrieval_service_factory=lambda session: StubRetrievalService(),
        langfuse_service=fake_langfuse,
    )

    result = await broker.search_archival(
        MemorySearchArchivalInput(
            query="broker observation",
            domains=[Domain.WORLD_RULE],
            top_k=1,
        )
    )

    assert result.hits[0].hit_id == "chunk-broker"
    observation_names = [
        item["name"]
        for item in fake_langfuse.events
        if item["kind"] == "observation_enter"
    ]
    assert "rp.retrieval.search_archival" in observation_names
    updates = [
        item["payload"]["output"]
        for item in fake_langfuse.events
        if item["kind"] == "observation_update"
        and item["name"] == "rp.retrieval.search_archival"
    ]
    assert updates
    observability = updates[-1]["observability"]
    assert updates[-1]["status"] == "ok"
    assert updates[-1]["search_kind"] == "chunks"
    assert observability["route"] == "retrieval.hybrid.stub"
    assert observability["returned_count"] == 1
    assert observability["maintenance"] is None
    assert observability["top_hits"][0]["block_view"]["source"] == "retrieval_store"
    assert observability["top_hits"][0]["block_view"]["block_id"].startswith(
        "retrieval.archival.rq_"
    )
    assert observability["top_hits"][0]["block_view"]["block_id"].endswith(
        ".chunk-broker"
    )
    score_names = {
        item["payload"]["name"]
        for item in fake_langfuse.events
        if item["kind"] == "score_trace"
        and item["name"] == "rp.retrieval.search_archival"
    }
    assert "retrieval.execution_status" in score_names
    assert "retrieval.metric.returned_count" in score_names
    assert "retrieval.warning_categories" in score_names
