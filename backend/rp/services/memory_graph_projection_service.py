"""Read/write inspection service for RP Memory Graph Projection."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_retrieval_store import (
    KnowledgeChunkRecord,
    MemoryGraphEdgeRecord,
    MemoryGraphEvidenceRecord,
    MemoryGraphExtractionJobRecord,
    MemoryGraphNodeRecord,
    SourceAssetRecord,
)
from rp.models.memory_graph_projection import (
    GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
    GRAPH_ERROR_MODEL_CONFIG_MISSING,
    GRAPH_EXTRACTION_SCHEMA_VERSION,
    GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    GRAPH_JOB_REASON_MANUAL_REBUILD,
    GRAPH_JOB_REASON_MANUAL_RETRY,
    GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED,
    GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED,
    GRAPH_JOB_STATUS_COMPLETED,
    GRAPH_JOB_STATUS_FAILED,
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_JOB_STATUS_RUNNING,
    GRAPH_JOB_STATUS_CANCELLED,
    GRAPH_JOB_STATUS_SKIPPED,
    GRAPH_SOURCE_LAYER_ARCHIVAL,
    GRAPH_TAXONOMY_VERSION,
    GRAPH_WARNING_NEIGHBORHOOD_TRUNCATED,
    MemoryGraphEdgeListResponse,
    MemoryGraphEdgeUpsert,
    MemoryGraphEdgeView,
    MemoryGraphEvidenceListResponse,
    MemoryGraphEvidenceUpsert,
    MemoryGraphEvidenceView,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphExtractionJobView,
    MemoryGraphMaintenanceSnapshot,
    MemoryGraphNeighborhoodResponse,
    MemoryGraphNodeListResponse,
    MemoryGraphNodeUpsert,
    MemoryGraphNodeView,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig
from .memory_graph_projection_repository import MemoryGraphProjectionRepository
from .retrieval_runtime_config_service import RetrievalRuntimeConfigService


@dataclass(frozen=True)
class _GraphExtractionSourceCandidate:
    source_asset_id: str
    chunk_id: str | None
    section_id: str | None
    workspace_id: str | None
    commit_id: str | None
    source_fingerprint: str


class MemoryGraphProjectionService:
    """Storage-neutral graph projection boundary for retrieval maintenance and inspection."""

    _DEFAULT_LIST_LIMIT = 100
    _DEFAULT_JOB_LIMIT = 10
    _DEFAULT_MAX_DEPTH = 1
    _MAX_DEPTH_CAP = 2
    _DEFAULT_MAX_NODES = 50
    _DEFAULT_MAX_EDGES = 75

    def __init__(
        self,
        session: Session,
        *,
        repository: MemoryGraphProjectionRepository | None = None,
        runtime_config_service: RetrievalRuntimeConfigService | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or MemoryGraphProjectionRepository(session)
        self._runtime_config_service = (
            runtime_config_service or RetrievalRuntimeConfigService(session)
        )

    def upsert_seed_graph(
        self,
        *,
        story_id: str,
        nodes: list[MemoryGraphNodeUpsert] | None = None,
        edges: list[MemoryGraphEdgeUpsert] | None = None,
        evidence: list[MemoryGraphEvidenceUpsert] | None = None,
        jobs: list[MemoryGraphExtractionJobUpsert] | None = None,
    ) -> MemoryGraphNeighborhoodResponse:
        """Insert deterministic graph rows for tests, eval fixtures, or manual inspection."""

        for node in nodes or []:
            self._repository.upsert_node(story_id=story_id, node=node)
        for edge in edges or []:
            self._repository.upsert_edge(story_id=story_id, edge=edge)
        for item in evidence or []:
            self._repository.upsert_evidence(story_id=story_id, evidence=item)
        for job in jobs or []:
            self._repository.upsert_job(story_id=story_id, job=job)
        self._session.flush()
        anchor = nodes[0].node_id if nodes else None
        return self.get_neighborhood(story_id=story_id, node_id=anchor)

    def get_maintenance_snapshot(
        self,
        *,
        story_id: str,
    ) -> MemoryGraphMaintenanceSnapshot:
        config = self._runtime_config_service.resolve_story_config(story_id=story_id)
        config_ref = self._model_config_ref(config)
        maintenance_warnings = []
        if config.graph_extraction_enabled and not config.graph_extraction_configured:
            maintenance_warnings.append(GRAPH_ERROR_MODEL_CONFIG_MISSING)

        jobs = self._repository.list_jobs(story_id=story_id, limit=None)
        status_counts = Counter(job.status for job in jobs)
        warning_counts: Counter[str] = Counter()
        error_counts: Counter[str] = Counter()
        for job in jobs:
            warning_counts.update(job.warning_codes_json or [])
            if job.error_code:
                error_counts.update([job.error_code])

        return MemoryGraphMaintenanceSnapshot(
            story_id=story_id,
            graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
            graph_extraction_enabled=config.graph_extraction_enabled,
            graph_extraction_configured=config.graph_extraction_configured,
            graph_extraction_model_config_ref=config_ref,
            graph_extraction_provider_id=config.graph_extraction_provider_id,
            graph_extraction_model_id=config.graph_extraction_model_id,
            maintenance_warnings=maintenance_warnings,
            source_layers=self._repository.list_source_layers(story_id=story_id),
            node_count=self._repository.count_nodes(story_id=story_id),
            edge_count=self._repository.count_edges(story_id=story_id),
            evidence_count=self._repository.count_evidence(story_id=story_id),
            job_count=len(jobs),
            queued_job_count=status_counts[GRAPH_JOB_STATUS_QUEUED],
            running_job_count=status_counts[GRAPH_JOB_STATUS_RUNNING],
            completed_job_count=status_counts[GRAPH_JOB_STATUS_COMPLETED],
            failed_job_count=status_counts[GRAPH_JOB_STATUS_FAILED],
            skipped_job_count=status_counts[GRAPH_JOB_STATUS_SKIPPED],
            cancelled_job_count=status_counts[GRAPH_JOB_STATUS_CANCELLED],
            retryable_job_ids=[
                job.graph_job_id for job in jobs if self._is_retryable_failed_job(job)
            ],
            warning_code_counts=dict(sorted(warning_counts.items())),
            error_code_counts=dict(sorted(error_counts.items())),
            recent_jobs=[
                self._job_to_view(job)
                for job in self._repository.list_jobs(
                    story_id=story_id,
                    limit=self._DEFAULT_JOB_LIMIT,
                )
            ],
        )

    def list_nodes(
        self,
        *,
        story_id: str,
        entity_types: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_statuses: list[str] | None = None,
        limit: int | None = None,
    ) -> MemoryGraphNodeListResponse:
        resolved_limit = self._DEFAULT_LIST_LIMIT if limit is None else limit
        records = self._repository.list_nodes(
            story_id=story_id,
            entity_types=entity_types,
            source_layers=source_layers,
            source_statuses=source_statuses,
            limit=resolved_limit,
        )
        return MemoryGraphNodeListResponse(
            story_id=story_id,
            graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
            source_layer=self._response_source_layer(source_layers, records),
            data=[self._node_to_view(record) for record in records],
        )

    def list_edges(
        self,
        *,
        story_id: str,
        relation_types: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_statuses: list[str] | None = None,
        node_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> MemoryGraphEdgeListResponse:
        resolved_limit = self._DEFAULT_LIST_LIMIT if limit is None else limit
        records = self._repository.list_edges(
            story_id=story_id,
            relation_types=relation_types,
            source_layers=source_layers,
            source_statuses=source_statuses,
            node_ids=node_ids,
            limit=resolved_limit,
        )
        evidence_counts = self._repository.evidence_count_by_edge_ids(
            story_id=story_id,
            edge_ids=[record.edge_id for record in records],
        )
        return MemoryGraphEdgeListResponse(
            story_id=story_id,
            graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
            source_layer=self._response_source_layer(source_layers, records),
            data=[
                self._edge_to_view(record, evidence_counts=evidence_counts)
                for record in records
            ],
        )

    def list_evidence(
        self,
        *,
        story_id: str,
        node_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_asset_ids: list[str] | None = None,
        chunk_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> MemoryGraphEvidenceListResponse:
        resolved_limit = self._DEFAULT_LIST_LIMIT if limit is None else limit
        records = self._repository.list_evidence(
            story_id=story_id,
            node_ids=node_ids,
            edge_ids=edge_ids,
            source_layers=source_layers,
            source_asset_ids=source_asset_ids,
            chunk_ids=chunk_ids,
            limit=resolved_limit,
        )
        return MemoryGraphEvidenceListResponse(
            story_id=story_id,
            graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
            source_layer=self._response_source_layer(source_layers, records),
            data=[self._evidence_to_view(record) for record in records],
        )

    def get_neighborhood(
        self,
        *,
        story_id: str,
        node_id: str | None,
        max_depth: int | None = None,
        max_nodes: int | None = None,
        max_edges: int | None = None,
        entity_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_statuses: list[str] | None = None,
    ) -> MemoryGraphNeighborhoodResponse:
        depth = min(
            max(
                int(max_depth if max_depth is not None else self._DEFAULT_MAX_DEPTH), 0
            ),
            self._MAX_DEPTH_CAP,
        )
        node_cap = max(
            int(max_nodes if max_nodes is not None else self._DEFAULT_MAX_NODES), 0
        )
        edge_cap = max(
            int(max_edges if max_edges is not None else self._DEFAULT_MAX_EDGES), 0
        )
        if not node_id:
            return MemoryGraphNeighborhoodResponse(
                story_id=story_id,
                graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
                source_layer=self._single_filter_value(source_layers),
                anchor_node_id=None,
                max_depth=depth,
                warnings=["graph_neighborhood_anchor_missing"],
            )

        anchor = self._repository.get_node(story_id=story_id, node_id=node_id)
        if anchor is None:
            return MemoryGraphNeighborhoodResponse(
                story_id=story_id,
                graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
                source_layer=self._single_filter_value(source_layers),
                anchor_node_id=node_id,
                max_depth=depth,
                warnings=["graph_neighborhood_anchor_not_found"],
            )

        visited_node_ids: set[str] = {node_id}
        selected_edge_ids: set[str] = set()
        frontier: set[str] = {node_id}
        truncated = False

        for _ in range(depth):
            if not frontier or len(selected_edge_ids) >= edge_cap:
                break
            candidate_edges = self._repository.list_edges(
                story_id=story_id,
                node_ids=sorted(frontier),
                relation_types=relation_types,
                source_layers=source_layers,
                source_statuses=source_statuses,
                limit=None,
            )
            next_frontier: set[str] = set()
            for edge in candidate_edges:
                if edge.edge_id in selected_edge_ids:
                    continue
                if len(selected_edge_ids) >= edge_cap:
                    truncated = True
                    break
                selected_edge_ids.add(edge.edge_id)
                for candidate_node_id in (edge.source_node_id, edge.target_node_id):
                    if candidate_node_id in visited_node_ids:
                        continue
                    if len(visited_node_ids) >= node_cap:
                        truncated = True
                        continue
                    visited_node_ids.add(candidate_node_id)
                    next_frontier.add(candidate_node_id)
            frontier = next_frontier

        node_records = self._repository.list_nodes(
            story_id=story_id,
            node_ids=sorted(visited_node_ids),
            entity_types=entity_types,
            source_layers=source_layers,
            source_statuses=source_statuses,
            limit=None,
        )
        retained_node_ids = {record.node_id for record in node_records}
        edge_records = [
            edge
            for edge in self._repository.list_edges(
                story_id=story_id,
                edge_ids=sorted(selected_edge_ids),
                relation_types=relation_types,
                source_layers=source_layers,
                source_statuses=source_statuses,
                limit=None,
            )
            if edge.source_node_id in retained_node_ids
            and edge.target_node_id in retained_node_ids
        ]
        evidence_records = self._repository.list_evidence(
            story_id=story_id,
            node_ids=sorted(retained_node_ids),
            edge_ids=[edge.edge_id for edge in edge_records],
            source_layers=source_layers,
            limit=None,
        )
        evidence_counts = self._repository.evidence_count_by_edge_ids(
            story_id=story_id,
            edge_ids=[edge.edge_id for edge in edge_records],
        )
        warnings = [GRAPH_WARNING_NEIGHBORHOOD_TRUNCATED] if truncated else []
        return MemoryGraphNeighborhoodResponse(
            story_id=story_id,
            graph_backend=GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT,
            source_layer=self._response_source_layer(
                source_layers,
                [*node_records, *edge_records, *evidence_records],
            ),
            anchor_node_id=node_id,
            max_depth=depth,
            truncated=truncated,
            warnings=warnings,
            nodes=[self._node_to_view(record) for record in node_records],
            edges=[
                self._edge_to_view(record, evidence_counts=evidence_counts)
                for record in edge_records
            ],
            evidence=[self._evidence_to_view(record) for record in evidence_records],
        )

    def queue_archival_extraction_jobs(
        self,
        *,
        story_id: str,
        source_asset_ids: list[str],
        workspace_id: str | None = None,
        commit_id: str | None = None,
        queued_reason: str | None = GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
        extraction_schema_version: str = GRAPH_EXTRACTION_SCHEMA_VERSION,
        taxonomy_version: str = GRAPH_TAXONOMY_VERSION,
    ) -> list[MemoryGraphExtractionJobView]:
        """Queue graph maintenance jobs only; G2 deliberately does not run extraction."""

        config = self._runtime_config_service.resolve_story_config(story_id=story_id)
        if not config.graph_extraction_enabled:
            return []

        candidates = self._build_archival_source_candidates(
            story_id=story_id,
            source_asset_ids=source_asset_ids,
            workspace_id=workspace_id,
            commit_id=commit_id,
        )
        jobs: list[MemoryGraphExtractionJobView] = []
        for candidate in candidates:
            jobs.append(
                self._queue_candidate_job(
                    story_id=story_id,
                    candidate=candidate,
                    config=config,
                    queued_reason=queued_reason,
                    extraction_schema_version=extraction_schema_version,
                    taxonomy_version=taxonomy_version,
                )
            )
        self._session.flush()
        return jobs

    def rebuild_story_graph(
        self,
        *,
        story_id: str,
        source_asset_ids: list[str] | None = None,
        workspace_id: str | None = None,
        commit_id: str | None = None,
        queued_reason: str = GRAPH_JOB_REASON_MANUAL_REBUILD,
        extraction_schema_version: str = GRAPH_EXTRACTION_SCHEMA_VERSION,
        taxonomy_version: str = GRAPH_TAXONOMY_VERSION,
    ) -> list[MemoryGraphExtractionJobView]:
        """Queue a manual graph rebuild against current archival source material."""

        reason = queued_reason or GRAPH_JOB_REASON_MANUAL_REBUILD
        if reason not in {
            GRAPH_JOB_REASON_MANUAL_REBUILD,
            GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED,
            GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED,
        }:
            raise ValueError(f"Unsupported graph rebuild queued_reason: {reason!r}")
        asset_ids = source_asset_ids or self._list_archival_source_asset_ids(
            story_id=story_id,
            workspace_id=workspace_id,
            commit_id=commit_id,
        )
        return self.queue_archival_extraction_jobs(
            story_id=story_id,
            source_asset_ids=asset_ids,
            workspace_id=workspace_id,
            commit_id=commit_id,
            queued_reason=reason,
            extraction_schema_version=extraction_schema_version,
            taxonomy_version=taxonomy_version,
        )

    def retry_failed_jobs(
        self,
        *,
        story_id: str,
        limit: int | None = None,
    ) -> list[MemoryGraphExtractionJobView]:
        """Queue retry rows for failed graph jobs without running extraction."""

        resolved_limit = 20 if limit is None else max(int(limit), 0)
        failed_jobs = self._repository.list_jobs(
            story_id=story_id,
            statuses=[GRAPH_JOB_STATUS_FAILED],
            limit=None,
        )
        retryable_jobs = [
            job for job in failed_jobs if self._is_retryable_failed_job(job)
        ][:resolved_limit]
        retry_jobs: list[MemoryGraphExtractionJobView] = []
        config = self._runtime_config_service.resolve_story_config(story_id=story_id)
        for failed in retryable_jobs:
            candidate = self._candidate_from_failed_job(failed)
            retry_jobs.append(
                self._queue_candidate_job(
                    story_id=story_id,
                    candidate=candidate,
                    config=config,
                    queued_reason=GRAPH_JOB_REASON_MANUAL_RETRY,
                    extraction_schema_version=failed.extraction_schema_version,
                    taxonomy_version=failed.taxonomy_version,
                    attempt_count=int(failed.attempt_count or 0) + 1,
                )
            )
        self._session.flush()
        return retry_jobs

    def _queue_candidate_job(
        self,
        *,
        story_id: str,
        candidate: _GraphExtractionSourceCandidate,
        config: RetrievalRuntimeConfig,
        queued_reason: str | None,
        extraction_schema_version: str,
        taxonomy_version: str,
        attempt_count: int = 0,
    ) -> MemoryGraphExtractionJobView:
        model_config_ref = self._model_config_ref(config)
        status = GRAPH_JOB_STATUS_QUEUED
        error_code = None
        error_message = None
        if not config.graph_extraction_configured:
            status = GRAPH_JOB_STATUS_FAILED
            error_code = GRAPH_ERROR_MODEL_CONFIG_MISSING
            error_message = (
                "Graph extraction provider/model is not configured for this story."
            )

        job = MemoryGraphExtractionJobUpsert(
            graph_job_id=f"graph_job_{uuid4().hex}",
            workspace_id=candidate.workspace_id,
            commit_id=candidate.commit_id,
            source_layer=GRAPH_SOURCE_LAYER_ARCHIVAL,
            source_asset_id=candidate.source_asset_id,
            chunk_id=candidate.chunk_id,
            section_id=candidate.section_id,
            input_fingerprint=self._input_fingerprint(
                source_fingerprint=candidate.source_fingerprint,
                model_config_ref=model_config_ref,
                extraction_schema_version=extraction_schema_version,
                taxonomy_version=taxonomy_version,
            ),
            status=status,
            attempt_count=attempt_count,
            model_config_ref=model_config_ref,
            provider_id=config.graph_extraction_provider_id,
            model_id=config.graph_extraction_model_id,
            extraction_schema_version=extraction_schema_version,
            taxonomy_version=taxonomy_version,
            error_code=error_code,
            error_message=error_message,
            queued_reason=queued_reason,
        )
        record = self._repository.upsert_job(story_id=story_id, job=job)
        return self._job_to_view(record)

    def _build_archival_source_candidates(
        self,
        *,
        story_id: str,
        source_asset_ids: list[str],
        workspace_id: str | None,
        commit_id: str | None,
    ) -> list[_GraphExtractionSourceCandidate]:
        asset_records = self._list_archival_source_asset_records(
            story_id=story_id,
            source_asset_ids=source_asset_ids,
            workspace_id=workspace_id,
            commit_id=commit_id,
        )
        asset_map = {record.asset_id: record for record in asset_records}
        if not asset_map:
            return []

        chunks = self._list_active_chunks(
            story_id=story_id,
            source_asset_ids=list(asset_map),
        )
        candidates: list[_GraphExtractionSourceCandidate] = []
        chunk_asset_ids: set[str] = set()
        for chunk in chunks:
            asset = asset_map.get(chunk.asset_id)
            if asset is None:
                continue
            chunk_asset_ids.add(chunk.asset_id)
            metadata = dict(chunk.metadata_json or {})
            section_id = self._metadata_section_id(metadata)
            candidates.append(
                _GraphExtractionSourceCandidate(
                    source_asset_id=chunk.asset_id,
                    chunk_id=chunk.chunk_id,
                    section_id=section_id,
                    workspace_id=asset.workspace_id,
                    commit_id=asset.commit_id,
                    source_fingerprint=self._hash_json(
                        {
                            "kind": "chunk",
                            "story_id": story_id,
                            "source_asset_id": chunk.asset_id,
                            "chunk_id": chunk.chunk_id,
                            "section_id": section_id,
                            "domain": chunk.domain,
                            "domain_path": chunk.domain_path,
                            "title": chunk.title,
                            "text": chunk.text,
                            "metadata": metadata,
                            "provenance_refs": list(chunk.provenance_refs_json or []),
                        }
                    ),
                )
            )

        for asset in asset_records:
            if asset.asset_id in chunk_asset_ids:
                continue
            candidates.append(self._candidate_from_asset_record(story_id, asset))
        return candidates

    def _candidate_from_failed_job(
        self,
        failed: MemoryGraphExtractionJobRecord,
    ) -> _GraphExtractionSourceCandidate:
        if failed.chunk_id:
            chunk = self._session.get(KnowledgeChunkRecord, failed.chunk_id)
            if chunk is not None:
                asset = self._session.get(SourceAssetRecord, chunk.asset_id)
                if asset is not None:
                    return self._candidate_from_chunk_record(chunk=chunk, asset=asset)

        asset = (
            self._session.get(SourceAssetRecord, failed.source_asset_id)
            if failed.source_asset_id
            else None
        )
        if asset is not None:
            return self._candidate_from_asset_record(failed.story_id, asset)

        return _GraphExtractionSourceCandidate(
            source_asset_id=str(failed.source_asset_id),
            chunk_id=failed.chunk_id,
            section_id=failed.section_id,
            workspace_id=failed.workspace_id,
            commit_id=failed.commit_id,
            source_fingerprint=f"previous:{failed.input_fingerprint}",
        )

    def _candidate_from_chunk_record(
        self,
        *,
        chunk: KnowledgeChunkRecord,
        asset: SourceAssetRecord,
    ) -> _GraphExtractionSourceCandidate:
        metadata = dict(chunk.metadata_json or {})
        section_id = self._metadata_section_id(metadata)
        return _GraphExtractionSourceCandidate(
            source_asset_id=chunk.asset_id,
            chunk_id=chunk.chunk_id,
            section_id=section_id,
            workspace_id=asset.workspace_id,
            commit_id=asset.commit_id,
            source_fingerprint=self._hash_json(
                {
                    "kind": "chunk",
                    "story_id": chunk.story_id,
                    "source_asset_id": chunk.asset_id,
                    "chunk_id": chunk.chunk_id,
                    "section_id": section_id,
                    "domain": chunk.domain,
                    "domain_path": chunk.domain_path,
                    "title": chunk.title,
                    "text": chunk.text,
                    "metadata": metadata,
                    "provenance_refs": list(chunk.provenance_refs_json or []),
                }
            ),
        )

    def _candidate_from_asset_record(
        self,
        story_id: str,
        asset: SourceAssetRecord,
    ) -> _GraphExtractionSourceCandidate:
        metadata = dict(asset.metadata_json or {})
        return _GraphExtractionSourceCandidate(
            source_asset_id=asset.asset_id,
            chunk_id=None,
            section_id=None,
            workspace_id=asset.workspace_id,
            commit_id=asset.commit_id,
            source_fingerprint=self._hash_json(
                {
                    "kind": "asset",
                    "story_id": story_id,
                    "source_asset_id": asset.asset_id,
                    "source_ref": asset.source_ref,
                    "title": asset.title,
                    "raw_excerpt": asset.raw_excerpt,
                    "metadata": metadata,
                }
            ),
        )

    def _list_archival_source_asset_ids(
        self,
        *,
        story_id: str,
        workspace_id: str | None,
        commit_id: str | None,
    ) -> list[str]:
        return [
            record.asset_id
            for record in self._list_archival_source_asset_records(
                story_id=story_id,
                source_asset_ids=None,
                workspace_id=workspace_id,
                commit_id=commit_id,
            )
        ]

    def _list_archival_source_asset_records(
        self,
        *,
        story_id: str,
        source_asset_ids: list[str] | None,
        workspace_id: str | None,
        commit_id: str | None,
    ) -> list[SourceAssetRecord]:
        stmt = select(SourceAssetRecord).where(SourceAssetRecord.story_id == story_id)
        asset_ids = list(dict.fromkeys(source_asset_ids or []))
        if asset_ids:
            stmt = stmt.where(SourceAssetRecord.asset_id.in_(asset_ids))
        if workspace_id is not None:
            stmt = stmt.where(SourceAssetRecord.workspace_id == workspace_id)
        if commit_id is not None:
            stmt = stmt.where(SourceAssetRecord.commit_id == commit_id)
        stmt = stmt.order_by(SourceAssetRecord.asset_id.asc())
        return [
            record
            for record in self._session.exec(stmt).all()
            if self._asset_is_archival(record)
        ]

    def _list_active_chunks(
        self,
        *,
        story_id: str,
        source_asset_ids: list[str],
    ) -> list[KnowledgeChunkRecord]:
        if not source_asset_ids:
            return []
        stmt = (
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.story_id == story_id)
            .where(KnowledgeChunkRecord.asset_id.in_(source_asset_ids))
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
            .order_by(
                KnowledgeChunkRecord.asset_id.asc(),
                KnowledgeChunkRecord.chunk_index.asc(),
                KnowledgeChunkRecord.chunk_id.asc(),
            )
        )
        return list(self._session.exec(stmt).all())

    @staticmethod
    def _asset_is_archival(record: SourceAssetRecord) -> bool:
        metadata = dict(record.metadata_json or {})
        return (
            metadata.get("layer") == GRAPH_SOURCE_LAYER_ARCHIVAL
            or metadata.get("materialized_to_archival") is True
            or (record.collection_id or "").endswith(":archival")
        )

    @staticmethod
    def _metadata_section_id(metadata: dict) -> str | None:
        for key in ("section_id", "parent_section_id", "source_section_id"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    @classmethod
    def _model_config_ref(cls, config: RetrievalRuntimeConfig) -> str:
        return (
            "graph_extraction:"
            + cls._hash_json(
                {
                    "provider_id": config.graph_extraction_provider_id,
                    "model_id": config.graph_extraction_model_id,
                    "structured_output_mode": (
                        config.graph_extraction_structured_output_mode
                    ),
                    "temperature": config.graph_extraction_temperature,
                    "max_output_tokens": config.graph_extraction_max_output_tokens,
                    "timeout_ms": config.graph_extraction_timeout_ms,
                    "retry_policy": config.graph_extraction_retry_policy.model_dump(
                        mode="json"
                    ),
                    "fallback_model_ref": config.graph_extraction_fallback_model_ref,
                    "enabled": config.graph_extraction_enabled,
                }
            )[:16]
        )

    @classmethod
    def _input_fingerprint(
        cls,
        *,
        source_fingerprint: str,
        model_config_ref: str,
        extraction_schema_version: str,
        taxonomy_version: str,
    ) -> str:
        return "graph_input:" + cls._hash_json(
            {
                "source_fingerprint": source_fingerprint,
                "model_config_ref": model_config_ref,
                "extraction_schema_version": extraction_schema_version,
                "taxonomy_version": taxonomy_version,
            }
        )

    @staticmethod
    def _hash_json(payload: dict) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_retryable_failed_job(job: MemoryGraphExtractionJobRecord) -> bool:
        return job.status == GRAPH_JOB_STATUS_FAILED and bool(job.source_asset_id)

    @staticmethod
    def _node_to_view(record: MemoryGraphNodeRecord) -> MemoryGraphNodeView:
        return MemoryGraphNodeView(
            id=record.node_id,
            label=record.canonical_name,
            type=record.entity_type,
            story_id=record.story_id,
            workspace_id=record.workspace_id,
            session_id=record.session_id,
            source_layer=record.source_layer,
            source_status=record.source_status,
            confidence=record.confidence,
            aliases=list(record.aliases_json or []),
            description=record.description,
            first_seen_source_ref=record.first_seen_source_ref,
            entity_schema_version=record.entity_schema_version,
            normalization_key=record.normalization_key,
            metadata=dict(record.metadata_json or {}),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _edge_to_view(
        record: MemoryGraphEdgeRecord,
        *,
        evidence_counts: dict[str, int],
    ) -> MemoryGraphEdgeView:
        return MemoryGraphEdgeView(
            id=record.edge_id,
            story_id=record.story_id,
            workspace_id=record.workspace_id,
            session_id=record.session_id,
            source=record.source_node_id,
            target=record.target_node_id,
            source_entity_name=record.source_entity_name,
            target_entity_name=record.target_entity_name,
            label=record.relation_type,
            relation_family=record.relation_family,
            relation_schema_version=record.relation_schema_version,
            raw_relation_text=record.raw_relation_text,
            source_layer=record.source_layer,
            source_status=record.source_status,
            confidence=record.confidence,
            direction=record.direction,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            branch_id=record.branch_id,
            canon_status=record.canon_status,
            evidence_count=int(evidence_counts.get(record.edge_id, 0)),
            metadata=dict(record.metadata_json or {}),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _evidence_to_view(record: MemoryGraphEvidenceRecord) -> MemoryGraphEvidenceView:
        return MemoryGraphEvidenceView(
            id=record.evidence_id,
            story_id=record.story_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            edge_id=record.edge_id,
            source_layer=record.source_layer,
            source_family=record.source_family,
            source_type=record.source_type,
            import_event=record.import_event,
            source_ref=record.source_ref,
            source_asset_id=record.source_asset_id,
            collection_id=record.collection_id,
            parsed_document_id=record.parsed_document_id,
            chunk_id=record.chunk_id,
            section_id=record.section_id,
            domain=record.domain,
            domain_path=record.domain_path,
            commit_id=record.commit_id,
            step_id=record.step_id,
            char_start=record.char_start,
            char_end=record.char_end,
            excerpt=record.evidence_excerpt,
            metadata=dict(record.metadata_json or {}),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _job_to_view(
        record: MemoryGraphExtractionJobRecord,
    ) -> MemoryGraphExtractionJobView:
        return MemoryGraphExtractionJobView(
            graph_job_id=record.graph_job_id,
            story_id=record.story_id,
            workspace_id=record.workspace_id,
            session_id=record.session_id,
            commit_id=record.commit_id,
            source_layer=record.source_layer,
            source_asset_id=record.source_asset_id,
            chunk_id=record.chunk_id,
            section_id=record.section_id,
            input_fingerprint=record.input_fingerprint,
            status=record.status,
            attempt_count=record.attempt_count,
            model_config_ref=record.model_config_ref,
            provider_id=record.provider_id,
            model_id=record.model_id,
            extraction_schema_version=record.extraction_schema_version,
            taxonomy_version=record.taxonomy_version,
            token_usage=dict(record.token_usage_json or {}),
            warning_codes=list(record.warning_codes_json or []),
            error_code=record.error_code,
            error_message=record.error_message,
            queued_reason=record.queued_reason,
            retry_after=record.retry_after,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _single_filter_value(values: list[str] | None) -> str | None:
        normalized = [str(value) for value in values or [] if str(value)]
        if len(normalized) == 1:
            return normalized[0]
        return None

    @classmethod
    def _response_source_layer(cls, values: list[str] | None, records) -> str | None:
        filter_layer = cls._single_filter_value(values)
        if filter_layer is not None:
            return filter_layer
        layers = {
            str(getattr(record, "source_layer", ""))
            for record in records
            if getattr(record, "source_layer", None)
        }
        if len(layers) == 1:
            return next(iter(layers))
        return None
