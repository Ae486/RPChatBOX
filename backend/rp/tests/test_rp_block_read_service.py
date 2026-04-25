"""Tests for read-only RP Block envelopes over Core State."""

from __future__ import annotations

from rp.models.dsl import Domain, Layer
from rp.models.story_runtime import LongformChapterPhase
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_repository import ProposalRepository
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService


def _seed_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-block-read",
        source_workspace_id="workspace-block-read",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Mirror Chapter"},
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
    chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Mirror foundation"],
            "blueprint_digest": ["Mirror blueprint"],
            "current_outline_digest": ["Mirror outline"],
            "recent_segment_digest": ["Mirror segment"],
            "current_state_digest": ["Mirror state"],
        },
    )
    return story_session_service, session, chapter


def _build_block_read_service(
    *,
    retrieval_session,
    story_session_service: StorySessionService,
    core_repo: CoreStateStoreRepository,
    store_read_enabled: bool,
) -> RpBlockReadService:
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_store_repository=core_repo,
        store_read_enabled=store_read_enabled,
    )
    builder_projection_context_service = BuilderProjectionContextService(
        projection_state_service
    )
    proposal_repository = ProposalRepository(retrieval_session)
    version_history_read_service = VersionHistoryReadService(
        adapter=StorySessionCoreStateAdapter(story_session_service),
        proposal_repository=proposal_repository,
        core_state_store_repository=core_repo,
        store_read_enabled=store_read_enabled,
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        proposal_repository=proposal_repository,
        version_history_read_service=version_history_read_service,
        core_state_store_repository=core_repo,
        store_read_enabled=store_read_enabled,
    )
    return RpBlockReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        core_state_store_repository=core_repo,
        memory_inspection_read_service=memory_inspection_read_service,
        store_read_enabled=store_read_enabled,
    )


def test_block_read_service_lists_formal_store_authoritative_and_projection_blocks(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_runtime(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        metadata_json={"test_marker": "formal_authoritative"},
        latest_apply_id="apply-formal-1",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    projection_row = core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=4,
        items_json=["Formal outline"],
        metadata_json={"test_marker": "formal_projection"},
        last_refresh_kind="test_refresh",
        payload_schema_ref="schema://core-state/projection-slot",
    )
    service = _build_block_read_service(
        retrieval_session=retrieval_session,
        story_session_service=story_session_service,
        core_repo=core_repo,
        store_read_enabled=True,
    )

    blocks = service.list_blocks(session_id=session.session_id)
    authoritative_block = next(
        block
        for block in blocks
        if block.block_id == authoritative_row.authoritative_object_id
    )
    projection_block = next(
        block for block in blocks if block.block_id == projection_row.projection_slot_id
    )

    assert (
        service.get_block(
            session_id=session.session_id,
            block_id=authoritative_row.authoritative_object_id,
        )
        == authoritative_block
    )
    assert authoritative_block.label == "chapter.current"
    assert authoritative_block.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert authoritative_block.domain == Domain.CHAPTER
    assert authoritative_block.domain_path == "chapter.current"
    assert authoritative_block.scope == "story"
    assert authoritative_block.revision == 3
    assert authoritative_block.source == "core_state_store"
    assert (
        authoritative_block.payload_schema_ref == "schema://core-state/chapter-current"
    )
    assert authoritative_block.data_json == {
        "current_chapter": 1,
        "title": "Formal Chapter",
    }
    assert authoritative_block.items_json is None
    assert authoritative_block.metadata["source_row_id"] == (
        authoritative_row.authoritative_object_id
    )
    assert authoritative_block.metadata["source_table"] == (
        "rp_core_state_authoritative_objects"
    )
    assert authoritative_block.metadata["session_id"] == session.session_id
    assert authoritative_block.metadata["latest_apply_id"] == "apply-formal-1"

    assert projection_block.label == "projection.current_outline_digest"
    assert projection_block.layer == Layer.CORE_STATE_PROJECTION
    assert projection_block.domain == Domain.CHAPTER
    assert projection_block.domain_path == "projection.current_outline_digest"
    assert projection_block.scope == "chapter"
    assert projection_block.revision == 4
    assert projection_block.source == "core_state_store"
    assert projection_block.payload_schema_ref == "schema://core-state/projection-slot"
    assert projection_block.data_json is None
    assert projection_block.items_json == ["Formal outline"]
    assert (
        projection_block.metadata["source_row_id"] == projection_row.projection_slot_id
    )
    assert projection_block.metadata["source_table"] == "rp_core_state_projection_slots"
    assert (
        projection_block.metadata["chapter_workspace_id"]
        == chapter.chapter_workspace_id
    )
    assert projection_block.metadata["last_refresh_kind"] == "test_refresh"


def test_block_read_service_lists_unmapped_formal_authoritative_rows(
    retrieval_session,
):
    story_session_service, session, _chapter = _seed_runtime(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    unmapped_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.WORLD_RULE.value,
        domain_path="world_rule.archive_policy",
        object_id="world_rule.archive_policy",
        scope="story",
        current_revision=7,
        data_json={"rule": "archive doors seal at dawn"},
        metadata_json={"test_marker": "unmapped_authoritative"},
        latest_apply_id="apply-unmapped-1",
        payload_schema_ref="schema://core-state/world-rule",
    )
    service = _build_block_read_service(
        retrieval_session=retrieval_session,
        story_session_service=story_session_service,
        core_repo=core_repo,
        store_read_enabled=True,
    )

    blocks = service.list_blocks(session_id=session.session_id)
    unmapped_block = next(
        block
        for block in blocks
        if block.block_id == unmapped_row.authoritative_object_id
    )

    assert unmapped_block.label == "world_rule.archive_policy"
    assert unmapped_block.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert unmapped_block.domain == Domain.WORLD_RULE
    assert unmapped_block.domain_path == "world_rule.archive_policy"
    assert unmapped_block.scope == "story"
    assert unmapped_block.revision == 7
    assert unmapped_block.source == "core_state_store"
    assert unmapped_block.payload_schema_ref == "schema://core-state/world-rule"
    assert unmapped_block.data_json == {"rule": "archive doors seal at dawn"}
    assert unmapped_block.metadata["source_row_id"] == (
        unmapped_row.authoritative_object_id
    )
    assert unmapped_block.metadata["source_table"] == (
        "rp_core_state_authoritative_objects"
    )
    assert unmapped_block.metadata["latest_apply_id"] == "apply-unmapped-1"


def test_block_read_service_lists_compatibility_mirror_blocks_when_store_is_empty(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_runtime(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    service = _build_block_read_service(
        retrieval_session=retrieval_session,
        story_session_service=story_session_service,
        core_repo=core_repo,
        store_read_enabled=True,
    )

    blocks = service.list_blocks(session_id=session.session_id)
    authoritative_block = next(
        block for block in blocks if block.label == "chapter.current"
    )
    projection_block = next(
        block for block in blocks if block.label == "projection.current_outline_digest"
    )

    assert authoritative_block.block_id == (
        "compatibility_mirror:core_state.authoritative:"
        f"{session.session_id}:chapter.current"
    )
    assert authoritative_block.source == "compatibility_mirror"
    assert authoritative_block.label == "chapter.current"
    assert authoritative_block.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert authoritative_block.domain == Domain.CHAPTER
    assert authoritative_block.domain_path == "chapter.current"
    assert authoritative_block.scope == "story"
    assert authoritative_block.revision == 1
    assert authoritative_block.data_json == {
        "current_chapter": 1,
        "title": "Mirror Chapter",
    }
    assert authoritative_block.metadata["route"] == "story_session.current_state_json"
    assert authoritative_block.metadata["source_field"] == "chapter_digest"
    assert authoritative_block.metadata["source_row_id"] is None
    assert authoritative_block.metadata["session_id"] == session.session_id

    assert projection_block.block_id == (
        "compatibility_mirror:core_state.projection:"
        f"{chapter.chapter_workspace_id}:projection.current_outline_digest"
    )
    assert projection_block.source == "compatibility_mirror"
    assert projection_block.label == "projection.current_outline_digest"
    assert projection_block.layer == Layer.CORE_STATE_PROJECTION
    assert projection_block.domain == Domain.CHAPTER
    assert projection_block.domain_path == "projection.current_outline_digest"
    assert projection_block.scope == "chapter"
    assert projection_block.revision == 1
    assert projection_block.items_json == ["Mirror outline"]
    assert projection_block.metadata["route"] == (
        "chapter_workspace.builder_snapshot_json"
    )
    assert projection_block.metadata["source_field"] == "current_outline_digest"
    assert projection_block.metadata["source_row_id"] is None
    assert projection_block.metadata["chapter_workspace_id"] == (
        chapter.chapter_workspace_id
    )


def test_block_read_service_respects_store_read_switch_when_rows_exist(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_runtime(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=9,
        data_json={"current_chapter": 1, "title": "Formal Hidden By Flag"},
    )
    core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=9,
        items_json=["Formal hidden by flag"],
        metadata_json={},
        last_refresh_kind="test_refresh",
    )
    service = _build_block_read_service(
        retrieval_session=retrieval_session,
        story_session_service=story_session_service,
        core_repo=core_repo,
        store_read_enabled=False,
    )

    blocks = service.list_blocks(session_id=session.session_id)
    authoritative_block = next(
        block for block in blocks if block.label == "chapter.current"
    )
    projection_block = next(
        block for block in blocks if block.label == "projection.current_outline_digest"
    )

    assert authoritative_block.source == "compatibility_mirror"
    assert authoritative_block.revision == 1
    assert authoritative_block.data_json["title"] == "Mirror Chapter"
    assert projection_block.source == "compatibility_mirror"
    assert projection_block.revision == 1
    assert projection_block.items_json == ["Mirror outline"]
