"""Tests for Gemini native routing inside runtime routing service."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig
from services.runtime_routing_service import RuntimeRoutingService


def _build_gemini_request(stream: bool = False) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gemini-2.5-flash",
        messages=[ChatMessage(role="user", content="hello")],
        stream=stream,
        provider=ProviderConfig(
            type="gemini",
            api_key="gemini-key",
            api_url="https://generativelanguage.googleapis.com/v1",
            custom_headers={},
        ),
    )


class TestRuntimeRoutingGeminiNative:
    @pytest.mark.asyncio
    async def test_auto_mode_prefers_gemini_native_for_non_streaming(self):
        request = _build_gemini_request(stream=False)
        native_service = MagicMock()
        native_service.supports_request.return_value = True
        native_service.chat_completion = AsyncMock(return_value={"id": "native-ok"})

        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock()
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            gemini_native_service=native_service,
            settings=MagicMock(
                llm_enable_httpx_fallback=True,
                llm_enable_gemini_native=True,
            ),
        )

        result = await service.chat_completion(request)

        assert result["id"] == "native-ok"
        primary_service.chat_completion.assert_not_called()
        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_native_failure_falls_back_to_existing_auto_chain(self):
        request = _build_gemini_request(stream=False)
        native_service = MagicMock()
        native_service.supports_request.return_value = True
        native_service.chat_completion = AsyncMock(side_effect=RuntimeError("native boom"))

        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(return_value={"id": "litellm-ok"})
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            gemini_native_service=native_service,
            settings=MagicMock(
                llm_enable_httpx_fallback=True,
                llm_enable_gemini_native=True,
            ),
        )

        result = await service.chat_completion(request)

        assert result["id"] == "litellm-ok"
        primary_service.chat_completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_mode_prefers_gemini_native_for_streaming(self):
        request = _build_gemini_request(stream=True)

        async def native_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from native"}}]}\n\n'
            yield "data: [DONE]\n\n"

        native_service = MagicMock()
        native_service.supports_request.return_value = True
        native_service.chat_completion_stream = MagicMock(return_value=native_stream())

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock()
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            gemini_native_service=native_service,
            settings=MagicMock(
                llm_enable_httpx_fallback=True,
                llm_enable_gemini_native=True,
            ),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(request):
            chunks.append(chunk)

        assert chunks[0].startswith('data: {"choices"')
        primary_service.chat_completion_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_native_stream_error_before_visible_chunk_falls_back_to_litellm(self):
        request = _build_gemini_request(stream=True)

        async def native_stream():
            yield 'data: {"error":{"message":"native fail","type":"RuntimeError"}}\n\n'
            yield "data: [DONE]\n\n"

        async def primary_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from litellm"}}]}\n\n'
            yield "data: [DONE]\n\n"

        native_service = MagicMock()
        native_service.supports_request.return_value = True
        native_service.chat_completion_stream = MagicMock(return_value=native_stream())

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock(return_value=primary_stream())
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            gemini_native_service=native_service,
            settings=MagicMock(
                llm_enable_httpx_fallback=True,
                llm_enable_gemini_native=True,
            ),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(request):
            chunks.append(chunk)

        assert any("Hello from litellm" in chunk for chunk in chunks)
        primary_service.chat_completion_stream.assert_called_once()
