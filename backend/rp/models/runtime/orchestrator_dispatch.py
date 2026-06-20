"""Orchestrator dispatch contracts for story-runtime worker scheduling."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rp.models.memory.contract_registry import MemoryRuntimeIdentity


class OrchestratorDispatchSelection(BaseModel):
    """One orchestrator-proposed worker routing selection."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    source_unit_numbers: list[int] = Field(default_factory=list)
    focus_hint: str | None = None
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("worker_id")
    @classmethod
    def _require_worker_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="worker_id")

    @field_validator("source_unit_numbers")
    @classmethod
    def _normalize_source_unit_numbers(cls, values: list[int]) -> list[int]:
        normalized_values: list[int] = []
        seen: set[int] = set()
        for value in values:
            if value < 1:
                raise ValueError("source_unit_numbers must be >= 1")
            if value in seen:
                continue
            seen.add(value)
            normalized_values.append(value)
        return normalized_values


class OrchestratorDispatchToolInput(BaseModel):
    """The orchestrator's only worker routing output."""

    model_config = ConfigDict(extra="forbid")

    selections: list[OrchestratorDispatchSelection] = Field(default_factory=list)


class OrchestratorPlanProposal(BaseModel):
    """Typed proposal wrapper around the closed dispatch input."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    phase: str
    dispatch_input: OrchestratorDispatchToolInput
    metadata: dict[str, Any] = Field(default_factory=dict)


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
