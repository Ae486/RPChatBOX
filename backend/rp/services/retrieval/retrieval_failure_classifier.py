"""Deterministic RET-013 writer-retrieval failure taxonomy classifier.

INPUT: a completed writer-retrieval harness outcome (succeeded flag, finish
reason, tool results).
OUTPUT: a normalized RetrievalOutcomeClassification distinguishing a broken
retrieval tool, an insufficient-source successful turn, and a model failure.
POS: retrieval-zone pure classifier; read-only over the harness result, no turn
mutation (RET-013 / ACC-11-retrieval-11).
"""

from __future__ import annotations

import json
from typing import Protocol

from rp.agent_runtime.kernel.runtime_tool_contracts import RuntimeToolResult
from rp.models.retrieval.runtime_contracts import (
    RETRIEVAL_INSUFFICIENCY_REASON_CODE,
    RetrievalFailureCategory,
    RetrievalOutcomeClassification,
)


class WriterRetrievalOutcome(Protocol):
    """Structural view of a completed writer-retrieval harness result."""

    succeeded: bool
    finish_reason: str | None
    tool_results: list[RuntimeToolResult]


def classify_writer_retrieval_outcome(
    result: WriterRetrievalOutcome,
) -> RetrievalOutcomeClassification | None:
    """Map a writer-retrieval outcome to its RET-013 normalized category.

    Precedence keeps the channels disjoint: a broken retrieval tool is the most
    specific signal, then an insufficient-but-successful search, then a residual
    model/harness failure. Returns ``None`` for a plain successful turn that
    produced usable hits and raised no retrieval-tool failure (no failure marker
    is warranted).
    """

    failed_tool = _first_failed_tool_result(result.tool_results)
    if failed_tool is not None:
        return RetrievalOutcomeClassification(
            category=RetrievalFailureCategory.RETRIEVAL_FAILURE,
            reason_code=failed_tool.error_code or "writer_retrieval_tool_failed",
        )
    if result.succeeded:
        if _has_insufficiency_signal(result.tool_results):
            return RetrievalOutcomeClassification(
                category=RetrievalFailureCategory.RETRIEVAL_INSUFFICIENCY,
                reason_code=RETRIEVAL_INSUFFICIENCY_REASON_CODE,
            )
        return None
    return RetrievalOutcomeClassification(
        category=RetrievalFailureCategory.MODEL_FAILURE,
        reason_code=str(result.finish_reason or "writer_retrieval_failed"),
    )


def _first_failed_tool_result(
    tool_results: list[RuntimeToolResult],
) -> RuntimeToolResult | None:
    for tool_result in tool_results:
        if not tool_result.success and tool_result.error_code:
            return tool_result
    return None


def _has_insufficiency_signal(tool_results: list[RuntimeToolResult]) -> bool:
    return any(
        tool_result.success
        and RETRIEVAL_INSUFFICIENCY_REASON_CODE in _tool_result_warnings(tool_result)
        for tool_result in tool_results
    )


def _tool_result_warnings(tool_result: RuntimeToolResult) -> list[str]:
    raw = tool_result.content_text
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [str(item) for item in warnings]
