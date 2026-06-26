"""Story-owned harness tool-loop hooks over the generic runtime graph substrate.

INPUT: story harness tool-loop lifecycle events.
OUTPUT: runtime-checkable hook contracts and a null implementation.
POS: story-zone harness tool-loop hooks; setup-free; imports kernel only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..kernel.runtime_tool_contracts import RuntimeToolCall, RuntimeToolResult


@runtime_checkable
class RuntimeToolLoopHooks(Protocol):
    def before_tool_call(self, call: RuntimeToolCall) -> None:
        ...

    def after_tool_result(self, result: RuntimeToolResult) -> None:
        ...

    def on_tool_error(self, call: RuntimeToolCall, error: BaseException) -> None:
        ...

    def on_cancellation(self) -> None:
        ...


class NullToolLoopHooks:
    def before_tool_call(self, call: RuntimeToolCall) -> None:
        return None

    def after_tool_result(self, result: RuntimeToolResult) -> None:
        return None

    def on_tool_error(self, call: RuntimeToolCall, error: BaseException) -> None:
        return None

    def on_cancellation(self) -> None:
        return None
