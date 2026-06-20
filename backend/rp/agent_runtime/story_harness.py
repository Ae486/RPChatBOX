"""Story-owned test harness over the generic runtime graph substrate.

INPUT: a scripted model response queue plus a turn goal string.
OUTPUT: a frozen StoryHarnessResult with status and normalized tool results.
POS: test-only story-runtime harness substrate; no setup-agent imports.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .graph import build_runtime_graph
from .runtime_tool_contracts import RuntimeToolCall, RuntimeToolResult
from .state import RpAgentRunState


@dataclass(frozen=True)
class StoryHarnessProfile:
    """Minimal story-owned profile for the S0 harness substrate."""

    profile_id: str = "story-harness-test-minimal"
    visible_tool_names: tuple[str, ...] = ("noop",)
    max_rounds: int = 4


TEST_MINIMAL_PROFILE = StoryHarnessProfile()


@dataclass(frozen=True)
class StoryHarnessResult:
    succeeded: bool
    status: str
    tool_results: list[RuntimeToolResult]


class _ScriptedLLM:
    def __init__(self) -> None:
        self._responses: list[dict[str, Any]] = []
        self.call_count = 0

    def set_responses(self, responses: list[dict[str, Any]]) -> None:
        self._responses = [dict(response) for response in responses]
        self.call_count = 0

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._responses:
            raise RuntimeError("StoryHarness scripted LLM queue is empty.")
        self.call_count += 1
        return self._responses.pop(0)

    async def chat_completion_stream(self, request: dict[str, Any]):
        response = await self.chat_completion(request)
        yield response

    def cleanup(self) -> None:
        self._responses.clear()
        self.call_count = 0


class _NoopToolExecutor:
    _REGISTERED_TOOL_NAMES = frozenset({"noop"})

    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        visible = {_normalize_tool_name(name) for name in visible_tool_names}
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Test-only no-op tool for story harness loops.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                },
            }
            for name in sorted(self._REGISTERED_TOOL_NAMES)
            if name in visible
        ]

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        visible = {_normalize_tool_name(name) for name in visible_tool_names}
        normalized_name = _normalize_tool_name(call.tool_name)
        if normalized_name in visible and normalized_name in self._REGISTERED_TOOL_NAMES:
            payload = {"ok": True, "tool_name": normalized_name}
            return RuntimeToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=True,
                content_text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                structured_payload={"content_payload": payload},
            )

        error_payload = {
            "error": {
                "code": "unknown_tool",
                "message": f"Unknown tool requested: {call.tool_name}",
            }
        }
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=False,
            content_text=json.dumps(
                error_payload,
                ensure_ascii=False,
                sort_keys=True,
            ),
            error_code="UNKNOWN_TOOL",
            structured_payload={"error_payload": error_payload["error"]},
        )


class StoryHarness:
    def __init__(self, *, profile: StoryHarnessProfile) -> None:
        self._profile = profile
        self._llm = _ScriptedLLM()
        self._tool_executor = _NoopToolExecutor()

    def tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": f"call_{uuid4().hex}",
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(
                                        dict(args),
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        }

    def final_text(self, text: str) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text,
                    }
                }
            ]
        }

    def set_responses(self, responses: list[dict[str, Any]]) -> None:
        self._llm.set_responses(responses)

    def run(self, *, turn_goal: str) -> StoryHarnessResult:
        graph = build_runtime_graph(
            prepare_input=self._prepare_input,
            derive_turn_goal=self._derive_turn_goal,
            plan_step_slice=self._plan_step_slice,
            build_model_request=self._build_model_request,
            call_model=self._call_model,
            inspect_model_output=self._inspect_model_output,
            execute_tools=self._execute_tools,
            apply_tool_results=self._apply_tool_results,
            assess_progress=self._assess_progress,
            reflect_if_needed=self._reflect_if_needed,
            finalize_success=self._finalize_success,
            finalize_failure=self._finalize_failure,
            route_after_inspect=self._route_after_inspect,
            route_after_assess=self._route_after_assess,
            route_after_reflect=self._route_after_reflect,
        )
        initial_state: RpAgentRunState = {
            "run_id": f"story-harness:{uuid4().hex}",
            "profile_id": self._profile.profile_id,
            "run_kind": "story_harness",
            "status": "initialized",
            "round_no": 0,
            "turn_input": {"turn_goal": turn_goal},
            "turn_goal": {"text": turn_goal},
            "normalized_messages": [],
            "tool_definitions": [],
            "pending_tool_calls": [],
            "tool_invocations": [],
            "tool_results": [],
            "latest_tool_batch": [],
            "assistant_text": "",
            "finish_reason": None,
            "next_action": "derive_turn_goal",
        }
        final_state = asyncio.run(graph.ainvoke(initial_state))
        status = str(final_state.get("status") or "")
        tool_results = [
            RuntimeToolResult.model_validate(item)
            for item in final_state.get("tool_results", [])
        ]
        return StoryHarnessResult(
            succeeded=status == "completed",
            status=status,
            tool_results=tool_results,
        )

    @property
    def model_call_count(self) -> int:
        return self._llm.call_count

    def cleanup(self) -> None:
        self._llm.cleanup()

    def _prepare_input(self, state: RpAgentRunState) -> RpAgentRunState:
        turn_goal = str((state.get("turn_input") or {}).get("turn_goal") or "")
        return {
            "status": "running",
            "round_no": 0,
            "normalized_messages": [{"role": "user", "content": turn_goal}],
        }

    def _derive_turn_goal(self, state: RpAgentRunState) -> RpAgentRunState:
        return {"status": "turn_goal_derived"}

    def _plan_step_slice(self, state: RpAgentRunState) -> RpAgentRunState:
        return {"status": "step_slice_planned"}

    def _build_model_request(self, state: RpAgentRunState) -> RpAgentRunState:
        round_no = int(state.get("round_no") or 0) + 1
        tool_definitions = self._tool_executor.get_openai_tool_definitions(
            visible_tool_names=self._profile.visible_tool_names,
        )
        latest_request = {
            "messages": list(state.get("normalized_messages", [])),
            "tools": tool_definitions,
            "tool_choice": "auto" if tool_definitions else None,
            "round_no": round_no,
        }
        return {
            "status": "model_request_built",
            "round_no": round_no,
            "tool_definitions": tool_definitions,
            "latest_request": latest_request,
        }

    async def _call_model(self, state: RpAgentRunState) -> RpAgentRunState:
        response = await self._llm.chat_completion(
            dict(state.get("latest_request") or {})
        )
        return {"status": "model_called", "latest_response": response}

    def _inspect_model_output(self, state: RpAgentRunState) -> RpAgentRunState:
        message = _response_message(dict(state.get("latest_response") or {}))
        assistant_text = str(message.get("content") or "")
        tool_calls = _runtime_tool_calls_from_message(
            message,
            source_round=int(state.get("round_no") or 0),
        )
        update: RpAgentRunState = {
            "status": "model_inspected",
            "assistant_text": assistant_text,
            "pending_tool_calls": [
                call.model_dump(mode="json", exclude_none=True) for call in tool_calls
            ],
            "next_action": "execute_tools" if tool_calls else "finalize_success",
        }
        if assistant_text and not tool_calls:
            normalized_messages = list(state.get("normalized_messages", []))
            normalized_messages.append(
                {"role": "assistant", "content": assistant_text}
            )
            update["normalized_messages"] = normalized_messages
        return update

    async def _execute_tools(self, state: RpAgentRunState) -> RpAgentRunState:
        aggregated_invocations = list(state.get("tool_invocations", []))
        aggregated_results = list(state.get("tool_results", []))
        latest_batch: list[dict[str, Any]] = []
        for item in state.get("pending_tool_calls", []):
            call = RuntimeToolCall.model_validate(item)
            invocation = call.model_dump(mode="json", exclude_none=True)
            result = await self._tool_executor.execute_tool_call(
                call,
                visible_tool_names=self._profile.visible_tool_names,
            )
            result_payload = result.model_dump(mode="json", exclude_none=True)
            aggregated_invocations.append(invocation)
            latest_batch.append(result_payload)
            aggregated_results.append(result_payload)
        return {
            "status": "tools_executed",
            "tool_invocations": aggregated_invocations,
            "tool_results": aggregated_results,
            "latest_tool_batch": latest_batch,
        }

    def _apply_tool_results(self, state: RpAgentRunState) -> RpAgentRunState:
        normalized_messages = list(state.get("normalized_messages", []))
        tool_calls = [
            RuntimeToolCall.model_validate(item)
            for item in state.get("pending_tool_calls", [])
        ]
        if tool_calls:
            normalized_messages.append(
                {
                    "role": "assistant",
                    "content": state.get("assistant_text") or "",
                    "tool_calls": [_tool_call_to_openai(call) for call in tool_calls],
                }
            )
        for item in state.get("latest_tool_batch", []):
            result = RuntimeToolResult.model_validate(item)
            normalized_messages.append(
                {
                    "role": "tool",
                    "name": result.tool_name,
                    "tool_call_id": result.call_id,
                    "content": result.content_text,
                }
            )
        return {
            "status": "tool_results_applied",
            "normalized_messages": normalized_messages,
            "pending_tool_calls": [],
        }

    def _assess_progress(self, state: RpAgentRunState) -> RpAgentRunState:
        if int(state.get("round_no") or 0) >= self._profile.max_rounds:
            return {
                "status": "assessed",
                "finish_reason": "max_rounds_exceeded",
                "next_action": "finalize_failure",
            }
        return {"status": "assessed", "next_action": "derive_turn_goal"}

    def _reflect_if_needed(self, state: RpAgentRunState) -> RpAgentRunState:
        return {"status": "reflected", "next_action": "derive_turn_goal"}

    def _finalize_success(self, state: RpAgentRunState) -> RpAgentRunState:
        return {
            "status": "completed",
            "finish_reason": state.get("finish_reason") or "assistant_final_text",
        }

    def _finalize_failure(self, state: RpAgentRunState) -> RpAgentRunState:
        return {
            "status": "failed",
            "finish_reason": state.get("finish_reason") or "runtime_failed",
        }

    @staticmethod
    def _route_after_inspect(state: RpAgentRunState) -> str:
        return (
            "execute_tools"
            if state.get("pending_tool_calls")
            else "finalize_success"
        )

    @staticmethod
    def _route_after_assess(state: RpAgentRunState) -> str:
        route = str(state.get("next_action") or "finalize_failure")
        return (
            route
            if route in {"derive_turn_goal", "finalize_failure"}
            else "finalize_failure"
        )

    @staticmethod
    def _route_after_reflect(state: RpAgentRunState) -> str:
        route = str(state.get("next_action") or "derive_turn_goal")
        return (
            route
            if route
            in {"derive_turn_goal", "finalize_success", "finalize_failure"}
            else "finalize_failure"
        )


def create_story_harness(
    *,
    profile: StoryHarnessProfile = TEST_MINIMAL_PROFILE,
) -> StoryHarness:
    return StoryHarness(profile=profile)


def _response_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict) and isinstance(first.get("message"), dict):
            return dict(first["message"])
    message = response.get("message")
    return dict(message) if isinstance(message, dict) else {}


def _runtime_tool_calls_from_message(
    message: dict[str, Any],
    *,
    source_round: int,
) -> list[RuntimeToolCall]:
    calls: list[RuntimeToolCall] = []
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return calls
    for position, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            continue
        function_payload = raw_call.get("function")
        function = function_payload if isinstance(function_payload, dict) else {}
        tool_name = str(function.get("name") or raw_call.get("name") or "").strip()
        if not tool_name:
            continue
        calls.append(
            RuntimeToolCall(
                call_id=str(raw_call.get("id") or f"call_{position}"),
                tool_name=tool_name,
                arguments=_parse_tool_arguments(function.get("arguments")),
                source_round=source_round,
            )
        )
    return calls


def _parse_tool_arguments(raw_arguments: object) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if isinstance(raw_arguments, str) and raw_arguments.strip():
        parsed = json.loads(raw_arguments)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _tool_call_to_openai(call: RuntimeToolCall) -> dict[str, Any]:
    return {
        "id": call.call_id,
        "type": "function",
        "function": {
            "name": call.tool_name,
            "arguments": json.dumps(
                call.arguments,
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    }


def _normalize_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    return normalized.removeprefix("rp_setup__")
