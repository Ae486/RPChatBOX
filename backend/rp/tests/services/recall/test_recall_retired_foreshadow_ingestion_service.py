"""Tests for chapter-close retired-foreshadow Recall retention."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast

import pytest

from rp.models.shared.dsl import Domain
from rp.models.memory.crud import MemorySearchRecallInput
from rp.models.retrieval.records import IndexJob
from rp.models.story.runtime import (
    LongformChapterPhase,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.writer.longform_regression_service import LongformRegressionService
from rp.services.recall.retired_foreshadow_ingestion_service import (
    RecallRetiredForeshadowIngestionService,
)
from rp.services.retrieval.broker import RetrievalBroker
from rp.services.retrieval.document_service import RetrievalDocumentService
from rp.services.story.session_service import StorySessionService


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
