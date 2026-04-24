"""LLM-guided orchestrator for longform MVP dispatch."""

from __future__ import annotations

import json

from models.chat import ChatMessage
from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    OrchestratorPlan,
    StoryArtifactKind,
    StorySession,
)
from .authoritative_state_view_service import AuthoritativeStateViewService
from .projection_state_service import ProjectionStateService
from .story_llm_gateway import StoryLlmGateway


class LongformOrchestratorService:
    """Produce one minimal worker plan per story turn."""

    def __init__(
        self,
        *,
        llm_gateway: StoryLlmGateway | None = None,
        authoritative_state_view_service: AuthoritativeStateViewService,
        projection_state_service: ProjectionStateService,
    ) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()
        self._authoritative_state_view_service = authoritative_state_view_service
        self._projection_state_service = projection_state_service

    async def plan(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        target_artifact_id: str | None,
    ) -> OrchestratorPlan:
        projection_snapshot = self._projection_state_service.build_planner_projection(
            session_id=session.session_id
        )
        authoritative_state = self._authoritative_state_view_service.get_state_map(
            session_id=session.session_id
        )
        fallback = self._fallback_plan(
            session=session,
            chapter=chapter,
            command_kind=command_kind,
            user_prompt=user_prompt,
            projection_snapshot=projection_snapshot,
        )
        if command_kind in {
            LongformTurnCommandKind.ACCEPT_OUTLINE,
            LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            LongformTurnCommandKind.COMPLETE_CHAPTER,
        }:
            return fallback

        system_prompt = (
            "You are the longform_orchestrator for an active-story MVP. "
            "Return JSON only. Decide one minimal plan for the current command. "
            "You may request archival/recall retrieval, choose output_kind, and "
            "write a concise writer_instruction. Do not generate user-visible prose."
        )
        user_payload = {
            "session_id": session.session_id,
            "story_id": session.story_id,
            "phase": chapter.phase.value,
            "command_kind": command_kind.value,
            "chapter_index": chapter.chapter_index,
            "chapter_goal": chapter.chapter_goal,
            "accepted_outline": chapter.accepted_outline_json,
            "projection_state": projection_snapshot,
            "authoritative_state": authoritative_state,
            "user_prompt": user_prompt,
            "target_artifact_id": target_artifact_id,
            "response_schema": {
                "output_kind": "chapter_outline|discussion_message|story_segment",
                "needs_retrieval": "bool",
                "archival_queries": ["..."],
                "recall_queries": ["..."],
                "specialist_focus": ["..."],
                "writer_instruction": "...",
                "notes": ["..."],
            },
        }

        try:
            raw = await self._llm_gateway.complete_text(
                model_id=model_id,
                provider_id=provider_id,
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
                ],
                temperature=0.2,
                max_tokens=600,
            )
            return OrchestratorPlan.model_validate(
                self._llm_gateway.extract_json_object(raw)
            )
        except Exception:
            return fallback

    def _fallback_plan(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        command_kind: LongformTurnCommandKind,
        user_prompt: str | None,
        projection_snapshot: dict[str, object],
    ) -> OrchestratorPlan:
        if command_kind == LongformTurnCommandKind.GENERATE_OUTLINE:
            return OrchestratorPlan(
                output_kind=StoryArtifactKind.CHAPTER_OUTLINE,
                needs_retrieval=True,
                archival_queries=[
                    query
                    for query in (
                        chapter.chapter_goal,
                        " ".join(projection_snapshot.get("blueprint_digest", [])[:2]),
                    )
                    if query
                ],
                specialist_focus=["chapter intent", "blueprint beats", "outline coverage"],
                writer_instruction=(
                    user_prompt
                    or "Draft a chapter outline that matches the blueprint and chapter goal."
                ),
                notes=["fallback_plan"],
            )
        if command_kind == LongformTurnCommandKind.DISCUSS_OUTLINE:
            return OrchestratorPlan(
                output_kind=StoryArtifactKind.DISCUSSION_MESSAGE,
                needs_retrieval=False,
                specialist_focus=["outline discussion", "chapter intent"],
                writer_instruction=(
                    user_prompt
                    or "Respond as a planning assistant about the current outline."
                ),
                notes=["fallback_plan"],
            )
        if command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT:
            return OrchestratorPlan(
                output_kind=StoryArtifactKind.STORY_SEGMENT,
                needs_retrieval=False,
                specialist_focus=["rewrite pending segment", "continuity guardrails"],
                writer_instruction=(
                    user_prompt
                    or "Rewrite the pending segment while preserving chapter continuity."
                ),
                notes=["fallback_plan"],
            )
        return OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            needs_retrieval=True,
            archival_queries=[
                query
                for query in (
                    chapter.chapter_goal,
                    " ".join(projection_snapshot.get("current_outline_digest", [])[:2]),
                    " ".join(projection_snapshot.get("current_state_digest", [])[:2]),
                )
                if query
            ],
            recall_queries=[
                f"chapter {max(1, chapter.chapter_index - 1)} summary"
                if chapter.chapter_index > 1
                else ""
            ],
            specialist_focus=["segment continuity", "current outline", "story momentum"],
            writer_instruction=(
                user_prompt
                or "Write the next longform story segment for the current chapter."
            ),
            notes=["fallback_plan", f"mode={session.mode}"],
        )
