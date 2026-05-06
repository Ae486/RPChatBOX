"""Shared authoritative Core mutation contracts for governed write paths."""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from rp.models.dsl import Domain, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_crud import StatePatchOperation


CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT = "user_direct_edit"
CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY = "worker_proposal_apply"
CORE_MUTATION_ORIGIN_BRAINSTORM_SUMMARY_APPLY = "brainstorm_summary_apply"
CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH = "deterministic_system_refresh"

CoreMutationOriginKind = Literal[
    "user_direct_edit",
    "worker_proposal_apply",
    "brainstorm_summary_apply",
    "deterministic_system_refresh",
]


class CoreMutationEnvelope(BaseModel):
    """Shared authoritative Core mutation envelope.

    `identity` remains optional for legacy/system-triggered callers that do not
    yet carry full boot-bar runtime identity. Outcome hooks only run when an
    identity is present.
    """

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity | None = None
    origin_kind: CoreMutationOriginKind
    actor: str
    worker_id: str | None = None
    phase: str | None = None
    domain: Domain
    domain_path: str | None = None
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    permission_decision: str | None = None
    permission_reason_codes: list[str] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator(
        "worker_id",
        "phase",
        "domain_path",
        "permission_decision",
        "reason",
    )
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("trace_refs", "permission_reason_codes")
    @classmethod
    def _normalize_text_lists(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _normalize_unique_text_list(
            values,
            field_name=info.field_name or "values",
        )

    @model_validator(mode="after")
    def _validate_origin_specific_fields(self) -> "CoreMutationEnvelope":
        if self.origin_kind == CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY:
            missing: list[str] = []
            if self.identity is None:
                missing.append("identity")
            if self.worker_id is None:
                missing.append("worker_id")
            if self.phase is None:
                missing.append("phase")
            if self.permission_decision is None:
                missing.append("permission_decision")
            if missing:
                raise ValueError("worker_proposal_apply requires " + ", ".join(missing))
        return self


class DirectCoreEditRequest(BaseModel):
    """Direct-edit request that still routes through governed proposal/apply."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    domain: Domain
    domain_path: str | None = None
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("domain_path", "reason")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _require_base_refs(self) -> "DirectCoreEditRequest":
        if not self.base_refs:
            raise ValueError("direct_core_edit_base_refs_required")
        return self


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _normalize_unique_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_values.append(normalized)
    return normalized_values
