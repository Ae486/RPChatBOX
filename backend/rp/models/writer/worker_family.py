"""Worker execution family = dispatcher routing key; distinct from concrete kind/subtype."""

from __future__ import annotations

from enum import StrEnum


class WorkerFamily(StrEnum):
    MEMORY_MAINTENANCE = "memory_maintenance"
    WRITER = "writer"
    RETRIEVAL = "retrieval"
    RUNTIME_CONTEXT = "runtime_context"
    SIMPLE = "simple"
