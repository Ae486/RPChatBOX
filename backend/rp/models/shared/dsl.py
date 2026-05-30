"""Shared DSL-facing models for RP Phase A."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Domain(StrEnum):
    """Coarse domain used by CRUD/query/proposal contracts."""

    SCENE = "scene"
    CHARACTER = "character"
    KNOWLEDGE_BOUNDARY = "knowledge_boundary"
    RELATION = "relation"
    GOAL = "goal"
    PLOT_THREAD = "plot_thread"
    FORESHADOW = "foreshadow"
    TIMELINE = "timeline"
    WORLD_RULE = "world_rule"
    INVENTORY = "inventory"
    RULE_STATE = "rule_state"
    CHAPTER = "chapter"
    NARRATIVE_PROGRESS = "narrative_progress"


class Layer(StrEnum):
    """Memory OS logical layer names frozen for Phase A."""

    CORE_STATE_AUTHORITATIVE = "core_state.authoritative"
    CORE_STATE_PROJECTION = "core_state.projection"
    RECALL = "recall"
    ARCHIVAL = "archival"
    RUNTIME_WORKSPACE = "runtime_workspace"


class ContractRef(BaseModel):
    """Lightweight reference used by the Phase A shared schema."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    ref_type: str
    label: str | None = None


class RefSet(BaseModel):
    """Optional structured refs container for future Phase A use."""

    model_config = ConfigDict(extra="forbid")

    base: list[ContractRef] = Field(default_factory=list)
    sources: list[ContractRef] = Field(default_factory=list)
    provenance: list[ContractRef] = Field(default_factory=list)
    related: list[ContractRef] = Field(default_factory=list)


class EnvelopeMeta(BaseModel):
    """Shared envelope metadata fields used across typed exchanges."""

    model_config = ConfigDict(extra="forbid")

    story_id: str | None = None
    mode: str | None = None
    lifecycle: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    producer: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    reason: str | None = None
    confidence: float | None = None


class ObjectRef(BaseModel):
    """Reference to one memory object target."""

    model_config = ConfigDict(extra="forbid")

    object_id: str
    layer: Layer
    domain: Domain
    domain_path: str | None = None
    scope: str | None = None
    revision: int | None = None


class TypedEnvelope(BaseModel, Generic[T]):
    """Canonical typed envelope used by shared RP models."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    type: str
    story_id: str | None = None
    mode: str | None = None
    lifecycle: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    producer: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    refs: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    confidence: float | None = None
    payload: T

    def canonical_dump(self) -> dict[str, Any]:
        """Return the stable JSON shape expected by downstream serializers."""
        return self.model_dump(mode="json", exclude_none=True)
