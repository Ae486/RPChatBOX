"""LiteLLM-based LLM service."""
import hashlib
import json
import logging
from typing import AsyncIterator

import litellm

from config import get_settings
from models.chat import ChatCompletionRequest, ProviderConfig
from services.request_normalization import get_request_normalization_service
from services.stream_normalization import StreamNormalizationService

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
        self._routers: dict[str, litellm.Router] = {}
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

    def _build_common_request_kwargs(
        self,
        request: ChatCompletionRequest,
        *,
        model: str,
    ) -> dict:
        """Build provider-agnostic request kwargs from a normalized request."""
        provider = request.provider
        kwargs = {
            "model": model,
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "stream": request.stream,
        }

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

        if request.include_reasoning is not None and provider.type != "gemini":
            kwargs["include_reasoning"] = request.include_reasoning

        return kwargs

    def _build_completion_kwargs_from_normalized(
        self, request: ChatCompletionRequest
    ) -> dict:
        """Build kwargs for litellm.acompletion() from a normalized request."""
        provider = request.provider
        kwargs = self._build_common_request_kwargs(
            request,
            model=self._get_litellm_model(provider, request.model),
        )
        kwargs["api_key"] = provider.api_key
        kwargs["timeout"] = self.settings.llm_request_timeout

        api_base = self._get_api_base(provider)
        if api_base:
            kwargs["api_base"] = api_base

        if provider.custom_headers:
            kwargs["extra_headers"] = provider.custom_headers

        logger.info(
            "LiteLLM kwargs: model=%s, api_base=%s, stream=%s",
            kwargs.get("model"), kwargs.get("api_base"), kwargs.get("stream"),
        )
        return kwargs

    def _build_completion_kwargs(self, request: ChatCompletionRequest) -> dict:
        """Build kwargs for litellm.acompletion()."""
        normalized_request = get_request_normalization_service().normalize(request)
        return self._build_completion_kwargs_from_normalized(normalized_request)

    def _build_router_request_kwargs_from_normalized(
        self, request: ChatCompletionRequest
    ) -> dict:
        """Build kwargs for Router.acompletion() from a normalized request."""
        kwargs = self._build_common_request_kwargs(request, model=request.model)
        logger.info(
            "LiteLLM Router request: model=%s, stream=%s",
            kwargs.get("model"),
            kwargs.get("stream"),
        )
        return kwargs

    def _build_router_model_list(
        self, request: ChatCompletionRequest
    ) -> list[dict[str, object]]:
        """Build a single-deployment Router config for the current request."""
        provider = request.provider
        stream_timeout = self._get_effective_stream_timeout(request)
        litellm_params: dict[str, object] = {
            "model": self._get_litellm_model(provider, request.model),
            "api_key": provider.api_key,
            "timeout": self.settings.llm_request_timeout,
        }

        api_base = self._get_api_base(provider)
        if api_base:
            litellm_params["api_base"] = api_base
        if provider.custom_headers:
            litellm_params["extra_headers"] = provider.custom_headers
        if stream_timeout > 0:
            litellm_params["stream_timeout"] = stream_timeout

        return [
            {
                "model_name": request.model,
                "litellm_params": litellm_params,
            }
        ]

    def _router_cache_key(self, request: ChatCompletionRequest) -> str:
        """Build a stable cache key for Router instances."""
        provider = request.provider
        raw_key = json.dumps(
            {
                "model": request.model,
                "provider_type": provider.type,
                "api_url": provider.api_url,
                "api_key": provider.api_key,
                "custom_headers": provider.custom_headers,
                "backend_mode": provider.backend_mode,
                "fallback_timeout_ms": provider.fallback_timeout_ms,
                "circuit_breaker": (
                    provider.circuit_breaker.model_dump(exclude_none=True)
                    if provider.circuit_breaker is not None
                    else None
                ),
                "effective_stream_timeout": self._get_effective_stream_timeout(request),
                "effective_allowed_fails": self._get_effective_allowed_fails(request),
                "effective_cooldown_time": self._get_effective_cooldown_time(request),
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _get_router(self, request: ChatCompletionRequest) -> litellm.Router | None:
        """Return a cached LiteLLM Router for the current provider/model."""
        if not self.settings.use_litellm_router or not hasattr(litellm, "Router"):
            return None

        cache_key = self._router_cache_key(request)
        router = self._routers.get(cache_key)
        if router is not None:
            return router

        router_kwargs: dict[str, object] = {
            "model_list": self._build_router_model_list(request),
            "num_retries": self.settings.llm_num_retries,
            "timeout": self.settings.llm_request_timeout,
            "stream_timeout": (
                self._get_effective_stream_timeout(request)
                if self._get_effective_stream_timeout(request) > 0
                else None
            ),
            "set_verbose": self.settings.debug,
        }
        allowed_fails = self._get_effective_allowed_fails(request)
        cooldown_time = self._get_effective_cooldown_time(request)
        if allowed_fails > 0:
            router_kwargs["allowed_fails"] = allowed_fails
        if cooldown_time > 0:
            router_kwargs["cooldown_time"] = cooldown_time

        router = litellm.Router(**router_kwargs)
        self._routers[cache_key] = router
        return router

    def _get_effective_stream_timeout(self, request: ChatCompletionRequest) -> float:
        """Resolve the first-chunk timeout for this request."""
        provider = request.provider
        if (
            provider
            and provider.backend_mode == "auto"
            and provider.fallback_timeout_ms is not None
            and provider.fallback_timeout_ms > 0
        ):
            return provider.fallback_timeout_ms / 1000.0
        return self.settings.llm_stream_timeout

    def _get_effective_allowed_fails(self, request: ChatCompletionRequest) -> int:
        """Resolve Router allowed_fails for this request."""
        provider = request.provider
        if (
            provider
            and provider.backend_mode == "auto"
            and provider.circuit_breaker is not None
            and provider.circuit_breaker.failure_threshold is not None
            and provider.circuit_breaker.failure_threshold > 0
        ):
            return provider.circuit_breaker.failure_threshold
        return self.settings.llm_allowed_fails

    def _get_effective_cooldown_time(self, request: ChatCompletionRequest) -> float:
        """Resolve Router cooldown_time (seconds) for this request."""
        provider = request.provider
        if (
            provider
            and provider.backend_mode == "auto"
            and provider.circuit_breaker is not None
            and provider.circuit_breaker.open_ms is not None
            and provider.circuit_breaker.open_ms > 0
        ):
            return provider.circuit_breaker.open_ms / 1000.0
        return self.settings.llm_cooldown_time

    async def chat_completion(self, request: ChatCompletionRequest) -> dict:
        """Handle non-streaming chat completion."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        normalized_request = get_request_normalization_service().normalize(request)
        router = self._get_router(normalized_request)
        if router is not None:
            kwargs = self._build_router_request_kwargs_from_normalized(
                normalized_request
            )
            kwargs["stream"] = False
            response = await router.acompletion(**kwargs)
        else:
            kwargs = self._build_completion_kwargs_from_normalized(normalized_request)
            kwargs["stream"] = False
            response = await litellm.acompletion(**kwargs)
        return response.model_dump()

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Handle streaming chat completion, yielding SSE formatted strings."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        normalized_request = get_request_normalization_service().normalize(request)
        router = self._get_router(normalized_request)
        if router is not None:
            kwargs = self._build_router_request_kwargs_from_normalized(
                normalized_request
            )
            kwargs["stream"] = True
        else:
            kwargs = self._build_completion_kwargs_from_normalized(normalized_request)
            kwargs["stream"] = True
        stream_normalizer = StreamNormalizationService(
            model=normalized_request.model,
            provider_type=normalized_request.provider.type,
        )
        typed_mode = normalized_request.stream_event_mode == "typed"

        try:
            if router is not None:
                response = await router.acompletion(**kwargs)
            else:
                response = await litellm.acompletion(**kwargs)

            async for chunk in response:
                chunk_dict = chunk.model_dump()
                events = stream_normalizer.extract_events(chunk_dict)
                if typed_mode:
                    for payload in stream_normalizer.emit_typed_payloads(events):
                        yield f"data: {json.dumps(payload)}\n\n"
                else:
                    for normalized_chunk in stream_normalizer.emit_compatible_chunks(
                        events,
                        template=chunk_dict,
                    ):
                        yield f"data: {json.dumps(normalized_chunk)}\n\n"

            if typed_mode:
                yield f"data: {json.dumps(stream_normalizer.build_done_payload())}\n\n"
            else:
                for normalized_chunk in stream_normalizer.flush():
                    yield f"data: {json.dumps(normalized_chunk)}\n\n"
                yield "data: [DONE]\n\n"

        except Exception as e:
            if typed_mode:
                error_payload = {
                    "type": "error",
                    "error": {"message": str(e), "type": type(e).__name__},
                }
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield f"data: {json.dumps(stream_normalizer.build_done_payload())}\n\n"
            else:
                for normalized_chunk in stream_normalizer.flush():
                    yield f"data: {json.dumps(normalized_chunk)}\n\n"
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
