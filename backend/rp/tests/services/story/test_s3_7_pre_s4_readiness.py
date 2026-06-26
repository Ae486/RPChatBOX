"""S-X8 pre-S4 readiness proof for the S3.7 harness tool-seam.

Capstone L1 slice. Deterministic and offline. Binds the committed building
blocks into one reachable path:

  build_writer_retrieval_harness (factory)
    -> StoryHarness.arun (kernel-graph tool loop)
    -> RuntimeStoryModelGateway (scripted complete_with_tools)
    -> RuntimeRetrievalToolProvider (executor + finalize guard)
    -> WorkerExecutorDispatcher / WorkerFamily (routing matrix)

Proves: (a) the tool-using harness path is reachable end-to-end via the factory,
(b) worker-side retrieval is OFF unless explicitly opted in
(ACC-07-worker-family-8 / INV-07-worker-family-21), (c) the negative routing
matrix (memory/context/simple families never reach the retrieval harness), and
(d) cancellation mid-loop mutates nothing (re-raise + zero-mutation contract,
per test_s2_harness_injection.py T6 -- no runner-level restart receipt here).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.shared.dsl import Domain
from rp.models.retrieval.records import SourceAsset
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import LongformChapterPhase
from rp.models.writer.worker_family import WorkerFamily
from rp.models.writer.worker_memory import WorkerSourceRefBundle
from rp.services.retrieval.collection_service import RetrievalCollectionService
from rp.services.retrieval.document_service import RetrievalDocumentService
from rp.services.retrieval.ingestion_service import RetrievalIngestionService
from rp.services.retrieval.retrieval_tool_definitions import (
    WRITER_RETRIEVAL_EXPAND_TOOL,
    WRITER_RETRIEVAL_SEARCH_TOOL,
    WRITER_RETRIEVAL_USAGE_TOOL,
)
from rp.services.retrieval.runtime_card_service import RuntimeRetrievalCardService
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.story_runtime_harness_factory import (
    build_writer_retrieval_harness,
)
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.writer.worker_executor_dispatcher import (
    WorkerExecutorDispatcher,
    WorkerExecutorRoute,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# DB-backed identity + recall seed (mirrors test_writing_worker_retrieval_loop_service)
# ---------------------------------------------------------------------------


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-s3-7-readiness",
        source_workspace_id="workspace-s3-7-readiness",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "segment_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.SEGMENT_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id)


def _seed_recall_asset(retrieval_session, *, story_id: str):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=story_id,
        scope="story",
        collection_kind="recall",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-s3-7-readiness-recall",
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="accepted_story_segment",
            source_ref="memory://s3-7-readiness-recall",
            title="S3.7 Readiness Recall",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["recall"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "seed:s3-7-readiness-recall",
                        "title": "S3.7 Readiness Recall",
                        "path": "chapter.recall.s3-7-readiness",
                        "level": 1,
                        "text": "The silver seal broke during the first storm at dusk.",
                        "metadata": {
                            "domain": Domain.CHAPTER.value,
                            "domain_path": "chapter.recall.s3-7-readiness",
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
        story_id=story_id,
        asset_id="asset-s3-7-readiness-recall",
        collection_id=collection.collection_id,
    )


def _build_identity(retrieval_session):
    session = _seed_story_runtime(retrieval_session)
    _seed_recall_asset(retrieval_session, story_id=session.story_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s3_7_pre_s4_readiness",
    )
    return StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="write_next_segment",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


# ---------------------------------------------------------------------------
# Scripted gateways (mirror _ToolLoopGateway from the retrieval-loop test)
# ---------------------------------------------------------------------------


class _ToolLoopGateway:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def supports_tools(self, **_kwargs) -> bool:
        return True

    async def complete_with_tools(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("No queued tool-loop response")
        return self._responses.pop(0)


class _CancelOnFirstCallGateway:
    """Scripted gateway that cancels mid-loop on the first model call."""

    def __init__(self) -> None:
        self.calls = 0

    def supports_tools(self, **_kwargs) -> bool:
        return True

    async def complete_with_tools(self, **_kwargs) -> dict:
        self.calls += 1
        raise asyncio.CancelledError()


def _tool_call(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _search_expand_usage_final_responses() -> list[dict]:
    return [
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            _tool_call(
                                "call_search",
                                WRITER_RETRIEVAL_SEARCH_TOOL,
                                {
                                    "query": "storm",
                                    "mode": "semantic",
                                    "lexical_anchors": ["storm"],
                                    "semantic_predicates": [],
                                },
                            )
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            _tool_call(
                                "call_expand",
                                WRITER_RETRIEVAL_EXPAND_TOOL,
                                {"card_short_ids": ["R1"]},
                            )
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 4,
                "total_tokens": 12,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            _tool_call(
                                "call_usage",
                                WRITER_RETRIEVAL_USAGE_TOOL,
                                {
                                    "used_card_short_ids": ["R1"],
                                    "used_expanded_short_ids": ["X1"],
                                    "knowledge_gaps": [],
                                },
                            )
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 6,
                "completion_tokens": 3,
                "total_tokens": 9,
            },
        },
        {
            "choices": [
                {
                    "message": {
                        "content": "Final segment grounded in retrieved evidence."
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 18,
                "total_tokens": 30,
            },
        },
    ]


# ---------------------------------------------------------------------------
# Minimal in-memory card service (mirrors the provider unit test's fake)
# ---------------------------------------------------------------------------


class _FakeRuntimeRetrievalCardService:
    """In-memory card service so the provider can be built without a DB."""

    def __init__(self) -> None:
        self.bundle = WorkerSourceRefBundle()

    def build_source_ref_bundle(self, *, identity):  # noqa: ANN001 - duck typed
        return self.bundle


# ===========================================================================
# 1) Capstone end-to-end: the tool-using harness path is reachable via factory.
# ===========================================================================


@pytest.mark.asyncio
async def test_harness_tool_loop_path_is_reachable_via_factory(retrieval_session):
    identity = _build_identity(retrieval_session)
    gateway = _ToolLoopGateway(_search_expand_usage_final_responses())
    harness, provider = build_writer_retrieval_harness(
        identity=identity,
        llm_gateway=gateway,
        runtime_retrieval_card_service=RuntimeRetrievalCardService(
            session=retrieval_session
        ),
        model_id="model",
        provider_id="provider",
        max_retrieval_attempts=2,
        temperature=None,
        max_tokens=None,
    )

    result = await harness.arun(
        seed_messages=[
            {"role": "system", "content": "You are the writing worker."},
            {"role": "user", "content": "Write the next segment grounded in recall."},
        ]
    )

    assert result.succeeded is True
    assert result.assistant_text == "Final segment grounded in retrieved evidence."
    assert result.usage_metadata["total_tokens"] == 66

    trace_refs = provider.tool_trace_refs
    assert any(
        ref.startswith(f"writer_tool:{WRITER_RETRIEVAL_SEARCH_TOOL}:")
        for ref in trace_refs
    )
    assert any(
        ref.startswith(f"writer_tool:{WRITER_RETRIEVAL_EXPAND_TOOL}:")
        for ref in trace_refs
    )

    bundle = provider.build_source_ref_bundle()
    assert not bundle.is_empty()
    assert bundle.retrieval_usage_material_ids


# ===========================================================================
# 2) Tool-using families route to the harness seam.
# ===========================================================================


def test_dispatcher_routes_tool_using_families_to_harness():
    dispatcher = WorkerExecutorDispatcher()

    assert (
        dispatcher.resolve(WorkerFamily.WRITER)
        == WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS
    )
    assert (
        dispatcher.resolve(WorkerFamily.RETRIEVAL)
        == WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS
    )


# ===========================================================================
# 3) Negative matrix: memory/context/simple never reach the retrieval harness.
# ===========================================================================


def test_memory_family_never_routes_to_retrieval_harness():
    dispatcher = WorkerExecutorDispatcher()

    assert (
        dispatcher.resolve(WorkerFamily.MEMORY_MAINTENANCE)
        == WorkerExecutorRoute.MEMORY_MAINTENANCE_STRUCTURED_OUTPUT
    )
    assert (
        dispatcher.resolve(WorkerFamily.RUNTIME_CONTEXT)
        == WorkerExecutorRoute.UNSUPPORTED
    )
    assert dispatcher.resolve(WorkerFamily.SIMPLE) == WorkerExecutorRoute.UNSUPPORTED


# ===========================================================================
# 4) Retrieval is OFF unless explicitly opted in (ACC-07-worker-family-8 / INV-21).
# ===========================================================================


def test_retrieval_is_off_unless_opted_in():
    identity = MemoryRuntimeIdentity(
        story_id="story-1",
        session_id="session-1",
        branch_head_id="branch-1",
        turn_id="turn-1",
        runtime_profile_snapshot_id="snapshot-1",
    )
    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )

    # No visibility opt-in -> zero tools, fail-closed.
    assert provider.get_openai_tool_definitions(visible_tool_names=()) == []

    visible = (
        WRITER_RETRIEVAL_SEARCH_TOOL,
        WRITER_RETRIEVAL_EXPAND_TOOL,
        WRITER_RETRIEVAL_USAGE_TOOL,
    )
    definitions = provider.get_openai_tool_definitions(visible_tool_names=visible)
    assert len(definitions) == 3
    assert {definition["function"]["name"] for definition in definitions} == set(visible)


# ===========================================================================
# 5) Cancellation mid-loop mutates nothing (re-raise + zero-mutation).
# ===========================================================================


@pytest.mark.asyncio
async def test_cancellation_mid_loop_mutates_nothing(retrieval_session):
    identity = _build_identity(retrieval_session)
    gateway = _CancelOnFirstCallGateway()
    harness, provider = build_writer_retrieval_harness(
        identity=identity,
        llm_gateway=gateway,
        runtime_retrieval_card_service=RuntimeRetrievalCardService(
            session=retrieval_session
        ),
        model_id="model",
        provider_id="provider",
        max_retrieval_attempts=2,
        temperature=None,
        max_tokens=None,
    )

    with pytest.raises(asyncio.CancelledError):
        await harness.arun(
            seed_messages=[
                {"role": "system", "content": "You are the writing worker."},
                {"role": "user", "content": "Write the next segment."},
            ]
        )

    # Zero post-cancellation mutation: no usage material recorded, nothing
    # promoted into the source-ref bundle, no writer-tool trace.
    assert gateway.calls == 1
    assert provider._state.usage_material_id is None
    assert provider.tool_trace_refs == []
    assert provider.build_source_ref_bundle().is_empty()
