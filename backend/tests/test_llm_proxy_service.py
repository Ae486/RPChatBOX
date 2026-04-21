"""Tests for raw httpx proxy request building."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.llm_proxy import LLMProxyService
from models.chat import AttachedFile, ChatCompletionRequest, ChatMessage, ProviderConfig


def _extract_contents(chunks):
    contents = []
    for chunk in chunks:
        if not chunk.startswith("data: {"):
            continue
        payload = json.loads(chunk[6:])
        choices = payload.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            contents.append(content)
    return contents


def _build_request(
    provider_type: str = "openai",
    model: str = "gpt-4o-mini",
    **kwargs,
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=[
            ChatMessage(role="system", content=""),
            ChatMessage(role="user", content="hello"),
        ],
        provider=ProviderConfig(
            type=provider_type,
            api_key="sk-test",
            api_url="https://api.example.com/v1",
            custom_headers={},
        ),
        **kwargs,
    )


def test_build_request_body_matches_direct_chain_parameter_shape():
    service = LLMProxyService()
    request = _build_request(
        temperature=0.7,
        max_tokens=2048,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )

    body = service._build_request_body(request)

    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 2048
    assert "top_p" not in body
    assert "frequency_penalty" not in body
    assert "presence_penalty" not in body


def test_build_request_body_adds_stream_usage_request_for_streaming_openai_compatible():
    service = LLMProxyService()
    request = _build_request()
    request.stream = True

    body = service._build_request_body(request)

    assert body["stream_options"] == {"include_usage": True}


def test_build_request_body_preserves_extra_body_field_for_gemini():
    service = LLMProxyService()
    request = _build_request(
        provider_type="gemini",
        model="gemini-2.5-flash",
        extra_body={"google": {"thinking_config": {"temperature": 0.1}}},
    )

    body = service._build_request_body(request)

    assert body["extra_body"] == {
        "google": {
            "thinking_config": {
                "temperature": 0.1,
                "include_thoughts": True,
            }
        }
    }


def test_build_request_body_merges_files_into_messages(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Alpha content", encoding="utf-8")

    service = LLMProxyService()
    request = _build_request(
        files=[
            AttachedFile(
                path=str(text_file),
                mime_type="text/plain",
                name="notes.txt",
            )
        ]
    )

    body = service._build_request_body(request)

    assert isinstance(body["messages"][0]["content"], list)
    assert body["messages"][0]["content"][0]["type"] == "text"
    assert "Alpha content" in body["messages"][0]["content"][0]["text"]


def test_build_request_body_forwards_tools_and_tool_choice():
    service = LLMProxyService()
    request = _build_request(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp_1770224826732__ask_question",
                    "description": "Ask DeepWiki",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice="auto",
    )

    body = service._build_request_body(request)

    assert body["tools"] == request.tools
    assert body["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_chat_completion_stream_normalizes_reasoning_chunks():
    service = LLMProxyService()
    request = _build_request(provider_type="deepseek", model="deepseek-r1")
    request.stream = True

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    async def mock_aiter_lines():
        yield 'data: {"id":"chatcmpl-test","model":"deepseek-r1","choices":[{"delta":{"reasoning_content":"先分析"}}]}'
        yield 'data: {"id":"chatcmpl-test","model":"deepseek-r1","choices":[{"delta":{"content":"最终答案"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    stream_context = MagicMock()
    stream_context.__aenter__.return_value = mock_response
    stream_context.__aexit__.return_value = None

    mock_client = MagicMock()
    mock_client.stream.return_value = stream_context

    with patch("services.llm_proxy.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        chunks = []
        async for chunk in service.chat_completion_stream(request):
            chunks.append(chunk)

    assert _extract_contents(chunks) == ["<think>", "先分析", "</think>", "最终答案"]
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_chat_completion_stream_typed_mode_emits_typed_payloads():
    service = LLMProxyService()
    request = _build_request(provider_type="deepseek", model="deepseek-r1")
    request.stream = True
    request.stream_event_mode = "typed"

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    async def mock_aiter_lines():
        yield 'data: {"id":"chatcmpl-test","model":"deepseek-r1","choices":[{"delta":{"reasoning_content":"先分析"}}]}'
        yield 'data: {"id":"chatcmpl-test","model":"deepseek-r1","choices":[{"delta":{"content":"最终答案"}}]}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    stream_context = MagicMock()
    stream_context.__aenter__.return_value = mock_response
    stream_context.__aexit__.return_value = None

    mock_client = MagicMock()
    mock_client.stream.return_value = stream_context

    with patch("services.llm_proxy.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        chunks = []
        async for chunk in service.chat_completion_stream(request):
            chunks.append(chunk)

    assert 'data: {"type": "thinking_delta", "delta": "\\u5148\\u5206\\u6790"}\n\n' in chunks
    assert 'data: {"type": "text_delta", "delta": "\\u6700\\u7ec8\\u7b54\\u6848"}\n\n' in chunks
    assert chunks[-1] == 'data: {"type": "done"}\n\n'


@pytest.mark.asyncio
async def test_chat_completion_stream_typed_mode_emits_usage_payload():
    service = LLMProxyService()
    request = _build_request()
    request.stream = True
    request.stream_event_mode = "typed"

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    async def mock_aiter_lines():
        yield 'data: {"id":"chatcmpl-test","model":"gpt-4o-mini","choices":[{"delta":{"content":"hello"}}]}'
        yield 'data: {"id":"chatcmpl-test","model":"gpt-4o-mini","choices":[],"usage":{"prompt_tokens":21,"completion_tokens":9,"total_tokens":30}}'
        yield "data: [DONE]"

    mock_response.aiter_lines = mock_aiter_lines

    stream_context = MagicMock()
    stream_context.__aenter__.return_value = mock_response
    stream_context.__aexit__.return_value = None

    mock_client = MagicMock()
    mock_client.stream.return_value = stream_context

    with patch("services.llm_proxy.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        chunks = []
        async for chunk in service.chat_completion_stream(request):
            chunks.append(chunk)

    assert 'data: {"type": "usage", "prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30}\n\n' in chunks
    assert chunks[-1] == 'data: {"type": "done"}\n\n'
