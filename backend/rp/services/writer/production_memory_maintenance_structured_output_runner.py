"""Production S3.5 runner for memory-maintenance structured output."""

from __future__ import annotations

import json
from typing import Any

from models.chat import ChatMessage
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerContextPacket,
    WorkerExecutionRequest,
)
from rp.services.runtime.structured_output_runner import (
    STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED,
    STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT,
    STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR,
    STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT,
    STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED,
    StoryStructuredOutputRunner,
    StructuredOutputRunRequest,
    StructuredOutputRunResult,
    StructuredOutputRunner,
    StructuredOutputToolPolicy,
)

from .memory_maintenance_worker_adapter import (
    MemoryMaintenanceStructuredOutputRunner,
    S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
)


class ProductionMemoryMaintenanceStructuredOutputRunner:
    """Bind the generic structured-output port to the memory worker contract."""

    def __init__(
        self,
        *,
        structured_output_runner: StructuredOutputRunner | None = None,
        default_timeout_s: float = 30.0,
        repair_budget: int = 0,
    ) -> None:
        self._structured_output_runner = (
            structured_output_runner or StoryStructuredOutputRunner()
        )
        self._default_timeout_s = default_timeout_s
        self._repair_budget = repair_budget

    async def run(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        context_packet: WorkerContextPacket | None,
    ) -> dict[str, Any]:
        if context_packet is None:
            return self._failure_output(
                reason_code="memory_worker_context_packet_missing",
                message="Memory-maintenance worker requires a context packet.",
                retryable=False,
                trace={
                    "runner_mode": "production",
                    "worker_id": request.worker_id,
                    "phase": request.phase,
                    "context_packet_ref": request.context_packet_ref,
                },
            )

        model_id = str(request.model_id or "").strip()
        if not model_id:
            return self._failure_output(
                reason_code="memory_worker_provider_error",
                message="Memory-maintenance worker request is missing model_id.",
                retryable=False,
                trace={
                    "runner_mode": "production",
                    "worker_id": request.worker_id,
                    "phase": request.phase,
                    "context_packet_ref": request.context_packet_ref,
                },
            )

        run_result = await self._structured_output_runner.run(
            request=StructuredOutputRunRequest(
                run_id=request.request_id,
                role="memory-maintenance-worker",
                worker_id=request.worker_id,
                phase=request.phase,
                provider_id=request.provider_id,
                model_id=model_id,
                schema_name="memory-maintenance-worker-output",
                schema_version=S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
                messages=self._build_messages(
                    request=request,
                    registration=registration,
                    context_packet=context_packet,
                ),
                response_schema=self._response_schema(),
                tool_policy=StructuredOutputToolPolicy(
                    tool_calls_enabled=False,
                    allowed_tools=[],
                    tool_results_enabled=False,
                ),
                timeout_s=self._default_timeout_s,
                repair_budget=self._repair_budget,
                metadata={
                    "context_packet_ref": request.context_packet_ref,
                    "source_worker_id": registration.source_worker_id,
                },
                gateway_request_metadata={
                    "temperature": 0.0,
                    "max_tokens": 1600,
                },
            )
        )
        if run_result.status == "completed":
            return self._completed_output(run_result)
        return self._failure_from_run_result(run_result)

    @staticmethod
    def _response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema_version": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["candidate_batch", "no_op", "failure"],
                },
                "worker_id": {"type": "string"},
                "phase": {"type": "string"},
                "candidate_batch": {"type": "object"},
                "no_op": {"type": "object"},
                "failure": {"type": "object"},
                "metadata": {"type": "object"},
            },
            "required": ["schema_version", "status", "worker_id", "phase"],
        }

    def _build_messages(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        context_packet: WorkerContextPacket,
    ) -> list[ChatMessage]:
        system_prompt = (
            "You are the LongformMemoryWorker for story runtime.\n"
            "Return strict JSON only.\n"
            "Allowed statuses: candidate_batch, no_op, failure.\n"
            "Tool calls are disabled.\n"
            "Do not mutate truth directly."
        )
        user_payload = {
            "request": {
                "request_id": request.request_id,
                "worker_id": request.worker_id,
                "phase": request.phase,
                "mode": request.mode,
                "turn_id": request.turn_id,
                "identity": request.identity.model_dump(mode="json"),
                "reason_codes": list(request.reason_codes),
                "scheduler_constraints": dict(request.scheduler_constraints),
                "context_packet_ref": request.context_packet_ref,
            },
            "registration": {
                "source_worker_id": registration.source_worker_id,
                "descriptor": registration.descriptor.model_dump(mode="json"),
                "execution_policy": registration.execution_policy.model_dump(
                    mode="json"
                ),
            },
            "context_packet": context_packet.model_dump(mode="json"),
        }
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(
                role="user",
                content=json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
            ),
        ]

    def _completed_output(
        self,
        run_result: StructuredOutputRunResult,
    ) -> dict[str, Any]:
        structured_output = dict(run_result.structured_output or {})
        metadata = dict(structured_output.get("metadata") or {})
        metadata["runner_mode"] = run_result.trace.get("runner_mode")
        metadata["runner_trace"] = dict(run_result.trace)
        metadata["raw_output_visibility"] = run_result.raw_output_visibility
        structured_output["metadata"] = metadata
        return structured_output

    def _failure_from_run_result(
        self,
        run_result: StructuredOutputRunResult,
    ) -> dict[str, Any]:
        return self._failure_output(
            reason_code=self._map_reason_code(run_result),
            message=run_result.message or "Structured-output runner failed.",
            retryable=run_result.retryable,
            trace=dict(run_result.trace),
        )

    @staticmethod
    def _map_reason_code(run_result: StructuredOutputRunResult) -> str:
        reason_code = run_result.reason_code
        if reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT:
            return "memory_worker_timeout"
        if reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED:
            return "memory_worker_cancelled"
        if reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT:
            return "memory_worker_invalid_structured_output"
        if reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED:
            return "memory_worker_tool_calls_disabled"
        if reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR:
            return "memory_worker_provider_error"
        return "memory_worker_provider_error"

    @staticmethod
    def _failure_output(
        *,
        reason_code: str,
        message: str,
        retryable: bool,
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
            "status": "failure",
            "worker_id": trace.get("worker_id") or "LongformMemoryWorker",
            "phase": trace.get("phase") or "post_write_maintenance",
            "failure": {
                "reason_code": reason_code,
                "message": message,
                "retryable": retryable,
                "metadata": {
                    "runner_trace": trace,
                    "runner_mode": trace.get("runner_mode"),
                },
            },
            "metadata": {
                "runner_trace": trace,
                "runner_mode": trace.get("runner_mode"),
            },
        }


__all__ = [
    "MemoryMaintenanceStructuredOutputRunner",
    "ProductionMemoryMaintenanceStructuredOutputRunner",
]
