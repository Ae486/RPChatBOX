"""Node adapters for the phase-1 StoryGraph shell."""
from __future__ import annotations

from typing import AsyncIterator

from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
)
from rp.models.writing_runtime import WritingPacket
from rp.services.story_command_policy import validate_story_command
from rp.services.story_turn_domain_service import StoryTurnDomainService

from .story_graph_state import StoryGraphState


class StoryGraphNodes:
    """Wrap current story domain service as coarse LangGraph nodes."""

    _SPECIAL_COMMANDS = {
        LongformTurnCommandKind.ACCEPT_OUTLINE,
        LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        LongformTurnCommandKind.COMPLETE_CHAPTER,
    }

    def __init__(self, *, domain_service: StoryTurnDomainService) -> None:
        self._domain_service = domain_service

    def load_session_and_chapter(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            chapter = self._domain_service.require_current_chapter(state["session_id"])
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_session_not_found",
                },
                "status": "failed",
            }
        return {
            "chapter_workspace_id": chapter.chapter_workspace_id,
            "chapter_phase": chapter.phase.value,
            "current_chapter_index": chapter.chapter_index,
            "status": "session_loaded",
        }

    def validate_command(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            chapter = self._domain_service.require_current_chapter(state["session_id"])
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_chapter_not_found",
                },
                "status": "failed",
            }
        try:
            validate_story_command(
                phase=chapter.phase,
                command_kind=LongformTurnCommandKind(state["command_kind"]),
            )
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_command_not_allowed",
                },
                "status": "failed",
            }
        return {"status": "command_validated"}

    def prepare_generation_inputs(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {"status": "special_command_prepared"}
        payload = self._domain_service.prepare_generation_inputs(
            session_id=state["session_id"],
            user_prompt=state.get("user_prompt"),
            target_artifact_id=state.get("target_artifact_id"),
        )
        return {**payload, "status": "generation_inputs_prepared"}

    async def orchestrator_plan(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        plan = await self._domain_service.orchestrator_plan(
            session_id=state["session_id"],
            command_kind=command_kind,
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
            user_prompt=state.get("user_prompt"),
            target_artifact_id=state.get("target_artifact_id"),
        )
        return {"plan": plan.model_dump(mode="json"), "status": "plan_ready"}

    async def specialist_analyze(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        bundle = await self._domain_service.specialist_analyze(
            session_id=state["session_id"],
            command_kind=command_kind,
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
            user_prompt=state.get("user_prompt"),
            plan=OrchestratorPlan.model_validate(state.get("plan") or {}),
            pending_artifact_id=state.get("pending_artifact_id"),
            accepted_segment_ids=list(state.get("accepted_segment_ids") or []),
        )
        return {
            "specialist_bundle": bundle.model_dump(mode="json"),
            "warnings": list(bundle.validation_findings),
            "status": "specialist_ready",
        }

    def build_packet(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        packet = self._domain_service.build_packet(
            session_id=state["session_id"],
            plan=OrchestratorPlan.model_validate(state.get("plan") or {}),
            specialist_bundle=SpecialistResultBundle.model_validate(
                state.get("specialist_bundle") or {}
            ),
        )
        return {"writing_packet": packet.model_dump(mode="json"), "status": "packet_ready"}

    async def writer_run(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        text = await self._domain_service.writer_run(
            packet=WritingPacket.model_validate(state.get("writing_packet") or {}),
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
        )
        return {"assistant_text": text, "status": "writer_completed"}

    async def writer_run_stream(self, state: StoryGraphState) -> AsyncIterator[str]:
        packet = WritingPacket.model_validate(state.get("writing_packet") or {})
        async for line in self._domain_service.writer_run_stream(
            packet=packet,
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
        ):
            yield line

    def persist_generated_artifact(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        response = self._domain_service.persist_generated_artifact(
            request=self._request_from_state(state),
            packet=WritingPacket.model_validate(state.get("writing_packet") or {}),
            plan=OrchestratorPlan.model_validate(state.get("plan") or {}),
            text=str(state.get("assistant_text") or ""),
            specialist_bundle=SpecialistResultBundle.model_validate(
                state.get("specialist_bundle") or {}
            ),
            pending_artifact_id=state.get("pending_artifact_id"),
        )
        return {
            "artifact_id": response.artifact_id,
            "artifact_kind": response.artifact_kind.value if response.artifact_kind else None,
            "chapter_workspace_id": response.chapter_workspace_id,
            "chapter_phase": response.current_phase.value,
            "current_chapter_index": response.current_chapter_index,
            "response_payload": response.model_dump(mode="json", exclude_none=True),
            "status": "artifact_persisted",
        }

    async def post_write_regression(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        return {"status": "post_write_regression_skipped"}

    def accept_outline(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            response = self._domain_service.accept_outline(
                request=self._request_from_state(state)
            )
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_turn_failed",
                },
                "status": "failed",
            }
        return {
            "assistant_text": response.assistant_text or "",
            "artifact_id": response.artifact_id,
            "artifact_kind": response.artifact_kind.value if response.artifact_kind else None,
            "chapter_workspace_id": response.chapter_workspace_id,
            "chapter_phase": response.current_phase.value,
            "current_chapter_index": response.current_chapter_index,
            "response_payload": response.model_dump(mode="json", exclude_none=True),
            "status": "completed",
        }

    async def accept_pending_segment(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            response = await self._domain_service.accept_pending_segment(
                request=self._request_from_state(state)
            )
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_turn_failed",
                },
                "status": "failed",
            }
        return {
            "assistant_text": response.assistant_text or "",
            "artifact_id": response.artifact_id,
            "artifact_kind": response.artifact_kind.value if response.artifact_kind else None,
            "chapter_workspace_id": response.chapter_workspace_id,
            "chapter_phase": response.current_phase.value,
            "current_chapter_index": response.current_chapter_index,
            "response_payload": response.model_dump(mode="json", exclude_none=True),
            "status": "completed",
        }

    async def complete_chapter(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            response = await self._domain_service.complete_chapter(
                request=self._request_from_state(state)
            )
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_turn_failed",
                },
                "status": "failed",
            }
        return {
            "assistant_text": response.assistant_text or "",
            "chapter_workspace_id": response.chapter_workspace_id,
            "chapter_phase": LongformChapterPhase.OUTLINE_DRAFTING.value,
            "current_chapter_index": response.current_chapter_index,
            "response_payload": response.model_dump(mode="json", exclude_none=True),
            "status": "completed",
        }

    def finalize_turn(self, state: StoryGraphState) -> StoryGraphState:
        return {}

    @staticmethod
    def _request_from_state(state: StoryGraphState) -> LongformTurnRequest:
        return LongformTurnRequest(
            session_id=state["session_id"],
            command_kind=LongformTurnCommandKind(state["command_kind"]),
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
            user_prompt=state.get("user_prompt"),
            target_artifact_id=state.get("target_artifact_id"),
        )

    @staticmethod
    def extract_text_delta(line: str) -> str:
        return StoryTurnDomainService.extract_text_delta(line)
