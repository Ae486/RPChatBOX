from __future__ import annotations

import pytest

from models.chat import ChatMessage
from rp.agent_runtime.story.harness_ports import RuntimeModelGateway
from rp.services.story.runtime_model_gateway import RuntimeStoryModelGateway


class _FakeStoryLlmGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"total_tokens": 1},
        }

    async def complete_with_tools(self, **kwargs) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


def _build_adapter(fake_gateway: _FakeStoryLlmGateway) -> RuntimeStoryModelGateway:
    return RuntimeStoryModelGateway(
        llm_gateway=fake_gateway,
        model_id="story-model",
        provider_id="story-provider",
        temperature=0.2,
        max_tokens=123,
        include_reasoning=True,
    )


def _mixed_messages() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    user_message = {
        "role": "user",
        "content": "Need evidence.",
    }
    assistant_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "retrieval.search",
                    "arguments": "{\"query\":\"storm\"}",
                },
            }
        ],
    }
    tool_message = {
        "role": "tool",
        "name": "retrieval.search",
        "tool_call_id": "call-1",
        "content": "evidence result",
    }
    return user_message, assistant_message, tool_message


@pytest.mark.asyncio
async def test_chat_completion_converts_dict_messages_to_chat_message_instances():
    fake_gateway = _FakeStoryLlmGateway()
    adapter = _build_adapter(fake_gateway)
    user_message, assistant_message, tool_message = _mixed_messages()

    await adapter.chat_completion(
        {
            "messages": [user_message, assistant_message, tool_message],
            "tools": [],
            "tool_choice": None,
            "round_no": 7,
        }
    )

    forwarded_messages = fake_gateway.calls[0]["messages"]
    assert all(isinstance(message, ChatMessage) for message in forwarded_messages)
    assert forwarded_messages[0].role == "user"
    assert forwarded_messages[0].content == "Need evidence."
    assert forwarded_messages[1].role == "assistant"
    assert forwarded_messages[1].content is None
    assert forwarded_messages[1].tool_calls == assistant_message["tool_calls"]
    assert forwarded_messages[2].role == "tool"
    assert forwarded_messages[2].name == "retrieval.search"
    assert forwarded_messages[2].tool_call_id == "call-1"
    assert forwarded_messages[2].content == "evidence result"


@pytest.mark.asyncio
async def test_chat_completion_forwards_tools_tool_choice_and_parallel_tool_calls_flag():
    fake_gateway = _FakeStoryLlmGateway()
    adapter = _build_adapter(fake_gateway)
    user_message, assistant_message, tool_message = _mixed_messages()
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
    tool_choice = "auto"

    await adapter.chat_completion(
        {
            "messages": [user_message, assistant_message, tool_message],
            "tools": tools,
            "tool_choice": tool_choice,
            "round_no": 8,
        }
    )

    forwarded = fake_gateway.calls[0]
    assert forwarded["tools"] == tools
    assert forwarded["tool_choice"] == tool_choice
    assert forwarded["extra_body"] == {"parallel_tool_calls": False}


@pytest.mark.asyncio
async def test_chat_completion_returns_gateway_dict_unchanged_and_counts_calls():
    fake_gateway = _FakeStoryLlmGateway()
    adapter = _build_adapter(fake_gateway)
    user_message, assistant_message, tool_message = _mixed_messages()
    request = {
        "messages": [user_message, assistant_message, tool_message],
        "tools": [],
        "tool_choice": None,
        "round_no": 9,
    }

    first = await adapter.chat_completion(request)
    second = await adapter.chat_completion(request)

    assert first is fake_gateway.response
    assert second is fake_gateway.response
    assert adapter.call_count == 2
    assert len(fake_gateway.calls) == 2


def test_runtime_story_model_gateway_satisfies_runtime_model_gateway_protocol():
    adapter = _build_adapter(_FakeStoryLlmGateway())

    assert isinstance(adapter, RuntimeModelGateway)
