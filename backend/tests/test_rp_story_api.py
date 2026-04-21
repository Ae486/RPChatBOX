"""Integration tests for active-story longform MVP APIs."""

from __future__ import annotations

import json


def _provider_payload(provider_id: str = "provider-story"):
    return {
        "id": provider_id,
        "name": "OpenAI",
        "type": "openai",
        "api_key": "sk-test-12345678",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }


def _model_payload(model_id: str = "model-story"):
    return {
        "id": model_id,
        "provider_id": "provider-story",
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "capabilities": ["text", "tool"],
        "default_params": {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "stream_output": True,
        },
        "is_enabled": True,
        "description": "story test model",
    }


class _MockStoryLLMService:
    async def chat_completion(self, request):
        system_prompt = request.messages[0].content or ""
        user_payload = request.messages[1].content or ""

        if "longform_orchestrator" in system_prompt:
            payload = json.loads(user_payload)
            command_kind = payload["command_kind"]
            if command_kind == "generate_outline":
                content = {
                    "output_kind": "chapter_outline",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["outline beats", "chapter intent"],
                    "writer_instruction": "Draft the opening chapter outline.",
                    "notes": ["mock_orchestrator"],
                }
            elif command_kind == "write_next_segment":
                content = {
                    "output_kind": "story_segment",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["segment continuity", "tension"],
                    "writer_instruction": "Write the next story segment.",
                    "notes": ["mock_orchestrator"],
                }
            else:
                content = {
                    "output_kind": "discussion_message",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["discussion"],
                    "writer_instruction": "Reply to the discussion prompt.",
                    "notes": ["mock_orchestrator"],
                }
            return {
                "choices": [{"message": {"role": "assistant", "content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        if "longform_specialist" in system_prompt:
            payload = json.loads(user_payload)
            command_kind = payload["command_kind"]
            state_patch = {}
            recall_summary = None
            if command_kind == "accept_pending_segment":
                state_patch = {
                    "narrative_progress": {
                        "accepted_segments": 1,
                        "chapter_summary": "The courier secures the ledger and escapes the archive.",
                    }
                }
            elif command_kind == "complete_chapter":
                state_patch = {
                    "chapter_digest": {
                        "current_chapter": 1,
                        "last_accepted_excerpt": "The courier secures the ledger and escapes the archive.",
                    },
                    "narrative_progress": {
                        "accepted_segments": 1,
                        "chapter_summary": "The courier secures the ledger and escapes the archive.",
                    },
                }
                recall_summary = "Chapter 1: the courier steals the ledger and survives the archive pursuit."
            content = {
                "foundation_digest": ["Rivergate forbids open ritual fire."],
                "blueprint_digest": ["Chapter one reveals the ledger and forces an escape."],
                "current_outline_digest": ["Open at the archive; end with a narrow escape."],
                "recent_segment_digest": ["The courier slips into the archive vault."],
                "current_state_digest": ["chapter=1", "phase=segment_drafting"],
                "writer_hints": ["Keep tension immediate.", "Stay concrete and lean."],
                "validation_findings": [],
                "state_patch_proposals": state_patch,
                "summary_updates": ["mock specialist digest"],
                "recall_summary_text": recall_summary,
            }
            return {
                "choices": [{"message": {"role": "assistant", "content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        content = "Writer fallback output."
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def chat_completion_stream(self, request):
        user_prompt = request.messages[1].content or ""
        if "output_kind: chapter_outline" in user_prompt:
            text = "Chapter Outline: The courier infiltrates the archive, finds the ledger, and flees before sunrise."
        elif "output_kind: story_segment" in user_prompt:
            text = "The courier eased the ledger free, heard the ward-chimes flare, and ran before the archive doors sealed shut."
        else:
            text = "The outline should lean harder on the ledger's cost."
        yield f'data: {json.dumps({"type": "text_delta", "delta": text})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'


class _RecoverableStoryLLMService(_MockStoryLLMService):
    def __init__(self):
        super().__init__()
        self._stream_calls = 0

    async def chat_completion_stream(self, request):
        self._stream_calls += 1
        if self._stream_calls == 1:
            yield f'data: {json.dumps({"type": "error", "error": {"message": "writer stream timeout", "type": "timeout"}})}\n\n'
            yield f'data: {json.dumps({"type": "done"})}\n\n'
            return
        async for chunk in super().chat_completion_stream(request):
            yield chunk


def _create_ready_workspace(client) -> str:
    workspace = client.post(
        "/api/rp/setup/workspaces",
        json={"story_id": "story_active_mvp", "mode": "longform"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["workspace_id"]

    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/story-config",
        json={
            "model_profile_ref": "model.default",
            "worker_profile_ref": "worker.longform",
            "post_write_policy_preset": "balanced",
            "notes": "Longform active story test",
        },
    ).status_code == 200
    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/writing-contract",
        json={
            "pov_rules": ["third_person_limited"],
            "style_rules": ["restrained", "lean"],
            "writing_constraints": ["avoid exposition dumps"],
            "task_writing_rules": ["keep scene motion visible"],
        },
    ).status_code == 200
    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/longform-blueprint",
        json={
            "premise": "A courier discovers the archive ledger is a prison key registry.",
            "central_conflict": "The courier must escape with proof before dawn.",
            "chapter_blueprints": [
                {
                    "chapter_id": "ch1",
                    "title": "The Ledger",
                    "purpose": "Discover the registry and escape alive.",
                    "major_beats": ["Infiltration", "Discovery", "Escape"],
                    "setup_payoff_targets": ["prison key registry"],
                }
            ],
        },
    ).status_code == 200
    assert client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/foundation/entries",
        json={
            "entry_id": "world_rule_fire",
            "domain": "world",
            "path": "law.fire_rituals",
            "title": "Fire Ritual Ban",
            "tags": ["law"],
            "source_refs": [],
            "content": {"summary": "Rivergate forbids open ritual fire inside the archive district."},
        },
    ).status_code == 200

    for step_id in ("story_config", "writing_contract", "foundation", "longform_blueprint"):
        proposal = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals",
            json={
                "step_id": step_id,
                "target_draft_refs": [f"draft:{step_id}"],
                "reason": f"freeze {step_id}",
            },
        )
        assert proposal.status_code == 200
        proposal_id = proposal.json()["updated_refs"][0].split("proposal:", 1)[1]
        accepted = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals/{proposal_id}/accept"
        )
        assert accepted.status_code == 200

    activation_check = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activation-check"
    )
    assert activation_check.status_code == 200
    assert activation_check.json()["ready"] is True
    return workspace_id


def test_story_activation_bootstraps_session(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )

    activation = client.post(f"/api/rp/setup/workspaces/{workspace_id}/activate")
    assert activation.status_code == 200
    payload = activation.json()
    assert payload["current_phase"] == "outline_drafting"

    session_id = payload["session_id"]
    session_snapshot = client.get(f"/api/rp/story-sessions/{session_id}")
    assert session_snapshot.status_code == 200
    snapshot = session_snapshot.json()
    assert snapshot["session"]["story_id"] == "story_active_mvp"
    assert snapshot["chapter"]["chapter_index"] == 1
    assert snapshot["chapter"]["phase"] == "outline_drafting"


def test_story_turn_chain_runs_outline_segment_and_complete(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

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
        body = "".join(response.iter_text())
    assert "Chapter Outline" in body

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    outline_artifact = next(
        item for item in snapshot["artifacts"] if item["artifact_kind"] == "chapter_outline"
    )
    assert snapshot["chapter"]["phase"] == "outline_review"

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
    assert accepted_outline.json()["current_phase"] == "segment_drafting"

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
        body = "".join(response.iter_text())
    assert "ward-chimes flare" in body

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    pending_segment = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "story_segment" and item["status"] == "draft"
    )
    assert snapshot["chapter"]["phase"] == "segment_review"

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

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    assert snapshot["chapter"]["phase"] == "segment_drafting"
    assert snapshot["session"]["current_state_json"]["narrative_progress"]["accepted_segments"] >= 1

    completed = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "complete_chapter",
            "model_id": "model-story",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["current_chapter_index"] == 2
    assert completed.json()["current_phase"] == "outline_drafting"

    chapter_two = client.get(f"/api/rp/story-sessions/{session_id}/chapters/2")
    assert chapter_two.status_code == 200
    assert chapter_two.json()["chapter"]["phase"] == "outline_drafting"


def test_story_runtime_debug_exposes_checkpoint_state(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as stream_response:
        assert stream_response.status_code == 200
        _ = "".join(stream_response.iter_text())

    debug_response = client.get(
        f"/api/rp/story-sessions/{session_id}/runtime/debug"
    )
    assert debug_response.status_code == 200
    payload = debug_response.json()
    assert payload["namespace"] == "rp_story"
    assert payload["latest_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["status"] in {
        "writer_completed",
        "completed",
        "artifact_persisted",
    }
    assert payload["latest_meaningful_checkpoint"]["state"]
    assert payload["history"]
    assert any(
        item["status"] in {"writer_completed", "completed", "artifact_persisted"}
        for item in payload["history"]
    )
    assert payload["history"]


def test_story_turn_rejects_command_not_allowed_for_phase(client):
    workspace_id = _create_ready_workspace(client)
    activation = client.post(f"/api/rp/setup/workspaces/{workspace_id}/activate")
    assert activation.status_code == 200
    session_id = activation.json()["session_id"]

    response = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
        },
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"]["code"] == "story_turn_failed"
    assert "not allowed during phase outline_drafting" in payload["detail"]["error"]["message"]


def test_story_turn_recovers_after_failed_stream_on_same_thread(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _RecoverableStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

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
        body = "".join(response.iter_text())

    assert "writer stream timeout" in body

    retry = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    )

    assert retry.status_code == 200
    payload = retry.json()
    assert payload["current_phase"] == "outline_review"
    assert payload["artifact_kind"] == "chapter_outline"
    assert payload["assistant_text"]
