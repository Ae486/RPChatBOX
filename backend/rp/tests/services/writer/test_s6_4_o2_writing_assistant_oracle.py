"""S6-4 O-2 / O-isolation oracle: writing-assistant generation (REV-027/028).

Offline/deterministic fake-writer oracle for the assistant generation path:
- O-2: generation returns text, records a non-truth candidate, mints NO
  revision+1 artifact / no ACCEPTED / no materialization; failure and cancel
  leave zero mutation; adoption stays with the S6-3 gate.
- O-isolation (REV-027): the writer packet carries the selection text and
  never any prior assistant-chat turn.

The service also has no maintenance-lock dependency by construction (lock
semantics v2): its collaborators are writer execution + candidate layer +
session repository only.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlmodel import select

from models.rp_story_store import StoryArtifactRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writer.writing_worker_contracts import (
    WritingWorkerExecutionRequest,
    WritingWorkerExecutionResult,
)
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.writer.assistant_session_repository import (
    AssistantSessionRepository,
)
from rp.services.writer.rewrite_candidate_service import RewriteCandidateService
from rp.services.writer.writing_assistant_service import (
    WritingAssistantService,
    WritingAssistantServiceError,
)

_PRIOR_TURN_MARKER = "PRIOR-CHAT-TURN-MUST-NOT-LEAK-7f3d"
_SELECTION_TEXT = "Mira paused at the bell tower door."
_GENERATED_TEXT = "Mira hesitated, palm flat against the cold bell tower door."


class _FakeWritingWorkerExecutionService:
    """Deterministic writer double capturing every execution request."""

    def __init__(
        self,
        *,
        output_text: str = _GENERATED_TEXT,
        result_status: str = "completed",
        failure_reason: str | None = None,
        raise_cancelled: bool = False,
    ) -> None:
        self.output_text = output_text
        self.result_status = result_status
        self.failure_reason = failure_reason
        self.raise_cancelled = raise_cancelled
        self.requests: list[WritingWorkerExecutionRequest] = []

    async def execute(
        self, *, request: WritingWorkerExecutionRequest
    ) -> WritingWorkerExecutionResult:
        self.requests.append(request)
        if self.raise_cancelled:
            raise asyncio.CancelledError()
        return WritingWorkerExecutionResult(
            request_id=request.request_id,
            packet_id=request.packet.packet_id,
            turn_id=request.packet.turn_id,
            operation_mode=request.operation_mode,
            output_text=self.output_text,
            output_kind=request.packet.output_kind,
            result_status=self.result_status,
            failure_reason=self.failure_reason,
        )


def test_o2_rewrite_generates_candidate_without_truth_mutation(retrieval_session):
    identity = _identity(turn_id="turn-s64-o2")
    fake_writer = _FakeWritingWorkerExecutionService()
    service = _service(retrieval_session, fake_writer)

    result = asyncio.run(
        service.generate(
            identity=identity,
            chapter_workspace_id="workspace-s64",
            mode="rewrite",
            user_requirements="Make it tenser.",
            selection_text=_SELECTION_TEXT,
            model_id="fake-model",
        )
    )

    assert result.generated_text == _GENERATED_TEXT
    assert result.candidate_ref is not None
    assert result.mode == "rewrite"

    # Candidate recorded as non-truth (REV-028/REV-002).
    candidates = RewriteCandidateService(session=retrieval_session).list_candidates(
        identity=identity
    )
    assert [candidate.candidate_id for candidate in candidates] == [
        result.candidate_ref
    ]
    assert candidates[0].canonical_truth is False
    assert candidates[0].full_output_text == _GENERATED_TEXT
    assert candidates[0].selected_output_ref is None
    assert candidates[0].adopted_output_ref is None
    assert candidates[0].draft_ref == (
        f"assistant_session:{result.assistant_session_id}"
    )

    # No revision+1 artifact, no ACCEPTED, no materialized draft (REV-024).
    _assert_zero_truth_mutation(retrieval_session, identity)

    # Session stores the exchange with a candidate REFERENCE, not a copy.
    record = AssistantSessionRepository(retrieval_session).load_session(
        result.assistant_session_id
    )
    assert record is not None
    assert record.story_id == identity.story_id
    roles = [turn["role"] for turn in record.messages_json]
    assert roles == ["user", "assistant"]
    assert record.messages_json[1]["candidate_ref"] == result.candidate_ref
    # REV-024 use-and-discard: the raw selection is not retained anywhere.
    assert _SELECTION_TEXT not in str(record.messages_json)
    assert _SELECTION_TEXT not in str(candidates[0].metadata_json)


def test_o2_continue_generates_text_without_candidate(retrieval_session):
    identity = _identity(turn_id="turn-s64-cont")
    fake_writer = _FakeWritingWorkerExecutionService()
    service = _service(retrieval_session, fake_writer)

    result = asyncio.run(
        service.generate(
            identity=identity,
            chapter_workspace_id="workspace-s64",
            mode="continue",
            user_requirements="Push the scene forward.",
            model_id="fake-model",
        )
    )

    # Continue mode is generate+store only for now: the candidate layer only
    # accepts operation_mode=="rewrite" (leader-flagged open question).
    assert result.candidate_ref is None
    assert fake_writer.requests[-1].operation_mode == "writing"
    assert (
        RewriteCandidateService(session=retrieval_session).list_candidates(
            identity=identity
        )
        == []
    )
    _assert_zero_truth_mutation(retrieval_session, identity)


def test_o2_rewrite_requires_selection(retrieval_session):
    service = _service(retrieval_session, _FakeWritingWorkerExecutionService())

    with pytest.raises(WritingAssistantServiceError) as exc:
        asyncio.run(
            service.generate(
                identity=_identity(turn_id="turn-s64-nosel"),
                chapter_workspace_id="workspace-s64",
                mode="rewrite",
                user_requirements="Tighter.",
                selection_text="   ",
                model_id="fake-model",
            )
        )
    assert exc.value.code == "assistant_rewrite_requires_selection"


def test_o2_unsupported_mode_rejected(retrieval_session):
    service = _service(retrieval_session, _FakeWritingWorkerExecutionService())

    with pytest.raises(WritingAssistantServiceError) as exc:
        asyncio.run(
            service.generate(
                identity=_identity(turn_id="turn-s64-badmode"),
                chapter_workspace_id="workspace-s64",
                mode="brainstorm",
                model_id="fake-model",
            )
        )
    assert exc.value.code == "assistant_mode_unsupported"


def test_o2_failure_leaves_zero_mutation(retrieval_session):
    identity = _identity(turn_id="turn-s64-fail")
    repo = AssistantSessionRepository(retrieval_session)
    seeded = repo.save_session(
        story_id=identity.story_id,
        title="existing",
        messages=[{"role": "user", "text": "earlier", "created_at": "2026-07-02"}],
    )
    fake_writer = _FakeWritingWorkerExecutionService(
        result_status="failed",
        failure_reason="provider_unavailable",
    )
    service = _service(retrieval_session, fake_writer)

    with pytest.raises(WritingAssistantServiceError) as exc:
        asyncio.run(
            service.generate(
                identity=identity,
                chapter_workspace_id="workspace-s64",
                mode="rewrite",
                selection_text=_SELECTION_TEXT,
                assistant_session_id=seeded.assistant_session_id,
                model_id="fake-model",
            )
        )
    assert exc.value.code == "assistant_generation_failed"

    reloaded = repo.load_session(seeded.assistant_session_id)
    assert reloaded is not None
    assert len(reloaded.messages_json) == 1  # exchange NOT appended
    assert (
        RewriteCandidateService(session=retrieval_session).list_candidates(
            identity=identity
        )
        == []
    )
    _assert_zero_truth_mutation(retrieval_session, identity)


def test_o2_cancel_leaves_zero_mutation(retrieval_session):
    identity = _identity(turn_id="turn-s64-cancel")
    fake_writer = _FakeWritingWorkerExecutionService(raise_cancelled=True)
    service = _service(retrieval_session, fake_writer)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            service.generate(
                identity=identity,
                chapter_workspace_id="workspace-s64",
                mode="rewrite",
                selection_text=_SELECTION_TEXT,
                model_id="fake-model",
            )
        )

    assert AssistantSessionRepository(retrieval_session).list_sessions(
        identity.story_id
    ) == []
    assert (
        RewriteCandidateService(session=retrieval_session).list_candidates(
            identity=identity
        )
        == []
    )
    _assert_zero_truth_mutation(retrieval_session, identity)


def test_o_isolation_prior_chat_never_enters_writer_packet(retrieval_session):
    identity = _identity(turn_id="turn-s64-isolation")
    repo = AssistantSessionRepository(retrieval_session)
    seeded = repo.save_session(
        story_id=identity.story_id,
        title="chat with history",
        messages=[
            {"role": "user", "text": _PRIOR_TURN_MARKER, "created_at": "2026-07-02"},
            {
                "role": "assistant",
                "text": f"echo {_PRIOR_TURN_MARKER}",
                "created_at": "2026-07-02",
            },
        ],
    )
    fake_writer = _FakeWritingWorkerExecutionService()
    service = _service(retrieval_session, fake_writer)

    result = asyncio.run(
        service.generate(
            identity=identity,
            chapter_workspace_id="workspace-s64",
            mode="rewrite",
            user_requirements="Quieter dread.",
            selection_text=_SELECTION_TEXT,
            assistant_session_id=seeded.assistant_session_id,
            model_id="fake-model",
        )
    )

    assert len(fake_writer.requests) == 1
    packet_dump = fake_writer.requests[0].packet.model_dump_json()
    # Selection and instruction go in; chat history never does (REV-027).
    assert _SELECTION_TEXT in packet_dump
    assert "Quieter dread." in packet_dump
    assert _PRIOR_TURN_MARKER not in packet_dump
    assert "rewrite mode" in fake_writer.requests[0].packet.user_instruction

    # The exchange still lands in the session afterwards.
    reloaded = repo.load_session(result.assistant_session_id)
    assert reloaded is not None
    assert len(reloaded.messages_json) == 4


def test_o2_deleting_session_leaves_candidate_untouched(retrieval_session):
    identity = _identity(turn_id="turn-s64-del")
    fake_writer = _FakeWritingWorkerExecutionService()
    service = _service(retrieval_session, fake_writer)
    result = asyncio.run(
        service.generate(
            identity=identity,
            chapter_workspace_id="workspace-s64",
            mode="rewrite",
            selection_text=_SELECTION_TEXT,
            model_id="fake-model",
        )
    )

    assert AssistantSessionRepository(retrieval_session).delete_session(
        result.assistant_session_id
    )
    candidates = RewriteCandidateService(session=retrieval_session).list_candidates(
        identity=identity
    )
    assert [candidate.candidate_id for candidate in candidates] == [
        result.candidate_ref
    ]
    assert candidates[0].canonical_truth is False


def _service(
    session,
    fake_writer: _FakeWritingWorkerExecutionService,
) -> WritingAssistantService:
    return WritingAssistantService(
        session=session,
        writing_worker_execution_service=fake_writer,  # type: ignore[arg-type]
    )


def _assert_zero_truth_mutation(session, identity: MemoryRuntimeIdentity) -> None:
    artifacts = list(session.exec(select(StoryArtifactRecord)).all())
    assert artifacts == []  # no revision+1 DRAFT, hence no ACCEPTED either
    materials = RuntimeWorkspaceMaterialService(session=session).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain="chapter",
    )
    draftlike = [
        material
        for material in materials
        if material.payload.get("payload_kind")
        in {"draft_document", "revision_overlay"}
    ]
    assert draftlike == []  # no materialization / persistent anchors (REV-024)


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-s64"),
        session_id=overrides.get("session_id", "session-s64"),
        branch_head_id=overrides.get("branch_head_id", "branch-s64"),
        turn_id=overrides.get("turn_id", "turn-s64"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-s64",
        ),
    )
