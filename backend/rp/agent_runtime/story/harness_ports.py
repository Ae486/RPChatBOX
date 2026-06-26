"""Story-owned harness injection-port contracts over the generic runtime graph substrate.

INPUT: story harness injection points for model and tool execution.
OUTPUT: runtime-checkable protocol contracts for harness injection.
POS: story-zone harness injection-port contracts; setup-free; imports kernel only.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..kernel.runtime_tool_contracts import RuntimeToolCall, RuntimeToolResult


@runtime_checkable
class RuntimeToolExecutor(Protocol):
    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        ...

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        ...


@runtime_checkable
class RuntimeModelGateway(Protocol):
    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        ...
