"""Branch-aware user-visible memory inspection and governed edit facade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Sequence
from uuid import uuid4

from rp.models.archival_evolution import (
    ArchivalEvolutionReceipt,
    ArchivalEvolutionRequest,
)
from rp.models.block_view import RpBlockView
from rp.models.core_mutation import DirectCoreEditRequest
from rp.models.dsl import Layer
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import ProposalReceipt
from rp.models.memory_inspection import (
    MemoryInspectionActionReceipt,
    RecallReviewAction,
    RecallReviewCommand,
)
from rp.models.memory_materialization import ARCHIVAL_LAYER, RECALL_LAYER
from rp.models.retrieval_records import SourceAsset
from rp.models.runtime_read_contract import RuntimeBranchReadScope
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialLifecycle

from .archival_evolution_service import ArchivalEvolutionService
from .memory_inspection_read_service import MemoryInspectionReadService
from .recall_lifecycle_service import RecallLifecycleService
from .retrieval_document_service import RetrievalDocumentService
from .rp_block_read_service import RpBlockReadService
from .runtime_read_manifest_service import BranchVisibilityResolver
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .story_block_mutation_service import StoryBlockMutationService


class MemoryInspectionError(ValueError):
    """Stable inspection/edit error with a machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}:{detail}")


class MemoryInspectionService:
    """One backend facade for visible memory inspection and governed actions."""

    _DEFAULT_LAYERS = [
        Layer.CORE_STATE_AUTHORITATIVE.value,
        Layer.CORE_STATE_PROJECTION.value,
        Layer.RUNTIME_WORKSPACE.value,
        Layer.RECALL.value,
        Layer.ARCHIVAL.value,
    ]

    def __init__(
        self,
        *,
        memory_inspection_read_service: MemoryInspectionReadService,
        rp_block_read_service: RpBlockReadService,
        story_block_mutation_service: StoryBlockMutationService | None = None,
        branch_visibility_resolver: BranchVisibilityResolver,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService,
        retrieval_document_service: RetrievalDocumentService,
        recall_lifecycle_service: RecallLifecycleService | None = None,
        archival_evolution_service: ArchivalEvolutionService | None = None,
    ) -> None:
        self._memory_inspection_read_service = memory_inspection_read_service
        self._rp_block_read_service = rp_block_read_service
        self._story_block_mutation_service = story_block_mutation_service
        self._branch_visibility_resolver = branch_visibility_resolver
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._retrieval_document_service = retrieval_document_service
        self._recall_lifecycle_service = recall_lifecycle_service
        self._archival_evolution_service = archival_evolution_service

    def inspect_visible_memory(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        layers: list[str] | None = None,
        domains: list[str] | None = None,
        include_hidden_audit: bool = False,
    ) -> dict[str, Any]:
        """Return one branch-aware user-visible memory inspection payload."""

        scope = self._branch_visibility_resolver.build_runtime_scope(identity=identity)
        layer_filter = self._normalize_layers(layers)
        domain_filter = self._normalize_filter(domains)
        layer_payloads: dict[str, dict[str, Any]] = {}

        if Layer.CORE_STATE_AUTHORITATIVE.value in layer_filter:
            items = [
                item
                for item in self._memory_inspection_read_service.list_authoritative_objects(
                    session_id=identity.session_id
                )
                if self._matches_domain(
                    _dict_path(item, "object_ref", "domain"),
                    domain_filter=domain_filter,
                )
            ]
            layer_payloads[Layer.CORE_STATE_AUTHORITATIVE.value] = self._layer_payload(
                items=items,
            )

        if Layer.CORE_STATE_PROJECTION.value in layer_filter:
            items = self._memory_inspection_read_service.list_projection_slots(
                session_id=identity.session_id
            )
            if domain_filter is not None:
                items = []
            layer_payloads[Layer.CORE_STATE_PROJECTION.value] = self._layer_payload(
                items=items,
            )

        if Layer.RUNTIME_WORKSPACE.value in layer_filter:
            items, hidden_items = self._runtime_workspace_items(
                identity=identity,
                domain_filter=domain_filter,
            )
            layer_payloads[Layer.RUNTIME_WORKSPACE.value] = self._layer_payload(
                items=items,
                hidden_items=hidden_items if include_hidden_audit else None,
            )

        retrieval_items = self._retrieval_layer_items(
            identity=identity,
            scope=scope,
            layer_filter=layer_filter,
            domain_filter=domain_filter,
        )
        for layer in (Layer.RECALL.value, Layer.ARCHIVAL.value):
            if layer not in layer_filter:
                continue
            items, hidden_items = retrieval_items[layer]
            layer_payloads[layer] = self._layer_payload(
                items=items,
                hidden_items=hidden_items if include_hidden_audit else None,
            )

        return {
            "identity": identity.model_dump(mode="json"),
            "branch_scope": scope.model_dump(mode="json"),
            "layers": layer_payloads,
            "include_hidden_audit": include_hidden_audit,
            "boundaries": [
                "core_direct_edit_routes_through_shared_mutation_kernel",
                "recall_review_routes_through_lifecycle_service",
                "archival_evolution_routes_through_evolution_service",
                "normal_inspection_filters_hidden_and_unrelated_branch_material",
            ],
        }

    async def direct_core_edit(
        self,
        *,
        request: DirectCoreEditRequest,
    ) -> ProposalReceipt:
        """Route a product-facing Core edit through the shared mutation kernel."""

        if self._story_block_mutation_service is None:
            raise MemoryInspectionError(
                "memory_core_direct_edit_not_configured",
                "story_block_mutation_service",
            )
        block = self._resolve_authoritative_block(request)
        receipt = await self._story_block_mutation_service.direct_edit_block(
            session_id=request.identity.session_id,
            block_id=block.block_id,
            payload=request,
        )
        if receipt is None:
            raise MemoryInspectionError(
                "memory_core_direct_edit_block_not_found",
                request.domain_path or request.domain.value,
            )
        return receipt

    def review_recall(
        self,
        *,
        command: RecallReviewCommand,
    ) -> MemoryInspectionActionReceipt:
        """Route Recall user review to the Recall lifecycle service."""

        if self._recall_lifecycle_service is None:
            raise MemoryInspectionError(
                "memory_recall_review_not_configured",
                "recall_lifecycle_service",
            )
        self._require_visible_material_refs(
            identity=command.identity,
            layer=Layer.RECALL.value,
            material_refs=command.material_refs,
        )
        reason = command.reason or f"user_visible_recall_review:{command.action.value}"
        event_id = command.event_id
        if command.action == RecallReviewAction.INVALIDATE:
            event_id = event_id or f"recall_review_event_{uuid4().hex}"
            touched = self._recall_lifecycle_service.invalidate_material(
                material_refs=command.material_refs,
                event_id=event_id,
                reason=reason,
            )
        elif command.action == RecallReviewAction.SUPERSEDE:
            touched = self._recall_lifecycle_service.supersede_material(
                material_refs=command.material_refs,
                replacement_metadata=self._recall_review_metadata(command),
            )
        elif command.action == RecallReviewAction.RECOMPUTE:
            touched = self._recall_lifecycle_service.recompute_material(
                material_refs=command.material_refs,
                replacement_metadata=self._recall_review_metadata(command),
            )
        else:  # pragma: no cover - guarded by pydantic enum validation.
            raise MemoryInspectionError(
                "memory_recall_review_action_unsupported",
                command.action.value,
            )
        return MemoryInspectionActionReceipt(
            action=command.action,
            identity=command.identity,
            actor=command.actor,
            material_refs=list(command.material_refs),
            touched_material_refs=touched,
            event_id=event_id,
            routed_through="RecallLifecycleService",
            reason=reason,
        )

    def evolve_archival(
        self,
        *,
        request: ArchivalEvolutionRequest,
    ) -> ArchivalEvolutionReceipt:
        """Route Archival corrections through governed evolution/reindex."""

        if self._archival_evolution_service is None:
            raise MemoryInspectionError(
                "memory_archival_evolution_not_configured",
                "archival_evolution_service",
            )
        self._require_visible_material_refs(
            identity=request.identity,
            layer=Layer.ARCHIVAL.value,
            material_refs=[request.source_asset_id],
        )
        return self._archival_evolution_service.evolve_source(request)

    def _resolve_authoritative_block(
        self,
        request: DirectCoreEditRequest,
    ) -> RpBlockView:
        requested_domain_path = request.domain_path
        candidates = self._rp_block_read_service.list_blocks(
            session_id=request.identity.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
        )
        for block in candidates:
            if block.domain != request.domain:
                continue
            if requested_domain_path is not None and (
                block.domain_path != requested_domain_path
            ):
                continue
            return block
        raise MemoryInspectionError(
            "memory_core_direct_edit_block_not_found",
            requested_domain_path or request.domain.value,
        )

    def _runtime_workspace_items(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain_filter: set[str] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        visible: list[dict[str, Any]] = []
        hidden: list[dict[str, Any]] = []
        for material in self._runtime_workspace_material_service.list_materials(
            identity=identity
        ):
            item = material.model_dump(mode="json")
            if not self._matches_domain(material.domain, domain_filter=domain_filter):
                continue
            if material.lifecycle in {
                RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
                RuntimeWorkspaceMaterialLifecycle.EXPIRED,
                RuntimeWorkspaceMaterialLifecycle.DISCARDED,
            }:
                hidden.append({**item, "hidden_reason": material.lifecycle.value})
                continue
            visible.append(item)
        return visible, hidden

    def _retrieval_layer_items(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        scope: RuntimeBranchReadScope,
        layer_filter: set[str],
        domain_filter: set[str] | None,
    ) -> dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
        result: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {
            Layer.RECALL.value: ([], []),
            Layer.ARCHIVAL.value: ([], []),
        }
        for asset in self._retrieval_document_service.list_story_assets(
            identity.story_id
        ):
            layer = self._asset_layer(asset)
            if layer is None or layer not in layer_filter:
                continue
            if not self._matches_domain(
                self._asset_domain(asset),
                domain_filter=domain_filter,
            ):
                continue
            item = self._asset_item(asset=asset, layer=layer)
            visible = self._asset_visible(asset=asset, scope=scope)
            target_items = result[layer][0 if visible else 1]
            if not visible:
                item["hidden_reason"] = "branch_or_lifecycle_hidden"
            target_items.append(item)
        return result

    def _require_visible_material_refs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        layer: str,
        material_refs: Sequence[str],
    ) -> None:
        scope = self._branch_visibility_resolver.build_runtime_scope(identity=identity)
        for material_ref in material_refs:
            asset = self._retrieval_document_service.get_source_asset(material_ref)
            if asset is None:
                raise MemoryInspectionError(
                    "memory_inspection_material_not_found",
                    material_ref,
                )
            if asset.story_id != identity.story_id:
                raise MemoryInspectionError(
                    "memory_inspection_material_story_mismatch",
                    f"{material_ref}:{asset.story_id}:{identity.story_id}",
                )
            asset_layer = self._asset_layer(asset)
            if asset_layer != layer:
                raise MemoryInspectionError(
                    "memory_inspection_material_layer_mismatch",
                    f"{material_ref}:{asset_layer or 'unknown'}:{layer}",
                )
            if not self._asset_visible(asset=asset, scope=scope):
                raise MemoryInspectionError(
                    "memory_inspection_material_not_visible",
                    material_ref,
                )

    @staticmethod
    def _recall_review_metadata(command: RecallReviewCommand) -> dict[str, Any]:
        return {
            "runtime_identity": command.identity.model_dump(mode="json"),
            "identity": command.identity.model_dump(mode="json"),
            "materialization_kind": "user_visible_recall_review",
            "review_action": command.action.value,
            "reviewed_by": command.actor,
            "reason": command.reason,
        }

    @classmethod
    def _normalize_layers(cls, layers: list[str] | None) -> set[str]:
        if not layers:
            return set(cls._DEFAULT_LAYERS)
        return {str(layer).strip() for layer in layers if str(layer).strip()}

    @staticmethod
    def _normalize_filter(values: Iterable[str] | None) -> set[str] | None:
        if values is None:
            return None
        normalized = {str(value).strip() for value in values if str(value).strip()}
        return normalized or None

    @staticmethod
    def _matches_domain(value: object, *, domain_filter: set[str] | None) -> bool:
        if domain_filter is None:
            return True
        return str(value or "").strip() in domain_filter

    @staticmethod
    def _layer_payload(
        *,
        items: list[dict[str, Any]],
        hidden_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"count": len(items), "items": items}
        if hidden_items is not None:
            payload["hidden_audit_count"] = len(hidden_items)
            payload["hidden_audit_items"] = hidden_items
        return payload

    @staticmethod
    def _asset_layer(asset: SourceAsset) -> str | None:
        metadata = dict(asset.metadata or {})
        layer = str(metadata.get("layer") or "").strip()
        if layer in {RECALL_LAYER, Layer.RECALL.value}:
            return Layer.RECALL.value
        if layer in {ARCHIVAL_LAYER, Layer.ARCHIVAL.value}:
            return Layer.ARCHIVAL.value
        if metadata.get("materialized_to_recall") is True:
            return Layer.RECALL.value
        if metadata.get("materialized_to_archival") is True:
            return Layer.ARCHIVAL.value
        return None

    @staticmethod
    def _asset_domain(asset: SourceAsset) -> str | None:
        metadata = dict(asset.metadata or {})
        domain = str(metadata.get("domain") or "").strip()
        return domain or None

    def _asset_visible(
        self,
        *,
        asset: SourceAsset,
        scope: RuntimeBranchReadScope,
    ) -> bool:
        metadata = dict(asset.metadata or {})
        selected_branch_ids = _string_list(
            metadata.get("selected_branch_head_ids")
            or metadata.get("branch_ids")
            or metadata.get("selected_branch_ids")
        )
        return self._branch_visibility_resolver.is_visible(
            scope=scope,
            visibility_scope=str(
                metadata.get("visibility_scope")
                or self._default_visibility_scope(metadata)
            ),
            visibility_state=str(
                metadata.get("visibility_state")
                or metadata.get("lifecycle_state")
                or "active"
            ),
            owning_branch_head_id=_first_text(
                metadata,
                "owning_branch_head_id",
                "branch_head_id",
                "branch_id",
            ),
            origin_turn_id=_first_text(metadata, "origin_turn_id", "turn_id"),
            selected_branch_head_ids=selected_branch_ids,
            hidden_by_branch_head_id=_first_text(metadata, "hidden_by_branch_head_id"),
            hidden_after_turn_id=_first_text(metadata, "hidden_after_turn_id"),
        )

    @staticmethod
    def _default_visibility_scope(metadata: dict[str, Any]) -> str:
        if metadata.get("selected_branch_head_ids") or metadata.get("branch_ids"):
            return "selected_branches"
        if _first_text(
            metadata, "owning_branch_head_id", "branch_head_id", "branch_id"
        ):
            return "branch_scoped"
        return "story_global"

    @staticmethod
    def _asset_item(*, asset: SourceAsset, layer: str) -> dict[str, Any]:
        metadata = dict(asset.metadata or {})
        return {
            "asset_id": asset.asset_id,
            "layer": layer,
            "domain": metadata.get("domain"),
            "domain_path": metadata.get("domain_path"),
            "title": asset.title,
            "source_ref": asset.source_ref,
            "lifecycle_state": metadata.get("lifecycle_state"),
            "visibility_scope": metadata.get("visibility_scope"),
            "visibility_state": metadata.get("visibility_state"),
            "owning_branch_head_id": _first_text(
                metadata,
                "owning_branch_head_id",
                "branch_head_id",
                "branch_id",
            ),
            "origin_turn_id": _first_text(metadata, "origin_turn_id", "turn_id"),
            "source_version": metadata.get("source_version")
            or metadata.get("source_asset_version"),
            "metadata": deepcopy(metadata),
        }


def _dict_path(value: dict[str, Any], *keys: str) -> object | None:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _string_list(value: Any) -> list[str] | None:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else None
    if not isinstance(value, list):
        return None
    result = [str(item).strip() for item in value if str(item).strip()]
    return result or None
