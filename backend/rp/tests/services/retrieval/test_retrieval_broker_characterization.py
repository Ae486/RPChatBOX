"""Golden characterization tests for RetrievalBroker T6-S0."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from rp.models.shared.dsl import Domain, Layer, ObjectRef
from rp.models.memory.crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalHit,
    RetrievalQuery,
    RetrievalSearchResult,
    RetrievalTrace,
)
from rp.models.setup_agent.drafts import StoryConfigDraft
from rp.models.setup_agent.workspace import StoryMode
from rp.services.retrieval.broker import RetrievalBroker
from rp.services.retrieval.runtime_config_service import RetrievalRuntimeConfigService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.tests.services.retrieval.test_retrieval_broker import (
    _FakeLangfuseService,
    _ingest_archival_seed_asset_and_return_chunk,
    _seed_story_runtime,
)


class _StubRetrievalService:
    def __init__(
        self,
        *,
        response_factory: Callable[[RetrievalQuery], RetrievalSearchResult],
    ) -> None:
        self._response_factory = response_factory
        self.seen_queries: list[RetrievalQuery] = []

    async def search_chunks(self, query: RetrievalQuery) -> RetrievalSearchResult:
        self.seen_queries.append(query)
        return self._response_factory(query)


def _make_hit(
    *,
    query_id: str,
    hit_id: str,
    layer: str,
    domain: Domain,
    domain_path: str,
    excerpt_text: str,
    score: float,
    rank: int,
    asset_id: str,
    title: str,
    section_id: str,
    section_part: int,
    contextual_text_version: str = "v1",
    extra_metadata: dict[str, Any] | None = None,
) -> RetrievalHit:
    metadata = {
        "asset_id": asset_id,
        "title": title,
        "section_id": section_id,
        "section_part": section_part,
        "contextual_text_version": contextual_text_version,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return RetrievalHit(
        hit_id=hit_id,
        query_id=query_id,
        layer=layer,
        domain=domain,
        domain_path=domain_path,
        excerpt_text=excerpt_text,
        score=score,
        rank=rank,
        metadata=metadata,
    )


def _make_trace(
    *,
    query: RetrievalQuery,
    trace_id: str,
    route: str,
    result_kind: str = "chunk",
    candidate_count: int = 2,
    returned_count: int = 2,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> RetrievalTrace:
    return RetrievalTrace(
        trace_id=trace_id,
        query_id=query.query_id,
        route=route,
        result_kind=result_kind,
        candidate_count=candidate_count,
        returned_count=returned_count,
        timings={},
        warnings=list(warnings or []),
        details=dict(details or {}),
    )


def _make_runtime_card_expand_hit(
    *,
    hit_id: str = "",
    chunk_id_metadata: str | None = None,
    knowledge_ref_chunk_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RetrievalHit:
    hit_metadata = dict(metadata or {})
    if chunk_id_metadata is not None:
        hit_metadata["chunk_id"] = chunk_id_metadata
    return RetrievalHit(
        hit_id=hit_id,
        query_id="query-expand-hit",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE,
        domain_path="foundation.world.expand-hit",
        knowledge_ref=(
            ObjectRef(
                object_id=knowledge_ref_chunk_id,
                layer=Layer.ARCHIVAL,
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.expand-hit",
                scope="story",
                revision=1,
            )
            if knowledge_ref_chunk_id is not None
            else None
        ),
        excerpt_text="Runtime card excerpt",
        score=0.77,
        rank=1,
        metadata=hit_metadata,
        provenance_refs=[],
    )


def _seed_expand_hit_chunk(
    retrieval_session,
    *,
    story_id: str,
    asset_id: str,
    text: str,
):
    return _ingest_archival_seed_asset_and_return_chunk(
        retrieval_session,
        story_id=story_id,
        asset_id=asset_id,
        text=text,
        metadata={
            "layer": Layer.ARCHIVAL.value,
            "source_family": "setup_source",
            "source_type": "foundation_entry",
            "source_origin": "setup_workspace",
        },
    )


def _latest_story_session(retrieval_session):
    session = StorySessionService(retrieval_session).get_latest_session_for_story(
        "story-1"
    )
    assert session is not None
    return session


@pytest.mark.asyncio
async def test_get_state_characterization(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")

    seeded = await broker.get_state(MemoryGetStateInput(domain=Domain.CHAPTER))
    fallback = await broker.get_state(MemoryGetStateInput(domain=Domain.SCENE))

    assert seeded.items[0].object_ref.object_id == "chapter.current"
    assert seeded.items[0].data["title"] == "Chapter One"
    assert seeded.items[0].warnings == []
    assert seeded.version_refs == ["chapter.current@1"]

    assert fallback.items[0].object_ref.object_id == "scene.current"
    assert fallback.items[0].data == {}
    assert fallback.items[0].warnings == [
        "phase_e_authoritative_ref_not_materialized:scene.current"
    ]
    assert fallback.version_refs == ["scene.current@1"]


@pytest.mark.asyncio
async def test_live_authoritative_versions_and_provenance_characterization(
    retrieval_session,
):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")
    seeded_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )
    fallback_ref = ObjectRef(
        object_id="scene.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.SCENE,
        domain_path="scene.current",
    )

    seeded_versions = await broker.list_versions(
        MemoryListVersionsInput(target_ref=seeded_ref)
    )
    seeded_provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(target_ref=seeded_ref)
    )
    fallback_versions = await broker.list_versions(
        MemoryListVersionsInput(target_ref=fallback_ref)
    )
    fallback_provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(target_ref=fallback_ref)
    )

    assert seeded_versions.versions == ["chapter.current@1"]
    assert seeded_versions.current_ref == "chapter.current@1"
    assert seeded_provenance.target_ref.object_id == "chapter.current"
    assert seeded_provenance.target_ref.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert seeded_provenance.target_ref.domain == Domain.CHAPTER
    assert seeded_provenance.target_ref.domain_path == "chapter.current"
    assert seeded_provenance.target_ref.revision == 1
    assert seeded_provenance.source_refs == [
        "compatibility_mirror:story_session.current_state_json"
    ]
    assert seeded_provenance.proposal_refs == []
    assert seeded_provenance.ingestion_refs == []

    assert fallback_versions.versions == ["scene.current@1"]
    assert fallback_versions.current_ref == "scene.current@1"
    assert fallback_provenance.target_ref.object_id == "scene.current"
    assert fallback_provenance.target_ref.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert fallback_provenance.target_ref.domain == Domain.SCENE
    assert fallback_provenance.target_ref.domain_path == "scene.current"
    assert fallback_provenance.target_ref.revision == 1
    assert fallback_provenance.source_refs == [
        "compatibility_mirror:story_session.current_state_json"
    ]
    assert fallback_provenance.proposal_refs == []
    assert fallback_provenance.ingestion_refs == []


@pytest.mark.asyncio
async def test_live_projection_versions_and_provenance_characterization(
    retrieval_session,
):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")
    projection_ref = ObjectRef(
        object_id="projection.current_state_digest",
        layer=Layer.CORE_STATE_PROJECTION,
        domain=Domain.CHAPTER,
        domain_path="projection.current_state_digest",
    )

    versions = await broker.list_versions(
        MemoryListVersionsInput(target_ref=projection_ref)
    )
    provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(target_ref=projection_ref)
    )

    assert versions.versions == ["projection.current_state_digest@1"]
    assert versions.current_ref == "projection.current_state_digest@1"
    assert provenance.target_ref.object_id == "projection.current_state_digest"
    assert provenance.target_ref.layer == Layer.CORE_STATE_PROJECTION
    assert provenance.target_ref.domain == Domain.CHAPTER
    assert provenance.target_ref.domain_path == "projection.current_state_digest"
    assert provenance.target_ref.revision == 1
    assert provenance.source_refs == [
        "compatibility_mirror:chapter_workspace.builder_snapshot_json"
    ]
    assert provenance.proposal_refs == []
    assert provenance.ingestion_refs == []


@pytest.mark.asyncio
async def test_get_summary_characterization(retrieval_session):
    _seed_story_runtime(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")

    explicit = await broker.get_summary(
        MemoryGetSummaryInput(
            summary_ids=["projection.current_state_digest", "foundation_digest"]
        )
    )
    domain_fallback = await broker.get_summary(
        MemoryGetSummaryInput(domains=[Domain.CHAPTER, Domain.NARRATIVE_PROGRESS])
    )

    assert [item.summary_id for item in explicit.items] == [
        "projection.current_state_digest",
        "projection.foundation_digest",
    ]
    assert [item.summary_text for item in explicit.items] == [
        "State A\nState B",
        "Found A\nFound B",
    ]
    assert {item.summary_id for item in domain_fallback.items} == {
        "projection.current_outline_digest",
        "projection.recent_segment_digest",
        "projection.current_state_digest",
    }
    assert all(item.summary_id != "writer_hints" for item in domain_fallback.items)


@pytest.mark.asyncio
async def test_search_recall_characterization(retrieval_session):
    captured_queries: list[RetrievalQuery] = []

    def _response_factory(query: RetrievalQuery) -> RetrievalSearchResult:
        captured_queries.append(query)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=[
                _make_hit(
                    query_id=query.query_id,
                    hit_id="recall-hit-2",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.story.hit-2",
                    excerpt_text="Second recall hit",
                    score=0.91,
                    rank=2,
                    asset_id="asset-recall-2",
                    title="Recall Two",
                    section_id="section-recall-2",
                    section_part=0,
                ),
                _make_hit(
                    query_id=query.query_id,
                    hit_id="recall-hit-1",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.story.hit-1",
                    excerpt_text="First recall hit",
                    score=0.95,
                    rank=1,
                    asset_id="asset-recall-1",
                    title="Recall One",
                    section_id="section-recall-1",
                    section_part=0,
                ),
            ],
            trace=_make_trace(
                query=query,
                trace_id="trace-recall",
                route="retrieval.stub.recall",
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id="story-recall-deterministic",
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )

    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="harbor dawn",
            scope="story",
            domains=[Domain.CHAPTER, Domain.NARRATIVE_PROGRESS],
            top_k=7,
            filters={
                "materialization_kinds": ["chapter_summary"],
                "source_families": ["longform_story_runtime"],
            },
        )
    )

    assert captured_queries[0].query_kind == "recall"
    assert captured_queries[0].story_id == "story-recall-deterministic"
    assert captured_queries[0].scope == "story"
    assert captured_queries[0].domains == [Domain.CHAPTER, Domain.NARRATIVE_PROGRESS]
    assert captured_queries[0].top_k == 7
    assert captured_queries[0].filters == {
        "materialization_kinds": ["chapter_summary"],
        "source_families": ["longform_story_runtime"],
    }
    assert [hit.hit_id for hit in result.hits] == ["recall-hit-2", "recall-hit-1"]
    assert result.trace is not None
    assert result.trace.route == "retrieval.stub.recall"


@pytest.mark.asyncio
async def test_search_archival_characterization(retrieval_session):
    captured_queries: list[RetrievalQuery] = []

    def _response_factory(query: RetrievalQuery) -> RetrievalSearchResult:
        captured_queries.append(query)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=[
                _make_hit(
                    query_id=query.query_id,
                    hit_id="archival-hit-2",
                    layer="archival",
                    domain=Domain.WORLD_RULE,
                    domain_path="foundation.world.hit-2",
                    excerpt_text="Second archival hit",
                    score=0.72,
                    rank=2,
                    asset_id="asset-archival-2",
                    title="Archival Two",
                    section_id="section-archival-2",
                    section_part=0,
                ),
                _make_hit(
                    query_id=query.query_id,
                    hit_id="archival-hit-1",
                    layer="archival",
                    domain=Domain.WORLD_RULE,
                    domain_path="foundation.world.hit-1",
                    excerpt_text="First archival hit",
                    score=0.88,
                    rank=1,
                    asset_id="asset-archival-1",
                    title="Archival One",
                    section_id="section-archival-1",
                    section_part=0,
                ),
            ],
            trace=_make_trace(
                query=query,
                trace_id="trace-archival",
                route="retrieval.stub.archival",
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id="story-archival-deterministic",
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )

    result = await broker.search_archival(
        MemorySearchArchivalInput(
            query="archive lore",
            knowledge_collections=["setup-a", "setup-b"],
            domains=[Domain.WORLD_RULE],
            top_k=4,
            filters={"source_types": ["foundation_entry"]},
        )
    )

    assert captured_queries[0].query_kind == "archival"
    assert captured_queries[0].scope is None
    assert captured_queries[0].filters["knowledge_collections"] == [
        "setup-a",
        "setup-b",
    ]
    assert captured_queries[0].filters["source_types"] == ["foundation_entry"]
    assert [hit.hit_id for hit in result.hits] == ["archival-hit-2", "archival-hit-1"]
    assert result.trace is not None
    assert result.trace.route == "retrieval.stub.archival"


@pytest.mark.asyncio
async def test_branch_visibility_characterization(retrieval_session):
    _seed_story_runtime(retrieval_session)
    story_session = _latest_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.branch_visibility_characterization",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    branch = identity_service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    turn_one = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    turn_two = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    retrieval_session.commit()
    identity = identity_service.resolve_memory_identity(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=branch.branch_head_id,
        turn_id=turn_one.turn_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    captured_queries: list[RetrievalQuery] = []

    def _response_factory(query: RetrievalQuery) -> RetrievalSearchResult:
        captured_queries.append(query)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=[
                _make_hit(
                    query_id=query.query_id,
                    hit_id="hit-visible",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.visible",
                    excerpt_text="Visible turn one hit",
                    score=0.9,
                    rank=1,
                    asset_id="asset-visible",
                    title="Visible Asset",
                    section_id="section-visible",
                    section_part=0,
                    extra_metadata={
                        "visibility_scope": "branch_scoped",
                        "visibility_state": "active",
                        "owning_branch_head_id": branch.branch_head_id,
                        "origin_turn_id": turn_one.turn_id,
                    },
                ),
                _make_hit(
                    query_id=query.query_id,
                    hit_id="hit-hidden",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.hidden",
                    excerpt_text="Hidden turn two hit",
                    score=0.8,
                    rank=2,
                    asset_id="asset-hidden",
                    title="Hidden Asset",
                    section_id="section-hidden",
                    section_part=0,
                    extra_metadata={
                        "visibility_scope": "branch_scoped",
                        "visibility_state": "active",
                        "owning_branch_head_id": branch.branch_head_id,
                        "origin_turn_id": turn_two.turn_id,
                    },
                ),
            ],
            trace=_make_trace(
                query=query,
                trace_id="trace-branch-visibility",
                route="retrieval.stub.branch_visibility",
                returned_count=2,
                candidate_count=2,
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id="caller-default-story",
        runtime_identity=identity,
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )

    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="branch visibility",
            scope="story",
            domains=[Domain.CHAPTER],
            top_k=10,
            filters={
                "story_id": "caller-story",
                "branch_ids": [branch.branch_head_id],
            },
        )
    )

    assert captured_queries[0].story_id == identity.story_id
    assert captured_queries[0].identity is not None
    assert captured_queries[0].identity.runtime_profile_snapshot_id == (
        identity.runtime_profile_snapshot_id
    )
    assert captured_queries[0].filters["runtime_identity"][
        "runtime_profile_snapshot_id"
    ] == identity.runtime_profile_snapshot_id
    assert "branch_ids" not in captured_queries[0].filters
    assert captured_queries[0].filters["_runtime_branch_visibility_ignored_filters"] == {
        "ignored_filter_keys": ["branch_ids"],
        "reason": "runtime_identity_branch_visibility_is_authoritative",
    }
    assert [hit.hit_id for hit in result.hits] == ["hit-visible"]
    assert result.trace is not None
    assert result.trace.returned_count == 1
    assert result.trace.route == "retrieval.stub.branch_visibility"
    assert result.trace.details["branch_visibility"]["active_branch_head_id"] == (
        branch.branch_head_id
    )
    assert any(
        item.get("ref_id") == "hit-hidden"
        for item in result.trace.details["branch_visibility"]["omitted_refs"]
    )
    assert "runtime_branch_filters_ignored:branch_ids" in result.warnings
    assert any(
        warning.startswith("runtime_branch_visibility_filtered:")
        for warning in result.warnings
    )
    assert "runtime_branch_visibility_filtered" in result.trace.warnings


@pytest.mark.asyncio
async def test_story_config_enables_rerank_and_explicit_policy_overrides(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-rerank-policy",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            retrieval_rerank_model_id="rerank-model-setup",
            retrieval_rerank_provider_id="provider-rerank-setup",
        ),
    )

    captured_queries: list[RetrievalQuery] = []

    def _response_factory(query: RetrievalQuery) -> RetrievalSearchResult:
        captured_queries.append(query)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=[
                _make_hit(
                    query_id=query.query_id,
                    hit_id="policy-hit",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.policy.hit",
                    excerpt_text="Policy hit",
                    score=0.9,
                    rank=1,
                    asset_id="asset-policy",
                    title="Policy Asset",
                    section_id="section-policy",
                    section_part=0,
                )
            ],
            trace=_make_trace(
                query=query,
                trace_id=f"trace-policy-{len(captured_queries)}",
                route="retrieval.stub.policy",
                returned_count=1,
                candidate_count=1,
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id="story-rerank-policy",
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )

    await broker.search_recall(
        MemorySearchRecallInput(
            query="rerank enabled",
            domains=[Domain.CHAPTER],
            top_k=3,
        )
    )
    await broker.search_recall(
        MemorySearchRecallInput(
            query="rerank off",
            domains=[Domain.CHAPTER],
            top_k=3,
            filters={"search_policy": {"rerank": "off"}},
        )
    )
    await broker.search_recall(
        MemorySearchRecallInput(
            query="rerank on",
            domains=[Domain.CHAPTER],
            top_k=3,
            filters={"search_policy": {"rerank": "on"}},
        )
    )

    assert [query.rerank for query in captured_queries] == [True, False, True]
    assert captured_queries[0].story_id == "story-rerank-policy"


@pytest.mark.asyncio
async def test_pinned_runtime_snapshot_beats_story_drift(retrieval_session):
    _seed_story_runtime(retrieval_session)
    session_service = StorySessionService(retrieval_session)
    story_session = _latest_story_session(retrieval_session)

    session_service.update_session(
        session_id=story_session.session_id,
        runtime_story_config_patch={
            "retrieval_rerank_model_id": "rerank-snapshot",
            "retrieval_rerank_provider_id": "provider-snapshot",
        },
    )
    session_service.commit()

    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.pinned_runtime_snapshot_beats_story_drift",
    )
    identity = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    session_service.update_session(
        session_id=story_session.session_id,
        runtime_story_config_patch={
            "retrieval_rerank_model_id": None,
            "retrieval_rerank_provider_id": None,
        },
    )
    session_service.commit()

    resolved_config = RetrievalRuntimeConfigService(retrieval_session).resolve_story_config(
        story_id=story_session.story_id
    )

    captured_queries: list[RetrievalQuery] = []

    def _response_factory(query: RetrievalQuery) -> RetrievalSearchResult:
        captured_queries.append(query)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=[
                _make_hit(
                    query_id=query.query_id,
                    hit_id="pinned-hit-visible",
                    layer="recall",
                    domain=Domain.CHAPTER,
                    domain_path="recall.pinned.visible",
                    excerpt_text="Pinned visible hit",
                    score=0.93,
                    rank=1,
                    asset_id="asset-pinned-visible",
                    title="Pinned Visible",
                    section_id="section-pinned-visible",
                    section_part=0,
                    extra_metadata={
                        "visibility_scope": "branch_scoped",
                        "visibility_state": "active",
                        "owning_branch_head_id": identity.branch_head_id,
                        "origin_turn_id": identity.turn_id,
                    },
                )
            ],
            trace=_make_trace(
                query=query,
                trace_id="trace-pinned",
                route="retrieval.stub.pinned",
                returned_count=1,
                candidate_count=1,
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id=story_session.story_id,
        runtime_identity=identity,
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )

    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="pinned rerank",
            scope="story",
            domains=[Domain.CHAPTER],
            top_k=5,
        )
    )

    assert resolved_config.rerank_model_id is None
    assert resolved_config.rerank_provider_id is None
    assert captured_queries[0].rerank is True
    assert captured_queries[0].identity is not None
    assert captured_queries[0].identity.runtime_profile_snapshot_id == (
        identity.runtime_profile_snapshot_id
    )
    assert [hit.hit_id for hit in result.hits] == ["pinned-hit-visible"]
    assert result.trace is not None
    assert result.trace.returned_count == 1


def test_expand_hit_resolves_chunk_id_from_runtime_card_metadata(
    retrieval_session,
):
    chunk = _seed_expand_hit_chunk(
        retrieval_session,
        story_id="story-expand-hit-metadata",
        asset_id="asset-expand-hit-metadata",
        text="The harbor bell is indexed as archival foundation evidence.",
    )
    broker = RetrievalBroker(
        default_story_id="story-expand-hit-metadata",
        session=retrieval_session,
    )
    hit = _make_runtime_card_expand_hit(
        chunk_id_metadata=chunk.chunk_id,
        knowledge_ref_chunk_id="chunk-expand-hit-wrong-knowledge-ref",
        metadata={
            "source_ref": "metadata://ignored-when-asset-exists",
            "asset_kind": "ignored_metadata_kind",
        },
    )

    expanded = broker.expand_hit(hit)

    assert expanded["chunk_id"] == chunk.chunk_id
    assert expanded["text"] == chunk.text
    assert expanded["metadata"]["section_id"] == "seed:asset-expand-hit-metadata"


def test_expand_hit_returns_observed_dict_for_knowledge_ref_chunk(
    retrieval_session,
):
    chunk = _seed_expand_hit_chunk(
        retrieval_session,
        story_id="story-expand-hit-found",
        asset_id="asset-expand-hit-found",
        text="The Order of Dawn protects Aileen under the covenant clause.",
    )
    broker = RetrievalBroker(
        default_story_id="story-expand-hit-found",
        session=retrieval_session,
    )
    hit = _make_runtime_card_expand_hit(
        knowledge_ref_chunk_id=chunk.chunk_id,
        metadata={
            "source_ref": "metadata://ignored-when-asset-exists",
            "asset_kind": "ignored_metadata_kind",
        },
    )

    expanded = broker.expand_hit(hit)

    assert set(expanded) == {
        "chunk_id",
        "asset_id",
        "parsed_document_id",
        "collection_id",
        "domain",
        "domain_path",
        "chunk_index",
        "title",
        "text",
        "token_count",
        "layer",
        "metadata",
        "provenance_refs",
        "source_ref",
        "asset_kind",
    }
    assert isinstance(expanded["chunk_id"], str)
    assert expanded == {
        "chunk_id": chunk.chunk_id,
        "asset_id": "asset-expand-hit-found",
        "parsed_document_id": chunk.parsed_document_id,
        "collection_id": chunk.collection_id,
        "domain": Domain.WORLD_RULE.value,
        "domain_path": "foundation.world.asset-expand-hit-found",
        "chunk_index": 0,
        "title": "Archival Seed asset-expand-hit-found",
        "text": "The Order of Dawn protects Aileen under the covenant clause.",
        "token_count": chunk.token_count,
        "layer": Layer.ARCHIVAL.value,
        "metadata": chunk.metadata_json,
        "provenance_refs": list(chunk.provenance_refs_json or []),
        "source_ref": "memory://asset-expand-hit-found",
        "asset_kind": "foundation_entry",
    }
    assert isinstance(expanded["parsed_document_id"], str)
    assert str(expanded["parsed_document_id"]).startswith("pd_asset-expand-hit-found_")
    assert isinstance(expanded["collection_id"], str)
    assert isinstance(expanded["metadata"], dict)
    assert isinstance(expanded["provenance_refs"], list)


def test_expand_hit_missing_chunk_raises_resolved_chunk_id(retrieval_session):
    broker = RetrievalBroker(
        default_story_id="story-expand-hit-missing",
        session=retrieval_session,
    )
    hit = _make_runtime_card_expand_hit(chunk_id_metadata="chunk-expand-hit-missing")

    with pytest.raises(
        ValueError,
        match="^retrieval_hit_chunk_not_found:chunk-expand-hit-missing$",
    ):
        broker.expand_hit(hit)


def test_expand_hit_missing_resolvable_id_raises(retrieval_session):
    broker = RetrievalBroker(
        default_story_id="story-expand-hit-id-missing",
        session=retrieval_session,
    )
    hit = _make_runtime_card_expand_hit()

    with pytest.raises(ValueError, match="^retrieval_hit_chunk_id_missing$"):
        broker.expand_hit(hit)
