"""Focused tests for the minimal internal worker memory service path."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy

import pytest

from config import get_settings
from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import (
    MemoryGetSummaryInput,
    MemorySearchRecallInput,
    ProposalSubmitInput,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.models.projection_refresh import ProjectionRefreshRequest
from rp.models.worker_memory import WorkerMemoryContext
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.proposal.repository import ProposalRepository
from rp.services.retrieval.collection_service import RetrievalCollectionService
from rp.services.retrieval.document_service import RetrievalDocumentService
from rp.services.retrieval.ingestion_service import RetrievalIngestionService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.writer.worker_memory_service import (
    WorkerMemoryPermissionError,
    WorkerMemoryService,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enable_core_write(monkeypatch) -> None:
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_WRITE_ENABLED", "true")
    get_settings.cache_clear()


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id), chapter, service


def _seed_recall_asset(retrieval_session, *, story_id: str):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=story_id,
        scope="story",
        collection_kind="recall",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-worker-recall-1",
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="accepted_story_segment",
            source_ref="memory://worker-recall-1",
            title="Worker Recall",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["recall"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "seed:worker-recall-1",
                        "title": "Worker Recall",
                        "path": "chapter.recall.worker-recall-1",
                        "level": 1,
                        "text": "The seal broke during the first storm.",
                        "metadata": {
                            "domain": Domain.CHAPTER.value,
                            "domain_path": "chapter.recall.worker-recall-1",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id=story_id,
        asset_id="asset-worker-recall-1",
        collection_id=collection.collection_id,
    )


def _build_ctx(retrieval_session) -> tuple[WorkerMemoryContext, StorySessionService]:
    session, _chapter, story_session_service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.worker_memory",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="write_next_segment",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return (
        WorkerMemoryContext(
            identity=identity,
            worker_id="specialist",
            phase="outline_drafting",
            domain=Domain.CHAPTER.value,
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
        ),
        story_session_service,
    )


@pytest.mark.asyncio
async def test_worker_memory_service_search_materializes_retrieval_cards(
    retrieval_session,
):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    _seed_recall_asset(retrieval_session, story_id=ctx.identity.story_id)
    service = WorkerMemoryService(session=retrieval_session)

    result = await service.search_recall(
        ctx=ctx,
        input_model=MemorySearchRecallInput(
            query="storm",
            scope="story",
            domains=[Domain.CHAPTER],
        ),
    )

    assert result.hits
    assert ctx.trace_refs
    card_refs = [
        ref
        for ref in ctx.source_refs
        if ref.source_type == "runtime_workspace_material"
    ]
    assert card_refs


@pytest.mark.asyncio
async def test_worker_memory_service_rejects_disabled_worker(retrieval_session):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.require_snapshot(ctx.runtime_profile_snapshot_id)
    compiled = deepcopy(snapshot.compiled_profile_json or {})
    compiled["worker_activation"]["specialist"]["active"] = False
    snapshot.compiled_profile_json = compiled
    retrieval_session.add(snapshot)
    retrieval_session.commit()
    service = WorkerMemoryService(session=retrieval_session)

    with pytest.raises(WorkerMemoryPermissionError) as exc_info:
        await service.get_summary(
            ctx=ctx,
            input_model=MemoryGetSummaryInput(domains=[Domain.CHAPTER], scope="story"),
        )

    assert exc_info.value.code == "worker_memory_worker_disabled"
    assert exc_info.value.reason_codes == ["disabled_worker"]


@pytest.mark.asyncio
async def test_worker_memory_service_rejects_forbidden_operation_kind(
    retrieval_session,
):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    ctx = ctx.model_copy(update={"worker_id": "writer"})
    service = WorkerMemoryService(session=retrieval_session)

    with pytest.raises(WorkerMemoryPermissionError) as exc_info:
        await service.search_recall(
            ctx=ctx,
            input_model=MemorySearchRecallInput(
                query="storm",
                scope="story",
                domains=[Domain.CHAPTER],
            ),
        )

    assert exc_info.value.code == "worker_memory_operation_forbidden"
    assert exc_info.value.reason_codes == ["forbidden_operation_kind"]


def test_worker_memory_service_rejects_sparse_worker_permission_defaults(
    retrieval_session,
):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.require_snapshot(ctx.runtime_profile_snapshot_id)
    compiled = deepcopy(snapshot.compiled_profile_json or {})
    compiled["permission_profile"]["worker_defaults"]["specialist"] = {
        "read": True,
        "propose": True,
    }
    snapshot.compiled_profile_json = compiled
    retrieval_session.add(snapshot)
    retrieval_session.commit()
    service = WorkerMemoryService(session=retrieval_session)

    with pytest.raises(WorkerMemoryPermissionError) as exc_info:
        service.refresh_projection(ctx=ctx, request=ProjectionRefreshRequest())

    assert exc_info.value.code == "worker_memory_operation_forbidden"
    assert exc_info.value.reason_codes == ["forbidden_operation_kind"]


@pytest.mark.asyncio
async def test_worker_memory_service_rejects_forbidden_phase(retrieval_session):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    ctx = ctx.model_copy(update={"phase": "segment_drafting"})
    service = WorkerMemoryService(session=retrieval_session)

    with pytest.raises(WorkerMemoryPermissionError) as exc_info:
        await service.get_summary(
            ctx=ctx,
            input_model=MemoryGetSummaryInput(domains=[Domain.CHAPTER], scope="story"),
        )

    assert exc_info.value.code == "worker_memory_phase_forbidden"
    assert exc_info.value.reason_codes == ["forbidden_phase"]


@pytest.mark.asyncio
async def test_worker_memory_service_persists_governance_metadata_on_proposal(
    retrieval_session,
):
    ctx, story_session_service = _build_ctx(retrieval_session)
    service = WorkerMemoryService(session=retrieval_session)

    receipt = await service.submit_proposal(
        ctx=ctx,
        input_model=ProposalSubmitInput(
            story_id=ctx.identity.story_id,
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Worker Updated Chapter"},
                }
            ],
        ),
    )

    assert receipt.status == "review_required"
    repository = ProposalRepository(retrieval_session)
    record = repository.get_proposal_record(receipt.proposal_id)
    assert record is not None
    assert "worker=specialist" in record.submit_source
    assert "permission=allowed" in (record.trace_id or "")
    assert record.governance_metadata_json["identity"]["turn_id"] == (
        ctx.identity.turn_id
    )
    assert record.governance_metadata_json["worker_id"] == "specialist"
    assert record.governance_metadata_json["phase"] == "outline_drafting"
    assert record.governance_metadata_json["permission_decision"] == "allowed"
    assert repository.list_apply_receipts_for_proposal(receipt.proposal_id) == []
    updated_session = story_session_service.get_session(ctx.identity.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    )


@pytest.mark.asyncio
async def test_worker_memory_service_auto_apply_dual_writes_core_and_mirror(
    retrieval_session,
    monkeypatch,
):
    _enable_core_write(monkeypatch)
    ctx, story_session_service = _build_ctx(retrieval_session)
    service = WorkerMemoryService(session=retrieval_session)

    receipt = await service.submit_proposal(
        ctx=ctx,
        input_model=ProposalSubmitInput(
            story_id=ctx.identity.story_id,
            mode="longform",
            domain=Domain.TIMELINE,
            domain_path="timeline.event_spine",
            operations=[
                {
                    "kind": "append_event",
                    "target_ref": {
                        "object_id": "timeline.event_spine",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.TIMELINE,
                        "domain_path": "timeline.event_spine",
                    },
                    "event_data": {"event": "worker-auto-applied"},
                }
            ],
        ),
    )

    assert receipt.status == "applied"
    repository = ProposalRepository(retrieval_session)
    apply_receipts = repository.list_apply_receipts_for_proposal(receipt.proposal_id)
    assert len(apply_receipts) == 1
    assert apply_receipts[0].apply_backend == "core_state_store"
    target_links = repository.list_apply_target_links_for_apply(apply_receipts[0].apply_id)
    assert len(target_links) == 1
    assert target_links[0].object_id == "timeline.event_spine"

    core_repo = CoreStateStoreRepository(retrieval_session)
    current_row = core_repo.get_authoritative_object(
        session_id=ctx.identity.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        scope="story",
        object_id="timeline.event_spine",
    )
    assert current_row is not None
    # Worker proposals carry governance metadata (a core mutation envelope), so the
    # apply follows the governed base-seed-then-applied revision pattern: rev1 =
    # activation_seed (pre-apply base), rev2 = proposal_apply (the appended event).
    # (Ungoverned tool proposals produce a single revision.)
    assert current_row.current_revision == 2
    assert current_row.data_json == [{"event": "worker-auto-applied"}]
    revisions = core_repo.list_authoritative_revisions(
        session_id=ctx.identity.session_id,
        object_id="timeline.event_spine",
    )
    assert [revision.revision for revision in revisions] == [1, 2]
    assert revisions[1].source_apply_id == apply_receipts[0].apply_id

    updated_session = story_session_service.get_session(ctx.identity.session_id)
    assert updated_session is not None
    assert updated_session.current_state_json["timeline_spine"] == [
        {"event": "worker-auto-applied"}
    ]


def test_worker_memory_service_refresh_projection_injects_identity_and_actor(
    retrieval_session,
):
    ctx, _story_session_service = _build_ctx(retrieval_session)
    service = WorkerMemoryService(session=retrieval_session)
    request = ProjectionRefreshRequest()

    service.refresh_projection(ctx=ctx, request=request)

    assert request.identity == ctx.identity
    assert request.refresh_actor == "worker.specialist"
    assert request.refresh_source_ref == "worker_memory:specialist:outline_drafting"
