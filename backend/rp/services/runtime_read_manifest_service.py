"""Shared runtime branch visibility and deterministic read-manifest services."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from sqlalchemy import asc
from sqlmodel import Session, select

from models.rp_story_store import BranchHeadRecord, StoryTurnRecord
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.runtime_read_contract import RuntimeBranchReadScope, RuntimeReadManifest
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)

from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService


class RuntimeReadManifestServiceError(ValueError):
    """Stable runtime read-manifest error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class BranchVisibilityResolver:
    """Resolve runtime branch lineage and visibility for boot-bar reads."""

    def __init__(self, session: Session):
        self._session = session
        self._turn_order_by_branch: dict[tuple[str, str], dict[str, int]] = {}

    def build_runtime_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> RuntimeBranchReadScope:
        branch = self._session.get(BranchHeadRecord, identity.branch_head_id)
        if branch is None:
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                identity.branch_head_id,
            )
        if (
            branch.story_id != identity.story_id
            or branch.session_id != identity.session_id
        ):
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                identity.branch_head_id,
            )
        scope_turn = self._require_scope_turn(
            identity=identity,
            selected_turn_id=selected_turn_id,
        )
        scope_turn_id = scope_turn.turn_id
        visible_branch_head_ids: list[str] = []
        turn_cutoff_by_branch: dict[str, str | None] = {}
        hidden_turn_ids_by_branch: dict[str, list[str]] = {}
        current: BranchHeadRecord | None = branch
        current_cutoff_turn_id: str | None = scope_turn_id
        seen: set[str] = set()
        while current is not None and current.branch_head_id not in seen:
            seen.add(current.branch_head_id)
            visible_branch_head_ids.append(current.branch_head_id)
            turn_cutoff_by_branch[current.branch_head_id] = current_cutoff_turn_id
            self._turn_order_by_branch[(current.session_id, current.branch_head_id)] = (
                self._load_turn_order(
                    session_id=current.session_id,
                    branch_head_id=current.branch_head_id,
                )
            )
            hidden_turn_ids_by_branch[current.branch_head_id] = (
                self._hidden_turn_ids_for_branch(current)
            )
            parent_branch_id = str(current.parent_branch_head_id or "").strip()
            current_cutoff_turn_id = current.forked_from_turn_id
            current = (
                self._session.get(BranchHeadRecord, parent_branch_id)
                if parent_branch_id
                else None
            )
        return RuntimeBranchReadScope(
            story_id=identity.story_id,
            session_id=identity.session_id,
            active_branch_head_id=identity.branch_head_id,
            active_turn_id=scope_turn_id,
            selected_turn_id=scope_turn_id,
            visible_branch_head_ids=visible_branch_head_ids,
            turn_cutoff_by_branch=turn_cutoff_by_branch,
            hidden_turn_ids_by_branch=hidden_turn_ids_by_branch,
            include_story_global=True,
        )

    def build_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> RuntimeBranchReadScope:
        """Stage-V resolver alias shared by writer/debug/inspection callers."""

        return self.build_runtime_scope(
            identity=identity,
            selected_turn_id=selected_turn_id,
        )

    def is_visible(
        self,
        *,
        scope: RuntimeBranchReadScope,
        visibility_scope: str,
        visibility_state: str,
        owning_branch_head_id: str | None,
        origin_turn_id: str | None,
        selected_branch_head_ids: list[str] | None = None,
        hidden_by_branch_head_id: str | None = None,
        hidden_after_turn_id: str | None = None,
    ) -> bool:
        normalized_visibility_scope = (
            str(visibility_scope or "").strip() or "story_global"
        )
        normalized_visibility_state = str(visibility_state or "").strip() or "active"
        if normalized_visibility_state in {
            "hidden",
            "invalidated",
            "superseded",
            "hidden_by_rollback",
        }:
            return False
        if (
            hidden_by_branch_head_id
            and hidden_by_branch_head_id == scope.active_branch_head_id
        ):
            return False
        normalized_owner = str(owning_branch_head_id or "").strip() or None
        normalized_origin_turn = str(origin_turn_id or "").strip() or None
        if (
            normalized_owner is not None
            and normalized_origin_turn is not None
            and normalized_origin_turn
            in set(scope.hidden_turn_ids_by_branch.get(normalized_owner, []))
        ):
            return False
        if normalized_visibility_scope == "story_global":
            return True
        if normalized_visibility_scope in {
            "selected_branches",
            "all_existing_branches",
        }:
            requested = [
                str(item).strip()
                for item in (selected_branch_head_ids or [])
                if str(item).strip()
            ]
            if not requested:
                return False
            return scope.active_branch_head_id in requested
        if normalized_visibility_scope not in {"branch_scoped", "current_branch"}:
            return False
        if normalized_owner is None:
            return False
        if normalized_owner not in scope.visible_branch_head_ids:
            return False
        if (
            normalized_origin_turn is not None
            and self._is_turn_hidden_by_rollback(
                session_id=scope.session_id,
                branch_head_id=normalized_owner,
                turn_id=normalized_origin_turn,
            )
        ):
            return False
        cutoff_turn_id = scope.turn_cutoff_by_branch.get(normalized_owner)
        if cutoff_turn_id is None or normalized_origin_turn is None:
            return not self._is_hidden_after_cutoff(
                session_id=scope.session_id,
                branch_head_id=normalized_owner,
                cutoff_turn_id=None,
                hidden_after_turn_id=hidden_after_turn_id,
            )
        turn_order = self._turn_order_by_branch.get(
            (scope.session_id, normalized_owner), {}
        )
        origin_order = turn_order.get(normalized_origin_turn)
        cutoff_order = turn_order.get(cutoff_turn_id)
        if origin_order is None or cutoff_order is None:
            if normalized_origin_turn != cutoff_turn_id:
                return False
            return not self._is_hidden_after_cutoff(
                session_id=scope.session_id,
                branch_head_id=normalized_owner,
                cutoff_turn_id=cutoff_turn_id,
                hidden_after_turn_id=hidden_after_turn_id,
            )
        if origin_order > cutoff_order:
            return False
        return not self._is_hidden_after_cutoff(
            session_id=scope.session_id,
            branch_head_id=normalized_owner,
            cutoff_turn_id=cutoff_turn_id,
            hidden_after_turn_id=hidden_after_turn_id,
        )

    def filter_visible_memory_refs(
        self,
        *,
        scope: RuntimeBranchReadScope,
        refs: list[MemorySourceRef],
    ) -> list[MemorySourceRef]:
        """Apply the same branch-visibility rules to formal memory source refs."""

        visible_refs: list[MemorySourceRef] = []
        for ref in refs:
            metadata = dict(ref.metadata or {})
            if self.is_visible(
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
                    "runtime_branch_head_id",
                    "branch_head_id",
                    "branch_id",
                ),
                origin_turn_id=_first_text(
                    metadata,
                    "origin_turn_id",
                    "runtime_turn_id",
                    "turn_id",
                ),
                selected_branch_head_ids=_string_list(
                    metadata.get("selected_branch_head_ids")
                    or metadata.get("branch_ids")
                    or metadata.get("selected_branch_ids")
                ),
                hidden_by_branch_head_id=_first_text(
                    metadata,
                    "hidden_by_branch_head_id",
                ),
                hidden_after_turn_id=_first_text(metadata, "hidden_after_turn_id"),
            ):
                visible_refs.append(ref)
        return visible_refs

    def _require_turn(self, *, identity: MemoryRuntimeIdentity) -> StoryTurnRecord:
        turn = self._session.get(StoryTurnRecord, identity.turn_id)
        if turn is None:
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                identity.turn_id,
            )
        if (
            turn.story_id != identity.story_id
            or turn.session_id != identity.session_id
            or turn.branch_head_id != identity.branch_head_id
            or turn.runtime_profile_snapshot_id != identity.runtime_profile_snapshot_id
        ):
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                identity.turn_id,
            )
        return turn

    def _require_scope_turn(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None,
    ) -> StoryTurnRecord:
        normalized_selected_turn_id = str(selected_turn_id or "").strip()
        if (
            not normalized_selected_turn_id
            or normalized_selected_turn_id == identity.turn_id
        ):
            return self._require_turn(identity=identity)
        turn = self._session.get(StoryTurnRecord, normalized_selected_turn_id)
        if turn is None:
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                normalized_selected_turn_id,
            )
        if (
            turn.story_id != identity.story_id
            or turn.session_id != identity.session_id
            or turn.branch_head_id != identity.branch_head_id
        ):
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                normalized_selected_turn_id,
            )
        return turn

    def _load_turn_order(
        self,
        *,
        session_id: str,
        branch_head_id: str,
    ) -> dict[str, int]:
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == session_id)
            .where(StoryTurnRecord.branch_head_id == branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        records = list(self._session.exec(stmt).all())
        return {record.turn_id: index for index, record in enumerate(records)}

    @staticmethod
    def _active_branch_cutoff_turn_id(
        *,
        branch: BranchHeadRecord,
        identity_turn_id: str,
    ) -> str:
        rollback_cutoff_turn_id = str(
            (branch.metadata_json or {}).get("rollback_cutoff_turn_id") or ""
        ).strip()
        branch_head_turn_id = str(branch.head_turn_id or "").strip()
        if branch_head_turn_id and branch_head_turn_id != rollback_cutoff_turn_id:
            return branch_head_turn_id
        if branch_head_turn_id:
            return branch_head_turn_id
        return identity_turn_id

    @staticmethod
    def _hidden_turn_ids_for_branch(branch: BranchHeadRecord) -> list[str]:
        metadata = dict(branch.metadata_json or {})
        hidden_turn_ids = metadata.get("rollback_hidden_turn_ids")
        if not isinstance(hidden_turn_ids, list):
            return []
        return [str(item).strip() for item in hidden_turn_ids if str(item).strip()]

    def _is_turn_hidden_by_rollback(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        turn_id: str,
    ) -> bool:
        turn = self._session.get(StoryTurnRecord, turn_id)
        if turn is None:
            return False
        if turn.session_id != session_id or turn.branch_head_id != branch_head_id:
            return False
        return str(turn.visibility_state or "").strip() == "hidden_by_rollback"

    def _is_hidden_after_cutoff(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        cutoff_turn_id: str | None,
        hidden_after_turn_id: str | None,
    ) -> bool:
        normalized_hidden_after = str(hidden_after_turn_id or "").strip()
        if not normalized_hidden_after or not cutoff_turn_id:
            return False
        turn_order = self._turn_order_by_branch.get((session_id, branch_head_id), {})
        cutoff_order = turn_order.get(cutoff_turn_id)
        hidden_after_order = turn_order.get(normalized_hidden_after)
        if cutoff_order is None or hidden_after_order is None:
            return cutoff_turn_id == normalized_hidden_after
        return cutoff_order >= hidden_after_order

    @staticmethod
    def _default_visibility_scope(metadata: dict[str, Any]) -> str:
        if (
            metadata.get("selected_branch_head_ids")
            or metadata.get("branch_ids")
            or metadata.get("selected_branch_ids")
        ):
            return "selected_branches"
        if _first_text(
            metadata,
            "owning_branch_head_id",
            "runtime_branch_head_id",
            "branch_head_id",
            "branch_id",
        ):
            return "branch_scoped"
        return "story_global"


class RuntimeReadManifestService:
    """Build deterministic packet-visible runtime read manifests."""

    def __init__(
        self,
        *,
        session: Session,
        branch_visibility_resolver: BranchVisibilityResolver | None = None,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService
        | None = None,
    ) -> None:
        self._session = session
        self._branch_visibility_resolver = (
            branch_visibility_resolver or BranchVisibilityResolver(session)
        )
        self._runtime_workspace_material_service = (
            runtime_workspace_material_service
            or RuntimeWorkspaceMaterialService(session=session)
        )

    def build_branch_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> RuntimeBranchReadScope:
        """Expose the shared branch scope for packet builders and diagnostics."""

        return self._branch_visibility_resolver.build_scope(
            identity=identity,
            selected_turn_id=selected_turn_id,
        )

    def build_writer_manifest(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        packet_kind: str,
        packet_sections: list[dict[str, Any]] | None = None,
        selected_section_labels: list[str] | None = None,
        policy_versions: dict[str, str] | None = None,
    ) -> RuntimeReadManifest:
        if identity is None:
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_identity_required",
                packet_kind,
            )
        scope = self._branch_visibility_resolver.build_runtime_scope(identity=identity)
        if not scope.visible_branch_head_ids:
            raise RuntimeReadManifestServiceError(
                "runtime_read_manifest_branch_scope_missing",
                identity.branch_head_id,
            )
        material_records = self._runtime_workspace_material_service.list_materials(
            identity=identity,
        )
        packet_visible_material_records = [
            material
            for material in material_records
            if material.visibility
            == RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value
        ]
        visible_refs = self._build_visible_refs(
            identity=identity,
            packet_sections=packet_sections or [],
            material_records=packet_visible_material_records,
        )
        selected = self._select_refs(
            visible_refs=visible_refs,
            selected_section_labels=selected_section_labels or [],
        )
        omitted = self._build_omitted_refs(
            visible_refs=visible_refs,
            selected_refs=selected,
        )
        manifest_id = uuid5(
            NAMESPACE_URL,
            self._manifest_seed(
                identity=identity,
                packet_kind=packet_kind,
                branch_scope=scope.model_dump(mode="json"),
                visible_refs=visible_refs,
                selected_refs=selected,
                omitted_refs=omitted,
                packet_sections=packet_sections or [],
            ),
        ).hex
        retrieval_card_refs = self._material_refs(
            material_records=packet_visible_material_records,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        )
        expanded_chunk_refs = self._material_refs(
            material_records=packet_visible_material_records,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
        )
        retrieval_miss_refs = self._material_refs(
            material_records=packet_visible_material_records,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS,
        )
        writer_usage_refs = self._material_refs(
            material_records=material_records,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
        )
        token_usage_metadata = self._token_usage_metadata(
            material_records=packet_visible_material_records
        )
        return RuntimeReadManifest(
            manifest_id=manifest_id,
            identity=identity,
            active_branch_lineage=list(scope.visible_branch_head_ids),
            branch_scope=scope.model_dump(mode="json"),
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            policy_versions=dict(policy_versions or {"packet_kind": packet_kind}),
            visible_refs=visible_refs,
            selected_refs=selected,
            omitted_refs=omitted,
            packet_sections=[deepcopy(item) for item in (packet_sections or [])],
            retrieval_card_refs=retrieval_card_refs,
            expanded_chunk_refs=expanded_chunk_refs,
            retrieval_miss_refs=retrieval_miss_refs,
            writer_usage_refs=writer_usage_refs,
            token_usage_metadata=token_usage_metadata,
        )

    def _build_visible_refs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        packet_sections: list[dict[str, Any]],
        material_records: list[Any],
    ) -> list[dict[str, Any]]:
        visible_refs: list[dict[str, Any]] = []
        for order, section in enumerate(packet_sections):
            label = str(section.get("label") or "").strip()
            section_id = str(section.get("section_id") or "").strip()
            source_kind = str(section.get("source_kind") or "").strip()
            source_ref_ids = [
                str(item).strip()
                for item in (section.get("source_ref_ids") or [])
                if str(item).strip()
            ]
            section_items = section.get("items")
            items = list(section_items) if isinstance(section_items, list) else []
            visible_refs.append(
                {
                    "ref_id": section_id or f"packet_section:{label or order}",
                    "ref_kind": "packet_section",
                    "domain_path": f"packet.{label}" if label else None,
                    "selection_group": label or f"section_{order}",
                    "source_route": self._packet_section_source_route(
                        source_kind=source_kind
                    ),
                    "packet_section_label": label or None,
                    "packet_section_source_kind": source_kind or None,
                    "source_ref_ids": source_ref_ids,
                    "revision": None,
                    "content_hash": self._stable_hash(items),
                    "item_count": len(items),
                }
            )
        for material in material_records:
            visible_refs.append(
                {
                    "ref_id": material.material_id,
                    "ref_kind": f"runtime_workspace.{material.material_kind.value}",
                    "domain_path": material.domain_path,
                    "selection_group": material.material_kind.value,
                    "source_route": "runtime_workspace",
                    "packet_section_label": None,
                    "revision": None,
                    "content_hash": self._stable_hash(material.payload),
                    "lifecycle": material.lifecycle.value,
                    "visibility": material.visibility,
                    "source_refs": [
                        item.model_dump(mode="json") for item in material.source_refs
                    ],
                }
            )
        visible_refs.sort(
            key=lambda item: (str(item.get("ref_kind")), str(item.get("ref_id")))
        )
        return visible_refs

    @staticmethod
    def _select_refs(
        *,
        visible_refs: list[dict[str, Any]],
        selected_section_labels: list[str],
    ) -> list[dict[str, Any]]:
        if not selected_section_labels:
            return [
                deepcopy(item)
                for item in visible_refs
                if item.get("ref_kind") == "packet_section"
            ]
        allowed = {
            str(item).strip() for item in selected_section_labels if str(item).strip()
        }
        return [
            deepcopy(item)
            for item in visible_refs
            if item.get("packet_section_label") in allowed
        ]

    @staticmethod
    def _build_omitted_refs(
        *,
        visible_refs: list[dict[str, Any]],
        selected_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selected_ids = {str(item.get("ref_id")) for item in selected_refs}
        omitted: list[dict[str, Any]] = []
        for item in visible_refs:
            ref_id = str(item.get("ref_id"))
            if ref_id in selected_ids:
                continue
            omitted_item = deepcopy(item)
            if item.get("ref_kind") == "packet_section":
                omitted_item["reason"] = "packet_section_not_selected"
            else:
                omitted_item["reason"] = "packet_visible_runtime_workspace_only"
            omitted.append(omitted_item)
        return omitted

    @staticmethod
    def _packet_section_source_route(*, source_kind: str) -> str:
        normalized = str(source_kind or "").strip()
        if normalized == "core_projection_view":
            return "core_state.derived_projection"
        if normalized == "story_discussion_entry_window":
            return "story_discussion"
        if normalized == "runtime_retrieval_card_summary":
            return "runtime_workspace"
        if normalized == "worker_hint_digest":
            return "worker_result"
        if normalized in {"mode_sidecar", "runtime_mode_sidecar", "review_overlay"}:
            return "mode_sidecar"
        return "packet_section"

    @staticmethod
    def _material_refs(
        *,
        material_records: list[Any],
        material_kind: RuntimeWorkspaceMaterialKind,
    ) -> list[str]:
        return [
            material.material_id
            for material in material_records
            if material.material_kind == material_kind
            and material.lifecycle != RuntimeWorkspaceMaterialLifecycle.INVALIDATED
        ]

    @staticmethod
    def _token_usage_metadata(*, material_records: list[Any]) -> dict[str, Any]:
        payloads: list[dict[str, Any]] = []
        for material in material_records:
            if (
                material.material_kind
                != RuntimeWorkspaceMaterialKind.TOKEN_USAGE_METADATA
            ):
                continue
            if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED:
                continue
            payloads.append(deepcopy(material.payload))
        return {
            "count": len(payloads),
            "entries": payloads,
        }

    @staticmethod
    def _stable_hash(value: Any) -> str:
        return uuid5(
            NAMESPACE_URL,
            RuntimeReadManifestService._canonical_json(value),
        ).hex

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def _manifest_seed(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        packet_kind: str,
        branch_scope: dict[str, Any],
        visible_refs: list[dict[str, Any]],
        selected_refs: list[dict[str, Any]],
        omitted_refs: list[dict[str, Any]],
        packet_sections: list[dict[str, Any]],
    ) -> str:
        return self._canonical_json(
            {
                "identity": identity.model_dump(mode="json"),
                "packet_kind": packet_kind,
                "branch_scope": branch_scope,
                "visible_refs": visible_refs,
                "selected_refs": selected_refs,
                "omitted_refs": omitted_refs,
                "packet_sections": packet_sections,
            }
        )


def filter_hits_by_branch_visibility(
    *,
    resolver: BranchVisibilityResolver,
    scope: RuntimeBranchReadScope,
    hits: list[Any],
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Filter retrieval hits by branch metadata and return deterministic omission metadata."""

    visible_hits: list[Any] = []
    omitted_refs: list[dict[str, Any]] = []
    for hit in hits:
        metadata = dict(getattr(hit, "metadata", {}) or {})
        default_visibility_scope = "story_global"
        if metadata.get("selected_branch_head_ids") or metadata.get("branch_ids"):
            default_visibility_scope = "selected_branches"
        elif (
            _first_text(
                metadata,
                "owning_branch_head_id",
                "runtime_branch_head_id",
                "branch_head_id",
                "branch_id",
            )
            is not None
        ):
            default_visibility_scope = "branch_scoped"
        visible = resolver.is_visible(
            scope=scope,
            visibility_scope=str(
                metadata.get("visibility_scope") or default_visibility_scope
            ),
            visibility_state=str(
                metadata.get("visibility_state")
                or metadata.get("lifecycle_state")
                or "active"
            ),
            owning_branch_head_id=_first_text(
                metadata,
                "owning_branch_head_id",
                "runtime_branch_head_id",
                "branch_head_id",
                "branch_id",
            ),
            origin_turn_id=_first_text(
                metadata,
                "origin_turn_id",
                "runtime_turn_id",
                "turn_id",
            ),
            selected_branch_head_ids=_string_list(
                metadata.get("selected_branch_head_ids")
                or metadata.get("branch_ids")
                or metadata.get("selected_branch_ids")
            ),
            hidden_by_branch_head_id=_first_text(metadata, "hidden_by_branch_head_id"),
            hidden_after_turn_id=_first_text(metadata, "hidden_after_turn_id"),
        )
        if visible:
            visible_hits.append(hit)
            continue
        omitted_refs.append(
            {
                "ref_id": getattr(hit, "hit_id", ""),
                "ref_kind": f"retrieval.{getattr(hit, 'layer', 'unknown')}",
                "reason": "branch_hidden",
                "metadata": metadata,
            }
        )
    return visible_hits, omitted_refs


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
