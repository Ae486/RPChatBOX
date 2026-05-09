"""Focused tests for Phase O1 roleplay/TRPG extension slots."""

from __future__ import annotations

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.mode_extension_contracts import (
    CHARACTER_MEMORY_WORKER_ID,
    RULE_CARD_SLOT_ID,
    RULE_STATE_CARD_SLOT_ID,
    RULE_STATE_WORKER_ID,
    SCENE_INTERACTION_WORKER_ID,
    RuleCardMaterial,
    RuleStateCardMaterial,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.worker_runtime_contracts import WorkerResultStatus
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.context_orchestration_service import ContextOrchestrationService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from rp.services.story_session_service import StorySessionService
from rp.services.worker_execution_service import WorkerExecutionService
from rp.services.worker_registry_service import (
    WRITING_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.worker_scheduler_service import (
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)
from rp.services.writing_packet_builder import WritingPacketBuilder


def _seed_story_runtime(retrieval_session, *, story_id: str, mode: StoryMode):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=mode,
    )
    session_service = StorySessionService(retrieval_session)
    session = session_service.create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=mode.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 1",
    )
    session_service.commit()
    return session, chapter


def _identity_for(session, *, snapshot_id: str, turn_id: str = "turn:test:1"):
    return MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id=session.active_branch_head_id,
        turn_id=turn_id,
        runtime_profile_snapshot_id=snapshot_id,
    )


def _context_orchestration(
    retrieval_session,
    *,
    runtime_workspace_material_service: RuntimeWorkspaceMaterialService,
) -> ContextOrchestrationService:
    story_session_service = StorySessionService(retrieval_session)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    return ContextOrchestrationService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        writing_packet_builder=WritingPacketBuilder(),
        runtime_workspace_material_service=runtime_workspace_material_service,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )


class _UnexpectedLongformSpecialist:
    async def analyze(self, **_kwargs):
        raise AssertionError("extension placeholder must not call longform specialist")


def test_roleplay_snapshot_compiles_extension_slots_and_registry_descriptors(
    retrieval_session,
):
    session, _ = _seed_story_runtime(
        retrieval_session,
        story_id="roleplay-extension-slots",
        mode=StoryMode.ROLEPLAY,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.roleplay",
    )
    compiled = snapshot.compiled_profile_json
    extension_profile = compiled["mode_specific_settings"]["mode_extension_profile"]
    scheduler = WorkerSchedulerService(
        worker_registry_service=WorkerRegistryService(retrieval_session)
    )
    plan = scheduler.build_plan(
        identity=_identity_for(
            session,
            snapshot_id=snapshot.runtime_profile_snapshot_id,
        ),
        phase=PRE_WRITE_CONTEXT_PHASE,
    )
    registry_workers = {
        worker.descriptor.worker_id
        for worker in WorkerRegistryService(retrieval_session).build_registry_for_snapshot(
            snapshot_id=snapshot.runtime_profile_snapshot_id
        ).workers
    }

    assert compiled["mode_profile"]["mode"] == "roleplay"
    assert extension_profile["mode"] == "roleplay"
    assert extension_profile["acceptance_policy"]["acceptance_signal"] == (
        "next_user_message"
    )
    assert extension_profile["acceptance_policy"][
        "create_longform_adoption_receipt"
    ] is False
    assert CHARACTER_MEMORY_WORKER_ID in compiled["worker_activation"]
    assert SCENE_INTERACTION_WORKER_ID in compiled["worker_activation"]
    assert registry_workers == {
        WRITING_WORKER_ID,
        CHARACTER_MEMORY_WORKER_ID,
        SCENE_INTERACTION_WORKER_ID,
    }
    assert [item.worker_id for item in plan.selected_workers] == [
        CHARACTER_MEMORY_WORKER_ID
    ]
    assert any(
        item.worker_id == SCENE_INTERACTION_WORKER_ID
        and item.skip_reason == "execution_class_not_bootstrapped"
        for item in plan.skipped_workers
    )


def test_trpg_snapshot_compiles_rule_state_extension_contract(
    retrieval_session,
):
    session, _ = _seed_story_runtime(
        retrieval_session,
        story_id="trpg-extension-slots",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.trpg",
    )
    compiled = snapshot.compiled_profile_json
    extension_profile = compiled["mode_specific_settings"]["mode_extension_profile"]
    registry_workers = {
        worker.descriptor.worker_id
        for worker in WorkerRegistryService(retrieval_session).build_registry_for_snapshot(
            snapshot_id=snapshot.runtime_profile_snapshot_id
        ).workers
    }

    assert compiled["mode_profile"]["mode"] == "trpg"
    assert extension_profile["mode"] == "trpg"
    assert compiled["packet_policy"]["mode_sidecar_slots"] == [
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
    ]
    assert compiled["mode_specific_settings"]["workspace_material_slots"] == [
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
    ]
    assert extension_profile["acceptance_policy"]["acceptance_signal"] == (
        "next_user_message"
    )
    assert extension_profile["acceptance_policy"][
        "create_longform_adoption_receipt"
    ] is False
    assert RULE_STATE_WORKER_ID in compiled["worker_activation"]
    assert registry_workers == {WRITING_WORKER_ID, RULE_STATE_WORKER_ID}


@pytest.mark.asyncio
async def test_missing_extension_executor_degrades_with_trace(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="roleplay-extension-degrade",
        mode=StoryMode.ROLEPLAY,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.degrade",
    )
    identity = _identity_for(session, snapshot_id=snapshot.runtime_profile_snapshot_id)
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    execution_service = WorkerExecutionService(
        worker_registry_service=WorkerRegistryService(retrieval_session),
        longform_specialist_service=_UnexpectedLongformSpecialist(),  # type: ignore[arg-type]
        context_orchestration_service=_context_orchestration(
            retrieval_session,
            runtime_workspace_material_service=runtime_workspace_material_service,
        ),
        runtime_workspace_facade=StoryRuntimeWorkspaceFacade(
            runtime_workspace_material_service=runtime_workspace_material_service
        ),
    )
    plan = WorkerSchedulerService(
        worker_registry_service=WorkerRegistryService(retrieval_session)
    ).build_plan(
        identity=identity,
        phase=PRE_WRITE_CONTEXT_PHASE,
    )

    outcome = await execution_service.execute_plan(
        session=session,
        chapter=chapter,
        plan=plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        orchestrator_plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue the interaction.",
        ),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert [item.worker_id for item in plan.selected_workers] == [
        CHARACTER_MEMORY_WORKER_ID
    ]
    assert len(outcome.worker_results) == 1
    result = outcome.worker_results[0]
    assert result.result_status == WorkerResultStatus.DEGRADED
    assert result.trace_summary["degrade_reason"] == (
        "runtime_worker_executor_missing"
    )
    assert result.metadata["degraded"] is True
    assert result.metadata["context_packet_ref"].startswith("worker-packet-")
    assert outcome.specialist_bundle == SpecialistResultBundle()


def test_trpg_rule_sidecars_are_branch_scoped_runtime_workspace_materials(
    retrieval_session,
):
    session, _ = _seed_story_runtime(
        retrieval_session,
        story_id="trpg-rule-sidecars",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.rule_cards",
    )
    identity = _identity_for(session, snapshot_id=snapshot.runtime_profile_snapshot_id)
    wrong_branch_identity = identity.model_copy(
        update={"branch_head_id": "branch:test:other"}
    )
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    facade = StoryRuntimeWorkspaceFacade(
        runtime_workspace_material_service=runtime_workspace_material_service
    )

    rule_card_id = facade.record_rule_card_material(
        material=RuleCardMaterial(
            material_id="rule-card:1",
            identity=identity,
            rule_refs=["rule:seal-at-dusk"],
            adjudication_summary="Relics must be sealed at dusk.",
            source_refs=["retrieval_card:storm-ward"],
        )
    )
    rule_state_id = facade.record_rule_state_card_material(
        material=RuleStateCardMaterial(
            material_id="rule-state-card:1",
            identity=identity,
            mechanics_state_patch={"hp": 8, "stress": 1},
            status_effects=[{"name": "bleeding", "severity": 1}],
            source_refs=["worker_evidence:storm-ward"],
        )
    )

    assert rule_card_id == "rule-card:1"
    assert rule_state_id == "rule-state-card:1"

    rule_cards = runtime_workspace_material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.RULE_CARD,
    )
    rule_state_cards = runtime_workspace_material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.RULE_STATE_CARD,
    )
    assert len(rule_cards) == 1
    assert len(rule_state_cards) == 1
    assert rule_cards[0].metadata["source_of_truth"] is False
    assert rule_state_cards[0].metadata["source_of_truth"] is False
    assert [source_ref.source_id for source_ref in rule_cards[0].source_refs] == [
        "retrieval_card:storm-ward",
    ]
    assert [source_ref.source_id for source_ref in rule_state_cards[0].source_refs] == [
        "worker_evidence:storm-ward",
    ]
    assert (
        runtime_workspace_material_service.get_material(
            identity=wrong_branch_identity,
            material_id="rule-card:1",
        )
        is None
    )
    assert (
        runtime_workspace_material_service.get_material(
            identity=wrong_branch_identity,
            material_id="rule-state-card:1",
        )
        is None
    )


def test_context_orchestration_mounts_trpg_sidecars_without_new_packet_fields(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="trpg-context-sidecars",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.context_sidecars",
    )
    identity = _identity_for(session, snapshot_id=snapshot.runtime_profile_snapshot_id)
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    facade = StoryRuntimeWorkspaceFacade(
        runtime_workspace_material_service=runtime_workspace_material_service
    )
    facade.record_rule_card_material(
        material=RuleCardMaterial(
            material_id="rule-card:ctx",
            identity=identity,
            rule_refs=["rule:storm-ward"],
            adjudication_summary="The storm ward blocks fire damage this turn.",
        )
    )
    facade.record_rule_state_card_material(
        material=RuleStateCardMaterial(
            material_id="rule-state-card:ctx",
            identity=identity,
            mechanics_state_patch={"initiative": 12},
            status_effects=[{"name": "storm_ward", "duration": 1}],
        )
    )
    orchestration = _context_orchestration(
        retrieval_session,
        runtime_workspace_material_service=runtime_workspace_material_service,
    )

    packet = orchestration.build_writing_packet(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Resolve the action.",
        ),
        specialist_bundle=SpecialistResultBundle(writer_hints=["Keep momentum."]),
        runtime_identity=identity,
    )
    worker_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase=PRE_WRITE_CONTEXT_PHASE,
        mode=session.mode,
        context_requirements={"sidecar_slot_ids": [RULE_CARD_SLOT_ID, RULE_STATE_CARD_SLOT_ID]},
    )
    packet_payload = packet.model_dump(mode="json")

    assert {section.label for section in packet.mode_sidecar_sections} == {
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
        "writer_hints",
    }
    assert packet.metadata["mode_sidecar_slot_ids"] == [
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
    ]
    sidecar_sections = [
        section
        for section in packet.mode_sidecar_sections
        if section.source_kind == "runtime_mode_sidecar"
    ]
    assert {section.label for section in sidecar_sections} == {
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
    }
    assert all(
        section.metadata_json["section_family"] == "mode_sidecar"
        for section in sidecar_sections
    )
    assert "rule_card_sections" not in packet_payload
    assert "rule_state_card_sections" not in packet_payload
    assert set(worker_packet.sidecar_refs) == {
        "rule-card:ctx",
        "rule-state-card:ctx",
    }


def test_worker_context_packet_respects_requested_mode_sidecar_slots(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="trpg-context-sidecar-filter",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.mode_extension.context_sidecar_filter",
    )
    identity = _identity_for(session, snapshot_id=snapshot.runtime_profile_snapshot_id)
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    facade = StoryRuntimeWorkspaceFacade(
        runtime_workspace_material_service=runtime_workspace_material_service
    )
    facade.record_rule_card_material(
        material=RuleCardMaterial(
            material_id="rule-card:filter",
            identity=identity,
            rule_refs=["rule:single-sidecar"],
        )
    )
    facade.record_rule_state_card_material(
        material=RuleStateCardMaterial(
            material_id="rule-state-card:filter",
            identity=identity,
            mechanics_state_patch={"initiative": 9},
        )
    )
    orchestration = _context_orchestration(
        retrieval_session,
        runtime_workspace_material_service=runtime_workspace_material_service,
    )

    worker_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase=PRE_WRITE_CONTEXT_PHASE,
        mode=session.mode,
        context_requirements={"sidecar_slot_ids": [RULE_CARD_SLOT_ID]},
    )

    assert worker_packet.sidecar_refs == ["rule-card:filter"]
    assert "rule-card:filter" not in worker_packet.workspace_refs
    assert "rule-state-card:filter" not in worker_packet.workspace_refs
    assert worker_packet.packet_metadata["section_counts"]["sidecar_refs"] == 1

    unrequested_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase=PRE_WRITE_CONTEXT_PHASE,
        mode=session.mode,
        context_requirements={},
    )

    assert unrequested_packet.sidecar_refs == []
    assert "rule-card:filter" not in unrequested_packet.workspace_refs
    assert "rule-state-card:filter" not in unrequested_packet.workspace_refs
    assert unrequested_packet.packet_metadata["section_counts"]["sidecar_refs"] == 0
