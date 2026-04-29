"""Tests for setup-to-Archival retrieval ingestion metadata."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from models.rp_retrieval_store import KnowledgeChunkRecord, SourceAssetRecord
from models.rp_setup_store import (
    SetupAcceptedCommitRecord,
    SetupImportedAssetRecord,
    SetupRetrievalIngestionJobRecord,
    SetupWorkspaceRecord,
)
from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchArchivalInput
from rp.services.minimal_retrieval_ingestion_service import (
    MinimalRetrievalIngestionService,
)
from rp.services.retrieval_broker import RetrievalBroker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_workspace(retrieval_session) -> None:
    retrieval_session.add(
        SetupWorkspaceRecord(
            workspace_id="workspace-archival",
            story_id="story-archival",
            mode="longform",
            workspace_state="setup",
            current_step="foundation",
        )
    )


@pytest.mark.asyncio
async def test_setup_foundation_ingestion_generates_archival_metadata(
    retrieval_session,
):
    _seed_workspace(retrieval_session)
    retrieval_session.add(
        SetupAcceptedCommitRecord(
            commit_id="commit-foundation",
            workspace_id="workspace-archival",
            proposal_id="proposal-foundation",
            step_id="foundation",
            committed_refs_json=["foundation:magic-law"],
            snapshot_payload_json={
                "foundation": {
                    "entries": [
                        {
                            "entry_id": "magic-law",
                            "domain": "world",
                            "path": "magic-law",
                            "title": "Magic Law",
                            "content": {
                                "rule": "Dusk-sealed gates cannot be opened by ritual."
                            },
                            "tags": ["world", "law", "world"],
                            "source_refs": ["manual:1"],
                        }
                    ]
                }
            },
        )
    )
    retrieval_session.add(
        SetupRetrievalIngestionJobRecord(
            job_id="setup-job-foundation",
            workspace_id="workspace-archival",
            commit_id="commit-foundation",
            step_id="foundation",
            target_type="foundation_entry",
            target_ref="magic-law",
            state="queued",
        )
    )
    retrieval_session.commit()

    completed = MinimalRetrievalIngestionService(retrieval_session).ingest_commit(
        workspace_id="workspace-archival",
        commit_id="commit-foundation",
    )

    asset = retrieval_session.get(
        SourceAssetRecord,
        "commit-foundation:foundation_entry:magic-law",
    )
    chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.asset_id
            == "commit-foundation:foundation_entry:magic-law"
        )
    ).all()

    assert completed == ["setup-job-foundation"]
    assert asset is not None
    assert asset.metadata_json["layer"] == "archival"
    assert asset.metadata_json["source_family"] == "setup_source"
    assert asset.metadata_json["import_event"] == "setup.commit_ingest"
    assert asset.metadata_json["source_type"] == "foundation_entry"
    assert asset.metadata_json["materialized_to_archival"] is True
    assert asset.metadata_json["materialized_to_recall"] is False
    assert asset.metadata_json["authoritative_mutation"] is False
    assert asset.metadata_json["workspace_id"] == "workspace-archival"
    assert asset.metadata_json["commit_id"] == "commit-foundation"
    assert asset.metadata_json["step_id"] == "foundation"
    assert asset.metadata_json["source_ref"] == (
        "setup_commit:commit-foundation:magic-law"
    )
    assert asset.metadata_json["domain"] == "world_rule"
    assert asset.metadata_json["domain_path"] == "foundation.world.magic-law"
    seed_metadata = asset.metadata_json["seed_sections"][0]["metadata"]
    assert seed_metadata["layer"] == "archival"
    assert seed_metadata["source_family"] == "setup_source"
    assert seed_metadata["tags"] == ["world", "law"]
    assert chunks
    assert chunks[0].metadata_json["layer"] == "archival"
    assert chunks[0].metadata_json["source_family"] == "setup_source"

    result = await RetrievalBroker(default_story_id="story-archival").search_archival(
        MemorySearchArchivalInput(
            query="dusk-sealed gates ritual",
            domains=[Domain.WORLD_RULE],
            top_k=1,
        )
    )
    assert result.hits
    assert result.hits[0].metadata["layer"] == "archival"
    assert result.hits[0].metadata["source_family"] == "setup_source"
    assert result.hits[0].metadata["source_type"] == "foundation_entry"
    assert result.hits[0].metadata["import_event"] == "setup.commit_ingest"


def test_setup_asset_ingestion_overrides_conflicting_archival_metadata(
    retrieval_session,
):
    _seed_workspace(retrieval_session)
    retrieval_session.add(
        SetupAcceptedCommitRecord(
            commit_id="commit-asset",
            workspace_id="workspace-archival",
            proposal_id="proposal-asset",
            step_id="foundation",
            committed_refs_json=["asset:asset-hero"],
            snapshot_payload_json={},
        )
    )
    retrieval_session.add(
        SetupImportedAssetRecord(
            asset_id="asset-hero",
            workspace_id="workspace-archival",
            step_id="foundation",
            asset_kind="character_profile",
            source_ref="upload://hero.md",
            title="Hero Profile",
            mime_type="text/markdown",
            parse_status="parsed",
            parsed_payload_json={
                "sections": [
                    {
                        "section_id": "hero-profile",
                        "title": "Hero",
                        "path": "source.character.hero",
                        "level": 1,
                        "text": "The hero knows the dusk gate law.",
                        "metadata": {
                            "layer": "recall",
                            "source_family": "wrong_source",
                            "source_type": "wrong_type",
                            "materialized_to_archival": False,
                            "materialized_to_recall": True,
                            "authoritative_mutation": True,
                            "domain": "character",
                            "domain_path": "source.character.hero",
                            "tags": ["character", "profile", "character"],
                        },
                    }
                ]
            },
            mapped_targets_json=["character.hero"],
        )
    )
    retrieval_session.add(
        SetupRetrievalIngestionJobRecord(
            job_id="setup-job-asset",
            workspace_id="workspace-archival",
            commit_id="commit-asset",
            step_id="foundation",
            target_type="asset",
            target_ref="asset-hero",
            state="queued",
        )
    )
    retrieval_session.commit()

    MinimalRetrievalIngestionService(retrieval_session).ingest_commit(
        workspace_id="workspace-archival",
        commit_id="commit-asset",
    )

    asset = retrieval_session.get(SourceAssetRecord, "asset-hero")
    chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.asset_id == "asset-hero"
        )
    ).all()

    assert asset is not None
    assert asset.metadata_json["layer"] == "archival"
    assert asset.metadata_json["source_family"] == "setup_source"
    assert asset.metadata_json["source_type"] == "imported_asset"
    assert asset.metadata_json["source_ref"] == "upload://hero.md"
    assert asset.metadata_json["domain"] == "character"
    assert asset.metadata_json["domain_path"] == "source.character.hero"
    seed_metadata = asset.metadata_json["seed_sections"][0]["metadata"]
    assert seed_metadata["layer"] == "archival"
    assert seed_metadata["source_family"] == "setup_source"
    assert seed_metadata["source_type"] == "imported_asset"
    assert seed_metadata["materialized_to_archival"] is True
    assert seed_metadata["materialized_to_recall"] is False
    assert seed_metadata["authoritative_mutation"] is False
    assert seed_metadata["tags"] == ["character", "profile"]
    assert chunks
    assert chunks[0].metadata_json["layer"] == "archival"
    assert chunks[0].metadata_json["source_type"] == "imported_asset"


def test_setup_blueprint_ingestion_generates_archival_metadata(retrieval_session):
    _seed_workspace(retrieval_session)
    retrieval_session.add(
        SetupAcceptedCommitRecord(
            commit_id="commit-blueprint",
            workspace_id="workspace-archival",
            proposal_id="proposal-blueprint",
            step_id="longform_blueprint",
            committed_refs_json=["longform_blueprint"],
            snapshot_payload_json={
                "longform_blueprint": {
                    "premise": "A sealed-city archive controls every dusk gate.",
                    "chapter_blueprints": [
                        {
                            "chapter_id": "chapter-1",
                            "title": "Gate Oath",
                            "purpose": "Reveal the gate law.",
                            "major_beats": ["The hero reads the archive ledger."],
                            "setup_payoff_targets": ["dusk-gate-law"],
                        }
                    ],
                }
            },
        )
    )
    retrieval_session.add(
        SetupRetrievalIngestionJobRecord(
            job_id="setup-job-blueprint",
            workspace_id="workspace-archival",
            commit_id="commit-blueprint",
            step_id="longform_blueprint",
            target_type="blueprint",
            target_ref="longform_blueprint",
            state="queued",
        )
    )
    retrieval_session.commit()

    completed = MinimalRetrievalIngestionService(retrieval_session).ingest_commit(
        workspace_id="workspace-archival",
        commit_id="commit-blueprint",
    )

    asset = retrieval_session.get(
        SourceAssetRecord,
        "commit-blueprint:blueprint:longform_blueprint",
    )
    chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.asset_id
            == "commit-blueprint:blueprint:longform_blueprint"
        )
    ).all()

    assert completed == ["setup-job-blueprint"]
    assert asset is not None
    assert asset.metadata_json["layer"] == "archival"
    assert asset.metadata_json["source_family"] == "setup_source"
    assert asset.metadata_json["source_type"] == "longform_blueprint"
    assert asset.metadata_json["import_event"] == "setup.commit_ingest"
    assert asset.metadata_json["domain"] == "chapter"
    assert asset.metadata_json["domain_path"] == "longform_blueprint.premise"
    assert len(asset.metadata_json["seed_sections"]) == 2
    assert {
        section["metadata"]["source_type"]
        for section in asset.metadata_json["seed_sections"]
    } == {"longform_blueprint"}
    assert {
        tuple(section["metadata"]["tags"])
        for section in asset.metadata_json["seed_sections"]
    } == {("blueprint",), ("blueprint", "chapter")}
    assert chunks
    assert {chunk.metadata_json["source_type"] for chunk in chunks} == {
        "longform_blueprint"
    }
