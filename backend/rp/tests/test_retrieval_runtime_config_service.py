"""Tests for story-scoped retrieval runtime config resolution."""

from __future__ import annotations

from rp.models.setup_drafts import StoryConfigDraft
from rp.models.story_runtime import LongformChapterPhase
from rp.models.setup_workspace import StoryMode
from rp.services.retrieval_runtime_config_service import RetrievalRuntimeConfigService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService


def test_resolve_story_config_reads_setup_story_config(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-runtime-config",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            retrieval_embedding_model_id="embedding-model-setup",
            retrieval_embedding_provider_id="provider-embedding",
            retrieval_rerank_model_id="rerank-model-setup",
            retrieval_rerank_provider_id="provider-rerank",
        ),
    )

    config = RetrievalRuntimeConfigService(retrieval_session).resolve_story_config(
        story_id="story-runtime-config"
    )

    assert config.embedding_model_id == "embedding-model-setup"
    assert config.embedding_provider_id == "provider-embedding"
    assert config.rerank_model_id == "rerank-model-setup"
    assert config.rerank_provider_id == "provider-rerank"


def test_resolve_story_config_prefers_active_story_session_and_falls_back_per_field(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-runtime-config-override",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            retrieval_embedding_model_id="embedding-model-setup",
            retrieval_embedding_provider_id="provider-embedding-setup",
            retrieval_rerank_model_id="rerank-model-setup",
            retrieval_rerank_provider_id="provider-rerank-setup",
        ),
    )
    StorySessionService(retrieval_session).create_session(
        story_id="story-runtime-config-override",
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={
            "retrieval_embedding_model_id": "embedding-model-session",
            "retrieval_embedding_provider_id": "provider-embedding-session",
            "retrieval_rerank_model_id": "rerank-model-session",
        },
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )

    config = RetrievalRuntimeConfigService(retrieval_session).resolve_story_config(
        story_id="story-runtime-config-override"
    )

    assert config.embedding_model_id == "embedding-model-session"
    assert config.embedding_provider_id == "provider-embedding-session"
    assert config.rerank_model_id == "rerank-model-session"
    assert config.rerank_provider_id == "provider-rerank-setup"


def test_resolve_story_config_reflects_runtime_story_config_updates(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-runtime-config-updated-session",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            retrieval_embedding_model_id="embedding-model-setup",
            retrieval_embedding_provider_id="provider-embedding-setup",
            retrieval_rerank_model_id="rerank-model-setup",
            retrieval_rerank_provider_id="provider-rerank-setup",
        ),
    )
    session_service = StorySessionService(retrieval_session)
    story_session = session_service.create_session(
        story_id="story-runtime-config-updated-session",
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    session_service.update_session(
        session_id=story_session.session_id,
        runtime_story_config_patch={
            "retrieval_embedding_model_id": "embedding-model-session-updated",
            "retrieval_embedding_provider_id": "provider-embedding-session-updated",
            "retrieval_rerank_model_id": None,
        },
    )
    session_service.commit()

    config = RetrievalRuntimeConfigService(retrieval_session).resolve_story_config(
        story_id="story-runtime-config-updated-session"
    )

    assert config.embedding_model_id == "embedding-model-session-updated"
    assert config.embedding_provider_id == "provider-embedding-session-updated"
    assert config.rerank_model_id == "rerank-model-setup"
    assert config.rerank_provider_id == "provider-rerank-setup"
