"""Tests for Memory Graph Projection storage, service, and retrieval isolation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

import pytest
from sqlmodel import select

from models.rp_retrieval_store import (
    KnowledgeChunkRecord,
    MemoryGraphExtractionJobRecord,
    MemoryGraphNodeRecord,
)
from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchArchivalInput
from rp.models.memory_graph_projection import (
    GRAPH_ENTITY_CHARACTER,
    GRAPH_ENTITY_TERM_OR_CONCEPT,
    GRAPH_ERROR_EXTRACTION_TIMEOUT,
    GRAPH_ERROR_MODEL_CONFIG_MISSING,
    GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
    GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    GRAPH_JOB_REASON_MANUAL_REBUILD,
    GRAPH_JOB_REASON_MANUAL_RETRY,
    GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED,
    GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED,
    GRAPH_JOB_STATUS_COMPLETED,
    GRAPH_JOB_STATUS_FAILED,
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_CANON_STATUS_SOURCE_REFERENCE,
    GRAPH_REL_AFFILIATED_WITH,
    GRAPH_REL_RELATED_TO,
    GRAPH_SOURCE_LAYER_ARCHIVAL,
    GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
    GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED,
    GRAPH_WARNING_MAPPED_TO_RELATED_TO,
    GRAPH_WARNING_NEIGHBORHOOD_TRUNCATED,
    GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE,
    GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE,
    MemoryGraphEdgeUpsert,
    MemoryGraphEvidenceUpsert,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphNodeUpsert,
    normalize_graph_relation_type,
    validate_graph_entity_type,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_drafts import StoryConfigDraft
from rp.models.story_runtime import LongformChapterPhase
from rp.models.setup_workspace import StoryMode
from rp.services.memory_graph_extraction_service import MemoryGraphExtractionService
from rp.services.memory_graph_projection_service import MemoryGraphProjectionService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _FakeGraphLlmGateway:
    def __init__(
        self,
        responses: list[str] | str,
        *,
        token_usage: dict | None = None,
    ) -> None:
        self._responses = [responses] if isinstance(responses, str) else list(responses)
        self._token_usage = token_usage or {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        }
        self.calls: list[dict] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        if self._responses:
            response = self._responses.pop(0)
        else:
            response = '{"entities":[],"relations":[],"warnings":[]}'
        return response, dict(self._token_usage)


class _HangingGraphLlmGateway:
    async def complete_text_with_usage(self, **_kwargs):
        await asyncio.sleep(60)
        return '{"entities":[],"relations":[],"warnings":[]}', {}


def _graph_response(
    *,
    entities: list[dict],
    relations: list[dict],
    warnings: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "entities": entities,
            "relations": relations,
            "warnings": warnings or [],
        },
        ensure_ascii=False,
    )


def _seed_archival_asset(
    retrieval_session, *, story_id: str, asset_id: str
) -> KnowledgeChunkRecord:
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=story_id,
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id=asset_id,
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            workspace_id="workspace-graph",
            commit_id="commit-graph",
            asset_kind="foundation_entry",
            source_ref=f"setup_commit:commit-graph:{asset_id}",
            title="Graph Foundation",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "layer": "archival",
                "source_family": "setup_source",
                "source_type": "foundation_entry",
                "import_event": "setup.commit_ingest",
                "workspace_id": "workspace-graph",
                "commit_id": "commit-graph",
                "seed_sections": [
                    {
                        "section_id": "section-aileen-order",
                        "title": "Aileen and the Order",
                        "path": "foundation.world.order",
                        "level": 1,
                        "text": "Aileen is protected by the Order of Dawn.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.order",
                            "source_family": "setup_source",
                            "source_type": "foundation_entry",
                            "import_event": "setup.commit_ingest",
                        },
                    }
                ],
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id=story_id,
        asset_id=asset_id,
        collection_id=collection.collection_id,
    )
    retrieval_session.flush()
    chunk = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.asset_id == asset_id)
    ).first()
    assert chunk is not None
    return chunk


def _seed_graph_extraction_config(
    retrieval_session,
    *,
    story_id: str,
    provider_id: str = "provider-graph",
    model_id: str = "graph-model",
    timeout_ms: int = 45000,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            graph_extraction_provider_id=provider_id,
            graph_extraction_model_id=model_id,
            graph_extraction_structured_output_mode="json_schema",
            graph_extraction_temperature=0.0,
            graph_extraction_max_output_tokens=1024,
            graph_extraction_timeout_ms=timeout_ms,
            graph_extraction_retry_policy={"max_attempts": 2},
            graph_extraction_enabled=True,
        ),
    )
    retrieval_session.flush()
    return workspace


def _seed_graph_projection(retrieval_session, *, story_id: str) -> None:
    chunk = _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-foundation",
    )
    service = MemoryGraphProjectionService(retrieval_session)
    service.upsert_seed_graph(
        story_id=story_id,
        nodes=[
            MemoryGraphNodeUpsert(
                node_id="graph-node-aileen",
                workspace_id="workspace-graph",
                entity_type="character",
                canonical_name="Aileen",
                aliases=["Ail"],
                confidence=0.91,
                first_seen_source_ref="setup_commit:commit-graph:asset-graph-foundation",
                normalization_key="character:aileen",
            ),
            MemoryGraphNodeUpsert(
                node_id="graph-node-order",
                workspace_id="workspace-graph",
                entity_type="faction_or_org",
                canonical_name="Order of Dawn",
                aliases=["the Order"],
                confidence=0.88,
                normalization_key="faction_or_org:order-of-dawn",
            ),
        ],
        edges=[
            MemoryGraphEdgeUpsert(
                edge_id="graph-edge-aileen-order",
                workspace_id="workspace-graph",
                source_node_id="graph-node-aileen",
                target_node_id="graph-node-order",
                source_entity_name="Aileen",
                target_entity_name="Order of Dawn",
                relation_type=GRAPH_REL_AFFILIATED_WITH,
                raw_relation_text="protected by the Order of Dawn",
                confidence=0.84,
            )
        ],
        evidence=[
            MemoryGraphEvidenceUpsert(
                evidence_id="graph-evidence-aileen-order",
                workspace_id="workspace-graph",
                edge_id="graph-edge-aileen-order",
                source_family="setup_source",
                source_type="foundation_entry",
                import_event="setup.commit_ingest",
                source_ref="setup_commit:commit-graph:asset-graph-foundation",
                source_asset_id="asset-graph-foundation",
                collection_id=chunk.collection_id,
                parsed_document_id=chunk.parsed_document_id,
                chunk_id=chunk.chunk_id,
                section_id="section-aileen-order",
                domain=chunk.domain,
                domain_path=chunk.domain_path,
                commit_id="commit-graph",
                evidence_excerpt="Aileen is protected by the Order of Dawn.",
            )
        ],
        jobs=[
            MemoryGraphExtractionJobUpsert(
                graph_job_id="graph-job-failed",
                workspace_id="workspace-graph",
                commit_id="commit-graph",
                source_asset_id="asset-graph-foundation",
                chunk_id=chunk.chunk_id,
                input_fingerprint="fingerprint:graph-foundation:v1",
                status=GRAPH_JOB_STATUS_FAILED,
                queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
                warning_codes=[GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE],
                error_code=GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
                error_message="invalid structured graph output",
            )
        ],
    )
    retrieval_session.commit()


def test_graph_taxonomy_constants_validate_and_explicitly_fallback():
    assert validate_graph_entity_type(GRAPH_ENTITY_CHARACTER) == GRAPH_ENTITY_CHARACTER

    relation, warnings = normalize_graph_relation_type(
        "freeform_relation",
        fallback_to_related_to=True,
    )

    assert relation == GRAPH_REL_RELATED_TO
    assert warnings == [
        GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE,
        GRAPH_WARNING_MAPPED_TO_RELATED_TO,
    ]

    with pytest.raises(ValueError):
        validate_graph_entity_type("scene")


def test_graph_projection_service_returns_visualization_ready_neighborhood(
    retrieval_session,
):
    story_id = "story-graph-projection"
    _seed_graph_projection(retrieval_session, story_id=story_id)
    service = MemoryGraphProjectionService(retrieval_session)

    nodes = service.list_nodes(story_id=story_id, entity_types=["character"])
    edges = service.list_edges(
        story_id=story_id, relation_types=[GRAPH_REL_AFFILIATED_WITH]
    )
    evidence = service.list_evidence(
        story_id=story_id, edge_ids=["graph-edge-aileen-order"]
    )
    neighborhood = service.get_neighborhood(
        story_id=story_id,
        node_id="graph-node-aileen",
        max_depth=1,
    )
    maintenance = service.get_maintenance_snapshot(story_id=story_id)

    assert [node.label for node in nodes.data] == ["Aileen"]
    assert nodes.data[0].source_layer == GRAPH_SOURCE_LAYER_ARCHIVAL
    assert edges.data[0].source == "graph-node-aileen"
    assert edges.data[0].target == "graph-node-order"
    assert edges.data[0].label == GRAPH_REL_AFFILIATED_WITH
    assert edges.data[0].source_status == GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
    assert edges.data[0].canon_status == GRAPH_CANON_STATUS_SOURCE_REFERENCE
    assert edges.data[0].evidence_count == 1
    assert evidence.data[0].source_asset_id == "asset-graph-foundation"
    assert evidence.data[0].chunk_id is not None
    assert {node.id for node in neighborhood.nodes} == {
        "graph-node-aileen",
        "graph-node-order",
    }
    assert [edge.id for edge in neighborhood.edges] == ["graph-edge-aileen-order"]
    assert [item.id for item in neighborhood.evidence] == [
        "graph-evidence-aileen-order"
    ]

    capped_neighborhood = service.get_neighborhood(
        story_id=story_id,
        node_id="graph-node-aileen",
        max_depth=1,
        max_nodes=1,
    )

    assert capped_neighborhood.truncated is True
    assert capped_neighborhood.warnings == [GRAPH_WARNING_NEIGHBORHOOD_TRUNCATED]
    assert [node.id for node in capped_neighborhood.nodes] == ["graph-node-aileen"]
    assert capped_neighborhood.edges == []
    assert maintenance.node_count == 2
    assert maintenance.edge_count == 1
    assert maintenance.evidence_count == 1
    assert maintenance.failed_job_count == 1
    assert maintenance.retryable_job_ids == ["graph-job-failed"]
    assert maintenance.warning_code_counts == {
        GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE: 1
    }
    assert maintenance.error_code_counts == {GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID: 1}

    stored_node = retrieval_session.get(MemoryGraphNodeRecord, "graph-node-aileen")
    assert stored_node is not None
    assert stored_node.story_id == story_id


def test_graph_extraction_queue_records_config_and_fingerprint_inputs(
    retrieval_session,
):
    story_id = "story-graph-job-config"
    _seed_graph_extraction_config(
        retrieval_session,
        story_id=story_id,
        provider_id="provider-graph-v1",
        model_id="graph-model-v1",
    )
    chunk = _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-job-config",
    )
    service = MemoryGraphProjectionService(retrieval_session)

    first_jobs = service.queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-job-config"],
        queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    )

    assert len(first_jobs) == 1
    first_job = first_jobs[0]
    assert first_job.status == GRAPH_JOB_STATUS_QUEUED
    assert first_job.source_asset_id == "asset-graph-job-config"
    assert first_job.chunk_id == chunk.chunk_id
    assert first_job.provider_id == "provider-graph-v1"
    assert first_job.model_id == "graph-model-v1"
    assert first_job.model_config_ref is not None
    assert first_job.queued_reason == GRAPH_JOB_REASON_ARCHIVAL_INGESTED

    StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id="workspace-graph",
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={"graph_extraction_model_id": "graph-model-v2"},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    model_changed = service.rebuild_story_graph(
        story_id=story_id,
        source_asset_ids=["asset-graph-job-config"],
        queued_reason=GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED,
    )[0]
    schema_changed = service.rebuild_story_graph(
        story_id=story_id,
        source_asset_ids=["asset-graph-job-config"],
        queued_reason=GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED,
        extraction_schema_version="graph_extraction_v2",
    )[0]

    stored_chunk = retrieval_session.get(KnowledgeChunkRecord, chunk.chunk_id)
    assert stored_chunk is not None
    stored_chunk.text = "Aileen is protected by the Order of Dawn and the dusk gate."
    retrieval_session.add(stored_chunk)
    retrieval_session.flush()
    source_changed = service.rebuild_story_graph(
        story_id=story_id,
        source_asset_ids=["asset-graph-job-config"],
        queued_reason=GRAPH_JOB_REASON_MANUAL_REBUILD,
    )[0]

    assert model_changed.queued_reason == GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED
    assert model_changed.model_id == "graph-model-v2"
    assert model_changed.input_fingerprint != first_job.input_fingerprint
    assert schema_changed.queued_reason == GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED
    assert schema_changed.input_fingerprint != model_changed.input_fingerprint
    assert source_changed.queued_reason == GRAPH_JOB_REASON_MANUAL_REBUILD
    assert source_changed.input_fingerprint != model_changed.input_fingerprint


def test_graph_extraction_missing_config_degrades_to_visible_job_status(
    retrieval_session,
):
    story_id = "story-graph-missing-config"
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-missing-config",
    )
    service = MemoryGraphProjectionService(retrieval_session)

    jobs = service.queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-missing-config"],
        queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    )
    maintenance = service.get_maintenance_snapshot(story_id=story_id)

    assert len(jobs) == 1
    assert jobs[0].status == GRAPH_JOB_STATUS_FAILED
    assert jobs[0].error_code == GRAPH_ERROR_MODEL_CONFIG_MISSING
    assert jobs[0].provider_id is None
    assert jobs[0].model_id is None
    assert GRAPH_ERROR_MODEL_CONFIG_MISSING in maintenance.maintenance_warnings
    assert maintenance.retryable_job_ids == [jobs[0].graph_job_id]


def test_graph_manual_rebuild_and_retry_controls_only_retryable_failed_jobs(
    retrieval_session,
):
    story_id = "story-graph-manual-controls"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-manual-controls",
    )
    service = MemoryGraphProjectionService(retrieval_session)

    rebuild_jobs = service.rebuild_story_graph(
        story_id=story_id,
        source_asset_ids=["asset-graph-manual-controls"],
    )
    service.upsert_seed_graph(
        story_id=story_id,
        jobs=[
            MemoryGraphExtractionJobUpsert(
                graph_job_id="graph-job-retryable",
                source_asset_id="asset-graph-manual-controls",
                input_fingerprint="old:fingerprint",
                status=GRAPH_JOB_STATUS_FAILED,
                attempt_count=1,
                queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
                error_code=GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
            ),
            MemoryGraphExtractionJobUpsert(
                graph_job_id="graph-job-not-retryable",
                input_fingerprint="old:no-source",
                status=GRAPH_JOB_STATUS_FAILED,
                queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
                error_code=GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
            ),
        ],
    )

    retry_jobs = service.retry_failed_jobs(story_id=story_id, limit=10)

    assert len(rebuild_jobs) == 1
    assert rebuild_jobs[0].queued_reason == GRAPH_JOB_REASON_MANUAL_REBUILD
    assert rebuild_jobs[0].status == GRAPH_JOB_STATUS_QUEUED
    assert len(retry_jobs) == 1
    assert retry_jobs[0].queued_reason == GRAPH_JOB_REASON_MANUAL_RETRY
    assert retry_jobs[0].attempt_count == 2
    assert retry_jobs[0].status == GRAPH_JOB_STATUS_QUEUED
    assert retry_jobs[0].source_asset_id == "asset-graph-manual-controls"
    retry_job_records = retrieval_session.exec(
        select(MemoryGraphExtractionJobRecord).where(
            MemoryGraphExtractionJobRecord.queued_reason
            == GRAPH_JOB_REASON_MANUAL_RETRY
        )
    ).all()
    assert len(retry_job_records) == 1


@pytest.mark.asyncio
async def test_graph_extraction_valid_output_merges_nodes_edges_and_evidence(
    retrieval_session,
):
    story_id = "story-graph-extraction-valid"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    chunk = _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-valid",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-valid"],
    )[0]
    gateway = _FakeGraphLlmGateway(
        _graph_response(
            entities=[
                {
                    "name": "Aileen",
                    "entity_type": "character",
                    "normalization_key": "character:aileen",
                    "aliases": ["Ail"],
                    "description": "Protected character in the setup source.",
                    "confidence": 0.91,
                },
                {
                    "name": "Order of Dawn",
                    "entity_type": "faction_or_org",
                    "normalization_key": "faction_or_org:order-of-dawn",
                    "aliases": ["the Order"],
                    "confidence": 0.88,
                },
            ],
            relations=[
                {
                    "source_entity": "Aileen",
                    "target_entity": "Order of Dawn",
                    "relation_type": GRAPH_REL_AFFILIATED_WITH,
                    "raw_relation_text": "protected by the Order of Dawn",
                    "confidence": 0.84,
                    "evidence": {
                        "excerpt": "Aileen is protected by the Order of Dawn.",
                        "char_start": 0,
                        "char_end": 42,
                    },
                }
            ],
        )
    )

    completed = await MemoryGraphExtractionService(
        retrieval_session, llm_gateway=gateway
    ).process_job(story_id=story_id, graph_job_id=queued_job.graph_job_id)
    projection = MemoryGraphProjectionService(retrieval_session)
    nodes = projection.list_nodes(story_id=story_id)
    edges = projection.list_edges(story_id=story_id)
    evidence = projection.list_evidence(story_id=story_id)

    assert completed.status == GRAPH_JOB_STATUS_COMPLETED
    assert completed.attempt_count == 1
    assert completed.error_code is None
    assert completed.completed_at is not None
    assert completed.token_usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert gateway.calls
    assert "entities" in str(gateway.calls[0]["messages"][1].content)
    assert {node.normalization_key for node in nodes.data} == {
        "character:aileen",
        "faction_or_org:order-of-dawn",
    }
    assert nodes.data[0].source_status == GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
    assert edges.data[0].label == GRAPH_REL_AFFILIATED_WITH
    assert edges.data[0].raw_relation_text == "protected by the Order of Dawn"
    assert edges.data[0].source_status == GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
    assert edges.data[0].canon_status == GRAPH_CANON_STATUS_SOURCE_REFERENCE
    assert edges.data[0].evidence_count == 1
    assert evidence.data[0].source_asset_id == "asset-graph-extraction-valid"
    assert evidence.data[0].chunk_id == chunk.chunk_id
    assert evidence.data[0].section_id == "section-aileen-order"
    assert evidence.data[0].domain == chunk.domain
    assert evidence.data[0].domain_path == chunk.domain_path
    assert evidence.data[0].commit_id == "commit-graph"
    assert evidence.data[0].excerpt == "Aileen is protected by the Order of Dawn."
    assert evidence.data[0].char_start == 0
    assert evidence.data[0].char_end == 42


@pytest.mark.asyncio
async def test_graph_extraction_invalid_structured_output_fails_without_partial_rows(
    retrieval_session,
):
    story_id = "story-graph-extraction-invalid"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-invalid",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-invalid"],
    )[0]

    failed = await MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_FakeGraphLlmGateway("not json"),
    ).process_job(story_id=story_id, graph_job_id=queued_job.graph_job_id)
    projection = MemoryGraphProjectionService(retrieval_session)

    assert failed.status == GRAPH_JOB_STATUS_FAILED
    assert failed.error_code == GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID
    assert failed.completed_at is not None
    assert projection.list_nodes(story_id=story_id).data == []
    assert projection.list_edges(story_id=story_id).data == []
    assert projection.list_evidence(story_id=story_id).data == []


@pytest.mark.asyncio
async def test_graph_extraction_invalid_schema_fails_without_partial_rows(
    retrieval_session,
):
    story_id = "story-graph-extraction-invalid-schema"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-invalid-schema",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-invalid-schema"],
    )[0]
    invalid_schema = json.dumps(
        {
            "entities": [
                {
                    "name": "Aileen",
                    "entity_type": "character",
                    "normalization_key": "character:aileen",
                }
            ],
            "relations": [
                {
                    "source_entity": "Aileen",
                    "target_entity": "Order of Dawn",
                    "relation_type": GRAPH_REL_AFFILIATED_WITH,
                }
            ],
            "warnings": [],
        }
    )

    failed = await MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_FakeGraphLlmGateway(invalid_schema),
    ).process_job(story_id=story_id, graph_job_id=queued_job.graph_job_id)
    projection = MemoryGraphProjectionService(retrieval_session)

    assert failed.status == GRAPH_JOB_STATUS_FAILED
    assert failed.error_code == GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID
    assert projection.list_nodes(story_id=story_id).data == []
    assert projection.list_edges(story_id=story_id).data == []
    assert projection.list_evidence(story_id=story_id).data == []


@pytest.mark.asyncio
async def test_graph_extraction_timeout_fails_job_without_partial_rows(
    retrieval_session,
):
    story_id = "story-graph-extraction-timeout"
    _seed_graph_extraction_config(
        retrieval_session,
        story_id=story_id,
        timeout_ms=1,
    )
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-timeout",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-timeout"],
    )[0]

    failed = await MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_HangingGraphLlmGateway(),
    ).process_job(story_id=story_id, graph_job_id=queued_job.graph_job_id)
    projection = MemoryGraphProjectionService(retrieval_session)

    assert failed.status == GRAPH_JOB_STATUS_FAILED
    assert failed.error_code == GRAPH_ERROR_EXTRACTION_TIMEOUT
    assert failed.completed_at is not None
    assert projection.list_nodes(story_id=story_id).data == []
    assert projection.list_edges(story_id=story_id).data == []
    assert projection.list_evidence(story_id=story_id).data == []


@pytest.mark.asyncio
async def test_graph_extraction_maps_unsupported_taxonomy_with_warnings(
    retrieval_session,
):
    story_id = "story-graph-extraction-taxonomy"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-taxonomy",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-taxonomy"],
    )[0]
    response = _graph_response(
        entities=[
            {
                "name": "Aileen",
                "entity_type": "heroic_figure",
                "normalization_key": "heroic_figure:aileen",
                "aliases": [],
                "confidence": 0.8,
            },
            {
                "name": "Order of Dawn",
                "entity_type": "faction_or_org",
                "aliases": ["the Order"],
                "confidence": 0.8,
            },
        ],
        relations=[
            {
                "source_entity": "Aileen",
                "target_entity": "Order of Dawn",
                "relation_type": "protects",
                "raw_relation_text": "protected by the Order of Dawn",
                "confidence": 0.7,
                "evidence": {
                    "excerpt": "Aileen is protected by the Order of Dawn.",
                    "char_start": 0,
                    "char_end": 42,
                },
            }
        ],
    )

    completed = await MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_FakeGraphLlmGateway(response),
    ).process_job(story_id=story_id, graph_job_id=queued_job.graph_job_id)
    projection = MemoryGraphProjectionService(retrieval_session)
    nodes = projection.list_nodes(story_id=story_id)
    edges = projection.list_edges(story_id=story_id)

    assert completed.status == GRAPH_JOB_STATUS_COMPLETED
    assert completed.warning_codes == [
        GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE,
        GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE,
        GRAPH_WARNING_MAPPED_TO_RELATED_TO,
    ]
    mapped_nodes = [
        node for node in nodes.data if node.type == GRAPH_ENTITY_TERM_OR_CONCEPT
    ]
    assert mapped_nodes
    assert mapped_nodes[0].normalization_key == "term_or_concept:aileen"
    assert edges.data[0].label == GRAPH_REL_RELATED_TO
    assert edges.data[0].raw_relation_text == "protected by the Order of Dawn"


@pytest.mark.asyncio
async def test_graph_extraction_alias_normalization_merge_and_dedupes_evidence(
    retrieval_session,
):
    story_id = "story-graph-extraction-merge"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-merge",
    )
    queued_job = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=["asset-graph-extraction-merge"],
    )[0]
    responses = [
        _graph_response(
            entities=[
                {
                    "name": "Aileen",
                    "entity_type": "character",
                    "normalization_key": "character:aileen",
                    "aliases": ["Ail"],
                    "confidence": 0.8,
                },
                {
                    "name": "Order of Dawn",
                    "entity_type": "faction_or_org",
                    "normalization_key": "faction_or_org:order-of-dawn",
                    "aliases": ["the Order"],
                    "confidence": 0.8,
                },
            ],
            relations=[
                {
                    "source_entity": "Aileen",
                    "target_entity": "Order of Dawn",
                    "relation_type": GRAPH_REL_AFFILIATED_WITH,
                    "raw_relation_text": "protected by the Order of Dawn",
                    "confidence": 0.8,
                    "evidence": {
                        "excerpt": "Aileen is protected by the Order of Dawn.",
                        "char_start": 0,
                        "char_end": 42,
                    },
                }
            ],
        ),
        _graph_response(
            entities=[
                {
                    "name": "Ailene",
                    "entity_type": "character",
                    "normalization_key": "character:aileen",
                    "aliases": ["Aileen"],
                    "confidence": 0.9,
                },
                {
                    "name": "The Order",
                    "entity_type": "faction_or_org",
                    "normalization_key": "faction_or_org:order-of-dawn",
                    "aliases": ["Order of Dawn"],
                    "confidence": 0.85,
                },
            ],
            relations=[
                {
                    "source_entity": "Ailene",
                    "target_entity": "The Order",
                    "relation_type": GRAPH_REL_AFFILIATED_WITH,
                    "raw_relation_text": "protected by the Order of Dawn",
                    "confidence": 0.9,
                    "evidence": {
                        "excerpt": "Aileen is protected by the Order of Dawn.",
                        "char_start": 0,
                        "char_end": 42,
                    },
                }
            ],
        ),
    ]
    extraction_service = MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_FakeGraphLlmGateway(responses),
    )

    first = await extraction_service.process_job(
        story_id=story_id,
        graph_job_id=queued_job.graph_job_id,
    )
    stored_job = retrieval_session.get(
        MemoryGraphExtractionJobRecord,
        queued_job.graph_job_id,
    )
    assert stored_job is not None
    stored_job.status = GRAPH_JOB_STATUS_QUEUED
    stored_job.error_code = None
    stored_job.error_message = None
    stored_job.completed_at = None
    retrieval_session.add(stored_job)
    retrieval_session.flush()
    second = await extraction_service.process_job(
        story_id=story_id,
        graph_job_id=queued_job.graph_job_id,
    )
    projection = MemoryGraphProjectionService(retrieval_session)
    nodes = projection.list_nodes(story_id=story_id)
    edges = projection.list_edges(story_id=story_id)
    evidence = projection.list_evidence(story_id=story_id)
    character = [
        node for node in nodes.data if node.normalization_key == "character:aileen"
    ][0]

    assert first.status == GRAPH_JOB_STATUS_COMPLETED
    assert second.status == GRAPH_JOB_STATUS_COMPLETED
    assert GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED in second.warning_codes
    assert len(nodes.data) == 2
    assert sorted(character.aliases) == ["Ail", "Aileen", "Ailene"]
    assert character.confidence == 0.9
    assert len(edges.data) == 1
    assert len(evidence.data) == 1


@pytest.mark.asyncio
async def test_graph_extraction_processes_story_queued_jobs(retrieval_session):
    story_id = "story-graph-extraction-story-queued"
    _seed_graph_extraction_config(retrieval_session, story_id=story_id)
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-story-queued-a",
    )
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graph-extraction-story-queued-b",
    )
    jobs = MemoryGraphProjectionService(
        retrieval_session
    ).queue_archival_extraction_jobs(
        story_id=story_id,
        source_asset_ids=[
            "asset-graph-extraction-story-queued-a",
            "asset-graph-extraction-story-queued-b",
        ],
    )
    response = _graph_response(
        entities=[
            {
                "name": "Aileen",
                "entity_type": "character",
                "normalization_key": "character:aileen",
                "aliases": [],
            }
        ],
        relations=[],
    )

    results = await MemoryGraphExtractionService(
        retrieval_session,
        llm_gateway=_FakeGraphLlmGateway([response, response]),
    ).process_story_queued_jobs(story_id=story_id, limit=10)

    assert len(jobs) == 2
    assert [item.status for item in results] == [
        GRAPH_JOB_STATUS_COMPLETED,
        GRAPH_JOB_STATUS_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_existing_archival_retrieval_works_without_graph_rows(retrieval_session):
    story_id = "story-graphless-archival"
    _seed_archival_asset(
        retrieval_session,
        story_id=story_id,
        asset_id="asset-graphless-foundation",
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id=story_id)
    result = await broker.search_archival(
        MemorySearchArchivalInput(
            query="Order of Dawn",
            domains=[Domain.WORLD_RULE],
            top_k=3,
        )
    )
    maintenance = MemoryGraphProjectionService(
        retrieval_session
    ).get_maintenance_snapshot(story_id=story_id)

    assert result.hits
    assert result.hits[0].metadata["asset_id"] == "asset-graphless-foundation"
    assert maintenance.node_count == 0
    assert maintenance.edge_count == 0
