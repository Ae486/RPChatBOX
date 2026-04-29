"""Tests for Phase E3 settled projection refresh and builder context flow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import cast

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import RetrievalHit
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
        self, *, session, chapter, accepted_artifact, model_id, provider_id
    ):
        return session, chapter

    async def run_heavy_regression(self, *, session, chapter, model_id, provider_id):
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


def _build_turn_domain_service(
    service: StorySessionService,
    *,
    orchestrator_service=None,
    specialist_service=None,
    block_consumer_state_service=None,
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
                "needs_retrieval": False,
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
