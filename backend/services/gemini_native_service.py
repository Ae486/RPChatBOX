"""Gemini native backend service using the official Google GenAI SDK."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from config import get_settings
from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig
from services.request_normalization import get_request_normalization_service
from services.stream_normalization import StreamNormalizationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _GeminiSdk:
    genai: Any
    types: Any


class GeminiNativeService:
    """Use the official Gemini SDK when the provider is a native Gemini config."""

    def __init__(self, settings: Any | None = None):
        self.settings = settings or get_settings()
        self._clients: dict[tuple[str, str], Any] = {}

    def supports_request(self, request: ChatCompletionRequest) -> bool:
        provider = request.provider
        if provider is None or provider.type != "gemini":
            return False
        return self._supports_provider(provider)

    async def chat_completion(self, request: ChatCompletionRequest) -> dict[str, Any]:
        if not request.provider:
            raise ValueError("Provider configuration is required")

        normalized_request = get_request_normalization_service().normalize(request)
        sdk = self._get_sdk()
        client = self._get_client(normalized_request.provider, sdk=sdk)
        contents, config = self._build_generate_content_inputs(normalized_request, sdk=sdk)

        response = await client.aio.models.generate_content(
            model=normalized_request.model,
            contents=contents,
            config=config,
        )
        response_dict = self._coerce_to_dict(response)
        return self._build_openai_compatible_response(
            response_dict,
            model=normalized_request.model,
            provider_type=normalized_request.provider.type,
        )

    async def chat_completion_stream(
        self,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[str]:
        if not request.provider:
            raise ValueError("Provider configuration is required")

        normalized_request = get_request_normalization_service().normalize(request)
        sdk = self._get_sdk()
        client = self._get_client(normalized_request.provider, sdk=sdk)
        contents, config = self._build_generate_content_inputs(normalized_request, sdk=sdk)
        stream_normalizer = StreamNormalizationService(
            model=normalized_request.model,
            provider_type=normalized_request.provider.type,
        )
        typed_mode = normalized_request.stream_event_mode == "typed"

        try:
            response_stream = await client.aio.models.generate_content_stream(
                model=normalized_request.model,
                contents=contents,
                config=config,
            )

            async for chunk in response_stream:
                chunk_dict = self._coerce_to_dict(chunk)
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
        except Exception as exc:
            if typed_mode:
                error_payload = {
                    "type": "error",
                    "error": {"message": str(exc), "type": type(exc).__name__},
                }
                yield f"data: {json.dumps(error_payload)}\n\n"
                yield f"data: {json.dumps(stream_normalizer.build_done_payload())}\n\n"
            else:
                for normalized_chunk in stream_normalizer.flush():
                    yield f"data: {json.dumps(normalized_chunk)}\n\n"
                error_data = {"error": {"message": str(exc), "type": type(exc).__name__}}
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: [DONE]\n\n"

    def _supports_provider(self, provider: ProviderConfig) -> bool:
        parsed = urlparse(provider.api_url.rstrip("/"))
        if parsed.scheme not in {"https", ""}:
            return False
        if "/openai" in parsed.path.lower():
            return False
        host = parsed.netloc.lower()
        return (
            "generativelanguage.googleapis.com" in host
            or host.endswith("googleapis.com")
        )

    def _get_client(self, provider: ProviderConfig, *, sdk: _GeminiSdk) -> Any:
        api_version = self._extract_api_version(provider.api_url)
        cache_key = (provider.api_key, api_version)
        client = self._clients.get(cache_key)
        if client is not None:
            return client

        http_options = sdk.types.HttpOptions(
            api_version=api_version,
            timeout=int(self.settings.llm_request_timeout * 1000),
        )
        client = sdk.genai.Client(
            api_key=provider.api_key,
            http_options=http_options,
        )
        self._clients[cache_key] = client
        return client

    def _build_generate_content_inputs(
        self,
        request: ChatCompletionRequest,
        *,
        sdk: _GeminiSdk,
    ) -> tuple[list[Any], Any]:
        contents: list[Any] = []
        system_fragments: list[str] = []

        for message in request.messages:
            if message.role == "system":
                system_text = self._message_to_plain_text(message)
                if system_text:
                    system_fragments.append(system_text)
                continue

            parts = self._message_to_parts(message, sdk=sdk)
            if not parts:
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append(sdk.types.Content(role=role, parts=parts))

        config_kwargs: dict[str, Any] = {}
        if request.temperature is not None:
            config_kwargs["temperature"] = request.temperature
        if request.top_p is not None:
            config_kwargs["top_p"] = request.top_p
        if request.max_tokens is not None:
            config_kwargs["max_output_tokens"] = request.max_tokens

        stop_sequences = self._normalize_stop_sequences(request.stop)
        if stop_sequences:
            config_kwargs["stop_sequences"] = stop_sequences

        if system_fragments:
            config_kwargs["system_instruction"] = "\n\n".join(system_fragments)

        thinking_config = self._build_thinking_config(request, sdk=sdk)
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config

        return contents, sdk.types.GenerateContentConfig(**config_kwargs)

    def _build_thinking_config(
        self,
        request: ChatCompletionRequest,
        *,
        sdk: _GeminiSdk,
    ) -> Any | None:
        google_extra = ((request.extra_body or {}).get("google") or {})
        raw_config = (google_extra.get("thinking_config") or {})
        kwargs: dict[str, Any] = {}

        include_thoughts = raw_config.get("include_thoughts")
        if include_thoughts is None and request.include_reasoning:
            include_thoughts = True
        if include_thoughts is not None:
            kwargs["include_thoughts"] = bool(include_thoughts)

        if raw_config.get("thinking_budget") is not None:
            kwargs["thinking_budget"] = raw_config["thinking_budget"]
        if raw_config.get("thinking_level") is not None:
            kwargs["thinking_level"] = raw_config["thinking_level"]

        if not kwargs:
            return None
        return sdk.types.ThinkingConfig(**kwargs)

    def _message_to_parts(self, message: ChatMessage, *, sdk: _GeminiSdk) -> list[Any]:
        content = message.content
        if isinstance(content, str):
            return [sdk.types.Part.from_text(text=content)] if content else []

        if not isinstance(content, list):
            fallback_text = self._message_to_plain_text(message)
            return [sdk.types.Part.from_text(text=fallback_text)] if fallback_text else []

        parts: list[Any] = []
        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = str(item.get("type") or "")
            if item_type in {"text", "input_text", "output_text"}:
                text = str(item.get("text") or "")
                if text:
                    parts.append(sdk.types.Part.from_text(text=text))
                continue

            if item_type == "image_url":
                image_url = item.get("image_url")
                url = (
                    image_url.get("url")
                    if isinstance(image_url, dict)
                    else str(image_url or "")
                )
                image_part = self._build_image_part(url, sdk=sdk)
                if image_part is not None:
                    parts.append(image_part)
                continue

            text = str(item.get("text") or item.get("content") or "")
            if text:
                parts.append(sdk.types.Part.from_text(text=text))

        return parts

    def _build_image_part(self, url: str, *, sdk: _GeminiSdk) -> Any | None:
        if not url:
            return None
        if url.startswith("data:"):
            mime_type, raw_bytes = self._parse_data_url(url)
            return sdk.types.Part.from_bytes(data=raw_bytes, mime_type=mime_type)
        return None

    def _build_openai_compatible_response(
        self,
        response_dict: dict[str, Any],
        *,
        model: str,
        provider_type: str,
    ) -> dict[str, Any]:
        normalizer = StreamNormalizationService(model=model, provider_type=provider_type)
        chunks = normalizer.normalize_chunk(response_dict)
        chunks.extend(normalizer.flush())

        text_fragments: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for chunk in chunks:
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta")
            if not isinstance(delta, dict):
                continue

            content = delta.get("content")
            if isinstance(content, str) and content:
                text_fragments.append(content)

            chunk_tool_calls = delta.get("tool_calls")
            if isinstance(chunk_tool_calls, list):
                tool_calls.extend(
                    item for item in chunk_tool_calls if isinstance(item, dict)
                )

        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(text_fragments),
        }
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "id": response_dict.get("response_id", response_dict.get("id", "gemini-native")),
            "object": "chat.completion",
            "created": response_dict.get("create_time", 0),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": self._extract_finish_reason(response_dict),
                }
            ],
            "usage": self._extract_usage(response_dict),
        }

    @staticmethod
    def _extract_finish_reason(response_dict: dict[str, Any]) -> str | None:
        candidates = response_dict.get("candidates")
        if isinstance(candidates, list) and candidates:
            candidate = candidates[0]
            if isinstance(candidate, dict):
                finish_reason = candidate.get("finish_reason") or candidate.get("finishReason")
                return str(finish_reason).lower() if finish_reason else None
        return None

    @staticmethod
    def _extract_usage(response_dict: dict[str, Any]) -> dict[str, int] | None:
        usage = response_dict.get("usage_metadata") or response_dict.get("usageMetadata")
        if not isinstance(usage, dict):
            return None
        prompt_tokens = int(usage.get("prompt_token_count") or usage.get("promptTokenCount") or 0)
        completion_tokens = int(
            usage.get("candidates_token_count")
            or usage.get("candidatesTokenCount")
            or usage.get("completion_token_count")
            or usage.get("completionTokenCount")
            or 0
        )
        total_tokens = int(usage.get("total_token_count") or usage.get("totalTokenCount") or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _extract_api_version(api_url: str) -> str:
        lower = api_url.lower()
        if "/v1alpha" in lower:
            return "v1alpha"
        if "/v1beta" in lower:
            return "v1beta"
        return "v1"

    @staticmethod
    def _normalize_stop_sequences(stop: str | list[str] | None) -> list[str] | None:
        if stop is None:
            return None
        if isinstance(stop, str):
            return [stop]
        return [item for item in stop if isinstance(item, str) and item]

    @staticmethod
    def _message_to_plain_text(message: ChatMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        fragments.append(str(text))
            return "\n".join(fragment for fragment in fragments if fragment)

        extras: list[str] = []
        if message.tool_calls:
            extras.append(json.dumps(message.tool_calls, ensure_ascii=False))
        if message.function_call:
            extras.append(json.dumps(message.function_call, ensure_ascii=False))
        if message.name:
            extras.append(message.name)
        return "\n".join(extras)

    @staticmethod
    def _parse_data_url(url: str) -> tuple[str, bytes]:
        header, encoded = url.split(",", 1)
        mime_type = header[5:].split(";")[0] or "application/octet-stream"
        return mime_type, base64.b64decode(encoded)

    @staticmethod
    def _coerce_to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(exclude_none=True)

        model_dump_json = getattr(value, "model_dump_json", None)
        if callable(model_dump_json):
            return json.loads(model_dump_json(exclude_none=True))

        to_json_dict = getattr(value, "to_json_dict", None)
        if callable(to_json_dict):
            return to_json_dict()

        raise TypeError(f"Unsupported Gemini SDK response type: {type(value)!r}")

    @staticmethod
    def _get_sdk() -> _GeminiSdk:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "google-genai is not installed; Gemini native backend route unavailable"
            ) from exc
        return _GeminiSdk(genai=genai, types=types)


_gemini_native_service: GeminiNativeService | None = None


def get_gemini_native_service() -> GeminiNativeService:
    """Get cached Gemini native service instance."""
    global _gemini_native_service
    if _gemini_native_service is None:
        _gemini_native_service = GeminiNativeService()
    return _gemini_native_service
