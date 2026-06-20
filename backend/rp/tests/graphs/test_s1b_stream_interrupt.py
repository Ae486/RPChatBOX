"""Oracle S1b Tier-A: end-to-end stream-interrupt contract (A1-A7).

Runner-level oracle over ``StoryGraphRunner.run_turn_stream`` for the
restart-interrupt path. It drives the FULL interrupt contract THROUGH the runner:
a writer stream is aborted mid-flight and the runner must shield-finalize the
pinned turn -> FAILED(failure_reason) + required-job -> FAILED + an idempotent
interrupt receipt, WITHOUT persisting any visible output, then re-raise. Grounded
in S1b/02-oracle-design.md rev.2 (ratified) + 03-design.md (§6 / §7 P3 deltas).

TWO injection variants pin the SAME contract through the SAME runner branch (the
impl widens the catch to ``except (asyncio.CancelledError, GeneratorExit)`` per
03-design.md E7 / impact-sweep §2,§9):
- ``test_s1b_stream_interrupt_finalizes_turn_failed_with_receipt`` — task-cancel:
  the fake ``writer_run_stream`` ``raise asyncio.CancelledError`` after 2 deltas;
  the abort escapes the ``async for`` so it is asserted via ``pytest.raises``.
- ``test_s1b_stream_aclose_generatorexit_finalizes_turn_failed`` — consumer
  ``aclose()`` / client-disconnect: the fake yields and stays suspended; driving
  the runner manually to two deltas then ``await agen.aclose()`` throws
  ``GeneratorExit`` at the suspended ``yield chunk`` (story_graph_runner.py:181).
  ``GeneratorExit`` is consumed by the close protocol (no ``pytest.raises``).

Both build the runner directly via the cited harness (mirrors
test_projection_builder_services.py:2854-2867) and seed ONE required
``REQUIRED_POST_WRITE_ANALYSIS`` obligation on the just-pinned turn inside the
fake, then force ``writer_stream_requires_buffered_execution`` -> False so the
streaming branch (runner.py:136-181) is the one driven.

Production surface this oracle pins (ALL absent today -> RED-by-design):
- ``StoryGraphRunner.run_turn_stream`` ``except (asyncio.CancelledError,
  GeneratorExit)`` branch. Today only ``except Exception`` (runner.py:248) exists;
  both abort signals are ``BaseException`` -> today they propagate with NO finalize.
- ``StoryTurnDomainService.finalize_interrupted_turn`` (shielded finalize).
- ``StoryTurnDomainService.list_interrupt_receipts`` (receipt query, dedupe key
  ``turn_id+reason``).
- ``RuntimeWorkflowJobService.mark_required_jobs_failed`` writing the job's
  dedicated ``failure_reason`` field (rp_story_store.py:353).
- the shared ``interrupted_by_restart`` reason-code constant (AUTH-012 closed set).

Per-assertion SoT mapping + RED status (green-by-omission ones LOCK the guarantee;
the design's curve-fit mutations break them). Both tests share one assertion block:
- A1 [TURN-008]          visible_output_ref None              -> green-by-omission today.
- A2 [TURN-008/TURN-011] no accepted story_segment artifact   -> green-by-omission today.
- A3 [AUTH-014/TURN-009/AUTH-012] status==FAILED AND failure_reason=="interrupted_by_restart"
                                                              -> GENUINELY RED today.
- A4 [HAR-006]           abort re-raised AND no success ``done`` emitted
                                                              -> green-by-omission today.
- A5 [AUTH-014]          exactly ONE interrupt receipt         -> GENUINELY RED today.
- A6 [AUTH-014]          seeded required job == FAILED AND its ``failure_reason``
                          == "interrupted_by_restart"          -> GENUINELY RED today
                          (no runner-path job-failure wiring; it stays PENDING).
- A7 [HAR-006]           no success-path refs/bookkeeping       -> green-by-omission today.

No assertion may be weakened to green and no ``xfail`` is used: they serve the S1b
SoT, not today's (pre-S1b) behaviour.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.graphs.story_graph_nodes import StoryGraphNodes
from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.turn_domain_service import StoryTurnDomainService
from rp.tests.services.projection.test_projection_builder_services import (
    _AsyncOrchestratorService,
    _AsyncSpecialistService,
    _build_turn_domain_service,
    _seed_story_runtime,
)


# AUTH-012 closed-set reason code the interrupt finalize must stamp. The impl must
# also expose this as a shared constant; the oracle pins the wire value.
_INTERRUPTED_BY_RESTART = "interrupted_by_restart"

# S1b receipt-query surface, guarded so the file COLLECTS even before S1b lands.
_list_interrupt_receipts = getattr(
    StoryTurnDomainService, "list_interrupt_receipts", None
)

# The pre-abort deltas the fake writer streams (only the first two are ever
# consumed in either variant; types — not content — are what the oracle pins).
_PRE_ABORT_DELTAS = (
    'data: {"type":"text_delta","delta":"Half "}\n\n',
    'data: {"type":"text_delta","delta":"a "}\n\n',
    'data: {"type":"text_delta","delta":"sentence"}\n\n',
)


def _chunk_types(chunks: list[str]) -> list[str | None]:
    """Decode the ``type`` field of every SSE data chunk (spacing-robust)."""

    types: list[str | None] = []
    for chunk in chunks:
        line = chunk.strip()
        if not line.startswith("data: "):
            continue
        body = line[6:]
        if not body or body == "[DONE]":
            continue
        try:
            types.append(json.loads(body).get("type"))
        except json.JSONDecodeError:
            continue
    return types


async def _build_segment_drafting_runner(retrieval_session):
    """Seed + advance to SEGMENT_DRAFTING so WRITE_NEXT_SEGMENT can stream.

    Returns ``(runner, domain_service, service, chapter, session_id)`` with the
    runner already past ACCEPT_OUTLINE — i.e. positioned to stream the next turn.
    """

    session, chapter, service = _seed_story_runtime(retrieval_session)
    service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.OUTLINE_REVIEW,
    )
    service.update_session(
        session_id=session.session_id,
        current_phase=LongformChapterPhase.OUTLINE_REVIEW,
    )
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft Outline",
    )
    service.commit()

    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )
    domain_service = _build_turn_domain_service(
        service,
        orchestrator_service=_AsyncOrchestratorService(),
        specialist_service=_AsyncSpecialistService(),
        runtime_identity_service=identity_service,
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        runtime_workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
    )
    runner = StoryGraphRunner(nodes=StoryGraphNodes(domain_service=domain_service))

    await runner.run_turn(
        LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
            model_id="model",
            target_artifact_id=outline.artifact_id,
        )
    )
    return runner, domain_service, service, chapter, session.session_id


def _make_seeding_fake(retrieval_session, captured: dict[str, str], *, delta_count, raise_cancelled):
    """Build a fake ``writer_run_stream`` that seeds a required obligation.

    The turn is already pinned (pin_runtime_identity ran in the prepared phase),
    so the obligation is attached to it before the abort fires. ``raise_cancelled``
    selects the task-cancel variant (raise after the deltas); the aclose/GeneratorExit
    variant leaves the generator suspended at a yield (``raise_cancelled=False``).
    """

    async def _fake_writer_run_stream(state):
        identity = MemoryRuntimeIdentity.model_validate(
            state.get("runtime_identity") or {}
        )
        captured["turn_id"] = identity.turn_id
        job = RuntimeWorkflowJobService(retrieval_session).ensure_job(
            identity=identity,
            job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
            job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
            creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
            required_for_turn_completion=True,
        )
        captured["job_id"] = job.job_id
        retrieval_session.flush()
        for chunk in _PRE_ABORT_DELTAS[:delta_count]:
            yield chunk
        if raise_cancelled:
            raise asyncio.CancelledError()

    return _fake_writer_run_stream


def _assert_interrupt_finalized_red_targets(
    retrieval_session,
    *,
    service,
    chapter,
    domain_service,
    captured: dict[str, str],
    collected: list[str],
) -> None:
    """Assert the full A1-A7 interrupt contract (shared by both injections)."""

    turn_id = captured["turn_id"]
    retrieval_session.expire_all()
    turn = retrieval_session.get(StoryTurnRecord, turn_id)
    assert turn is not None

    # A1 [TURN-008]: no visible output was bound by the interrupt finalize.
    assert turn.visible_output_ref is None

    # A2 [TURN-008/TURN-011]: no accepted story_segment artifact for the turn (the
    # half-stream text must never reach the workspace/history).
    segment_artifacts = [
        artifact
        for artifact in service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
    ]
    assert segment_artifacts == []

    # A3 [AUTH-014/TURN-009/AUTH-012]: turn FAILED with the exact closed-set reason.
    # A mark-FAILED-without-reason impl (or no-finalize, as today) fails here.
    assert turn.status == StoryTurnStatus.FAILED.value
    assert turn.failure_reason == _INTERRUPTED_BY_RESTART

    # A4 [HAR-006]: no success ``done`` SSE event was emitted (a done-then-reraise
    # impl must fail). Only the two pre-abort deltas are seen.
    assert "done" not in _chunk_types(collected)
    assert _chunk_types(collected) == ["text_delta", "text_delta"]

    # A5 [AUTH-014]: exactly ONE interrupt receipt for the turn (proves the runner
    # actually invoked the shielded finalize through the abort path).
    assert _list_interrupt_receipts is not None, (
        "AUTH-014: StoryTurnDomainService.list_interrupt_receipts is not "
        "implemented. S1b must add an idempotent interrupt receipt writer "
        "(dedupe key turn_id+reason) plus this query, and the runner's "
        "except (asyncio.CancelledError, GeneratorExit) branch must invoke "
        "finalize_interrupted_turn."
    )
    receipts = domain_service.list_interrupt_receipts(turn_id=turn_id)
    assert len(receipts) == 1
    assert receipts[0].reason == _INTERRUPTED_BY_RESTART

    # A6 [AUTH-014]: the seeded required job was FAILED through the runner path
    # (NOT left PENDING, NOT deferred) AND stamped with the dedicated failure_reason
    # (a status-only impl must not false-green). Today it stays PENDING -> RED.
    job = retrieval_session.get(RuntimeWorkflowJobRecord, captured["job_id"])
    assert job is not None
    assert job.status == RuntimeWorkflowJobStatus.FAILED.value
    assert job.failure_reason == _INTERRUPTED_BY_RESTART

    # A7 [HAR-006]: no success-path mutation beyond the receipt + FAILED-status +
    # job-failure (no selected output ref, no settled/completed bookkeeping).
    assert turn.selected_output_ref is None
    assert turn.settlement_reason is None
    assert turn.settled_at is None


@pytest.mark.asyncio
async def test_s1b_stream_interrupt_finalizes_turn_failed_with_receipt(
    retrieval_session,
    monkeypatch,
) -> None:
    runner, domain_service, service, chapter, session_id = (
        await _build_segment_drafting_runner(retrieval_session)
    )

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        runner._nodes,
        "writer_run_stream",
        _make_seeding_fake(
            retrieval_session, captured, delta_count=2, raise_cancelled=True
        ),
    )
    monkeypatch.setattr(
        runner._nodes,
        "writer_stream_requires_buffered_execution",
        lambda state: False,
    )

    collected: list[str] = []
    # A4 (part 1): the CancelledError must propagate out of the runner (re-raised,
    # not swallowed). A swallow-then-return impl makes this pytest.raises fail.
    with pytest.raises(asyncio.CancelledError):
        async for chunk in runner.run_turn_stream(
            LongformTurnRequest(
                session_id=session_id,
                command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
                model_id="model",
                user_prompt="Continue.",
            )
        ):
            collected.append(chunk)

    _assert_interrupt_finalized_red_targets(
        retrieval_session,
        service=service,
        chapter=chapter,
        domain_service=domain_service,
        captured=captured,
        collected=collected,
    )


@pytest.mark.asyncio
async def test_s1b_stream_aclose_generatorexit_finalizes_turn_failed(
    retrieval_session,
    monkeypatch,
) -> None:
    runner, domain_service, service, chapter, session_id = (
        await _build_segment_drafting_runner(retrieval_session)
    )

    captured: dict[str, str] = {}
    # The fake yields three deltas and never raises, so after we consume two it
    # stays suspended at a ``yield`` — the production abort then arrives as a
    # GeneratorExit thrown by ``aclose()`` (consumer disconnect), NOT a raise.
    monkeypatch.setattr(
        runner._nodes,
        "writer_run_stream",
        _make_seeding_fake(
            retrieval_session, captured, delta_count=3, raise_cancelled=False
        ),
    )
    monkeypatch.setattr(
        runner._nodes,
        "writer_stream_requires_buffered_execution",
        lambda state: False,
    )

    agen = runner.run_turn_stream(
        LongformTurnRequest(
            session_id=session_id,
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
            model_id="model",
            user_prompt="Continue.",
        )
    )
    collected: list[str] = []
    collected.append(await agen.__anext__())
    collected.append(await agen.__anext__())

    # A4 (part 1, aclose variant): aclose() throws GeneratorExit at the suspended
    # ``yield chunk`` (story_graph_runner.py:181). The widened
    # ``except (asyncio.CancelledError, GeneratorExit)`` branch must run the
    # shielded finalize then re-raise -> aclose() returns normally (GeneratorExit
    # is consumed by the close protocol; no pytest.raises). Today no finalize runs.
    await agen.aclose()

    _assert_interrupt_finalized_red_targets(
        retrieval_session,
        service=service,
        chapter=chapter,
        domain_service=domain_service,
        captured=captured,
        collected=collected,
    )
