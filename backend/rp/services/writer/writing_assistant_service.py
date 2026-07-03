"""Writing-assistant agent generation service (S6-4 step 1).

One governed generation path shared by assistant modes (rewrite/continue):
compose the per-mode instruction with the user's free-text requirements,
invoke the writer with ONLY [mode instruction + requirements + selection
text] (REV-027 one-way isolation: assistant chat history never enters the
writer packet), record rewrite output as a non-truth candidate (REV-028),
and append the exchange to the story-scoped assistant session.

The generation path never mints a revision+1 artifact, never auto-inserts,
never auto-accepts (adoption stays with the S6-3 accept gate), and carries
no maintenance-lock dependency (lock semantics v2: locks never block user
operations). The framed selection is use-and-discard (REV-024): it enters
the transient writer packet only and is not retained in the rewrite request,
the candidate metadata, or the session messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session

from rp.errors import RPError
from rp.models.core_state.revision_overlay_contracts import RewriteRequest
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.writer.writing_assistant_contracts import (
    WritingAssistantGenerationResult,
)
from rp.models.writer.writing_runtime import PacketSection, WritingPacket
from rp.models.writer.writing_worker_contracts import (
    WritingWorkerExecutionRequest,
    WritingWorkerExecutionResult,
)
from .assistant_session_repository import AssistantSessionRepository
from .rewrite_candidate_service import RewriteCandidateService
from .writing_worker_execution_service import WritingWorkerExecutionService

_ASSISTANT_MODES = ("rewrite", "continue")

_MODE_INSTRUCTIONS: dict[str, str] = {
    "rewrite": (
        "You are the story writing assistant in rewrite mode. Rewrite the "
        "selected text according to the requirements while preserving the "
        "established facts and continuity. Output only the rewritten prose."
    ),
    "continue": (
        "You are the story writing assistant in continue mode. Continue the "
        "story forward from the provided context. Do not alter or restate "
        "prior text. Output only the newly written prose."
    ),
}


class WritingAssistantServiceError(RPError, ValueError):
    """Stable writing-assistant service error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class WritingAssistantService:
    """Generate assistant candidates and persist the conversation exchange."""

    def __init__(
        self,
        *,
        session: Session,
        writing_worker_execution_service: WritingWorkerExecutionService | None = None,
        rewrite_candidate_service: RewriteCandidateService | None = None,
        assistant_session_repository: AssistantSessionRepository | None = None,
    ) -> None:
        self._writing_worker_execution_service = (
            writing_worker_execution_service or WritingWorkerExecutionService()
        )
        self._rewrite_candidate_service = rewrite_candidate_service or (
            RewriteCandidateService(session=session)
        )
        self._assistant_sessions = assistant_session_repository or (
            AssistantSessionRepository(session)
        )

    async def generate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        chapter_workspace_id: str,
        mode: str,
        user_requirements: str = "",
        selection_text: str | None = None,
        assistant_session_id: str | None = None,
        session_title: str | None = None,
        model_id: str,
        provider_id: str | None = None,
    ) -> WritingAssistantGenerationResult:
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode not in _ASSISTANT_MODES:
            raise WritingAssistantServiceError("assistant_mode_unsupported", mode)
        requirements = (user_requirements or "").strip()
        selection = (selection_text or "").strip() or None
        if normalized_mode == "rewrite" and selection is None:
            raise WritingAssistantServiceError(
                "assistant_rewrite_requires_selection",
                identity.turn_id,
            )
        workspace_id = (chapter_workspace_id or "").strip()
        if not workspace_id:
            raise WritingAssistantServiceError(
                "assistant_workspace_required",
                identity.story_id,
            )

        # Resolve the session target up front but WRITE only after a
        # successful generation, so failures leave zero mutation.
        record = None
        if assistant_session_id is not None:
            record = self._assistant_sessions.load_session(assistant_session_id)
            if record is None:
                raise WritingAssistantServiceError(
                    "assistant_session_not_found",
                    assistant_session_id,
                )
            if record.story_id != identity.story_id:
                raise WritingAssistantServiceError(
                    "assistant_session_story_mismatch",
                    record.story_id,
                )
        resolved_session_id = (
            record.assistant_session_id
            if record is not None
            else f"assistant_session_{uuid4().hex[:12]}"
        )
        prior_messages = list(record.messages_json) if record is not None else []

        instruction = _MODE_INSTRUCTIONS[normalized_mode]
        if requirements:
            instruction = f"{instruction}\n\nUser requirements:\n{requirements}"

        packet = self._build_packet(
            identity=identity,
            chapter_workspace_id=workspace_id,
            mode=normalized_mode,
            instruction=instruction,
            selection=selection,
        )
        request = WritingWorkerExecutionRequest(
            request_id=f"assistant-writer:{uuid4().hex}",
            identity=identity,
            operation_mode=packet.operation_mode,
            packet=packet,
            writer_model_id=model_id,
            writer_provider_id=provider_id,
            retrieval_allowed=False,
            max_retrieval_attempts=0,
        )
        result = await self._writing_worker_execution_service.execute(request=request)
        if result.result_status != "completed" or not result.output_text.strip():
            raise WritingAssistantServiceError(
                "assistant_generation_failed",
                result.failure_reason or result.result_status,
            )

        candidate_ref: str | None = None
        if normalized_mode == "rewrite":
            candidate_ref = self._record_rewrite_candidate(
                identity=identity,
                assistant_session_id=resolved_session_id,
                instruction=instruction,
                writer_result=result,
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        user_turn = {
            "role": "user",
            "mode": normalized_mode,
            "text": requirements,
            "created_at": now_iso,
        }
        assistant_turn: dict[str, object] = {
            "role": "assistant",
            "mode": normalized_mode,
            "text": result.output_text,
            "created_at": now_iso,
        }
        if candidate_ref is not None:
            assistant_turn["candidate_ref"] = candidate_ref
        saved = self._assistant_sessions.save_session(
            assistant_session_id=resolved_session_id,
            story_id=identity.story_id,
            title=session_title if record is None else None,
            messages=[*prior_messages, user_turn, assistant_turn],
        )
        return WritingAssistantGenerationResult(
            assistant_session_id=saved.assistant_session_id,
            mode=normalized_mode,
            generated_text=result.output_text,
            candidate_ref=candidate_ref,
            request_id=result.request_id,
            packet_id=result.packet_id,
        )

    def _build_packet(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        chapter_workspace_id: str,
        mode: str,
        instruction: str,
        selection: str | None,
    ) -> WritingPacket:
        # REV-027: only the mode instruction, requirements, and selection go
        # in; assistant chat history must never reach the writer.
        mode_sidecar_sections = []
        if selection is not None:
            mode_sidecar_sections.append(
                PacketSection(
                    section_id=f"assistant-selection:{uuid4().hex[:12]}",
                    label="assistant_selection",
                    source_kind="assistant_selection",
                    items=[selection],
                )
            )
        return WritingPacket(
            packet_id=f"assistant-packet:{uuid4().hex}",
            identity=identity,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            turn_id=identity.turn_id,
            chapter_workspace_id=chapter_workspace_id,
            output_kind="story_segment",
            phase="writing_assistant",
            operation_mode="rewrite" if mode == "rewrite" else "writing",
            mode_sidecar_sections=mode_sidecar_sections,
            user_instruction=instruction,
        )

    def _record_rewrite_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        assistant_session_id: str,
        instruction: str,
        writer_result: WritingWorkerExecutionResult,
    ) -> str:
        # No materialized draft exists on the assistant path; draft_ref points
        # back at the assistant session for traceability and the document id
        # is a transient selection marker (REV-024: no persistent anchors).
        rewrite_request = RewriteRequest(
            request_id=f"assistant_rewrite_{uuid4().hex[:12]}",
            session_id=identity.session_id,
            turn_id=identity.turn_id,
            draft_ref=f"assistant_session:{assistant_session_id}",
            draft_document_id=f"assistant_selection:{uuid4().hex[:12]}",
            rewrite_scope="full",
            global_instruction=instruction,
            metadata_json={
                "story_id": identity.story_id,
                "session_id": identity.session_id,
                "branch_head_id": identity.branch_head_id,
                "turn_id": identity.turn_id,
                "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
            },
        )
        candidate = self._rewrite_candidate_service.create_full_rewrite_candidate(
            identity=identity,
            rewrite_request=rewrite_request,
            writer_result=writer_result,
        )
        return candidate.candidate_id
