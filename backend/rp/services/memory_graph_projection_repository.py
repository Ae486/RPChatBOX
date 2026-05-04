"""SQLModel-backed repository for RP Memory Graph Projection rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import or_
from sqlmodel import Session, select

from models.rp_retrieval_store import (
    MemoryGraphEdgeRecord,
    MemoryGraphEvidenceRecord,
    MemoryGraphExtractionJobRecord,
    MemoryGraphNodeRecord,
)
from rp.models.memory_graph_projection import (
    GRAPH_CANON_STATUSES,
    GRAPH_EDGE_DIRECTIONS,
    GRAPH_ERROR_CODES,
    GRAPH_JOB_QUEUED_REASONS,
    GRAPH_JOB_STATUSES,
    GRAPH_RELATION_FAMILIES,
    GRAPH_SOURCE_LAYERS,
    GRAPH_SOURCE_STATUSES,
    GRAPH_WARNING_CODES,
    MemoryGraphEdgeUpsert,
    MemoryGraphEvidenceUpsert,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphNodeUpsert,
    validate_graph_constant,
    validate_graph_entity_type,
    validate_graph_relation_type,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    return list(dict.fromkeys(str(value) for value in values if str(value)))


class MemoryGraphProjectionRepository:
    """Persist and inspect the PostgreSQL-lightweight graph projection tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_node(
        self,
        *,
        story_id: str,
        node: MemoryGraphNodeUpsert,
    ) -> MemoryGraphNodeRecord:
        self._validate_node(node)
        now = _utcnow()
        record = self._session.get(MemoryGraphNodeRecord, node.node_id)
        payload = {
            "story_id": story_id,
            "workspace_id": node.workspace_id,
            "session_id": node.session_id,
            "source_layer": node.source_layer,
            "entity_type": node.entity_type,
            "canonical_name": node.canonical_name,
            "aliases_json": list(node.aliases),
            "description": node.description,
            "source_status": node.source_status,
            "confidence": node.confidence,
            "first_seen_source_ref": node.first_seen_source_ref,
            "entity_schema_version": node.entity_schema_version,
            "normalization_key": node.normalization_key,
            "metadata_json": dict(node.metadata),
            "updated_at": now,
        }
        if record is None:
            record = MemoryGraphNodeRecord(
                node_id=node.node_id,
                created_at=now,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        self._session.flush()
        return record

    def upsert_edge(
        self,
        *,
        story_id: str,
        edge: MemoryGraphEdgeUpsert,
    ) -> MemoryGraphEdgeRecord:
        self._validate_edge(edge)
        now = _utcnow()
        record = self._session.get(MemoryGraphEdgeRecord, edge.edge_id)
        payload = {
            "story_id": story_id,
            "workspace_id": edge.workspace_id,
            "session_id": edge.session_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "source_entity_name": edge.source_entity_name,
            "target_entity_name": edge.target_entity_name,
            "relation_type": edge.relation_type,
            "relation_family": edge.relation_family,
            "relation_schema_version": edge.relation_schema_version,
            "raw_relation_text": edge.raw_relation_text,
            "source_layer": edge.source_layer,
            "source_status": edge.source_status,
            "confidence": edge.confidence,
            "direction": edge.direction,
            "valid_from": edge.valid_from,
            "valid_to": edge.valid_to,
            "branch_id": edge.branch_id,
            "canon_status": edge.canon_status,
            "metadata_json": dict(edge.metadata),
            "updated_at": now,
        }
        if record is None:
            record = MemoryGraphEdgeRecord(
                edge_id=edge.edge_id,
                created_at=now,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        self._session.flush()
        return record

    def upsert_evidence(
        self,
        *,
        story_id: str,
        evidence: MemoryGraphEvidenceUpsert,
    ) -> MemoryGraphEvidenceRecord:
        self._validate_evidence(evidence)
        now = _utcnow()
        record = self._session.get(MemoryGraphEvidenceRecord, evidence.evidence_id)
        payload = {
            "story_id": story_id,
            "workspace_id": evidence.workspace_id,
            "node_id": evidence.node_id,
            "edge_id": evidence.edge_id,
            "source_layer": evidence.source_layer,
            "source_family": evidence.source_family,
            "source_type": evidence.source_type,
            "import_event": evidence.import_event,
            "source_ref": evidence.source_ref,
            "source_asset_id": evidence.source_asset_id,
            "collection_id": evidence.collection_id,
            "parsed_document_id": evidence.parsed_document_id,
            "chunk_id": evidence.chunk_id,
            "section_id": evidence.section_id,
            "domain": evidence.domain,
            "domain_path": evidence.domain_path,
            "commit_id": evidence.commit_id,
            "step_id": evidence.step_id,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
            "evidence_excerpt": evidence.evidence_excerpt,
            "metadata_json": dict(evidence.metadata),
            "updated_at": now,
        }
        if record is None:
            record = MemoryGraphEvidenceRecord(
                evidence_id=evidence.evidence_id,
                created_at=now,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        self._session.flush()
        return record

    def upsert_job(
        self,
        *,
        story_id: str,
        job: MemoryGraphExtractionJobUpsert,
    ) -> MemoryGraphExtractionJobRecord:
        self._validate_job(job)
        now = _utcnow()
        record = self._session.get(MemoryGraphExtractionJobRecord, job.graph_job_id)
        payload = {
            "story_id": story_id,
            "workspace_id": job.workspace_id,
            "session_id": job.session_id,
            "commit_id": job.commit_id,
            "source_layer": job.source_layer,
            "source_asset_id": job.source_asset_id,
            "chunk_id": job.chunk_id,
            "section_id": job.section_id,
            "input_fingerprint": job.input_fingerprint,
            "status": job.status,
            "attempt_count": job.attempt_count,
            "model_config_ref": job.model_config_ref,
            "provider_id": job.provider_id,
            "model_id": job.model_id,
            "extraction_schema_version": job.extraction_schema_version,
            "taxonomy_version": job.taxonomy_version,
            "token_usage_json": dict(job.token_usage),
            "warning_codes_json": list(job.warning_codes),
            "error_code": job.error_code,
            "error_message": job.error_message,
            "queued_reason": job.queued_reason,
            "retry_after": job.retry_after,
            "completed_at": job.completed_at,
            "updated_at": now,
        }
        if record is None:
            record = MemoryGraphExtractionJobRecord(
                graph_job_id=job.graph_job_id,
                created_at=now,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        self._session.flush()
        return record

    def get_node(self, *, story_id: str, node_id: str) -> MemoryGraphNodeRecord | None:
        record = self._session.get(MemoryGraphNodeRecord, node_id)
        if record is None or record.story_id != story_id:
            return None
        return record

    def get_job(
        self, *, story_id: str, graph_job_id: str
    ) -> MemoryGraphExtractionJobRecord | None:
        record = self._session.get(MemoryGraphExtractionJobRecord, graph_job_id)
        if record is None or record.story_id != story_id:
            return None
        return record

    def find_node_by_normalization_key(
        self,
        *,
        story_id: str,
        normalization_key: str,
    ) -> MemoryGraphNodeRecord | None:
        key = str(normalization_key or "").strip()
        if not key:
            return None
        stmt = (
            select(MemoryGraphNodeRecord)
            .where(MemoryGraphNodeRecord.story_id == story_id)
            .where(MemoryGraphNodeRecord.normalization_key == key)
            .order_by(MemoryGraphNodeRecord.updated_at.desc())
        )
        return self._session.exec(stmt).first()

    def find_node_by_canonical_name(
        self,
        *,
        story_id: str,
        entity_type: str,
        canonical_name: str,
        source_layer: str,
    ) -> MemoryGraphNodeRecord | None:
        name = str(canonical_name or "").strip()
        if not name:
            return None
        stmt = (
            select(MemoryGraphNodeRecord)
            .where(MemoryGraphNodeRecord.story_id == story_id)
            .where(MemoryGraphNodeRecord.entity_type == entity_type)
            .where(MemoryGraphNodeRecord.source_layer == source_layer)
            .where(MemoryGraphNodeRecord.canonical_name == name)
            .order_by(MemoryGraphNodeRecord.updated_at.desc())
        )
        return self._session.exec(stmt).first()

    def list_nodes(
        self,
        *,
        story_id: str,
        node_ids: list[str] | None = None,
        entity_types: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_statuses: list[str] | None = None,
        limit: int | None = 100,
    ) -> list[MemoryGraphNodeRecord]:
        stmt = select(MemoryGraphNodeRecord).where(
            MemoryGraphNodeRecord.story_id == story_id
        )
        node_ids = _dedupe(node_ids)
        if node_ids:
            stmt = stmt.where(MemoryGraphNodeRecord.node_id.in_(node_ids))
        entity_types = self._validate_filter_values(
            entity_types,
            validator=validate_graph_entity_type,
        )
        if entity_types:
            stmt = stmt.where(MemoryGraphNodeRecord.entity_type.in_(entity_types))
        source_layers = self._validate_filter_values(
            source_layers,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        if source_layers:
            stmt = stmt.where(MemoryGraphNodeRecord.source_layer.in_(source_layers))
        source_statuses = self._validate_filter_values(
            source_statuses,
            allowed=GRAPH_SOURCE_STATUSES,
            field_name="source_status",
        )
        if source_statuses:
            stmt = stmt.where(MemoryGraphNodeRecord.source_status.in_(source_statuses))
        stmt = stmt.order_by(
            MemoryGraphNodeRecord.canonical_name.asc(),
            MemoryGraphNodeRecord.node_id.asc(),
        )
        if limit is not None:
            stmt = stmt.limit(max(int(limit), 0))
        return list(self._session.exec(stmt).all())

    def list_edges(
        self,
        *,
        story_id: str,
        edge_ids: list[str] | None = None,
        node_ids: list[str] | None = None,
        relation_types: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_statuses: list[str] | None = None,
        limit: int | None = 100,
    ) -> list[MemoryGraphEdgeRecord]:
        stmt = select(MemoryGraphEdgeRecord).where(
            MemoryGraphEdgeRecord.story_id == story_id
        )
        edge_ids = _dedupe(edge_ids)
        if edge_ids:
            stmt = stmt.where(MemoryGraphEdgeRecord.edge_id.in_(edge_ids))
        node_ids = _dedupe(node_ids)
        if node_ids:
            stmt = stmt.where(
                or_(
                    MemoryGraphEdgeRecord.source_node_id.in_(node_ids),
                    MemoryGraphEdgeRecord.target_node_id.in_(node_ids),
                )
            )
        relation_types = self._validate_filter_values(
            relation_types,
            validator=validate_graph_relation_type,
        )
        if relation_types:
            stmt = stmt.where(MemoryGraphEdgeRecord.relation_type.in_(relation_types))
        source_layers = self._validate_filter_values(
            source_layers,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        if source_layers:
            stmt = stmt.where(MemoryGraphEdgeRecord.source_layer.in_(source_layers))
        source_statuses = self._validate_filter_values(
            source_statuses,
            allowed=GRAPH_SOURCE_STATUSES,
            field_name="source_status",
        )
        if source_statuses:
            stmt = stmt.where(MemoryGraphEdgeRecord.source_status.in_(source_statuses))
        stmt = stmt.order_by(
            MemoryGraphEdgeRecord.relation_type.asc(),
            MemoryGraphEdgeRecord.source_entity_name.asc(),
            MemoryGraphEdgeRecord.target_entity_name.asc(),
            MemoryGraphEdgeRecord.edge_id.asc(),
        )
        if limit is not None:
            stmt = stmt.limit(max(int(limit), 0))
        return list(self._session.exec(stmt).all())

    def list_evidence(
        self,
        *,
        story_id: str,
        evidence_ids: list[str] | None = None,
        node_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        source_layers: list[str] | None = None,
        source_asset_ids: list[str] | None = None,
        chunk_ids: list[str] | None = None,
        limit: int | None = 100,
    ) -> list[MemoryGraphEvidenceRecord]:
        stmt = select(MemoryGraphEvidenceRecord).where(
            MemoryGraphEvidenceRecord.story_id == story_id
        )
        evidence_ids = _dedupe(evidence_ids)
        if evidence_ids:
            stmt = stmt.where(MemoryGraphEvidenceRecord.evidence_id.in_(evidence_ids))
        node_ids = _dedupe(node_ids)
        edge_ids = _dedupe(edge_ids)
        if node_ids and edge_ids:
            stmt = stmt.where(
                or_(
                    MemoryGraphEvidenceRecord.node_id.in_(node_ids),
                    MemoryGraphEvidenceRecord.edge_id.in_(edge_ids),
                )
            )
        elif node_ids:
            stmt = stmt.where(MemoryGraphEvidenceRecord.node_id.in_(node_ids))
        elif edge_ids:
            stmt = stmt.where(MemoryGraphEvidenceRecord.edge_id.in_(edge_ids))
        source_layers = self._validate_filter_values(
            source_layers,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        if source_layers:
            stmt = stmt.where(MemoryGraphEvidenceRecord.source_layer.in_(source_layers))
        source_asset_ids = _dedupe(source_asset_ids)
        if source_asset_ids:
            stmt = stmt.where(
                MemoryGraphEvidenceRecord.source_asset_id.in_(source_asset_ids)
            )
        chunk_ids = _dedupe(chunk_ids)
        if chunk_ids:
            stmt = stmt.where(MemoryGraphEvidenceRecord.chunk_id.in_(chunk_ids))
        stmt = stmt.order_by(
            MemoryGraphEvidenceRecord.source_asset_id.asc(),
            MemoryGraphEvidenceRecord.chunk_id.asc(),
            MemoryGraphEvidenceRecord.evidence_id.asc(),
        )
        if limit is not None:
            stmt = stmt.limit(max(int(limit), 0))
        return list(self._session.exec(stmt).all())

    def list_jobs(
        self,
        *,
        story_id: str,
        statuses: list[str] | None = None,
        source_layers: list[str] | None = None,
        limit: int | None = 50,
    ) -> list[MemoryGraphExtractionJobRecord]:
        stmt = select(MemoryGraphExtractionJobRecord).where(
            MemoryGraphExtractionJobRecord.story_id == story_id
        )
        statuses = self._validate_filter_values(
            statuses,
            allowed=GRAPH_JOB_STATUSES,
            field_name="status",
        )
        if statuses:
            stmt = stmt.where(MemoryGraphExtractionJobRecord.status.in_(statuses))
        source_layers = self._validate_filter_values(
            source_layers,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        if source_layers:
            stmt = stmt.where(
                MemoryGraphExtractionJobRecord.source_layer.in_(source_layers)
            )
        stmt = stmt.order_by(
            MemoryGraphExtractionJobRecord.updated_at.desc(),
            MemoryGraphExtractionJobRecord.graph_job_id.asc(),
        )
        if limit is not None:
            stmt = stmt.limit(max(int(limit), 0))
        return list(self._session.exec(stmt).all())

    def count_nodes(self, *, story_id: str) -> int:
        stmt = select(MemoryGraphNodeRecord.node_id).where(
            MemoryGraphNodeRecord.story_id == story_id
        )
        return len(self._session.exec(stmt).all())

    def count_edges(self, *, story_id: str) -> int:
        stmt = select(MemoryGraphEdgeRecord.edge_id).where(
            MemoryGraphEdgeRecord.story_id == story_id
        )
        return len(self._session.exec(stmt).all())

    def count_evidence(self, *, story_id: str) -> int:
        stmt = select(MemoryGraphEvidenceRecord.evidence_id).where(
            MemoryGraphEvidenceRecord.story_id == story_id
        )
        return len(self._session.exec(stmt).all())

    def list_source_layers(self, *, story_id: str) -> list[str]:
        layers: set[str] = set()
        for model, column in (
            (MemoryGraphNodeRecord, MemoryGraphNodeRecord.source_layer),
            (MemoryGraphEdgeRecord, MemoryGraphEdgeRecord.source_layer),
            (
                MemoryGraphExtractionJobRecord,
                MemoryGraphExtractionJobRecord.source_layer,
            ),
        ):
            stmt = select(column).where(model.story_id == story_id)
            layers.update(str(item) for item in self._session.exec(stmt).all() if item)
        return sorted(layers)

    def evidence_count_by_edge_ids(
        self,
        *,
        story_id: str,
        edge_ids: list[str],
    ) -> dict[str, int]:
        edge_ids = _dedupe(edge_ids)
        if not edge_ids:
            return {}
        records = self.list_evidence(
            story_id=story_id,
            edge_ids=edge_ids,
            limit=None,
        )
        counts: dict[str, int] = {edge_id: 0 for edge_id in edge_ids}
        for record in records:
            if record.edge_id is None:
                continue
            counts[record.edge_id] = counts.get(record.edge_id, 0) + 1
        return counts

    @staticmethod
    def _validate_node(node: MemoryGraphNodeUpsert) -> None:
        validate_graph_entity_type(node.entity_type)
        validate_graph_constant(
            node.source_layer,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        validate_graph_constant(
            node.source_status,
            allowed=GRAPH_SOURCE_STATUSES,
            field_name="source_status",
        )

    @staticmethod
    def _validate_edge(edge: MemoryGraphEdgeUpsert) -> None:
        validate_graph_relation_type(edge.relation_type)
        validate_graph_constant(
            edge.relation_family,
            allowed=GRAPH_RELATION_FAMILIES,
            field_name="relation_family",
        )
        validate_graph_constant(
            edge.source_layer,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        validate_graph_constant(
            edge.source_status,
            allowed=GRAPH_SOURCE_STATUSES,
            field_name="source_status",
        )
        validate_graph_constant(
            edge.direction,
            allowed=GRAPH_EDGE_DIRECTIONS,
            field_name="direction",
        )
        validate_graph_constant(
            edge.canon_status,
            allowed=GRAPH_CANON_STATUSES,
            field_name="canon_status",
        )

    @staticmethod
    def _validate_evidence(evidence: MemoryGraphEvidenceUpsert) -> None:
        validate_graph_constant(
            evidence.source_layer,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        if not evidence.node_id and not evidence.edge_id:
            raise ValueError("Graph evidence requires node_id or edge_id")

    @staticmethod
    def _validate_job(job: MemoryGraphExtractionJobUpsert) -> None:
        validate_graph_constant(
            job.source_layer,
            allowed=GRAPH_SOURCE_LAYERS,
            field_name="source_layer",
        )
        validate_graph_constant(
            job.status, allowed=GRAPH_JOB_STATUSES, field_name="status"
        )
        if job.queued_reason is not None:
            validate_graph_constant(
                job.queued_reason,
                allowed=GRAPH_JOB_QUEUED_REASONS,
                field_name="queued_reason",
            )
        for code in job.warning_codes:
            validate_graph_constant(
                code,
                allowed=GRAPH_WARNING_CODES,
                field_name="warning_code",
            )
        if job.error_code is not None:
            validate_graph_constant(
                job.error_code,
                allowed=GRAPH_ERROR_CODES,
                field_name="error_code",
            )

    @staticmethod
    def _validate_filter_values(
        values: list[str] | None,
        *,
        allowed: tuple[str, ...] | None = None,
        field_name: str | None = None,
        validator=None,
    ) -> list[str]:
        normalized = _dedupe(values)
        if not normalized:
            return []
        if validator is not None:
            return [validator(value) for value in normalized]
        if allowed is None or field_name is None:
            return normalized
        return [
            validate_graph_constant(value, allowed=allowed, field_name=field_name)
            for value in normalized
        ]
