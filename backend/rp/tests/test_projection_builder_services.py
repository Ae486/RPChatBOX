"""Tests for Phase E3 settled projection refresh and builder context flow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import desc
from sqlmodel import select

from models.rp_story_store import BranchHeadRecord, StoryTurnRecord
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import RetrievalHit
from rp.models.projection_refresh import (
    ProjectionRefreshRequest,
    ProjectionRefreshServiceError,
)
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
    StorySegmentStructuredMetadata,
    StoryArtifactStatus,
    StoryArtifactKind,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
)
from rp.graphs.story_graph_nodes import StoryGraphNodes
from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.services.authoritative_state_view_service import AuthoritativeStateViewService
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.longform_orchestrator_service import LongformOrchestratorService
from rp.services.longform_specialist_service import LongformSpecialistService
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.projection_refresh_service import ProjectionRefreshService
from rp.services.proposal_repository import ProposalRepository
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story_block_consumer_state_service import (
    StoryBlockConsumerStateService,
)
from rp.services.story_block_prompt_compile_service import (
    StoryBlockPromptCompileService,
)
from rp.services.story_block_prompt_context_service import (
    StoryBlockPromptContextService,
)
from rp.services.story_block_prompt_render_service import (
    StoryBlockPromptRenderService,
)
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.services.writing_packet_builder import WritingPacketBuilder


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={"style_rules": ["Lean"]},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
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
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
            "writer_hints": ["Persisted Hint"],
        },
    )
    service.commit()
    return (
        service.get_session(session.session_id),
        service.get_chapter_by_index(
            session_id=session.session_id,
            chapter_index=1,
        ),
        service,
    )


def _build_boundary_services(
    service: StorySessionService,
) -> tuple[
    AuthoritativeStateViewService,
    ProjectionStateService,
]:
    authoritative_state_view_service = AuthoritativeStateViewService(
        adapter=StorySessionCoreStateAdapter(service)
    )
    projection_state_service = ProjectionStateService(
        story_session_service=service,
        adapter=ChapterWorkspaceProjectionAdapter(service),
    )
    return authoritative_state_view_service, projection_state_service


class _NoopRegressionService:
    async def run_light_regression(
        self,
        *,
        session,
        chapter,
        accepted_artifact,
        model_id,
        provider_id,
        runtime_identity=None,
    ):
        return session, chapter

    async def run_heavy_regression(
        self, *, session, chapter, model_id, provider_id, runtime_identity=None
    ):
        return session, chapter


class _RecordingBlockConsumerStateService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def mark_consumer_synced(self, *, session_id: str, consumer_key: str):
        self.calls.append((session_id, consumer_key))
        return None


class _RecordingStoryLlmGateway:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[dict] = []

    async def complete_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self._response_text

    @staticmethod
    def extract_json_object(raw: str) -> dict:
        return json.loads(raw)


class _StubMemoryOsService:
    def __init__(
        self,
        *,
        archival_hits: list[RetrievalHit] | None = None,
        recall_hits: list[RetrievalHit] | None = None,
    ) -> None:
        self._archival_hits = list(archival_hits or [])
        self._recall_hits = list(recall_hits or [])

    async def search_archival(self, *_args, **_kwargs):
        return SimpleNamespace(hits=list(self._archival_hits))

    async def search_recall(self, *_args, **_kwargs):
        return SimpleNamespace(hits=list(self._recall_hits))


class _RecordingMemoryOsService(_StubMemoryOsService):
    def __init__(self) -> None:
        super().__init__()
        self.archival_inputs: list[Any] = []
        self.recall_inputs: list[Any] = []

    async def search_archival(self, input_model, *_args, **_kwargs):
        self.archival_inputs.append(input_model)
        return await super().search_archival(input_model, *_args, **_kwargs)

    async def search_recall(self, input_model, *_args, **_kwargs):
        self.recall_inputs.append(input_model)
        return await super().search_recall(input_model, *_args, **_kwargs)


class _FailingMemoryOsService:
    async def search_archival(self, *_args, **_kwargs):
        raise AssertionError("retrieval should not run for this plan")

    async def search_recall(self, *_args, **_kwargs):
        raise AssertionError("retrieval should not run for this plan")


def _build_turn_domain_service(
    service: StorySessionService,
    *,
    orchestrator_service=None,
    specialist_service=None,
    block_consumer_state_service=None,
    runtime_identity_service=None,
    runtime_workspace_material_service=None,
) -> StoryTurnDomainService:
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    return StoryTurnDomainService(
        story_session_service=service,
        orchestrator_service=orchestrator_service or SimpleNamespace(),
        specialist_service=cast(
            LongformSpecialistService,
            specialist_service or SimpleNamespace(),
        ),
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        projection_state_service=projection_state_service,
        writing_packet_builder=WritingPacketBuilder(),
        writing_worker_execution_service=SimpleNamespace(),
        regression_service=_NoopRegressionService(),
        block_consumer_state_service=block_consumer_state_service,
        runtime_identity_service=runtime_identity_service,
        runtime_workspace_material_service=runtime_workspace_material_service,
    )


def test_authoritative_state_view_service_reads_session_scoped_objects(
    retrieval_session,
):
    session, _, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, _ = _build_boundary_services(service)

    chapter_digest = authoritative_state_view_service.get_chapter_digest(
        session_id=session.session_id
    )
    narrative_progress = authoritative_state_view_service.get_narrative_progress(
        session_id=session.session_id
    )

    assert chapter_digest == {"current_chapter": 1, "title": "Chapter One"}
    assert (
        narrative_progress["current_phase"]
        == LongformChapterPhase.OUTLINE_DRAFTING.value
    )


def test_projection_state_service_updates_slots_and_rollover(retrieval_session):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)

    projection_state_service.set_current_outline(
        chapter_workspace_id=chapter.chapter_workspace_id,
        outline_text="Fresh Outline",
    )
    projection_state_service.append_recent_segment(
        chapter_workspace_id=chapter.chapter_workspace_id,
        excerpt="Segment B",
    )
    next_chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 2",
    )
    projection_state_service.seed_next_chapter(
        previous_chapter_workspace_id=chapter.chapter_workspace_id,
        next_chapter_workspace_id=next_chapter.chapter_workspace_id,
        next_chapter_index=2,
    )

    updated_chapter = service.get_chapter_workspace(chapter.chapter_workspace_id)
    seeded_chapter = service.get_chapter_workspace(next_chapter.chapter_workspace_id)

    assert updated_chapter is not None
    assert seeded_chapter is not None
    assert updated_chapter.builder_snapshot_json["current_outline_digest"] == [
        "Fresh Outline"
    ]
    assert updated_chapter.builder_snapshot_json["recent_segment_digest"] == [
        "Segment A",
        "Segment B",
    ]
    assert seeded_chapter.builder_snapshot_json["blueprint_digest"] == ["Blueprint A"]
    assert seeded_chapter.builder_snapshot_json["current_outline_digest"] == []
    assert seeded_chapter.builder_snapshot_json["recent_segment_digest"] == []
    assert seeded_chapter.builder_snapshot_json["chapter_index"] == 2


def test_builder_projection_context_service_ignores_writer_hints(retrieval_session):
    session, _, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)
    context_service = BuilderProjectionContextService(projection_state_service)

    context_sections = context_service.build_context_sections(
        session_id=session.session_id
    )

    assert [section["label"] for section in context_sections] == [
        "foundation_digest",
        "blueprint_digest",
        "current_outline_digest",
        "recent_segment_digest",
        "current_state_digest",
    ]


def test_writing_packet_builder_uses_projection_sections_and_runtime_hints(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)
    context_service = BuilderProjectionContextService(projection_state_service)
    builder = WritingPacketBuilder()

    packet = builder.build(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        projection_context_sections=context_service.build_context_sections(
            session_id=session.session_id
        ),
        runtime_writer_hints=["Runtime Hint"],
        user_instruction="Write the next segment.",
    )

    assert [section["label"] for section in packet.context_sections] == [
        "foundation_digest",
        "blueprint_digest",
        "current_outline_digest",
        "recent_segment_digest",
        "current_state_digest",
        "writer_hints",
    ]
    assert packet.context_sections[-1]["items"] == ["Runtime Hint"]


def test_writing_packet_builder_has_no_raw_retrieval_hit_surface(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)
    context_service = BuilderProjectionContextService(projection_state_service)
    builder = WritingPacketBuilder()

    packet = builder.build(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        projection_context_sections=context_service.build_context_sections(
            session_id=session.session_id
        ),
        runtime_writer_hints=["Composed specialist continuity hint."],
        user_instruction="Write the next segment.",
    )
    payload = packet.model_dump(mode="json")

    assert "retrieval_hits" not in payload
    assert "archival_hits" not in payload
    assert "recall_hits" not in payload
    assert packet.context_sections[-1] == {
        "label": "writer_hints",
        "items": ["Composed specialist continuity hint."],
    }


def test_projection_refresh_service_updates_settled_slots_only(retrieval_session):
    _, chapter, service = _seed_story_runtime(retrieval_session)
    refresh_service = ProjectionRefreshService(service)

    updated_chapter = refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
    )

    assert updated_chapter.builder_snapshot_json["foundation_digest"] == ["New Found"]
    assert "writer_hints" not in updated_chapter.builder_snapshot_json


def test_projection_refresh_service_requires_identity_for_explicit_runtime_request(
    retrieval_session,
):
    _, chapter, service = _seed_story_runtime(retrieval_session)
    refresh_service = ProjectionRefreshService(service)

    with pytest.raises(ProjectionRefreshServiceError) as exc_info:
        refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=SpecialistResultBundle(
                foundation_digest=["New Found"],
                blueprint_digest=["New Blueprint"],
                current_outline_digest=["New Outline"],
                recent_segment_digest=["New Segment"],
                current_state_digest=["New State"],
            ),
            refresh_request=ProjectionRefreshRequest(),
        )

    assert exc_info.value.code == "projection_refresh_identity_required"


def test_story_turn_domain_service_build_packet_attaches_deterministic_read_manifest(
    retrieval_session,
):
    session, _, service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.packet_manifest",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    runtime_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    RuntimeWorkspaceMaterialService(session=retrieval_session).record_material(
        RuntimeWorkspaceMaterial(
            material_id="packet-card-R1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=runtime_identity,
            domain="chapter",
            domain_path="runtime.packet.card",
            payload={"title": "Packet Card"},
            visibility="writer_visible",
            created_by="worker.retrieval",
        )
    )
    turn_domain_service = _build_turn_domain_service(
        service,
        runtime_identity_service=identity_service,
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
    )
    bundle = SpecialistResultBundle(
        foundation_digest=["Found A"],
        blueprint_digest=["Blueprint A"],
        current_outline_digest=["Outline A"],
        recent_segment_digest=["Segment A"],
        current_state_digest=["State A"],
        writer_hints=["Hint A"],
    )

    packet_a = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        specialist_bundle=bundle,
        runtime_identity=runtime_identity,
    )
    packet_b = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        specialist_bundle=bundle,
        runtime_identity=runtime_identity,
    )

    manifest_a = packet_a.metadata["runtime_read_manifest"]
    manifest_b = packet_b.metadata["runtime_read_manifest"]

    assert manifest_a["manifest_id"] == manifest_b["manifest_id"]
    assert manifest_a["identity"]["turn_id"] == runtime_identity.turn_id
    assert manifest_a["active_branch_lineage"] == [runtime_identity.branch_head_id]
    assert manifest_a["retrieval_card_refs"] == ["packet-card-R1"]
    assert any(
        item["reason"] == "packet_visible_runtime_workspace_only"
        for item in manifest_a["omitted_refs"]
    )


def test_story_turn_domain_service_build_packet_uses_runtime_workspace_retrieval_context_and_records_usage(
    retrieval_session,
):
    session, _, service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.packet_retrieval_usage",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    runtime_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="packet-card-R1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=runtime_identity,
            domain="chapter",
            domain_path="chapter.runtime.packet.card",
            short_id="R1",
            payload={
                "summary": "A recalled storm callback matters here.",
                "title": "Storm Callback",
            },
            visibility="writer_visible",
            created_by="worker.specialist",
        )
    )
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="packet-expanded-X1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            identity=runtime_identity,
            domain="chapter",
            domain_path="chapter.runtime.packet.expanded",
            short_id="X1",
            payload={
                "summary": "Expanded detail: the seal broke during the first storm.",
                "text": "Expanded detail: the seal broke during the first storm.",
                "title": "Storm Callback Expanded",
            },
            lifecycle=RuntimeWorkspaceMaterialLifecycle.EXPANDED,
            visibility="writer_visible",
            created_by="worker.specialist",
        )
    )
    turn_domain_service = _build_turn_domain_service(
        service,
        runtime_identity_service=identity_service,
        runtime_workspace_material_service=material_service,
    )
    bundle = SpecialistResultBundle(
        foundation_digest=["Found A"],
        blueprint_digest=["Blueprint A"],
        current_outline_digest=["Outline A"],
        recent_segment_digest=["Segment A"],
        current_state_digest=["State A"],
        writer_hints=["Hint A"],
    )
    plan = OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
    )

    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=plan,
        specialist_bundle=bundle,
        runtime_identity=runtime_identity,
    )

    retrieval_sections = [
        section
        for section in packet.context_sections
        if section.get("label") == "retrieval_context"
    ]
    assert len(retrieval_sections) == 1
    assert retrieval_sections[0]["items"] == [
        "R1 [retrieval_card] Storm Callback: A recalled storm callback matters here.",
        "X1 [retrieval_expanded_chunk] Storm Callback Expanded: Expanded detail: the seal broke during the first storm.",
    ]
    bundle_metadata = packet.metadata["worker_source_ref_bundle"]
    assert bundle_metadata["retrieval_card_material_ids"] == ["packet-card-R1"]
    assert bundle_metadata["retrieval_expanded_chunk_material_ids"] == [
        "packet-expanded-X1"
    ]
    assert bundle_metadata["retrieval_usage_material_ids"] == []

    usage_records = material_service.list_materials(
        identity=runtime_identity,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
    )
    assert usage_records == []

    response = turn_domain_service.persist_generated_artifact(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
            model_id="model",
        ),
        packet=packet,
        plan=plan,
        text="Generated segment text.",
        specialist_bundle=bundle,
        pending_artifact_id=None,
    )
    artifact = service.get_artifact(response.artifact_id)

    usage_records = material_service.list_materials(
        identity=runtime_identity,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
    )
    assert len(usage_records) == 1
    assert usage_records[0].payload["used_card_material_ids"] == ["packet-card-R1"]
    assert usage_records[0].payload["used_expanded_chunk_material_ids"] == [
        "packet-expanded-X1"
    ]

    assert artifact is not None
    artifact_bundle = artifact.metadata["worker_source_ref_bundle"]
    assert artifact_bundle["retrieval_card_material_ids"] == ["packet-card-R1"]
    assert artifact_bundle["retrieval_expanded_chunk_material_ids"] == [
        "packet-expanded-X1"
    ]
    assert artifact_bundle["retrieval_usage_material_ids"] == [
        usage_records[0].material_id
    ]
    assert (
        artifact.metadata["runtime_read_manifest_id"]
        == packet.metadata["runtime_read_manifest_id"]
    )


def test_orchestrator_fallback_uses_projection_slots_not_writer_hints(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    orchestrator_service = LongformOrchestratorService(
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
    )
    plan = orchestrator_service._fallback_plan(
        session=session,
        chapter=chapter,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        user_prompt=None,
        projection_snapshot=projection_state_service.build_planner_projection(
            session_id=session.session_id
        ),
    )

    assert "Persisted Hint" not in " ".join(plan.archival_queries)
    assert any("Outline A" in query for query in plan.archival_queries)


def test_orchestrator_accept_fallback_does_not_request_retrieval(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    orchestrator_service = LongformOrchestratorService(
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
    )

    plan = orchestrator_service._fallback_plan(
        session=session,
        chapter=chapter,
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        user_prompt=None,
        projection_snapshot=projection_state_service.build_planner_projection(
            session_id=session.session_id
        ),
    )

    assert plan.needs_retrieval is False
    assert plan.archival_queries == []
    assert plan.recall_queries == []


@pytest.mark.asyncio
async def test_specialist_skips_memory_os_when_plan_does_not_need_retrieval(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    specialist_service = LongformSpecialistService(
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
        memory_os_factory=lambda _story_id: _FailingMemoryOsService(),
    )

    bundle = await specialist_service.analyze(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            needs_retrieval=False,
            archival_queries=["should not run"],
            recall_queries=["should not run"],
            writer_instruction="Accept the pending segment.",
        ),
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt=None,
        accepted_segments=[],
        pending_artifact=None,
    )

    assert bundle.state_patch_proposals["narrative_progress"]["last_command"] == (
        LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT.value
    )


def test_story_segment_structured_metadata_normalizes_latest_foreshadow_update():
    metadata = StorySegmentStructuredMetadata(
        foreshadow_status_updates=[
            {
                "foreshadow_id": "envoy_debt",
                "status": "active",
                "summary": "  bell tower debt  ",
            },
            {
                "foreshadow_id": "   ",
                "status": "closed",
            },
            {
                "foreshadow_id": "envoy_debt",
                "status": "resolved",
                "summary": "bell tower debt",
                "resolution": " Settled at the river gate. ",
            },
        ]
    )

    assert metadata.to_artifact_metadata() == {
        "foreshadow_status_updates": [
            {
                "foreshadow_id": "envoy_debt",
                "status": "resolved",
                "summary": "bell tower debt",
                "resolution": "Settled at the river gate.",
            }
        ]
    }


def test_story_segment_structured_metadata_schema_stays_typed_and_degrades_bad_items():
    schema = SpecialistResultBundle.model_json_schema()
    assert (
        schema["$defs"]["StorySegmentStructuredMetadata"]["properties"][
            "foreshadow_status_updates"
        ]["items"]["$ref"]
        == "#/$defs/ForeshadowStatusUpdateMetadata"
    )

    bundle = SpecialistResultBundle.model_validate(
        {
            "story_segment_metadata": {
                "foreshadow_status_updates": [
                    {
                        "foreshadow_id": "envoy_debt",
                        "status": "resolved",
                        "summary": " bell tower debt ",
                    },
                    "not-a-dict",
                    {
                        "foreshadow_id": "   ",
                        "status": "closed",
                    },
                ],
                "unsupported_family": [{"ignored": True}],
            }
        }
    )

    assert bundle.story_segment_metadata.to_artifact_metadata() == {
        "foreshadow_status_updates": [
            {
                "foreshadow_id": "envoy_debt",
                "status": "resolved",
                "summary": "bell tower debt",
            }
        ]
    }


def test_story_turn_accept_outline_updates_projection_via_boundary_service(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    turn_domain_service = _build_turn_domain_service(service)
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Accepted Outline Text",
    )

    response = turn_domain_service.accept_outline(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
            model_id="model",
            target_artifact_id=outline.artifact_id,
        )
    )
    updated_chapter = service.get_current_chapter(session.session_id)

    assert updated_chapter is not None
    assert updated_chapter.builder_snapshot_json["current_outline_digest"] == [
        "Accepted Outline Text"
    ]
    assert response.current_phase == LongformChapterPhase.SEGMENT_DRAFTING


class _AsyncOrchestratorService:
    async def plan(self, **_kwargs):
        return OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        )


class _AsyncSpecialistService:
    async def analyze(self, **_kwargs):
        return SpecialistResultBundle(
            foundation_digest=["Found A"],
            blueprint_digest=["Blueprint A"],
            current_outline_digest=["Outline A"],
            recent_segment_digest=["Segment A"],
            current_state_digest=["State A"],
            writer_hints=["Hint A"],
        )


@pytest.mark.asyncio
async def test_story_turn_domain_service_marks_consumers_synced(retrieval_session):
    session, _, service = _seed_story_runtime(retrieval_session)
    recorder = _RecordingBlockConsumerStateService()
    turn_domain_service = _build_turn_domain_service(
        service,
        orchestrator_service=_AsyncOrchestratorService(),
        specialist_service=_AsyncSpecialistService(),
        block_consumer_state_service=recorder,
    )

    plan = await turn_domain_service.orchestrator_plan(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        target_artifact_id=None,
    )
    bundle = await turn_domain_service.specialist_analyze(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        plan=plan,
        pending_artifact_id=None,
        accepted_segment_ids=[],
    )
    _ = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=plan,
        specialist_bundle=bundle,
    )

    assert recorder.calls == [
        (session.session_id, "story.orchestrator"),
        (session.session_id, "story.specialist"),
        (session.session_id, "story.writer_packet"),
    ]


@pytest.mark.asyncio
async def test_story_graph_runner_pins_runtime_identity_before_special_command(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.OUTLINE_REVIEW,
    )
    service.update_session(
        session_id=session.session_id,
        current_phase=LongformChapterPhase.OUTLINE_REVIEW,
    )
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Pinned Identity Outline",
    )
    service.commit()
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )
    runner = StoryGraphRunner(
        nodes=StoryGraphNodes(
            domain_service=_build_turn_domain_service(
                service,
                runtime_identity_service=identity_service,
            )
        )
    )

    response = await runner.run_turn(
        LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
            model_id="model",
            target_artifact_id=outline.artifact_id,
        )
    )
    debug = runner.get_runtime_debug(session_id=session.session_id)
    turn = retrieval_session.exec(
        select(StoryTurnRecord)
        .where(StoryTurnRecord.session_id == session.session_id)
        .order_by(desc(StoryTurnRecord.created_at))
    ).first()
    branch = retrieval_session.exec(
        select(BranchHeadRecord).where(
            BranchHeadRecord.session_id == session.session_id
        )
    ).first()

    assert response.current_phase == LongformChapterPhase.SEGMENT_DRAFTING
    assert branch is not None
    assert turn is not None
    assert turn.branch_head_id == branch.branch_head_id
    assert turn.runtime_profile_snapshot_id
    assert turn.status == "completed"
    assert turn.completed_at is not None
    meaningful_state = debug["latest_meaningful_checkpoint"]["state"]
    assert meaningful_state["branch_head_id"] == branch.branch_head_id
    assert meaningful_state["turn_id"] == turn.turn_id
    assert (
        meaningful_state["runtime_profile_snapshot_id"]
        == turn.runtime_profile_snapshot_id
    )
    assert meaningful_state["runtime_identity"]["turn_id"] == turn.turn_id


@pytest.mark.asyncio
async def test_story_graph_runner_marks_pinned_turn_failed_on_command_error(
    retrieval_session,
):
    session, _, service = _seed_story_runtime(retrieval_session)
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )
    runner = StoryGraphRunner(
        nodes=StoryGraphNodes(
            domain_service=_build_turn_domain_service(
                service,
                runtime_identity_service=identity_service,
            )
        )
    )

    with pytest.raises(ValueError):
        await runner.run_turn(
            LongformTurnRequest(
                session_id=session.session_id,
                command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
                model_id="model",
            )
        )
    turn = retrieval_session.exec(
        select(StoryTurnRecord)
        .where(StoryTurnRecord.session_id == session.session_id)
        .order_by(desc(StoryTurnRecord.created_at))
    ).first()

    assert turn is not None
    assert turn.status == "failed"
    assert turn.completed_at is not None


@pytest.mark.asyncio
async def test_specialist_retrieval_inputs_carry_runtime_identity_filters(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    recorder = _RecordingMemoryOsService()
    specialist_service = LongformSpecialistService(
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
        memory_os_factory=lambda story_id, **_kwargs: recorder,
    )
    runtime_identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch:test:main",
        turn_id="turn:test:1",
        runtime_profile_snapshot_id="snapshot:test:1",
    )

    await specialist_service.analyze(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            needs_retrieval=True,
            archival_queries=["archive pin"],
            recall_queries=["recall pin"],
            writer_instruction="Write the next segment.",
        ),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        accepted_segments=[],
        pending_artifact=None,
        runtime_identity=runtime_identity,
    )

    assert recorder.archival_inputs
    assert recorder.recall_inputs
    assert (
        recorder.archival_inputs[0].filters["runtime_identity"][
            "runtime_profile_snapshot_id"
        ]
        == "snapshot:test:1"
    )
    assert recorder.recall_inputs[0].filters["runtime_identity"]["turn_id"] == (
        "turn:test:1"
    )


@pytest.mark.asyncio
async def test_orchestrator_and_specialist_include_block_prompt_context(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = (
        _build_boundary_services(service)
    )
    proposal_repository = ProposalRepository(retrieval_session)
    version_history_read_service = VersionHistoryReadService(
        adapter=StorySessionCoreStateAdapter(service),
        proposal_repository=proposal_repository,
    )
    builder_projection_context_service = BuilderProjectionContextService(
        projection_state_service
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=service,
        builder_projection_context_service=builder_projection_context_service,
        proposal_repository=proposal_repository,
        version_history_read_service=version_history_read_service,
    )
    rp_block_read_service = RpBlockReadService(
        story_session_service=service,
        builder_projection_context_service=builder_projection_context_service,
        memory_inspection_read_service=memory_inspection_read_service,
    )
    consumer_state_service = StoryBlockConsumerStateService(
        session=retrieval_session,
        story_session_service=service,
        rp_block_read_service=rp_block_read_service,
    )
    block_prompt_context_service = StoryBlockPromptContextService(
        rp_block_read_service=rp_block_read_service,
        story_block_consumer_state_service=consumer_state_service,
    )
    block_prompt_render_service = StoryBlockPromptRenderService()
    block_prompt_compile_service = StoryBlockPromptCompileService(
        story_block_prompt_context_service=block_prompt_context_service,
        story_block_prompt_render_service=block_prompt_render_service,
        story_block_consumer_state_service=consumer_state_service,
    )
    orchestrator_gateway = _RecordingStoryLlmGateway(
        response_text=json.dumps(
            {
                "output_kind": StoryArtifactKind.STORY_SEGMENT.value,
                "needs_retrieval": True,
                "archival_queries": ["archive policy"],
                "recall_queries": ["storm callback"],
                "specialist_focus": ["segment continuity"],
                "writer_instruction": "Write the next segment.",
                "notes": ["gateway"],
            }
        )
    )
    specialist_gateway = _RecordingStoryLlmGateway(
        response_text=SpecialistResultBundle(
            foundation_digest=["Found A"],
            blueprint_digest=["Blueprint A"],
            current_outline_digest=["Outline A"],
            recent_segment_digest=["Segment A"],
            current_state_digest=["State A"],
            writer_hints=["Hint A"],
            story_segment_metadata=StorySegmentStructuredMetadata(
                foreshadow_status_updates=[
                    {
                        "foreshadow_id": "envoy_debt",
                        "status": "resolved",
                        "summary": "bell tower debt",
                    }
                ]
            ),
        ).model_dump_json()
    )
    archival_hits = [
        RetrievalHit(
            hit_id="chunk-archive-1",
            query_id="rq-archive-1",
            layer=Layer.ARCHIVAL.value,
            domain=Domain.WORLD_RULE,
            domain_path="foundation.world.rules.archive_policy",
            knowledge_ref=ObjectRef(
                object_id="world_rule.archive_policy",
                layer=Layer.ARCHIVAL,
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.rules.archive_policy",
                scope="story",
                revision=2,
            ),
            excerpt_text="Archive policy says all relics must be sealed at dusk.",
            score=0.91,
            rank=1,
            metadata={"title": "Archive Policy"},
            provenance_refs=["prov:archive-policy"],
        )
    ]
    recall_hits = [
        RetrievalHit(
            hit_id="recall-note-1",
            query_id="rq-recall-1",
            layer=Layer.RECALL.value,
            domain=Domain.CHAPTER,
            domain_path="chapter.one.scene.callback",
            knowledge_ref=ObjectRef(
                object_id="recall.note.storm_callback",
                layer=Layer.RECALL,
                domain=Domain.CHAPTER,
                domain_path="chapter.one.scene.callback",
                scope="story",
                revision=1,
            ),
            excerpt_text="Earlier in chapter one, the seal broke during the storm.",
            score=0.77,
            rank=1,
            metadata={
                "title": "Storm Callback",
                "layer": "recall",
                "source_family": "longform_story_runtime",
                "materialization_event": "heavy_regression.chapter_close",
                "materialization_kind": "accepted_story_segment",
                "materialized_to_recall": True,
                "chapter_index": 1,
                "artifact_id": "artifact-storm",
                "artifact_revision": 2,
                "asset_id": "recall_detail_artifact-storm",
                "asset_kind": "accepted_story_segment",
                "source_ref": (
                    "story_session:session-1:chapter:1:artifact:artifact-storm"
                ),
            },
            provenance_refs=["prov:storm-callback"],
        )
    ]
    orchestrator_service = LongformOrchestratorService(
        llm_gateway=orchestrator_gateway,
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
        story_block_prompt_compile_service=block_prompt_compile_service,
        story_block_prompt_context_service=block_prompt_context_service,
    )
    specialist_service = LongformSpecialistService(
        llm_gateway=specialist_gateway,
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
        memory_os_factory=lambda _story_id: _StubMemoryOsService(
            archival_hits=archival_hits,
            recall_hits=recall_hits,
        ),
        story_block_prompt_compile_service=block_prompt_compile_service,
        story_block_prompt_context_service=block_prompt_context_service,
    )

    plan = await orchestrator_service.plan(
        session=session,
        chapter=chapter,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        target_artifact_id=None,
    )
    bundle = await specialist_service.analyze(
        session=session,
        chapter=chapter,
        plan=plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue.",
        accepted_segments=[],
        pending_artifact=None,
    )

    orchestrator_payload = json.loads(
        orchestrator_gateway.calls[0]["messages"][1].content
    )
    specialist_payload = json.loads(specialist_gateway.calls[0]["messages"][1].content)
    orchestrator_system_prompt = orchestrator_gateway.calls[0]["messages"][0].content
    specialist_system_prompt = specialist_gateway.calls[0]["messages"][0].content

    assert orchestrator_payload["block_context"]["consumer_key"] == "story.orchestrator"
    assert specialist_payload["block_context"]["consumer_key"] == "story.specialist"
    assert (
        orchestrator_payload["authoritative_state"]["chapter_digest"]["title"]
        == "Chapter One"
    )
    assert orchestrator_payload["projection_state"]["current_outline_digest"] == [
        "Outline A"
    ]
    assert specialist_payload["projection_state"]["current_outline_digest"] == [
        "Outline A"
    ]
    assert {
        block["label"]
        for block in orchestrator_payload["block_context"]["attached_blocks"]
    } == {
        "chapter.current",
        "character.state_digest",
        "foreshadow.registry",
        "narrative_progress.current",
        "plot_thread.active",
        "timeline.event_spine",
        "projection.foundation_digest",
        "projection.blueprint_digest",
        "projection.current_outline_digest",
        "projection.recent_segment_digest",
        "projection.current_state_digest",
    }
    assert (
        specialist_payload["block_context"]["attached_blocks"]
        == orchestrator_payload["block_context"]["attached_blocks"]
    )
    assert specialist_payload["archival_hits"][0]["excerpt_text"] == (
        "Archive policy says all relics must be sealed at dusk."
    )
    assert specialist_payload["recall_hits"][0]["excerpt_text"] == (
        "Earlier in chapter one, the seal broke during the storm."
    )
    assert (
        specialist_payload["recall_hits"][0]["source_family"]
        == "longform_story_runtime"
    )
    assert (
        specialist_payload["recall_hits"][0]["materialization_kind"]
        == "accepted_story_segment"
    )
    assert (
        specialist_payload["recall_hits"][0]["materialization_event"]
        == "heavy_regression.chapter_close"
    )
    assert (
        specialist_payload["recall_hits"][0]["metadata"]["artifact_id"]
        == "artifact-storm"
    )
    assert specialist_payload["archival_block_views"][0]["source"] == "retrieval_store"
    assert (
        specialist_payload["archival_block_views"][0]["label"]
        == "world_rule.archive_policy"
    )
    assert (
        specialist_payload["archival_block_views"][0]["data_json"]["excerpt_text"]
        == "Archive policy says all relics must be sealed at dusk."
    )
    assert specialist_payload["recall_block_views"][0]["source"] == "retrieval_store"
    assert (
        specialist_payload["recall_block_views"][0]["label"]
        == "recall.note.storm_callback"
    )
    assert (
        specialist_payload["recall_block_views"][0]["metadata"]["query_id"]
        == "rq-recall-1"
    )
    assert (
        specialist_payload["recall_block_views"][0]["metadata"]["materialization_kind"]
        == "accepted_story_segment"
    )
    assert (
        specialist_payload["recall_block_views"][0]["data_json"]["source_family"]
        == "longform_story_runtime"
    )
    assert "[BLOCK_PROMPT_CONTEXT]" in orchestrator_system_prompt
    assert 'label="chapter.current"' in orchestrator_system_prompt
    assert 'label="projection.current_outline_digest"' in orchestrator_system_prompt
    assert "[BLOCK_PROMPT_CONTEXT]" in specialist_system_prompt
    assert 'label="chapter.current"' in specialist_system_prompt
    assert plan.notes == ["gateway"]
    assert bundle.writer_hints == ["Hint A"]
    assert [
        item.model_dump(mode="json", exclude_none=True)
        for item in bundle.story_segment_metadata.foreshadow_status_updates
    ] == [
        {
            "foreshadow_id": "envoy_debt",
            "status": "resolved",
            "summary": "bell tower debt",
        }
    ]
