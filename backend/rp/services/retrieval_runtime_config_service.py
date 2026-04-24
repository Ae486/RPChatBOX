"""Resolve story-scoped retrieval runtime model selections."""

from __future__ import annotations

from sqlmodel import select

from models.rp_setup_store import SetupDraftBlockRecord, SetupWorkspaceRecord
from models.rp_story_store import StorySessionRecord
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig


class RetrievalRuntimeConfigService:
    """Resolve retrieval embedding/rerank model choices from setup or active story."""

    def __init__(self, session) -> None:
        self._session = session

    def resolve_story_config(self, *, story_id: str) -> RetrievalRuntimeConfig:
        if not story_id or story_id == "*":
            return RetrievalRuntimeConfig()

        workspace_config = self._setup_workspace_config(story_id=story_id)
        session_config = self._story_session_config(story_id=story_id)
        return workspace_config.overlay(override=session_config)

    def _setup_workspace_config(self, *, story_id: str) -> RetrievalRuntimeConfig:
        workspace = self._session.exec(
            select(SetupWorkspaceRecord).where(SetupWorkspaceRecord.story_id == story_id)
        ).first()
        if workspace is None:
            return RetrievalRuntimeConfig()

        block = self._session.exec(
            select(SetupDraftBlockRecord)
            .where(SetupDraftBlockRecord.workspace_id == workspace.workspace_id)
            .where(SetupDraftBlockRecord.block_type == "story_config")
        ).first()
        if block is None:
            return RetrievalRuntimeConfig()
        return self._config_from_payload(block.payload_json or {})

    def _story_session_config(self, *, story_id: str) -> RetrievalRuntimeConfig | None:
        session = self._session.exec(
            select(StorySessionRecord)
            .where(StorySessionRecord.story_id == story_id)
            .order_by(StorySessionRecord.updated_at.desc())
        ).first()
        if session is None:
            return None
        return self._config_from_payload(session.runtime_story_config_json or {})

    @staticmethod
    def _config_from_payload(payload: dict) -> RetrievalRuntimeConfig:
        return RetrievalRuntimeConfig(
            embedding_model_id=payload.get("retrieval_embedding_model_id"),
            embedding_provider_id=payload.get("retrieval_embedding_provider_id"),
            rerank_model_id=payload.get("retrieval_rerank_model_id"),
            rerank_provider_id=payload.get("retrieval_rerank_provider_id"),
        )
