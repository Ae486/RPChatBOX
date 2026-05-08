from __future__ import annotations

import pytest

from models.chat import ChatMessage, ProviderConfig
from rp.services.story_llm_gateway import StoryLlmGateway


class _RecordingLiteLLMService:
    def __init__(self) -> None:
        self.requests = []

    async def chat_completion(self, request):
        self.requests.append(request)
        return {"choices": [{"message": {"content": "ok"}}], "usage": {}}


def _patch_model_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ProviderConfig(
        type="openai",
        api_key="test-key",
        api_url="https://example.com/v1",
    )
    monkeypatch.setattr(
        StoryLlmGateway,
        "_resolve_provider_and_model",
        staticmethod(lambda **_kwargs: (provider, "resolved-model")),
    )


@pytest.mark.asyncio
async def test_complete_with_tools_enables_tool_runtime_request(monkeypatch):
    _patch_model_resolution(monkeypatch)
    llm_service = _RecordingLiteLLMService()
    gateway = StoryLlmGateway(llm_service=llm_service)

    await gateway.complete_with_tools(
        model_id="story-model",
        provider_id="story-provider",
        messages=[ChatMessage(role="user", content="Find recall evidence.")],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "retrieval.search",
                    "description": "Search retrieval cards.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice="auto",
    )

    request = llm_service.requests[0]
    assert request.enable_tools is True


@pytest.mark.asyncio
async def test_complete_with_tools_preserves_tools_and_tool_choice(monkeypatch):
    _patch_model_resolution(monkeypatch)
    llm_service = _RecordingLiteLLMService()
    gateway = StoryLlmGateway(llm_service=llm_service)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "retrieval.expand",
                "description": "Expand a retrieval card.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    tool_choice = {
        "type": "function",
        "function": {"name": "retrieval.expand"},
    }

    await gateway.complete_with_tools(
        model_id="story-model",
        provider_id="story-provider",
        messages=[ChatMessage(role="user", content="Expand card R1.")],
        tools=tools,
        tool_choice=tool_choice,
    )

    request = llm_service.requests[0]
    assert request.tools == tools
    assert request.tool_choice == tool_choice
