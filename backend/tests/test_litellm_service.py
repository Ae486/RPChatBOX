"""Tests for LiteLLM service."""
import pytest
from unittest.mock import patch, MagicMock

import litellm

from services.litellm_service import LiteLLMService, get_http_status_for_exception
from models.chat import ChatCompletionRequest, ProviderConfig, ChatMessage


@pytest.fixture
def service():
    with patch("services.litellm_service.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(llm_request_timeout=120.0, debug=False)
        return LiteLLMService()


@pytest.fixture
def openai_provider():
    return ProviderConfig(type="openai", api_key="sk-test", api_url="https://api.openai.com/v1")


@pytest.fixture
def sample_request(openai_provider):
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hello")],
        stream=False,
        temperature=0.7,
        provider=openai_provider,
    )


class TestGetLitellmModel:
    def test_adds_prefix(self, service, openai_provider):
        assert service._get_litellm_model(openai_provider, "gpt-4") == "openai/gpt-4"

    def test_deepseek(self, service):
        p = ProviderConfig(type="deepseek", api_key="", api_url="https://api.deepseek.com/v1")
        assert service._get_litellm_model(p, "deepseek-chat") == "deepseek/deepseek-chat"

    def test_gemini(self, service):
        p = ProviderConfig(type="gemini", api_key="", api_url="https://generativelanguage.googleapis.com")
        assert service._get_litellm_model(p, "gemini-2.0-flash") == "gemini/gemini-2.0-flash"

    def test_claude(self, service):
        p = ProviderConfig(type="claude", api_key="", api_url="https://api.anthropic.com")
        assert service._get_litellm_model(p, "claude-3-opus") == "anthropic/claude-3-opus"

    def test_already_prefixed(self, service, openai_provider):
        assert service._get_litellm_model(openai_provider, "custom/model") == "custom/model"

    def test_unknown_provider_defaults_openai(self, service):
        p = ProviderConfig(type="unknown", api_key="", api_url="https://custom.com")
        assert service._get_litellm_model(p, "model") == "openai/model"


class TestGetApiBase:
    """Core fix: strip endpoint paths Flutter appends (e.g., /chat/completions)."""

    def test_strips_chat_completions(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="https://api.openai.com/v1/chat/completions")
        assert service._get_api_base(p) == "https://api.openai.com/v1"

    def test_strips_messages(self, service):
        p = ProviderConfig(type="claude", api_key="", api_url="https://api.anthropic.com/v1/messages")
        assert service._get_api_base(p) == "https://api.anthropic.com/v1"

    def test_no_stripping_needed(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="https://my-proxy.com/v1")
        assert service._get_api_base(p) == "https://my-proxy.com/v1"

    def test_base_only(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="https://my-proxy.com")
        assert service._get_api_base(p) == "https://my-proxy.com"

    def test_force_mode_hash(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="https://api.example.com/custom#")
        assert service._get_api_base(p) == "https://api.example.com/custom"

    def test_trailing_slash_stripped(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="https://api.example.com/v1/")
        assert service._get_api_base(p) == "https://api.example.com/v1"

    def test_empty_url_returns_none(self, service):
        p = ProviderConfig(type="openai", api_key="", api_url="")
        assert service._get_api_base(p) is None


class TestBuildCompletionKwargs:
    def test_basic_kwargs(self, service, sample_request):
        kwargs = service._build_completion_kwargs(sample_request)
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["api_base"] == "https://api.openai.com/v1"
        assert kwargs["temperature"] == 0.7

    def test_full_url_gets_stripped(self, service):
        """The actual bug: Flutter sends full URL, must strip for LiteLLM."""
        p = ProviderConfig(type="openai", api_key="sk-test", api_url="https://my-proxy.com/v1/chat/completions")
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Hello")],
            provider=p,
        )
        kwargs = service._build_completion_kwargs(req)
        assert kwargs["api_base"] == "https://my-proxy.com/v1"

    def test_extra_body(self, service, openai_provider):
        req = ChatCompletionRequest(
            model="gemini-2.0-flash",
            messages=[ChatMessage(role="user", content="Hi")],
            provider=openai_provider,
            extra_body={"google": {"thinking_config": {"include_thoughts": True}}},
        )
        kwargs = service._build_completion_kwargs(req)
        assert kwargs["extra_body"]["google"]["thinking_config"]["include_thoughts"] is True

    def test_custom_headers(self, service):
        p = ProviderConfig(
            type="openai", api_key="sk-test", api_url="https://api.example.com",
            custom_headers={"X-Custom": "value"},
        )
        req = ChatCompletionRequest(
            model="gpt-4", messages=[ChatMessage(role="user", content="Hi")], provider=p,
        )
        kwargs = service._build_completion_kwargs(req)
        assert kwargs["extra_headers"] == {"X-Custom": "value"}

    def test_none_params_excluded(self, service, openai_provider):
        req = ChatCompletionRequest(
            model="gpt-4", messages=[ChatMessage(role="user", content="Hi")], provider=openai_provider,
        )
        kwargs = service._build_completion_kwargs(req)
        assert "temperature" not in kwargs
        assert "max_tokens" not in kwargs

    def test_include_reasoning_passed(self, service, openai_provider):
        req = ChatCompletionRequest(
            model="deepseek-reasoner",
            messages=[ChatMessage(role="user", content="Hi")],
            provider=openai_provider,
            include_reasoning=True,
        )
        kwargs = service._build_completion_kwargs(req)
        assert kwargs["include_reasoning"] is True

    def test_include_reasoning_not_set(self, service, openai_provider):
        req = ChatCompletionRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
            provider=openai_provider,
        )
        kwargs = service._build_completion_kwargs(req)
        assert "include_reasoning" not in kwargs


class TestChatCompletion:
    @pytest.mark.asyncio
    @patch("services.litellm_service.litellm.acompletion")
    async def test_non_streaming(self, mock_acompletion, service, sample_request):
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "Hi!"}}],
        }
        mock_acompletion.return_value = mock_response

        result = await service.chat_completion(sample_request)
        assert result["id"] == "chatcmpl-test"
        mock_acompletion.assert_called_once()
        assert mock_acompletion.call_args[1]["stream"] is False

    @pytest.mark.asyncio
    async def test_missing_provider(self, service):
        req = ChatCompletionRequest(
            model="gpt-4", messages=[ChatMessage(role="user", content="Hi")],
        )
        with pytest.raises(ValueError, match="Provider configuration is required"):
            await service.chat_completion(req)


class TestChatCompletionStream:
    @pytest.mark.asyncio
    @patch("services.litellm_service.litellm.acompletion")
    async def test_streaming(self, mock_acompletion, service, sample_request):
        chunk1 = MagicMock()
        chunk1.model_dump.return_value = {"choices": [{"delta": {"content": "Hello"}}]}
        chunk2 = MagicMock()
        chunk2.model_dump.return_value = {"choices": [{"delta": {"content": " world"}}]}

        async def mock_aiter():
            yield chunk1
            yield chunk2

        mock_acompletion.return_value = mock_aiter()
        sample_request.stream = True

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert len(chunks) == 3  # 2 data chunks + [DONE]
        assert chunks[0].startswith("data: ")
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    @patch("services.litellm_service.litellm.acompletion")
    async def test_error_before_stream(self, mock_acompletion, service, sample_request):
        mock_acompletion.side_effect = litellm.AuthenticationError(
            message="Invalid API key", llm_provider="openai", model="gpt-4o"
        )
        sample_request.stream = True

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert len(chunks) == 2  # error event + [DONE]
        assert '"error"' in chunks[0]
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    @patch("services.litellm_service.litellm.acompletion")
    async def test_error_mid_stream(self, mock_acompletion, service, sample_request):
        chunk1 = MagicMock()
        chunk1.model_dump.return_value = {"choices": [{"delta": {"content": "Hi"}}]}

        async def mock_aiter_with_error():
            yield chunk1
            raise litellm.APIConnectionError(
                message="Connection lost", llm_provider="openai", model="gpt-4o"
            )

        mock_acompletion.return_value = mock_aiter_with_error()
        sample_request.stream = True

        chunks = []
        async for chunk in service.chat_completion_stream(sample_request):
            chunks.append(chunk)

        assert len(chunks) == 3  # 1 data + error event + [DONE]
        assert '"error"' in chunks[1]
        assert chunks[-1] == "data: [DONE]\n\n"


class TestExceptionMapping:
    def test_auth_error(self):
        exc = litellm.AuthenticationError(
            message="Invalid key", llm_provider="openai", model="gpt-4"
        )
        status, code = get_http_status_for_exception(exc)
        assert status == 401

    def test_unknown_exception(self):
        status, code = get_http_status_for_exception(RuntimeError("unknown"))
        assert status == 500
