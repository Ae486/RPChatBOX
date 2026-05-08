"""Shared provider/model resolution and LLM execution helpers for story runtime."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from models.chat import ChatCompletionRequest, ChatMessage
from services.litellm_service import LiteLLMService, get_litellm_service
from services.model_capability_service import supports_function_calling
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
        message, _usage = await self.complete_message_with_usage(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
        )
        return self._message_text(message)

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
        message, usage = await self.complete_message_with_usage(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
        )
        return self._message_text(message), usage

    async def complete_message_with_usage(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
        enable_tools: bool | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        request = self.build_request(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            enable_tools=enable_tools,
        )
        response = await self._llm_service.chat_completion(request)
        response_dict = self._coerce_response_dict(response)
        choices = response_dict.get("choices") or []
        message = choices[0].get("message") if choices else {}
        usage = response_dict.get("usage")
        return (
            dict(message or {}) if isinstance(message, dict) else {},
            dict(usage or {}) if isinstance(usage, dict) else {},
        )

    async def complete_with_tools(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self.build_request(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            include_reasoning=include_reasoning,
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            enable_tools=True,
        )
        response = await self._llm_service.chat_completion(request)
        return self._coerce_response_dict(response)

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
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
        enable_tools: bool | None = None,
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
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            enable_tools=enable_tools if enable_tools is not None else False,
        )

    def supports_tools(self, *, model_id: str, provider_id: str | None) -> bool:
        model_entry = get_model_registry_service().get_entry(model_id)
        if model_entry is not None:
            capability_profile = model_entry.capability_profile
            if (
                capability_profile is not None
                and capability_profile.supports_function_calling is not None
            ):
                return bool(capability_profile.supports_function_calling)
            return "tool" in model_entry.capabilities
        provider, model_name = self._resolve_provider_and_model(
            model_id=model_id,
            provider_id=provider_id,
        )
        return supports_function_calling(provider.type, model_name)

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return str(content or "")

    @staticmethod
    def _coerce_response_dict(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            return response.model_dump(exclude_none=True)
        if isinstance(response, dict):
            return response
        raise TypeError(f"Unsupported chat completion response type: {type(response)!r}")

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
