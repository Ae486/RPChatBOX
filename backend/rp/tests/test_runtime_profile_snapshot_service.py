"""Tests for immutable runtime profile snapshot compilation and activation."""

from __future__ import annotations

from sqlmodel import select

from models.rp_story_store import RuntimeProfileSnapshotRecord, StorySessionRecord
from rp.models.runtime_identity import RuntimeProfileSnapshotCompiledProfile
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
    writer_contract: dict | None = None,
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
        writer_contract=writer_contract or {},
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
        "writer_policy",
        "post_write_policy",
        "budget_latency_policy",
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
    assert first.compiled_profile_json["writer_policy"] == {
        "supported_operation_modes": ["writing", "rewrite", "discussion"],
        "retrieval_mode": "bounded_tool_loop",
        "rewrite_requires_explicit_selection": True,
        "discussion_summary_enabled": True,
        "pov_rules": [],
        "style_rules": [],
        "writing_constraints": [],
        "task_writing_rules": [],
    }
    assert first.compiled_profile_json["post_write_policy"]["preset_id"] == "balanced"
    assert (
        first.compiled_profile_json["post_write_policy"]["fallback_decision"]
        == "review_required"
    )
    assert first.compiled_profile_json["budget_latency_policy"] == {
        "max_blocking_analysis_workers": 1,
        "max_writer_workers": 1,
        "token_usage_source": "provider_usage_metadata",
        "prewrite_estimation_enabled": True,
    }


def test_compile_snapshot_carries_writer_contract_and_post_write_preset(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-policy-shape",
        runtime_story_config={
            "post_write_policy_preset": "conservative",
        },
        writer_contract={
            "pov_rules": ["third_person_limited"],
            "style_rules": ["Keep continuity tight."],
            "writing_constraints": ["Avoid omniscient narration."],
            "task_writing_rules": ["Preserve review overlay intent."],
        },
        setup_patch=StoryConfigDraft(
            model_profile_ref="writer-profile-b",
            worker_profile_ref="worker-profile-b",
        ),
    )

    snapshot = RuntimeProfileSnapshotService(retrieval_session).compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.compile.policy_shape",
    )

    assert snapshot.compiled_profile_json["writer_policy"]["pov_rules"] == [
        "third_person_limited"
    ]
    assert snapshot.compiled_profile_json["writer_policy"]["style_rules"] == [
        "Keep continuity tight."
    ]
    assert snapshot.compiled_profile_json["writer_policy"]["writing_constraints"] == [
        "Avoid omniscient narration."
    ]
    assert snapshot.compiled_profile_json["writer_policy"]["task_writing_rules"] == [
        "Preserve review overlay intent."
    ]
    assert (
        snapshot.compiled_profile_json["post_write_policy"]["preset_id"]
        == "conservative"
    )


def test_compiled_profile_model_accepts_legacy_snapshot_without_new_policy_fields():
    compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
        {
            "mode_profile": {
                "mode": "longform",
                "registry_version": "bootstrap",
            },
            "domain_activation": {},
            "block_activation": {},
            "worker_activation": {},
            "permission_profile": {},
            "retrieval_policy": {},
            "context_policy": {},
            "packet_policy": {},
            "writer_model_profile": {},
            "worker_model_profiles": {},
            "mode_specific_settings": {},
        }
    )

    assert compiled.writer_policy.retrieval_mode == "bounded_tool_loop"
    assert compiled.writer_policy.rewrite_requires_explicit_selection is False
    assert compiled.post_write_policy.preset_id == "balanced"
    assert compiled.budget_latency_policy.max_blocking_analysis_workers == 1


def test_publish_snapshot_supersedes_previous_active_snapshot(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-publish",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)

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
    refreshed_session = story_session_service.get_session(story_session.session_id)

    assert activated_first.activated_at is not None
    assert refreshed_first.status == "superseded"
    assert refreshed_first.superseded_at is not None
    assert refreshed_first.compiled_profile_json == first.compiled_profile_json
    assert activated_second.status == "active"
    assert activated_second.activated_at is not None
    assert refreshed_session is not None
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        activated_second.runtime_profile_snapshot_id
    )


def test_ensure_active_snapshot_compiles_once_and_reuses_existing_active(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-ensure-active",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)

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
    refreshed_session = story_session_service.get_session(story_session.session_id)

    assert first.runtime_profile_snapshot_id == second.runtime_profile_snapshot_id
    assert first.status == "active"
    assert len(rows) == 1
    assert refreshed_session is not None
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        first.runtime_profile_snapshot_id
    )


def test_require_active_snapshot_repairs_stale_session_pointer_from_existing_active_row(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-repair-stale-session-pointer",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)
    active = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.require_active.initial",
    )

    session_record = retrieval_session.get(StorySessionRecord, story_session.session_id)
    assert session_record is not None
    session_record.active_runtime_profile_snapshot_id = "missing-runtime-snapshot"
    retrieval_session.add(session_record)
    retrieval_session.flush()

    repaired = service.require_active_snapshot(session_id=story_session.session_id)
    refreshed_session = story_session_service.get_session(story_session.session_id)

    assert repaired.runtime_profile_snapshot_id == active.runtime_profile_snapshot_id
    assert refreshed_session is not None
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        active.runtime_profile_snapshot_id
    )


def test_ensure_active_snapshot_rebuilds_when_session_pointer_is_stale(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-stale-session-anchor-backfill",
    )
    service = RuntimeProfileSnapshotService(retrieval_session)
    first = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure_active.initial",
    )

    session_record = retrieval_session.get(StorySessionRecord, story_session.session_id)
    assert session_record is not None
    session_record.active_runtime_profile_snapshot_id = "missing-runtime-snapshot"
    retrieval_session.add(session_record)
    retrieval_session.flush()

    rebuilt = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure_active.backfill",
    )
    refreshed_first = service.require_snapshot(first.runtime_profile_snapshot_id)
    refreshed_session = retrieval_session.get(StorySessionRecord, story_session.session_id)

    assert rebuilt.runtime_profile_snapshot_id != first.runtime_profile_snapshot_id
    assert rebuilt.status == "active"
    assert rebuilt.compiled_profile_json == first.compiled_profile_json
    assert rebuilt.source_config_revision == first.source_config_revision
    assert refreshed_first.status == "superseded"
    assert refreshed_session is not None
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        rebuilt.runtime_profile_snapshot_id
    )


def test_ensure_active_snapshot_republishes_when_writer_contract_changes(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="snapshot-writer-contract-revision",
        writer_contract={"style_rules": ["Lean prose."]},
    )
    service = RuntimeProfileSnapshotService(retrieval_session)
    first = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure.writer_contract.first",
    )

    session_record = retrieval_session.get(StorySessionRecord, story_session.session_id)
    assert session_record is not None
    session_record.writer_contract_json = {
        "style_rules": ["Lean prose.", "Keep continuity precise."],
    }
    retrieval_session.add(session_record)
    retrieval_session.flush()

    second = service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.ensure.writer_contract.second",
    )
    rows = retrieval_session.exec(
        select(RuntimeProfileSnapshotRecord).where(
            RuntimeProfileSnapshotRecord.session_id == story_session.session_id
        )
    ).all()

    assert second.runtime_profile_snapshot_id != first.runtime_profile_snapshot_id
    assert second.status == "active"
    assert (
        second.compiled_profile_json["writer_policy"]["style_rules"]
        == ["Lean prose.", "Keep continuity precise."]
    )
    assert len(rows) == 2
