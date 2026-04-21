"""Tool-augmented chat completion with streaming typed events."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator

from models.chat import ChatCompletionRequest, ChatMessage
from services.mcp_manager import McpManager, get_mcp_manager

logger = logging.getLogger(__name__)

# Maximum number of tool-call rounds to prevent infinite loops.
_MAX_TOOL_ROUNDS = 10


class ToolRuntimeService:
    """Self-managed tool loop: model → tool_call → execute → result → model.

    Each round streams thinking/text deltas to the client in real time.
    When the model returns tool_calls, this service executes them via
    McpManager and feeds the results back, then starts a new LLM round.

    Typed SSE events emitted:
    - thinking_delta / text_delta (pass-through from LLM)
    - tool_call   (model declared intent)
    - tool_started (execution begins)
    - tool_result  (execution succeeded)
    - tool_error   (execution failed)
    - error / done (terminal)
    """

    def __init__(self, *, mcp_manager: McpManager | None = None):
        self._mcp = mcp_manager or get_mcp_manager()

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        llm_service: Any,
    ) -> dict[str, Any]:
        """Run the tool loop for non-streaming requests."""
        messages = [msg.model_copy() for msg in request.messages]
        tools_defs = self._mcp.get_openai_tool_definitions()
        usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for round_idx in range(_MAX_TOOL_ROUNDS):
            round_request = request.model_copy(
                update={
                    "messages": messages,
                    "tools": tools_defs,
                    "tool_choice": "auto",
                    "stream": False,
                }
            )

            response_dict = self._coerce_response_dict(
                await llm_service.chat_completion(round_request)
            )
            self._accumulate_usage(usage_totals, response_dict.get("usage"))

            choice = self._get_first_choice(response_dict)
            if choice is None:
                response_dict["usage"] = usage_totals
                return response_dict

            message_payload = choice.get("message") or {}
            raw_tool_calls = message_payload.get("tool_calls") or []
            tool_calls = [call for call in raw_tool_calls if isinstance(call, dict)]

            if not tool_calls:
                response_dict["usage"] = usage_totals
                return response_dict

            messages.append(self._build_assistant_tool_message(message_payload, tool_calls))
            tool_results_messages = await self._execute_tool_calls(tool_calls)
            messages.extend(tool_results_messages)

            logger.info(
                "[TOOL] round=%d tool_calls=%d continuing",
                round_idx + 1,
                len(tool_calls),
            )

        raise RuntimeError(f"Tool loop exceeded {_MAX_TOOL_ROUNDS} rounds")

    async def chat_completion_stream(
        self,
        request: ChatCompletionRequest,
        *,
        llm_service: Any,
    ) -> AsyncIterator[str]:
        """Run the tool loop, yielding typed SSE lines.

        ``llm_service`` must expose ``chat_completion_stream(request)``
        returning ``AsyncIterator[str]`` of ``data: {...}\\n\\n`` lines.
        """
        messages = [msg.model_copy() for msg in request.messages]
        tools_defs = self._mcp.get_openai_tool_definitions()
        logger.info(
            "[TOOL_STREAM] start model=%s model_id=%s provider_id=%s message_count=%s tool_defs=%s",
            request.model,
            request.model_id or "",
            request.provider_id or "",
            len(messages),
            len(tools_defs),
        )

        for round_idx in range(_MAX_TOOL_ROUNDS):
            logger.info(
                "[TOOL_STREAM] round_start round=%s model=%s message_count=%s",
                round_idx + 1,
                request.model,
                len(messages),
            )
            # Build request for this round
            round_request = request.model_copy(
                update={
                    "messages": messages,
                    "tools": tools_defs,
                    "tool_choice": "auto",
                    "stream": True,
                    "stream_event_mode": "typed",
                }
            )

            # Accumulate this round's full response for context
            accumulated_tool_calls: dict[int, dict[str, Any]] = {}
            accumulated_text = ""
            saw_done = False
            async for line in llm_service.chat_completion_stream(round_request):
                payload = self._parse_sse_payload(line)
                if payload is None:
                    continue

                event_type = payload.get("type")

                if event_type == "done":
                    # Don't forward yet — check if we need another round
                    saw_done = True
                    logger.info(
                        "[TOOL_STREAM] round_done_signal round=%s text_chars=%s tool_call_slots=%s",
                        round_idx + 1,
                        len(accumulated_text),
                        len(accumulated_tool_calls),
                    )
                    break

                if event_type in ("thinking_delta", "text_delta"):
                    if event_type == "text_delta":
                        accumulated_text += payload.get("delta", "")
                    yield line
                    continue

                if event_type == "tool_call":
                    raw_calls = payload.get("tool_calls", [])
                    self._merge_stream_tool_calls(accumulated_tool_calls, raw_calls)
                    logger.info(
                        "[TOOL_STREAM] round_tool_call round=%s raw_calls=%s accumulated_slots=%s",
                        round_idx + 1,
                        len(raw_calls) if isinstance(raw_calls, list) else 0,
                        len(accumulated_tool_calls),
                    )
                    # Forward tool_call event to frontend (pending bubbles)
                    yield line
                    continue

                if event_type == "error":
                    logger.error(
                        "[TOOL_STREAM] round_error_event round=%s payload=%s",
                        round_idx + 1,
                        payload,
                    )
                    yield line
                    yield self._emit_done()
                    return

                # Pass through other events
                yield line

            # Round finished. Were there tool calls?
            finalized_tool_calls = self._finalize_stream_tool_calls(accumulated_tool_calls)
            logger.info(
                "[TOOL_STREAM] round_end round=%s saw_done=%s text_chars=%s finalized_tool_calls=%s",
                round_idx + 1,
                saw_done,
                len(accumulated_text),
                len(finalized_tool_calls),
            )
            if not finalized_tool_calls:
                # No tools needed — stream is complete
                logger.info(
                    "[TOOL_STREAM] complete_no_tools round=%s final_text_chars=%s",
                    round_idx + 1,
                    len(accumulated_text),
                )
                yield self._emit_done()
                return

            # Execute tool calls and emit lifecycle events
            tool_results_messages = []

            for call in finalized_tool_calls:
                call_id = self._tool_call_id(call)
                tool_name = self._tool_name(call)

                yield self._emit_typed(
                    {"type": "tool_started", "call_id": call_id, "tool_name": tool_name}
                )

                logger.info(
                    "[TOOL_STREAM] tool_start round=%s call_id=%s tool_name=%s",
                    round_idx + 1,
                    call_id,
                    tool_name,
                )
                result = await self._call_tool(call)

                if result["success"]:
                    logger.info(
                        "[TOOL_STREAM] tool_success round=%s call_id=%s tool_name=%s content_chars=%s",
                        round_idx + 1,
                        call_id,
                        tool_name,
                        len(str(result.get("content") or "")),
                    )
                    yield self._emit_typed(
                        {
                            "type": "tool_result",
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "result": result["content"],
                        }
                    )
                else:
                    logger.warning(
                        "[TOOL_STREAM] tool_failure round=%s call_id=%s tool_name=%s error_code=%s content_chars=%s",
                        round_idx + 1,
                        call_id,
                        tool_name,
                        result.get("error_code"),
                        len(str(result.get("content") or "")),
                    )
                    yield self._emit_typed(
                        {
                            "type": "tool_error",
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "error": result["content"],
                        }
                    )

                tool_results_messages.append(
                    ChatMessage(
                        role="tool",
                        name=tool_name,
                        tool_call_id=call_id,
                        content=result["content"],
                    )
                )

            # Append assistant message with tool_calls + tool results to context
            messages.append(
                self._build_assistant_tool_message(
                    {"content": accumulated_text or None},
                    finalized_tool_calls,
                )
            )
            messages.extend(tool_results_messages)

            logger.info(
                "[TOOL] round=%d tool_calls=%d continuing",
                round_idx + 1,
                len(finalized_tool_calls),
            )

        # Max rounds exhausted
        logger.error(
            "[TOOL_STREAM] max_rounds_exceeded model=%s model_id=%s provider_id=%s",
            request.model,
            request.model_id or "",
            request.provider_id or "",
        )
        yield self._emit_typed(
            {
                "type": "error",
                "error": {
                    "message": f"Tool loop exceeded {_MAX_TOOL_ROUNDS} rounds",
                    "type": "max_rounds_exceeded",
                },
            }
        )
        yield self._emit_done()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[ChatMessage]:
        tool_messages: list[ChatMessage] = []
        for call in tool_calls:
            result = await self._call_tool(call)
            tool_messages.append(
                ChatMessage(
                    role="tool",
                    name=self._tool_name(call),
                    tool_call_id=self._tool_call_id(call),
                    content=result["content"],
                )
            )
        return tool_messages

    async def _call_tool(self, call: dict[str, Any]) -> dict[str, Any]:
        return await self._mcp.call_tool_by_qualified_name(
            qualified_name=self._tool_name(call),
            arguments=self._tool_arguments(call),
        )

    @staticmethod
    def _coerce_response_dict(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            return response.model_dump(exclude_none=True)
        if isinstance(response, dict):
            return response
        raise TypeError(f"Unsupported chat completion response type: {type(response)!r}")

    @staticmethod
    def _get_first_choice(response: dict[str, Any]) -> dict[str, Any] | None:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        return choice if isinstance(choice, dict) else None

    @staticmethod
    def _accumulate_usage(
        totals: dict[str, int],
        usage: Any,
    ) -> None:
        if not isinstance(usage, dict):
            return
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or (prompt_tokens + completion_tokens)
        )
        totals["prompt_tokens"] += prompt_tokens
        totals["completion_tokens"] += completion_tokens
        totals["total_tokens"] += total_tokens

    @classmethod
    def _build_assistant_tool_message(
        cls,
        message_payload: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> ChatMessage:
        content = message_payload.get("content")
        if content is None and tool_calls:
            content = ""
        return ChatMessage(
            role="assistant",
            content=content,
            tool_calls=[cls._normalize_tool_call(call) for call in tool_calls],
        )

    @staticmethod
    def _normalize_tool_call(call: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(call)
        normalized["id"] = ToolRuntimeService._tool_call_id(call)
        normalized["type"] = str(normalized.get("type") or "function")
        function = normalized.get("function")
        normalized["function"] = function if isinstance(function, dict) else {}
        return normalized

    @staticmethod
    def _merge_stream_tool_calls(
        accumulators: dict[int, dict[str, Any]],
        raw_calls: Any,
    ) -> None:
        if not isinstance(raw_calls, list):
            return

        for position, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, dict):
                continue

            index = raw_call.get("index")
            key = index if isinstance(index, int) else position
            current = accumulators.setdefault(
                key,
                {"type": "function", "function": {}},
            )

            for field, value in raw_call.items():
                if field in {"index", "function"}:
                    continue
                if value is None:
                    continue
                if isinstance(value, str) and not value:
                    continue
                current[field] = value

            raw_function = raw_call.get("function")
            if not isinstance(raw_function, dict):
                continue

            current_function = current.setdefault("function", {})

            for field, value in raw_function.items():
                if field == "arguments":
                    if isinstance(value, str):
                        existing = current_function.get("arguments")
                        if isinstance(existing, str):
                            current_function["arguments"] = existing + value
                        elif existing is None:
                            current_function["arguments"] = value
                        else:
                            current_function["arguments"] = value
                    elif value is not None:
                        current_function["arguments"] = value
                    continue

                if value is None:
                    continue
                if isinstance(value, str) and not value:
                    continue
                current_function[field] = value

    @staticmethod
    def _finalize_stream_tool_calls(
        accumulators: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [accumulators[key] for key in sorted(accumulators)]

    @staticmethod
    def _tool_call_id(call: dict[str, Any]) -> str:
        existing = call.get("id")
        if existing:
            return str(existing)
        generated = f"call_{uuid.uuid4().hex[:8]}"
        call["id"] = generated
        return generated

    @classmethod
    def _tool_name(cls, call: dict[str, Any]) -> str:
        function = call.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return ""

    @classmethod
    def _tool_arguments(cls, call: dict[str, Any]) -> dict[str, Any]:
        function = call.get("function")
        raw_args = function.get("arguments", "{}") if isinstance(function, dict) else "{}"
        if isinstance(raw_args, dict):
            return raw_args
        if not isinstance(raw_args, str):
            return {}
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_sse_payload(line: str) -> dict[str, Any] | None:
        if not line.startswith("data: "):
            return None
        data_str = line[6:].strip()
        if not data_str or data_str == "[DONE]":
            return None
        try:
            return json.loads(data_str)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _emit_typed(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    @staticmethod
    def _emit_done() -> str:
        return f"data: {json.dumps({'type': 'done'})}\n\n"
