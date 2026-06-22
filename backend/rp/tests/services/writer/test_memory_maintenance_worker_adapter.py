from __future__ import annotations

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerDescriptor,
    WorkerExecutionClass,
    WorkerExecutionPolicy,
    WorkerExecutionRequest,
    WorkerResultStatus,
)
from rp.services.writer.memory_maintenance_worker_adapter import (
    MemoryMaintenanceWorkerAdapter,
    S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
    S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
    S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
    ScriptedMemoryMaintenanceStructuredOutputRunner,
)
from rp.services.writer.worker_registry_service import LONGFORM_MEMORY_WORKER_ID


@pytest.mark.asyncio
async def test_valid_structured_candidate_batch_returns_non_truth_worker_candidate():
    adapter = MemoryMaintenanceWorkerAdapter()

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=_candidate_output(),
    )

    assert result.result_status == WorkerResultStatus.COMPLETED
    assert len(result.proposal_candidates) == 1
    candidate = result.proposal_candidates[0]
    assert candidate["candidate_kind"] == S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    assert candidate["source_of_truth"] is False
    assert candidate["authoritative_mutation"] is False
    assert candidate["metadata"] == {
        "adapter": "s3_memory_maintenance_worker_adapter",
        "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
        "source_worker_id": "specialist",
    }
    payload = candidate["payload"]
    assert payload["schema_version"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION
    )
    assert payload["worker_id"] == LONGFORM_MEMORY_WORKER_ID
    assert payload["phase"] == "post_write_maintenance"
    assert payload["candidates"][0]["target_domain"] == "current_scene"
    assert payload["candidates"][0]["target_block_id"] == "scene.frame"
    assert payload["candidates"][0]["base_block_revision_id"] == "block-revision-1"
    assert payload["candidates"][0]["operations"][0]["kind"] == "append_item"
    assert payload["candidates"][0]["operations"][0]["content"] == (
        "The storm has cut off the bridge."
    )
    assert result.metadata["source_of_truth"] is False
    assert result.metadata["authoritative_mutation"] is False
    assert result.trace_summary["mutation_boundary"] == (
        "candidate_only_no_truth_write"
    )
    assert result.recall_candidates == []
    assert result.projection_refresh_requests == []


@pytest.mark.asyncio
async def test_scripted_runner_path_returns_candidate_batch():
    runner = ScriptedMemoryMaintenanceStructuredOutputRunner([_candidate_output()])
    adapter = MemoryMaintenanceWorkerAdapter(structured_output_runner=runner)

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
    )

    assert runner.call_count == 1
    assert result.result_status == WorkerResultStatus.COMPLETED
    assert result.proposal_candidates[0]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )


@pytest.mark.asyncio
async def test_no_op_structured_output_returns_explicit_skip_without_candidate():
    adapter = MemoryMaintenanceWorkerAdapter()

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output={
            "schema_version": "story-runtime.memory-maintenance-worker-output.v1",
            "status": "no_op",
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": "post_write_maintenance",
            "no_op": {
                "reason_code": "memory_worker_no_relevant_change",
                "message": "Accepted source did not require memory maintenance.",
                "inspected_block_refs": ["current_scene:scene.frame"],
            },
        },
    )

    assert result.result_status == WorkerResultStatus.SKIPPED
    assert result.proposal_candidates == []
    assert result.trace_summary["structured_output_status"] == "no_op"
    assert result.trace_summary["no_op_reason_code"] == (
        "memory_worker_no_relevant_change"
    )
    assert result.metadata["no_op"] is True
    assert result.metadata["authoritative_mutation"] is False


@pytest.mark.asyncio
async def test_invalid_structured_output_returns_failure_with_stable_reason_code():
    adapter = MemoryMaintenanceWorkerAdapter()

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output={
            "schema_version": "story-runtime.memory-maintenance-worker-output.v1",
            "status": "candidate_batch",
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": "post_write_maintenance",
            "unexpected_field": "must fail closed",
        },
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.validation_findings[0]["reason_code"] == (
        "memory_worker_invalid_structured_output"
    )
    assert result.trace_summary["failure_source"] == "schema_parse"
    assert result.metadata["authoritative_mutation"] is False


@pytest.mark.asyncio
async def test_missing_worker_output_schema_version_fails_closed():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload.pop("schema_version")

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.validation_findings[0]["reason_code"] == (
        "memory_worker_invalid_structured_output"
    )
    assert result.trace_summary["failure_source"] == "schema_parse"


@pytest.mark.asyncio
async def test_unsupported_worker_output_schema_version_fails_closed():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload["schema_version"] = "story-runtime.memory-maintenance-worker-output.v0"

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.trace_summary["failure_source"] == "schema_parse"
    assert result.trace_summary["reason_code"] == (
        "memory_worker_structured_output_identity_mismatch"
    )
    assert [
        finding["reason_code"] for finding in result.validation_findings
    ] == ["memory_worker_output_schema_version_unsupported"]


@pytest.mark.asyncio
async def test_worker_output_identity_mismatch_fails_closed():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload["worker_id"] = "OtherWorker"

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.trace_summary["failure_source"] == "schema_parse"
    assert [
        finding["reason_code"] for finding in result.validation_findings
    ] == ["memory_worker_output_worker_mismatch"]


@pytest.mark.asyncio
async def test_candidate_batch_schema_version_mismatch_fails_closed():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload["candidate_batch"]["schema_version"] = (
        "s3.memory-maintenance-candidate.v0"
    )

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.trace_summary["failure_source"] == "validation"
    assert [
        finding["reason_code"] for finding in result.validation_findings
    ] == ["memory_worker_candidate_batch_schema_version_unsupported"]


@pytest.mark.asyncio
async def test_candidate_batch_identity_mismatch_fails_closed():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload["candidate_batch"]["worker_id"] = "OtherWorker"

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.trace_summary["failure_source"] == "validation"
    assert [
        finding["reason_code"] for finding in result.validation_findings
    ] == ["memory_worker_candidate_batch_identity_mismatch"]


@pytest.mark.asyncio
async def test_validator_rejected_candidate_returns_failure_and_reason_codes():
    adapter = MemoryMaintenanceWorkerAdapter()
    payload = _candidate_output()
    payload["candidate_batch"]["candidates"][0]["operations"][0]["kind"] = (
        "create_block"
    )

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output=payload,
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.trace_summary["failure_source"] == "validation"
    assert result.trace_summary["reason_code"] == (
        "memory_worker_candidate_validation_failed"
    )
    assert [
        finding["reason_code"] for finding in result.validation_findings
    ] == ["memory_candidate_forbidden_schema_operation"]


@pytest.mark.asyncio
async def test_structured_worker_failure_maps_to_failed_worker_result():
    adapter = MemoryMaintenanceWorkerAdapter()

    result = await adapter.execute(
        request=_request(),
        registration=_registration(),
        structured_output={
            "schema_version": "story-runtime.memory-maintenance-worker-output.v1",
            "status": "failure",
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": "post_write_maintenance",
            "failure": {
                "reason_code": "memory_worker_tool_error",
                "message": "Fake memory tool failed.",
                "retryable": True,
                "tool_call_id": "tool-call-1",
            },
        },
    )

    assert result.result_status == WorkerResultStatus.FAILED
    assert result.proposal_candidates == []
    assert result.validation_findings == [
        {
            "reason_code": "memory_worker_tool_error",
            "message": "Fake memory tool failed.",
            "retryable": True,
            "tool_call_id": "tool-call-1",
            "invalid_output_path": None,
        }
    ]
    assert result.trace_summary["failure_source"] == "worker_output_failure"


def _request() -> WorkerExecutionRequest:
    return WorkerExecutionRequest(
        request_id="worker-request-s3b-1",
        identity=MemoryRuntimeIdentity(
            story_id="story-s3b",
            session_id="session-s3b",
            branch_head_id="branch-s3b-main",
            turn_id="turn-s3b-1",
            runtime_profile_snapshot_id="snapshot-s3b-1",
        ),
        worker_id=LONGFORM_MEMORY_WORKER_ID,
        phase="post_write_maintenance",
        mode="longform",
        turn_id="turn-s3b-1",
        context_packet_ref="worker-packet-s3b-1",
        execution_policy=_execution_policy(),
    )


def _registration() -> RuntimeWorkerRegistration:
    return RuntimeWorkerRegistration(
        descriptor=WorkerDescriptor(
            worker_id=LONGFORM_MEMORY_WORKER_ID,
            display_name="Longform Memory Worker",
            default_execution_policy="longform_memory_worker.default",
            supported_phases=["post_write_maintenance"],
        ),
        execution_policy=_execution_policy(),
        source_worker_id="specialist",
    )


def _execution_policy() -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="longform_memory_worker.default",
        execution_class=WorkerExecutionClass.MAINTENANCE,
        blocking_default=True,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
    )


def _candidate_output():
    return {
        "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
        "status": "candidate_batch",
        "worker_id": LONGFORM_MEMORY_WORKER_ID,
        "phase": "post_write_maintenance",
        "candidate_batch": _candidate_batch_payload(),
        "metadata": {"fake_runner": True},
    }


def _candidate_batch_payload():
    return {
        "schema_version": S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
        "worker_id": LONGFORM_MEMORY_WORKER_ID,
        "phase": "post_write_maintenance",
        "candidates": [
            {
                "target_domain": "current_scene",
                "target_block_id": "scene.frame",
                "base_block_revision_id": "block-revision-1",
                "operations": [
                    {
                        "kind": "append_item",
                        "field_id": "facts",
                        "content": "The storm has cut off the bridge.",
                    }
                ],
                "source_refs": [
                    {
                        "source_type": "accepted_prose",
                        "source_id": "segment-1",
                        "layer": "runtime_workspace",
                    }
                ],
                "change_summary": "Track the bridge cutoff as scene framing.",
            }
        ],
    }
