"""Tests for runtime config control-plane snapshot publish."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlmodel import select

from models.rp_story_store import (
    RuntimeConfigControlReceiptRecord,
    RuntimeProfileSnapshotRecord,
    RuntimeWorkflowJobRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.runtime_config_contracts import RuntimeConfigPatchRequest
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.runtime_workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase, LongformTurnCommandKind
from rp.services.runtime_config_control_service import (
    RuntimeConfigControlService,
    RuntimeConfigControlServiceError,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.memory_registry_management_service import MemoryRegistryManagementService
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


class _FakeProviderRegistry:
    def __init__(self, providers: dict[str, object] | None = None) -> None:
        self._providers = providers or {}

    def get_entry(self, provider_id: str):
        return self._providers.get(provider_id)


class _FakeModelRegistry:
    def __init__(self, models: dict[str, object] | None = None) -> None:
        self._models = models or {}

    def get_entry(self, model_id: str):
        return self._models.get(model_id)


def _seed_story_session(retrieval_session, *, story_id: str = "runtime-config-story"):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    session = StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    return session


def _control_service(retrieval_session) -> RuntimeConfigControlService:
    provider = SimpleNamespace(provider_id="provider-runtime", is_enabled=True)
    model = SimpleNamespace(
        id="model-runtime",
        provider_id="provider-runtime",
        is_enabled=True,
    )
    return RuntimeConfigControlService(
        retrieval_session,
        model_registry_service=_FakeModelRegistry({"model-runtime": model}),
        provider_registry_service=_FakeProviderRegistry({"provider-runtime": provider}),
    )


def test_publish_patch_creates_active_snapshot_and_control_history(retrieval_session):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.initial",
    )
    initial_profile = dict(initial.compiled_profile_json)
    service = _control_service(retrieval_session)

    receipt = service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            actor_id="user-1",
            expected_active_snapshot_id=initial.runtime_profile_snapshot_id,
            worker_overrides={"specialist": {"active": False}},
            permission_overrides={
                "specialist": {"domains": {"chapter": {"level": "propose"}}}
            },
            retrieval_policy_patch={"graph_extraction_enabled": False},
            reason="disable specialist for next turn",
        )
    )
    retrieval_session.commit()

    refreshed_initial = snapshot_service.require_snapshot(
        initial.runtime_profile_snapshot_id
    )
    active = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )
    history = service.list_control_history(session_id=story_session.session_id)
    receipt_row = retrieval_session.get(
        RuntimeConfigControlReceiptRecord,
        receipt.receipt_id,
    )

    assert refreshed_initial.status == "superseded"
    assert refreshed_initial.compiled_profile_json == initial_profile
    assert active.runtime_profile_snapshot_id == receipt.published_snapshot_id
    assert active.runtime_profile_snapshot_id != initial.runtime_profile_snapshot_id
    assert active.compiled_profile_json["worker_activation"]["specialist"]["active"] is False
    assert active.compiled_profile_json["retrieval_policy"][
        "graph_extraction_enabled"
    ] is False
    assert active.compiled_profile_json["permission_profile"][
        "runtime_config_overrides"
    ]["specialist"]["domains"]["chapter"]["level"] == "propose"
    assert receipt.previous_snapshot_id == initial.runtime_profile_snapshot_id
    assert receipt.actor_id == "user-1"
    assert "worker_overrides" in receipt.changed_fields
    assert [item.receipt_id for item in history] == [receipt.receipt_id]
    assert receipt_row is not None
    assert receipt_row.reason == "disable specialist for next turn"


def test_publish_patch_derives_from_active_snapshot_without_mode_profile_drift(
    retrieval_session,
):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.profile_drift.initial",
    )
    MemoryRegistryManagementService(retrieval_session).create_mode_profile(
        profile_id="longform-runtime-config-drift",
        mode=StoryMode.LONGFORM.value,
        config_json={"worker_overrides": {"specialist": {"active": False}}},
        actor="test",
    )
    MemoryRegistryManagementService(retrieval_session).activate_mode_profile(
        profile_id="longform-runtime-config-drift",
        actor="test",
    )
    service = _control_service(retrieval_session)

    receipt = service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            packet_policy_patch={"max_context_tokens": 1024},
        )
    )
    retrieval_session.commit()

    published = snapshot_service.require_snapshot(receipt.published_snapshot_id)

    assert initial.compiled_profile_json["worker_activation"]["specialist"][
        "active"
    ] is True
    assert published.compiled_profile_json["worker_activation"]["specialist"][
        "active"
    ] is True
    assert published.compiled_profile_json["packet_policy"]["max_context_tokens"] == 1024


@pytest.mark.parametrize(
    ("patch_request", "error_code"),
    [
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                worker_overrides={"missing_worker": {"active": False}},
            ),
            "runtime_config_unknown_worker",
        ),
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                permission_overrides={"missing_domain": {"level": "observe"}},
            ),
            "runtime_config_unknown_domain",
        ),
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                permission_overrides={"chapter": {"level": "god_mode"}},
            ),
            "runtime_config_invalid_permission_level",
        ),
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                model_profile_patch={"writer": {"model_id": "missing-model"}},
            ),
            "runtime_config_invalid_model_profile",
        ),
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                packet_policy_patch={"max_context_tokens": -1},
            ),
            "runtime_config_invalid_budget",
        ),
        (
            RuntimeConfigPatchRequest(
                session_id="placeholder",
                packet_policy_patch={"max_context_tokens": True},
            ),
            "runtime_config_invalid_budget",
        ),
    ],
)
def test_validation_fail_closed_rejects_without_partial_publish(
    retrieval_session,
    patch_request,
    error_code,
):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.fail_closed.initial",
    )
    retrieval_session.commit()
    service = RuntimeConfigControlService(
        retrieval_session,
        model_registry_service=_FakeModelRegistry(),
        provider_registry_service=_FakeProviderRegistry(),
    )
    patch_request = patch_request.model_copy(
        update={"session_id": story_session.session_id}
    )

    with pytest.raises(RuntimeConfigControlServiceError) as exc_info:
        service.publish_patch(patch_request)

    refreshed_session = retrieval_session.get(StorySessionRecord, story_session.session_id)
    snapshots = retrieval_session.exec(
        select(RuntimeProfileSnapshotRecord).where(
            RuntimeProfileSnapshotRecord.session_id == story_session.session_id
        )
    ).all()
    receipts = retrieval_session.exec(
        select(RuntimeConfigControlReceiptRecord).where(
            RuntimeConfigControlReceiptRecord.session_id == story_session.session_id
        )
    ).all()

    assert exc_info.value.code == error_code
    assert refreshed_session is not None
    assert refreshed_session.runtime_story_config_json == {}
    assert [item.runtime_profile_snapshot_id for item in snapshots] == [
        initial.runtime_profile_snapshot_id
    ]
    assert receipts == []


def test_expected_active_snapshot_conflict_rejects_publish(retrieval_session):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.conflict.initial",
    )
    service = _control_service(retrieval_session)

    with pytest.raises(RuntimeConfigControlServiceError) as exc_info:
        service.publish_patch(
            RuntimeConfigPatchRequest(
                session_id=story_session.session_id,
                expected_active_snapshot_id="stale-snapshot",
                retrieval_policy_patch={"graph_extraction_enabled": False},
            )
        )

    active = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )
    assert exc_info.value.code == "runtime_config_snapshot_conflict"
    assert active.runtime_profile_snapshot_id == initial.runtime_profile_snapshot_id


def test_started_turn_and_pending_job_keep_creation_snapshot(retrieval_session):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.pin.initial",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="runtime-config-test",
        requested_runtime_profile_snapshot_id=initial.runtime_profile_snapshot_id,
    )
    job = RuntimeWorkflowJobService(retrieval_session).ensure_job(
        identity=identity,
        job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
        job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
        creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
        required_for_turn_completion=True,
    )
    service = _control_service(retrieval_session)

    receipt = service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            retrieval_policy_patch={"graph_extraction_enabled": False},
        )
    )
    retrieval_session.commit()

    turn_row = retrieval_session.get(StoryTurnRecord, identity.turn_id)
    job_row = retrieval_session.get(RuntimeWorkflowJobRecord, job.job_id)
    active = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )

    assert receipt.previous_snapshot_id == initial.runtime_profile_snapshot_id
    assert active.runtime_profile_snapshot_id == receipt.published_snapshot_id
    assert turn_row is not None
    assert job_row is not None
    assert turn_row.runtime_profile_snapshot_id == initial.runtime_profile_snapshot_id
    assert job_row.runtime_profile_snapshot_id == initial.runtime_profile_snapshot_id


def test_story_rollback_does_not_remove_runtime_config_history(retrieval_session):
    story_session = _seed_story_session(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_config.rollback.initial",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    first_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="runtime-config-test",
        requested_runtime_profile_snapshot_id=initial.runtime_profile_snapshot_id,
    )
    identity_service.update_turn_status(
        turn_id=first_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        settlement_reason="test_first_settled",
    )
    service = _control_service(retrieval_session)
    receipt = service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            retrieval_policy_patch={"graph_extraction_enabled": False},
        )
    )
    second_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="runtime-config-test",
    )
    identity_service.update_turn_status(
        turn_id=second_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        settlement_reason="test_second_settled",
    )
    identity_service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=first_identity.turn_id,
        actor="runtime-config-test",
    )
    retrieval_session.commit()

    history = service.list_control_history(session_id=story_session.session_id)
    active = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )

    assert [item.receipt_id for item in history] == [receipt.receipt_id]
    assert active.runtime_profile_snapshot_id == receipt.published_snapshot_id
