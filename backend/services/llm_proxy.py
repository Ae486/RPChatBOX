"""LLM Proxy Service - forwards requests to upstream LLM APIs."""
import json
import time
import uuid
from typing import AsyncIterator

import httpx

from config import get_settings
from models.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ProviderConfig,
    Choice,
    ChatMessage,
    Delta,
    Usage,
)
from services.request_normalization import get_request_normalization_service
from services.stream_normalization import StreamNormalizationService


class LLMProxyService:
    """Service for proxying LLM API requests."""

    # Provider-specific API path mappings
    PROVIDER_PATHS = {
        "openai": "/chat/completions",
        "deepseek": "/chat/completions",
        "gemini": "/chat/completions",  # Using OpenAI-compatible endpoint
        "claude": "/messages",
    }

    def __init__(self):
        self.settings = get_settings()

    def _get_upstream_url(self, provider: ProviderConfig) -> str:
        """Build upstream API URL based on provider config."""
        base_url = provider.api_url.rstrip("/")

        # Handle URL suffix rules (matching Flutter's ApiUrlHelper)
        if base_url.endswith("#"):
            # Force mode: use URL as-is (remove #)
            return base_url[:-1]

        # Auto-append path if not present
        path = self.PROVIDER_PATHS.get(provider.type, "/chat/completions")
        if not base_url.endswith(path):
            # Check if /v1 is needed
            if "/v1" not in base_url and provider.type in ("openai", "deepseek"):
                base_url = f"{base_url}/v1"
            return f"{base_url}{path}"

        return base_url

    def _build_headers(self, provider: ProviderConfig) -> dict[str, str]:
        """Build request headers for upstream API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}",
        }
        # Merge custom headers
        headers.update(provider.custom_headers)
        return headers

    def _build_request_body(self, request: ChatCompletionRequest) -> dict:
        """Build request body for upstream API."""
        request = get_request_normalization_service().normalize(request)
        body = {
            "model": request.model,
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "stream": request.stream,
        }

        # Add optional parameters if provided
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            body["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            body["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            body["stop"] = request.stop

        # Provider-specific extensions
        if request.include_reasoning is not None:
            body["include_reasoning"] = request.include_reasoning
        if request.extra_body:
            body["extra_body"] = request.extra_body

        return body

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Handle non-streaming chat completion."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        url = self._get_upstream_url(request.provider)
        headers = self._build_headers(request.provider)
        body = self._build_request_body(request)
        body["stream"] = False

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                self.settings.llm_request_timeout,
                connect=self.settings.llm_connect_timeout,
            ),
            proxy=None,  # 禁用系统代理
        ) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        # Convert to our response format
        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            created=data.get("created", int(time.time())),
            model=data.get("model", request.model),
            choices=[
                Choice(
                    index=c.get("index", 0),
                    message=ChatMessage(**c["message"]) if "message" in c else None,
                    finish_reason=c.get("finish_reason"),
                )
                for c in data.get("choices", [])
            ],
            usage=Usage(**data["usage"]) if "usage" in data else None,
        )

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Handle streaming chat completion, yielding SSE formatted strings."""
        if not request.provider:
            raise ValueError("Provider configuration is required")

        normalized_request = get_request_normalization_service().normalize(request)
        url = self._get_upstream_url(request.provider)
        headers = self._build_headers(request.provider)
        body = self._build_request_body(normalized_request)
        body["stream"] = True
        stream_normalizer = StreamNormalizationService(
            model=normalized_request.model,
            provider_type=normalized_request.provider.type,
        )
        typed_mode = normalized_request.stream_event_mode == "typed"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                self.settings.llm_request_timeout,
                connect=self.settings.llm_connect_timeout,
            ),
            proxy=None,  # 禁用系统代理
        ) as client:
            async with client.stream(
                "POST", url, headers=headers, json=body
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # Pass through SSE format
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        if data_str.strip() == "[DONE]":
                            if typed_mode:
                                yield f"data: {json.dumps(stream_normalizer.build_done_payload())}\n\n"
                            else:
                                for normalized_chunk in stream_normalizer.flush():
                                    yield f"data: {json.dumps(normalized_chunk)}\n\n"
                                yield "data: [DONE]\n\n"
                            break

                        # Parse and re-emit to ensure format consistency
                        try:
                            data = json.loads(data_str)
                            events = stream_normalizer.extract_events(data)
                            if typed_mode:
                                for payload in stream_normalizer.emit_typed_payloads(events):
                                    yield f"data: {json.dumps(payload)}\n\n"
                            else:
                                for normalized_chunk in stream_normalizer.emit_compatible_chunks(
                                    events,
                                    template=data,
                                ):
                                    yield f"data: {json.dumps(normalized_chunk)}\n\n"
                        except json.JSONDecodeError:
                            # Pass through as-is if not valid JSON
                            yield f"data: {data_str}\n\n"
                    elif line.strip():
                        # Non-empty, non-data line (might be event: or comment)
                        # Skip these as per constraint SSE-4
                        pass


# Singleton instance
_llm_proxy_service: LLMProxyService | None = None


def get_llm_proxy_service() -> LLMProxyService:
    """Get LLM proxy service instance."""
    global _llm_proxy_service
    if _llm_proxy_service is None:
        _llm_proxy_service = LLMProxyService()
    return _llm_proxy_service
