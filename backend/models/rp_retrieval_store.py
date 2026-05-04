"""SQLModel storage records and schema helpers for RP retrieval-core."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator, UserDefinedType
from sqlmodel import Field, SQLModel

from rp.models.memory_graph_projection import (
    GRAPH_CANON_STATUS_SOURCE_REFERENCE,
    GRAPH_EDGE_DIRECTION_DIRECTED,
    GRAPH_ENTITY_SCHEMA_VERSION,
    GRAPH_EXTRACTION_SCHEMA_VERSION,
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_RELATION_FAMILY_STABLE_SETUP,
    GRAPH_RELATION_SCHEMA_VERSION,
    GRAPH_SOURCE_LAYER_ARCHIVAL,
    GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
    GRAPH_TAXONOMY_VERSION,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


def _format_vector(value: Iterable[float]) -> str:
    return (
        "["
        + ",".join(f"{float(item):.12f}".rstrip("0").rstrip(".") for item in value)
        + "]"
    )


def _parse_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        if text_value.startswith("[") and text_value.endswith("]"):
            inner = text_value[1:-1].strip()
            if not inner:
                return []
            return [float(item) for item in inner.split(",")]
        try:
            decoded = json.loads(text_value)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, list):
            return [float(item) for item in decoded]
    return None


class _PgVectorType(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "vector"


class PgVectorJSON(TypeDecorator):
    """Store vectors as PostgreSQL pgvector or JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVectorType())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect):
        vector = _parse_vector(value)
        if vector is None:
            return None
        if dialect.name == "postgresql":
            return _format_vector(vector)
        return vector

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return _parse_vector(value)
        return _parse_vector(value)


class KnowledgeCollectionRecord(SQLModel, table=True):
    """Authoritative retrieval collection record."""

    __tablename__ = "rp_knowledge_collections"

    collection_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    scope: str = Field(index=True)
    collection_kind: str = Field(index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class SourceAssetRecord(SQLModel, table=True):
    """Authoritative retrieval source asset record."""

    __tablename__ = "rp_source_assets"

    asset_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    mode: str = Field(index=True)
    collection_id: str | None = Field(default=None, index=True)
    workspace_id: str | None = Field(default=None, index=True)
    step_id: str | None = Field(default=None, index=True)
    commit_id: str | None = Field(default=None, index=True)
    asset_kind: str = Field(index=True)
    source_ref: str
    title: str | None = None
    storage_path: str | None = None
    mime_type: str | None = None
    raw_excerpt: str | None = None
    parse_status: str = Field(index=True)
    ingestion_status: str = Field(index=True)
    mapped_targets_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class ParsedDocumentRecord(SQLModel, table=True):
    """Structured parsed document retained for retrieval ingestion provenance."""

    __tablename__ = "rp_parsed_documents"

    parsed_document_id: str = Field(primary_key=True, index=True)
    asset_id: str = Field(foreign_key="rp_source_assets.asset_id", index=True)
    story_id: str = Field(index=True)
    parser_kind: str = Field(index=True)
    document_structure_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    parse_warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class KnowledgeChunkRecord(SQLModel, table=True):
    """Archival or recall knowledge chunk record."""

    __tablename__ = "rp_knowledge_chunks"

    chunk_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    collection_id: str | None = Field(default=None, index=True)
    asset_id: str = Field(foreign_key="rp_source_assets.asset_id", index=True)
    parsed_document_id: str = Field(
        foreign_key="rp_parsed_documents.parsed_document_id",
        index=True,
    )
    chunk_index: int
    domain: str = Field(index=True)
    domain_path: str | None = Field(default=None, index=True)
    title: str | None = None
    text: str
    token_count: int | None = Field(default=None, index=True)
    is_active: bool = Field(default=True, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    provenance_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class EmbeddingRecordRecord(SQLModel, table=True):
    """Dense-vector record for retrieval chunks."""

    __tablename__ = "rp_embedding_records"

    embedding_id: str = Field(primary_key=True, index=True)
    chunk_id: str = Field(foreign_key="rp_knowledge_chunks.chunk_id", index=True)
    embedding_model: str = Field(index=True)
    provider_id: str | None = Field(default=None, index=True)
    vector_dim: int
    status: str = Field(index=True)
    is_active: bool = Field(default=True, index=True)
    embedding_vector: list[float] | None = Field(
        default=None,
        sa_column=Column(PgVectorJSON(), nullable=True),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class IndexJobRecord(SQLModel, table=True):
    """Retrieval-side execution record for ingestion and reindex jobs."""

    __tablename__ = "rp_index_jobs"

    job_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    asset_id: str | None = Field(default=None, index=True)
    collection_id: str | None = Field(default=None, index=True)
    job_kind: str = Field(index=True)
    job_state: str = Field(index=True)
    target_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    completed_at: datetime | None = Field(default=None, index=True)


class MemoryGraphNodeRecord(SQLModel, table=True):
    """Lightweight graph projection node over retrieval-owned memory material."""

    __tablename__ = "rp_memory_graph_nodes"

    node_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    workspace_id: str | None = Field(default=None, index=True)
    session_id: str | None = Field(default=None, index=True)
    source_layer: str = Field(default=GRAPH_SOURCE_LAYER_ARCHIVAL, index=True)
    entity_type: str = Field(index=True)
    canonical_name: str = Field(index=True)
    aliases_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    description: str | None = None
    source_status: str = Field(default=GRAPH_SOURCE_STATUS_SOURCE_REFERENCE, index=True)
    confidence: float | None = Field(default=None, index=True)
    first_seen_source_ref: str | None = Field(default=None, index=True)
    entity_schema_version: str = Field(default=GRAPH_ENTITY_SCHEMA_VERSION, index=True)
    normalization_key: str | None = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryGraphEdgeRecord(SQLModel, table=True):
    """Evidence-backed relation candidate between graph projection nodes."""

    __tablename__ = "rp_memory_graph_edges"

    edge_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    workspace_id: str | None = Field(default=None, index=True)
    session_id: str | None = Field(default=None, index=True)
    source_node_id: str = Field(
        foreign_key="rp_memory_graph_nodes.node_id",
        index=True,
    )
    target_node_id: str = Field(
        foreign_key="rp_memory_graph_nodes.node_id",
        index=True,
    )
    source_entity_name: str | None = Field(default=None, index=True)
    target_entity_name: str | None = Field(default=None, index=True)
    relation_type: str = Field(index=True)
    relation_family: str = Field(default=GRAPH_RELATION_FAMILY_STABLE_SETUP, index=True)
    relation_schema_version: str = Field(
        default=GRAPH_RELATION_SCHEMA_VERSION, index=True
    )
    raw_relation_text: str | None = None
    source_layer: str = Field(default=GRAPH_SOURCE_LAYER_ARCHIVAL, index=True)
    source_status: str = Field(default=GRAPH_SOURCE_STATUS_SOURCE_REFERENCE, index=True)
    confidence: float | None = Field(default=None, index=True)
    direction: str = Field(default=GRAPH_EDGE_DIRECTION_DIRECTED, index=True)
    valid_from: str | None = Field(default=None, index=True)
    valid_to: str | None = Field(default=None, index=True)
    branch_id: str | None = Field(default=None, index=True)
    canon_status: str = Field(default=GRAPH_CANON_STATUS_SOURCE_REFERENCE, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryGraphEvidenceRecord(SQLModel, table=True):
    """Retrieval-core provenance pointer for one graph node or edge."""

    __tablename__ = "rp_memory_graph_evidence"

    evidence_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    workspace_id: str | None = Field(default=None, index=True)
    node_id: str | None = Field(
        default=None,
        foreign_key="rp_memory_graph_nodes.node_id",
        index=True,
    )
    edge_id: str | None = Field(
        default=None,
        foreign_key="rp_memory_graph_edges.edge_id",
        index=True,
    )
    source_layer: str = Field(default=GRAPH_SOURCE_LAYER_ARCHIVAL, index=True)
    source_family: str | None = Field(default=None, index=True)
    source_type: str | None = Field(default=None, index=True)
    import_event: str | None = Field(default=None, index=True)
    source_ref: str | None = Field(default=None, index=True)
    source_asset_id: str | None = Field(
        default=None,
        foreign_key="rp_source_assets.asset_id",
        index=True,
    )
    collection_id: str | None = Field(default=None, index=True)
    parsed_document_id: str | None = Field(
        default=None,
        foreign_key="rp_parsed_documents.parsed_document_id",
        index=True,
    )
    chunk_id: str | None = Field(
        default=None,
        foreign_key="rp_knowledge_chunks.chunk_id",
        index=True,
    )
    section_id: str | None = Field(default=None, index=True)
    domain: str | None = Field(default=None, index=True)
    domain_path: str | None = Field(default=None, index=True)
    commit_id: str | None = Field(default=None, index=True)
    step_id: str | None = Field(default=None, index=True)
    char_start: int | None = Field(default=None, index=True)
    char_end: int | None = Field(default=None, index=True)
    evidence_excerpt: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryGraphExtractionJobRecord(SQLModel, table=True):
    """Asynchronous graph extraction maintenance job audit row."""

    __tablename__ = "rp_memory_graph_extraction_jobs"

    graph_job_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    workspace_id: str | None = Field(default=None, index=True)
    session_id: str | None = Field(default=None, index=True)
    commit_id: str | None = Field(default=None, index=True)
    source_layer: str = Field(default=GRAPH_SOURCE_LAYER_ARCHIVAL, index=True)
    source_asset_id: str | None = Field(
        default=None,
        foreign_key="rp_source_assets.asset_id",
        index=True,
    )
    chunk_id: str | None = Field(
        default=None,
        foreign_key="rp_knowledge_chunks.chunk_id",
        index=True,
    )
    section_id: str | None = Field(default=None, index=True)
    input_fingerprint: str = Field(index=True)
    status: str = Field(default=GRAPH_JOB_STATUS_QUEUED, index=True)
    attempt_count: int = Field(default=0, index=True)
    model_config_ref: str | None = Field(default=None, index=True)
    provider_id: str | None = Field(default=None, index=True)
    model_id: str | None = Field(default=None, index=True)
    extraction_schema_version: str = Field(
        default=GRAPH_EXTRACTION_SCHEMA_VERSION,
        index=True,
    )
    taxonomy_version: str = Field(default=GRAPH_TAXONOMY_VERSION, index=True)
    token_usage_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    warning_codes_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    error_code: str | None = Field(default=None, index=True)
    error_message: str | None = None
    queued_reason: str | None = Field(default=None, index=True)
    retry_after: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    completed_at: datetime | None = Field(default=None, index=True)


def _ensure_column(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
        )


def ensure_retrieval_store_compatible_schema(engine: Engine) -> None:
    """Patch existing retrieval tables in-place for retrieval-core MVP."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name

    if "rp_source_assets" in tables:
        _ensure_column(engine, "rp_source_assets", "raw_excerpt", "TEXT")

    if "rp_knowledge_chunks" in tables:
        _ensure_column(engine, "rp_knowledge_chunks", "token_count", "INTEGER")
        _ensure_column(
            engine,
            "rp_knowledge_chunks",
            "is_active",
            "BOOLEAN DEFAULT TRUE NOT NULL"
            if dialect == "postgresql"
            else "INTEGER DEFAULT 1 NOT NULL",
        )

    if "rp_embedding_records" in tables:
        _ensure_column(engine, "rp_embedding_records", "provider_id", "VARCHAR")
        _ensure_column(
            engine,
            "rp_embedding_records",
            "is_active",
            "BOOLEAN DEFAULT TRUE NOT NULL"
            if dialect == "postgresql"
            else "INTEGER DEFAULT 1 NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_embedding_records",
            "embedding_vector",
            "vector" if dialect == "postgresql" else "JSON",
        )

    if "rp_index_jobs" in tables:
        _ensure_column(
            engine,
            "rp_index_jobs",
            "target_refs_json",
            "JSONB DEFAULT '[]'::jsonb NOT NULL"
            if dialect == "postgresql"
            else "JSON DEFAULT '[]' NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_index_jobs",
            "started_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )

    with engine.begin() as connection:
        if dialect == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_knowledge_chunks_story_collection_domain_active "
                    "ON rp_knowledge_chunks (story_id, collection_id, domain, is_active)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_knowledge_chunks_fts "
                    "ON rp_knowledge_chunks USING GIN "
                    "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(\"text\", '')))"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_embedding_records_chunk_model_active "
                    "ON rp_embedding_records (chunk_id, embedding_model, is_active)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_source_assets_story_collection_ingestion "
                    "ON rp_source_assets (story_id, collection_id, ingestion_status)"
                )
            )
            _create_graph_projection_indexes(connection)
        else:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_knowledge_chunks_story_collection_domain_active "
                    "ON rp_knowledge_chunks (story_id, collection_id, domain, is_active)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_embedding_records_chunk_model_active "
                    "ON rp_embedding_records (chunk_id, embedding_model, is_active)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_source_assets_story_collection_ingestion "
                    "ON rp_source_assets (story_id, collection_id, ingestion_status)"
                )
            )
            _create_graph_projection_indexes(connection)


def _create_graph_projection_indexes(connection) -> None:
    """Create additive graph projection indexes when the graph tables exist."""

    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_nodes_story_source_entity "
            "ON rp_memory_graph_nodes (story_id, source_layer, entity_type)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_nodes_story_normalization "
            "ON rp_memory_graph_nodes (story_id, normalization_key)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_edges_story_relation "
            "ON rp_memory_graph_edges (story_id, source_layer, relation_type)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_edges_story_nodes "
            "ON rp_memory_graph_edges (story_id, source_node_id, target_node_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_evidence_story_edge "
            "ON rp_memory_graph_evidence (story_id, edge_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_evidence_story_source "
            "ON rp_memory_graph_evidence (story_id, source_asset_id, chunk_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_jobs_story_status "
            "ON rp_memory_graph_extraction_jobs (story_id, status)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_rp_memory_graph_jobs_story_source "
            "ON rp_memory_graph_extraction_jobs (story_id, source_layer, source_asset_id)"
        )
    )


def ensure_pgvector_hnsw_index(engine: Engine, *, vector_dim: int) -> None:
    """Create a per-dimension partial HNSW index when PostgreSQL is active."""

    if engine.dialect.name != "postgresql" or vector_dim <= 0:
        return

    index_name = f"ix_rp_embedding_records_hnsw_dim_{int(vector_dim)}"
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                "ON rp_embedding_records USING hnsw "
                f"((embedding_vector::vector({int(vector_dim)})) vector_cosine_ops) "
                f"WHERE is_active = true AND vector_dim = {int(vector_dim)} AND embedding_vector IS NOT NULL"
            )
        )
