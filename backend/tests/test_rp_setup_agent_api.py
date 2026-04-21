"""Integration tests for SetupAgent turn and stream APIs."""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session

from config import get_settings
from models.rp_setup_store import SetupWorkspaceRecord
from services.database import get_engine

def _provider_payload(provider_id: str = "provider-setup"):
    return {
        "id": provider_id,
        "name": "OpenAI",
        "type": "openai",
        "api_key": "sk-test-12345678",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }


def _model_payload(model_id: str = "model-setup"):
    return {
        "id": model_id,
        "provider_id": "provider-setup",
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
        "description": "setup test model",
    }


class _MockSetupLLMService:
    def __init__(self):
        self._stream_round = 0
        self._chat_round = 0

    async def chat_completion_stream(self, request):
        self._stream_round += 1
        workspace_id = request.messages[0].content.split('"workspace_id": "')[1].split('"')[0]
        if self._stream_round == 1:
            yield (
                'data: {"type":"tool_call","tool_calls":[{"id":"call_patch",'
                '"function":{"name":"rp_setup__setup.patch.writing_contract",'
                '"arguments":"{\\"workspace_id\\":\\"%s\\",\\"patch\\":{\\"pov_rules\\":[\\"third_person_limited\\"],'
                '\\"style_rules\\":[\\"restrained\\"],\\"writing_constraints\\":[\\"avoid exposition dumps\\"]}}"}}]}\n\n'
                % workspace_id
            )
            yield 'data: {"type":"done"}\n\n'
            return
        yield 'data: {"type":"text_delta","delta":"Writing contract updated. Continue refining before commit."}\n\n'
        yield 'data: {"type":"done"}\n\n'

    async def chat_completion(self, request):
        self._chat_round += 1
        workspace_id = request.messages[0].content.split('"workspace_id": "')[1].split('"')[0]
        if self._chat_round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_commit",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.proposal.commit",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": workspace_id,
                                                "step_id": "writing_contract",
                                                "target_draft_refs": ["draft:writing_contract"],
                                                "reason": "Current constraints and style are coherent enough for review.",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I prepared a commit proposal for your review.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _CaptureStepLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        system_prompt = request.messages[0].content or ""
        current_step = "unknown"
        marker = "Current step: "
        if marker in system_prompt:
            current_step = system_prompt.split(marker, 1)[1].split("\n", 1)[0].strip()
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"step={current_step}",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _RecoverableSetupLLMService:
    async def chat_completion_stream(self, request):
        yield (
            'data: {"type":"error","error":{"message":"upstream timeout","type":"timeout"}}\n\n'
        )
        yield 'data: {"type":"done"}\n\n'

    async def chat_completion(self, request):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "recovered after timeout",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def _create_workspace(client) -> str:
    response = client.post(
        "/api/rp/setup/workspaces",
        json={"story_id": "story_setup_agent", "mode": "longform"},
    )
    assert response.status_code == 201
    return response.json()["workspace_id"]


def test_setup_agent_stream_turn_applies_setup_patch(client, monkeypatch):
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _MockSetupLLMService(),
    )

    with client.stream(
        "POST",
        f"/api/rp/setup/workspaces/{workspace_id}/turn/stream",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "history": [],
            "user_prompt": "请帮我先收敛写作契约。",
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"type":"tool_call"' in body or '"type": "tool_call"' in body
    assert '"type":"tool_result"' in body or '"type": "tool_result"' in body
    assert "Writing contract updated" in body

    workspace = client.get(f"/api/rp/setup/workspaces/{workspace_id}").json()
    assert workspace["writing_contract_draft"]["pov_rules"] == ["third_person_limited"]
    assert workspace["writing_contract_draft"]["style_rules"] == ["restrained"]


def test_setup_agent_turn_creates_commit_proposal(client, monkeypatch):
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/writing-contract",
        json={
            "pov_rules": ["third_person_limited"],
            "style_rules": ["restrained"],
            "writing_constraints": ["avoid exposition dumps"],
        },
    )
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _MockSetupLLMService(),
    )

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "history": [
                {"role": "assistant", "content": "We already have the draft details."}
            ],
            "user_prompt": "如果已经足够，请发起 review。",
        },
    )

    assert response.status_code == 200
    assert "commit proposal" in response.json()["assistant_text"]

    workspace = client.get(f"/api/rp/setup/workspaces/{workspace_id}").json()
    proposals = [
        item for item in workspace["commit_proposals"] if item["status"] == "pending_review"
    ]
    assert len(proposals) == 1
    assert proposals[0]["step_id"] == "writing_contract"


def test_setup_agent_target_step_overrides_workspace_current_step(client, monkeypatch):
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    with Session(get_engine()) as session:
        record = session.get(SetupWorkspaceRecord, workspace_id)
        assert record is not None
        record.current_step = "story_config"
        session.add(record)
        session.commit()
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CaptureStepLLMService(),
    )

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "target_step": "foundation",
            "history": [],
            "user_prompt": "请继续世界观背景。",
        },
    )

    assert response.status_code == 200
    assert response.json()["assistant_text"] == "step=foundation"


def test_setup_runtime_debug_exposes_checkpoint_state(client, monkeypatch):
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CaptureStepLLMService(),
    )

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "history": [],
            "user_prompt": "请继续世界观背景。",
        },
    )
    assert response.status_code == 200

    debug_response = client.get(
        f"/api/rp/setup/workspaces/{workspace_id}/runtime/debug"
    )
    assert debug_response.status_code == 200
    payload = debug_response.json()
    assert payload["namespace"] == "rp_setup"
    assert payload["latest_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["status"] == "completed"
    assert payload["latest_meaningful_checkpoint"]["state"]["assistant_text"]
    response_payload = payload["latest_meaningful_checkpoint"]["state"]["response_payload"]
    assert response_payload["turn_goal"]["current_step"] == "foundation"
    assert response_payload["working_plan"]["patch_targets"] == ["foundation_draft.entries"]
    assert response_payload["completion_guard"]["allow_finalize"] is True
    assert response_payload["tool_result_count"] == 0
    assert payload["history"]


def test_setup_turn_recovers_after_failed_stream_on_same_thread(client, monkeypatch):
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _RecoverableSetupLLMService(),
    )

    with client.stream(
        "POST",
        f"/api/rp/setup/workspaces/{workspace_id}/turn/stream",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "history": [],
            "user_prompt": "第一次流式执行会失败。",
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "upstream timeout" in body

    retry_response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "history": [],
            "user_prompt": "现在重试。",
        },
    )

    assert retry_response.status_code == 200
    assert retry_response.json()["assistant_text"] == "recovered after timeout"


def test_setup_agent_turn_uses_runtime_v2_by_default(client, monkeypatch):
    monkeypatch.delenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", raising=False)
    monkeypatch.delenv(
        "CHATBOX_BACKEND_RP_SETUP_AGENT_RUNTIME_V2_ENABLED",
        raising=False,
    )
    get_settings.cache_clear()
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CaptureStepLLMService(),
    )

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "target_step": "foundation",
            "history": [],
            "user_prompt": "请继续世界观背景。",
        },
    )

    assert response.status_code == 200
    assert response.json()["assistant_text"] == "step=foundation"

    debug_response = client.get(
        f"/api/rp/setup/workspaces/{workspace_id}/runtime/debug"
    )
    assert debug_response.status_code == 200
    assert (
        debug_response.json()["latest_meaningful_checkpoint"]["state"]["finish_reason"]
        == "completed_text"
    )

    get_settings.cache_clear()


def test_setup_agent_turn_can_fallback_to_legacy_when_flag_disabled(client, monkeypatch):
    monkeypatch.setenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", "false")
    get_settings.cache_clear()
    client.put("/api/providers/provider-setup", json=_provider_payload())
    client.put(
        "/api/providers/provider-setup/models/model-setup",
        json=_model_payload(),
    )
    workspace_id = _create_workspace(client)
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CaptureStepLLMService(),
    )

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/turn",
        json={
            "workspace_id": workspace_id,
            "model_id": "model-setup",
            "target_step": "foundation",
            "history": [],
            "user_prompt": "请继续世界观背景。",
        },
    )

    assert response.status_code == 200
    assert response.json()["assistant_text"] == "step=foundation"

    debug_response = client.get(
        f"/api/rp/setup/workspaces/{workspace_id}/runtime/debug"
    )
    assert debug_response.status_code == 200
    assert (
        debug_response.json()["latest_meaningful_checkpoint"]["state"]["finish_reason"]
        == "legacy_tool_runtime"
    )

    get_settings.cache_clear()
