"""LiteLLM-based LLM service."""
import json
import logging
from typing import AsyncIterator

import litellm

from config import get_settings
from models.chat import ChatCompletionRequest, ProviderConfig

logger = logging.getLogger(__name__)


class LiteLLMService:
    """LLM service using LiteLLM SDK."""

    PROVIDER_PREFIX = {
        "openai": "openai",
        "deepseek": "deepseek",
        "gemini": "gemini",
        "claude": "anthropic",
    }

    # Endpoint paths that LiteLLM appends automatically
    _ENDPOINT_SUFFIXES = ["/chat/completions", "/completions", "/messages", "/embeddings"]

    def __init__(self):
        self.settings = get_settings()
        litellm.telemetry = False
        litellm.drop_params = True
        if self.settings.debug:
            litellm.set_verbose = True

    def _get_litellm_model(self, provider: ProviderConfig, model: str) -> str:
        """Convert model name to LiteLLM format: provider/model."""
        if "/" in model:
            return model
        prefix = self.PROVIDER_PREFIX.get(provider.type, "openai")
        return f"{prefix}/{model}"

    def _get_api_base(self, provider: ProviderConfig) -> str | None:
        """Extract base URL from full endpoint URL.

        Flutter sends full URLs like 'https://host/v1/chat/completions'.
        LiteLLM expects base URL only (e.g., 'https://host/v1') and
        appends the endpoint path automatically.
        """
        base_url = provider.api_url.rstrip("/")
        if not base_url:
            return None

        # Force mode: use URL as-is (remove #)
        if base_url.endswith("#"):
            return base_url[:-1]

        # Strip endpoint paths that LiteLLM adds automatically
        for suffix in self._ENDPOINT_SUFFIXES:
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break

        return base_url.rstrip("/") or None

    def _build_completion_kwargs(self, request: ChatCompletionRequest) -> dict:
        """Build kwargs for litellm.acompletion()."""
        provider = request.provider

        kwargs = {
            "model": self._get_litellm_model(provider, request.model),
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "stream": request.stream,
            "api_key": provider.api_key,
            "timeout": self.settings.llm_request_timeout,
        }

        api_base = self._get_api_base(provider)
        if api_base:
            kwargs["api_base"] = api_base

        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            kwargs["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            kwargs["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            kwargs["stop"] = request.stop

        if request.extra_body:
            kwargs["extra_body"] = request.extra_body

        if request.include_reasoning is not None:
            kwargs["include_reasoning"] = request.include_reasoning

        if provider.custom_headers:
            kwargs["extra_headers"] = provider.custom_headers

        logger.info(
            "LiteLLM kwargs: model=%s, api_base=%s, stream=%s",
            kwargs.get("model"), kwargs.get("api_base"), kwargs.get("stream"),
        )
        return kwargs

    async def chat_completion(self, request: ChatCompletionRequest) -> dict:
        """Handle non-streaming chat completion."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        kwargs = self._build_completion_kwargs(request)
        kwargs["stream"] = False

        response = await litellm.acompletion(**kwargs)
        return response.model_dump()

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Handle streaming chat completion, yielding SSE formatted strings."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        kwargs = self._build_completion_kwargs(request)
        kwargs["stream"] = True

        try:
            response = await litellm.acompletion(**kwargs)

            async for chunk in response:
                chunk_dict = chunk.model_dump()
                yield f"data: {json.dumps(chunk_dict)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            error_data = {"error": {"message": str(e), "type": type(e).__name__}}
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"


def get_http_status_for_exception(exc: Exception) -> tuple[int, str]:
    """Map LiteLLM exceptions to HTTP status codes."""
    if isinstance(exc, litellm.AuthenticationError):
        return 401, "authentication_error"
    elif isinstance(exc, litellm.RateLimitError):
        return 429, "rate_limit_error"
    elif isinstance(exc, litellm.ServiceUnavailableError):
        return 503, "service_unavailable"
    elif isinstance(exc, litellm.Timeout):
        return 504, "timeout"
    elif isinstance(exc, litellm.APIConnectionError):
        return 502, "connection_error"
    elif isinstance(exc, litellm.BadRequestError):
        return 400, "bad_request"
    elif isinstance(exc, litellm.ContextWindowExceededError):
        return 400, "context_window_exceeded"
    else:
        return 500, "internal_error"


_litellm_service: LiteLLMService | None = None


def get_litellm_service() -> LiteLLMService:
    """Get LiteLLM service instance."""
    global _litellm_service
    if _litellm_service is None:
        _litellm_service = LiteLLMService()
    return _litellm_service
