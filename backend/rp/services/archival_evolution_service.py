"""Governed version evolution for retrieval-core-backed Archival Knowledge."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlmodel import select

from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    KnowledgeCollectionRecord,
    KnowledgeChunkRecord,
)
from models.rp_story_store import BranchHeadRecord
from rp.models.archival_evolution import (
    ARCHIVAL_EVOLUTION_EVENT,
    ARCHIVAL_EVOLUTION_SOURCE_FAMILY,
    ARCHIVAL_LIFECYCLE_ACTIVE,
    ARCHIVAL_LIFECYCLE_SUPERSEDED,
    ARCHIVAL_VISIBILITY_ACTIVE,
    ArchivalEvolutionReceipt,
    ArchivalEvolutionRequest,
    ArchivalEvolutionSection,
    ArchivalEvolutionVisibilityScope,
)
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemorySourceRef,
)
from rp.models.memory_materialization import ARCHIVAL_LAYER
from rp.models.retrieval_records import SourceAsset
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArchivalEvolutionService:
    """Create versioned archival source replacements over retrieval-core rows."""

    def __init__(
        self,
        session,
        *,
        document_service: RetrievalDocumentService | None = None,
        ingestion_service: RetrievalIngestionService | None = None,
        memory_change_event_service: MemoryChangeEventService | None = None,
    ) -> None:
        self._session = session
        self._document_service = document_service or RetrievalDocumentService(session)
        self._ingestion_service = ingestion_service or RetrievalIngestionService(
            session
        )
        self._memory_change_event_service = (
            memory_change_event_service or MemoryChangeEventService(session=session)
        )

    def evolve_source(
        self,
        request: ArchivalEvolutionRequest,
    ) -> ArchivalEvolutionReceipt:
        """Create a new archival source version and hide the superseded version.

        The old source text is never overwritten. The replacement becomes a new
        `SourceAssetRecord`, is indexed through the existing ingestion pipeline,
        and the supersession chain is captured in asset/chunk metadata plus one
        persistent memory event.
        """

        source_asset = self._document_service.get_source_asset(request.source_asset_id)
        if source_asset is None:
            raise ValueError(
                f"archival_evolution_source_asset_not_found:{request.source_asset_id}"
            )
        if source_asset.story_id != request.identity.story_id:
            raise ValueError(
                "archival_evolution_story_mismatch:"
                f"{source_asset.story_id}:{request.identity.story_id}"
            )
        self._require_archival_source_asset(source_asset)

        superseded_version = _source_version(source_asset.metadata)
        if (
            request.expected_source_version is not None
            and request.expected_source_version != superseded_version
        ):
            raise ValueError(
                "archival_evolution_source_version_conflict:"
                f"expected={request.expected_source_version}:"
                f"actual={superseded_version}"
            )

        evolution_id = f"archival_evolution_{uuid4().hex}"
        new_source_version = superseded_version + 1
        root_source_asset_id = str(
            source_asset.metadata.get("root_source_asset_id")
            or source_asset.metadata.get("original_source_asset_id")
            or source_asset.asset_id
        )
        new_asset_id = self._new_asset_id(
            root_source_asset_id=root_source_asset_id,
            new_source_version=new_source_version,
            evolution_id=evolution_id,
        )
        selected_branch_head_ids = self._selected_branch_ids(request)
        new_metadata = self._build_new_source_metadata(
            request=request,
            source_asset=source_asset,
            evolution_id=evolution_id,
            new_asset_id=new_asset_id,
            root_source_asset_id=root_source_asset_id,
            new_source_version=new_source_version,
            superseded_source_version=superseded_version,
            selected_branch_head_ids=selected_branch_head_ids,
        )
        now = _utcnow()
        new_asset = SourceAsset(
            asset_id=new_asset_id,
            story_id=source_asset.story_id,
            mode=source_asset.mode,
            collection_id=source_asset.collection_id,
            workspace_id=source_asset.workspace_id,
            step_id=source_asset.step_id,
            commit_id=source_asset.commit_id,
            asset_kind=source_asset.asset_kind,
            source_ref=f"{source_asset.source_ref}#v{new_source_version}",
            title=source_asset.title,
            storage_path=None,
            mime_type=source_asset.mime_type,
            raw_excerpt=self._first_section_excerpt(request.replacement_sections),
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=list(source_asset.mapped_targets),
            metadata=new_metadata,
            created_at=now,
            updated_at=now,
        )
        self._document_service.upsert_source_asset(new_asset)
        self._session.flush()

        job = self._ingestion_service.reindex_asset(
            story_id=source_asset.story_id,
            asset_id=new_asset_id,
        )
        self._session.flush()
        replacement_chunk_ids = self._annotate_replacement_chunks(
            new_asset_id=new_asset_id,
            evolution_id=evolution_id,
            new_source_version=new_source_version,
            superseded_source_asset_id=source_asset.asset_id,
            superseded_source_version=superseded_version,
            reindex_job_id=job.job_id,
            source_refs=request.source_refs,
        )

        warnings: list[str] = []
        if job.job_state == "completed":
            self._supersede_source_asset(
                source_asset=source_asset,
                evolution_id=evolution_id,
                replacement_asset_id=new_asset_id,
                replacement_source_version=new_source_version,
            )
        else:
            warnings.append(
                f"archival_evolution_reindex_not_completed:{job.job_id}:{job.job_state}"
            )

        event = self._record_evolution_event(
            request=request,
            evolution_id=evolution_id,
            domain=str(new_metadata.get("domain") or "world_rule"),
            new_asset_id=new_asset_id,
            root_source_asset_id=root_source_asset_id,
            new_source_version=new_source_version,
            superseded_source_asset_id=source_asset.asset_id,
            superseded_source_version=superseded_version,
            replacement_chunk_ids=replacement_chunk_ids,
            reindex_job_id=job.job_id,
            selected_branch_head_ids=selected_branch_head_ids,
            warnings=warnings,
        )
        self._session.flush()

        return ArchivalEvolutionReceipt(
            evolution_id=evolution_id,
            source_asset_id=new_asset_id,
            superseded_source_asset_id=source_asset.asset_id,
            root_source_asset_id=root_source_asset_id,
            new_source_version=new_source_version,
            superseded_source_version=superseded_version,
            visibility_scope=request.visibility_scope,
            selected_branch_head_ids=selected_branch_head_ids,
            replacement_chunk_ids=replacement_chunk_ids,
            reindex_job_ids=[job.job_id],
            event_ids=[event.event_id],
            source_refs=self._receipt_source_refs(
                request=request,
                new_asset_id=new_asset_id,
                new_source_version=new_source_version,
                replacement_chunk_ids=replacement_chunk_ids,
                reindex_job_id=job.job_id,
                event_id=event.event_id,
            ),
            warnings=warnings,
        )

    def _require_archival_source_asset(self, source_asset: SourceAsset) -> None:
        collection_kind: str | None = None
        if source_asset.collection_id:
            collection = self._session.get(
                KnowledgeCollectionRecord,
                source_asset.collection_id,
            )
            collection_kind = (
                str(collection.collection_kind or "").strip()
                if collection is not None
                else None
            )
            if collection_kind and collection_kind != "archival":
                raise ValueError(
                    "archival_evolution_non_archival_source:"
                    f"{source_asset.asset_id}:collection={collection_kind}"
                )

        metadata = dict(source_asset.metadata or {})
        layer = str(metadata.get("layer") or "").strip()
        materialized_to_archival = bool(metadata.get("materialized_to_archival"))
        if collection_kind == "archival" or layer == ARCHIVAL_LAYER:
            return
        if materialized_to_archival:
            return
        raise ValueError(
            "archival_evolution_non_archival_source:"
            f"{source_asset.asset_id}:layer={layer or 'missing'}"
        )

    def _new_asset_id(
        self,
        *,
        root_source_asset_id: str,
        new_source_version: int,
        evolution_id: str,
    ) -> str:
        base = f"{root_source_asset_id}__v{new_source_version}"
        if self._document_service.get_source_asset(base) is None:
            return base
        return f"{base}_{evolution_id.rsplit('_', 1)[-1][:8]}"

    def _selected_branch_ids(
        self,
        request: ArchivalEvolutionRequest,
    ) -> list[str]:
        if request.visibility_scope == ArchivalEvolutionVisibilityScope.CURRENT_BRANCH:
            return [request.identity.branch_head_id]
        if (
            request.visibility_scope
            == ArchivalEvolutionVisibilityScope.SELECTED_BRANCHES
        ):
            return _dedupe_text_values(request.selected_branch_head_ids)
        if (
            request.visibility_scope
            == ArchivalEvolutionVisibilityScope.ALL_EXISTING_BRANCHES
        ):
            stmt = (
                select(BranchHeadRecord.branch_head_id)
                .where(BranchHeadRecord.story_id == request.identity.story_id)
                .where(BranchHeadRecord.session_id == request.identity.session_id)
                .order_by(BranchHeadRecord.created_at.asc())
                .order_by(BranchHeadRecord.branch_head_id.asc())
            )
            branch_ids = [str(item) for item in self._session.exec(stmt).all()]
            if request.identity.branch_head_id not in branch_ids:
                branch_ids.append(request.identity.branch_head_id)
            return _dedupe_text_values(branch_ids)
        return []

    def _build_new_source_metadata(
        self,
        *,
        request: ArchivalEvolutionRequest,
        source_asset: SourceAsset,
        evolution_id: str,
        new_asset_id: str,
        root_source_asset_id: str,
        new_source_version: int,
        superseded_source_version: int,
        selected_branch_head_ids: list[str],
    ) -> dict[str, Any]:
        base_metadata = {
            key: deepcopy(value)
            for key, value in dict(source_asset.metadata).items()
            if key
            not in {
                "seed_sections",
                "lifecycle_state",
                "visibility_state",
                "superseded_by_source_asset_id",
                "superseded_by_evolution_id",
                "superseded_by_source_version",
                "superseded_at",
            }
        }
        domain = str(base_metadata.get("domain") or "world_rule")
        domain_path = str(
            base_metadata.get("domain_path")
            or f"{domain}.archival.{root_source_asset_id}"
        )
        source_refs = [item.model_dump(mode="json") for item in request.source_refs]
        metadata = {
            **base_metadata,
            "layer": ARCHIVAL_LAYER,
            "source_family": ARCHIVAL_EVOLUTION_SOURCE_FAMILY,
            "source_origin": "story_evolution",
            "import_event": ARCHIVAL_EVOLUTION_EVENT,
            "materialized_to_archival": True,
            "materialized_to_recall": False,
            "authoritative_mutation": False,
            "source_type": str(
                base_metadata.get("source_type") or source_asset.asset_kind
            ),
            "source_ref": f"{source_asset.source_ref}#v{new_source_version}",
            "domain": domain,
            "domain_path": domain_path,
            "archival_evolution_id": evolution_id,
            "root_source_asset_id": root_source_asset_id,
            "source_asset_id": new_asset_id,
            "source_version": new_source_version,
            "source_asset_version": new_source_version,
            "supersedes_source_asset_id": source_asset.asset_id,
            "supersedes_source_version": superseded_source_version,
            "runtime_identity": request.identity.model_dump(mode="json"),
            "branch_head_id": request.identity.branch_head_id,
            "owning_branch_head_id": request.identity.branch_head_id,
            "turn_id": request.identity.turn_id,
            "origin_turn_id": request.identity.turn_id,
            "runtime_profile_snapshot_id": (
                request.identity.runtime_profile_snapshot_id
            ),
            "visibility_scope": request.visibility_scope.value,
            "selected_branch_head_ids": list(selected_branch_head_ids),
            "lifecycle_state": ARCHIVAL_LIFECYCLE_ACTIVE,
            "visibility_state": ARCHIVAL_VISIBILITY_ACTIVE,
            "source_refs": source_refs,
            "reason": request.reason,
        }
        metadata["seed_sections"] = [
            self._build_seed_section(
                section=section,
                index=index,
                metadata=metadata,
                evolution_id=evolution_id,
                new_source_version=new_source_version,
            )
            for index, section in enumerate(request.replacement_sections)
        ]
        return metadata

    @staticmethod
    def _build_seed_section(
        *,
        section: ArchivalEvolutionSection,
        index: int,
        metadata: Mapping[str, Any],
        evolution_id: str,
        new_source_version: int,
    ) -> dict[str, Any]:
        section_metadata = dict(section.metadata)
        section_metadata.update(
            {
                key: deepcopy(value)
                for key, value in metadata.items()
                if key != "seed_sections"
            }
        )
        section_metadata["section_source_version"] = new_source_version
        tags = _dedupe_text_values(
            [
                *list(section.tags),
                "archival",
                "story_evolution",
                f"source_version:{new_source_version}",
            ]
        )
        return {
            "section_id": section.section_id or f"{evolution_id}:section:{index}",
            "title": section.title
            or str(metadata.get("title") or "Archival Evolution"),
            "path": section.path
            or f"{metadata.get('domain_path')}.v{new_source_version}.section_{index}",
            "level": section.level,
            "text": section.text,
            "metadata": {**section_metadata, "tags": tags},
        }

    def _annotate_replacement_chunks(
        self,
        *,
        new_asset_id: str,
        evolution_id: str,
        new_source_version: int,
        superseded_source_asset_id: str,
        superseded_source_version: int,
        reindex_job_id: str,
        source_refs: Sequence[MemorySourceRef],
    ) -> list[str]:
        stmt = (
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.asset_id == new_asset_id)
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
            .order_by(KnowledgeChunkRecord.chunk_index.asc())
        )
        chunks = list(self._session.exec(stmt).all())
        source_ref_payloads = [item.model_dump(mode="json") for item in source_refs]
        for chunk in chunks:
            metadata = dict(chunk.metadata_json or {})
            metadata.update(
                {
                    "archival_evolution_id": evolution_id,
                    "source_version": new_source_version,
                    "source_asset_version": new_source_version,
                    "chunk_version": new_source_version,
                    "supersedes_source_asset_id": superseded_source_asset_id,
                    "supersedes_source_version": superseded_source_version,
                    "reindex_job_id": reindex_job_id,
                    "source_refs": source_ref_payloads,
                }
            )
            chunk.metadata_json = metadata
            chunk.provenance_refs_json = _dedupe_text_values(
                [
                    *list(chunk.provenance_refs_json or []),
                    f"archival_evolution:{evolution_id}",
                    f"source_asset:{new_asset_id}@v{new_source_version}",
                    (
                        f"supersedes_source_asset:{superseded_source_asset_id}"
                        f"@v{superseded_source_version}"
                    ),
                    f"index_job:{reindex_job_id}",
                ]
            )
            self._session.add(chunk)
        return [chunk.chunk_id for chunk in chunks]

    def _supersede_source_asset(
        self,
        *,
        source_asset: SourceAsset,
        evolution_id: str,
        replacement_asset_id: str,
        replacement_source_version: int,
    ) -> None:
        metadata = deepcopy(source_asset.metadata)
        metadata.update(
            {
                "lifecycle_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                "visibility_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                "superseded_by_source_asset_id": replacement_asset_id,
                "superseded_by_evolution_id": evolution_id,
                "superseded_by_source_version": replacement_source_version,
                "superseded_at": _utcnow().isoformat(),
            }
        )
        seed_sections = metadata.get("seed_sections")
        if isinstance(seed_sections, list):
            metadata["seed_sections"] = [
                self._superseded_seed_section(
                    section=section,
                    evolution_id=evolution_id,
                    replacement_asset_id=replacement_asset_id,
                    replacement_source_version=replacement_source_version,
                )
                for section in seed_sections
                if isinstance(section, dict)
            ]
        self._document_service.upsert_source_asset(
            source_asset.model_copy(
                update={"metadata": metadata, "updated_at": _utcnow()}
            )
        )
        self._deactivate_superseded_chunks(
            source_asset_id=source_asset.asset_id,
            evolution_id=evolution_id,
            replacement_asset_id=replacement_asset_id,
            replacement_source_version=replacement_source_version,
        )

    @staticmethod
    def _superseded_seed_section(
        *,
        section: dict[str, Any],
        evolution_id: str,
        replacement_asset_id: str,
        replacement_source_version: int,
    ) -> dict[str, Any]:
        updated = deepcopy(section)
        section_metadata = dict(updated.get("metadata") or {})
        section_metadata.update(
            {
                "lifecycle_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                "visibility_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                "superseded_by_source_asset_id": replacement_asset_id,
                "superseded_by_evolution_id": evolution_id,
                "superseded_by_source_version": replacement_source_version,
            }
        )
        updated["metadata"] = section_metadata
        return updated

    def _deactivate_superseded_chunks(
        self,
        *,
        source_asset_id: str,
        evolution_id: str,
        replacement_asset_id: str,
        replacement_source_version: int,
    ) -> None:
        chunks = list(
            self._session.exec(
                select(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.asset_id == source_asset_id
                )
            ).all()
        )
        chunk_ids: list[str] = []
        for chunk in chunks:
            chunk_ids.append(chunk.chunk_id)
            metadata = dict(chunk.metadata_json or {})
            metadata.update(
                {
                    "lifecycle_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                    "visibility_state": ARCHIVAL_LIFECYCLE_SUPERSEDED,
                    "superseded_by_source_asset_id": replacement_asset_id,
                    "superseded_by_evolution_id": evolution_id,
                    "superseded_by_source_version": replacement_source_version,
                }
            )
            chunk.metadata_json = metadata
            chunk.is_active = False
            self._session.add(chunk)
        if not chunk_ids:
            return
        embeddings = list(
            self._session.exec(
                select(EmbeddingRecordRecord).where(
                    EmbeddingRecordRecord.chunk_id.in_(chunk_ids)
                )
            ).all()
        )
        for embedding in embeddings:
            embedding.is_active = False
            embedding.updated_at = _utcnow()
            self._session.add(embedding)

    def _record_evolution_event(
        self,
        *,
        request: ArchivalEvolutionRequest,
        evolution_id: str,
        domain: str,
        new_asset_id: str,
        root_source_asset_id: str,
        new_source_version: int,
        superseded_source_asset_id: str,
        superseded_source_version: int,
        replacement_chunk_ids: list[str],
        reindex_job_id: str,
        selected_branch_head_ids: list[str],
        warnings: list[str],
    ) -> MemoryChangeEvent:
        source_refs = self._receipt_source_refs(
            request=request,
            new_asset_id=new_asset_id,
            new_source_version=new_source_version,
            replacement_chunk_ids=replacement_chunk_ids,
            reindex_job_id=reindex_job_id,
            event_id=None,
        )
        event = MemoryChangeEvent(
            event_id=f"archival_evolution_event_{uuid4().hex}",
            identity=request.identity,
            actor=request.actor,
            event_kind="archival_source_evolved",
            layer=ARCHIVAL_LAYER,
            domain=domain,
            block_id=f"{domain}.archival",
            entry_id=evolution_id,
            operation_kind="archival_evolution.evolve_source",
            source_refs=source_refs,
            dirty_targets=[
                MemoryDirtyTarget(
                    target_kind="retrieval_archival_index",
                    target_id=root_source_asset_id,
                    layer=ARCHIVAL_LAYER,
                    domain=domain,
                    block_id=f"{domain}.archival",
                    reason="archival_source_evolved",
                    metadata={
                        "evolution_id": evolution_id,
                        "new_source_asset_id": new_asset_id,
                        "superseded_source_asset_id": superseded_source_asset_id,
                        "new_source_version": new_source_version,
                        "superseded_source_version": superseded_source_version,
                        "reindex_job_id": reindex_job_id,
                        "replacement_chunk_ids": list(replacement_chunk_ids),
                    },
                )
            ],
            visibility_effect=request.visibility_scope.value,
            metadata={
                "evolution_id": evolution_id,
                "root_source_asset_id": root_source_asset_id,
                "new_source_asset_id": new_asset_id,
                "new_source_version": new_source_version,
                "superseded_source_asset_id": superseded_source_asset_id,
                "superseded_source_version": superseded_source_version,
                "visibility_scope": request.visibility_scope.value,
                "selected_branch_head_ids": list(selected_branch_head_ids),
                "replacement_chunk_ids": list(replacement_chunk_ids),
                "reindex_job_id": reindex_job_id,
                "warnings": list(warnings),
                "reason": request.reason,
            },
        )
        return self._memory_change_event_service.record_event(event)

    @staticmethod
    def _receipt_source_refs(
        *,
        request: ArchivalEvolutionRequest,
        new_asset_id: str,
        new_source_version: int,
        replacement_chunk_ids: list[str],
        reindex_job_id: str,
        event_id: str | None,
    ) -> list[MemorySourceRef]:
        refs = [
            *request.source_refs,
            MemorySourceRef(
                source_type="archival_source_asset",
                source_id=new_asset_id,
                layer=ARCHIVAL_LAYER,
                revision=new_source_version,
                metadata={"source_version": new_source_version},
            ),
            MemorySourceRef(
                source_type="retrieval_index_job",
                source_id=reindex_job_id,
                layer="retrieval_core",
                metadata={"job_kind": "reindex"},
            ),
        ]
        refs.extend(
            MemorySourceRef(
                source_type="archival_chunk",
                source_id=chunk_id,
                layer=ARCHIVAL_LAYER,
                revision=new_source_version,
                metadata={
                    "source_asset_id": new_asset_id,
                    "source_version": new_source_version,
                },
            )
            for chunk_id in replacement_chunk_ids
        )
        if event_id is not None:
            refs.append(
                MemorySourceRef(
                    source_type="memory_change_event",
                    source_id=event_id,
                    layer=ARCHIVAL_LAYER,
                    metadata={"event_kind": "archival_source_evolved"},
                )
            )
        return _dedupe_source_refs(refs)

    @staticmethod
    def _first_section_excerpt(
        sections: Sequence[ArchivalEvolutionSection],
    ) -> str | None:
        for section in sections:
            text = section.text.strip()
            if text:
                return text[:280]
        return None


def _source_version(metadata: Mapping[str, Any]) -> int:
    for key in ("source_version", "source_asset_version"):
        raw_value = metadata.get(key)
        if raw_value is None:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 1


def _dedupe_text_values(values: Sequence[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values


def _dedupe_source_refs(refs: Sequence[MemorySourceRef]) -> list[MemorySourceRef]:
    deduped: list[MemorySourceRef] = []
    seen: set[tuple[str, str, int | None]] = set()
    for ref in refs:
        key = (ref.source_type.casefold(), ref.source_id.casefold(), ref.revision)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped
