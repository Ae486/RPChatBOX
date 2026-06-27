"""S-Y1 oracle test 6: durable-gate verdict equals the in-flight guard verdict.

Codex blocker B1: a durable gate that merely counts usage materials would
false-pass ``search -> usage -> expand`` (stale usage), violating RET-005. This
test proves ``RuntimeRetrievalToolProvider.final_ledger_snapshot()`` is a
faithful carry-forward of the order-sensitive in-flight ``_LedgerState`` by
cross-checking, on a shared fixture, the durable re-application of the frozen
guard rule against ``evaluate_final_output`` for every tool sequence.

Offline, deterministic, L1 (no network / no keys).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rp.agent_runtime.kernel.runtime_tool_contracts import RuntimeToolCall
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writer.worker_memory import WorkerSourceRefBundle
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.services.retrieval.writer_usage_guard_service import (
    WriterRetrievalUsageGuardService,
    WriterRetrievalUsageGuardServiceError,
)


SEARCH_TOOL = "retrieval.search"
EXPAND_TOOL = "retrieval.expand"
USAGE_TOOL = "retrieval.usage"
VISIBLE = (SEARCH_TOOL, EXPAND_TOOL, USAGE_TOOL)

_SEARCH = (SEARCH_TOOL, {"query": "storm"})
_EXPAND = (EXPAND_TOOL, {"card_short_ids": ["R1"]})
_USAGE = (
    USAGE_TOOL,
    {
        "used_card_short_ids": ["R1"],
        "used_expanded_short_ids": [],
        "missed_query_short_ids": [],
        "knowledge_gaps": [],
    },
)


def _identity() -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-1",
        session_id="session-1",
        branch_head_id="branch-1",
        turn_id="turn-1",
        runtime_profile_snapshot_id="snapshot-1",
    )


def _material(*, material_id: str, short_id: str, material_kind, payload=None):
    return SimpleNamespace(
        material_id=material_id,
        short_id=short_id,
        material_kind=material_kind,
        payload=payload or {},
    )


class _SearchExecution:
    def __init__(self) -> None:
        self.output = SimpleNamespace(
            model_dump_json=lambda exclude_none=True: json.dumps(
                {"query": "storm", "results": [], "warnings": []}
            )
        )
        self.materials = [
            _material(
                material_id="retrieval_card_1",
                short_id="R1",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            )
        ]
        self.miss_materials: list[object] = []


class _SearchService:
    async def search_for_writer(self, *, identity, input_model, actor, attempt_index):
        return _SearchExecution()


class _CardService:
    """Minimal fake exposing the surface the provider + guard consume."""

    def expand_cards_by_refs(self, *, identity, card_refs, actor):
        return [
            _material(
                material_id="retrieval_expanded_1",
                short_id="X1",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
                payload={
                    "card_short_id": card_refs[0],
                    "title": "Expanded",
                    "summary": "summary",
                    "text": "text",
                },
            )
        ]

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
        return _material(
            material_id="retrieval_usage_1",
            short_id="U1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            payload={
                "used_card_short_ids": list(used_card_ids),
                "expanded_card_short_ids": [],
                "missed_query_short_ids": list(missed_query_ids or []),
                "knowledge_gaps": [],
            },
        )

    def build_source_ref_bundle(self, *, identity):
        return WorkerSourceRefBundle()

    def require_material(self, *, identity, material_id):
        # The writer loop only ever sets usage_material_id to a real usage
        # record; the durable gate kind-checks that id.
        return _material(
            material_id=material_id,
            short_id="U1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
        )


def _call(tool_name: str, call_id: str, arguments: dict) -> RuntimeToolCall:
    return RuntimeToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments=arguments,
        source_round=1,
    )


async def _drive(steps: list[tuple[str, dict]]):
    identity = _identity()
    card_service = _CardService()
    provider = RuntimeRetrievalToolProvider(
        identity=identity,
        runtime_retrieval_card_service=card_service,
        runtime_retrieval_search_service=_SearchService(),
        usage_guard_service=WriterRetrievalUsageGuardService(
            runtime_retrieval_card_service=card_service
        ),
        max_retrieval_attempts=5,
    )
    for index, (tool_name, arguments) in enumerate(steps):
        result = await provider.execute_tool_call(
            _call(tool_name, f"call-{index}", arguments),
            visible_tool_names=VISIBLE,
        )
        assert result.success is True, result.error_code

    snapshot = provider.final_ledger_snapshot()
    in_flight = provider.evaluate_final_output(assistant_text="done")

    # Durable re-application: the production gate reads these generations from the
    # persisted ledger and re-applies the SAME frozen guard rule.
    durable_allowed = True
    try:
        WriterRetrievalUsageGuardService(
            runtime_retrieval_card_service=card_service
        ).ensure_final_output_allowed(
            identity=identity,
            retrieval_generation=snapshot.retrieval_generation,
            usage_generation=snapshot.usage_generation,
            usage_material_id=snapshot.usage_material_id,
        )
    except WriterRetrievalUsageGuardServiceError:
        durable_allowed = False
    return snapshot, in_flight, durable_allowed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "steps, expected_allowed, expected_ret, expected_use, expected_mat",
    [
        ([_SEARCH], False, 1, 0, None),
        ([_SEARCH, _USAGE], True, 1, 1, "retrieval_usage_1"),
        ([_SEARCH, _USAGE, _EXPAND], False, 2, 1, None),  # B1 expand-after-usage
        ([_SEARCH, _USAGE, _EXPAND, _USAGE], True, 2, 2, "retrieval_usage_1"),
        ([_SEARCH, _USAGE, _USAGE], True, 1, 1, "retrieval_usage_1"),
    ],
    ids=[
        "search",
        "search-usage",
        "search-usage-expand",
        "search-usage-expand-usage",
        "search-usage-usage",
    ],
)
async def test_durable_gate_matches_in_flight_guard(
    steps,
    expected_allowed,
    expected_ret,
    expected_use,
    expected_mat,
) -> None:
    snapshot, in_flight, durable_allowed = await _drive(steps)

    # The snapshot is the faithful carry-forward of the order-sensitive ledger.
    assert snapshot.retrieval_generation == expected_ret
    assert snapshot.usage_generation == expected_use
    assert snapshot.usage_material_id == expected_mat

    # Durable verdict == in-flight verdict == expected, for every sequence.
    assert in_flight.allowed == expected_allowed
    assert durable_allowed == expected_allowed
    assert durable_allowed == in_flight.allowed
