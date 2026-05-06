"""Tests for immutable runtime profile snapshot compilation and activation."""

from __future__ import annotations

from sqlmodel import select

from models.rp_story_store import RuntimeProfileSnapshotRecord
from rp.models.setup_drafts import StoryConfigDraft
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService


def _seed_story_session(
    retrieval_session,
    *,
    story_id: str,
    runtime_story_config: dict | None = None,
    setup_patch: StoryConfigDraft | None = None,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    if setup_patch is not None:
        workspace_service.patch_story_config(
            workspace_id=workspace.workspace_id,
            patch=setup_patch,
        )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config=runtime_story_config or {},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def test_compile_snapshot_is_deterministic_and_pins_minimum_profile(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-deterministic",
        runtime_story_config={
            "retrieval_embedding_model_id": "embed-session",
            "retrieval_embedding_provider_id": "provider-session",
            "graph_extraction_enabled": False,
            "model_profile_ref": "writer-profile-a",
            "worker_profile_ref": "worker-profile-a",
        },
        setup_patch=StoryConfigDraft(
            retrieval_rerank_model_id="rerank-setup",
            retrieval_rerank_provider_id="rerank-provider-setup",
        ),
    )
    service = RuntimeProfileSnapshotService(retrieval_session)

    first = service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.compile.first",
    )
    second = service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.compile.second",
    )

    assert first.status == "draft"
    assert second.status == "draft"
    assert first.compiled_profile_json == second.compiled_profile_json
    assert first.source_config_revision == second.source_config_revision
    assert set(first.compiled_profile_json) == {
        "mode_profile",
        "domain_activation",
        "block_activation",
        "worker_activation",
        "permission_profile",
        "retrieval_policy",
        "context_policy",
        "packet_policy",
        "writer_model_profile",
        "worker_model_profiles",
        "mode_specific_settings",
    }
    assert (
        first.compiled_profile_json["retrieval_policy"]["embedding_model_id"]
        == "embed-session"
    )
    assert (
        first.compiled_profile_json["retrieval_policy"]["rerank_model_id"]
        == "rerank-setup"
    )
    assert (
        first.compiled_profile_json["worker_activation"]["graph_extraction"]["active"]
        is False
    )
    worker_defaults = first.compiled_profile_json["permission_profile"][
        "worker_defaults"
    ]
    assert worker_defaults["specialist"]["refresh_projection"] is True
    assert worker_defaults["writer"]["refresh_projection"] is False
    assert worker_defaults["graph_extraction"]["read"] is True
    assert first.compiled_profile_json["mode_profile"]["mode"] == "longform"


def test_publish_snapshot_supersedes_previous_active_snapshot(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-publish",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)

    first = service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.publish.first",
    )
    second = service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.publish.second",
    )

    activated_first = service.publish_snapshot(first.runtime_profile_snapshot_id)
    activated_second = service.publish_snapshot(second.runtime_profile_snapshot_id)
    refreshed_first = service.require_snapshot(first.runtime_profile_snapshot_id)

    assert activated_first.activated_at is not None
    assert refreshed_first.status == "superseded"
    assert refreshed_first.superseded_at is not None
    assert refreshed_first.compiled_profile_json == first.compiled_profile_json
    assert activated_second.status == "active"
    assert activated_second.activated_at is not None


def test_ensure_active_snapshot_compiles_once_and_reuses_existing_active(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-ensure-active",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)

    first = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure",
    )
    second = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure.repeat",
    )
    rows = retrieval_session.exec(
        select(RuntimeProfileSnapshotRecord).where(
            RuntimeProfileSnapshotRecord.session_id == story_session.session_id
        )
    ).all()

    assert first.runtime_profile_snapshot_id == second.runtime_profile_snapshot_id
    assert first.status == "active"
    assert len(rows) == 1
