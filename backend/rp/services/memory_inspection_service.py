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
    MemoryDisplayBlock,
    MemoryDisplayEntry,
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
        display_blocks: list[MemoryDisplayBlock] = []
        hidden_display_blocks: list[MemoryDisplayBlock] = []

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
            display_blocks.extend(
                self._core_state_display_blocks(
                    identity=identity,
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain_filter=domain_filter,
                )
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
            display_blocks.extend(
                self._core_state_display_blocks(
                    identity=identity,
                    layer=Layer.CORE_STATE_PROJECTION,
                    domain_filter=domain_filter,
                )
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
            display_blocks.extend(
                self._runtime_workspace_display_block(item) for item in items
            )
            if include_hidden_audit:
                hidden_display_blocks.extend(
                    self._runtime_workspace_display_block(item) for item in hidden_items
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
            display_blocks.extend(
                self._retrieval_display_block(item=item, layer=layer) for item in items
            )
            if include_hidden_audit:
                hidden_display_blocks.extend(
                    self._retrieval_display_block(item=item, layer=layer)
                    for item in hidden_items
                )

        payload = {
            "identity": identity.model_dump(mode="json"),
            "branch_scope": scope.model_dump(mode="json"),
            "canonical_envelope": {
                "schema_version": "rp.memory.display.v1",
                "producer": "MemoryInspectionService",
                "governance_bound": True,
                "shared_by": [
                    "inspection_ui",
                    "governed_user_edit_ui",
                    "worker_proposal_trace",
                    "debug_eval_tools",
                ],
            },
            "blocks": [block.model_dump(mode="json") for block in display_blocks],
            "block_count": len(display_blocks),
            "layers": layer_payloads,
            "include_hidden_audit": include_hidden_audit,
            "boundaries": [
                "core_direct_edit_routes_through_shared_mutation_kernel",
                "recall_review_routes_through_lifecycle_service",
                "archival_evolution_routes_through_evolution_service",
                "normal_inspection_filters_hidden_and_unrelated_branch_material",
            ],
        }
        if include_hidden_audit:
            payload["hidden_audit_blocks"] = [
                block.model_dump(mode="json") for block in hidden_display_blocks
            ]
            payload["hidden_audit_block_count"] = len(hidden_display_blocks)
        return payload

    def _core_state_display_blocks(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        layer: Layer,
        domain_filter: set[str] | None,
    ) -> list[MemoryDisplayBlock]:
        blocks: list[MemoryDisplayBlock] = []
        for block in self._rp_block_read_service.list_blocks(
            session_id=identity.session_id,
            layer=layer,
        ):
            if not self._matches_domain(
                block.domain.value, domain_filter=domain_filter
            ):
                continue
            blocks.append(
                self._block_view_display_block(
                    block=block,
                    identity=identity,
                )
            )
        return blocks

    def _block_view_display_block(
        self,
        *,
        block: RpBlockView,
        identity: MemoryRuntimeIdentity,
    ) -> MemoryDisplayBlock:
        value = (
            deepcopy(block.data_json)
            if block.data_json is not None
            else deepcopy(block.items_json or [])
        )
        source_refs = [
            self._display_source_ref(
                source_type="core_state_block",
                source_id=block.block_id,
                layer=block.layer.value,
                domain=block.domain.value,
                block_id=block.block_id,
                entry_id=f"{block.block_id}:current",
                revision=block.revision,
                metadata={
                    "source": block.source,
                    "label": block.label,
                    "domain_path": block.domain_path,
                },
            )
        ]
        editable_fields = (
            self._editable_value_fields(value)
            if block.layer == Layer.CORE_STATE_AUTHORITATIVE
            else []
        )
        allowed_actions = self._allowed_actions(block.layer.value)
        entry = MemoryDisplayEntry(
            entry_id=f"{block.block_id}:current",
            entry_type=self._entry_type(block.layer.value),
            label=block.label,
            current_value=value,
            editable_fields=list(editable_fields),
            field_validation_rules=self._field_validation_rules(block.layer.value),
            base_revision=block.revision,
            source_refs=source_refs,
            user_edit_metadata=self._user_edit_metadata(block.layer.value),
            conflict_state="none",
            last_modified_actor=_first_text(block.metadata, "last_modified_actor"),
            last_modified_turn_or_event_id=_first_text(
                block.metadata,
                "last_modified_turn_id",
                "last_modified_event_id",
                "latest_apply_id",
                "last_refresh_kind",
            ),
            allowed_actions=allowed_actions,
        )
        return MemoryDisplayBlock(
            block_id=block.block_id,
            domain=block.domain.value,
            layer=block.layer.value,
            scope=block.scope,
            visibility=self._identity_visibility(identity, scope=block.scope),
            revision=block.revision,
            permission_level=self._permission_level(block.layer.value),
            lifecycle_state=str(block.metadata.get("lifecycle_state") or "active"),
            source_refs=source_refs,
            provenance={
                "source": block.source,
                "label": block.label,
                "domain_path": block.domain_path,
                "payload_schema_ref": block.payload_schema_ref,
                "metadata": deepcopy(block.metadata),
            },
            validation_summary=self._validation_summary(),
            editable_fields=list(editable_fields),
            allowed_actions=allowed_actions,
            entrypoints=self._entrypoints(block.layer.value),
            entries=[entry],
        )

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

    def _runtime_workspace_display_block(
        self,
        item: dict[str, Any],
    ) -> MemoryDisplayBlock:
        material_id = str(item.get("material_id") or "")
        block_id = f"runtime_workspace:material:{material_id}"
        entry_id = material_id or f"{block_id}:payload"
        layer = Layer.RUNTIME_WORKSPACE.value
        domain = str(item.get("domain") or "")
        source_refs = [
            *self._coerce_source_refs(item.get("source_refs")),
            self._display_source_ref(
                source_type="runtime_workspace_material",
                source_id=material_id,
                layer=layer,
                domain=domain,
                block_id=block_id,
                entry_id=entry_id,
                metadata={
                    "material_kind": item.get("material_kind"),
                    "short_id": item.get("short_id"),
                },
            ),
        ]
        allowed_actions = self._allowed_actions(layer)
        entry = MemoryDisplayEntry(
            entry_id=entry_id,
            entry_type=str(item.get("material_kind") or "runtime_workspace_material"),
            label=str(item.get("short_id") or material_id),
            current_value=deepcopy(item.get("payload") or {}),
            editable_fields=[],
            field_validation_rules={
                "durable_edit": "not_allowed_from_runtime_workspace",
                "promotion": "requires_governed_proposal_or_apply_path",
            },
            source_refs=source_refs,
            user_edit_metadata={
                "durable_edit_path": "promotion_or_governed_apply_only",
                "raw_editor_path": False,
            },
            conflict_state=None,
            last_modified_actor=_first_text(item, "created_by"),
            last_modified_turn_or_event_id=_first_text(
                self._dict(item.get("identity")),
                "turn_id",
            ),
            allowed_actions=allowed_actions,
        )
        return MemoryDisplayBlock(
            block_id=block_id,
            domain=domain,
            layer=layer,
            scope=str(item.get("visibility") or "runtime_workspace"),
            visibility={
                "visibility": item.get("visibility"),
                "lifecycle": item.get("lifecycle"),
                "identity": deepcopy(item.get("identity") or {}),
                "hidden_reason": item.get("hidden_reason"),
            },
            revision=None,
            permission_level=self._permission_level(layer),
            lifecycle_state=str(item.get("lifecycle") or "active"),
            source_refs=source_refs,
            provenance={
                "material_id": material_id,
                "material_kind": item.get("material_kind"),
                "short_id": item.get("short_id"),
                "created_by": item.get("created_by"),
                "materialization_ref": item.get("materialization_ref"),
                "metadata": deepcopy(item.get("metadata") or {}),
            },
            validation_summary=self._validation_summary(),
            editable_fields=[],
            allowed_actions=allowed_actions,
            entrypoints=self._entrypoints(layer),
            entries=[entry],
        )

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

    def _retrieval_display_block(
        self,
        *,
        item: dict[str, Any],
        layer: str,
    ) -> MemoryDisplayBlock:
        asset_id = str(item.get("asset_id") or "")
        block_id = f"{layer}:asset:{asset_id}"
        entry_id = asset_id or f"{block_id}:asset"
        domain = str(item.get("domain") or "unknown")
        source_refs = self._retrieval_source_refs(
            item=item,
            layer=layer,
            block_id=block_id,
            entry_id=entry_id,
        )
        allowed_actions = self._allowed_actions(layer)
        editable_fields = (
            ["replacement_sections"] if layer == Layer.ARCHIVAL.value else []
        )
        entry = MemoryDisplayEntry(
            entry_id=entry_id,
            entry_type=(
                "archival_source_asset"
                if layer == Layer.ARCHIVAL.value
                else "recall_material_asset"
            ),
            label=str(item.get("title") or asset_id),
            current_value={
                "asset_id": asset_id,
                "title": item.get("title"),
                "source_ref": item.get("source_ref"),
                "source_version": item.get("source_version"),
                "lifecycle_state": item.get("lifecycle_state"),
                "visibility_scope": item.get("visibility_scope"),
            },
            editable_fields=editable_fields,
            field_validation_rules=self._field_validation_rules(layer),
            base_revision=self._optional_int(item.get("source_version")),
            source_refs=source_refs,
            user_edit_metadata=self._user_edit_metadata(layer),
            conflict_state="none" if layer == Layer.ARCHIVAL.value else None,
            last_modified_actor=_first_text(
                self._dict(item.get("metadata")),
                "last_modified_actor",
                "reviewed_by",
                "evolved_by",
            ),
            last_modified_turn_or_event_id=_first_text(
                self._dict(item.get("metadata")),
                "last_modified_turn_id",
                "last_modified_event_id",
                "origin_turn_id",
                "turn_id",
            )
            or _first_text(item, "origin_turn_id"),
            allowed_actions=allowed_actions,
        )
        return MemoryDisplayBlock(
            block_id=block_id,
            domain=domain,
            layer=layer,
            scope=str(item.get("visibility_scope") or "story_global"),
            visibility={
                "visibility_scope": item.get("visibility_scope"),
                "visibility_state": item.get("visibility_state"),
                "owning_branch_head_id": item.get("owning_branch_head_id"),
                "origin_turn_id": item.get("origin_turn_id"),
                "hidden_reason": item.get("hidden_reason"),
            },
            revision=self._optional_int(item.get("source_version")),
            permission_level=self._permission_level(layer),
            lifecycle_state=str(item.get("lifecycle_state") or "active"),
            source_refs=source_refs,
            provenance={
                "asset_id": asset_id,
                "source_ref": item.get("source_ref"),
                "source_version": item.get("source_version"),
                "metadata": deepcopy(item.get("metadata") or {}),
            },
            validation_summary=self._validation_summary(),
            editable_fields=editable_fields,
            allowed_actions=allowed_actions,
            entrypoints=self._entrypoints(layer),
            entries=[entry],
        )

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
    def _identity_visibility(
        identity: MemoryRuntimeIdentity,
        *,
        scope: str | None,
    ) -> dict[str, Any]:
        return {
            "story_id": identity.story_id,
            "session_id": identity.session_id,
            "branch_head_id": identity.branch_head_id,
            "turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
            "scope": scope,
            "visibility_scope": "active_runtime_identity",
        }

    @staticmethod
    def _allowed_actions(layer: str) -> list[str]:
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return ["inspect", "direct_core_edit"]
        if layer == Layer.CORE_STATE_PROJECTION.value:
            return ["inspect", "request_projection_refresh"]
        if layer == Layer.RECALL.value:
            return [
                "inspect",
                "review_recall:recompute",
                "review_recall:invalidate",
                "review_recall:supersede",
            ]
        if layer == Layer.ARCHIVAL.value:
            return ["inspect", "evolve_archival"]
        if layer == Layer.RUNTIME_WORKSPACE.value:
            return ["inspect"]
        return ["inspect"]

    @staticmethod
    def _entrypoints(layer: str) -> dict[str, Any]:
        inspection = {
            "method": "GET",
            "path_template": ("/api/rp/story-sessions/{session_id}/memory/inspection"),
        }
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return {
                "inspection": inspection,
                "direct_core_edit": {
                    "method": "POST",
                    "path_template": (
                        "/api/rp/story-sessions/{session_id}/memory/core/direct-edit"
                    ),
                    "requires": [
                        "identity",
                        "actor",
                        "domain",
                        "operations",
                        "base_refs",
                    ],
                    "governed_by": "StoryBlockMutationService.direct_edit_block",
                },
            }
        if layer == Layer.RECALL.value:
            return {
                "inspection": inspection,
                "review_recall": {
                    "method": "POST",
                    "path_template": (
                        "/api/rp/story-sessions/{session_id}/memory/recall/actions"
                    ),
                    "allowed_actions": [action.value for action in RecallReviewAction],
                    "governed_by": "RecallLifecycleService",
                },
            }
        if layer == Layer.ARCHIVAL.value:
            return {
                "inspection": inspection,
                "evolve_archival": {
                    "method": "POST",
                    "path_template": (
                        "/api/rp/story-sessions/{session_id}/memory/archival/evolution"
                    ),
                    "requires": [
                        "identity",
                        "actor",
                        "source_asset_id",
                        "replacement_sections",
                    ],
                    "governed_by": "ArchivalEvolutionService.evolve_source",
                },
            }
        return {"inspection": inspection}

    @staticmethod
    def _permission_level(layer: str) -> dict[str, Any]:
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return {
                "read": True,
                "governed_write": True,
                "direct_edit": True,
                "raw_edit": False,
                "governance": "shared_core_mutation_kernel",
            }
        if layer == Layer.CORE_STATE_PROJECTION.value:
            return {
                "read": True,
                "refresh_projection": True,
                "governed_write": False,
                "raw_edit": False,
                "governance": "projection_refresh_or_authoritative_edit",
            }
        if layer == Layer.RECALL.value:
            return {
                "read": True,
                "review": True,
                "recompute": True,
                "invalidate": True,
                "supersede": True,
                "raw_edit": False,
                "governance": "recall_lifecycle_service",
            }
        if layer == Layer.ARCHIVAL.value:
            return {
                "read": True,
                "evolution": True,
                "reindex": True,
                "raw_source_overwrite": False,
                "governance": "archival_evolution_service",
            }
        if layer == Layer.RUNTIME_WORKSPACE.value:
            return {
                "read": True,
                "durable_edit": False,
                "raw_edit": False,
                "governance": "promotion_or_governed_apply_only",
            }
        return {"read": True, "raw_edit": False}

    @staticmethod
    def _field_validation_rules(layer: str) -> dict[str, Any]:
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return {
                "base_refs": "required",
                "operations": "StatePatchOperation[]",
                "conflict_check": "current_revision_must_match_base_revision",
            }
        if layer == Layer.CORE_STATE_PROJECTION.value:
            return {
                "direct_text_edit": "not_allowed",
                "refresh": "requires_projection_refresh_contract",
                "base_revision": "required_for_refresh_when_available",
            }
        if layer == Layer.RECALL.value:
            return {
                "raw_fact_write": "not_allowed",
                "review_action": [action.value for action in RecallReviewAction],
            }
        if layer == Layer.ARCHIVAL.value:
            return {
                "raw_source_overwrite": "not_allowed",
                "replacement_sections": "required_for_evolution",
                "expected_source_version": "recommended_for_conflict_check",
            }
        if layer == Layer.RUNTIME_WORKSPACE.value:
            return {
                "durable_edit": "not_allowed",
                "promotion": "requires_governed_path",
            }
        return {}

    @staticmethod
    def _user_edit_metadata(layer: str) -> dict[str, Any]:
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return {
                "editable": True,
                "edit_path": "direct_core_edit",
                "governed_backend": "StoryBlockMutationService.direct_edit_block",
                "requires_base_revision": True,
            }
        if layer == Layer.CORE_STATE_PROJECTION.value:
            return {
                "editable": False,
                "edit_path": "edit_authoritative_or_request_projection_refresh",
            }
        if layer == Layer.RECALL.value:
            return {
                "editable": False,
                "reviewable": True,
                "edit_path": "review_recall_action",
            }
        if layer == Layer.ARCHIVAL.value:
            return {
                "editable": True,
                "edit_path": "archival_evolution",
                "governed_backend": "ArchivalEvolutionService.evolve_source",
                "raw_source_overwrite": False,
            }
        if layer == Layer.RUNTIME_WORKSPACE.value:
            return {
                "editable": False,
                "edit_path": "promotion_or_governed_apply_only",
            }
        return {"editable": False}

    @staticmethod
    def _entry_type(layer: str) -> str:
        if layer == Layer.CORE_STATE_AUTHORITATIVE.value:
            return "core_state_object"
        if layer == Layer.CORE_STATE_PROJECTION.value:
            return "core_state_projection_slot"
        return "memory_entry"

    @staticmethod
    def _validation_summary(
        *,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        error_items = list(errors or [])
        warning_items = list(warnings or [])
        return {
            "state": "invalid" if error_items else "valid",
            "error_count": len(error_items),
            "warning_count": len(warning_items),
            "errors": error_items,
            "warnings": warning_items,
        }

    @staticmethod
    def _editable_value_fields(value: Any) -> list[str]:
        if isinstance(value, dict):
            return sorted(str(key) for key in value)
        return ["current_value"]

    @classmethod
    def _retrieval_source_refs(
        cls,
        *,
        item: dict[str, Any],
        layer: str,
        block_id: str,
        entry_id: str,
    ) -> list[dict[str, Any]]:
        asset_id = str(item.get("asset_id") or "")
        domain = str(item.get("domain") or "")
        metadata = cls._dict(item.get("metadata"))
        refs = [
            *cls._coerce_source_refs(metadata.get("source_refs")),
            cls._display_source_ref(
                source_type="retrieval_asset",
                source_id=asset_id,
                layer=layer,
                domain=domain,
                block_id=block_id,
                entry_id=entry_id,
                revision=cls._optional_int(item.get("source_version")),
                metadata={
                    "source_ref": item.get("source_ref"),
                    "title": item.get("title"),
                },
            ),
        ]
        source_ref = item.get("source_ref")
        if isinstance(source_ref, str) and source_ref.strip():
            refs.append(
                cls._display_source_ref(
                    source_type="source_ref",
                    source_id=source_ref.strip(),
                    layer=layer,
                    domain=domain,
                    block_id=block_id,
                    entry_id=entry_id,
                )
            )
        return cls._dedupe_source_ref_dicts(refs)

    @staticmethod
    def _display_source_ref(
        *,
        source_type: str,
        source_id: str,
        layer: str | None = None,
        domain: str | None = None,
        block_id: str | None = None,
        entry_id: str | None = None,
        revision: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "source_type": source_type,
            "source_id": source_id,
            "layer": layer,
            "domain": domain,
            "block_id": block_id,
            "entry_id": entry_id,
            "revision": revision,
            "metadata": deepcopy(metadata or {}),
        }

    @classmethod
    def _coerce_source_refs(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        refs: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                refs.append(deepcopy(item))
            elif isinstance(item, str) and item.strip():
                refs.append(
                    cls._display_source_ref(
                        source_type="source_ref",
                        source_id=item.strip(),
                    )
                )
        return cls._dedupe_source_ref_dicts(refs)

    @staticmethod
    def _dedupe_source_ref_dicts(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str | None, str | None]] = set()
        for ref in refs:
            source_type = str(ref.get("source_type") or "")
            source_id = str(ref.get("source_id") or "")
            if not source_type or not source_id:
                continue
            key = (
                source_type,
                source_id,
                ref.get("block_id"),
                ref.get("entry_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(ref)
        return result

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

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
