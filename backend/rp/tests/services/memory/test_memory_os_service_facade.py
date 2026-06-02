"""Facade delegation and runtime broker parity tests for MemoryOsService."""

from __future__ import annotations

from typing import Any

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
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
from rp.services.memory.os_service import MemoryOsService
from rp.services.retrieval.broker import RetrievalBroker
from rp.services.retrieval.runtime_config_service import RetrievalRuntimeConfigService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.tests.services.retrieval.test_retrieval_broker import (
    _FakeLangfuseService,
    _seed_story_runtime,
)


TARGET_REF = ObjectRef(
    object_id="chapter.current",
    layer=Layer.CORE_STATE_AUTHORITATIVE,
    domain=Domain.CHAPTER,
    domain_path="chapter.current",
)


class _StubBroker:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, object]] = []

    async def get_state(self, input_model):
        self.calls.append(("get_state", input_model))
        return self._responses["get_state"]

    async def get_summary(self, input_model):
        self.calls.append(("get_summary", input_model))
        return self._responses["get_summary"]

    async def search_recall(self, input_model):
        self.calls.append(("search_recall", input_model))
        return self._responses["search_recall"]

    async def search_archival(self, input_model):
        self.calls.append(("search_archival", input_model))
        return self._responses["search_archival"]

    async def list_versions(self, input_model):
        self.calls.append(("list_versions", input_model))
        return self._responses["list_versions"]

    async def read_provenance(self, input_model):
        self.calls.append(("read_provenance", input_model))
        return self._responses["read_provenance"]


class _StubRetrievalService:
    def __init__(self, response_factory) -> None:
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
    candidate_count: int = 1,
    returned_count: int = 1,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "input_model"),
    [
        ("get_state", MemoryGetStateInput(domain=Domain.CHAPTER)),
        (
            "get_summary",
            MemoryGetSummaryInput(summary_ids=["projection.foundation_digest"]),
        ),
        (
            "search_recall",
            MemorySearchRecallInput(
                query="delegate recall",
                scope="story",
                domains=[Domain.CHAPTER],
                top_k=3,
                filters={"source_families": ["longform_story_runtime"]},
            ),
        ),
        (
            "search_archival",
            MemorySearchArchivalInput(
                query="delegate archival",
                knowledge_collections=["setup-a"],
                domains=[Domain.WORLD_RULE],
                top_k=2,
                filters={"source_types": ["foundation_entry"]},
            ),
        ),
        ("list_versions", MemoryListVersionsInput(target_ref=TARGET_REF)),
        ("read_provenance", MemoryReadProvenanceInput(target_ref=TARGET_REF)),
    ],
)
async def test_memory_os_service_forwards_all_public_methods(
    method_name,
    input_model,
):
    responses = {name: object() for name in (
        "get_state",
        "get_summary",
        "search_recall",
        "search_archival",
        "list_versions",
        "read_provenance",
    )}
    broker = _StubBroker(responses)
    service = MemoryOsService(retrieval_broker=broker)

    returned = await getattr(service, method_name)(input_model)

    assert returned is responses[method_name]
    assert broker.calls == [(method_name, input_model)]
    assert broker.calls[0][1] is input_model


@pytest.mark.asyncio
async def test_memory_os_service_with_runtime_broker_preserves_result_and_query_fields(
    retrieval_session,
):
    _seed_story_runtime(retrieval_session)
    session_service = StorySessionService(retrieval_session)
    story_session = session_service.get_latest_session_for_story("story-1")
    assert story_session is not None

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
        created_from="test.memory_os_service_runtime_broker",
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
                trace_id="trace-memory-facade-runtime",
                route="retrieval.stub.runtime",
                returned_count=2,
                candidate_count=2,
            ),
        )

    stub_service = _StubRetrievalService(response_factory=_response_factory)
    broker = RetrievalBroker(
        default_story_id=story_session.story_id,
        runtime_identity=identity,
        retrieval_service_factory=lambda _session: stub_service,
        langfuse_service=_FakeLangfuseService(),
    )
    service = MemoryOsService(retrieval_broker=broker)

    result = await service.search_recall(
        MemorySearchRecallInput(
            query="memory facade runtime broker",
            scope="story",
            domains=[Domain.CHAPTER],
            top_k=10,
            filters={
                "branch_ids": [branch.branch_head_id],
                "story_id": "caller-story",
            },
        )
    )

    assert resolved_config.rerank_model_id is None
    assert resolved_config.rerank_provider_id is None
    assert captured_queries[0].rerank is True
    assert captured_queries[0].identity is not None
    assert captured_queries[0].identity.runtime_profile_snapshot_id == (
        identity.runtime_profile_snapshot_id
    )
    assert "branch_ids" not in captured_queries[0].filters
    assert captured_queries[0].filters["_runtime_branch_visibility_ignored_filters"] == {
        "ignored_filter_keys": ["branch_ids"],
        "reason": "runtime_identity_branch_visibility_is_authoritative",
    }
    assert [hit.hit_id for hit in result.hits] == ["hit-visible"]
    assert "runtime_branch_filters_ignored:branch_ids" in result.warnings
    assert any(
        warning.startswith("runtime_branch_visibility_filtered:")
        for warning in result.warnings
    )
    assert result.trace is not None
    assert result.trace.returned_count == 1
    assert result.trace.route == "retrieval.stub.runtime"
