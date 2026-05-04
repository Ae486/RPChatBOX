"""Shared provider/model resolution and LLM execution helpers for story runtime."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from models.chat import ChatCompletionRequest, ChatMessage
from services.litellm_service import LiteLLMService, get_litellm_service
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service


class StoryLlmGateway:
    """Thin gateway over the existing backend LLM stack."""

    def __init__(self, *, llm_service: LiteLLMService | None = None) -> None:
        self._llm_service = llm_service or get_litellm_service()

    async def complete_text(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
    ) -> str:
        request = self.build_request(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
        )
        response = await self._llm_service.chat_completion(request)
        choices = response.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = (message or {}).get("content")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return str(content or "")

    async def complete_text_with_usage(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
    ) -> tuple[str, dict[str, Any]]:
        request = self.build_request(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
        )
        response = await self._llm_service.chat_completion(request)
        choices = response.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = (message or {}).get("content")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        else:
            text = str(content or "")
        usage = response.get("usage")
        return text, dict(usage or {}) if isinstance(usage, dict) else {}

    def stream_text(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
    ) -> AsyncIterator[str]:
        request = self.build_request(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
        )
        return self._llm_service.chat_completion_stream(request)

    def build_request(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        stream: bool,
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
    ) -> ChatCompletionRequest:
        provider, model_name = self._resolve_provider_and_model(
            model_id=model_id,
            provider_id=provider_id,
        )
        return ChatCompletionRequest(
            model=model_name,
            model_id=model_id,
            provider_id=provider_id,
            provider=provider,
            messages=messages,
            stream=stream,
            stream_event_mode="typed" if stream else None,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
            enable_tools=False,
        )

    @staticmethod
    def extract_json_object(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if not stripped:
            raise ValueError("Empty model response")
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(stripped[start : end + 1])

    @staticmethod
    def _resolve_provider_and_model(*, model_id: str, provider_id: str | None):
        model_entry = get_model_registry_service().get_entry(model_id)
        if model_entry is None or not model_entry.is_enabled:
            raise ValueError(f"Model not found or disabled: {model_id}")
        resolved_provider_id = provider_id or model_entry.provider_id
        provider_entry = get_provider_registry_service().get_entry(resolved_provider_id)
        if provider_entry is None or not provider_entry.is_enabled:
            raise ValueError(f"Provider not found or disabled: {resolved_provider_id}")
        return provider_entry.to_runtime_provider(), model_entry.model_name
