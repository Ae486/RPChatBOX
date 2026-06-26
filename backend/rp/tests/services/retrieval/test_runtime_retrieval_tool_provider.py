"""Offline unit tests for the runtime retrieval tool provider."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rp.agent_runtime.kernel.runtime_tool_contracts import RuntimeToolCall
from rp.agent_runtime.story.harness_finalize import RuntimeFinalizeGuard
from rp.agent_runtime.story.harness_ports import RuntimeToolExecutor
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.writer.worker_memory import WorkerSourceRefBundle
from rp.services.retrieval.runtime_card_service import RuntimeRetrievalCardServiceError
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.services.retrieval.writer_usage_guard_service import (
    WriterRetrievalUsageGuardServiceError,
)


def _identity() -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-1",
        session_id="session-1",
        branch_head_id="branch-1",
        turn_id="turn-1",
        runtime_profile_snapshot_id="snapshot-1",
    )


def _call(tool_name: str, call_id: str, arguments: dict[str, object]) -> RuntimeToolCall:
    return RuntimeToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments=arguments,
        source_round=1,
    )


def _material(*, material_id: str, short_id: str, payload: dict[str, object]):
    return SimpleNamespace(material_id=material_id, short_id=short_id, payload=payload)


class _FakeSearchExecution:
    def __init__(self, *, output: object, materials: list[object] | None = None, miss_materials: list[object] | None = None) -> None:
        self.output = output
        self.materials = list(materials or [])
        self.miss_materials = list(miss_materials or [])


class _FakeRetrievalSearchService:
    def __init__(self, execution: _FakeSearchExecution) -> None:
        self.execution = execution
        self.calls: list[dict[str, object]] = []

    async def search_for_writer(self, *, identity, input_model, actor, attempt_index):
        self.calls.append(
            {
                "identity": identity,
                "input_model": input_model,
                "actor": actor,
                "attempt_index": attempt_index,
            }
        )
        return self.execution


class _FakeRuntimeRetrievalCardService:
    def __init__(self) -> None:
        self.expanded_payloads: list[dict[str, object]] = []
        self.usage_calls: list[dict[str, object]] = []
        self.bundle = WorkerSourceRefBundle(
            retrieval_card_material_ids=["retrieval_card_1"],
            retrieval_expanded_chunk_material_ids=["retrieval_expanded_1"],
            retrieval_usage_material_ids=["retrieval_usage_1"],
        )
        self.raise_on_expand: RuntimeRetrievalCardServiceError | None = None

    def expand_cards_by_refs(self, *, identity, card_refs, actor):
        if self.raise_on_expand is not None:
            raise self.raise_on_expand
        payload = _material(
            material_id="retrieval_expanded_1",
            short_id="X1",
            payload={
                "card_short_id": card_refs[0],
                "title": "Expanded Title",
                "summary": "Expanded summary",
                "text": "Expanded text",
            },
        )
        self.expanded_payloads.append(
            {"identity": identity, "card_refs": list(card_refs), "actor": actor}
        )
        return [payload]

    def record_writer_usage(
        self,
        *,
        identity,
        used_card_ids,
        used_expanded_chunk_ids,
        missed_query_ids,
        actor,
        knowledge_gaps,
    ):
        self.usage_calls.append(
            {
                "identity": identity,
                "used_card_ids": list(used_card_ids),
                "used_expanded_chunk_ids": list(used_expanded_chunk_ids),
                "missed_query_ids": list(missed_query_ids or []),
                "actor": actor,
                "knowledge_gaps": list(knowledge_gaps or []),
            }
        )
        return _material(
            material_id="retrieval_usage_1",
            short_id="U1",
            payload={
                "used_card_short_ids": list(used_card_ids),
                "expanded_card_short_ids": list(used_card_ids),
                "missed_query_short_ids": list(missed_query_ids or []),
                "knowledge_gaps": [
                    gap.model_dump(mode="json") if hasattr(gap, "model_dump") else gap
                    for gap in (knowledge_gaps or [])
                ],
            },
        )

    def build_source_ref_bundle(self, *, identity):
        self.bundle_identity = identity
        return self.bundle


class _AllowUsageGuard:
    def ensure_final_output_allowed(self, *, identity, retrieval_generation, usage_generation, usage_material_id):
        return None


class _RejectUsageGuard:
    def ensure_final_output_allowed(self, *, identity, retrieval_generation, usage_generation, usage_material_id):
        raise WriterRetrievalUsageGuardServiceError(
            "writer_retrieval_usage_required",
            identity.turn_id,
        )


@pytest.mark.asyncio
async def test_allowlist_dispatch_records_search_and_updates_generation():
    identity = _identity()
    card_service = _FakeRuntimeRetrievalCardService()
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=SimpleNamespace(
                model_dump_json=lambda exclude_none=True: json.dumps(
                    {"query": "storm", "results": [], "warnings": []}
                )
            ),
            materials=[_material(material_id="retrieval_card_1", short_id="R1", payload={"title": "A"})],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=card_service,
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )

    result = await provider.execute_tool_call(
        _call("retrieval.search", "call-1", {"query": "storm"}),
        visible_tool_names=("retrieval.search",),
    )

    assert result.success is True
    assert json.loads(result.content_text) == {"query": "storm", "results": [], "warnings": []}
    assert provider.tool_trace_refs[0] == "writer_tool:retrieval.search:call-1"
    assert provider._state.retrieval_generation == 1
    assert search_service.calls[0]["attempt_index"] == 1


@pytest.mark.asyncio
async def test_unknown_or_hidden_tool_is_typed_failure():
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )

    result = await provider.execute_tool_call(
        _call("retrieval.search", "call-2", {"query": "storm"}),
        visible_tool_names=("retrieval.expand",),
    )

    assert result.success is False
    assert result.error_code == "writer_retrieval_tool_not_allowed"


@pytest.mark.asyncio
async def test_attempt_limit_blocks_second_search_without_incrementing_past_limit():
    identity = _identity()
    card_service = _FakeRuntimeRetrievalCardService()
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=SimpleNamespace(
                model_dump_json=lambda exclude_none=True: json.dumps(
                    {"query": "storm", "results": [], "warnings": []}
                )
            ),
            materials=[],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=card_service,
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=1,
    )

    first = await provider.execute_tool_call(
        _call("retrieval.search", "call-1", {"query": "storm"}),
        visible_tool_names=("retrieval.search",),
    )
    second = await provider.execute_tool_call(
        _call("retrieval.search", "call-2", {"query": "storm again"}),
        visible_tool_names=("retrieval.search",),
    )

    assert first.success is True
    assert second.success is False
    assert second.error_code == "writer_retrieval_attempt_limit_exceeded"
    assert provider._state.attempts == 1


@pytest.mark.asyncio
async def test_usage_does_not_consume_attempt_budget():
    identity = _identity()
    card_service = _FakeRuntimeRetrievalCardService()
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=SimpleNamespace(
                model_dump_json=lambda exclude_none=True: json.dumps(
                    {"query": "storm", "results": [], "warnings": []}
                )
            ),
            materials=[],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=card_service,
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=1,
    )

    usage = await provider.execute_tool_call(
        _call(
            "retrieval.usage",
            "call-usage",
            {
                "used_card_short_ids": ["R1"],
                "used_expanded_short_ids": ["X1"],
                "missed_query_short_ids": [],
                "knowledge_gaps": [],
            },
        ),
        visible_tool_names=("retrieval.usage",),
    )
    search = await provider.execute_tool_call(
        _call("retrieval.search", "call-search", {"query": "storm"}),
        visible_tool_names=("retrieval.search", "retrieval.usage"),
    )

    assert usage.success is True
    assert search.success is True
    assert provider._state.attempts == 1


def test_finalize_guard_matrix():
    allowed_provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )
    rejected_provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        usage_guard_service=_RejectUsageGuard(),
        max_retrieval_attempts=3,
    )

    allowed = allowed_provider.evaluate_final_output(assistant_text="done")
    rejected = rejected_provider.evaluate_final_output(assistant_text="done")

    assert allowed.allowed is True
    assert rejected.allowed is False
    assert rejected.reason_code == "writer_retrieval_usage_required"


@pytest.mark.asyncio
async def test_card_service_error_returns_typed_result_on_expand():
    card_service = _FakeRuntimeRetrievalCardService()
    card_service.raise_on_expand = RuntimeRetrievalCardServiceError(
        "runtime_retrieval_expand_failed",
        "boom",
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=card_service,
        max_retrieval_attempts=3,
    )

    result = await provider.execute_tool_call(
        _call("retrieval.expand", "call-expand", {"card_short_ids": ["R1"]}),
        visible_tool_names=("retrieval.expand",),
    )

    assert result.success is False
    assert result.error_code == "runtime_retrieval_expand_failed"


def test_ports_are_runtime_checkable():
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )

    assert isinstance(provider, RuntimeToolExecutor)
    assert isinstance(provider, RuntimeFinalizeGuard)


@pytest.mark.asyncio
async def test_short_handles_only_in_tool_outputs():
    card_service = _FakeRuntimeRetrievalCardService()
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=SimpleNamespace(
                model_dump_json=lambda exclude_none=True: json.dumps(
                    {
                        "query": "storm",
                        "results": [
                            {
                                "result_id": "R1",
                                "title": "Storm",
                                "summary": "short summary",
                                "excerpt": "short excerpt",
                                "text": "short text",
                                "section": "S1",
                            }
                        ],
                        "warnings": [],
                    }
                )
            ),
            materials=[_material(material_id="retrieval_card_1", short_id="R1", payload={"title": "A"})],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=card_service,
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )

    search = await provider.execute_tool_call(
        _call("retrieval.search", "call-search", {"query": "storm"}),
        visible_tool_names=("retrieval.search",),
    )
    expand = await provider.execute_tool_call(
        _call("retrieval.expand", "call-expand", {"card_short_ids": ["R1"]}),
        visible_tool_names=("retrieval.expand",),
    )
    usage = await provider.execute_tool_call(
        _call(
            "retrieval.usage",
            "call-usage",
            {
                "used_card_short_ids": ["R1"],
                "used_expanded_short_ids": ["X1"],
                "missed_query_short_ids": [],
                "knowledge_gaps": [],
            },
        ),
        visible_tool_names=("retrieval.search", "retrieval.expand", "retrieval.usage"),
    )

    assert "hit_id" not in search.content_text
    assert "chunk_id" not in expand.content_text
    assert "material_id" not in usage.content_text
    assert '"result_id"' in search.content_text
    assert '"card_short_id"' in expand.content_text
    assert '"usage_short_id"' in usage.content_text
