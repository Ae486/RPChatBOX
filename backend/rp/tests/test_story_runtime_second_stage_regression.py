"""Focused second-stage regression matrix for Phase P2 runtime story surfaces."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_retrieval_store import SourceAssetRecord
from models.rp_story_store import RuntimeWorkflowJobRecord, StorySessionRecord, StoryTurnRecord
from rp.models.archival_evolution import ArchivalEvolutionRequest
from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchArchivalInput
from rp.models.mode_extension_contracts import (
    RULE_CARD_SLOT_ID,
    RULE_STATE_CARD_SLOT_ID,
    RULE_STATE_WORKER_ID,
    RuleCardMaterial,
    RuleStateCardMaterial,
)
from rp.models.runtime_config_contracts import RuntimeConfigPatchRequest
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.runtime_workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.archival_evolution_service import ArchivalEvolutionService
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.runtime_config_control_service import RuntimeConfigControlService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from rp.tests.test_archival_evolution_service import (
    _seed_archival_asset,
    _seed_branch_identity,
    _seed_runtime_identities,
)
from rp.tests.test_longform_chapter_runtime_service import (
    _accept_outline,
    _build_context_orchestration_service,
    _identity as _longform_identity,
    _seed_story_runtime as _seed_longform_story_runtime,
    _segment_plan,
    _specialist_bundle,
)
from rp.tests.test_mode_extension_slots import (
    _context_orchestration as _mode_context_orchestration,
    _identity_for,
    _seed_story_runtime as _seed_mode_story_runtime,
)
from rp.tests.test_runtime_config_control_service import (
    _control_service,
    _seed_story_session,
)


def test_second_stage_runtime_config_publish_keeps_started_turn_and_pending_job_snapshots(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="runtime-config-second-stage-regression",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.second_stage.runtime_config.initial",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    started_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="second-stage-runtime-config",
        requested_runtime_profile_snapshot_id=(
            initial_snapshot.runtime_profile_snapshot_id
        ),
    )
    pending_job = RuntimeWorkflowJobService(retrieval_session).ensure_job(
        identity=started_identity,
        job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
        job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
        creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
        required_for_turn_completion=True,
    )
    control_service: RuntimeConfigControlService = _control_service(retrieval_session)

    receipt = control_service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            expected_active_snapshot_id=initial_snapshot.runtime_profile_snapshot_id,
            packet_policy_patch={"max_context_tokens": 1536},
            reason="second-stage regression hot update",
        )
    )
    retrieval_session.commit()

    next_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="second-stage-runtime-config-next",
    )
    turn_row = retrieval_session.get(StoryTurnRecord, started_identity.turn_id)
    job_row = retrieval_session.get(RuntimeWorkflowJobRecord, pending_job.job_id)
    active_snapshot = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )

    assert receipt.previous_snapshot_id == initial_snapshot.runtime_profile_snapshot_id
    assert active_snapshot.runtime_profile_snapshot_id == receipt.published_snapshot_id
    assert turn_row is not None
    assert turn_row.runtime_profile_snapshot_id == (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert job_row is not None
    assert job_row.runtime_profile_snapshot_id == (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert next_identity.runtime_profile_snapshot_id == receipt.published_snapshot_id
    assert next_identity.runtime_profile_snapshot_id != (
        started_identity.runtime_profile_snapshot_id
    )


@pytest.mark.asyncio
async def test_second_stage_story_evolution_selected_branch_and_story_global_visibility(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-second-stage-selected",
        text="selectedstageoldanchor original law.",
    )
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-second-stage-global",
        text="globalstageoldanchor original law.",
    )

    selected_receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-second-stage-selected",
            visibility_scope="selected_branches",
            selected_branch_head_ids=[
                main_identity.branch_head_id,
                sibling_identity.branch_head_id,
            ],
            replacement_sections=[
                {
                    "text": "selectedstagenewanchor replacement law for selected branches.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-second-stage-selected",
                    },
                }
            ],
        )
    )
    global_receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="writer",
            source_asset_id="asset-second-stage-global",
            visibility_scope="story_global",
            replacement_sections=[
                {
                    "text": "globalstagenewanchor replacement law for every future branch.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-second-stage-global",
                    },
                }
            ],
        )
    )
    future_identity = _seed_branch_identity(
        retrieval_session,
        identity=main_identity,
        branch_head_id=f"branch:{main_identity.session_id}:future-second-stage",
    )

    sibling_selected = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=sibling_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="selectedstagenewanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    future_selected = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=future_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="selectedstagenewanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    sibling_global = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=sibling_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="globalstagenewanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
    future_global = await RetrievalBroker(
        default_story_id=main_identity.story_id,
        runtime_identity=future_identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query="globalstagenewanchor",
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )

    assert selected_receipt.visibility_scope == "selected_branches"
    assert global_receipt.visibility_scope == "story_global"
    assert sibling_selected.hits
    assert sibling_selected.hits[0].metadata["asset_id"] == (
        selected_receipt.source_asset_id
    )
    assert future_selected.hits == []
    assert sibling_global.hits
    assert sibling_global.hits[0].metadata["asset_id"] == global_receipt.source_asset_id
    assert future_global.hits
    assert future_global.hits[0].metadata["asset_id"] == global_receipt.source_asset_id


def test_second_stage_longform_chapter_bridge_packet_is_branch_and_target_scoped(
    retrieval_session,
):
    story_session_service, session, chapter_one = _seed_longform_story_runtime(
        retrieval_session
    )
    _accept_outline(story_session_service, session, chapter_one)
    accepted_one = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter_one.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted chapter ending for branch-target regression.",
    )
    chapter_one = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter_one.chapter_workspace_id,
        accepted_segment_ids=[accepted_one.artifact_id],
    )
    chapter_runtime_service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-complete-main-1",
            runtime_profile_snapshot_id="snapshot-main",
        ),
        session=session,
        chapter=chapter_one,
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-sibling",
            turn_id="turn-complete-sibling-1",
            runtime_profile_snapshot_id="snapshot-main",
        ),
        session=session,
        chapter=chapter_one,
    )

    chapter_two = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Carry the tower debt into the next chapter.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": [],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    accepted_two = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter_two.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted chapter two handoff summary.",
    )
    chapter_two = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter_two.chapter_workspace_id,
        accepted_segment_ids=[accepted_two.artifact_id],
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-complete-main-2",
            runtime_profile_snapshot_id="snapshot-main",
        ),
        session=session,
        chapter=chapter_two,
    )
    chapter_three = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=3,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Open chapter three from the chapter two fallout.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": [],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    story_session_service.commit()

    orchestration = _build_context_orchestration_service(
        story_session_service,
        retrieval_session,
        chapter_runtime_service=chapter_runtime_service,
    )
    packet_two = orchestration.build_writing_packet(
        session=session,
        chapter=chapter_two,
        plan=_segment_plan(),
        specialist_bundle=_specialist_bundle(),
        runtime_identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-next-write-2",
            runtime_profile_snapshot_id="snapshot-main",
        ),
    )
    packet_three = orchestration.build_writing_packet(
        session=session,
        chapter=chapter_three,
        plan=_segment_plan(),
        specialist_bundle=_specialist_bundle(),
        runtime_identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-next-write-3",
            runtime_profile_snapshot_id="snapshot-main",
        ),
    )
    main_target_two = chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        target_chapter_index=2,
    )
    sibling_target_two = (
        chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-sibling",
            target_chapter_index=2,
        )
    )
    main_target_three = (
        chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            target_chapter_index=3,
        )
    )

    assert main_target_two is not None
    assert sibling_target_two is not None
    assert main_target_three is not None
    assert packet_two.metadata["chapter_bridge_material_ref"] == main_target_two[0]
    assert packet_two.metadata["chapter_bridge_material_ref"] != sibling_target_two[0]
    assert packet_two.metadata["chapter_bridge_material_ref"] != main_target_three[0]
    assert packet_two.mode_sidecar_sections[0].items[0] == (
        "Prior chapter bridge summary: "
        "Accepted chapter ending for branch-target regression."
    )
    assert packet_two.mode_sidecar_sections[0].metadata_json["section_family"] == (
        "mode_sidecar"
    )
    assert packet_two.mode_sidecar_sections[0].metadata_json["target_chapter_index"] == 2
    assert packet_three.metadata["chapter_bridge_material_ref"] == main_target_three[0]
    assert packet_three.mode_sidecar_sections[0].items[0] == (
        "Prior chapter bridge summary: Accepted chapter two handoff summary."
    )
    assert (
        packet_three.mode_sidecar_sections[0].metadata_json["target_chapter_index"] == 3
    )


def test_second_stage_trpg_sidecars_filter_requested_slots_and_stay_runtime_only(
    retrieval_session,
):
    session, chapter = _seed_mode_story_runtime(
        retrieval_session,
        story_id="trpg-second-stage-regression",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.second_stage.trpg",
    )
    identity = _identity_for(
        session,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_id="turn:second-stage:trpg",
    )
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    facade = StoryRuntimeWorkspaceFacade(
        runtime_workspace_material_service=runtime_workspace_material_service
    )
    facade.record_rule_card_material(
        material=RuleCardMaterial(
            material_id="rule-card:second-stage",
            identity=identity,
            rule_refs=["rule:storm-ward"],
            adjudication_summary="Storm ward blocks fire damage this turn.",
            source_refs=["retrieval_card:storm-ward"],
        )
    )
    facade.record_rule_state_card_material(
        material=RuleStateCardMaterial(
            material_id="rule-state-card:second-stage",
            identity=identity,
            mechanics_state_patch={"initiative": 11, "hp": 8},
            status_effects=[{"name": "storm_ward", "duration": 1}],
            source_refs=["worker_evidence:storm-ward"],
        )
    )
    orchestration = _mode_context_orchestration(
        retrieval_session,
        runtime_workspace_material_service=runtime_workspace_material_service,
    )

    packet = orchestration.build_writing_packet(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Resolve the warded strike.",
        ),
        specialist_bundle=SpecialistResultBundle(writer_hints=["Keep initiative clear."]),
        runtime_identity=identity,
    )
    worker_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase="pre_write_context",
        mode=session.mode,
        context_requirements={"sidecar_slot_ids": [RULE_STATE_CARD_SLOT_ID]},
    )
    packet_payload = packet.model_dump(mode="json")
    rule_card = runtime_workspace_material_service.require_material(
        identity=identity,
        material_id="rule-card:second-stage",
    )
    rule_state = runtime_workspace_material_service.require_material(
        identity=identity,
        material_id="rule-state-card:second-stage",
    )
    session_record = retrieval_session.get(StorySessionRecord, session.session_id)
    source_assets = retrieval_session.exec(
        select(SourceAssetRecord).where(SourceAssetRecord.story_id == session.story_id)
    ).all()

    assert {section.label for section in packet.mode_sidecar_sections} == {
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
        "writer_hints",
    }
    assert "rule_card_sections" not in packet_payload
    assert "rule_state_card_sections" not in packet_payload
    sidecar_sections = [
        section
        for section in packet.mode_sidecar_sections
        if section.source_kind == "runtime_mode_sidecar"
    ]
    assert all(
        section.metadata_json["section_family"] == "mode_sidecar"
        for section in sidecar_sections
    )
    assert worker_packet.sidecar_refs == ["rule-state-card:second-stage"]
    assert rule_card.material_kind == RuntimeWorkspaceMaterialKind.RULE_CARD
    assert [source_ref.source_id for source_ref in rule_card.source_refs] == [
        "retrieval_card:storm-ward",
    ]
    assert [source_ref.source_id for source_ref in rule_state.source_refs] == [
        "worker_evidence:storm-ward",
    ]
    for material in (rule_card, rule_state):
        assert material.metadata["source_of_truth"] is False
        assert material.metadata["core_state_truth"] is False
        assert material.metadata["recall_truth"] is False
        assert material.metadata["archival_truth"] is False
        assert material.metadata["temporary"] is True
    assert session_record is not None
    assert session_record.current_state_json == {}
    assert source_assets == []
