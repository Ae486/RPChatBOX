"""Resolve story-scoped retrieval runtime model selections."""

from __future__ import annotations

from sqlmodel import select

from models.rp_setup_store import SetupDraftBlockRecord, SetupWorkspaceRecord
from models.rp_story_store import StorySessionRecord
from rp.models.retrieval_runtime_config import (
    GraphExtractionRetryPolicy,
    RetrievalRuntimeConfig,
)


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
            select(SetupWorkspaceRecord).where(
                SetupWorkspaceRecord.story_id == story_id
            )
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
        field_map = {
            "embedding_model_id": "retrieval_embedding_model_id",
            "embedding_provider_id": "retrieval_embedding_provider_id",
            "rerank_model_id": "retrieval_rerank_model_id",
            "rerank_provider_id": "retrieval_rerank_provider_id",
            "graph_extraction_provider_id": "graph_extraction_provider_id",
            "graph_extraction_model_id": "graph_extraction_model_id",
            "graph_extraction_structured_output_mode": (
                "graph_extraction_structured_output_mode"
            ),
            "graph_extraction_temperature": "graph_extraction_temperature",
            "graph_extraction_max_output_tokens": (
                "graph_extraction_max_output_tokens"
            ),
            "graph_extraction_timeout_ms": "graph_extraction_timeout_ms",
            "graph_extraction_fallback_model_ref": (
                "graph_extraction_fallback_model_ref"
            ),
            "graph_extraction_enabled": "graph_extraction_enabled",
        }
        values = {
            field_name: payload[payload_key]
            for field_name, payload_key in field_map.items()
            if payload_key in payload
        }
        if "graph_extraction_retry_policy" in payload:
            raw_policy = payload.get("graph_extraction_retry_policy")
            if isinstance(raw_policy, dict):
                values["graph_extraction_retry_policy"] = (
                    GraphExtractionRetryPolicy.model_validate(raw_policy)
                )
        return RetrievalRuntimeConfig(**values)
