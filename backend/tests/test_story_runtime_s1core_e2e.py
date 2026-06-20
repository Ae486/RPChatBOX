"""Oracle node-5 Tier-B: full intake->writer->artifact->obligations->settle (E2E-1).

Consumer-backed lifecycle proof that the runtime kernel wires together end-to-end
through the real FastAPI surface + a fake LLM. Modeled on the existing chain test
``test_story_turn_chain_runs_outline_segment_and_complete``
(backend/tests/test_rp_story_api.py:1988), reusing its helpers + ``_MockStoryLLMService``.

The existing test asserts the *product* view (phases, artifacts, foreshadow). This
oracle adds the *runtime-kernel* lock the Tier-A unit oracles cannot give at the
service boundary: after a segment is written + accepted through the live HTTP path,
the writer-completion creation-time obligation jobs [WRK-004] must exist for the
session's turns. Introspection uses ``Session(get_engine())`` against the same tmp
DB the ``client`` fixture provisions.

Lives OUTSIDE ``pytest -n auto rp`` (backend/tests/). Characterization: expected to
pass if the kernel already wires obligations through the API path; if it does not,
this fails honestly rather than being weakened.
"""

from __future__ import annotations

from sqlmodel import Session, select

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from services.database import get_engine
from tests.test_rp_story_api import (
    _MockStoryLLMService,
    _create_ready_workspace,
    _model_payload,
    _provider_payload,
)


def test_e2e1_full_turn_chain_creates_writer_completion_obligations(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story.llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    # Intake -> writer: generate + accept the outline, then write a segment.
    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as response:
        assert response.status_code == 200
        "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    outline_artifact = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "chapter_outline"
    )
    accepted_outline = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
            "target_artifact_id": outline_artifact["artifact_id"],
        },
    )
    assert accepted_outline.status_code == 200

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "write_next_segment",
            "model_id": "model-story",
            "user_prompt": "Write the first escape segment.",
        },
    ) as response:
        assert response.status_code == 200
        "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    pending_segment = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "story_segment" and item["status"] == "draft"
    )
    accepted_segment = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_pending_segment",
            "model_id": "model-story",
            "target_artifact_id": pending_segment["artifact_id"],
        },
    )
    assert accepted_segment.status_code == 200

    # API-visible lifecycle progressed (consumer-backed green).
    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    assert (
        snapshot["session"]["current_state_json"]["narrative_progress"][
            "accepted_segments"
        ]
        >= 1
    )

    # Runtime-kernel lock [WRK-004]: writer-completion created creation-time
    # obligation jobs for the session's turns, persisted in the same DB.
    with Session(get_engine()) as db:
        turns = db.exec(
            select(StoryTurnRecord).where(StoryTurnRecord.session_id == session_id)
        ).all()
        assert turns, "no StoryTurnRecord persisted for the session"
        turn_ids = [turn.turn_id for turn in turns]
        jobs = db.exec(
            select(RuntimeWorkflowJobRecord).where(
                RuntimeWorkflowJobRecord.turn_id.in_(turn_ids)
            )
        ).all()
        required_obligations = [
            job for job in jobs if job.required_for_turn_completion
        ]
        assert required_obligations, (
            "WRK-004 e2e: writer-completion must register creation-time obligation "
            "jobs for the segment turn; none were found across the live chain."
        )
