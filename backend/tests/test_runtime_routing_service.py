"""Tests for backend runtime routing service."""
from unittest.mock import AsyncMock, MagicMock

import litellm
import pytest

from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig
from services.runtime_routing_service import (
    BackendFallbackPolicy,
    RuntimeRoutingService,
)


@pytest.fixture
def sample_request():
    return ChatCompletionRequest(
        model="gpt-4o-mini",
        messages=[ChatMessage(role="user", content="hello")],
        stream=False,
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://api.openai.com/v1",
            custom_headers={},
        ),
    )


class TestBackendFallbackPolicy:
    def test_should_fallback_exception_for_connection_error(self):
        exc = litellm.APIConnectionError(
            message="Connection failed",
            llm_provider="openai",
            model="gpt-4o-mini",
        )

        assert BackendFallbackPolicy.should_fallback_exception(
            exc,
            has_emitted_chunk=False,
        )

    def test_should_not_fallback_exception_after_chunks(self):
        exc = litellm.APIConnectionError(
            message="Connection failed",
            llm_provider="openai",
            model="gpt-4o-mini",
        )

        assert not BackendFallbackPolicy.should_fallback_exception(
            exc,
            has_emitted_chunk=True,
        )

    def test_should_not_fallback_auth_error(self):
        exc = litellm.AuthenticationError(
            message="Invalid key",
            llm_provider="openai",
            model="gpt-4o-mini",
        )

        assert not BackendFallbackPolicy.should_fallback_exception(
            exc,
            has_emitted_chunk=False,
        )

    def test_should_fallback_sse_error_for_connection_type(self):
        assert BackendFallbackPolicy.should_fallback_sse_error(
            error_type="APIConnectionError",
            error_message="Connection lost",
            has_emitted_chunk=False,
        )

    def test_should_not_fallback_sse_error_after_chunks(self):
        assert not BackendFallbackPolicy.should_fallback_sse_error(
            error_type="APIConnectionError",
            error_message="Connection lost",
            has_emitted_chunk=True,
        )


class TestRuntimeRoutingService:
    @pytest.mark.asyncio
    async def test_stream_tool_runtime_requires_enable_tools_flag(
        self,
        sample_request,
        monkeypatch,
    ):
        sample_request.stream = True
        sample_request.stream_event_mode = "typed"
        sample_request.enable_tools = False

        async def primary_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from primary"}}]}\n\n'
            yield "data: [DONE]\n\n"

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock(return_value=primary_stream())
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock()

        fake_mcp = MagicMock()
        fake_mcp.has_tools.return_value = True
        monkeypatch.setattr(
            "services.runtime_routing_service.get_mcp_manager",
            lambda: fake_mcp,
        )

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert chunks == [
            'data: {"choices":[{"delta":{"content":"Hello from primary"}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        primary_service.chat_completion_stream.assert_called_once_with(sample_request)
        fallback_service.chat_completion_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_tool_runtime_uses_litellm_even_when_provider_direct(
        self,
        sample_request,
        monkeypatch,
    ):
        sample_request.stream = True
        sample_request.stream_event_mode = "typed"
        sample_request.enable_tools = True
        sample_request.provider.backend_mode = "direct"

        async def primary_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from primary"}}]}\n\n'
            yield "data: [DONE]\n\n"

        async def passthrough_tool_runtime(self, request, *, llm_service):
            async for chunk in llm_service.chat_completion_stream(request):
                yield chunk

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock(return_value=primary_stream())
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock()

        fake_mcp = MagicMock()
        fake_mcp.has_tools.return_value = True
        monkeypatch.setattr(
            "services.runtime_routing_service.get_mcp_manager",
            lambda: fake_mcp,
        )
        monkeypatch.setattr(
            "services.runtime_routing_service.ToolRuntimeService.chat_completion_stream",
            passthrough_tool_runtime,
        )

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert chunks == [
            'data: {"choices":[{"delta":{"content":"Hello from primary"}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        primary_service.chat_completion_stream.assert_called_once_with(sample_request)
        fallback_service.chat_completion_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_stream_tool_runtime_requires_enable_tools_flag(
        self,
        sample_request,
        monkeypatch,
    ):
        sample_request.enable_tools = False

        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(return_value={"id": "primary-ok"})
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        fake_mcp = MagicMock()
        fake_mcp.has_tools.return_value = True
        monkeypatch.setattr(
            "services.runtime_routing_service.get_mcp_manager",
            lambda: fake_mcp,
        )

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        result = await service.chat_completion(sample_request)

        assert result == {"id": "primary-ok"}
        primary_service.chat_completion.assert_awaited_once_with(sample_request)
        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_stream_tool_runtime_uses_litellm_even_when_provider_direct(
        self,
        sample_request,
        monkeypatch,
    ):
        sample_request.enable_tools = True
        sample_request.provider.backend_mode = "direct"

        async def passthrough_tool_runtime(self, request, *, llm_service):
            return await llm_service.chat_completion(request)

        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(return_value={"id": "litellm-tool"})
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        fake_mcp = MagicMock()
        fake_mcp.has_tools.return_value = True
        monkeypatch.setattr(
            "services.runtime_routing_service.get_mcp_manager",
            lambda: fake_mcp,
        )
        monkeypatch.setattr(
            "services.runtime_routing_service.ToolRuntimeService.chat_completion",
            passthrough_tool_runtime,
        )

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        result = await service.chat_completion(sample_request)

        assert result == {"id": "litellm-tool"}
        primary_service.chat_completion.assert_awaited_once_with(sample_request)
        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_streaming_falls_back_to_httpx_on_safe_litellm_error(
        self, sample_request
    ):
        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(
            side_effect=litellm.APIConnectionError(
                message="Connection failed",
                llm_provider="openai",
                model="gpt-4o-mini",
            )
        )
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock(return_value={"id": "fallback-ok"})

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        result = await service.chat_completion(sample_request)

        assert result == {"id": "fallback-ok"}
        fallback_service.chat_completion.assert_awaited_once_with(sample_request)

    @pytest.mark.asyncio
    async def test_non_streaming_does_not_fallback_on_auth_error(self, sample_request):
        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(
            side_effect=litellm.AuthenticationError(
                message="Invalid key",
                llm_provider="openai",
                model="gpt-4o-mini",
            )
        )
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        with pytest.raises(litellm.AuthenticationError):
            await service.chat_completion(sample_request)

        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_streaming_uses_httpx_only_when_backend_mode_direct(
        self, sample_request
    ):
        sample_request.provider.backend_mode = "direct"
        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(return_value={"id": "primary-should-not-run"})
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock(return_value={"id": "httpx-direct"})

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        result = await service.chat_completion(sample_request)

        assert result == {"id": "httpx-direct"}
        primary_service.chat_completion.assert_not_called()
        fallback_service.chat_completion.assert_awaited_once_with(sample_request)

    @pytest.mark.asyncio
    async def test_non_streaming_proxy_mode_disables_httpx_fallback(self, sample_request):
        sample_request.provider.backend_mode = "proxy"
        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(
            side_effect=litellm.APIConnectionError(
                message="Connection failed",
                llm_provider="openai",
                model="gpt-4o-mini",
            )
        )
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        with pytest.raises(litellm.APIConnectionError):
            await service.chat_completion(sample_request)

        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_streaming_auto_mode_honors_provider_fallback_disabled(
        self, sample_request
    ):
        sample_request.provider.backend_mode = "auto"
        sample_request.provider.fallback_enabled = False
        primary_service = MagicMock()
        primary_service.chat_completion = AsyncMock(
            side_effect=litellm.APIConnectionError(
                message="Connection failed",
                llm_provider="openai",
                model="gpt-4o-mini",
            )
        )
        fallback_service = MagicMock()
        fallback_service.chat_completion = AsyncMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        with pytest.raises(litellm.APIConnectionError):
            await service.chat_completion(sample_request)

        fallback_service.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_falls_back_on_pre_chunk_error_event(self, sample_request):
        async def primary_stream():
            yield (
                'data: {"error":{"message":"status_code=503 upstream unavailable",'
                '"type":"ServiceUnavailableError"}}\n\n'
            )
            yield "data: [DONE]\n\n"

        async def fallback_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from fallback"}}]}\n\n'
            yield "data: [DONE]\n\n"

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock(return_value=primary_stream())
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock(return_value=fallback_stream())

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert chunks == [
            'data: {"choices":[{"delta":{"content":"Hello from fallback"}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        fallback_service.chat_completion_stream.assert_called_once_with(sample_request)

    @pytest.mark.asyncio
    async def test_stream_direct_mode_uses_httpx_only(self, sample_request):
        sample_request.provider.backend_mode = "direct"

        async def direct_stream():
            yield 'data: {"choices":[{"delta":{"content":"Hello from httpx"}}]}\n\n'
            yield "data: [DONE]\n\n"

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock()
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock(return_value=direct_stream())

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert chunks == [
            'data: {"choices":[{"delta":{"content":"Hello from httpx"}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        primary_service.chat_completion_stream.assert_not_called()
        fallback_service.chat_completion_stream.assert_called_once_with(sample_request)

    @pytest.mark.asyncio
    async def test_stream_does_not_fallback_after_visible_content(self, sample_request):
        async def primary_stream():
            yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            yield (
                'data: {"error":{"message":"status_code=503 upstream unavailable",'
                '"type":"ServiceUnavailableError"}}\n\n'
            )
            yield "data: [DONE]\n\n"

        primary_service = MagicMock()
        primary_service.chat_completion_stream = MagicMock(return_value=primary_stream())
        fallback_service = MagicMock()
        fallback_service.chat_completion_stream = MagicMock()

        service = RuntimeRoutingService(
            primary_service=primary_service,
            fallback_service=fallback_service,
            settings=MagicMock(llm_enable_httpx_fallback=True),
        )

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert chunks == [
            'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
            'data: {"error":{"message":"status_code=503 upstream unavailable","type":"ServiceUnavailableError"}}\n\n',
            "data: [DONE]\n\n",
        ]
        fallback_service.chat_completion_stream.assert_not_called()
