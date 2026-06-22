"""S3 runtime longform memory contract models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class RuntimeMemoryOperationKind(StrEnum):
    """First-slice fact operations allowed inside declared S3 longform blocks."""

    APPEND_ITEM = "append_item"
    UPDATE_ITEM = "update_item"
    REMOVE_ITEM = "remove_item"


RUNTIME_MEMORY_FACT_FIELD_ID = "facts"
RUNTIME_MEMORY_FACT_FIELD_SHAPE = "facts_list"
RUNTIME_MEMORY_FACT_ITEM_SHAPE = "fact_item"
RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS: tuple[str, ...] = tuple(
    operation.value for operation in RuntimeMemoryOperationKind
)


class RuntimeMemoryFieldContract(BaseModel):
    """Field-level contract for worker-maintained runtime memory blocks."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = RUNTIME_MEMORY_FACT_FIELD_ID
    value_shape: str = RUNTIME_MEMORY_FACT_FIELD_SHAPE
    item_shape: str = RUNTIME_MEMORY_FACT_ITEM_SHAPE
    group_by: str | None = None
    allowed_operations: tuple[str, ...] = RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("field_id", "value_shape", "item_shape")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("group_by")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="group_by")

    @field_validator("allowed_operations")
    @classmethod
    def _normalize_allowed_operations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized_values = _normalize_unique_text_tuple(
            values,
            field_name="allowed_operations",
        )
        unsupported = [
            value
            for value in normalized_values
            if value not in RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS
        ]
        if unsupported:
            raise ValueError(f"unsupported field operations: {unsupported}")
        return normalized_values

    @model_validator(mode="after")
    def _validate_first_slice_fact_shape(self) -> "RuntimeMemoryFieldContract":
        if self.field_id != RUNTIME_MEMORY_FACT_FIELD_ID:
            raise ValueError("S3a runtime memory fields must use facts")
        if self.value_shape != RUNTIME_MEMORY_FACT_FIELD_SHAPE:
            raise ValueError("S3a runtime memory fields must use facts_list shape")
        if self.item_shape != RUNTIME_MEMORY_FACT_ITEM_SHAPE:
            raise ValueError("S3a runtime memory fields must use fact_item shape")
        return self


class RuntimeMemoryBlockContract(BaseModel):
    """Predeclared block slot under an S3 longform runtime memory domain."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    domain_id: str
    label: str
    description: str | None = None
    primary_field_id: str = RUNTIME_MEMORY_FACT_FIELD_ID
    fields: tuple[RuntimeMemoryFieldContract, ...] = Field(
        default_factory=lambda: (RuntimeMemoryFieldContract(),)
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("block_id", "domain_id", "label", "primary_field_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("description")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="description")

    @model_validator(mode="after")
    def _validate_fields(self) -> "RuntimeMemoryBlockContract":
        field_ids = [field.field_id for field in self.fields]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError(f"duplicate field_id in block {self.block_id}")
        if self.primary_field_id not in field_ids:
            raise ValueError(
                f"primary_field_id {self.primary_field_id} is not declared"
            )
        if self.primary_field_id != RUNTIME_MEMORY_FACT_FIELD_ID:
            raise ValueError("S3a runtime memory blocks must use facts as primary")
        return self

    def facts_field(self) -> RuntimeMemoryFieldContract:
        """Return the first-slice facts field contract for this block."""

        for field in self.fields:
            if field.field_id == RUNTIME_MEMORY_FACT_FIELD_ID:
                return field
        raise ValueError(f"block {self.block_id} does not declare facts")


class RuntimeMemoryDomainContract(BaseModel):
    """S3 longform memory domain contract with fixed block topology."""

    model_config = ConfigDict(extra="forbid")

    domain_id: str
    label: str
    description: str | None = None
    blocks: tuple[RuntimeMemoryBlockContract, ...]
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("domain_id", "label")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("description")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="description")

    @model_validator(mode="after")
    def _validate_blocks(self) -> "RuntimeMemoryDomainContract":
        block_ids: set[str] = set()
        for block in self.blocks:
            if _normalize_key(block.domain_id) != _normalize_key(self.domain_id):
                raise ValueError("block domain_id must match parent domain_id")
            block_key = _normalize_key(block.block_id)
            if block_key in block_ids:
                raise ValueError(f"duplicate block_id in domain {self.domain_id}")
            block_ids.add(block_key)
        return self


class RuntimeMemoryContractRegistry(BaseModel):
    """Versioned runtime longform registry used by S3 memory workers."""

    model_config = ConfigDict(extra="forbid")

    version: str
    mode: str
    domains: tuple[RuntimeMemoryDomainContract, ...]

    @field_validator("version", "mode")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _validate_domains(self) -> "RuntimeMemoryContractRegistry":
        domain_ids: set[str] = set()
        for domain in self.domains:
            domain_key = _normalize_key(domain.domain_id)
            if domain_key in domain_ids:
                raise ValueError(f"duplicate domain_id: {domain.domain_id}")
            domain_ids.add(domain_key)
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


def _normalize_unique_text_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        key = _normalize_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return tuple(normalized_values)


def _normalize_key(value: str) -> str:
    return value.strip().lower()
