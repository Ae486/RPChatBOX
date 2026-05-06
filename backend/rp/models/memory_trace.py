"""Read-only memory trace bundle contracts for debug and eval surfaces."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


MemoryTraceKind = Literal["turn", "branch", "source_ref", "proposal", "material"]

MEMORY_TRACE_READ_SURFACE_METADATA: dict[str, Any] = {
    "trace_role": "memory_debug_eval_read_surface",
    "source_of_truth": False,
    "event_replay": False,
    "mutation_surface": False,
}


class MemoryTraceBundle(BaseModel):
    """Deterministic read-only evidence bundle for one memory trace query.

    The bundle deliberately keeps events, materials, manifests, and proposal
    receipts as evidence. It does not collapse them into reconstructed Core,
    Projection, Recall, Archival, or Runtime Workspace truth.
    """

    model_config = ConfigDict(extra="forbid")

    trace_kind: MemoryTraceKind
    trace_scope: dict[str, Any] = Field(default_factory=dict)
    identity: MemoryRuntimeIdentity | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    runtime_workspace_materials: list[dict[str, Any]] = Field(default_factory=list)
    read_manifests: list[dict[str, Any]] = Field(default_factory=list)
    proposal_receipts: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_usage_refs: list[dict[str, Any]] = Field(default_factory=list)
    dirty_targets: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=lambda: dict(MEMORY_TRACE_READ_SURFACE_METADATA)
    )
