"""Tests for active-story Block consumer registry and lazy dirty evaluation."""

from __future__ import annotations

from datetime import datetime

from rp.models.dsl import Domain, Layer
from rp.models.story_runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
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
from rp.services.story_block_consumer_state_service import (
    StoryBlockConsumerStateService,
)
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None)


def _seed_consumer_story_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-consumer-registry",
        source_workspace_id="workspace-consumer-registry",
        mode="longform",
        runtime_story_config={},
        writer_contract={"style_rules": ["Lean"]},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "current_outline_digest": ["Outline A"],
        },
    )
    story_session_service.commit()
    return session, chapter, story_session_service


def _build_consumer_service(
    retrieval_session, story_session_service: StorySessionService
):
    proposal_repository = ProposalRepository(retrieval_session)
    core_state_store_repository = CoreStateStoreRepository(retrieval_session)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    builder_projection_context_service = BuilderProjectionContextService(
        projection_state_service=projection_state_service,
    )
    version_history_read_service = VersionHistoryReadService(
        adapter=StorySessionCoreStateAdapter(story_session_service),
        proposal_repository=proposal_repository,
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        proposal_repository=proposal_repository,
        version_history_read_service=version_history_read_service,
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    rp_block_read_service = RpBlockReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        core_state_store_repository=core_state_store_repository,
        memory_inspection_read_service=memory_inspection_read_service,
        store_read_enabled=True,
    )
    return (
        StoryBlockConsumerStateService(
            session=retrieval_session,
            story_session_service=story_session_service,
            rp_block_read_service=rp_block_read_service,
        ),
        core_state_store_repository,
    )


def test_story_block_consumer_state_service_tracks_lazy_dirty(retrieval_session):
    session, chapter, story_session_service = _seed_consumer_story_runtime(
        retrieval_session
    )
    consumer_state_service, core_repo = _build_consumer_service(
        retrieval_session,
        story_session_service,
    )
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter One"},
        metadata_json={"test_marker": "consumer_authoritative"},
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter One"},
        revision_source_kind="test",
        metadata_json={"test_marker": "consumer_authoritative_revision"},
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
        items_json=["Formal Outline A"],
        metadata_json={"test_marker": "consumer_projection"},
        last_refresh_kind="test_refresh",
    )
    core_repo.upsert_projection_slot_revision(
        projection_slot_id=projection_row.projection_slot_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        revision=4,
        items_json=["Formal Outline A"],
        refresh_source_kind="test_refresh",
        metadata_json={"test_marker": "consumer_projection_revision"},
    )

    consumers = {
        item.consumer_key: item
        for item in consumer_state_service.list_consumers(session_id=session.session_id)
    }

    assert set(consumers) == {
        "story.orchestrator",
        "story.specialist",
        "story.writer_packet",
    }
    assert consumers["story.orchestrator"].dirty is True
    assert consumers["story.orchestrator"].dirty_reasons == ["never_synced"]
    assert [
        item.label for item in consumers["story.writer_packet"].attached_blocks
    ] == ["projection.current_outline_digest"]

    writer_packet_consumer = consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )
    orchestrator_consumer = consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    specialist_consumer = consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.specialist",
    )

    assert writer_packet_consumer is not None and writer_packet_consumer.dirty is False
    assert orchestrator_consumer is not None and orchestrator_consumer.dirty is False
    assert specialist_consumer is not None and specialist_consumer.dirty is False

    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=5,
        data_json={"current_chapter": 1, "title": "Formal Chapter Two"},
        metadata_json={"test_marker": "consumer_authoritative"},
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=5,
        data_json={"current_chapter": 1, "title": "Formal Chapter Two"},
        revision_source_kind="test",
        metadata_json={"test_marker": "consumer_authoritative_revision_2"},
    )

    consumers_after_authoritative = {
        item.consumer_key: item
        for item in consumer_state_service.list_consumers(session_id=session.session_id)
    }
    assert consumers_after_authoritative["story.orchestrator"].dirty is True
    assert (
        "block_revision_changed"
        in consumers_after_authoritative["story.orchestrator"].dirty_reasons
    )
    assert consumers_after_authoritative["story.specialist"].dirty is True
    assert consumers_after_authoritative["story.writer_packet"].dirty is False

    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.specialist",
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
        current_revision=6,
        items_json=["Formal Outline B"],
        metadata_json={"test_marker": "consumer_projection"},
        last_refresh_kind="test_refresh",
    )
    core_repo.upsert_projection_slot_revision(
        projection_slot_id=projection_row.projection_slot_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        revision=6,
        items_json=["Formal Outline B"],
        refresh_source_kind="test_refresh",
        metadata_json={"test_marker": "consumer_projection_revision_2"},
    )

    consumers_after_projection = {
        item.consumer_key: item
        for item in consumer_state_service.list_consumers(session_id=session.session_id)
    }
    assert consumers_after_projection["story.writer_packet"].dirty is True
    assert (
        "block_revision_changed"
        in consumers_after_projection["story.writer_packet"].dirty_reasons
    )


def test_story_block_consumer_state_service_marks_chapter_change_dirty(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_consumer_story_runtime(
        retrieval_session
    )
    consumer_state_service, core_repo = _build_consumer_service(
        retrieval_session,
        story_session_service,
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
        items_json=["Formal Outline A"],
        metadata_json={"test_marker": "consumer_projection"},
        last_refresh_kind="test_refresh",
    )
    core_repo.upsert_projection_slot_revision(
        projection_slot_id=projection_row.projection_slot_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        revision=4,
        items_json=["Formal Outline A"],
        refresh_source_kind="test_refresh",
        metadata_json={"test_marker": "consumer_projection_revision"},
    )

    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )

    next_chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={},
    )
    story_session_service.update_session(
        session_id=session.session_id,
        current_chapter_index=next_chapter.chapter_index,
    )
    story_session_service.commit()

    writer_packet_consumer = consumer_state_service.get_consumer(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )

    assert writer_packet_consumer is not None
    assert writer_packet_consumer.dirty is True
    assert "chapter_workspace_changed" in writer_packet_consumer.dirty_reasons


def test_story_block_consumer_state_service_keeps_sync_timestamp_stable_for_same_snapshot(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_consumer_story_runtime(
        retrieval_session
    )
    consumer_state_service, core_repo = _build_consumer_service(
        retrieval_session,
        story_session_service,
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
        current_revision=4,
        items_json=["Formal Outline A"],
        metadata_json={"test_marker": "consumer_projection"},
        last_refresh_kind="test_refresh",
    )

    first = consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )
    second = consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )

    assert first is not None
    assert second is not None
    assert first.last_synced_at is not None
    assert _normalize_datetime(second.last_synced_at) == _normalize_datetime(
        first.last_synced_at
    )


def test_story_block_consumer_state_service_keeps_runtime_workspace_out_of_core_state_consumers(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_consumer_story_runtime(
        retrieval_session
    )
    consumer_state_service, core_repo = _build_consumer_service(
        retrieval_session,
        story_session_service,
    )
    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter One"},
        metadata_json={"test_marker": "consumer_authoritative"},
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
        current_revision=4,
        items_json=["Formal Outline A"],
        metadata_json={"test_marker": "consumer_projection"},
        last_refresh_kind="test_refresh",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.specialist",
    )

    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Runtime draft segment should not dirty core-state consumers",
        metadata={"command_kind": "write_next_segment"},
        revision=2,
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Runtime discussion should stay outside consumer attachments.",
    )

    orchestrator = consumer_state_service.get_consumer(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    specialist = consumer_state_service.get_consumer(
        session_id=session.session_id,
        consumer_key="story.specialist",
    )
    writer_packet = consumer_state_service.get_consumer(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )

    assert orchestrator is not None
    assert specialist is not None
    assert writer_packet is not None
    assert orchestrator.dirty is False
    assert specialist.dirty is False
    assert all(
        item.layer in {Layer.CORE_STATE_AUTHORITATIVE, Layer.CORE_STATE_PROJECTION}
        for item in orchestrator.attached_blocks
    )
    assert all(
        item.layer in {Layer.CORE_STATE_AUTHORITATIVE, Layer.CORE_STATE_PROJECTION}
        for item in specialist.attached_blocks
    )
    assert all(
        item.layer == Layer.CORE_STATE_PROJECTION
        for item in writer_packet.attached_blocks
    )
