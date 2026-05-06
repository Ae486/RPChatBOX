"""Contracts for RP memory registry, runtime identity, and change events."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


class MemoryLifecycleState(StrEnum):
    """Lifecycle state for registry entries that must remain readable over time."""

    ACTIVE = "active"
    HIDDEN = "hidden"
    RETIRED = "retired"
    MIGRATED = "migrated"


class MemoryPermissionDefaults(BaseModel):
    """Default permission hints attached to domains and block templates.

    The registry owns these defaults so callers do not scatter mode/domain
    allowlists while the full RuntimeProfileSnapshot permission system is still
    being built.
    """

    model_config = ConfigDict(extra="forbid")

    read: bool = True
    propose: bool = True
    refresh_projection: bool = True
    governed_write: bool = False
    auto_apply: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryModeDefault(BaseModel):
    """Mode-specific activation and UI visibility default for one domain."""

    model_config = ConfigDict(extra="forbid")

    active: bool = False
    ui_visible: bool = False
    permission_overrides: dict[str, Any] = Field(default_factory=dict)


class MemoryWorkerModeDefault(BaseModel):
    """Mode-specific activation and permission defaults for one runtime worker."""

    model_config = ConfigDict(extra="forbid")

    active: bool = False
    profile_ref: str | None = None
    permission_defaults: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_ref")
    @classmethod
    def _normalize_profile_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="profile_ref")


class MemoryBlockTemplate(BaseModel):
    """Declarative template for a layer-specific memory container."""

    model_config = ConfigDict(extra="forbid")

    block_template_id: str
    domain_id: str
    layer: str
    label: str
    description: str | None = None
    domain_path_pattern: str | None = None
    lifecycle: MemoryLifecycleState = MemoryLifecycleState.ACTIVE
    aliases: list[str] = Field(default_factory=list)
    migrated_to: str | None = None
    ui_visible: bool = True
    permission_defaults: MemoryPermissionDefaults = Field(
        default_factory=MemoryPermissionDefaults
    )
    allowed_operations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("block_template_id", "domain_id", "layer", "label")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("description", "domain_path_pattern", "migrated_to")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("allowed_operations")
    @classmethod
    def _normalize_allowed_operations(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="allowed_operations")

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="aliases")

    @model_validator(mode="after")
    def _validate_block_template(self) -> "MemoryBlockTemplate":
        if self.lifecycle == MemoryLifecycleState.MIGRATED and self.migrated_to is None:
            raise ValueError("migrated block templates must declare migrated_to")
        return self


class MemoryWorkerDescriptor(BaseModel):
    """Declarative runtime worker descriptor compiled into profile snapshots."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    label: str
    description: str | None = None
    lifecycle: MemoryLifecycleState = MemoryLifecycleState.ACTIVE
    aliases: list[str] = Field(default_factory=list)
    migrated_to: str | None = None
    mode_defaults: dict[str, MemoryWorkerModeDefault] = Field(default_factory=dict)
    permission_defaults: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("worker_id", "label")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("description", "migrated_to")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="aliases")

    @field_validator("mode_defaults")
    @classmethod
    def _normalize_mode_keys(
        cls,
        value: dict[str, MemoryWorkerModeDefault],
    ) -> dict[str, MemoryWorkerModeDefault]:
        normalized: dict[str, MemoryWorkerModeDefault] = {}
        for mode, defaults in value.items():
            key = _normalize_key(mode)
            if key in normalized:
                raise ValueError(f"duplicate mode_defaults key: {key}")
            normalized[key] = defaults
        return normalized

    @model_validator(mode="after")
    def _validate_worker_descriptor(self) -> "MemoryWorkerDescriptor":
        if self.lifecycle == MemoryLifecycleState.MIGRATED and self.migrated_to is None:
            raise ValueError("migrated workers must declare migrated_to")
        return self


class MemoryDomainContract(BaseModel):
    """Domain-level registry entry for Memory OS vocabulary and defaults."""

    model_config = ConfigDict(extra="forbid")

    domain_id: str
    label: str
    description: str | None = None
    lifecycle: MemoryLifecycleState = MemoryLifecycleState.ACTIVE
    aliases: list[str] = Field(default_factory=list)
    migrated_to: str | None = None
    allowed_layers: list[str] = Field(default_factory=list)
    ui_visible: bool = True
    mode_defaults: dict[str, MemoryModeDefault] = Field(default_factory=dict)
    permission_defaults: MemoryPermissionDefaults = Field(
        default_factory=MemoryPermissionDefaults
    )
    block_templates: list[MemoryBlockTemplate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domain_id", "label")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("description", "migrated_to")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("aliases", "allowed_layers")
    @classmethod
    def _normalize_text_list(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _normalize_unique_text_list(
            values, field_name=info.field_name or "values"
        )

    @field_validator("mode_defaults")
    @classmethod
    def _normalize_mode_keys(
        cls,
        value: dict[str, MemoryModeDefault],
    ) -> dict[str, MemoryModeDefault]:
        normalized: dict[str, MemoryModeDefault] = {}
        for mode, defaults in value.items():
            key = _normalize_key(mode)
            if key in normalized:
                raise ValueError(f"duplicate mode_defaults key: {key}")
            normalized[key] = defaults
        return normalized

    @model_validator(mode="after")
    def _validate_domain_contract(self) -> "MemoryDomainContract":
        if self.lifecycle == MemoryLifecycleState.MIGRATED and self.migrated_to is None:
            raise ValueError("migrated domains must declare migrated_to")
        for template in self.block_templates:
            if _normalize_key(template.domain_id) != _normalize_key(self.domain_id):
                raise ValueError("block template domain_id must match parent domain_id")
        return self


class MemoryContractRegistry(BaseModel):
    """Versioned declarative registry for domain and block contracts."""

    model_config = ConfigDict(extra="forbid")

    version: str
    domains: list[MemoryDomainContract]
    workers: list[MemoryWorkerDescriptor] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _require_version(cls, value: str) -> str:
        return _require_non_blank(value, field_name="version")

    @model_validator(mode="after")
    def _validate_unique_domains_and_aliases(self) -> "MemoryContractRegistry":
        domain_ids: set[str] = set()
        aliases: dict[str, str] = {}
        for domain in self.domains:
            domain_key = _normalize_key(domain.domain_id)
            if domain_key in domain_ids:
                raise ValueError(f"duplicate domain_id: {domain.domain_id}")
            if domain_key in aliases:
                raise ValueError(f"domain_id conflicts with alias: {domain.domain_id}")
            domain_ids.add(domain_key)
            for alias in domain.aliases:
                alias_key = _normalize_key(alias)
                if alias_key in domain_ids:
                    raise ValueError(f"alias conflicts with domain_id: {alias}")
                previous = aliases.get(alias_key)
                if previous is not None:
                    raise ValueError(
                        f"duplicate alias: {alias} for {previous} and {domain.domain_id}"
                    )
                aliases[alias_key] = domain.domain_id
        block_template_ids: set[str] = set()
        block_template_aliases: dict[str, str] = {}
        for domain in self.domains:
            for template in domain.block_templates:
                template_key = _normalize_key(template.block_template_id)
                if template_key in block_template_ids:
                    raise ValueError(
                        f"duplicate block_template_id: {template.block_template_id}"
                    )
                if template_key in block_template_aliases:
                    raise ValueError(
                        "block_template_id conflicts with alias: "
                        f"{template.block_template_id}"
                    )
                block_template_ids.add(template_key)
                for alias in template.aliases:
                    alias_key = _normalize_key(alias)
                    if alias_key in block_template_ids:
                        raise ValueError(
                            f"block template alias conflicts with id: {alias}"
                        )
                    previous = block_template_aliases.get(alias_key)
                    if previous is not None:
                        raise ValueError(
                            f"duplicate block template alias: {alias} "
                            f"for {previous} and {template.block_template_id}"
                        )
                    block_template_aliases[alias_key] = template.block_template_id
        worker_ids: set[str] = set()
        worker_aliases: dict[str, str] = {}
        for worker in self.workers:
            worker_key = _normalize_key(worker.worker_id)
            if worker_key in worker_ids:
                raise ValueError(f"duplicate worker_id: {worker.worker_id}")
            if worker_key in worker_aliases:
                raise ValueError(f"worker_id conflicts with alias: {worker.worker_id}")
            worker_ids.add(worker_key)
            for alias in worker.aliases:
                alias_key = _normalize_key(alias)
                if alias_key in worker_ids:
                    raise ValueError(f"worker alias conflicts with worker_id: {alias}")
                previous = worker_aliases.get(alias_key)
                if previous is not None:
                    raise ValueError(
                        f"duplicate worker alias: {alias} "
                        f"for {previous} and {worker.worker_id}"
                    )
                worker_aliases[alias_key] = worker.worker_id
        return self


class MemoryRuntimeIdentity(BaseModel):
    """Pinned story-runtime identity required by future memory operations."""

    model_config = ConfigDict(extra="forbid")

    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str

    @field_validator(
        "story_id",
        "session_id",
        "branch_head_id",
        "turn_id",
        "runtime_profile_snapshot_id",
    )
    @classmethod
    def _require_identity_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "identity")


class MemorySourceRef(BaseModel):
    """Reference to evidence or runtime material that produced a memory event."""

    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    layer: str | None = None
    domain: str | None = None
    block_id: str | None = None
    entry_id: str | None = None
    revision: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", "source_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("layer", "domain", "block_id", "entry_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class MemoryDirtyTarget(BaseModel):
    """Downstream read/compile consumer that became stale after a change."""

    model_config = ConfigDict(extra="forbid")

    target_kind: str
    target_id: str
    layer: str | None = None
    domain: str | None = None
    block_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_kind", "target_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("layer", "domain", "block_id", "reason")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class MemoryChangeEvent(BaseModel):
    """Trace/invalidation event skeleton over memory stores.

    This model deliberately does not become an event-sourcing truth store. It
    carries enough identity, source, dirty-target, and visibility data for later
    rollback, audit, worker refresh, and packet/window recompute slices.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    identity: MemoryRuntimeIdentity
    actor: str
    event_kind: str
    layer: str
    domain: str
    block_id: str | None = None
    entry_id: str | None = None
    operation_kind: str
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    dirty_targets: list[MemoryDirtyTarget] = Field(default_factory=list)
    visibility_effect: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "event_id",
        "actor",
        "event_kind",
        "layer",
        "domain",
        "operation_kind",
        "visibility_effect",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("block_id", "entry_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


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
        key = _normalize_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values


def _normalize_key(value: str) -> str:
    return value.strip().lower()
