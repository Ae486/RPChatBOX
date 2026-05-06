"""Govern lifecycle transitions for retrieval-core-backed Recall material."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_materialization import (
    RECALL_LIFECYCLE_INVALIDATED,
    RECALL_LIFECYCLE_RECOMPUTED,
    RECALL_LIFECYCLE_SUPERSEDED,
    RecallLifecycleMetadata,
)

from .retrieval_document_service import RetrievalDocumentService
from .retrieval_ingestion_service import RetrievalIngestionService


class RecallLifecycleService:
    """Apply minimal lifecycle governance without introducing a second Recall store."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def supersede_material(
        self,
        *,
        material_refs: Sequence[str],
        replacement_metadata: RecallLifecycleMetadata | Mapping[str, Any],
    ) -> list[str]:
        return self._mark_assets(
            asset_ids=material_refs,
            lifecycle_state=RECALL_LIFECYCLE_SUPERSEDED,
            metadata_update={
                "superseded_by_runtime_identity": self._replacement_identity_payload(
                    replacement_metadata
                ),
            },
        )

    def invalidate_material(
        self,
        *,
        material_refs: Sequence[str],
        event_id: str,
        reason: str,
    ) -> list[str]:
        normalized_event_id = event_id.strip()
        normalized_reason = reason.strip()
        if not normalized_event_id:
            raise ValueError("event_id must be non-empty")
        if not normalized_reason:
            raise ValueError("reason must be non-empty")
        return self._mark_assets(
            asset_ids=material_refs,
            lifecycle_state=RECALL_LIFECYCLE_INVALIDATED,
            metadata_update={
                "invalidated_reason": normalized_reason,
            },
            invalidated_event_id=normalized_event_id,
        )

    def recompute_material(
        self,
        *,
        material_refs: Sequence[str],
        replacement_metadata: RecallLifecycleMetadata | Mapping[str, Any],
    ) -> list[str]:
        replacement_payload = (
            replacement_metadata.model_dump(mode="json")
            if isinstance(replacement_metadata, RecallLifecycleMetadata)
            else dict(replacement_metadata)
        )
        touched_asset_ids: list[str] = []
        seen: set[str] = set()
        for raw_asset_id in material_refs:
            asset_id = str(raw_asset_id or "").strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            asset = self._document_service.get_source_asset(asset_id)
            if asset is None:
                continue
            metadata = self.build_recomputed_metadata(
                existing_metadata=asset.metadata,
                replacement_metadata={
                    **replacement_payload,
                    "recomputed_by_runtime_identity": self._replacement_identity_payload(
                        replacement_payload
                    ),
                },
            )
            seed_sections = metadata.get("seed_sections")
            if isinstance(seed_sections, list):
                normalized_sections: list[dict[str, Any]] = []
                for item in seed_sections:
                    if not isinstance(item, dict):
                        continue
                    section = deepcopy(item)
                    section_metadata = dict(section.get("metadata") or {})
                    section_metadata.update(
                        {
                            "lifecycle_state": metadata.get("lifecycle_state"),
                            "visibility_state": metadata.get("visibility_state"),
                            "supersedes_refs": list(
                                metadata.get("supersedes_refs") or []
                            ),
                        }
                    )
                    section["metadata"] = section_metadata
                    normalized_sections.append(section)
                metadata["seed_sections"] = normalized_sections
            self._document_service.upsert_source_asset(
                asset.model_copy(update={"metadata": metadata})
            )
            job = self._ingestion_service.reindex_asset(
                story_id=asset.story_id,
                asset_id=asset.asset_id,
            )
            if job.job_state != "completed":
                error_detail = job.error_message or job.job_state
                raise RuntimeError(
                    f"recall_lifecycle_reindex_failed:{asset.asset_id}:{error_detail}"
                )
            touched_asset_ids.append(asset.asset_id)
        return touched_asset_ids

    @staticmethod
    def build_recomputed_metadata(
        *,
        existing_metadata: Mapping[str, Any],
        replacement_metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        metadata = deepcopy(dict(replacement_metadata))
        supersedes_refs = list(metadata.get("supersedes_refs") or [])
        supersedes_refs.extend(list(existing_metadata.get("supersedes_refs") or []))
        for ref in list(existing_metadata.get("source_refs") or []):
            if not isinstance(ref, dict):
                continue
            source_type = str(ref.get("source_type") or "").strip()
            source_id = str(ref.get("source_id") or "").strip()
            if not source_type or not source_id:
                continue
            supersedes_refs.append(f"{source_type}:{source_id}")
        existing_runtime_identity = existing_metadata.get("runtime_identity")
        if isinstance(existing_runtime_identity, dict):
            turn_id = str(existing_runtime_identity.get("turn_id") or "").strip()
            if turn_id:
                supersedes_refs.append(f"story_turn:{turn_id}")
        metadata["lifecycle_state"] = RECALL_LIFECYCLE_RECOMPUTED
        metadata["visibility_state"] = "active"
        metadata["supersedes_refs"] = RecallLifecycleService._dedupe_text_values(
            supersedes_refs
        )
        return metadata

    def _mark_assets(
        self,
        *,
        asset_ids: Sequence[str],
        lifecycle_state: str,
        metadata_update: Mapping[str, Any] | None = None,
        invalidated_event_id: str | None = None,
    ) -> list[str]:
        touched_asset_ids: list[str] = []
        seen: set[str] = set()
        for raw_asset_id in asset_ids:
            asset_id = str(raw_asset_id or "").strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            asset = self._document_service.get_source_asset(asset_id)
            if asset is None:
                continue
            metadata = deepcopy(asset.metadata)
            metadata["lifecycle_state"] = lifecycle_state
            metadata["visibility_state"] = self._visibility_state_for_lifecycle(
                lifecycle_state
            )
            if invalidated_event_id is not None:
                existing_ids = list(metadata.get("invalidated_by_event_ids") or [])
                if invalidated_event_id not in existing_ids:
                    existing_ids.append(invalidated_event_id)
                metadata["invalidated_by_event_ids"] = existing_ids
            if metadata_update:
                metadata.update(dict(metadata_update))
            seed_sections = metadata.get("seed_sections")
            if isinstance(seed_sections, list):
                normalized_sections: list[dict[str, Any]] = []
                for item in seed_sections:
                    if not isinstance(item, dict):
                        continue
                    section = deepcopy(item)
                    section_metadata = dict(section.get("metadata") or {})
                    section_metadata["lifecycle_state"] = lifecycle_state
                    section_metadata["visibility_state"] = (
                        self._visibility_state_for_lifecycle(lifecycle_state)
                    )
                    if invalidated_event_id is not None:
                        existing_ids = list(
                            section_metadata.get("invalidated_by_event_ids") or []
                        )
                        if invalidated_event_id not in existing_ids:
                            existing_ids.append(invalidated_event_id)
                        section_metadata["invalidated_by_event_ids"] = existing_ids
                    if metadata_update:
                        section_metadata.update(dict(metadata_update))
                    section["metadata"] = section_metadata
                    normalized_sections.append(section)
                metadata["seed_sections"] = normalized_sections
            self._document_service.upsert_source_asset(
                asset.model_copy(update={"metadata": metadata})
            )
            job = self._ingestion_service.reindex_asset(
                story_id=asset.story_id,
                asset_id=asset.asset_id,
            )
            if job.job_state != "completed":
                error_detail = job.error_message or job.job_state
                raise RuntimeError(
                    f"recall_lifecycle_reindex_failed:{asset.asset_id}:{error_detail}"
                )
            touched_asset_ids.append(asset.asset_id)
        return touched_asset_ids

    @staticmethod
    def _replacement_identity_payload(
        metadata: RecallLifecycleMetadata | Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if isinstance(metadata, RecallLifecycleMetadata):
            identity = metadata.identity
        else:
            payload = dict(metadata)
            raw_identity = payload.get("runtime_identity") or payload.get("identity")
            if raw_identity is None:
                identity = None
            else:
                identity = MemoryRuntimeIdentity.model_validate(raw_identity)
        if identity is None:
            return None
        return identity.model_dump(mode="json")

    @staticmethod
    def _visibility_state_for_lifecycle(lifecycle_state: str) -> str:
        if lifecycle_state == RECALL_LIFECYCLE_RECOMPUTED:
            return "active"
        return lifecycle_state

    @staticmethod
    def _dedupe_text_values(values: Sequence[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped
