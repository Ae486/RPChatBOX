"""Write-authority characterization for story artifacts and discussion entries."""

from __future__ import annotations

import inspect

from models.rp_story_store import StoryDiscussionEntryRecord
from rp.devtools.check_story_session_write_boundary import (
    DEFAULT_BACKEND_ROOT,
    scan_story_session_write_boundary,
)
from rp.models.story.runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.story.session_service import StorySessionService


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-artifact-discussion-write-authority",
        source_workspace_id="workspace-artifact-discussion-write-authority",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "segment_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.SEGMENT_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        chapter_goal="Chapter 1",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return session, chapter, service


def test_artifact_create_resolves_scene_ref_and_creation_timestamps(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)

    segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Scene-local segment",
    )
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Chapter outline",
    )
    explicit_scene = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Explicit scene outline",
        scene_ref="chapter:1:scene:explicit",
    )

    assert segment.scene_ref == chapter.current_scene_ref
    assert outline.scene_ref is None
    assert explicit_scene.scene_ref == "chapter:1:scene:explicit"
    assert segment.created_at == segment.updated_at
    assert outline.created_at == outline.updated_at
    assert explicit_scene.created_at == explicit_scene.updated_at


def test_update_artifact_replaces_mutable_fields_and_preserves_partial_update(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    artifact = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Initial segment",
        metadata={"tone": "initial", "keep": "drop"},
        revision=1,
    )

    replacement_metadata = {"tone": "revised"}
    updated = service.update_artifact(
        artifact_id=artifact.artifact_id,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted segment",
        metadata=replacement_metadata,
        revision=2,
    )
    replacement_metadata["tone"] = "mutated-after-call"
    fetched_after_mutation = service.get_artifact(artifact.artifact_id)
    assert fetched_after_mutation is not None

    assert updated.status == StoryArtifactStatus.ACCEPTED
    assert updated.content_text == "Accepted segment"
    assert updated.metadata == {"tone": "revised"}
    assert updated.revision == 2
    assert updated.updated_at > artifact.created_at
    assert fetched_after_mutation.metadata == {"tone": "revised"}

    partial = service.update_artifact(
        artifact_id=artifact.artifact_id,
        content_text="Only content changes",
    )

    assert partial.status == StoryArtifactStatus.ACCEPTED
    assert partial.content_text == "Only content changes"
    assert partial.metadata == {"tone": "revised"}
    assert partial.revision == 2
    assert partial.updated_at > updated.updated_at


def test_discussion_entry_create_resolves_scene_and_passthrough_fields(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    artifact = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Linked segment",
    )

    omitted_scene = service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Keep the scene tight.",
        linked_artifact_id=artifact.artifact_id,
    )
    explicit_scene = service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Move this comment elsewhere.",
        linked_artifact_id=None,
        scene_ref="chapter:1:scene:manual",
    )

    assert omitted_scene.scene_ref == chapter.current_scene_ref
    assert omitted_scene.role == "assistant"
    assert omitted_scene.content_text == "Keep the scene tight."
    assert omitted_scene.linked_artifact_id == artifact.artifact_id
    assert explicit_scene.scene_ref == "chapter:1:scene:manual"
    assert explicit_scene.role == "user"
    assert explicit_scene.content_text == "Move this comment elsewhere."
    assert explicit_scene.linked_artifact_id is None


def test_discussion_entry_is_append_only_without_update_surface() -> None:
    update_discussion_methods = [
        name
        for name, member in inspect.getmembers(StorySessionService)
        if name.startswith("update_discussion") and callable(member)
    ]

    assert "updated_at" not in StoryDiscussionEntryRecord.model_fields
    assert not hasattr(StoryDiscussionEntryRecord, "updated_at")
    assert update_discussion_methods == []


def test_story_artifact_and_discussion_records_construct_only_in_session_service():
    result = scan_story_session_write_boundary(DEFAULT_BACKEND_ROOT)
    target_records = {"StoryArtifactRecord", "StoryDiscussionEntryRecord"}
    construction_findings = [
        finding
        for finding in result.allowed_authorized
        if finding.bypass_type == "construction" and finding.record in target_records
    ]

    assert construction_findings
    assert {
        finding.record for finding in construction_findings
    } == target_records
    assert {
        finding.path for finding in construction_findings
    } == {"rp/services/story/session_service.py"}
