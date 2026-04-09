"""Tests for Gemini native backend service."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig
from services.gemini_native_service import GeminiNativeService


class _FakePartFactory:
    @staticmethod
    def from_text(*, text):
        return {"kind": "text", "text": text}

    @staticmethod
    def from_bytes(*, data, mime_type):
        return {"kind": "bytes", "data": data, "mime_type": mime_type}


class _FakeContent:
    def __init__(self, *, role, parts):
        self.role = role
        self.parts = parts


class _FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeThinkingConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeHttpOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeTypes:
    Part = _FakePartFactory
    Content = _FakeContent
    GenerateContentConfig = _FakeGenerateContentConfig
    ThinkingConfig = _FakeThinkingConfig
    HttpOptions = _FakeHttpOptions


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, exclude_none=True):
        return self._payload


def _build_request(**kwargs) -> ChatCompletionRequest:
    provider = kwargs.pop(
        "provider",
        ProviderConfig(
            type="gemini",
            api_key="gemini-key",
            api_url="https://generativelanguage.googleapis.com/v1",
            custom_headers={},
        ),
    )
    return ChatCompletionRequest(
        model="gemini-2.5-flash",
        messages=[
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="hello"),
        ],
        provider=provider,
        **kwargs,
    )


def test_supports_request_only_for_native_gemini_provider():
    service = GeminiNativeService(settings=MagicMock(llm_request_timeout=120.0))

    assert service.supports_request(_build_request()) is True

    openai_like = _build_request(
        provider=ProviderConfig(
            type="gemini",
            api_key="gemini-key",
            api_url="https://generativelanguage.googleapis.com/v1beta/openai",
            custom_headers={},
        )
    )
    assert service.supports_request(openai_like) is False


def test_build_generate_content_inputs_maps_messages_and_images():
    service = GeminiNativeService(settings=MagicMock(llm_request_timeout=120.0))
    sdk = SimpleNamespace(types=_FakeTypes)
    request = ChatCompletionRequest(
        model="gemini-2.5-flash",
        messages=[
            ChatMessage(role="system", content="System rule"),
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    },
                ],
            ),
            ChatMessage(role="assistant", content="Previous answer"),
        ],
        provider=ProviderConfig(
            type="gemini",
            api_key="gemini-key",
            api_url="https://generativelanguage.googleapis.com/v1",
            custom_headers={},
        ),
        include_reasoning=True,
        extra_body={"google": {"thinking_config": {"include_thoughts": True}}},
    )

    contents, config = service._build_generate_content_inputs(request, sdk=sdk)

    assert len(contents) == 2
    assert contents[0].role == "user"
    assert contents[0].parts[0]["text"] == "Describe this image"
    assert contents[0].parts[1]["mime_type"] == "image/png"
    assert contents[1].role == "model"
    assert config.kwargs["system_instruction"] == "System rule"
    assert config.kwargs["thinking_config"].kwargs["include_thoughts"] is True


@pytest.mark.asyncio
async def test_chat_completion_stream_converts_native_chunks_to_compatible_sse():
    settings = MagicMock(llm_request_timeout=120.0)
    service = GeminiNativeService(settings=settings)

    fake_client = MagicMock()
    fake_stream = AsyncMock()
    fake_stream.__aiter__.return_value = [
        _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": "先思考"},
                                {"text": "再输出"},
                            ]
                        }
                    }
                ]
            }
        )
    ]
    fake_client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream)

    service._get_sdk = MagicMock(return_value=SimpleNamespace(types=_FakeTypes))
    service._get_client = MagicMock(return_value=fake_client)
    service._build_generate_content_inputs = MagicMock(return_value=([], None))

    chunks = []
    async for chunk in service.chat_completion_stream(_build_request(stream=True)):
        chunks.append(chunk)

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

    assert contents == ["<think>", "先思考", "</think>", "再输出"]
    assert chunks[-1] == "data: [DONE]\n\n"


def test_build_openai_compatible_response_preserves_thinking_tags():
    service = GeminiNativeService(settings=MagicMock(llm_request_timeout=120.0))
    payload = {
        "id": "gemini-response",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": "先思考"},
                        {"text": "最终回答"},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
    }

    response = service._build_openai_compatible_response(
        payload,
        model="gemini-2.5-flash",
        provider_type="gemini",
    )

    assert response["choices"][0]["message"]["content"] == "<think>先思考</think>最终回答"
    assert response["usage"]["total_tokens"] == 15
