"""LLM-backed graph extraction executor for queued Memory Graph jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlmodel import Session

from models.chat import ChatMessage
from models.rp_retrieval_store import (
    KnowledgeChunkRecord,
    MemoryGraphExtractionJobRecord,
    SourceAssetRecord,
)
from rp.models.memory_graph_projection import (
    GRAPH_CANON_STATUS_SOURCE_REFERENCE,
    GRAPH_EDGE_DIRECTION_DIRECTED,
    GRAPH_EDGE_DIRECTIONS,
    GRAPH_ENTITY_TERM_OR_CONCEPT,
    GRAPH_ENTITY_TYPES,
    GRAPH_ERROR_EVIDENCE_POINTER_INVALID,
    GRAPH_ERROR_EXTRACTION_TIMEOUT,
    GRAPH_ERROR_MODEL_CONFIG_MISSING,
    GRAPH_ERROR_PERSISTENCE_FAILED,
    GRAPH_ERROR_PROVIDER_UNAVAILABLE,
    GRAPH_ERROR_SOURCE_CHUNK_MISSING,
    GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
    GRAPH_EXTRACTION_SCHEMA_VERSION,
    GRAPH_JOB_STATUS_COMPLETED,
    GRAPH_JOB_STATUS_FAILED,
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_JOB_STATUS_RUNNING,
    GRAPH_REL_RELATED_TO,
    GRAPH_RELATION_FAMILY_STABLE_SETUP,
    GRAPH_RELATION_TYPES,
    GRAPH_SOURCE_LAYER_ARCHIVAL,
    GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
    GRAPH_TAXONOMY_VERSION,
    GRAPH_WARNING_CODES,
    GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED,
    GRAPH_WARNING_MISSING_OPTIONAL_EVIDENCE_SPAN,
    GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE,
    MemoryGraphEdgeUpsert,
    MemoryGraphEvidenceUpsert,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphExtractionJobView,
    MemoryGraphNodeUpsert,
    normalize_graph_entity_type,
    normalize_graph_relation_type,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig
from .memory_graph_projection_repository import MemoryGraphProjectionRepository
from .retrieval_runtime_config_service import RetrievalRuntimeConfigService
from .story_llm_gateway import StoryLlmGateway


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _clean_text(value: str | None) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


class _StructuredOutputInvalid(ValueError):
    pass


class _SourceContextMissing(ValueError):
    pass


class _GraphExtractionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excerpt: str
    char_start: int | None = None
    char_end: int | None = None

    @field_validator("excerpt")
    @classmethod
    def _validate_excerpt(cls, value: str) -> str:
        excerpt = _clean_text(value)
        if not excerpt:
            raise ValueError("Graph relation evidence excerpt is required")
        return excerpt

    @model_validator(mode="after")
    def _validate_span(self):
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("Graph relation evidence char_end must be >= char_start")
        return self


class _GraphExtractionEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    confidence: float | None = None
    normalization_key: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        name = _clean_text(value)
        if not name:
            raise ValueError("Graph entity name is required")
        return name


class _GraphExtractionRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity: str
    target_entity: str
    relation_type: str
    raw_relation_text: str | None = None
    confidence: float | None = None
    direction: str = GRAPH_EDGE_DIRECTION_DIRECTED
    evidence: _GraphExtractionEvidence
    source_normalization_key: str | None = None
    target_normalization_key: str | None = None

    @field_validator("source_entity", "target_entity")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        endpoint = _clean_text(value)
        if not endpoint:
            raise ValueError("Graph relation endpoints are required")
        return endpoint

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, value: str) -> str:
        direction = _clean_text(value) or GRAPH_EDGE_DIRECTION_DIRECTED
        if direction not in GRAPH_EDGE_DIRECTIONS:
            raise ValueError(f"Unsupported graph relation direction: {value!r}")
        return direction


class _GraphExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[_GraphExtractionEntity]
    relations: list[_GraphExtractionRelation]
    warnings: list[str]

    @field_validator("warnings")
    @classmethod
    def _validate_warnings(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            code = _clean_text(value)
            if code and code not in GRAPH_WARNING_CODES:
                raise ValueError(f"Unsupported graph extraction warning: {value!r}")
            if code:
                normalized.append(code)
        return _dedupe(normalized)


@dataclass(frozen=True)
class _GraphExtractionSourceContext:
    story_id: str
    workspace_id: str | None
    session_id: str | None
    source_layer: str
    source_asset_id: str
    chunk_id: str | None
    section_id: str | None
    collection_id: str | None
    parsed_document_id: str | None
    domain: str | None
    domain_path: str | None
    title: str | None
    text: str
    source_ref: str | None
    source_family: str | None
    source_type: str | None
    import_event: str | None
    commit_id: str | None
    step_id: str | None
    char_start: int | None
    char_end: int | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _PreparedMerge:
    nodes: list[MemoryGraphNodeUpsert]
    edges: list[MemoryGraphEdgeUpsert]
    evidence: list[MemoryGraphEvidenceUpsert]
    warning_codes: list[str]


class MemoryGraphExtractionService:
    """Run queued graph extraction jobs without blocking retrieval ingestion."""

    def __init__(
        self,
        session: Session,
        *,
        repository: MemoryGraphProjectionRepository | None = None,
        runtime_config_service: RetrievalRuntimeConfigService | None = None,
        llm_gateway: StoryLlmGateway | Any | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or MemoryGraphProjectionRepository(session)
        self._runtime_config_service = (
            runtime_config_service or RetrievalRuntimeConfigService(session)
        )
        self._llm_gateway = llm_gateway or StoryLlmGateway()

    async def process_job(
        self,
        *,
        story_id: str,
        graph_job_id: str,
    ) -> MemoryGraphExtractionJobView:
        job = self._repository.get_job(story_id=story_id, graph_job_id=graph_job_id)
        if job is None:
            raise ValueError(f"Graph extraction job not found: {graph_job_id}")
        if job.status != GRAPH_JOB_STATUS_QUEUED:
            return self._job_to_view(job)

        attempt_count = int(job.attempt_count or 0) or 1
        running_job = self._write_job_status(
            job,
            status=GRAPH_JOB_STATUS_RUNNING,
            attempt_count=attempt_count,
            warning_codes=[],
            error_code=None,
            error_message=None,
            token_usage={},
            completed_at=None,
        )

        if not running_job.provider_id or not running_job.model_id:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_MODEL_CONFIG_MISSING,
                error_message="Graph extraction provider/model is missing.",
            )

        try:
            context = self._build_source_context(running_job)
        except _SourceContextMissing as exc:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_SOURCE_CHUNK_MISSING,
                error_message=str(exc),
            )

        config = self._runtime_config_service.resolve_story_config(story_id=story_id)
        try:
            response_text, token_usage = await asyncio.wait_for(
                self._complete_extraction(
                    job=running_job,
                    config=config,
                    context=context,
                ),
                timeout=max(config.graph_extraction_timeout_ms, 1) / 1000,
            )
        except TimeoutError:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_EXTRACTION_TIMEOUT,
                error_message=(
                    "Graph extraction timed out after "
                    f"{config.graph_extraction_timeout_ms} ms."
                ),
            )
        except Exception as exc:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_PROVIDER_UNAVAILABLE,
                error_message=f"{type(exc).__name__}: {exc}",
            )

        try:
            extraction = self._parse_extraction_response(response_text)
            prepared = self._prepare_merge(
                story_id=story_id,
                job=running_job,
                context=context,
                extraction=extraction,
            )
        except _StructuredOutputInvalid as exc:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
                error_message=str(exc),
                token_usage=token_usage,
            )

        try:
            with self._session.begin_nested():
                for node in prepared.nodes:
                    self._repository.upsert_node(story_id=story_id, node=node)
                for edge in prepared.edges:
                    self._repository.upsert_edge(story_id=story_id, edge=edge)
                for item in prepared.evidence:
                    self._repository.upsert_evidence(story_id=story_id, evidence=item)
        except Exception as exc:
            return self._fail_job(
                running_job,
                error_code=GRAPH_ERROR_PERSISTENCE_FAILED,
                error_message=f"{type(exc).__name__}: {exc}",
                token_usage=token_usage,
            )

        completed = self._write_job_status(
            running_job,
            status=GRAPH_JOB_STATUS_COMPLETED,
            attempt_count=attempt_count,
            warning_codes=prepared.warning_codes,
            error_code=None,
            error_message=None,
            token_usage=token_usage,
            completed_at=_utcnow(),
        )
        return self._job_to_view(completed)

    async def process_story_queued_jobs(
        self,
        *,
        story_id: str,
        limit: int | None = None,
    ) -> list[MemoryGraphExtractionJobView]:
        resolved_limit = 20 if limit is None else max(int(limit), 0)
        queued_jobs = self._repository.list_jobs(
            story_id=story_id,
            statuses=[GRAPH_JOB_STATUS_QUEUED],
            limit=resolved_limit,
        )
        results = []
        for job in queued_jobs:
            results.append(
                await self.process_job(
                    story_id=story_id,
                    graph_job_id=job.graph_job_id,
                )
            )
        return results

    def _build_source_context(
        self,
        job: MemoryGraphExtractionJobRecord,
    ) -> _GraphExtractionSourceContext:
        asset: SourceAssetRecord | None = None
        chunk: KnowledgeChunkRecord | None = None
        chunk_metadata: dict[str, Any] = {}

        if job.chunk_id:
            chunk = self._session.get(KnowledgeChunkRecord, job.chunk_id)
            if chunk is None or chunk.story_id != job.story_id:
                raise _SourceContextMissing(
                    f"Graph source chunk not found: {job.chunk_id}"
                )
            asset = self._session.get(SourceAssetRecord, chunk.asset_id)
        elif job.source_asset_id:
            asset = self._session.get(SourceAssetRecord, job.source_asset_id)

        if asset is None or asset.story_id != job.story_id:
            raise _SourceContextMissing(
                f"Graph source asset not found: {job.source_asset_id}"
            )

        asset_metadata = dict(asset.metadata_json or {})
        if chunk is not None:
            chunk_metadata = dict(chunk.metadata_json or {})
            text = chunk.text
            title = chunk.title or asset.title
            collection_id = chunk.collection_id or asset.collection_id
            parsed_document_id = chunk.parsed_document_id
            domain = chunk.domain or self._metadata_value(
                "domain", chunk_metadata, asset_metadata
            )
            domain_path = chunk.domain_path or self._metadata_value(
                "domain_path", chunk_metadata, asset_metadata
            )
            char_start = self._metadata_int("char_start", chunk_metadata)
            char_end = self._metadata_int("char_end", chunk_metadata)
        else:
            text = self._asset_text(asset)
            title = asset.title
            collection_id = asset.collection_id
            parsed_document_id = None
            domain = self._metadata_value("domain", asset_metadata)
            domain_path = self._metadata_value("domain_path", asset_metadata)
            char_start = self._metadata_int("char_start", asset_metadata)
            char_end = self._metadata_int("char_end", asset_metadata)

        if not _clean_text(text):
            raise _SourceContextMissing(
                f"Graph source text is empty for asset: {asset.asset_id}"
            )

        return _GraphExtractionSourceContext(
            story_id=job.story_id,
            workspace_id=job.workspace_id or asset.workspace_id,
            session_id=job.session_id,
            source_layer=job.source_layer or GRAPH_SOURCE_LAYER_ARCHIVAL,
            source_asset_id=asset.asset_id,
            chunk_id=chunk.chunk_id if chunk is not None else None,
            section_id=(
                job.section_id
                or self._metadata_section_id(chunk_metadata)
                or self._metadata_section_id(asset_metadata)
            ),
            collection_id=collection_id,
            parsed_document_id=parsed_document_id,
            domain=domain,
            domain_path=domain_path,
            title=title,
            text=text,
            source_ref=self._metadata_value(
                "source_ref",
                chunk_metadata,
                asset_metadata,
                fallback=asset.source_ref,
            ),
            source_family=self._metadata_value(
                "source_family", chunk_metadata, asset_metadata
            ),
            source_type=self._metadata_value(
                "source_type", chunk_metadata, asset_metadata
            ),
            import_event=self._metadata_value(
                "import_event", chunk_metadata, asset_metadata
            ),
            commit_id=(
                job.commit_id
                or asset.commit_id
                or self._metadata_value("commit_id", chunk_metadata, asset_metadata)
            ),
            step_id=asset.step_id
            or self._metadata_value("step_id", chunk_metadata, asset_metadata),
            char_start=char_start,
            char_end=char_end,
            metadata={**asset_metadata, **chunk_metadata},
        )

    async def _complete_extraction(
        self,
        *,
        job: MemoryGraphExtractionJobRecord,
        config: RetrievalRuntimeConfig,
        context: _GraphExtractionSourceContext,
    ) -> tuple[str, dict[str, Any]]:
        kwargs = {
            "model_id": str(job.model_id),
            "provider_id": job.provider_id,
            "messages": self._build_messages(job=job, context=context),
            "temperature": config.graph_extraction_temperature,
            "max_tokens": config.graph_extraction_max_output_tokens,
            "include_reasoning": False,
        }
        if hasattr(self._llm_gateway, "complete_text_with_usage"):
            result = await self._llm_gateway.complete_text_with_usage(**kwargs)
            if isinstance(result, tuple):
                text, usage = result
                return str(text or ""), dict(usage or {})
            if isinstance(result, dict):
                return str(result.get("text") or result.get("content") or ""), dict(
                    result.get("token_usage") or result.get("usage") or {}
                )
        text = await self._llm_gateway.complete_text(**kwargs)
        return str(text or ""), {}

    def _build_messages(
        self,
        *,
        job: MemoryGraphExtractionJobRecord,
        context: _GraphExtractionSourceContext,
    ) -> list[ChatMessage]:
        allowed_entities = ", ".join(GRAPH_ENTITY_TYPES)
        allowed_relations = ", ".join(GRAPH_RELATION_TYPES)
        schema = {
            "entities": [
                {
                    "name": "Aileen",
                    "entity_type": "character",
                    "normalization_key": "character:aileen",
                    "aliases": ["Ail"],
                    "description": "Optional short source-grounded note.",
                    "confidence": 0.82,
                }
            ],
            "relations": [
                {
                    "source_entity": "Aileen",
                    "target_entity": "Order of Dawn",
                    "relation_type": "affiliated_with",
                    "raw_relation_text": "protected by the Order of Dawn",
                    "confidence": 0.74,
                    "direction": "directed",
                    "evidence": {
                        "excerpt": "Aileen is protected by the Order of Dawn.",
                        "char_start": 0,
                        "char_end": 43,
                    },
                }
            ],
            "warnings": [],
        }
        source_payload = {
            "story_id": context.story_id,
            "graph_job_id": job.graph_job_id,
            "source_layer": context.source_layer,
            "source_asset_id": context.source_asset_id,
            "chunk_id": context.chunk_id,
            "section_id": context.section_id,
            "source_ref": context.source_ref,
            "source_family": context.source_family,
            "source_type": context.source_type,
            "import_event": context.import_event,
            "domain": context.domain,
            "domain_path": context.domain_path,
            "commit_id": context.commit_id,
            "step_id": context.step_id,
            "title": context.title,
            "text": context.text,
        }
        return [
            ChatMessage(
                role="system",
                content=(
                    "You extract a small evidence-backed knowledge graph from one "
                    "RP archival source chunk. Return only one strict JSON object. "
                    "Do not include markdown. Use only these entity types: "
                    f"{allowed_entities}. Use only these relation types: "
                    f"{allowed_relations}. If a relation wording does not fit, use "
                    f"{GRAPH_REL_RELATED_TO} and preserve raw_relation_text. "
                    "Each relation must include evidence.excerpt from the source text."
                ),
            ),
            ChatMessage(
                role="user",
                content="\n".join(
                    [
                        "Required JSON schema example:",
                        json.dumps(schema, ensure_ascii=False, sort_keys=True),
                        "Source context:",
                        json.dumps(source_payload, ensure_ascii=False, sort_keys=True),
                    ]
                ),
            ),
        ]

    def _parse_extraction_response(
        self,
        response_text: str,
    ) -> _GraphExtractionResponse:
        try:
            payload = StoryLlmGateway.extract_json_object(response_text)
            return _GraphExtractionResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise _StructuredOutputInvalid(
                f"Invalid graph extraction structured output: {exc}"
            ) from exc

    def _prepare_merge(
        self,
        *,
        story_id: str,
        job: MemoryGraphExtractionJobRecord,
        context: _GraphExtractionSourceContext,
        extraction: _GraphExtractionResponse,
    ) -> _PreparedMerge:
        warning_codes = list(extraction.warnings)
        node_upserts: list[MemoryGraphNodeUpsert] = []
        node_by_lookup: dict[str, MemoryGraphNodeUpsert] = {}
        seen_node_ids: set[str] = set()

        for entity in extraction.entities:
            node, entity_warnings = self._node_from_entity(
                story_id=story_id,
                context=context,
                entity=entity,
            )
            warning_codes.extend(entity_warnings)
            if node.node_id in seen_node_ids:
                warning_codes.append(GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED)
                node = self._merge_node_upserts(
                    next(item for item in node_upserts if item.node_id == node.node_id),
                    node,
                )
                node_upserts = [
                    node if item.node_id == node.node_id else item
                    for item in node_upserts
                ]
            else:
                seen_node_ids.add(node.node_id)
                node_upserts.append(node)
            for lookup in self._node_lookup_keys(node):
                node_by_lookup[lookup] = node

        edge_upserts: list[MemoryGraphEdgeUpsert] = []
        evidence_upserts: list[MemoryGraphEvidenceUpsert] = []
        for relation in extraction.relations:
            source_node = self._resolve_relation_node(
                relation.source_entity,
                relation.source_normalization_key,
                node_by_lookup,
            )
            target_node = self._resolve_relation_node(
                relation.target_entity,
                relation.target_normalization_key,
                node_by_lookup,
            )
            if source_node is None or target_node is None:
                raise _StructuredOutputInvalid(
                    "Graph relation endpoint is missing from entities: "
                    f"{relation.source_entity!r} -> {relation.target_entity!r}"
                )

            relation_type, relation_warnings = normalize_graph_relation_type(
                relation.relation_type,
                fallback_to_related_to=True,
            )
            warning_codes.extend(relation_warnings)
            if (
                relation.evidence.char_start is None
                or relation.evidence.char_end is None
            ):
                warning_codes.append(GRAPH_WARNING_MISSING_OPTIONAL_EVIDENCE_SPAN)

            edge_id = self._edge_id(
                story_id=story_id,
                source_node_id=source_node.node_id,
                target_node_id=target_node.node_id,
                relation_type=relation_type,
                source_layer=context.source_layer,
            )
            edge_upserts.append(
                MemoryGraphEdgeUpsert(
                    edge_id=edge_id,
                    workspace_id=context.workspace_id,
                    session_id=context.session_id,
                    source_node_id=source_node.node_id,
                    target_node_id=target_node.node_id,
                    source_entity_name=source_node.canonical_name,
                    target_entity_name=target_node.canonical_name,
                    relation_type=relation_type,
                    relation_family=GRAPH_RELATION_FAMILY_STABLE_SETUP,
                    raw_relation_text=relation.raw_relation_text,
                    source_layer=context.source_layer,
                    source_status=GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
                    confidence=relation.confidence,
                    direction=relation.direction,
                    canon_status=GRAPH_CANON_STATUS_SOURCE_REFERENCE,
                    metadata={
                        "graph_job_id": job.graph_job_id,
                        "input_fingerprint": job.input_fingerprint,
                        "source_ref": context.source_ref,
                    },
                )
            )
            evidence_upserts.append(
                self._evidence_from_relation(
                    edge_id=edge_id,
                    context=context,
                    relation=relation,
                    job=job,
                )
            )

        if extraction.relations and not evidence_upserts:
            raise _StructuredOutputInvalid(GRAPH_ERROR_EVIDENCE_POINTER_INVALID)

        return _PreparedMerge(
            nodes=node_upserts,
            edges=edge_upserts,
            evidence=evidence_upserts,
            warning_codes=_dedupe(warning_codes),
        )

    def _node_from_entity(
        self,
        *,
        story_id: str,
        context: _GraphExtractionSourceContext,
        entity: _GraphExtractionEntity,
    ) -> tuple[MemoryGraphNodeUpsert, list[str]]:
        entity_type, warnings = normalize_graph_entity_type(
            entity.entity_type,
            fallback_to_term=True,
        )
        if entity_type == GRAPH_ENTITY_TERM_OR_CONCEPT and entity.entity_type not in (
            GRAPH_ENTITY_TERM_OR_CONCEPT,
        ):
            warnings = _dedupe([*warnings, GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE])
        normalization_key = self._normalization_key(
            entity_type=entity_type,
            canonical_name=entity.name,
            provided_key=entity.normalization_key,
        )
        existing = self._repository.find_node_by_normalization_key(
            story_id=story_id,
            normalization_key=normalization_key,
        ) or self._repository.find_node_by_canonical_name(
            story_id=story_id,
            entity_type=entity_type,
            canonical_name=entity.name,
            source_layer=context.source_layer,
        )
        node_id = (
            existing.node_id
            if existing is not None
            else self._node_id(
                story_id=story_id,
                normalization_key=normalization_key,
            )
        )
        aliases = list(entity.aliases)
        description = entity.description
        confidence = entity.confidence
        first_seen_source_ref = context.source_ref
        canonical_name = entity.name
        metadata = {
            "graph_extraction_schema_version": GRAPH_EXTRACTION_SCHEMA_VERSION,
            "graph_taxonomy_version": GRAPH_TAXONOMY_VERSION,
            "last_seen_source_ref": context.source_ref,
        }
        if existing is not None:
            aliases = [
                *list(existing.aliases_json or []),
                *aliases,
            ]
            if existing.canonical_name != entity.name:
                aliases.append(entity.name)
            canonical_name = existing.canonical_name or entity.name
            description = existing.description or description
            confidence = self._max_confidence(existing.confidence, confidence)
            first_seen_source_ref = existing.first_seen_source_ref or context.source_ref
            metadata = {**dict(existing.metadata_json or {}), **metadata}
            warnings.append(GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED)
        return (
            MemoryGraphNodeUpsert(
                node_id=node_id,
                workspace_id=context.workspace_id,
                session_id=context.session_id,
                source_layer=context.source_layer,
                entity_type=entity_type,
                canonical_name=canonical_name,
                aliases=_dedupe([_clean_text(alias) for alias in aliases]),
                description=description,
                source_status=GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
                confidence=confidence,
                first_seen_source_ref=first_seen_source_ref,
                normalization_key=normalization_key,
                metadata=metadata,
            ),
            _dedupe(warnings),
        )

    def _merge_node_upserts(
        self,
        existing: MemoryGraphNodeUpsert,
        candidate: MemoryGraphNodeUpsert,
    ) -> MemoryGraphNodeUpsert:
        aliases = _dedupe(
            [
                *existing.aliases,
                *candidate.aliases,
                candidate.canonical_name
                if candidate.canonical_name != existing.canonical_name
                else "",
            ]
        )
        return existing.model_copy(
            update={
                "aliases": aliases,
                "description": existing.description or candidate.description,
                "confidence": self._max_confidence(
                    existing.confidence, candidate.confidence
                ),
                "metadata": {**existing.metadata, **candidate.metadata},
            }
        )

    def _evidence_from_relation(
        self,
        *,
        edge_id: str,
        context: _GraphExtractionSourceContext,
        relation: _GraphExtractionRelation,
        job: MemoryGraphExtractionJobRecord,
    ) -> MemoryGraphEvidenceUpsert:
        char_start = relation.evidence.char_start
        char_end = relation.evidence.char_end
        if char_start is None:
            char_start = context.char_start
        if char_end is None:
            char_end = context.char_end
        evidence_id = self._evidence_id(
            edge_id=edge_id,
            context=context,
            relation=relation,
            char_start=char_start,
            char_end=char_end,
        )
        return MemoryGraphEvidenceUpsert(
            evidence_id=evidence_id,
            workspace_id=context.workspace_id,
            edge_id=edge_id,
            source_layer=context.source_layer,
            source_family=context.source_family,
            source_type=context.source_type,
            import_event=context.import_event,
            source_ref=context.source_ref,
            source_asset_id=context.source_asset_id,
            collection_id=context.collection_id,
            parsed_document_id=context.parsed_document_id,
            chunk_id=context.chunk_id,
            section_id=context.section_id,
            domain=context.domain,
            domain_path=context.domain_path,
            commit_id=context.commit_id,
            step_id=context.step_id,
            char_start=char_start,
            char_end=char_end,
            evidence_excerpt=relation.evidence.excerpt,
            metadata={
                "graph_job_id": job.graph_job_id,
                "input_fingerprint": job.input_fingerprint,
                "raw_relation_text": relation.raw_relation_text,
            },
        )

    def _resolve_relation_node(
        self,
        entity_name: str,
        normalization_key: str | None,
        node_by_lookup: dict[str, MemoryGraphNodeUpsert],
    ) -> MemoryGraphNodeUpsert | None:
        lookup_candidates = []
        if normalization_key:
            lookup_candidates.append(self._lookup_key(normalization_key))
        lookup_candidates.append(self._lookup_key(entity_name))
        for key in lookup_candidates:
            node = node_by_lookup.get(key)
            if node is not None:
                return node
        return None

    def _node_lookup_keys(self, node: MemoryGraphNodeUpsert) -> list[str]:
        values = [node.canonical_name, node.normalization_key or "", *node.aliases]
        return _dedupe([self._lookup_key(value) for value in values])

    def _write_job_status(
        self,
        job: MemoryGraphExtractionJobRecord,
        *,
        status: str,
        attempt_count: int,
        warning_codes: list[str],
        error_code: str | None,
        error_message: str | None,
        token_usage: dict[str, Any],
        completed_at: datetime | None,
    ) -> MemoryGraphExtractionJobRecord:
        return self._repository.upsert_job(
            story_id=job.story_id,
            job=MemoryGraphExtractionJobUpsert(
                graph_job_id=job.graph_job_id,
                workspace_id=job.workspace_id,
                session_id=job.session_id,
                commit_id=job.commit_id,
                source_layer=job.source_layer,
                source_asset_id=job.source_asset_id,
                chunk_id=job.chunk_id,
                section_id=job.section_id,
                input_fingerprint=job.input_fingerprint,
                status=status,
                attempt_count=attempt_count,
                model_config_ref=job.model_config_ref,
                provider_id=job.provider_id,
                model_id=job.model_id,
                extraction_schema_version=job.extraction_schema_version,
                taxonomy_version=job.taxonomy_version,
                token_usage=token_usage,
                warning_codes=_dedupe(warning_codes),
                error_code=error_code,
                error_message=error_message,
                queued_reason=job.queued_reason,
                retry_after=job.retry_after,
                completed_at=completed_at,
            ),
        )

    def _fail_job(
        self,
        job: MemoryGraphExtractionJobRecord,
        *,
        error_code: str,
        error_message: str,
        token_usage: dict[str, Any] | None = None,
    ) -> MemoryGraphExtractionJobView:
        failed = self._write_job_status(
            job,
            status=GRAPH_JOB_STATUS_FAILED,
            attempt_count=int(job.attempt_count or 0) or 1,
            warning_codes=list(job.warning_codes_json or []),
            error_code=error_code,
            error_message=error_message,
            token_usage=token_usage or dict(job.token_usage_json or {}),
            completed_at=_utcnow(),
        )
        return self._job_to_view(failed)

    @staticmethod
    def _asset_text(asset: SourceAssetRecord) -> str:
        if _clean_text(asset.raw_excerpt):
            return _clean_text(asset.raw_excerpt)
        metadata = dict(asset.metadata_json or {})
        sections = metadata.get("seed_sections")
        if not isinstance(sections, list):
            return ""
        texts = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            text = _clean_text(section.get("text"))
            if text:
                texts.append(text)
        return "\n\n".join(texts)

    @staticmethod
    def _metadata_value(
        key: str,
        *metadata_items: dict[str, Any],
        fallback: str | None = None,
    ) -> str | None:
        for metadata in metadata_items:
            value = metadata.get(key)
            if value is not None and _clean_text(str(value)):
                return str(value)
        return fallback

    @staticmethod
    def _metadata_int(key: str, metadata: dict[str, Any]) -> int | None:
        value = metadata.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _metadata_section_id(metadata: dict[str, Any]) -> str | None:
        for key in ("section_id", "parent_section_id", "source_section_id"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _normalization_key(
        *,
        entity_type: str,
        canonical_name: str,
        provided_key: str | None,
    ) -> str:
        raw_key = _clean_text(provided_key).lower()
        if raw_key:
            if ":" in raw_key:
                prefix, suffix = raw_key.split(":", 1)
                if prefix == entity_type and suffix:
                    return raw_key
                return f"{entity_type}:{_slug(suffix or raw_key)}"
            return f"{entity_type}:{_slug(raw_key)}"
        return f"{entity_type}:{_slug(canonical_name)}"

    @staticmethod
    def _lookup_key(value: str | None) -> str:
        return _clean_text(value).lower()

    @staticmethod
    def _node_id(*, story_id: str, normalization_key: str) -> str:
        digest = hashlib.sha256(
            f"{story_id}:{normalization_key}".encode("utf-8")
        ).hexdigest()[:20]
        return f"graph_node_{digest}"

    @staticmethod
    def _edge_id(
        *,
        story_id: str,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        source_layer: str,
    ) -> str:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "story_id": story_id,
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "relation_type": relation_type,
                    "source_layer": source_layer,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:20]
        return f"graph_edge_{digest}"

    @staticmethod
    def _evidence_id(
        *,
        edge_id: str,
        context: _GraphExtractionSourceContext,
        relation: _GraphExtractionRelation,
        char_start: int | None,
        char_end: int | None,
    ) -> str:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "edge_id": edge_id,
                    "source_asset_id": context.source_asset_id,
                    "chunk_id": context.chunk_id,
                    "section_id": context.section_id,
                    "char_start": char_start,
                    "char_end": char_end,
                    "excerpt": relation.evidence.excerpt,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:20]
        return f"graph_evidence_{digest}"

    @staticmethod
    def _max_confidence(
        left: float | None,
        right: float | None,
    ) -> float | None:
        values = [value for value in (left, right) if value is not None]
        return max(values) if values else None

    @staticmethod
    def _job_to_view(
        job: MemoryGraphExtractionJobRecord,
    ) -> MemoryGraphExtractionJobView:
        return MemoryGraphExtractionJobView(
            graph_job_id=job.graph_job_id,
            story_id=job.story_id,
            workspace_id=job.workspace_id,
            session_id=job.session_id,
            commit_id=job.commit_id,
            source_layer=job.source_layer,
            source_asset_id=job.source_asset_id,
            chunk_id=job.chunk_id,
            section_id=job.section_id,
            input_fingerprint=job.input_fingerprint,
            status=job.status,
            attempt_count=job.attempt_count,
            model_config_ref=job.model_config_ref,
            provider_id=job.provider_id,
            model_id=job.model_id,
            extraction_schema_version=job.extraction_schema_version,
            taxonomy_version=job.taxonomy_version,
            token_usage=dict(job.token_usage_json or {}),
            warning_codes=list(job.warning_codes_json or []),
            error_code=job.error_code,
            error_message=job.error_message,
            queued_reason=job.queued_reason,
            retry_after=job.retry_after,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )
