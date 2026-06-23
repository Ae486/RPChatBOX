"""Deterministic validator for S3 memory maintenance candidates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rp.models.memory.maintenance_candidate import (
    FORBIDDEN_MEMORY_SCHEMA_OPERATION_KINDS,
    SUPPORTED_MEMORY_MAINTENANCE_OPERATION_KINDS,
    MemoryMaintenanceCandidate,
    MemoryMaintenanceCandidateBatch,
    MemoryMaintenanceOperation,
)
from rp.models.memory.runtime_memory_contract import RUNTIME_MEMORY_FACT_FIELD_ID
from rp.services.memory.runtime_memory_contract_registry import (
    RuntimeLongformMemoryContractRegistryService,
    RuntimeMemoryContractRegistryError,
)


class MemoryCandidateValidationErrorItem(BaseModel):
    """One deterministic fail-closed validation finding."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    candidate_index: int | None = None
    operation_index: int | None = None
    target_domain: str | None = None
    target_block_id: str | None = None
    operation_kind: str | None = None


class MemoryCandidateValidationResult(BaseModel):
    """Validation result; this service never mutates memory truth."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    errors: list[MemoryCandidateValidationErrorItem] = Field(default_factory=list)


class MemoryCandidateValidationService:
    """Validate worker candidate contracts against the S3 longform registry."""

    def __init__(
        self,
        registry_service: RuntimeLongformMemoryContractRegistryService | None = None,
    ) -> None:
        self._registry_service = (
            registry_service or RuntimeLongformMemoryContractRegistryService()
        )

    def validate_batch(
        self,
        batch: MemoryMaintenanceCandidateBatch | dict[str, Any],
    ) -> MemoryCandidateValidationResult:
        parsed_batch = self._parse_batch(batch)
        if isinstance(parsed_batch, MemoryCandidateValidationResult):
            return parsed_batch

        errors: list[MemoryCandidateValidationErrorItem] = []
        for candidate_index, candidate in enumerate(parsed_batch.candidates):
            errors.extend(self._validate_candidate(candidate_index, candidate))

        return MemoryCandidateValidationResult(
            accepted=not errors,
            errors=errors,
        )

    def _parse_batch(
        self,
        batch: MemoryMaintenanceCandidateBatch | dict[str, Any],
    ) -> MemoryMaintenanceCandidateBatch | MemoryCandidateValidationResult:
        if isinstance(batch, MemoryMaintenanceCandidateBatch):
            return batch
        try:
            return MemoryMaintenanceCandidateBatch.model_validate(batch)
        except ValidationError as exc:
            return MemoryCandidateValidationResult(
                accepted=False,
                errors=[
                    MemoryCandidateValidationErrorItem(
                        code="memory_candidate_invalid_schema",
                        message=str(exc),
                    )
                ],
            )

    def _validate_candidate(
        self,
        candidate_index: int,
        candidate: MemoryMaintenanceCandidate,
    ) -> list[MemoryCandidateValidationErrorItem]:
        errors: list[MemoryCandidateValidationErrorItem] = []
        if not candidate.base_block_revision_id:
            errors.append(
                self._candidate_error(
                    "memory_candidate_missing_base_block_revision",
                    "candidate must include base_block_revision_id",
                    candidate_index,
                    candidate,
                )
            )
        if not candidate.source_refs:
            errors.append(
                self._candidate_error(
                    "memory_candidate_missing_source_refs",
                    "candidate must include at least one source ref",
                    candidate_index,
                    candidate,
                )
            )

        try:
            self._registry_service.require_block(
                domain_id=candidate.target_domain,
                block_id=candidate.target_block_id,
            )
        except RuntimeMemoryContractRegistryError as exc:
            code = (
                "memory_candidate_unknown_target_domain"
                if exc.code == "runtime_memory_domain_not_registered"
                else "memory_candidate_unknown_target_block"
            )
            errors.append(
                self._candidate_error(
                    code,
                    str(exc),
                    candidate_index,
                    candidate,
                )
            )
            return errors

        seen_targets: dict[str, int] = {}
        for operation_index, operation in enumerate(candidate.operations):
            errors.extend(
                self._validate_operation(
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                    seen_targets,
                )
            )
        return errors

    def _validate_operation(
        self,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
        seen_targets: dict[str, int],
    ) -> list[MemoryCandidateValidationErrorItem]:
        errors = self._validate_operation_kind(
            candidate_index,
            operation_index,
            candidate,
            operation,
        )
        if errors:
            return errors

        errors = self._validate_operation_support(
            candidate_index,
            operation_index,
            candidate,
            operation,
        )
        if errors:
            return errors

        return self._validate_operation_payload(
            candidate_index,
            operation_index,
            candidate,
            operation,
            seen_targets,
        )

    def _validate_operation_kind(
        self,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
    ) -> list[MemoryCandidateValidationErrorItem]:
        if operation.kind in FORBIDDEN_MEMORY_SCHEMA_OPERATION_KINDS:
            return [
                self._operation_error(
                    "memory_candidate_forbidden_schema_operation",
                    "workers cannot create/delete domains, create/delete blocks, or change schema",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            ]
        if operation.kind not in SUPPORTED_MEMORY_MAINTENANCE_OPERATION_KINDS:
            return [
                self._operation_error(
                    "memory_candidate_unsupported_operation",
                    f"unsupported operation kind: {operation.kind}",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            ]
        return []

    def _validate_operation_support(
        self,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
    ) -> list[MemoryCandidateValidationErrorItem]:
        if operation.field_id != RUNTIME_MEMORY_FACT_FIELD_ID:
            return [
                self._operation_error(
                    "memory_candidate_unsupported_field",
                    "S3a candidates may only target facts",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            ]

        try:
            self._registry_service.require_operation_supported(
                domain_id=candidate.target_domain,
                block_id=candidate.target_block_id,
                field_id=operation.field_id,
                operation_kind=operation.kind,
            )
        except RuntimeMemoryContractRegistryError as exc:
            return [
                self._operation_error(
                    "memory_candidate_unsupported_operation",
                    str(exc),
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            ]
        return []

    def _validate_operation_payload(
        self,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
        seen_targets: dict[str, int],
    ) -> list[MemoryCandidateValidationErrorItem]:
        errors: list[MemoryCandidateValidationErrorItem] = []
        if operation.kind == "append_item" and operation.target_key() is not None:
            errors.append(
                self._operation_error(
                    "memory_candidate_append_targets_existing_fact",
                    "append_item must not target an existing fact",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            )
        if operation.kind in {"append_item", "update_item"} and not operation.content:
            errors.append(
                self._operation_error(
                    "memory_candidate_missing_fact_content",
                    f"{operation.kind} requires content",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            )
        if operation.kind in {"update_item", "remove_item"}:
            errors.extend(
                self._validate_targeted_operation_payload(
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                    seen_targets,
                )
            )
        return errors

    def _validate_targeted_operation_payload(
        self,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
        seen_targets: dict[str, int],
    ) -> list[MemoryCandidateValidationErrorItem]:
        target_key = operation.target_key()
        if target_key is None:
            return [
                self._operation_error(
                    "memory_candidate_missing_target_fact",
                    f"{operation.kind} requires target_fact_id or target_fact_handle",
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            ]

        errors: list[MemoryCandidateValidationErrorItem] = []
        previous_index = seen_targets.get(target_key)
        if previous_index is not None:
            errors.append(
                self._operation_error(
                    "memory_candidate_contradictory_operations",
                    (
                        "candidate contains multiple operations for the "
                        f"same fact target at operation {previous_index}"
                    ),
                    candidate_index,
                    operation_index,
                    candidate,
                    operation,
                )
            )
        seen_targets[target_key] = operation_index
        return errors

    @staticmethod
    def _candidate_error(
        code: str,
        message: str,
        candidate_index: int,
        candidate: MemoryMaintenanceCandidate,
    ) -> MemoryCandidateValidationErrorItem:
        return MemoryCandidateValidationErrorItem(
            code=code,
            message=message,
            candidate_index=candidate_index,
            target_domain=candidate.target_domain,
            target_block_id=candidate.target_block_id,
        )

    @staticmethod
    def _operation_error(
        code: str,
        message: str,
        candidate_index: int,
        operation_index: int,
        candidate: MemoryMaintenanceCandidate,
        operation: MemoryMaintenanceOperation,
    ) -> MemoryCandidateValidationErrorItem:
        return MemoryCandidateValidationErrorItem(
            code=code,
            message=message,
            candidate_index=candidate_index,
            operation_index=operation_index,
            target_domain=candidate.target_domain,
            target_block_id=candidate.target_block_id,
            operation_kind=operation.kind,
        )
