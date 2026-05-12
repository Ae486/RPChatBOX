"""Authoritative read service over formal store with mirror fallback."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .core_state_backfill_service import CoreStateBackfillService
from .core_state_as_of_resolver import (
    CoreStateAsOfResolver,
    CoreStateAsOfResolverError,
)
from .core_state_store_repository import CoreStateStoreRepository
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProvenanceResult,
    StateReadResult,
    StateReadResultItem,
    VersionListResult,
)

from .memory_object_mapper import (
    default_authoritative_ref_for_domain,
    normalize_authoritative_ref,
    resolve_authoritative_binding,
)
from .story_session_core_state_adapter import StorySessionCoreStateAdapter


class CoreStateReadService:
    """Read authoritative Core State from formal store or compatibility mirror."""

    def __init__(
        self,
        *,
        adapter: StorySessionCoreStateAdapter,
        version_history_read_service=None,
        provenance_read_service=None,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
        core_state_backfill_service: CoreStateBackfillService | None = None,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        core_state_as_of_resolver: CoreStateAsOfResolver | None = None,
    ) -> None:
        self._adapter = adapter
        self._version_history_read_service = version_history_read_service
        self._provenance_read_service = provenance_read_service
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled
        self._core_state_backfill_service = core_state_backfill_service
        self._runtime_identity = runtime_identity
        self._core_state_as_of_resolver = core_state_as_of_resolver

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        refs = input_model.refs or [
            default_authoritative_ref_for_domain(
                input_model.domain,
                scope=input_model.scope,
            )
        ]
        session_id = self._runtime_session_id()
        session = self._adapter.get_story_session(session_id=session_id)
        _, payload = self._adapter.get_state_payload(session_id=session_id)
        items: list[StateReadResultItem] = []
        version_refs: list[str] = []
        top_level_warnings: list[str] = []
        if session is None:
            top_level_warnings.append("phase_e_story_context_missing")
        authoritative_store_hydrated = False
        runtime_owned_read = self._runtime_identity is not None
        core_manifest = None
        if runtime_owned_read and self._core_state_as_of_resolver is not None:
            core_manifest = self._core_state_as_of_resolver.ensure_manifest_for_identity(
                identity=self._runtime_identity
            )
            compatibility_warning = str(
                core_manifest.metadata.get("compatibility_warning") or ""
            ).strip()
            if compatibility_warning:
                top_level_warnings.append(compatibility_warning)

        for raw_ref in refs:
            ref = normalize_authoritative_ref(raw_ref)
            binding = resolve_authoritative_binding(ref)
            current_revision = self._current_revision(
                ref,
                session_id=session.session_id if session is not None else None,
            )
            effective_ref = ref.model_copy(update={"revision": current_revision})
            data: dict[str, Any] = {}
            warnings: list[str] = []
            if session is None:
                warnings.append("phase_e_story_context_missing")
            if binding is None:
                warnings.append(
                    f"phase_e_authoritative_ref_not_materialized:{effective_ref.object_id}"
                )
            else:
                has_store_value = False
                if (
                    self._store_read_enabled
                    and self._core_state_store_repository is not None
                    and session is not None
                ):
                    if core_manifest is not None:
                        try:
                            if self._core_state_as_of_resolver is None:
                                raise CoreStateAsOfResolverError(
                                    "core_state_as_of_resolver_missing",
                                    ref.object_id,
                                )
                            revision_row = (
                                self._core_state_as_of_resolver.resolve_object_revision(
                                    manifest=core_manifest,
                                    object_ref=ref,
                                )
                            )
                            data = self._clone_state_payload(revision_row.data_json)
                            effective_ref = ref.model_copy(
                                update={"revision": revision_row.revision}
                            )
                            has_store_value = True
                        except CoreStateAsOfResolverError as exc:
                            warnings.append(exc.code)
                    elif runtime_owned_read:
                        warnings.append(
                            "core_state_as_of_manifest_missing_runtime_read_forbidden"
                        )
                    else:
                        row = self._core_state_store_repository.get_authoritative_object(
                            session_id=session.session_id,
                            layer=ref.layer.value,
                            scope=ref.scope or "story",
                            object_id=ref.object_id,
                        )
                        if (
                            row is None
                            and not authoritative_store_hydrated
                            and self._core_state_backfill_service is not None
                        ):
                            self._core_state_backfill_service.backfill_authoritative_for_session(
                                session_id=session.session_id
                            )
                            authoritative_store_hydrated = True
                            row = self._core_state_store_repository.get_authoritative_object(
                                session_id=session.session_id,
                                layer=ref.layer.value,
                                scope=ref.scope or "story",
                                object_id=ref.object_id,
                            )
                        if row is not None:
                            data = self._clone_state_payload(row.data_json)
                            has_store_value = True
                        else:
                            warnings.append(
                                "phase_g_store_row_missing_fallback:"
                                f"{effective_ref.object_id}"
                            )
                if not has_store_value and not runtime_owned_read:
                    value = payload.get(binding.backend_field)
                    if value is None:
                        warnings.append(
                            f"phase_e_authoritative_value_missing:{binding.backend_field}"
                        )
                    else:
                        data = self._clone_state_payload(value)
                elif not has_store_value and runtime_owned_read:
                    warnings.append(
                        "core_state_runtime_current_row_and_session_mirror_fallback_blocked"
                    )
            items.append(
                StateReadResultItem(
                    object_ref=effective_ref, data=data, warnings=warnings
                )
            )
            version_refs.append(
                f"{effective_ref.object_id}@{effective_ref.revision or 1}"
            )

        return StateReadResult(
            items=items,
            version_refs=version_refs,
            warnings=top_level_warnings,
        )

    async def list_versions(
        self, input_model: MemoryListVersionsInput
    ) -> VersionListResult:
        if self._version_history_read_service is not None:
            return self._version_history_read_service.list_versions(
                input_model.target_ref,
                session_id=self._runtime_session_id(),
            )
        ref = normalize_authoritative_ref(input_model.target_ref)
        current_ref = f"{ref.object_id}@{ref.revision or 1}"
        return VersionListResult(versions=[current_ref], current_ref=current_ref)

    async def read_provenance(
        self, input_model: MemoryReadProvenanceInput
    ) -> ProvenanceResult:
        if self._provenance_read_service is not None:
            return self._provenance_read_service.read_provenance(
                input_model.target_ref,
                session_id=self._runtime_session_id(),
            )
        ref = normalize_authoritative_ref(input_model.target_ref)
        return ProvenanceResult(
            target_ref=ref,
            source_refs=["compatibility_mirror:story_session.current_state_json"],
            proposal_refs=[],
            ingestion_refs=[],
        )

    def _current_revision(
        self,
        ref,
        *,
        session_id: str | None,
    ) -> int:
        if self._version_history_read_service is None:
            return ref.revision or 1
        version_result = self._version_history_read_service.list_versions(
            ref,
            session_id=session_id,
        )
        current_ref = (
            version_result.current_ref or f"{ref.object_id}@{ref.revision or 1}"
        )
        try:
            return int(current_ref.rsplit("@", 1)[1])
        except (IndexError, ValueError):
            return ref.revision or 1

    def _runtime_session_id(self) -> str | None:
        if self._runtime_identity is None:
            return None
        return self._runtime_identity.session_id

    @staticmethod
    def _clone_state_payload(value: Any) -> dict[str, Any]:
        cloned = deepcopy(value)
        if isinstance(cloned, dict):
            return cloned
        if isinstance(cloned, list):
            return {"items": cloned}
        if cloned is None:
            return {}
        return {"value": cloned}
