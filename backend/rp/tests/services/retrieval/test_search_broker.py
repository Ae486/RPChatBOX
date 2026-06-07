"""Tests for the SearchBroker private search engine guards."""

from __future__ import annotations

from rp.models.shared.dsl import Domain
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import LongformChapterPhase
from rp.services.retrieval.context import RetrievalBrokerContext
from rp.services.retrieval.search import SearchBroker
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService


def test_runtime_owned_retrieval_uses_snapshot_pinned_policy_not_latest_story_drift(
    retrieval_session,
) -> None:
    session_service = StorySessionService(retrieval_session)
    story_session = session_service.create_session(
        story_id="story-runtime-pinned-retrieval",
        source_workspace_id="workspace-runtime-pinned-retrieval",
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={
            "retrieval_rerank_model_id": "rerank-pinned",
            "retrieval_rerank_provider_id": "provider-pinned",
        },
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.runtime_retrieval_pinned",
    )
    identity = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )
    session_service.update_session(
        session_id=story_session.session_id,
        runtime_story_config_patch={
            "retrieval_rerank_model_id": None,
            "retrieval_rerank_provider_id": None,
        },
    )
    session_service.commit()

    ctx = RetrievalBrokerContext(
        default_story_id=story_session.story_id,
        runtime_identity=identity,
    )
    search = SearchBroker(context=ctx)
    query = search._build_query(
        query_kind="recall",
        text_query="pinned policy",
        scope="story",
        domains=[Domain.CHAPTER],
        top_k=5,
        filters={},
    )
    resolved_query = search._query_with_runtime_search_policy(
        query=query,
        session=retrieval_session,
    )
    retrieval_service = search._build_retrieval_service(
        session=retrieval_session,
        query=resolved_query,
    )
    resolved_config = (
        retrieval_service._retrieval_runtime_config_service.resolve_story_config(
            story_id=story_session.story_id
        )
    )

    assert resolved_query.rerank is True
    assert resolved_query.filters["runtime_identity"]["turn_id"] == identity.turn_id
    assert resolved_config.rerank_model_id == "rerank-pinned"
    assert resolved_config.rerank_provider_id == "provider-pinned"
