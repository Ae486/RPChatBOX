"""Focused tests for governed Archival source evolution over retrieval-core."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_retrieval_store import (
    IndexJobRecord,
    KnowledgeChunkRecord,
    SourceAssetRecord,
)
from models.rp_story_store import BranchHeadRecord
from rp.models.archival_evolution import ArchivalEvolutionRequest
from rp.models.dsl import Domain
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_crud import MemorySearchArchivalInput
from rp.models.memory_materialization import (
    FOUNDATION_ENTRY_SOURCE_TYPE,
    SETUP_COMMIT_IMPORT_EVENT,
    build_archival_seed_section,
    build_archival_source_metadata,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.archival_evolution_service import ArchivalEvolutionService
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_index_job_service import RetrievalIndexJobService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story_session_service import StorySessionService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService


def _seed_runtime_identities(retrieval_session):
    story_service = StorySessionService(retrieval_session)
    story_session = story_service.create_session(
        story_id="story-archival-evolution",
        source_workspace_id="workspace-archival-evolution",
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    story_service.create_chapter_workspace(
        session_id=story_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={},
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.archival_evolution",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    main_branch = identity_service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    main_turn = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    sibling_branch = BranchHeadRecord(
        branch_head_id=f"branch:{story_session.session_id}:sibling",
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        branch_name="sibling",
        parent_branch_head_id=None,
        forked_from_turn_id=None,
        head_turn_id=None,
        status="active",
        visibility_scope="active_lineage",
    )
    retrieval_session.add(sibling_branch)
    retrieval_session.flush()
    sibling_turn = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=sibling_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    return (
        MemoryRuntimeIdentity(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            branch_head_id=main_branch.branch_head_id,
            turn_id=main_turn.turn_id,
            runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        ),
        MemoryRuntimeIdentity(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            branch_head_id=sibling_branch.branch_head_id,
            turn_id=sibling_turn.turn_id,
            runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        ),
    )


def _seed_archival_asset(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    asset_id: str,
    text: str,
) -> SourceAsset:
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=identity.story_id,
        scope="story",
        collection_kind="archival",
    )
    metadata = build_archival_source_metadata(
        source_type=FOUNDATION_ENTRY_SOURCE_TYPE,
        import_event=SETUP_COMMIT_IMPORT_EVENT,
        workspace_id="workspace-archival-evolution",
        commit_id="commit-archival-evolution",
        step_id="foundation",
        source_ref=f"setup_commit:commit-archival-evolution:{asset_id}",
        domain=Domain.WORLD_RULE.value,
        domain_path=f"foundation.world.{asset_id}",
        extra={"title": f"Archival {asset_id}"},
    )
    metadata["seed_sections"] = [
        build_archival_seed_section(
            section_id=f"foundation:{asset_id}",
            title=f"Archival {asset_id}",
            path=f"foundation.world.{asset_id}",
            text=text,
            metadata=metadata,
            tags=["archival", "world_rule"],
        )
    ]
    asset = SourceAsset(
        asset_id=asset_id,
        story_id=identity.story_id,
        mode=StoryMode.LONGFORM,
        collection_id=collection.collection_id,
        workspace_id="workspace-archival-evolution",
        step_id="foundation",
        commit_id="commit-archival-evolution",
        asset_kind=FOUNDATION_ENTRY_SOURCE_TYPE,
        source_ref=f"memory://{asset_id}",
        title=f"Archival {asset_id}",
        parse_status="queued",
        ingestion_status="queued",
        mapped_targets=["foundation"],
        metadata=metadata,
        created_at=story_time(),
        updated_at=story_time(),
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(asset)
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id=identity.story_id,
        asset_id=asset_id,
        collection_id=collection.collection_id,
    )
    retrieval_session.flush()
    return asset


def _seed_non_archival_asset(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    asset_id: str,
) -> SourceAsset:
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=identity.story_id,
        scope="story",
        collection_kind="recall",
    )
    asset = SourceAsset(
        asset_id=asset_id,
        story_id=identity.story_id,
        mode=StoryMode.LONGFORM,
        collection_id=collection.collection_id,
        workspace_id="workspace-archival-evolution",
        step_id="chapter-close",
        commit_id="commit-recall",
        asset_kind="accepted_story_segment",
        source_ref=f"memory://{asset_id}",
        title=f"Recall {asset_id}",
        parse_status="completed",
        ingestion_status="completed",
        mapped_targets=["chapter"],
        metadata={
            "layer": "recall",
            "source_family": "longform_story_runtime",
            "materialized_to_recall": True,
            "materialized_to_archival": False,
        },
        created_at=story_time(),
        updated_at=story_time(),
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(asset)
    retrieval_session.flush()
    return asset


def story_time():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


class _FailingReindexService(RetrievalIngestionService):
    def __init__(self, retrieval_session) -> None:
        self._session = retrieval_session
        self._index_job_service = RetrievalIndexJobService(retrieval_session)

    def reindex_asset(self, *, story_id: str, asset_id: str):
        job = self._index_job_service.submit_reindex_job(
            story_id=story_id,
            target_refs=[f"asset:{asset_id}"],
        )
        self._session.flush()
        return self._index_job_service.update_job_state(
            job_id=job.job_id,
            state="failed",
            warnings=["stub_reindex_failure"],
            error_message="stub reindex failure",
            completed_at=story_time(),
        )


@pytest.mark.asyncio
async def test_archival_evolution_defaults_to_current_branch_visibility(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-branch-default",
        text="seedglobalanchor original setup law is visible to every branch.",
    )
    sibling_before = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=sibling_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="seedglobalanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    assert [hit.metadata["asset_id"] for hit in sibling_before.hits] == [
        "asset-branch-default"
    ]

    receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-branch-default",
            expected_source_version=1,
            replacement_sections=[
                {
                    "text": "branchonlyanchor replacement law only belongs to main.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-branch-default",
                    },
                }
            ],
            source_refs=[
                MemorySourceRef(
                    source_type="story_turn",
                    source_id=main_identity.turn_id,
                    layer="runtime_identity",
                )
            ],
        )
    )
    retrieval_session.flush()

    main_result = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=main_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="branchonlyanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    sibling_result = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=sibling_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="branchonlyanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )

    assert main_result.hits
    assert main_result.hits[0].metadata["asset_id"] == receipt.source_asset_id
    assert main_result.hits[0].metadata["visibility_scope"] == "current_branch"
    assert main_result.hits[0].metadata["owning_branch_head_id"] == (
        main_identity.branch_head_id
    )
    assert sibling_result.hits == []


@pytest.mark.asyncio
async def test_archival_evolution_selected_branch_widening_is_explicit(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-selected-visibility",
        text="selectedoldanchor original law.",
    )

    receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-selected-visibility",
            visibility_scope="selected_branches",
            selected_branch_head_ids=[
                main_identity.branch_head_id,
                sibling_identity.branch_head_id,
            ],
            replacement_sections=[
                {
                    "text": "selectedwideanchor replacement law shared with sibling.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-selected-visibility",
                    },
                }
            ],
        )
    )
    sibling_result = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=sibling_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="selectedwideanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )

    assert receipt.selected_branch_head_ids == [
        main_identity.branch_head_id,
        sibling_identity.branch_head_id,
    ]
    assert sibling_result.hits
    assert sibling_result.hits[0].metadata["visibility_scope"] == "selected_branches"
    assert sibling_result.hits[0].metadata["selected_branch_head_ids"] == (
        receipt.selected_branch_head_ids
    )


@pytest.mark.asyncio
async def test_archival_evolution_records_version_reindex_event_and_excludes_old(
    retrieval_session,
):
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-versioned-provenance",
        text="oldprovenanceanchor original law should disappear from active search.",
    )

    receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-versioned-provenance",
            expected_source_version=1,
            replacement_sections=[
                {
                    "text": "newprovenanceanchor replacement law cites exact versions.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-versioned-provenance",
                    },
                }
            ],
            reason="correct foundation law",
        )
    )
    retrieval_session.flush()

    old_asset = retrieval_session.get(SourceAssetRecord, "asset-versioned-provenance")
    new_asset = retrieval_session.get(SourceAssetRecord, receipt.source_asset_id)
    reindex_job = retrieval_session.get(IndexJobRecord, receipt.reindex_job_ids[0])
    old_active_chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord)
        .where(KnowledgeChunkRecord.asset_id == "asset-versioned-provenance")
        .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
    ).all()
    new_chunk = retrieval_session.get(
        KnowledgeChunkRecord, receipt.replacement_chunk_ids[0]
    )
    events = MemoryChangeEventService(session=retrieval_session).list_events(
        identity=main_identity,
        layer="archival",
        event_kind="archival_source_evolved",
    )
    old_search = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=main_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="oldprovenanceanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    new_search = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=main_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="newprovenanceanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )

    assert old_asset is not None
    assert new_asset is not None
    assert reindex_job is not None
    assert new_chunk is not None
    assert old_asset.metadata_json["visibility_state"] == "superseded"
    assert old_asset.metadata_json["superseded_by_source_asset_id"] == (
        receipt.source_asset_id
    )
    assert new_asset.metadata_json["source_version"] == 2
    assert new_asset.metadata_json["supersedes_source_asset_id"] == (
        "asset-versioned-provenance"
    )
    assert reindex_job.job_kind == "reindex"
    assert reindex_job.asset_id == receipt.source_asset_id
    assert old_active_chunks == []
    assert new_chunk.metadata_json["archival_evolution_id"] == receipt.evolution_id
    assert new_chunk.metadata_json["source_version"] == 2
    assert new_chunk.metadata_json["chunk_version"] == 2
    assert f"archival_evolution:{receipt.evolution_id}" in (
        new_chunk.provenance_refs_json
    )
    assert receipt.event_ids == [events[0].event_id]
    assert events[0].metadata["reindex_job_id"] == receipt.reindex_job_ids[0]
    assert events[0].metadata["replacement_chunk_ids"] == receipt.replacement_chunk_ids
    assert all(
        hit.metadata["asset_id"] != "asset-versioned-provenance"
        for hit in old_search.hits
    )
    assert all("oldprovenanceanchor" not in hit.excerpt_text for hit in old_search.hits)
    assert new_search.hits
    assert new_search.hits[0].metadata["source_version"] == 2
    assert new_search.hits[0].metadata["archival_evolution_id"] == (
        receipt.evolution_id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility_state", ["hidden", "superseded"])
async def test_archival_runtime_search_excludes_hidden_or_superseded_active_chunks(
    retrieval_session,
    visibility_state: str,
):
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    asset_id = f"asset-{visibility_state}-active-exclusion"
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id=asset_id,
        text=f"{visibility_state}activeanchor archival law should not surface.",
    )
    chunk = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.asset_id == asset_id)
    ).first()
    assert chunk is not None
    chunk.metadata_json = {
        **dict(chunk.metadata_json or {}),
        "visibility_scope": "story_global",
        "visibility_state": visibility_state,
    }
    chunk.is_active = True
    retrieval_session.add(chunk)
    retrieval_session.flush()

    result = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=main_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query=f"{visibility_state}activeanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )

    assert result.hits == []
    assert any(
        warning.startswith("runtime_branch_visibility_filtered:")
        for warning in result.warnings
    )


def test_archival_evolution_failed_reindex_stays_traceable(retrieval_session):
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-failed-reindex",
        text="failedreindexoldanchor original law remains active until reindex works.",
    )

    receipt = ArchivalEvolutionService(
        retrieval_session,
        ingestion_service=_FailingReindexService(retrieval_session),
    ).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-failed-reindex",
            expected_source_version=1,
            replacement_sections=[
                {
                    "text": "failedreindexnewanchor replacement awaits retry.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-failed-reindex",
                    },
                }
            ],
        )
    )
    retrieval_session.flush()

    job_record = retrieval_session.get(IndexJobRecord, receipt.reindex_job_ids[0])
    old_asset = retrieval_session.get(SourceAssetRecord, "asset-failed-reindex")
    new_asset = retrieval_session.get(SourceAssetRecord, receipt.source_asset_id)
    events = MemoryChangeEventService(session=retrieval_session).list_events(
        identity=main_identity,
        layer="archival",
        event_kind="archival_source_evolved",
    )

    assert job_record is not None
    assert old_asset is not None
    assert new_asset is not None
    assert receipt.replacement_chunk_ids == []
    assert receipt.event_ids == [events[0].event_id]
    assert receipt.warnings == [
        f"archival_evolution_reindex_not_completed:{job_record.job_id}:failed"
    ]
    assert job_record.job_state == "failed"
    assert job_record.error_message == "stub reindex failure"
    assert job_record.asset_id == receipt.source_asset_id
    assert old_asset.metadata_json["visibility_state"] == "active"
    assert old_asset.metadata_json.get("superseded_by_source_asset_id") is None
    assert new_asset.metadata_json["source_version"] == 2
    assert new_asset.metadata_json["visibility_scope"] == "current_branch"
    assert events[0].metadata["warnings"] == receipt.warnings
    assert events[0].metadata["reindex_job_id"] == job_record.job_id
    assert any(
        ref.source_type == "retrieval_index_job" and ref.source_id == job_record.job_id
        for ref in events[0].source_refs
    )


def test_archival_evolution_rejects_non_archival_source_asset(retrieval_session):
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_non_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-recall-not-archival",
    )

    with pytest.raises(
        ValueError,
        match="archival_evolution_non_archival_source:asset-recall-not-archival",
    ):
        ArchivalEvolutionService(retrieval_session).evolve_source(
            ArchivalEvolutionRequest(
                identity=main_identity,
                actor="writer",
                source_asset_id="asset-recall-not-archival",
                replacement_sections=[
                    {
                        "text": "invalid archival replacement",
                        "metadata": {"domain": Domain.WORLD_RULE.value},
                    }
                ],
            )
        )


def test_archival_evolution_event_domain_follows_source_asset_domain(
    retrieval_session,
):
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-character-domain",
        text="characterdomainoldanchor original character dossier.",
    )
    source_record = retrieval_session.get(SourceAssetRecord, "asset-character-domain")
    assert source_record is not None
    source_record.metadata_json = {
        **dict(source_record.metadata_json or {}),
        "domain": Domain.CHARACTER.value,
        "domain_path": "foundation.character.asset-character-domain",
    }
    retrieval_session.add(source_record)
    retrieval_session.flush()

    receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-character-domain",
            replacement_sections=[
                {
                    "text": "characterdomainnewanchor replacement character dossier.",
                }
            ],
        )
    )
    events = MemoryChangeEventService(session=retrieval_session).list_events(
        identity=main_identity,
        layer="archival",
        event_kind="archival_source_evolved",
    )

    assert receipt.event_ids == [events[0].event_id]
    assert events[0].domain == Domain.CHARACTER.value
    assert events[0].block_id == f"{Domain.CHARACTER.value}.archival"
