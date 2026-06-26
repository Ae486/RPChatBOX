from __future__ import annotations

from types import SimpleNamespace

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.story.runtime import LongformTurnCommandKind
from rp.models.writer.worker_family import WorkerFamily
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerDescriptor,
    WorkerExecutionClass,
    WorkerExecutionPolicy,
    WorkerExecutionRequest,
    WorkerResultStatus,
)
from rp.services.writer.worker_executor_dispatcher import (
    WorkerExecutorDispatcher,
    WorkerExecutorRoute,
)
from rp.services.writer.worker_execution_service import (
    WorkerExecutionService,
    WorkerExecutionServiceError,
)


def test_worker_executor_dispatcher_routes_by_family() -> None:
    dispatcher = WorkerExecutorDispatcher()

    assert (
        dispatcher.resolve(WorkerFamily.MEMORY_MAINTENANCE)
        == WorkerExecutorRoute.MEMORY_MAINTENANCE_STRUCTURED_OUTPUT
    )
    assert (
        dispatcher.resolve(WorkerFamily.WRITER)
        == WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS
    )
    assert (
        dispatcher.resolve(WorkerFamily.RETRIEVAL)
        == WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS
    )
    assert (
        dispatcher.resolve(WorkerFamily.RUNTIME_CONTEXT)
        == WorkerExecutorRoute.UNSUPPORTED
    )
    assert dispatcher.resolve(WorkerFamily.SIMPLE) == WorkerExecutorRoute.UNSUPPORTED


@pytest.mark.asyncio
async def test_execute_one_routes_memory_family_by_family_not_worker_id() -> None:
    service = _service()
    request = _request(worker_id="CharacterMemoryWorker")
    registration = _registration(
        worker_id="CharacterMemoryWorker",
        family=WorkerFamily.MEMORY_MAINTENANCE,
        allow_degrade=False,
    )

    outcome = await service._execute_one(  # noqa: SLF001
        request=request,
        registration=registration,
        session=SimpleNamespace(),
        chapter=SimpleNamespace(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model-a",
        provider_id="provider-a",
        user_prompt="Continue.",
        orchestrator_plan=SimpleNamespace(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert outcome.worker_result.result_status == WorkerResultStatus.DEGRADED
    assert outcome.worker_result.trace_summary["degrade_reason"] == (
        "runtime_worker_executor_missing"
    )
    assert outcome.worker_result.metadata["degraded"] is True


@pytest.mark.asyncio
async def test_execute_one_routes_non_memory_family_to_fallback() -> None:
    adapter = _FailIfCalledAdapter()
    service = _service(longform_memory_worker_adapter=adapter)
    request = _request(worker_id="WritingWorker")
    registration = _registration(
        worker_id="WritingWorker",
        family=WorkerFamily.WRITER,
        allow_degrade=True,
    )

    outcome = await service._execute_one(  # noqa: SLF001
        request=request,
        registration=registration,
        session=SimpleNamespace(),
        chapter=SimpleNamespace(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model-a",
        provider_id="provider-a",
        user_prompt="Continue.",
        orchestrator_plan=SimpleNamespace(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert adapter.calls == 0
    assert outcome.worker_result.result_status == WorkerResultStatus.DEGRADED
    assert outcome.worker_result.trace_summary["degrade_reason"] == (
        "runtime_worker_executor_missing"
    )
    assert outcome.worker_result.metadata["degraded"] is True


@pytest.mark.asyncio
async def test_execute_one_raises_for_non_memory_family_when_degrade_disabled() -> None:
    service = _service(longform_memory_worker_adapter=_FailIfCalledAdapter())
    request = _request(worker_id="SimpleWorker")
    registration = _registration(
        worker_id="SimpleWorker",
        family=WorkerFamily.SIMPLE,
        allow_degrade=False,
    )

    with pytest.raises(WorkerExecutionServiceError) as exc_info:
        await service._execute_one(  # noqa: SLF001
            request=request,
            registration=registration,
            session=SimpleNamespace(),
            chapter=SimpleNamespace(),
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
            model_id="model-a",
            provider_id="provider-a",
            user_prompt="Continue.",
            orchestrator_plan=SimpleNamespace(),
            accepted_segments=[],
            pending_artifact=None,
        )

    assert exc_info.value.code == "runtime_worker_executor_not_supported"
    assert "SimpleWorker" in str(exc_info.value)


def _service(*, longform_memory_worker_adapter=None) -> WorkerExecutionService:
    return WorkerExecutionService(
        worker_registry_service=SimpleNamespace(),
        longform_specialist_service=SimpleNamespace(),
        longform_memory_worker_adapter=longform_memory_worker_adapter,
    )


def _request(*, worker_id: str) -> WorkerExecutionRequest:
    return WorkerExecutionRequest(
        request_id="worker-request-1",
        identity=MemoryRuntimeIdentity(
            story_id="story-1",
            session_id="session-1",
            branch_head_id="branch-1",
            turn_id="turn-1",
            runtime_profile_snapshot_id="snapshot-1",
        ),
        worker_id=worker_id,
        phase="post_write_maintenance",
        mode="longform",
        turn_id="turn-1",
        model_id="model-a",
        provider_id="provider-a",
        context_packet_ref="worker-packet-1",
        execution_policy=_execution_policy(allow_degrade=True),
    )


def _registration(
    *,
    worker_id: str,
    family: WorkerFamily,
    allow_degrade: bool,
) -> RuntimeWorkerRegistration:
    return RuntimeWorkerRegistration(
        descriptor=WorkerDescriptor(
            worker_id=worker_id,
            display_name="Worker",
            kind="memory_maintenance_worker",
            family=family,
            default_execution_policy="worker.default",
            supported_phases=["post_write_maintenance"],
        ),
        execution_policy=_execution_policy(allow_degrade=allow_degrade),
        source_worker_id="specialist",
    )


def _execution_policy(*, allow_degrade: bool) -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="worker.default",
        execution_class=WorkerExecutionClass.MAINTENANCE,
        blocking_default=True,
        allow_async=False,
        allow_degrade=allow_degrade,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
    )


class _FailIfCalledAdapter:
    def __init__(self) -> None:
        self.calls = 0
        self.has_structured_output_runner = True

    async def execute(self, **kwargs):
        self.calls += 1
        raise AssertionError("memory adapter should not be called for this family")
