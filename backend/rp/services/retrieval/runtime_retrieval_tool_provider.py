"""Production writer-retrieval tool provider over the harness executor/finalize ports.

INPUT: runtime tool calls and visible tool names from the story harness.
OUTPUT: typed runtime tool results plus finalize-guard decisions.
POS: production writer-retrieval tool provider over the harness executor/finalize ports; candidate-only, source_of_truth=False; setup-free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from rp.agent_runtime.kernel.runtime_tool_contracts import (
    RuntimeToolCall,
    RuntimeToolResult,
)
from rp.agent_runtime.story.harness_finalize import FinalizeGuardDecision
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.retrieval.runtime_contracts import (
    RetrievalUsageLedgerSnapshot,
    WriterRetrievalExpandToolInput,
    WriterRetrievalSearchToolInput,
    WriterRetrievalUsageToolInput,
)
from .runtime_card_service import (
    RuntimeRetrievalCardService,
    RuntimeRetrievalCardServiceError,
)
from .runtime_search_service import RuntimeRetrievalSearchService
from .retrieval_tool_definitions import (
    WRITER_RETRIEVAL_EXPAND_TOOL,
    WRITER_RETRIEVAL_SEARCH_TOOL,
    WRITER_RETRIEVAL_USAGE_TOOL,
    writer_retrieval_tool_definitions,
)
from .writer_usage_guard_service import (
    WriterRetrievalUsageGuardService,
    WriterRetrievalUsageGuardServiceError,
)


@dataclass
class _LedgerState:
    retrieval_generation: int = 0
    usage_generation: int = 0
    usage_material_id: str | None = None
    tool_trace_refs: list[str] = field(default_factory=list)
    attempts: int = 0


class RuntimeRetrievalToolProvider:
    SOURCE_OF_TRUTH = False

    def __init__(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        runtime_retrieval_card_service: RuntimeRetrievalCardService,
        max_retrieval_attempts: int,
        runtime_retrieval_search_service: RuntimeRetrievalSearchService | None = None,
        usage_guard_service: WriterRetrievalUsageGuardService | None = None,
    ) -> None:
        if max_retrieval_attempts <= 0:
            raise ValueError(
                f"writer_retrieval_attempt_limit_invalid:{max_retrieval_attempts}"
            )
        self._identity = identity
        self._runtime_retrieval_card_service = runtime_retrieval_card_service
        self._runtime_retrieval_search_service = (
            runtime_retrieval_search_service
            or RuntimeRetrievalSearchService(
                runtime_retrieval_card_service=runtime_retrieval_card_service
            )
        )
        self._usage_guard_service = (
            usage_guard_service
            or WriterRetrievalUsageGuardService(
                runtime_retrieval_card_service=runtime_retrieval_card_service
            )
        )
        self._max_retrieval_attempts = max_retrieval_attempts
        self._state = _LedgerState()

    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        return writer_retrieval_tool_definitions(
            visible_tool_names=visible_tool_names,
        )

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        tool_name = call.tool_name
        arguments = dict(call.arguments or {})
        if tool_name not in visible_tool_names or tool_name not in {
            WRITER_RETRIEVAL_SEARCH_TOOL,
            WRITER_RETRIEVAL_EXPAND_TOOL,
            WRITER_RETRIEVAL_USAGE_TOOL,
        }:
            self._append_tool_trace_ref(
                tool_name=tool_name,
                call_id=call.call_id,
            )
            return self._typed_error_result(
                call=call,
                error_code="writer_retrieval_tool_not_allowed",
                message=tool_name,
            )
        try:
            if tool_name in {
                WRITER_RETRIEVAL_SEARCH_TOOL,
                WRITER_RETRIEVAL_EXPAND_TOOL,
            }:
                if self._state.attempts >= self._max_retrieval_attempts:
                    return self._typed_error_result(
                        call=call,
                        error_code="writer_retrieval_attempt_limit_exceeded",
                        message=str(self._max_retrieval_attempts),
                    )
                self._state.attempts += 1
                self._append_tool_trace_ref(
                    tool_name=tool_name,
                    call_id=call.call_id,
                )
            if tool_name == WRITER_RETRIEVAL_SEARCH_TOOL:
                content_text = await self._handle_search(
                    arguments=arguments,
                    attempt_index=self._state.attempts,
                )
            elif tool_name == WRITER_RETRIEVAL_EXPAND_TOOL:
                content_text = self._handle_expand(arguments=arguments)
            else:
                content_text = self._handle_usage(arguments=arguments)
        except ValidationError as exc:
            return self._typed_error_result(
                call=call,
                error_code="SCHEMA_VALIDATION_FAILED",
                message=f"Writer retrieval tool arguments failed validation: {exc}",
            )
        except (
            RuntimeRetrievalCardServiceError,
            WriterRetrievalUsageGuardServiceError,
        ) as exc:
            return self._typed_error_result(
                call=call,
                error_code=exc.code,
                message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive surface
            return self._typed_error_result(
                call=call,
                error_code="writer_retrieval_tool_execution_error",
                message=f"Writer retrieval tool execution failed: {exc}",
            )
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=tool_name,
            success=True,
            content_text=content_text,
            structured_payload={"content_payload_json": content_text},
        )

    def evaluate_final_output(self, *, assistant_text: str) -> FinalizeGuardDecision:
        try:
            self._usage_guard_service.ensure_final_output_allowed(
                identity=self._identity,
                retrieval_generation=self._state.retrieval_generation,
                usage_generation=self._state.usage_generation,
                usage_material_id=self._state.usage_material_id,
            )
            return FinalizeGuardDecision(allowed=True)
        except WriterRetrievalUsageGuardServiceError as exc:
            return FinalizeGuardDecision(allowed=False, reason_code=exc.code)

    def build_source_ref_bundle(self):
        return self._runtime_retrieval_card_service.build_source_ref_bundle(
            identity=self._identity
        )

    @property
    def tool_trace_refs(self) -> list[str]:
        return list(self._state.tool_trace_refs)

    def final_ledger_snapshot(self) -> RetrievalUsageLedgerSnapshot:
        """Read-only durable carry-forward of the in-flight gate ledger state."""

        return RetrievalUsageLedgerSnapshot(
            retrieval_generation=self._state.retrieval_generation,
            usage_generation=self._state.usage_generation,
            usage_material_id=self._state.usage_material_id,
            tool_trace_refs=list(self._state.tool_trace_refs),
        )

    async def _handle_search(self, *, arguments: dict[str, Any], attempt_index: int) -> str:
        payload = WriterRetrievalSearchToolInput.model_validate(arguments)
        execution = await self._runtime_retrieval_search_service.search_for_writer(
            identity=self._identity,
            input_model=payload,
            actor="writer.retrieval",
            attempt_index=attempt_index,
        )
        if execution.materials or execution.miss_materials:
            self._state.retrieval_generation += 1
            for material_id in [
                *(material.material_id for material in execution.materials),
                *(material.material_id for material in execution.miss_materials),
            ]:
                self._state.tool_trace_refs.append(f"runtime_workspace:{material_id}")
        self._state.usage_material_id = None
        return execution.output.model_dump_json(exclude_none=True)

    def _handle_expand(self, *, arguments: dict[str, Any]) -> str:
        payload = WriterRetrievalExpandToolInput.model_validate(arguments)
        expanded = self._runtime_retrieval_card_service.expand_cards_by_refs(
            identity=self._identity,
            card_refs=payload.card_short_ids,
            actor="writer.retrieval",
        )
        if expanded:
            self._state.retrieval_generation += 1
            self._state.usage_material_id = None
            for material in expanded:
                self._state.tool_trace_refs.append(
                    f"runtime_workspace:{material.material_id}"
                )
        return json.dumps(
            {
                "expanded": [self._expanded_tool_payload(item) for item in expanded],
            },
            ensure_ascii=False,
        )

    def _handle_usage(self, *, arguments: dict[str, Any]) -> str:
        payload = WriterRetrievalUsageToolInput.model_validate(arguments)
        usage = self._runtime_retrieval_card_service.record_writer_usage(
            identity=self._identity,
            used_card_ids=payload.used_card_short_ids,
            used_expanded_chunk_ids=payload.used_expanded_short_ids,
            missed_query_ids=payload.missed_query_short_ids,
            actor="writer.retrieval",
            knowledge_gaps=payload.knowledge_gaps,
        )
        self._state.usage_generation = self._state.retrieval_generation
        self._state.usage_material_id = usage.material_id
        self._state.tool_trace_refs.append(f"runtime_workspace:{usage.material_id}")
        return json.dumps(
            {
                "usage_short_id": usage.short_id,
                "used_card_short_ids": usage.payload.get("used_card_short_ids", []),
                "expanded_card_short_ids": usage.payload.get(
                    "expanded_card_short_ids", []
                ),
                "missed_query_short_ids": usage.payload.get(
                    "missed_query_short_ids", []
                ),
                "knowledge_gaps": usage.payload.get("knowledge_gaps", []),
            },
            ensure_ascii=False,
        )

    def _typed_error_result(
        self,
        *,
        call: RuntimeToolCall,
        error_code: str,
        message: str,
    ) -> RuntimeToolResult:
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=False,
            error_code=error_code,
            content_text=json.dumps(
                {"error": {"code": error_code, "message": message}},
                ensure_ascii=False,
            ),
        )

    def _append_tool_trace_ref(self, *, tool_name: str, call_id: str) -> str:
        trace_ref = f"writer_tool:{tool_name}:{call_id}"
        self._state.tool_trace_refs.append(trace_ref)
        return trace_ref

    @staticmethod
    def _expanded_tool_payload(material) -> dict[str, Any]:
        return {
            "short_id": material.short_id,
            "card_short_id": material.payload.get("card_short_id"),
            "title": material.payload.get("title"),
            "summary": material.payload.get("summary"),
            "text": material.payload.get("text"),
        }
