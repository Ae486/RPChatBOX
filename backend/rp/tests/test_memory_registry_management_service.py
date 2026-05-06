"""Tests for persistent registry/profile management and snapshot compilation."""

from __future__ import annotations

from sqlmodel import select

from models.rp_registry_store import MemoryModeProfileRecord
from models.rp_story_store import RuntimeProfileSnapshotRecord, StoryTurnRecord
from rp.models.memory_contract_registry import (
    MemoryBlockTemplate,
    MemoryDomainContract,
    MemoryLifecycleState,
    MemoryModeDefault,
    MemoryWorkerDescriptor,
    MemoryWorkerModeDefault,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.memory_contract_registry import (
    CORE_STATE_AUTHORITATIVE_LAYER,
    RUNTIME_WORKSPACE_LAYER,
)
from rp.services.memory_registry_management_service import (
    MemoryRegistryManagementService,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


def _seed_story_session(retrieval_session, *, story_id: str):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def _magic_domain() -> MemoryDomainContract:
    return MemoryDomainContract(
        domain_id="magic_system",
        label="Magic System",
        description="Magic rules and current spell constraints.",
        aliases=["magic"],
        allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER, RUNTIME_WORKSPACE_LAYER],
        mode_defaults={
            "longform": MemoryModeDefault(active=True, ui_visible=True),
            "roleplay": MemoryModeDefault(active=True, ui_visible=True),
        },
    )


def _magic_block_template() -> MemoryBlockTemplate:
    return MemoryBlockTemplate(
        block_template_id="magic_system.authoritative",
        domain_id="magic_system",
        layer=CORE_STATE_AUTHORITATIVE_LAYER,
        label="Magic System Authoritative State",
        aliases=["magic.authoritative"],
        domain_path_pattern="magic_system.current",
        allowed_operations=["read", "proposal.submit"],
    )


def _magic_worker() -> MemoryWorkerDescriptor:
    return MemoryWorkerDescriptor(
        worker_id="magic_worker",
        label="Magic Worker",
        aliases=["arcane"],
        mode_defaults={
            "longform": MemoryWorkerModeDefault(
                active=True,
                permission_defaults={
                    "read": True,
                    "propose": True,
                    "refresh_projection": False,
                },
                metadata={"role": "magic_context"},
            ),
        },
        permission_defaults={
            "read": True,
            "propose": True,
            "refresh_projection": False,
        },
    )


def test_persistent_descriptors_cover_lifecycle_alias_and_migration(
    retrieval_session,
):
    service = MemoryRegistryManagementService(retrieval_session)
    service.upsert_domain_descriptor(_magic_domain(), actor="test")
    service.upsert_block_template_descriptor(_magic_block_template(), actor="test")
    service.upsert_worker_descriptor(_magic_worker(), actor="test")

    assert "magic_system" in {
        item["domain_id"] for item in service.list_domain_descriptors(mode="longform")
    }
    assert "magic_system.authoritative" in {
        item["block_template_id"]
        for item in service.list_block_template_descriptors(domain_id="magic_system")
    }
    assert "magic_worker" in {
        item["worker_id"] for item in service.list_worker_descriptors(mode="longform")
    }
    assert service.registry_service().resolve_alias("magic") == "magic_system"
    assert service.registry_service().resolve_worker_alias("arcane") == "magic_worker"
    assert (
        service.registry_service().resolve_block_template_alias("magic.authoritative")
        == "magic_system.authoritative"
    )

    service.hide_block_template_descriptor(
        block_template_id="magic_system.authoritative",
        actor="test",
    )

    assert "magic_system.authoritative" not in {
        item["block_template_id"]
        for item in service.list_block_template_descriptors(domain_id="magic_system")
    }
    assert "magic_system.authoritative" in {
        item["block_template_id"]
        for item in service.list_block_template_descriptors(
            domain_id="magic_system",
            include_hidden=True,
        )
    }

    service.upsert_block_template_descriptor(_magic_block_template(), actor="test")
    service.hide_domain_descriptor(domain_id="magic_system", actor="test")

    assert "magic_system" not in {
        item["domain_id"] for item in service.list_domain_descriptors(mode="longform")
    }
    assert "magic_system" in {
        item["domain_id"]
        for item in service.list_domain_descriptors(include_hidden=True)
    }

    service.upsert_domain_descriptor(
        MemoryDomainContract(
            domain_id="old_magic",
            label="Old Magic",
            lifecycle=MemoryLifecycleState.MIGRATED,
            aliases=["spellcraft"],
            migrated_to="magic_system",
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
        ),
        actor="test",
    )
    service.upsert_worker_descriptor(
        MemoryWorkerDescriptor(
            worker_id="old_magic_worker",
            label="Old Magic Worker",
            lifecycle=MemoryLifecycleState.MIGRATED,
            aliases=["old_arcane"],
            migrated_to="magic_worker",
        ),
        actor="test",
    )
    service.upsert_block_template_descriptor(
        MemoryBlockTemplate(
            block_template_id="magic_system.legacy_authoritative",
            domain_id="magic_system",
            layer=CORE_STATE_AUTHORITATIVE_LAYER,
            label="Legacy Magic Authoritative State",
            aliases=["magic.legacy"],
        ),
        actor="test",
    )
    service.migrate_block_template_descriptor(
        block_template_id="magic_system.legacy_authoritative",
        migrated_to="magic_system.authoritative",
        actor="test",
    )
    service.retire_block_template_descriptor(
        block_template_id="magic_system.authoritative",
        actor="test",
    )

    registry = service.registry_service()
    assert registry.resolve_alias("spellcraft") == "magic_system"
    assert registry.resolve_worker_alias("old_arcane") == "magic_worker"
    assert (
        registry.resolve_block_template_alias("magic.legacy")
        == "magic_system.authoritative"
    )
    assert "magic_system.authoritative" not in {
        item["block_template_id"]
        for item in service.list_block_template_descriptors(domain_id="magic_system")
    }


def test_active_mode_profile_compiles_persistent_descriptors_into_snapshot(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="registry-profile-compile",
    )
    management = MemoryRegistryManagementService(retrieval_session)
    management.upsert_domain_descriptor(_magic_domain(), actor="test")
    management.upsert_block_template_descriptor(_magic_block_template(), actor="test")
    management.upsert_worker_descriptor(_magic_worker(), actor="test")
    management.create_mode_profile(
        profile_id="longform_magic_v1",
        mode="longform",
        actor="test",
        config_json={
            "domain_overrides": {
                "foreshadow": {"active": False, "ui_visible": False},
                "magic_system": {"active": True, "ui_visible": True},
            },
            "worker_overrides": {
                "specialist": {"active": False},
                "magic_worker": {
                    "active": True,
                    "profile_ref": "worker-profile-magic",
                    "metadata": {"allowed_phases": ["outline_drafting"]},
                },
            },
            "permission_profile": {
                "worker_defaults": {
                    "magic_worker": {
                        "read": True,
                        "propose": True,
                        "refresh_projection": False,
                    }
                }
            },
            "retrieval_policy": {"graph_extraction_enabled": False},
            "context_policy": {"consumer_keys": ["story.magic_worker"]},
        },
    )

    assert (
        management.publish_mode_profile(profile_id="longform_magic_v1", actor="test")
        == "longform_magic_v1"
    )
    assert (
        management.activate_mode_profile(profile_id="longform_magic_v1", actor="test")
        == "longform_magic_v1"
    )

    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.registry_profile.activate",
    )
    compiled = snapshot.compiled_profile_json

    assert snapshot.status == "active"
    assert compiled["mode_profile"]["mode_profile_ref"] == "longform_magic_v1"
    assert compiled["mode_profile"]["mode_profile_version"] == 1
    assert compiled["domain_activation"]["magic_system"]["active"] is True
    assert compiled["domain_activation"]["foreshadow"]["active"] is False
    assert compiled["block_activation"]["magic_system.authoritative"]["active"] is True
    assert compiled["worker_activation"]["specialist"]["active"] is False
    assert compiled["worker_activation"]["magic_worker"]["active"] is True
    assert (
        compiled["worker_activation"]["magic_worker"]["profile_ref"]
        == "worker-profile-magic"
    )
    assert compiled["worker_activation"]["graph_extraction"]["active"] is False
    assert compiled["context_policy"]["consumer_keys"] == ["story.magic_worker"]


def test_profile_overrides_cannot_reactivate_inactive_descriptors(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="registry-profile-inactive-guard",
    )
    management = MemoryRegistryManagementService(retrieval_session)
    management.upsert_domain_descriptor(_magic_domain(), actor="test")
    management.upsert_block_template_descriptor(_magic_block_template(), actor="test")
    management.upsert_worker_descriptor(_magic_worker(), actor="test")
    management.hide_domain_descriptor(domain_id="magic_system", actor="test")
    management.hide_worker_descriptor(worker_id="magic_worker", actor="test")
    management.create_mode_profile(
        profile_id="longform_inactive_override",
        mode="longform",
        actor="test",
        config_json={
            "domain_overrides": {"magic_system": {"active": True, "ui_visible": True}},
            "block_overrides": {"magic_system.authoritative": {"active": True}},
            "worker_overrides": {"magic_worker": {"active": True}},
        },
    )
    management.activate_mode_profile(
        profile_id="longform_inactive_override",
        actor="test",
    )

    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.registry_profile.inactive_guard",
    )
    compiled = snapshot.compiled_profile_json

    assert compiled["domain_activation"]["magic_system"]["active"] is False
    assert compiled["domain_activation"]["magic_system"]["ui_visible"] is False
    assert compiled["block_activation"]["magic_system.authoritative"]["active"] is False
    assert compiled["worker_activation"]["magic_worker"]["active"] is False


def test_profile_activation_changes_future_turn_snapshots_only(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="registry-profile-future-turn",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.initial",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    first_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )

    management = MemoryRegistryManagementService(retrieval_session)
    management.create_mode_profile(
        profile_id="longform_worker_disable",
        mode="longform",
        actor="test",
        config_json={"worker_overrides": {"specialist": {"active": False}}},
    )
    management.activate_mode_profile(
        profile_id="longform_worker_disable",
        actor="test",
    )
    future_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.future_profile",
    )
    future_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )

    first_turn = retrieval_session.get(StoryTurnRecord, first_identity.turn_id)
    refreshed_initial = retrieval_session.get(
        RuntimeProfileSnapshotRecord,
        initial_snapshot.runtime_profile_snapshot_id,
    )
    profile = retrieval_session.exec(
        select(MemoryModeProfileRecord).where(
            MemoryModeProfileRecord.profile_id == "longform_worker_disable"
        )
    ).one()

    assert first_turn is not None
    assert first_turn.runtime_profile_snapshot_id == (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert future_snapshot.runtime_profile_snapshot_id != (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert refreshed_initial is not None
    assert refreshed_initial.status == "superseded"
    assert future_identity.runtime_profile_snapshot_id == (
        future_snapshot.runtime_profile_snapshot_id
    )
    assert (
        future_snapshot.compiled_profile_json["worker_activation"]["specialist"][
            "active"
        ]
        is False
    )
    assert profile.status == "active"
