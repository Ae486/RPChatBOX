"""Contract tests for the S-X2 StoryHarness injection seam."""

from __future__ import annotations

import asyncio

import pytest

from rp.agent_runtime.kernel.runtime_tool_contracts import RuntimeToolCall, RuntimeToolResult
from rp.agent_runtime.story.harness_finalize import FinalizeGuardDecision
from rp.agent_runtime.story.story_harness import (
    TEST_MINIMAL_PROFILE,
    StoryHarness,
    StoryHarnessResult,
    create_story_harness,
)


def _noop_tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "noop",
                "description": "test noop",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        }
    ]


class RecordingHooks:
    def __init__(self) -> None:
        self.before_calls: list[RuntimeToolCall] = []
        self.after_results: list[RuntimeToolResult] = []
        self.errors: list[tuple[RuntimeToolCall, BaseException]] = []
        self.cancellation_count = 0

    def before_tool_call(self, call: RuntimeToolCall) -> None:
        self.before_calls.append(call)

    def after_tool_result(self, result: RuntimeToolResult) -> None:
        self.after_results.append(result)

    def on_tool_error(self, call: RuntimeToolCall, error: BaseException) -> None:
        self.errors.append((call, error))

    def on_cancellation(self) -> None:
        self.cancellation_count += 1


class RaisingToolExecutor:
    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, object]]:
        return _noop_tool_definitions()

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        raise RuntimeError("boom")


class SuccessfulToolExecutor:
    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, object]]:
        return _noop_tool_definitions()

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=True,
            content_text='{"ok": true}',
            structured_payload={"content_payload": {"ok": True}},
        )


class CancelledToolExecutor:
    def get_openai_tool_definitions(
        self,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> list[dict[str, object]]:
        return _noop_tool_definitions()

    async def execute_tool_call(
        self,
        call: RuntimeToolCall,
        *,
        visible_tool_names: tuple[str, ...],
    ) -> RuntimeToolResult:
        raise asyncio.CancelledError()


class DenyFinalizeGuard:
    def evaluate_final_output(self, *, assistant_text: str) -> FinalizeGuardDecision:
        return FinalizeGuardDecision(allowed=False, reason_code="blocked_xyz")


class AllowFinalizeGuard:
    def evaluate_final_output(self, *, assistant_text: str) -> FinalizeGuardDecision:
        return FinalizeGuardDecision(allowed=True)


class RecordingLifecycleHarness(StoryHarness):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.apply_tool_results_calls = 0
        self.finalize_success_calls = 0
        self.finalize_failure_calls = 0

    def _apply_tool_results(self, state):
        self.apply_tool_results_calls += 1
        return super()._apply_tool_results(state)

    def _finalize_success(self, state):
        self.finalize_success_calls += 1
        return super()._finalize_success(state)

    def _finalize_failure(self, state):
        self.finalize_failure_calls += 1
        return super()._finalize_failure(state)


def test_s2_t1_default_scripted_final_text_turn_remains_completed() -> None:
    harness = create_story_harness(profile=TEST_MINIMAL_PROFILE)
    try:
        harness.set_responses([harness.final_text("done")])
        result = harness.run(turn_goal="default final text")
    finally:
        harness.cleanup()

    assert result.succeeded
    assert result.status == "completed"


def test_s2_t2_executor_error_routes_to_finalize_failure() -> None:
    hooks = RecordingHooks()
    harness = StoryHarness(
        profile=TEST_MINIMAL_PROFILE,
        tool_executor=RaisingToolExecutor(),
        hooks=hooks,
    )
    try:
        harness.set_responses([harness.tool_call("noop", {})])
        result = harness.run(turn_goal="executor failure")
    finally:
        harness.cleanup()

    assert result.status == "failed"
    assert result.finish_reason == "tool_execution_error"
    assert len(hooks.errors) == 1
    assert hooks.errors[0][0].tool_name == "noop"
    assert isinstance(hooks.errors[0][1], RuntimeError)


def test_s2_t3_finalize_guard_deny_returns_failed_reason_code() -> None:
    harness = StoryHarness(
        profile=TEST_MINIMAL_PROFILE,
        finalize_guard=DenyFinalizeGuard(),
    )
    try:
        harness.set_responses([harness.final_text("blocked")])
        result = harness.run(turn_goal="guard deny")
    finally:
        harness.cleanup()

    assert result.status == "failed"
    assert result.finish_reason == "blocked_xyz"


def test_s2_t4_finalize_guard_allow_keeps_success_path() -> None:
    harness = StoryHarness(
        profile=TEST_MINIMAL_PROFILE,
        finalize_guard=AllowFinalizeGuard(),
    )
    try:
        harness.set_responses([harness.final_text("allowed")])
        result = harness.run(turn_goal="guard allow")
    finally:
        harness.cleanup()

    assert result.status == "completed"


def test_s2_t5_hooks_fire_around_successful_tool_execution() -> None:
    hooks = RecordingHooks()
    harness = StoryHarness(
        profile=TEST_MINIMAL_PROFILE,
        tool_executor=SuccessfulToolExecutor(),
        hooks=hooks,
    )
    try:
        harness.set_responses(
            [
                harness.tool_call("noop", {}),
                harness.final_text("done"),
            ]
        )
        result = harness.run(turn_goal="hook success")
    finally:
        harness.cleanup()

    assert result.status == "completed"
    assert len(hooks.before_calls) == 1
    assert len(hooks.after_results) == 1
    assert hooks.before_calls[0].tool_name == "noop"
    assert hooks.after_results[0].tool_name == "noop"


def test_s2_t6_cancellation_propagates_without_finalize_or_tool_append() -> None:
    hooks = RecordingHooks()
    harness = RecordingLifecycleHarness(
        profile=TEST_MINIMAL_PROFILE,
        tool_executor=CancelledToolExecutor(),
        hooks=hooks,
    )
    try:
        harness.set_responses([harness.tool_call("noop", {})])

        async def _run() -> None:
            await harness.arun(turn_goal="cancel")

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(_run())
    finally:
        harness.cleanup()

    assert hooks.cancellation_count >= 1
    assert hooks.after_results == []
    assert harness.apply_tool_results_calls == 0
    assert harness.finalize_success_calls == 0
    assert harness.finalize_failure_calls == 0


def test_s2_t7_arun_matches_run_for_scripted_default_path() -> None:
    sync_harness = create_story_harness(profile=TEST_MINIMAL_PROFILE)
    async_harness = create_story_harness(profile=TEST_MINIMAL_PROFILE)
    try:
        sync_harness.set_responses([sync_harness.final_text("same")])
        async_harness.set_responses([async_harness.final_text("same")])
        sync_result = sync_harness.run(turn_goal="parity")
        async_result = asyncio.run(async_harness.arun(turn_goal="parity"))
    finally:
        sync_harness.cleanup()
        async_harness.cleanup()

    assert isinstance(sync_result, StoryHarnessResult)
    assert sync_result == async_result
