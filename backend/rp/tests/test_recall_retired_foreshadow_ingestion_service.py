"""Tests for chapter-close retired-foreshadow Recall retention."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.retrieval_records import IndexJob
from rp.models.story_runtime import (
    LongformChapterPhase,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.authoritative_state_view_service import AuthoritativeStateViewService
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.longform_regression_service import LongformRegressionService
from rp.services.longform_specialist_service import LongformSpecialistService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.recall_retired_foreshadow_ingestion_service import (
    RecallRetiredForeshadowIngestionService,
)
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _index_job(
    *,
    story_id: str,
    asset_id: str,
    state: Literal["completed", "failed"],
    error_message: str | None = None,
) -> IndexJob:
    now = _utcnow()
    return IndexJob(
        job_id=f"{state}_{asset_id}",
        story_id=story_id,
        asset_id=asset_id,
        collection_id=None,
        job_kind="reindex",
        job_state=state,
        target_refs=[f"asset:{asset_id}"],
        warnings=[],
        error_message=error_message,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )


def _seed_story_runtime(
    retrieval_session,
    *,
    foreshadow_registry: list[dict[str, Any]] | None = None,
):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-recall-retired-foreshadow",
        source_workspace_id="workspace-recall-retired-foreshadow",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "chapter_completed",
                "accepted_segments": 1,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": foreshadow_registry or [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.SEGMENT_REVIEW,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        builder_snapshot_json={},
    )
    service.commit()
    session = service.get_session(session.session_id)
    chapter = service.get_chapter_by_index(
        session_id=chapter.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert session is not None
    assert chapter is not None
    return service, session, chapter


class _StaticPlanOrchestrator:
    async def plan(self, **kwargs):
        return OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue the chapter.",
        )


class _HeavyRegressionSpecialist:
    async def analyze(self, **kwargs):
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=chapter_completed"],
            summary_updates=["The bell tower debt finally came due at the river gate."],
            recall_summary_text="Chapter one closed several long-planted threads.",
        )


class _LightRegressionSpecialist:
    async def analyze(self, **kwargs):
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=segment_review"],
            summary_updates=["This should stay transient during light regression."],
        )


class _FailIfRetiredForeshadowIngestionRuns:
    def ingest_retired_foreshadow_summaries(self, **kwargs) -> list[str]:
        raise AssertionError(
            "light regression must not materialize retired-foreshadow recall"
        )


def _build_workflow(retrieval_session) -> ProposalWorkflowService:
    story_session_service = StorySessionService(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    apply_service = ProposalApplyService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
    )
    return ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )


def _build_real_regression_service(retrieval_session) -> LongformRegressionService:
    story_session_service = StorySessionService(retrieval_session)
    specialist_service = LongformSpecialistService(
        authoritative_state_view_service=AuthoritativeStateViewService(
            adapter=StorySessionCoreStateAdapter(story_session_service)
        ),
        projection_state_service=ProjectionStateService(
            story_session_service=story_session_service,
            adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        ),
        memory_os_factory=lambda _story_id: object(),
    )
    return LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=specialist_service,
        proposal_workflow_service=_build_workflow(retrieval_session),
        recall_retired_foreshadow_ingestion_service=(
            RecallRetiredForeshadowIngestionService(retrieval_session)
        ),
    )


@pytest.mark.asyncio
async def test_heavy_regression_ingests_retired_foreshadow_from_updated_session(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The bell tower debt was finally settled at the river gate beneath the "
            "oath-marked lantern."
        ),
    )
    story_session_service.commit()

    updated_session = session.model_copy(
        update={
            "current_state_json": {
                **session.current_state_json,
                "foreshadow_registry": [
                    {
                        "foreshadow_id": "envoy_debt",
                        "summary": "bell tower debt",
                        "status": "active",
                    },
                    {
                        "foreshadow_id": "envoy_debt",
                        "summary": "bell tower debt",
                        "status": "resolved",
                        "resolution": "Settled at the river gate.",
                    },
                    {
                        "foreshadow_id": "masked_seal",
                        "summary": "masked seal clue",
                        "state": "closed",
                    },
                    {
                        "foreshadow_id": "still_open",
                        "summary": "unpaid harbor oath",
                        "status": "active",
                    },
                    {
                        "foreshadow_id": "   ",
                        "summary": "blank id",
                        "status": "resolved",
                    },
                ],
            }
        }
    )

    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=_HeavyRegressionSpecialist(),
        proposal_workflow_service=object(),
        recall_retired_foreshadow_ingestion_service=(
            RecallRetiredForeshadowIngestionService(retrieval_session)
        ),
    )

    async def fake_apply_bundle(**kwargs):
        return updated_session, chapter

    monkeypatch.setattr(regression_service, "_apply_bundle", fake_apply_bundle)

    await regression_service.run_heavy_regression(
        session=session,
        chapter=chapter,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 2
    assert {asset.asset_kind for asset in assets} == {"retired_foreshadow_summary"}
    envoy_asset = next(
        asset for asset in assets if asset.metadata["foreshadow_id"] == "envoy_debt"
    )
    assert envoy_asset.metadata["terminal_status"] == "resolved"
    assert envoy_asset.metadata["materialization_kind"] == (
        "retired_foreshadow_summary"
    )
    assert envoy_asset.metadata["accepted_segment_evidence_count"] == 1
    assert envoy_asset.metadata["continuity_note_count"] == 1
    assert envoy_asset.metadata["includes_chapter_summary"] is True
    envoy_text = envoy_asset.metadata["seed_sections"][0]["text"]
    assert "Terminal status: resolved" in envoy_text
    assert accepted_segment.artifact_id in envoy_text


@pytest.mark.asyncio
async def test_heavy_regression_produces_terminal_foreshadow_snapshots_from_segment_metadata(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The unpaid bell tower debt kept shadowing every bargain at the river gate."
        ),
        metadata={
            "foreshadow_status_updates": [
                {
                    "foreshadow_id": "envoy_debt",
                    "summary": "bell tower debt",
                    "status": "active",
                },
                {
                    "foreshadow_id": "still_open",
                    "summary": "unpaid harbor oath",
                    "status": "active",
                },
            ]
        },
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "At the river gate, the envoy finally settled the bell tower debt and "
            "exposed the masked seal clue."
        ),
        metadata={
            "foreshadow_status_updates": [
                {
                    "foreshadow_id": "envoy_debt",
                    "summary": "bell tower debt",
                    "status": "resolved",
                    "resolution": "Settled at the river gate.",
                },
                {
                    "foreshadow_id": "masked_seal",
                    "summary": "masked seal clue",
                    "state": "closed",
                },
                {
                    "foreshadow_id": "   ",
                    "summary": "blank id",
                    "status": "resolved",
                },
                {
                    "summary": "missing id",
                    "status": "resolved",
                },
                "bad-shape",
            ]
        },
    )
    story_session_service.commit()

    regression_service = _build_real_regression_service(retrieval_session)
    session = story_session_service.get_session(session.session_id)
    chapter = story_session_service.get_chapter_by_index(
        session_id=chapter.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert session is not None
    assert chapter is not None

    updated_session, updated_chapter = await regression_service.run_heavy_regression(
        session=session,
        chapter=chapter,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assert updated_session.current_state_json["foreshadow_registry"] == [
        {
            "foreshadow_id": "envoy_debt",
            "summary": "bell tower debt",
            "status": "resolved",
            "resolution": "Settled at the river gate.",
        },
        {
            "foreshadow_id": "masked_seal",
            "summary": "masked seal clue",
            "state": "closed",
            "status": "closed",
        },
    ]
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 2
    assert {asset.asset_kind for asset in assets} == {"retired_foreshadow_summary"}

    rerun_session = story_session_service.get_session(session.session_id)
    rerun_chapter = story_session_service.get_chapter_by_index(
        session_id=updated_chapter.session_id,
        chapter_index=updated_chapter.chapter_index,
    )
    assert rerun_session is not None
    assert rerun_chapter is not None

    rerun_updated_session, _ = await regression_service.run_heavy_regression(
        session=rerun_session,
        chapter=rerun_chapter,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assert len(rerun_updated_session.current_state_json["foreshadow_registry"]) == 2
    assert (
        len(
            RetrievalDocumentService(retrieval_session).list_story_assets(
                session.story_id
            )
        )
        == 2
    )


@pytest.mark.asyncio
async def test_heavy_regression_skips_foreshadow_updates_without_explicit_terminal_metadata(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The harbor oath still hangs unresolved over the market bridge.",
        metadata={
            "foreshadow_status_updates": [
                {
                    "foreshadow_id": "still_open",
                    "summary": "harbor oath",
                    "status": "active",
                }
            ]
        },
    )
    story_session_service.commit()

    regression_service = _build_real_regression_service(retrieval_session)
    session = story_session_service.get_session(session.session_id)
    chapter = story_session_service.get_chapter_by_index(
        session_id=chapter.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert session is not None
    assert chapter is not None

    updated_session, _ = await regression_service.run_heavy_regression(
        session=session,
        chapter=chapter,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assert updated_session.current_state_json["foreshadow_registry"] == []
    assert (
        RetrievalDocumentService(retrieval_session).list_story_assets(session.story_id)
        == []
    )


@pytest.mark.asyncio
async def test_light_regression_does_not_ingest_retired_foreshadow(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        foreshadow_registry=[
            {
                "foreshadow_id": "envoy_debt",
                "summary": "bell tower debt",
                "status": "resolved",
            }
        ],
    )
    accepted_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The envoy finally paid the bell tower debt.",
    )
    story_session_service.commit()

    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=_LightRegressionSpecialist(),
        proposal_workflow_service=object(),
        recall_retired_foreshadow_ingestion_service=(
            cast(
                RecallRetiredForeshadowIngestionService,
                _FailIfRetiredForeshadowIngestionRuns(),
            )
        ),
    )

    async def fake_apply_bundle(**kwargs):
        return session, chapter

    monkeypatch.setattr(regression_service, "_apply_bundle", fake_apply_bundle)

    await regression_service.run_light_regression(
        session=session,
        chapter=chapter,
        accepted_artifact=accepted_artifact,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assert (
        RetrievalDocumentService(retrieval_session).list_story_assets(session.story_id)
        == []
    )


def test_ingest_retired_foreshadow_skips_nonterminal_and_latest_terminal_wins(
    retrieval_session,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = StorySessionService(retrieval_session).create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The silver oath ledger at the harbor bridge finally matched the old clue."
        ),
    )
    retrieval_session.commit()

    asset_ids = RecallRetiredForeshadowIngestionService(
        retrieval_session
    ).ingest_retired_foreshadow_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        foreshadow_registry=[
            {
                "foreshadow_id": "ledger_clue",
                "summary": "silver oath ledger",
                "status": "active",
            },
            {
                "foreshadow_id": "ledger_clue",
                "summary": "silver oath ledger",
                "status": "resolved",
            },
            {
                "foreshadow_id": "ledger_clue",
                "summary": "silver oath ledger",
                "state": "closed",
            },
            {
                "foreshadow_id": "bridge_debt",
                "summary": "harbor bridge debt",
                "status": "retired",
            },
            {
                "foreshadow_id": "still_open",
                "summary": "open thread",
                "status": "active",
            },
            {"summary": "missing id", "status": "resolved"},
        ],
        chapter_summary_text="Chapter one finally paid off older debts.",
        continuity_notes=["The bridge debt no longer threatens chapter two."],
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    assert len(asset_ids) == 2
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    ledger_asset = next(
        asset for asset in assets if asset.metadata["foreshadow_id"] == "ledger_clue"
    )
    assert ledger_asset.metadata["terminal_status"] == "closed"
    assert (
        "Terminal status: closed" in ledger_asset.metadata["seed_sections"][0]["text"]
    )


def test_ingest_retired_foreshadow_reuses_asset_id_and_reindexes(
    retrieval_session,
    monkeypatch,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallRetiredForeshadowIngestionService(retrieval_session)
    first_asset_ids = service.ingest_retired_foreshadow_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        foreshadow_registry=[
            {
                "foreshadow_id": "envoy_debt",
                "summary": "bell tower debt",
                "status": "resolved",
            }
        ],
        chapter_summary_text="The first chapter settled the old debt.",
        continuity_notes=["The debt should not return next chapter."],
        accepted_segments=[],
    )
    retrieval_session.commit()

    reindexed_asset_ids: list[str] = []

    def reindex_asset(**kwargs):
        reindexed_asset_ids.append(kwargs["asset_id"])
        return _index_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
            state="completed",
        )

    monkeypatch.setattr(service._ingestion_service, "reindex_asset", reindex_asset)

    second_asset_ids = service.ingest_retired_foreshadow_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        foreshadow_registry=[
            {
                "foreshadow_id": "envoy_debt",
                "summary": "bell tower debt",
                "state": "closed",
            }
        ],
        chapter_summary_text="The first chapter settled the old debt for good.",
        continuity_notes=["The debt should not return next chapter."],
        accepted_segments=[],
    )
    retrieval_session.commit()

    assert second_asset_ids == first_asset_ids
    assert reindexed_asset_ids == first_asset_ids
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 1
    assert assets[0].asset_id == first_asset_ids[0]
    assert assets[0].metadata["terminal_status"] == "closed"


@pytest.mark.asyncio
async def test_ingest_retired_foreshadow_searchable_by_materialization_kind_filter(
    retrieval_session,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = StorySessionService(retrieval_session).create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The masked seal clue finally resolved when the oath ledger was opened."
        ),
    )
    retrieval_session.commit()

    asset_ids = RecallRetiredForeshadowIngestionService(
        retrieval_session
    ).ingest_retired_foreshadow_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        foreshadow_registry=[
            {
                "foreshadow_id": "masked_seal",
                "summary": "masked seal clue",
                "status": "resolved",
            }
        ],
        chapter_summary_text="Chapter one finally resolved the masked seal clue.",
        continuity_notes=["The seal clue no longer needs to stay active."],
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="masked seal clue oath ledger resolved",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
            filters={
                "materialization_kinds": ["retired_foreshadow_summary"],
            },
        )
    )

    assert result.hits
    assert result.hits[0].metadata["asset_id"] == asset_ids[0]
    assert result.hits[0].metadata["materialization_kind"] == (
        "retired_foreshadow_summary"
    )
    assert result.hits[0].metadata["foreshadow_id"] == "masked_seal"
    assert result.hits[0].metadata["materialized_to_recall"] is True


def test_ingest_retired_foreshadow_raises_explicit_failure(
    retrieval_session,
    monkeypatch,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallRetiredForeshadowIngestionService(retrieval_session)
    asset_id = service._build_asset_id(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        foreshadow_id="masked_seal",
    )

    monkeypatch.setattr(
        service._ingestion_service,
        "ingest_asset",
        lambda **kwargs: _index_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
            state="failed",
            error_message="embedding_provider_unavailable",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "recall_retired_foreshadow_ingestion_failed:"
            f"{asset_id}:embedding_provider_unavailable"
        ),
    ):
        service.ingest_retired_foreshadow_summaries(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            source_workspace_id=session.source_workspace_id,
            foreshadow_registry=[
                {
                    "foreshadow_id": "masked_seal",
                    "summary": "masked seal clue",
                    "status": "resolved",
                }
            ],
            chapter_summary_text="The clue finally resolved.",
            continuity_notes=[],
            accepted_segments=[],
        )
