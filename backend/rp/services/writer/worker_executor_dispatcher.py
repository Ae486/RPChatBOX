"""family→executor-route dispatcher; replaces worker_id literals with definition-driven routing (INV-07-worker-family-9)."""

from __future__ import annotations

from enum import StrEnum

from rp.models.writer.worker_family import WorkerFamily


class WorkerExecutorRoute(StrEnum):
    """Executor route selected from a worker family."""

    MEMORY_MAINTENANCE_STRUCTURED_OUTPUT = "memory_maintenance_structured_output"
    WRITER_TOOL_LOOP_HARNESS = "writer_tool_loop_harness"
    UNSUPPORTED = "unsupported"


_ROUTE_BY_FAMILY: dict[WorkerFamily, WorkerExecutorRoute] = {
    WorkerFamily.MEMORY_MAINTENANCE: WorkerExecutorRoute.MEMORY_MAINTENANCE_STRUCTURED_OUTPUT,
    WorkerFamily.WRITER: WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS,
    WorkerFamily.RETRIEVAL: WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS,
    WorkerFamily.RUNTIME_CONTEXT: WorkerExecutorRoute.UNSUPPORTED,
    WorkerFamily.SIMPLE: WorkerExecutorRoute.UNSUPPORTED,
}


class WorkerExecutorDispatcher:
    """Resolve a worker family into a concrete executor route."""

    _ROUTE_BY_FAMILY = _ROUTE_BY_FAMILY

    def resolve(self, family: WorkerFamily) -> WorkerExecutorRoute:
        return self._ROUTE_BY_FAMILY.get(family, WorkerExecutorRoute.UNSUPPORTED)
