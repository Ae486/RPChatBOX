from __future__ import annotations

from datetime import datetime, timezone

from rp.agent_runtime.contracts import RpAgentTurnResult
from rp.eval.trace_capture import build_setup_trace
from rp.models.setup_agent import SetupAgentTurnRequest


def test_build_setup_trace_emits_cognitive_artifacts_and_attributes():
    request = SetupAgentTurnRequest.model_validate(
        {
            "workspace_id": "workspace-trace-1",
            "model_id": "model-trace-1",
            "provider_id": "provider-trace-1",
            "target_step": "foundation",
            "history": [],
            "user_prompt": "请根据最新修改继续收敛。",
        }
    )
    runtime_result = RpAgentTurnResult(
        status="completed",
        finish_reason="continue_discussion",
        assistant_text="We should reconcile the updated world rules first.",
        structured_payload={
            "repair_route": "continue_discussion",
            "cognitive_state_summary": {
                "current_step": "foundation",
                "invalidated": True,
                "invalidation_reasons": ["user_edit_delta"],
                "ready_for_review": False,
                "remaining_open_issues": ["Need to confirm the revised guild law."],
            },
            "cognitive_state": {
                "workspace_id": "workspace-trace-1",
                "current_step": "foundation",
                "state_version": 1,
                "invalidated": True,
                "invalidation_reasons": ["user_edit_delta"],
                "source_basis": {
                    "workspace_version": 2,
                    "draft_fingerprint": "abc",
                    "pending_user_edit_delta_ids": ["delta-1"],
                    "last_proposal_status": None,
                    "current_step": "foundation",
                },
            },
        },
    )

    trace, artifacts = build_setup_trace(
        trace_id="trace-1",
        run_id="run-1",
        case_id="case-1",
        story_id="story-trace-1",
        request=request,
        runtime_result=runtime_result,
        runtime_events=[],
        workspace_before=None,
        workspace_after=None,
        runtime_debug=None,
        activation_check={
            "ready": False,
            "blocking_issues": ["Step not frozen: foundation"],
            "handoff": None,
        },
        capture_tool_sequence=True,
        stream_mode=False,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )

    root_span = trace.spans[0]
    artifact_kinds = {item.kind for item in artifacts}

    assert root_span.attributes["repair_route"] == "continue_discussion"
    assert root_span.attributes["story_id"] == "story-trace-1"
    assert root_span.attributes["cognitive_state_invalidated"] is True
    assert root_span.attributes["cognitive_ready_for_review"] is False
    assert root_span.attributes["cognitive_remaining_issue_count"] == 1
    assert "cognitive_state_summary" in artifact_kinds
    assert "cognitive_state" in artifact_kinds
    assert "tool_sequence" in artifact_kinds
    assert "activation_check" in artifact_kinds
