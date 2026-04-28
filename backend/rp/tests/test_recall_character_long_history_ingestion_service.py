"""Tests for chapter-close per-character Recall retention."""

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
from rp.services.longform_regression_service import LongformRegressionService
from rp.services.recall_character_long_history_ingestion_service import (
    RecallCharacterLongHistoryIngestionService,
)
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.story_session_service import StorySessionService


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
    character_state_digest: dict[str, Any] | None = None,
):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-recall-character-history",
        source_workspace_id="workspace-recall-character-history",
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
            "foreshadow_registry": [],
            "character_state_digest": character_state_digest or {},
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
            summary_updates=["Hero now distrusts the harbor bellmaster."],
            recall_summary_text="Chapter one closed with the hero on alert.",
        )


class _LightRegressionSpecialist:
    async def analyze(self, **kwargs):
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=segment_review"],
            summary_updates=["This should stay transient during light regression."],
        )


class _FailIfCharacterLongHistoryIngestionRuns:
    def ingest_character_summaries(self, **kwargs) -> list[str]:
        raise AssertionError(
            "light regression must not materialize character long-history recall"
        )


@pytest.mark.asyncio
async def test_heavy_regression_ingests_character_long_history_from_updated_session(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The hero kept one hand on the lantern while the market froze.",
    )
    story_session_service.commit()

    updated_session = session.model_copy(
        update={
            "current_state_json": {
                **session.current_state_json,
                "character_state_digest": {
                    "hero": {"mood": "alert"},
                    "   ": {"mood": "blank"},
                    "guide": {},
                },
            }
        }
    )

    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=_HeavyRegressionSpecialist(),
        proposal_workflow_service=object(),
        recall_character_long_history_ingestion_service=(
            RecallCharacterLongHistoryIngestionService(retrieval_session)
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
    assert len(assets) == 1
    asset = assets[0]
    assert asset.asset_kind == "character_long_history_summary"
    assert asset.metadata["character_key"] == "hero"
    assert asset.metadata["materialization_kind"] == ("character_long_history_summary")
    assert asset.metadata["accepted_segment_evidence_count"] == 1
    assert asset.metadata["continuity_note_count"] == 1
    assert asset.metadata["includes_chapter_summary"] is True
    assert accepted_segment.artifact_id in asset.metadata["seed_sections"][0]["text"]


@pytest.mark.asyncio
async def test_light_regression_does_not_ingest_character_long_history(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        character_state_digest={"hero": {"mood": "alert"}},
    )
    accepted_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The hero accepted the warning and stayed by the gate.",
    )
    story_session_service.commit()

    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=_LightRegressionSpecialist(),
        proposal_workflow_service=object(),
        recall_character_long_history_ingestion_service=(
            cast(
                RecallCharacterLongHistoryIngestionService,
                _FailIfCharacterLongHistoryIngestionRuns(),
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


def test_ingest_character_summaries_skips_blank_keys_and_empty_snapshots(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The hero watched the oath lantern flicker twice.",
    )
    story_session_service.commit()

    asset_ids = RecallCharacterLongHistoryIngestionService(
        retrieval_session
    ).ingest_character_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        character_state_digest={
            "": {"mood": "blank"},
            "  ": {"mood": "blank"},
            "hero": {},
            "guide": None,
            "watcher": {"stance": "wary"},
        },
        chapter_summary_text="A wary watcher held the stair.",
        continuity_notes=["The watcher has the upper balcony key."],
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    assert len(asset_ids) == 1
    asset = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )[0]
    assert asset.metadata["character_key"] == "watcher"


def test_ingest_character_summaries_reuses_asset_id_and_reindexes(
    retrieval_session,
    monkeypatch,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallCharacterLongHistoryIngestionService(retrieval_session)
    first_asset_ids = service.ingest_character_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        character_state_digest={"hero": {"mood": "alert"}},
        chapter_summary_text="The hero stayed alert at the market gate.",
        continuity_notes=["The harbor bellmaster is now suspicious."],
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

    second_asset_ids = service.ingest_character_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        character_state_digest={"hero": {"mood": "wary"}},
        chapter_summary_text="The hero stayed wary at the market gate.",
        continuity_notes=["The harbor bellmaster is now suspicious."],
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
    assert "wary" in (assets[0].raw_excerpt or "").lower()


@pytest.mark.asyncio
async def test_ingest_character_summaries_searchable_by_materialization_kind_filter(
    retrieval_session,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = StorySessionService(retrieval_session).create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The hero hid the silver oath braid beneath the market stair.",
    )
    retrieval_session.commit()

    asset_ids = RecallCharacterLongHistoryIngestionService(
        retrieval_session
    ).ingest_character_summaries(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        character_state_digest={"hero": {"mood": "alert"}},
        chapter_summary_text="The hero left chapter one on alert.",
        continuity_notes=["The hero now knows the river password."],
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="hero alert river password silver oath braid",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
            filters={
                "materialization_kinds": ["character_long_history_summary"],
            },
        )
    )

    assert result.hits
    assert result.hits[0].metadata["asset_id"] == asset_ids[0]
    assert result.hits[0].metadata["materialization_kind"] == (
        "character_long_history_summary"
    )
    assert result.hits[0].metadata["character_key"] == "hero"
    assert result.hits[0].metadata["materialized_to_recall"] is True


def test_ingest_character_summaries_raises_explicit_failure(
    retrieval_session,
    monkeypatch,
):
    _, session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallCharacterLongHistoryIngestionService(retrieval_session)
    asset_id = service._build_asset_id(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        character_key="hero",
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
            "recall_character_long_history_ingestion_failed:"
            f"{asset_id}:embedding_provider_unavailable"
        ),
    ):
        service.ingest_character_summaries(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            source_workspace_id=session.source_workspace_id,
            character_state_digest={"hero": {"mood": "alert"}},
            chapter_summary_text="The hero stayed alert.",
            continuity_notes=[],
            accepted_segments=[],
        )
