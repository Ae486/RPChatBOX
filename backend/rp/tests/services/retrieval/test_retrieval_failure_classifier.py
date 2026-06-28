"""Deterministic RET-013 failure-taxonomy matrix for the writer-retrieval loop.

L1 fake-role: every injected fault is mapped to its own normalized category and
the three channels are proven pairwise distinct (no shared reason code). Real
provider output grounds the retrieval-tool failure / insufficiency codes; the
model-failure codes are the harness/finalize finish reasons.
"""

from __future__ import annotations

import json
from collections import defaultdict
from types import SimpleNamespace

import pytest

from rp.agent_runtime.kernel.runtime_tool_contracts import RuntimeToolResult
from rp.agent_runtime.story.story_harness import StoryHarnessResult
from rp.models.retrieval.runtime_contracts import (
    RETRIEVAL_INSUFFICIENCY_REASON_CODE,
    RetrievalFailureCategory,
)
from rp.services.retrieval.retrieval_failure_classifier import (
    classify_writer_retrieval_outcome,
)
from rp.services.retrieval.runtime_card_service import (
    RuntimeRetrievalCardServiceError,
)
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.tests.services.retrieval.test_runtime_retrieval_tool_provider import (
    _AllowUsageGuard,
    _FakeRetrievalSearchService,
    _FakeRuntimeRetrievalCardService,
    _FakeSearchExecution,
    _call,
    _identity,
    _material,
)


def _outcome(
    *,
    succeeded: bool,
    tool_results: list[RuntimeToolResult],
    finish_reason: str | None,
) -> StoryHarnessResult:
    return StoryHarnessResult(
        succeeded=succeeded,
        status="completed" if succeeded else "failed",
        tool_results=list(tool_results),
        finish_reason=finish_reason,
    )


def _search_output(*, results: list[dict], warnings: list[str]):
    payload = json.dumps({"query": "q", "results": results, "warnings": warnings})
    return SimpleNamespace(model_dump_json=lambda exclude_none=True: payload)


async def _real_tool_not_allowed() -> RuntimeToolResult:
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )
    return await provider.execute_tool_call(
        _call("retrieval.search", "call-not-allowed", {"query": "storm"}),
        visible_tool_names=("retrieval.expand",),
    )


async def _real_schema_invalid() -> RuntimeToolResult:
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )
    return await provider.execute_tool_call(
        _call("retrieval.search", "call-schema", {"query": ""}),
        visible_tool_names=("retrieval.search",),
    )


async def _real_card_service_error() -> RuntimeToolResult:
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
    return await provider.execute_tool_call(
        _call("retrieval.expand", "call-expand", {"card_short_ids": ["R1"]}),
        visible_tool_names=("retrieval.expand",),
    )


async def _real_attempt_limit() -> RuntimeToolResult:
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=_search_output(results=[], warnings=[]),
            materials=[],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=1,
    )
    await provider.execute_tool_call(
        _call("retrieval.search", "call-1", {"query": "storm"}),
        visible_tool_names=("retrieval.search",),
    )
    return await provider.execute_tool_call(
        _call("retrieval.search", "call-2", {"query": "storm again"}),
        visible_tool_names=("retrieval.search",),
    )


async def _real_zero_hit_search() -> RuntimeToolResult:
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=_search_output(
                results=[],
                warnings=[RETRIEVAL_INSUFFICIENCY_REASON_CODE],
            ),
            materials=[],
            miss_materials=[
                _material(material_id="retrieval_miss_1", short_id="M1", payload={}),
            ],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )
    return await provider.execute_tool_call(
        _call("retrieval.search", "call-miss", {"query": "ghost"}),
        visible_tool_names=("retrieval.search",),
    )


async def _real_hit_search() -> RuntimeToolResult:
    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=_search_output(
                results=[
                    {"result_id": "R1", "text": "The seal broke during the storm."}
                ],
                warnings=[],
            ),
            materials=[
                _material(material_id="retrieval_card_1", short_id="R1", payload={}),
            ],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )
    return await provider.execute_tool_call(
        _call("retrieval.search", "call-hit", {"query": "storm"}),
        visible_tool_names=("retrieval.search",),
    )


@pytest.mark.asyncio
async def test_tool_failures_classify_as_retrieval_failure_with_distinct_subcodes():
    cases = {
        "writer_retrieval_tool_not_allowed": await _real_tool_not_allowed(),
        "SCHEMA_VALIDATION_FAILED": await _real_schema_invalid(),
        "runtime_retrieval_expand_failed": await _real_card_service_error(),
        "writer_retrieval_attempt_limit_exceeded": await _real_attempt_limit(),
    }

    for expected_code, tool_result in cases.items():
        assert tool_result.success is False
        assert tool_result.error_code == expected_code
        classification = classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[tool_result],
                finish_reason="tool_execution_error",
            )
        )
        assert classification is not None
        assert classification.category is RetrievalFailureCategory.RETRIEVAL_FAILURE
        assert classification.reason_code == expected_code


@pytest.mark.asyncio
async def test_zero_hit_search_classifies_as_insufficiency_and_does_not_fail_turn():
    search_result = await _real_zero_hit_search()

    # Insufficiency rides on a SUCCESSFUL tool call: it can never trip the
    # failed-tool channel, so the turn proceeds (insufficiency != failure).
    assert search_result.success is True
    assert search_result.error_code is None

    classification = classify_writer_retrieval_outcome(
        _outcome(
            succeeded=True,
            tool_results=[search_result],
            finish_reason="assistant_final_text",
        )
    )

    assert classification is not None
    assert classification.category is RetrievalFailureCategory.RETRIEVAL_INSUFFICIENCY
    assert classification.reason_code == RETRIEVAL_INSUFFICIENCY_REASON_CODE


@pytest.mark.parametrize(
    "finish_reason",
    ["length", "error", "writer_retrieval_usage_required_before_final_output"],
)
def test_non_tool_failures_classify_as_model_failure(finish_reason: str):
    classification = classify_writer_retrieval_outcome(
        _outcome(succeeded=False, tool_results=[], finish_reason=finish_reason)
    )

    assert classification is not None
    assert classification.category is RetrievalFailureCategory.MODEL_FAILURE
    assert classification.reason_code == finish_reason


def test_model_failure_falls_back_when_finish_reason_missing():
    classification = classify_writer_retrieval_outcome(
        _outcome(succeeded=False, tool_results=[], finish_reason=None)
    )

    assert classification is not None
    assert classification.category is RetrievalFailureCategory.MODEL_FAILURE
    assert classification.reason_code == "writer_retrieval_failed"


@pytest.mark.asyncio
async def test_successful_turn_with_usable_hits_has_no_failure_marker():
    search_result = await _real_hit_search()

    classification = classify_writer_retrieval_outcome(
        _outcome(
            succeeded=True,
            tool_results=[search_result],
            finish_reason="assistant_final_text",
        )
    )

    assert classification is None


@pytest.mark.asyncio
async def test_failure_taxonomy_is_pairwise_distinct_no_shared_reason_code():
    classifications = {
        "tool_not_allowed": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[await _real_tool_not_allowed()],
                finish_reason="tool_execution_error",
            )
        ),
        "schema_invalid": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[await _real_schema_invalid()],
                finish_reason="tool_execution_error",
            )
        ),
        "card_error": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[await _real_card_service_error()],
                finish_reason="tool_execution_error",
            )
        ),
        "attempt_limit": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[await _real_attempt_limit()],
                finish_reason="tool_execution_error",
            )
        ),
        "insufficiency": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=True,
                tool_results=[await _real_zero_hit_search()],
                finish_reason="assistant_final_text",
            )
        ),
        "model_length": classify_writer_retrieval_outcome(
            _outcome(succeeded=False, tool_results=[], finish_reason="length")
        ),
        "model_usage": classify_writer_retrieval_outcome(
            _outcome(
                succeeded=False,
                tool_results=[],
                finish_reason="writer_retrieval_usage_required_before_final_output",
            )
        ),
    }
    assert all(item is not None for item in classifications.values())

    # All three normalized categories are present and distinct.
    categories = {item.category for item in classifications.values()}
    assert categories == {
        RetrievalFailureCategory.RETRIEVAL_FAILURE,
        RetrievalFailureCategory.RETRIEVAL_INSUFFICIENCY,
        RetrievalFailureCategory.MODEL_FAILURE,
    }

    # No normalized reason code is shared across two different categories.
    code_to_categories: dict[str, set[RetrievalFailureCategory]] = defaultdict(set)
    for item in classifications.values():
        code_to_categories[item.reason_code].add(item.category)
    for reason_code, owning_categories in code_to_categories.items():
        assert len(owning_categories) == 1, (
            f"reason_code {reason_code!r} spans categories {owning_categories!r}"
        )

    # The retrieval-tool failure sub-codes stay individually distinguishable.
    retrieval_failure_codes = [
        item.reason_code
        for item in classifications.values()
        if item.category is RetrievalFailureCategory.RETRIEVAL_FAILURE
    ]
    assert sorted(retrieval_failure_codes) == [
        "SCHEMA_VALIDATION_FAILED",
        "runtime_retrieval_expand_failed",
        "writer_retrieval_attempt_limit_exceeded",
        "writer_retrieval_tool_not_allowed",
    ]
