"""Node adapters for the phase-1 StoryGraph shell."""

from __future__ import annotations

from typing import AsyncIterator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
)
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
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

    def resolve_graph_thread_binding(self, *, session_id: str) -> dict[str, str]:
        return self._domain_service.resolve_graph_thread_binding(
            session_id=session_id
        )

    def pin_runtime_identity(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        try:
            identity = self._domain_service.resolve_runtime_entry_identity(
                session_id=state["session_id"],
                command_kind=LongformTurnCommandKind(state["command_kind"]),
                requested_branch_head_id=(
                    str(state.get("branch_head_id") or "").strip() or None
                ),
            )
        except ValueError as exc:
            return {
                "error": {
                    "message": str(exc),
                    "type": "story_turn_identity_failed",
                },
                "status": "failed",
            }
        if identity is None:
            return {"status": "runtime_identity_skipped"}
        return {
            "runtime_identity": identity.model_dump(mode="json"),
            "branch_head_id": identity.branch_head_id,
            "turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
            "status": "runtime_identity_pinned",
        }

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
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if (
            state.get("story_segment_metadata_patch") is not None
            and command_kind != LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT
        ):
            return {
                "error": {
                    "message": (
                        "story_segment_metadata_patch is only allowed on "
                        "accept_pending_segment"
                    ),
                    "type": "story_turn_failed",
                },
                "status": "failed",
            }
        try:
            validate_story_command(
                phase=chapter.phase,
                command_kind=command_kind,
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
        pending_artifact_id = payload.get("pending_artifact_id")
        accepted_segment_ids = payload.get("accepted_segment_ids")
        return {
            "pending_artifact_id": (
                pending_artifact_id if isinstance(pending_artifact_id, str) else None
            ),
            "accepted_segment_ids": (
                [item for item in accepted_segment_ids if isinstance(item, str)]
                if isinstance(accepted_segment_ids, list)
                else []
            ),
            "status": "generation_inputs_prepared",
        }

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
            runtime_identity=self._runtime_identity_from_state(state),
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
            command_kind=LongformTurnCommandKind(state["command_kind"]),
            runtime_identity=self._runtime_identity_from_state(state),
        )
        return {
            "writing_packet": packet.model_dump(mode="json"),
            "status": "packet_ready",
        }

    async def writer_run(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        result = await self._domain_service.writer_run(
            packet=WritingPacket.model_validate(state.get("writing_packet") or {}),
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
        )
        return {
            "assistant_text": result.output_text,
            "writing_result": result.model_dump(mode="json", exclude_none=True),
            "status": "writer_completed",
        }

    async def writer_run_stream(self, state: StoryGraphState) -> AsyncIterator[str]:
        packet = WritingPacket.model_validate(state.get("writing_packet") or {})
        async for line in self._domain_service.writer_run_stream(
            packet=packet,
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
        ):
            yield line

    def writer_stream_requires_buffered_execution(
        self,
        state: StoryGraphState,
    ) -> bool:
        packet = WritingPacket.model_validate(state.get("writing_packet") or {})
        return self._domain_service.writer_stream_requires_buffered_execution(
            packet=packet,
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
        )

    def build_stream_writing_result(
        self,
        state: StoryGraphState,
        *,
        assistant_text: str,
        usage_metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        packet = WritingPacket.model_validate(state.get("writing_packet") or {})
        result = self._domain_service.build_stream_writing_result(
            packet=packet,
            text=assistant_text,
            usage_metadata=usage_metadata,
        )
        return result.model_dump(mode="json", exclude_none=True)

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
            writing_result=(
                None
                if not isinstance(state.get("writing_result"), dict)
                or not state.get("writing_result")
                else WritingWorkerExecutionResult.model_validate(
                    state.get("writing_result") or {}
                )
            ),
            specialist_bundle=SpecialistResultBundle.model_validate(
                state.get("specialist_bundle") or {}
            ),
            pending_artifact_id=state.get("pending_artifact_id"),
        )
        return {
            "artifact_id": response.artifact_id,
            "artifact_kind": response.artifact_kind.value
            if response.artifact_kind
            else None,
            "chapter_workspace_id": response.chapter_workspace_id,
            "chapter_phase": response.current_phase.value,
            "current_chapter_index": response.current_chapter_index,
            "writing_result": (
                response.writing_result.model_dump(mode="json", exclude_none=True)
                if response.writing_result is not None
                else {}
            ),
            "response_payload": response.model_dump(mode="json", exclude_none=True),
            "status": "artifact_persisted",
        }

    async def post_write_regression(self, state: StoryGraphState) -> StoryGraphState:
        if state.get("error"):
            return {}
        command_kind = LongformTurnCommandKind(state["command_kind"])
        if command_kind in self._SPECIAL_COMMANDS:
            return {}
        trigger_result = await self._domain_service.trigger_post_write(
            runtime_identity=self._runtime_identity_from_state(state),
            model_id=state.get("model_id"),
            provider_id=state.get("provider_id"),
            user_prompt=state.get("user_prompt"),
            orchestrator_plan=OrchestratorPlan.model_validate(state.get("plan") or {}),
        )
        return {
            "post_write_trigger": trigger_result,
            "status": "post_write_triggered",
        }

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
            "artifact_kind": response.artifact_kind.value
            if response.artifact_kind
            else None,
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
                request=self._request_from_state(state),
                runtime_identity=self._runtime_identity_from_state(state),
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
            "artifact_kind": response.artifact_kind.value
            if response.artifact_kind
            else None,
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
                request=self._request_from_state(state),
                runtime_identity=self._runtime_identity_from_state(state),
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
        failed = bool(state.get("error")) or state.get("status") == "failed"
        self._domain_service.finalize_runtime_turn(
            turn_id=state.get("turn_id"),
            failed=failed,
        )
        return {"status": "failed" if failed else "completed"}

    def record_graph_checkpoint_binding(
        self,
        *,
        turn_id: str | None,
        checkpoint_id: str | None,
        parent_checkpoint_id: str | None = None,
        captured_after_node: str = "finalize_turn",
        checkpoint_ns: str = "rp_story",
    ) -> dict:
        return self._domain_service.record_graph_checkpoint_binding(
            turn_id=turn_id,
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            captured_after_node=captured_after_node,
            checkpoint_ns=checkpoint_ns,
        )

    @staticmethod
    def _request_from_state(state: StoryGraphState) -> LongformTurnRequest:
        return LongformTurnRequest(
            session_id=state["session_id"],
            command_kind=LongformTurnCommandKind(state["command_kind"]),
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
            user_prompt=state.get("user_prompt"),
            target_artifact_id=state.get("target_artifact_id"),
            story_segment_metadata_patch=state.get("story_segment_metadata_patch"),
        )

    @staticmethod
    def extract_text_delta(line: str) -> str:
        return StoryTurnDomainService.extract_text_delta(line)

    @staticmethod
    def _runtime_identity_from_state(
        state: StoryGraphState,
    ) -> MemoryRuntimeIdentity | None:
        payload = state.get("runtime_identity")
        if not isinstance(payload, dict):
            return None
        try:
            return MemoryRuntimeIdentity.model_validate(payload)
        except ValueError:
            return None
