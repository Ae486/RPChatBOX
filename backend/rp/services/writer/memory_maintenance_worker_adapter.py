"""S3b adapter for memory-maintenance worker structured output.

This module is deliberately adapter-only: it validates structured worker output
and maps it into the existing ``WorkerResult`` contract without writing Core
truth, projection truth, Runtime Workspace material, or proposal/apply records.
The later S3c handoff owns governance routing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from rp.models.memory.contract_registry import MemorySourceRef
from rp.models.memory.maintenance_candidate import MemoryMaintenanceCandidateBatch
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerContextPacket,
    WorkerExecutionRequest,
    WorkerResult,
    WorkerResultStatus,
)
from rp.services.memory.memory_candidate_validation_service import (
    MemoryCandidateValidationService,
)

S3_MEMORY_MAINTENANCE_CANDIDATE_KIND = "s3_memory_maintenance_candidate"
S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION = (
    "s3a.memory-maintenance-candidate.v1"
)
S3_MEMORY_WORKER_ADAPTER_ID = "s3_memory_maintenance_worker_adapter"
S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION = (
    "story-runtime.memory-maintenance-worker-output.v1"
)


class MemoryMaintenanceNoOp(BaseModel):
    """Explicit no-op output from a memory-maintenance worker."""

    model_config = ConfigDict(extra="forbid")

    reason_code: str
    message: str
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    inspected_block_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryMaintenanceFailure(BaseModel):
    """Structured worker-side failure output.

    This is for failures returned by the worker path itself. Adapter parse and
    validator failures are normalized separately so their source is unambiguous.
    """

    model_config = ConfigDict(extra="forbid")

    reason_code: str
    message: str
    retryable: bool = False
    tool_call_id: str | None = None
    invalid_output_path: str | None = None
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryMaintenanceWorkerStructuredOutput(BaseModel):
    """Strict S3b worker output variants before mapping into WorkerResult."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    status: Literal["candidate_batch", "no_op", "failure"]
    worker_id: str
    phase: str
    candidate_batch: MemoryMaintenanceCandidateBatch | None = None
    no_op: MemoryMaintenanceNoOp | None = None
    failure: MemoryMaintenanceFailure | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_status_payload(self) -> "MemoryMaintenanceWorkerStructuredOutput":
        payload_count = sum(
            value is not None
            for value in (self.candidate_batch, self.no_op, self.failure)
        )
        if payload_count != 1:
            raise ValueError(
                "structured output must carry exactly one status payload"
            )
        if self.status == "candidate_batch" and self.candidate_batch is None:
            raise ValueError("candidate_batch status requires candidate_batch")
        if self.status == "no_op" and self.no_op is None:
            raise ValueError("no_op status requires no_op")
        if self.status == "failure" and self.failure is None:
            raise ValueError("failure status requires failure")
        return self


class MemoryMaintenanceStructuredOutputRunner(Protocol):
    """Future-facing seam for fake, scripted, or real structured-output runs."""

    async def run(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        context_packet: WorkerContextPacket | None,
    ) -> MemoryMaintenanceWorkerStructuredOutput | dict[str, Any]:
        """Return raw or parsed structured output for the adapter to normalize."""


class ScriptedMemoryMaintenanceStructuredOutputRunner:
    """Deterministic fake runner for tests and future harness wiring."""

    def __init__(
        self,
        outputs: Sequence[MemoryMaintenanceWorkerStructuredOutput | dict[str, Any]],
    ) -> None:
        self._outputs = list(outputs)
        self.call_count = 0

    async def run(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        context_packet: WorkerContextPacket | None,
    ) -> MemoryMaintenanceWorkerStructuredOutput | dict[str, Any]:
        if not self._outputs:
            raise RuntimeError("scripted memory-maintenance output queue is empty")
        self.call_count += 1
        return self._outputs.pop(0)


class MemoryMaintenanceWorkerAdapter:
    """Map S3 memory-maintenance worker outputs to existing WorkerResult values."""

    def __init__(
        self,
        *,
        validation_service: MemoryCandidateValidationService | None = None,
        structured_output_runner: MemoryMaintenanceStructuredOutputRunner | None = None,
    ) -> None:
        self._validation_service = (
            validation_service or MemoryCandidateValidationService()
        )
        self._structured_output_runner = structured_output_runner

    @property
    def has_structured_output_runner(self) -> bool:
        """Report whether this adapter can execute through a configured runner."""

        return self._structured_output_runner is not None

    async def execute(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        context_packet: WorkerContextPacket | None = None,
        structured_output: MemoryMaintenanceWorkerStructuredOutput
        | dict[str, Any]
        | None = None,
    ) -> WorkerResult:
        """Validate structured output and produce a non-mutating WorkerResult."""

        if structured_output is None:
            if self._structured_output_runner is None:
                return self._failure_result(
                    request=request,
                    registration=registration,
                    reason_code="memory_worker_structured_output_runner_missing",
                    message="No structured output runner was configured.",
                    failure_source="fake_execution",
                    retryable=False,
                )
            try:
                structured_output = await self._structured_output_runner.run(
                    request=request,
                    registration=registration,
                    context_packet=context_packet,
                )
            except asyncio.CancelledError as exc:
                return self._failure_result(
                    request=request,
                    registration=registration,
                    reason_code="memory_worker_cancelled",
                    message=str(exc) or "Memory worker execution was cancelled.",
                    failure_source="runner_execution",
                    retryable=True,
                )
            except TimeoutError as exc:
                return self._failure_result(
                    request=request,
                    registration=registration,
                    reason_code="memory_worker_timeout",
                    message=str(exc) or "Memory worker execution timed out.",
                    failure_source="runner_execution",
                    retryable=True,
                )
            except Exception as exc:  # pragma: no cover - exact exception type is runner-owned.
                return self._failure_result(
                    request=request,
                    registration=registration,
                    reason_code="memory_worker_provider_error",
                    message=str(exc),
                    failure_source="runner_execution",
                    retryable=True,
                )

        parsed = self._parse_structured_output(
            request=request,
            registration=registration,
            structured_output=structured_output,
        )
        if isinstance(parsed, WorkerResult):
            return parsed

        if parsed.status == "candidate_batch" and parsed.candidate_batch is not None:
            return self._candidate_batch_result(
                request=request,
                registration=registration,
                output=parsed,
                batch=parsed.candidate_batch,
            )
        if parsed.status == "no_op" and parsed.no_op is not None:
            return self._no_op_result(
                request=request,
                registration=registration,
                output=parsed,
                no_op=parsed.no_op,
            )
        if parsed.status == "failure" and parsed.failure is not None:
            return self._worker_failure_result(
                request=request,
                registration=registration,
                output=parsed,
                failure=parsed.failure,
            )

        return self._failure_result(
            request=request,
            registration=registration,
            reason_code="memory_worker_invalid_structured_output",
            message="Structured output status did not match an adapter variant.",
            failure_source="schema_parse",
            retryable=False,
        )

    def _parse_structured_output(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        structured_output: MemoryMaintenanceWorkerStructuredOutput | dict[str, Any],
    ) -> MemoryMaintenanceWorkerStructuredOutput | WorkerResult:
        try:
            parsed = (
                structured_output
                if isinstance(
                    structured_output,
                    MemoryMaintenanceWorkerStructuredOutput,
                )
                else MemoryMaintenanceWorkerStructuredOutput.model_validate(
                    structured_output
                )
            )
        except ValidationError as exc:
            return self._failure_result(
                request=request,
                registration=registration,
                reason_code="memory_worker_invalid_structured_output",
                message=str(exc),
                failure_source="schema_parse",
                retryable=False,
            )

        findings: list[dict[str, Any]] = []
        if parsed.schema_version != S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION:
            findings.append(
                {
                    "reason_code": "memory_worker_output_schema_version_unsupported",
                    "message": (
                        "Unsupported memory-maintenance worker output schema version."
                    ),
                    "schema_version": parsed.schema_version,
                }
            )
        if parsed.worker_id != request.worker_id:
            findings.append(
                {
                    "reason_code": "memory_worker_output_worker_mismatch",
                    "message": "Structured output worker_id does not match request.",
                    "expected_worker_id": request.worker_id,
                    "actual_worker_id": parsed.worker_id,
                }
            )
        if parsed.phase != request.phase:
            findings.append(
                {
                    "reason_code": "memory_worker_output_phase_mismatch",
                    "message": "Structured output phase does not match request.",
                    "expected_phase": request.phase,
                    "actual_phase": parsed.phase,
                }
            )
        if findings:
            has_schema_version_mismatch = any(
                finding["reason_code"]
                == "memory_worker_output_schema_version_unsupported"
                for finding in findings
            )
            reason_code = (
                "memory_worker_output_schema_version_unsupported"
                if has_schema_version_mismatch
                else "memory_worker_structured_output_identity_mismatch"
            )
            message = (
                "Unsupported memory-maintenance worker output schema version."
                if has_schema_version_mismatch
                else "Structured output identity fields do not match request."
            )
            return self._failure_result(
                request=request,
                registration=registration,
                reason_code=reason_code,
                message=message,
                failure_source="schema_parse",
                retryable=False,
                validation_findings=findings,
                extra_trace_summary=self._runner_trace_summary(parsed),
            )
        return parsed

    def _candidate_batch_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        output: MemoryMaintenanceWorkerStructuredOutput,
        batch: MemoryMaintenanceCandidateBatch,
    ) -> WorkerResult:
        validation_failure = self._candidate_batch_schema_version_result(
            request=request,
            registration=registration,
            batch=batch,
        )
        if validation_failure is not None:
            return self._with_runner_trace_summary(validation_failure, output)

        validation_failure = self._candidate_batch_identity_result(
            request=request,
            registration=registration,
            batch=batch,
        )
        if validation_failure is not None:
            return self._with_runner_trace_summary(validation_failure, output)

        validation = self._validation_service.validate_batch(batch)
        if not validation.accepted:
            return self._with_runner_trace_summary(
                self._candidate_batch_validation_error_result(
                    request=request,
                    registration=registration,
                    validation_errors=validation.errors,
                ),
                output,
            )

        return self._candidate_batch_success_result(
            request=request,
            registration=registration,
            output=output,
            batch=batch,
        )

    def _candidate_batch_schema_version_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        batch: MemoryMaintenanceCandidateBatch,
    ) -> WorkerResult | None:
        if (
            batch.schema_version
            == S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION
        ):
            return None
        return self._failure_result(
            request=request,
            registration=registration,
            reason_code="memory_worker_candidate_batch_schema_version_unsupported",
            message="Unsupported memory-maintenance candidate batch schema version.",
            failure_source="validation",
            retryable=False,
            validation_findings=[
                {
                    "reason_code": (
                        "memory_worker_candidate_batch_schema_version_unsupported"
                    ),
                    "message": (
                        "Unsupported memory-maintenance candidate batch schema version."
                    ),
                    "expected_schema_version": (
                        S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION
                    ),
                    "actual_schema_version": batch.schema_version,
                }
            ],
        )

    @staticmethod
    def _candidate_batch_identity_result(
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        batch: MemoryMaintenanceCandidateBatch,
    ) -> WorkerResult | None:
        if batch.worker_id == request.worker_id and batch.phase == request.phase:
            return None
        return MemoryMaintenanceWorkerAdapter._failure_result(
            request=request,
            registration=registration,
            reason_code="memory_worker_candidate_batch_identity_mismatch",
            message="Candidate batch identity fields do not match request.",
            failure_source="validation",
            retryable=False,
            validation_findings=[
                {
                    "reason_code": "memory_worker_candidate_batch_identity_mismatch",
                    "message": "Candidate batch identity fields do not match request.",
                    "expected_worker_id": request.worker_id,
                    "actual_worker_id": batch.worker_id,
                    "expected_phase": request.phase,
                    "actual_phase": batch.phase,
                }
            ],
        )

    def _candidate_batch_validation_error_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        validation_errors: list[Any],
    ) -> WorkerResult:
        top_reason_code = self._top_level_validation_reason_code(validation_errors)
        return self._failure_result(
            request=request,
            registration=registration,
            reason_code=top_reason_code,
            message="Memory-maintenance candidate batch failed validation.",
            failure_source="validation",
            retryable=False,
            validation_findings=[
                {
                    "reason_code": error.code,
                    "message": error.message,
                    "candidate_index": error.candidate_index,
                    "operation_index": error.operation_index,
                    "target_domain": error.target_domain,
                    "target_block_id": error.target_block_id,
                    "operation_kind": error.operation_kind,
                }
                for error in validation_errors
            ],
        )

    @staticmethod
    def _top_level_validation_reason_code(validation_errors: list[Any]) -> str:
        if len(validation_errors) == 1:
            error_code = str(getattr(validation_errors[0], "code", "") or "")
            if error_code == "memory_candidate_missing_source_refs":
                return "memory_worker_source_ref_missing"
            if error_code == "memory_candidate_missing_base_block_revision":
                return "memory_worker_base_ref_missing"
        return "memory_worker_candidate_validation_failed"

    @staticmethod
    def _candidate_batch_success_candidate(
        *,
        registration: RuntimeWorkerRegistration,
        output: MemoryMaintenanceWorkerStructuredOutput,
        batch_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "candidate_kind": S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
            "payload": batch_payload,
            "source_of_truth": False,
            "authoritative_mutation": False,
            "metadata": {
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "schema_version": output.schema_version,
                "source_worker_id": registration.source_worker_id,
            },
        }

    def _candidate_batch_success_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        output: MemoryMaintenanceWorkerStructuredOutput,
        batch: MemoryMaintenanceCandidateBatch,
    ) -> WorkerResult:
        batch_payload = batch.model_dump(mode="json")
        return WorkerResult(
            worker_id=request.worker_id,
            phase=request.phase,
            result_status=WorkerResultStatus.COMPLETED,
            proposal_candidates=[
                self._candidate_batch_success_candidate(
                    registration=registration,
                    output=output,
                    batch_payload=batch_payload,
                )
            ],
            trace_summary={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "structured_output_status": "candidate_batch",
                "candidate_kind": S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
                "candidate_count": len(batch.candidates),
                "source_of_truth": False,
                "authoritative_mutation": False,
                "mutation_boundary": "candidate_only_no_truth_write",
                "context_packet_ref": request.context_packet_ref,
                **self._runner_trace_summary(output),
            },
            metadata={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "adapter_only": True,
                "runtime_truth": "worker_runtime_contract",
                "source_worker_id": registration.source_worker_id,
                "context_packet_ref": request.context_packet_ref,
                "source_of_truth": False,
                "authoritative_mutation": False,
                "structured_output_metadata": dict(output.metadata),
            },
        )

    def _no_op_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        output: MemoryMaintenanceWorkerStructuredOutput,
        no_op: MemoryMaintenanceNoOp,
    ) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            phase=request.phase,
            result_status=WorkerResultStatus.SKIPPED,
            proposal_candidates=[],
            evidence_refs=[
                f"{ref.source_type}:{ref.source_id}" for ref in no_op.source_refs
            ],
            trace_summary={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "structured_output_status": "no_op",
                "no_op_reason_code": no_op.reason_code,
                "no_op_message": no_op.message,
                "inspected_block_refs": list(no_op.inspected_block_refs),
                "source_of_truth": False,
                "authoritative_mutation": False,
                "context_packet_ref": request.context_packet_ref,
                **self._runner_trace_summary(output),
            },
            metadata={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "adapter_only": True,
                "runtime_truth": "worker_runtime_contract",
                "source_worker_id": registration.source_worker_id,
                "context_packet_ref": request.context_packet_ref,
                "source_of_truth": False,
                "authoritative_mutation": False,
                "no_op": True,
                "structured_output_metadata": dict(output.metadata),
                "no_op_metadata": dict(no_op.metadata),
            },
        )

    def _worker_failure_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        output: MemoryMaintenanceWorkerStructuredOutput,
        failure: MemoryMaintenanceFailure,
    ) -> WorkerResult:
        return self._failure_result(
            request=request,
            registration=registration,
            reason_code=failure.reason_code,
            message=failure.message,
            failure_source="worker_output_failure",
            retryable=failure.retryable,
            validation_findings=[
                {
                    "reason_code": failure.reason_code,
                    "message": failure.message,
                    "retryable": failure.retryable,
                    "tool_call_id": failure.tool_call_id,
                    "invalid_output_path": failure.invalid_output_path,
                }
            ],
            extra_metadata={
                "structured_output_metadata": dict(output.metadata),
                "failure_metadata": dict(failure.metadata),
            },
            extra_trace_summary=self._runner_trace_summary(output),
        )

    @staticmethod
    def _with_runner_trace_summary(
        result: WorkerResult,
        output: MemoryMaintenanceWorkerStructuredOutput,
    ) -> WorkerResult:
        runner_trace_summary = MemoryMaintenanceWorkerAdapter._runner_trace_summary(
            output
        )
        if not runner_trace_summary:
            return result
        return result.model_copy(
            update={
                "trace_summary": {
                    **dict(result.trace_summary),
                    **runner_trace_summary,
                },
                "metadata": {
                    **dict(result.metadata),
                    "runner_trace_summary": runner_trace_summary,
                },
            }
        )

    @staticmethod
    def _runner_trace_summary(
        output: MemoryMaintenanceWorkerStructuredOutput,
    ) -> dict[str, Any]:
        runner_trace = output.metadata.get("runner_trace")
        if not isinstance(runner_trace, dict):
            return {}

        summary: dict[str, Any] = {}
        field_map = {
            "runner_mode": "runner_mode",
            "schema_name": "runner_schema_name",
            "schema_version": "runner_schema_version",
            "provider_id": "runner_provider_id",
            "model_id": "runner_model_id",
        }
        for source_key, target_key in field_map.items():
            value = runner_trace.get(source_key)
            if isinstance(value, str) and value.strip():
                summary[target_key] = value
        return summary

    @staticmethod
    def _failure_result(
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        reason_code: str,
        message: str,
        failure_source: str,
        retryable: bool,
        validation_findings: list[dict[str, Any]] | None = None,
        extra_metadata: dict[str, Any] | None = None,
        extra_trace_summary: dict[str, Any] | None = None,
    ) -> WorkerResult:
        findings = validation_findings or [
            {
                "reason_code": reason_code,
                "message": message,
                "retryable": retryable,
            }
        ]
        return WorkerResult(
            worker_id=request.worker_id,
            phase=request.phase,
            result_status=WorkerResultStatus.FAILED,
            proposal_candidates=[],
            validation_findings=findings,
            trace_summary={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "failure_source": failure_source,
                "reason_code": reason_code,
                "message": message,
                "retryable": retryable,
                "source_of_truth": False,
                "authoritative_mutation": False,
                "context_packet_ref": request.context_packet_ref,
                **dict(extra_trace_summary or {}),
            },
            metadata={
                "adapter": S3_MEMORY_WORKER_ADAPTER_ID,
                "adapter_only": True,
                "runtime_truth": "worker_runtime_contract",
                "source_worker_id": registration.source_worker_id,
                "context_packet_ref": request.context_packet_ref,
                "source_of_truth": False,
                "authoritative_mutation": False,
                "failure_source": failure_source,
                **dict(extra_metadata or {}),
            },
        )
