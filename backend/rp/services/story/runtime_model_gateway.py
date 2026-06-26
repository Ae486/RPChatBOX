"""Story-owned runtime model gateway adapter for the harness.

INPUT: harness request dict with messages, tools, tool_choice, and round_no.
OUTPUT: dict completion response from StoryLlmGateway.complete_with_tools.
POS: story-zone adapter; converts request messages to ChatMessage; no setup imports.
"""

from __future__ import annotations

from typing import Any

from models.chat import ChatMessage

from .llm_gateway import StoryLlmGateway


class RuntimeStoryModelGateway:
    """Thin production adapter for the runtime harness model port."""

    def __init__(
        self,
        *,
        llm_gateway: StoryLlmGateway,
        model_id: str,
        provider_id: str | None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        include_reasoning: bool | None = None,
    ) -> None:
        self._llm_gateway = llm_gateway
        self._model_id = model_id
        self._provider_id = provider_id
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._include_reasoning = include_reasoning
        self.call_count = 0

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        messages = [
            ChatMessage.model_validate(dict(item))
            for item in request.get("messages", [])
        ]
        tools = list(request.get("tools") or [])
        tool_choice = request.get("tool_choice")
        return await self._llm_gateway.complete_with_tools(
            model_id=self._model_id,
            provider_id=self._provider_id,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            include_reasoning=self._include_reasoning,
            extra_body={"parallel_tool_calls": False},
        )
