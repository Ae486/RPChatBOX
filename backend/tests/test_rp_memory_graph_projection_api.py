"""Contract tests for Memory Graph Projection inspection API endpoints."""

from __future__ import annotations

from sqlmodel import Session

from rp.models.memory_graph_projection import (
    GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    GRAPH_JOB_REASON_MANUAL_RETRY,
    GRAPH_JOB_STATUS_FAILED,
    GRAPH_REL_MEMBER_OF,
    MemoryGraphEdgeUpsert,
    MemoryGraphEvidenceUpsert,
    MemoryGraphExtractionJobUpsert,
    MemoryGraphNodeUpsert,
)
from rp.services.memory_graph_projection_service import MemoryGraphProjectionService
from services.database import get_engine


def _seed_api_graph() -> None:
    with Session(get_engine()) as session:
        MemoryGraphProjectionService(session).upsert_seed_graph(
            story_id="story-api-graph",
            nodes=[
                MemoryGraphNodeUpsert(
                    node_id="api-node-character",
                    entity_type="character",
                    canonical_name="Mira",
                    confidence=0.82,
                    normalization_key="character:mira",
                ),
                MemoryGraphNodeUpsert(
                    node_id="api-node-faction",
                    entity_type="faction_or_org",
                    canonical_name="Cartographers Guild",
                    confidence=0.79,
                    normalization_key="faction_or_org:cartographers-guild",
                ),
            ],
            edges=[
                MemoryGraphEdgeUpsert(
                    edge_id="api-edge-member",
                    source_node_id="api-node-character",
                    target_node_id="api-node-faction",
                    source_entity_name="Mira",
                    target_entity_name="Cartographers Guild",
                    relation_type=GRAPH_REL_MEMBER_OF,
                    raw_relation_text="Mira belongs to the Cartographers Guild",
                    confidence=0.75,
                )
            ],
            evidence=[
                MemoryGraphEvidenceUpsert(
                    evidence_id="api-evidence-member",
                    edge_id="api-edge-member",
                    source_family="setup_source",
                    source_type="foundation_entry",
                    source_ref="setup_commit:commit-api:mira",
                    source_asset_id="asset-api-graph",
                    chunk_id="chunk-api-graph",
                    section_id="section-api-graph",
                    evidence_excerpt="Mira belongs to the Cartographers Guild.",
                )
            ],
            jobs=[
                MemoryGraphExtractionJobUpsert(
                    graph_job_id="api-graph-job-failed",
                    source_asset_id="asset-api-graph",
                    input_fingerprint="api:fingerprint:v1",
                    status=GRAPH_JOB_STATUS_FAILED,
                    queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
                )
            ],
        )
        session.commit()


def test_graph_inspection_api_returns_visualization_ready_payloads(client):
    _seed_api_graph()

    maintenance = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/maintenance"
    )
    nodes = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/nodes",
        params={"entity_type": "character"},
    )
    edges = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/edges",
        params={"relation_type": GRAPH_REL_MEMBER_OF},
    )
    evidence = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/evidence",
        params={"edge_id": "api-edge-member"},
    )
    neighborhood = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/neighborhood",
        params={"node_id": "api-node-character", "max_depth": 1},
    )
    capped_neighborhood = client.get(
        "/api/rp/retrieval/stories/story-api-graph/graph/neighborhood",
        params={"node_id": "api-node-character", "max_depth": 1, "max_nodes": 1},
    )
    retry = client.post(
        "/api/rp/retrieval/stories/story-api-graph/graph/retry",
        json={"limit": 5},
    )

    assert maintenance.status_code == 200
    assert maintenance.json()["graph_backend"] == "postgres_lightweight"
    assert maintenance.json()["node_count"] == 2
    assert maintenance.json()["edge_count"] == 1
    assert maintenance.json()["evidence_count"] == 1

    assert nodes.status_code == 200
    assert nodes.json()["object"] == "list"
    assert nodes.json()["data"][0]["label"] == "Mira"
    assert nodes.json()["data"][0]["type"] == "character"

    assert edges.status_code == 200
    assert edges.json()["data"][0]["source"] == "api-node-character"
    assert edges.json()["data"][0]["target"] == "api-node-faction"
    assert edges.json()["data"][0]["evidence_count"] == 1

    assert evidence.status_code == 200
    assert evidence.json()["data"][0]["source_asset_id"] == "asset-api-graph"
    assert evidence.json()["data"][0]["excerpt"] == (
        "Mira belongs to the Cartographers Guild."
    )

    assert neighborhood.status_code == 200
    payload = neighborhood.json()
    assert payload["graph_backend"] == "postgres_lightweight"
    assert {node["id"] for node in payload["nodes"]} == {
        "api-node-character",
        "api-node-faction",
    }
    assert payload["edges"][0]["id"] == "api-edge-member"
    assert payload["evidence"][0]["id"] == "api-evidence-member"

    assert capped_neighborhood.status_code == 200
    capped_payload = capped_neighborhood.json()
    assert capped_payload["truncated"] is True
    assert capped_payload["warnings"] == ["graph_neighborhood_truncated"]
    assert [node["id"] for node in capped_payload["nodes"]] == ["api-node-character"]
    assert capped_payload["edges"] == []

    assert retry.status_code == 200
    retry_payload = retry.json()
    assert retry_payload["object"] == "list"
    assert retry_payload["data"][0]["queued_reason"] == GRAPH_JOB_REASON_MANUAL_RETRY
    assert retry_payload["data"][0]["source_asset_id"] == "asset-api-graph"
