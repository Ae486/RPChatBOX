"""Settled projection read service over formal store with mirror fallback."""

from __future__ import annotations

from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import (
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProvenanceResult,
    SummaryEntry,
    SummaryReadResult,
    VersionListResult,
)

from .core_state_backfill_service import CoreStateBackfillService
from .core_state_store_repository import CoreStateStoreRepository
from .chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from .memory_object_mapper import (
    normalize_projection_summary_id,
    projection_summary_ids_for_domain,
    resolve_projection_binding,
)


class ProjectionReadService:
    """Read settled projection slots from formal store or compatibility mirror."""

    def __init__(
        self,
        *,
        adapter: ChapterWorkspaceProjectionAdapter,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
        core_state_backfill_service: CoreStateBackfillService | None = None,
    ) -> None:
        self._adapter = adapter
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled
        self._core_state_backfill_service = core_state_backfill_service

    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult:
        summary_ids, resolution_warnings = self._resolve_summary_ids(input_model)
        session, chapter, payload = self._adapter.get_projection_payload()
        items: list[SummaryEntry] = []
        warnings: list[str] = list(resolution_warnings)
        projection_store_hydrated = False

        if chapter is None:
            warnings.append("phase_e_story_context_missing")
            return SummaryReadResult(items=items, warnings=warnings)

        for summary_id in summary_ids:
            binding = resolve_projection_binding(summary_id)
            if binding is None:
                warnings.append(f"phase_e_projection_summary_not_materialized:{summary_id}")
                continue
            raw_value = None
            route = "projection.compatibility_mirror"
            if (
                self._store_read_enabled
                and self._core_state_store_repository is not None
                and chapter is not None
            ):
                row = self._core_state_store_repository.get_projection_slot(
                    chapter_workspace_id=chapter.chapter_workspace_id,
                    summary_id=binding.summary_id,
                )
                if (
                    row is None
                    and not projection_store_hydrated
                    and self._core_state_backfill_service is not None
                ):
                    self._core_state_backfill_service.backfill_projection_for_chapter(
                        chapter_workspace_id=chapter.chapter_workspace_id
                    )
                    projection_store_hydrated = True
                    row = self._core_state_store_repository.get_projection_slot(
                        chapter_workspace_id=chapter.chapter_workspace_id,
                        summary_id=binding.summary_id,
                    )
                if row is not None:
                    raw_value = row.items_json
                    route = "projection.formal_store"
                else:
                    warnings.append(f"phase_g_projection_store_row_missing_fallback:{binding.summary_id}")
            if raw_value is None:
                raw_value = payload.get(binding.slot_name)
            if raw_value is None:
                warnings.append(f"phase_e_projection_slot_empty:{binding.summary_id}")
                summary_text = ""
            elif isinstance(raw_value, list):
                summary_text = "\n".join(str(item) for item in raw_value if item is not None)
            else:
                summary_text = str(raw_value)
            items.append(
                SummaryEntry(
                    summary_id=binding.summary_id,
                    domain=binding.domain,
                    domain_path=binding.domain_path,
                    summary_text=summary_text,
                    metadata={
                        "slot_name": binding.slot_name,
                        "route": route,
                        "scope": input_model.scope,
                        "session_id": session.session_id if session is not None else None,
                        "chapter_workspace_id": chapter.chapter_workspace_id,
                    },
                )
            )

        return SummaryReadResult(items=items, warnings=warnings)

    async def list_versions(self, input_model: MemoryListVersionsInput) -> VersionListResult:
        ref = input_model.target_ref.model_copy(
            update={
                "layer": Layer.CORE_STATE_PROJECTION,
                "domain_path": input_model.target_ref.domain_path or input_model.target_ref.object_id,
                "revision": input_model.target_ref.revision or 1,
            }
        )
        if self._store_read_enabled and self._core_state_store_repository is not None:
            _, chapter = self._adapter.get_current_chapter()
            if chapter is not None:
                revisions = self._core_state_store_repository.list_projection_slot_revisions(
                    chapter_workspace_id=chapter.chapter_workspace_id,
                    summary_id=normalize_projection_summary_id(ref.object_id),
                )
                if revisions:
                    versions = [
                        f"{ref.object_id}@{item.revision}"
                        for item in sorted(revisions, key=lambda item: item.revision, reverse=True)
                    ]
                    return VersionListResult(versions=versions, current_ref=versions[0])
        current_ref = f"{ref.object_id}@{ref.revision or 1}"
        return VersionListResult(versions=[current_ref], current_ref=current_ref)

    async def read_provenance(self, input_model: MemoryReadProvenanceInput) -> ProvenanceResult:
        ref = input_model.target_ref.model_copy(
            update={
                "layer": Layer.CORE_STATE_PROJECTION,
                "domain_path": input_model.target_ref.domain_path or input_model.target_ref.object_id,
                "revision": input_model.target_ref.revision or 1,
            }
        )
        if self._store_read_enabled and self._core_state_store_repository is not None:
            _, chapter = self._adapter.get_current_chapter()
            if chapter is not None:
                row = self._core_state_store_repository.get_projection_slot(
                    chapter_workspace_id=chapter.chapter_workspace_id,
                    summary_id=normalize_projection_summary_id(ref.object_id),
                )
                if row is not None:
                    return ProvenanceResult(
                        target_ref=ref.model_copy(update={"revision": row.current_revision}),
                        source_refs=["core_state_store:projection_slot_revision"],
                        proposal_refs=[],
                        ingestion_refs=[],
                    )
        return ProvenanceResult(
            target_ref=ref,
            source_refs=["compatibility_mirror:chapter_workspace.builder_snapshot_json"],
            proposal_refs=[],
            ingestion_refs=[],
        )

    @staticmethod
    def _resolve_summary_ids(input_model: MemoryGetSummaryInput) -> tuple[list[str], list[str]]:
        if input_model.summary_ids:
            return (
                [normalize_projection_summary_id(summary_id) for summary_id in input_model.summary_ids],
                [],
            )

        summary_ids: list[str] = []
        warnings: list[str] = []
        for domain in input_model.domains:
            domain_summary_ids = projection_summary_ids_for_domain(domain)
            if domain_summary_ids:
                summary_ids.extend(domain_summary_ids)
                continue
            warnings.append(f"phase_e_projection_domain_not_materialized:{domain.value}")
        return summary_ids, warnings
