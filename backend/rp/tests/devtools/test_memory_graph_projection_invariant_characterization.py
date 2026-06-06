"""Pre-refactor characterization for MemoryGraphProjection repository invariants.

These tests pin the current repository entry behavior before aggregate-boundary
refactoring. They are not curve-fit expectations: validation happens at the
repository command entries, and the repository owns flush visibility for the rows
it writes.
"""

from __future__ import annotations

from typing import Any

import pytest

from models.rp_retrieval_store import MemoryGraphNodeRecord
from rp.models.memory.graph_projection import (
    GRAPH_EDGE_DIRECTION_DIRECTED,
    GRAPH_ENTITY_CHARACTER,
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_REL_AFFILIATED_WITH,
    MemoryGraphEdgeUpsert,
    MemoryGraphEvidenceUpsert,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphNodeUpsert,
)
from rp.services.memory.graph_projection_repository import (
    MemoryGraphProjectionRepository,
)


def _valid_node_upsert(**overrides: Any) -> MemoryGraphNodeUpsert:
    payload: dict[str, Any] = {
        "node_id": "graph-node-aileen",
        "workspace_id": "workspace-graph",
        "entity_type": GRAPH_ENTITY_CHARACTER,
        "canonical_name": "Aileen",
        "aliases": ["Ail"],
        "confidence": 0.91,
        "first_seen_source_ref": "setup_commit:commit-graph:asset-graph-foundation",
        "normalization_key": "character:aileen",
    }
    payload.update(overrides)
    return MemoryGraphNodeUpsert(**payload)


def _valid_edge_upsert(**overrides: Any) -> MemoryGraphEdgeUpsert:
    payload: dict[str, Any] = {
        "edge_id": "graph-edge-aileen-order",
        "workspace_id": "workspace-graph",
        "source_node_id": "graph-node-aileen",
        "target_node_id": "graph-node-order",
        "source_entity_name": "Aileen",
        "target_entity_name": "Order of Dawn",
        "relation_type": GRAPH_REL_AFFILIATED_WITH,
        "raw_relation_text": "protected by the Order of Dawn",
        "confidence": 0.84,
        "direction": GRAPH_EDGE_DIRECTION_DIRECTED,
    }
    payload.update(overrides)
    return MemoryGraphEdgeUpsert(**payload)


def _valid_evidence_upsert(**overrides: Any) -> MemoryGraphEvidenceUpsert:
    payload: dict[str, Any] = {
        "evidence_id": "graph-evidence-aileen-order",
        "workspace_id": "workspace-graph",
        "edge_id": "graph-edge-aileen-order",
        "source_family": "setup_source",
        "source_type": "foundation_entry",
        "import_event": "setup.commit_ingest",
        "source_ref": "setup_commit:commit-graph:asset-graph-foundation",
        "source_asset_id": "asset-graph-foundation",
        "collection_id": "collection-graph",
        "parsed_document_id": "document-graph",
        "chunk_id": "chunk-graph",
        "section_id": "section-aileen-order",
        "domain": "world_rule",
        "domain_path": "foundation.world.order",
        "commit_id": "commit-graph",
        "evidence_excerpt": "Aileen is protected by the Order of Dawn.",
    }
    payload.update(overrides)
    return MemoryGraphEvidenceUpsert(**payload)


def _valid_job_upsert(**overrides: Any) -> MemoryGraphExtractionJobUpsert:
    payload: dict[str, Any] = {
        "graph_job_id": "graph-job-aileen-order",
        "workspace_id": "workspace-graph",
        "commit_id": "commit-graph",
        "source_asset_id": "asset-graph-foundation",
        "chunk_id": "chunk-graph",
        "input_fingerprint": "fingerprint:graph-foundation:v1",
        "status": GRAPH_JOB_STATUS_QUEUED,
    }
    payload.update(overrides)
    return MemoryGraphExtractionJobUpsert(**payload)


def test_upsert_node_validates_entity_type_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError):
        repository.upsert_node(
            story_id="story-graph-invariant",
            node=_valid_node_upsert(entity_type="scene"),
        )


def test_upsert_node_validates_source_layer_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError):
        repository.upsert_node(
            story_id="story-graph-invariant",
            node=_valid_node_upsert(source_layer="runtime"),
        )


def test_upsert_edge_validates_relation_type_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError):
        repository.upsert_edge(
            story_id="story-graph-invariant",
            edge=_valid_edge_upsert(relation_type="protects"),
        )


def test_upsert_edge_validates_direction_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError):
        repository.upsert_edge(
            story_id="story-graph-invariant",
            edge=_valid_edge_upsert(direction="bidirectional"),
        )


def test_upsert_evidence_requires_node_or_edge_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError, match="Graph evidence requires node_id or edge_id"):
        repository.upsert_evidence(
            story_id="story-graph-invariant",
            evidence=_valid_evidence_upsert(node_id=None, edge_id=None),
        )


def test_upsert_job_validates_status_at_entry(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)

    with pytest.raises(ValueError):
        repository.upsert_job(
            story_id="story-graph-invariant",
            job=_valid_job_upsert(status="waiting"),
        )


def test_upsert_node_flushes_record_before_return(retrieval_session) -> None:
    repository = MemoryGraphProjectionRepository(retrieval_session)
    node_id = "graph-node-flush-visible"

    repository.upsert_node(
        story_id="story-graph-flush",
        node=_valid_node_upsert(node_id=node_id),
    )

    with retrieval_session.no_autoflush:
        stored = retrieval_session.get(MemoryGraphNodeRecord, node_id)

    assert stored is not None
    assert stored.story_id == "story-graph-flush"
    assert stored.node_id == node_id
