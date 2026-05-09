"""Story-level facade for governed Memory OS evolution actions."""

from __future__ import annotations

from typing import Any

from rp.models.archival_evolution import (
    ArchivalEvolutionReceipt,
    ArchivalEvolutionRequest,
)
from rp.models.story_evolution_contracts import (
    StoryEvolutionOperation,
    StoryEvolutionReceipt,
    StoryEvolutionRequest,
    StoryEvolutionStatus,
    StoryEvolutionTargetLayer,
)
from rp.services.archival_evolution_service import ArchivalEvolutionService


class StoryEvolutionServiceError(ValueError):
    """Stable Story Evolution error with a machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}:{detail}")


class StoryEvolutionService:
    """Route Story Evolution through existing governed layer services.

    This service is intentionally thin in M1. It gives runtime code one
    story-level command surface while preserving Archival evolution, Core
    mutation, Recall lifecycle, retrieval maintenance, and event-spine ownership.
    """

    def __init__(
        self,
        *,
        archival_evolution_service: ArchivalEvolutionService,
    ) -> None:
        self._archival_evolution_service = archival_evolution_service

    def apply_evolution(
        self,
        request: StoryEvolutionRequest,
    ) -> StoryEvolutionReceipt:
        if request.target_layer == StoryEvolutionTargetLayer.CORE:
            raise StoryEvolutionServiceError(
                "story_evolution_core_raw_write_forbidden",
                request.operation.value,
            )
        if request.target_layer == StoryEvolutionTargetLayer.RECALL:
            raise StoryEvolutionServiceError(
                "story_evolution_target_layer_unsupported",
                f"{request.target_layer.value}:{request.operation.value}",
            )
        if request.target_layer != StoryEvolutionTargetLayer.ARCHIVAL:
            raise StoryEvolutionServiceError(
                "story_evolution_target_layer_unsupported",
                request.target_layer.value,
            )
        if request.operation not in {
            StoryEvolutionOperation.EDIT,
            StoryEvolutionOperation.IMPORT,
        }:
            raise StoryEvolutionServiceError(
                "story_evolution_target_layer_unsupported",
                f"{request.target_layer.value}:{request.operation.value}",
            )

        archival_request = self._archival_request_from_story_request(request)
        archival_receipt = self._archival_evolution_service.evolve_source(
            archival_request
        )
        return self._receipt_from_archival(
            request=request,
            archival_receipt=archival_receipt,
        )

    def _archival_request_from_story_request(
        self,
        request: StoryEvolutionRequest,
    ) -> ArchivalEvolutionRequest:
        payload = dict(request.payload)
        source_asset_id = _required_text(payload, "source_asset_id")
        return ArchivalEvolutionRequest(
            identity=request.identity,
            actor=request.actor_id or "story_evolution",
            source_asset_id=source_asset_id,
            expected_source_version=_optional_int(
                payload.get("expected_source_version")
            ),
            visibility_scope=request.visibility_scope,
            selected_branch_head_ids=list(request.selected_branch_head_ids),
            replacement_sections=_required_list(payload, "replacement_sections"),
            source_refs=list(request.source_refs),
            reason=request.reason,
        )

    @staticmethod
    def _receipt_from_archival(
        *,
        request: StoryEvolutionRequest,
        archival_receipt: ArchivalEvolutionReceipt,
    ) -> StoryEvolutionReceipt:
        status = (
            StoryEvolutionStatus.PENDING_REINDEX
            if archival_receipt.warnings
            else StoryEvolutionStatus.ACCEPTED
        )
        return StoryEvolutionReceipt(
            evolution_id=archival_receipt.evolution_id,
            identity=request.identity,
            target_layer=StoryEvolutionTargetLayer.ARCHIVAL,
            operation=request.operation,
            visibility_scope=archival_receipt.visibility_scope,
            affected_refs=list(archival_receipt.source_refs),
            reindex_job_ids=list(archival_receipt.reindex_job_ids),
            event_ids=list(archival_receipt.event_ids),
            status=status,
            metadata_json={
                "archival_receipt": archival_receipt.model_dump(mode="json"),
                "source_asset_id": archival_receipt.source_asset_id,
                "superseded_source_asset_id": (
                    archival_receipt.superseded_source_asset_id
                ),
                "root_source_asset_id": archival_receipt.root_source_asset_id,
                "new_source_version": archival_receipt.new_source_version,
                "superseded_source_version": (
                    archival_receipt.superseded_source_version
                ),
                "replacement_chunk_ids": list(
                    archival_receipt.replacement_chunk_ids
                ),
                "warnings": list(archival_receipt.warnings),
            },
        )


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoryEvolutionServiceError(
            "story_evolution_payload_invalid",
            key,
        )
    return value.strip()


def _required_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise StoryEvolutionServiceError(
            "story_evolution_payload_invalid",
            key,
        )
    return list(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise StoryEvolutionServiceError(
            "story_evolution_payload_invalid",
            "expected_source_version",
        ) from exc
