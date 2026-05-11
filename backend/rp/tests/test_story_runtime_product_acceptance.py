"""Phase Q1 product-like acceptance tests for story runtime surfaces."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from config import get_settings
from main import create_app
from models.rp_retrieval_store import SourceAssetRecord
from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.archival_evolution import ArchivalEvolutionRequest
from rp.models.dsl import Domain
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_crud import MemorySearchArchivalInput
from rp.models.mode_extension_contracts import (
    RULE_CARD_SLOT_ID,
    RULE_STATE_CARD_SLOT_ID,
    RULE_STATE_WORKER_ID,
    RuleCardMaterial,
    RuleStateCardMaterial,
)
from rp.models.revision_overlay_contracts import (
    RevisionAnchorRef,
)
from rp.models.runtime_config_contracts import RuntimeConfigPatchRequest
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterialKind,
)
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
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.draft_selection_service import DraftSelectionService
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_candidate_service import RewriteCandidateService
from rp.services.rewrite_request_builder_service import RewriteRequestBuilderService
from rp.services.runtime_config_control_service import RuntimeConfigControlService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
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
    _identity_for as _mode_identity_for,
    _seed_story_runtime as _seed_mode_story_runtime,
)
from rp.tests.test_runtime_config_control_service import (
    _control_service,
    _seed_story_session,
)
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from services.database import get_engine
from services.langfuse_config_service import reset_langfuse_config_service
from services.langfuse_service import reset_langfuse_service
from services.mcp_manager import reset_mcp_manager
from services.provider_registry import get_provider_registry_service
from tests.test_rp_story_api import (
    _seed_formal_memory_block_session,
    _seed_runtime_debug_read_surface,
    _seed_runtime_surface_second_stage_data,
)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBOX_BACKEND_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'product-acceptance.db').as_posix()}",
    )
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        "true",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_provider_registry_service.cache_clear()
    reset_langfuse_config_service()
    reset_langfuse_service()
    reset_mcp_manager()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_mcp_manager()
    reset_langfuse_config_service()
    reset_langfuse_service()
    get_provider_registry_service.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()


def test_q1_longform_review_rewrite_adopt_continue_keeps_adoption_explicit(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_longform_story_runtime(
        retrieval_session
    )
    _accept_outline(story_session_service, session, chapter)
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="q1.product_acceptance.longform_review",
    )
    identity = _resolve_identity(
        retrieval_session,
        session_id=session.session_id,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
        actor="q1.longform.review",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Original draft before review.",
        metadata={
            "command_kind": LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
            "runtime_story_id": identity.story_id,
            "runtime_session_id": identity.session_id,
            "runtime_branch_head_id": identity.branch_head_id,
            "runtime_turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_product_draft(
        overlay_service,
        identity=identity,
        draft_ref=f"artifact:{pending.artifact_id}",
        source_output_ref=pending.artifact_id,
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        selected_excerpt=draft.blocks[0].selected_excerpt,
        instruction_text="Make the bell-tower debt explicit before continuing.",
    )
    tracked_change = overlay_service.add_tracked_change(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[1].block_id),
        change_kind="replace",
        original_text=draft.blocks[1].selected_excerpt,
        suggested_text="Mira turned back toward the bell tower.",
    )
    rewrite_request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Rewrite from the accepted review overlay.",
        comment_refs=[comment.comment_id],
        tracked_change_refs=[tracked_change.tracked_change_id],
    )
    unadopted_candidate = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=rewrite_request,
        writer_result=_writer_result(
            identity=identity,
            output_text="Unadopted rewrite: Mira ignores the bell-tower debt.",
        ),
    )
    adopted_candidate = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=rewrite_request,
        writer_result=_writer_result(
            identity=identity,
            output_text="Adopted rewrite: Mira pays the bell-tower debt.",
        ),
    )
    selection_service = DraftSelectionService(session=retrieval_session)

    assert rewrite_request.comment_refs == [comment.comment_id]
    assert rewrite_request.tracked_change_refs == [tracked_change.tracked_change_id]
    assert unadopted_candidate.selected_output_ref is None
    assert adopted_candidate.selected_output_ref is None
    assert selection_service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=draft.draft_ref,
    ) is None

    selection = selection_service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=draft.draft_ref,
        candidate_output_refs=[
            unadopted_candidate.candidate_output_ref,
            adopted_candidate.candidate_output_ref,
        ],
        selected_output_ref=adopted_candidate.candidate_output_ref,
    )

    assert selection.selected_output_ref == adopted_candidate.candidate_output_ref
    assert selection_service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=draft.draft_ref,
    ) is None

    adoption = selection_service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=draft.draft_ref,
    )
    anchor = selection_service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=draft.draft_ref,
    )
    adoption_material = _review_material_by_record_id(
        retrieval_session,
        identity=identity,
        record_id=adoption.receipt_id,
    )
    artifact_after_rewrite = story_session_service.get_artifact(pending.artifact_id)

    assert adoption.metadata_json["accept_and_continue"] is True
    assert adoption.metadata_json["canonical_continuation_base"] is True
    assert adoption.selection_receipt_id == selection.receipt_id
    assert anchor is not None
    assert anchor["adopted_output_ref"] == adopted_candidate.candidate_output_ref
    assert anchor["adopted_output_ref"] != unadopted_candidate.candidate_output_ref
    assert anchor["source_kind"] == "longform_draft_adoption_receipt"
    assert any(
        ref.source_type == "draft_selection_receipt"
        and ref.source_id == selection.receipt_id
        for ref in adoption_material.source_refs
    )
    assert artifact_after_rewrite is not None
    assert artifact_after_rewrite.content_text == "Original draft before review."


def test_q1_chapter_completion_promotes_adopted_candidate_into_branch_bridge(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_longform_story_runtime(
        retrieval_session
    )
    _accept_outline(story_session_service, session, chapter)
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Pending draft that must wait for adoption.",
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    review_identity = _longform_identity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-q1-main",
        turn_id="turn-q1-review",
        runtime_profile_snapshot_id="snapshot-q1-review",
    )
    _create_adopted_product_candidate(
        retrieval_session,
        identity=review_identity,
        draft_ref=f"artifact:{pending.artifact_id}",
        output_text="Adopted chapter ending for bridge continuity.",
    )
    chapter_runtime_service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )

    prepared = chapter_runtime_service.prepare_chapter_transition(
        identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-q1-main",
            turn_id="turn-q1-complete",
            runtime_profile_snapshot_id="snapshot-q1-complete",
        ),
        session=session,
        chapter=chapter,
    )
    bridge = chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-q1-main",
        target_chapter_index=2,
    )
    sibling_bridge = chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-q1-sibling",
        target_chapter_index=2,
    )
    next_chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Carry the bridge into chapter two.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": [],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    orchestration = _build_context_orchestration_service(
        story_session_service,
        retrieval_session,
        chapter_runtime_service=chapter_runtime_service,
    )
    packet = orchestration.build_writing_packet(
        session=session,
        chapter=next_chapter,
        plan=_segment_plan(),
        specialist_bundle=_specialist_bundle(),
        runtime_identity=_longform_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-q1-main",
            turn_id="turn-q1-next-write",
            runtime_profile_snapshot_id="snapshot-q1-next",
        ),
    )
    adopted_artifact = story_session_service.get_artifact(pending.artifact_id)

    assert prepared.receipt is not None
    assert prepared.receipt.metadata_json["bridge_source"] == "draft_adoption_receipt"
    assert adopted_artifact is not None
    assert adopted_artifact.status == StoryArtifactStatus.ACCEPTED
    assert adopted_artifact.content_text == (
        "Adopted chapter ending for bridge continuity."
    )
    assert bridge is not None
    bridge_material_id, bridge_record = bridge
    assert bridge_record.summary_text == "Adopted chapter ending for bridge continuity."
    assert prepared.receipt.adopted_output_ref in bridge_record.source_refs
    assert any(ref.startswith("draft_adoption_") for ref in bridge_record.source_refs)
    assert sibling_bridge is None
    assert packet.metadata["chapter_bridge_material_ref"] == bridge_material_id
    assert packet.mode_sidecar_sections[0].metadata_json["section_family"] == (
        "mode_sidecar"
    )
    assert "Adopted chapter ending" in packet.mode_sidecar_sections[0].items[0]


def test_q1_runtime_config_hot_update_pins_started_turns_and_survives_rollback(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="q1-runtime-config-acceptance",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="q1.runtime_config.initial",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    started_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="q1.runtime_config.started_turn",
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
        source_ref_ids=["packet:q1-started"],
    )
    control_service: RuntimeConfigControlService = _control_service(retrieval_session)

    receipt = control_service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=story_session.session_id,
            expected_active_snapshot_id=initial_snapshot.runtime_profile_snapshot_id,
            packet_policy_patch={"max_context_tokens": 1792},
            reason="q1 runtime config future-turn update",
        )
    )
    identity_service.update_turn_status(
        turn_id=started_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref="artifact:q1-config",
        selected_output_ref="artifact:q1-config",
        settlement_reason="q1_config_acceptance",
    )
    rollback_receipt = identity_service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=started_identity.turn_id,
        actor="q1.runtime_config.rollback",
    )
    next_identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="q1.runtime_config.next_turn",
    )
    retrieval_session.commit()

    turn_row = retrieval_session.get(StoryTurnRecord, started_identity.turn_id)
    job_row = retrieval_session.get(RuntimeWorkflowJobRecord, pending_job.job_id)
    control_history = control_service.list_control_history(
        session_id=story_session.session_id
    )
    active_snapshot = snapshot_service.require_active_snapshot(
        session_id=story_session.session_id
    )

    assert receipt.previous_snapshot_id == initial_snapshot.runtime_profile_snapshot_id
    assert receipt.published_snapshot_id == active_snapshot.runtime_profile_snapshot_id
    assert receipt.changed_fields == ["packet_policy_patch"]
    assert turn_row is not None
    assert turn_row.runtime_profile_snapshot_id == (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert job_row is not None
    assert job_row.runtime_profile_snapshot_id == (
        initial_snapshot.runtime_profile_snapshot_id
    )
    assert next_identity.runtime_profile_snapshot_id == receipt.published_snapshot_id
    assert control_history[0].receipt_id == receipt.receipt_id
    assert rollback_receipt.target_turn_id == started_identity.turn_id
    assert control_service.list_control_history(
        session_id=story_session.session_id
    )[0].receipt_id == receipt.receipt_id


@pytest.mark.asyncio
async def test_q1_story_evolution_visibility_excludes_hidden_and_superseded_chunks(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-q1-evolution",
        text="q1oldanchor original archival law.",
    )

    receipt = ArchivalEvolutionService(retrieval_session).evolve_source(
        ArchivalEvolutionRequest(
            identity=main_identity,
            actor="q1.story_evolution",
            source_asset_id="asset-q1-evolution",
            expected_source_version=1,
            replacement_sections=[
                {
                    "text": "q1newanchor evolved archival law for the active branch.",
                    "metadata": {
                        "domain": Domain.WORLD_RULE.value,
                        "domain_path": "foundation.world.asset-q1-evolution",
                    },
                }
            ],
            source_refs=[
                MemorySourceRef(
                    source_type="story_turn",
                    source_id=main_identity.turn_id,
                    layer="runtime_identity",
                )
            ],
            reason="q1 current-branch archival evolution",
        )
    )
    future_identity = _seed_branch_identity(
        retrieval_session,
        identity=main_identity,
        branch_head_id=f"branch:{main_identity.session_id}:q1-future",
    )

    main_new = await _search_archival(main_identity, retrieval_session, "q1newanchor")
    sibling_new = await _search_archival(
        sibling_identity,
        retrieval_session,
        "q1newanchor",
    )
    future_new = await _search_archival(future_identity, retrieval_session, "q1newanchor")
    main_old = await _search_archival(main_identity, retrieval_session, "q1oldanchor")

    evolved_asset = retrieval_session.get(SourceAssetRecord, receipt.source_asset_id)

    assert receipt.visibility_scope == "current_branch"
    assert receipt.source_refs[0].source_id == main_identity.turn_id
    assert main_new.hits
    assert main_new.hits[0].metadata["asset_id"] == receipt.source_asset_id
    assert main_new.hits[0].metadata["source_asset_version"] == 2
    assert main_new.hits[0].metadata["supersedes_source_asset_id"] == (
        "asset-q1-evolution"
    )
    assert main_new.hits[0].metadata["owning_branch_head_id"] == (
        main_identity.branch_head_id
    )
    assert sibling_new.hits == []
    assert future_new.hits == []
    assert main_old.hits == []
    assert evolved_asset is not None
    assert receipt.reindex_job_ids
    assert evolved_asset.metadata_json["archival_evolution_id"] == receipt.evolution_id


def test_q1_mode_sidecars_require_explicit_slots_and_stay_runtime_only(
    retrieval_session,
):
    session, chapter = _seed_mode_story_runtime(
        retrieval_session,
        story_id="q1-trpg-sidecar-isolation",
        mode=StoryMode.TRPG,
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="q1.mode_sidecar",
    )
    identity = _mode_identity_for(
        session,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_id="turn:q1:sidecar",
    )
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    facade = StoryRuntimeWorkspaceFacade(
        runtime_workspace_material_service=material_service
    )
    facade.record_rule_card_material(
        material=RuleCardMaterial(
            material_id="rule-card:q1",
            identity=identity,
            rule_refs=["rule:q1"],
            adjudication_summary="Only requested sidecar slots may surface.",
            source_refs=["retrieval_card:q1-rule"],
        )
    )
    facade.record_rule_state_card_material(
        material=RuleStateCardMaterial(
            material_id="rule-state-card:q1",
            identity=identity,
            mechanics_state_patch={"initiative": 13},
            status_effects=[{"name": "warded", "duration": 1}],
            source_refs=["worker_evidence:q1-rule"],
        )
    )
    orchestration = _mode_context_orchestration(
        retrieval_session,
        runtime_workspace_material_service=material_service,
    )

    unrequested_worker_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase="pre_write_context",
        mode=session.mode,
        context_requirements={},
    )
    requested_worker_packet = orchestration.build_worker_context_packet(
        session=session,
        chapter=chapter,
        identity=identity,
        worker_id=RULE_STATE_WORKER_ID,
        phase="pre_write_context",
        mode=session.mode,
        context_requirements={"sidecar_slot_ids": [RULE_STATE_CARD_SLOT_ID]},
    )
    writing_packet = orchestration.build_writing_packet(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Resolve the warded action.",
        ),
        specialist_bundle=SpecialistResultBundle(writer_hints=["Keep turn order."]),
        runtime_identity=identity,
    )
    source_assets = retrieval_session.exec(
        select(SourceAssetRecord).where(SourceAssetRecord.story_id == session.story_id)
    ).all()
    rule_card = material_service.require_material(
        identity=identity,
        material_id="rule-card:q1",
    )
    rule_state_card = material_service.require_material(
        identity=identity,
        material_id="rule-state-card:q1",
    )

    assert unrequested_worker_packet.sidecar_refs == []
    assert "rule-card:q1" not in unrequested_worker_packet.workspace_refs
    assert "rule-state-card:q1" not in unrequested_worker_packet.workspace_refs
    assert requested_worker_packet.sidecar_refs == ["rule-state-card:q1"]
    assert "rule-state-card:q1" not in requested_worker_packet.workspace_refs
    assert {section.label for section in writing_packet.mode_sidecar_sections} == {
        RULE_CARD_SLOT_ID,
        RULE_STATE_CARD_SLOT_ID,
        "writer_hints",
    }
    assert all(
        section.metadata_json["section_family"] == "mode_sidecar"
        for section in writing_packet.mode_sidecar_sections
        if section.source_kind == "runtime_mode_sidecar"
    )
    assert [ref.source_id for ref in rule_card.source_refs] == ["retrieval_card:q1-rule"]
    assert [ref.source_id for ref in rule_state_card.source_refs] == [
        "worker_evidence:q1-rule"
    ]
    assert rule_card.metadata["source_of_truth"] is False
    assert rule_state_card.metadata["source_of_truth"] is False
    assert source_assets == []


def test_q1_runtime_inspect_route_returns_read_only_exact_identity_bundle(
    api_client,
):
    seeded = _seed_formal_memory_block_session()
    runtime_seed = _seed_runtime_debug_read_surface(seeded["session_id"])
    second_stage_seed = _seed_runtime_surface_second_stage_data(runtime_seed)
    config_response = api_client.patch(
        f"/api/rp/story-sessions/{seeded['session_id']}/runtime-config",
        json={
            "packet_policy_patch": {"max_context_tokens": 1024},
            "reason": "q1 inspect route control history",
        },
    )
    assert config_response.status_code == 200

    response = api_client.get(
        f"/api/rp/story-sessions/{seeded['session_id']}/runtime/inspect",
        params={"turn_id": runtime_seed["turn_id"], "target_chapter_index": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["selection"]["selected_turn_id"] == runtime_seed["turn_id"]
    assert payload["selection"]["selected_branch_head_id"] == (
        runtime_seed["branch_head_id"]
    )
    assert payload["runtime_profile_snapshot"]["runtime_profile_snapshot_id"] == (
        runtime_seed["runtime_profile_snapshot_id"]
    )
    assert payload["runtime_config"]["control_history"][0]["reason"] == (
        "q1 inspect route control history"
    )
    assert payload["writer_packet"]["runtime_read_manifest_ids"]
    assert {
        item["material_kind"] for item in payload["runtime_workspace"]["materials"]
    } >= {"retrieval_card", "retrieval_usage_record", "packet_ref"}
    assert payload["retrieval"]["usage_refs"][0]["material_id"] == (
        runtime_seed["usage_material_id"]
    )
    assert payload["chapter_bridge"]["latest_for_target_chapter"]["material_id"] == (
        second_stage_seed["main_bridge_material_id"]
    )
    assert payload["chapter_bridge"]["latest_for_target_chapter"]["source_refs"]
    sidecar_material_ids = {
        item["material_id"] for item in payload["mode_sidecars"]["materials"]
    }
    assert second_stage_seed["main_rule_card_id"] in sidecar_material_ids
    assert second_stage_seed["main_rule_state_id"] in sidecar_material_ids
    assert all(item["source_refs"] for item in payload["mode_sidecars"]["materials"])
    assert not any(
        item["material_id"].startswith(
            f"rule-card:{second_stage_seed['sibling_turn_id']}"
        )
        for item in payload["mode_sidecars"]["materials"]
    )
    assert payload["story_evolution"]["items"][0]["evolution_id"] == (
        second_stage_seed["evolution_id"]
    )
    assert payload["story_evolution"]["items"][0]["source_refs"]
    assert payload["proposal_governance"]["proposal_receipts"][0]["proposal"][
        "proposal_id"
    ] == runtime_seed["proposal_id"]
    assert any(
        item["receipt_id"] == runtime_seed["branch_control_receipt_id"]
        for item in payload["branch_control_receipts"]
    )
    assert "read_only_debug_surface" in payload["boundaries"]
    assert "extension_sidecars_expose_formal_source_refs_only" in payload["boundaries"]


def _resolve_identity(
    retrieval_session,
    *,
    session_id: str,
    snapshot_id: str,
    actor: str,
) -> MemoryRuntimeIdentity:
    return StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    ).resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor=actor,
        requested_runtime_profile_snapshot_id=snapshot_id,
    )


def _record_product_draft(
    overlay_service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    source_output_ref: str,
):
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=source_output_ref,
        output_text=(
            "The storm arrived at dusk.\n\n"
            "Mira kept walking.\n\n"
            "The bell tower answered."
        ),
        source_format="markdown",
    )
    return overlay_service.record_draft_document(
        identity=identity,
        draft_document=draft,
    )


def _anchor(block_id: str) -> RevisionAnchorRef:
    return RevisionAnchorRef(
        anchor_scope="single_block",
        block_ids=[block_id],
        start_offset=0,
        end_offset=5,
    )


def _writer_result(
    *,
    identity: MemoryRuntimeIdentity,
    output_text: str,
) -> WritingWorkerExecutionResult:
    return WritingWorkerExecutionResult(
        request_id=f"writer-request:{identity.turn_id}",
        packet_id=f"packet:{identity.turn_id}",
        turn_id=identity.turn_id,
        operation_mode="rewrite",
        output_text=output_text,
        output_kind="story_segment",
        result_status="completed",
    )


def _review_material_by_record_id(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    record_id: str,
):
    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain=Domain.CHAPTER.value,
    )
    for material in materials:
        if material.payload.get("record_id") == record_id:
            return material
    raise AssertionError(f"Review material not found: {record_id}")


def _create_adopted_product_candidate(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    output_text: str,
):
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_product_draft(
        overlay_service,
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=draft_ref.replace("artifact:", ""),
    )
    rewrite_request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Adopt this chapter ending.",
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=rewrite_request,
        writer_result=_writer_result(identity=identity, output_text=output_text),
    )
    DraftSelectionService(session=retrieval_session).adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=draft.draft_ref,
    )
    return candidate


async def _search_archival(
    identity: MemoryRuntimeIdentity,
    retrieval_session,
    query: str,
) -> Any:
    return await RetrievalBroker(
        default_story_id=identity.story_id,
        runtime_identity=identity,
        session=retrieval_session,
    ).search_archival(
        MemorySearchArchivalInput(
            query=query,
            domains=[Domain.WORLD_RULE],
            top_k=5,
        )
    )
