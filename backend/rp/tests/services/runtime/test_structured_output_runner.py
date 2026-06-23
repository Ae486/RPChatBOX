from __future__ import annotations

import asyncio

import pytest

from models.chat import ChatMessage
from rp.services.runtime.structured_output_runner import (
    STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED,
    STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT,
    STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR,
    STRUCTURED_OUTPUT_RUNNER_REASON_SCRIPTED_QUEUE_EMPTY,
    STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT,
    STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED,
    ScriptedStructuredOutputRunner,
    StoryStructuredOutputRunner,
    StructuredOutputRunRequest,
    StructuredOutputRunResult,
    StructuredOutputToolPolicy,
)


def _request(*, tool_calls_enabled: bool = False) -> StructuredOutputRunRequest:
    return StructuredOutputRunRequest(
        run_id="run-001",
        role="memory-maintenance",
        worker_id="worker-memory-01",
        phase="post_write_maintenance",
        provider_id="provider-a",
        model_id="model-a",
        schema_name="memory-maintenance-output",
        schema_version="v1",
        messages=[
            ChatMessage(role="system", content="Return structured JSON only."),
            ChatMessage(role="user", content="Summarize the candidate."),
        ],
        response_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["status", "summary"],
        },
        tool_policy=StructuredOutputToolPolicy(
            tool_calls_enabled=tool_calls_enabled,
            allowed_tools=["memory.search"] if tool_calls_enabled else [],
        ),
        timeout_s=5.0,
        repair_budget=1,
        metadata={"origin": "unit-test"},
    )


def test_structured_output_request_defaults_to_tool_calls_disabled():
    request = _request()

    assert request.tool_policy.tool_calls_enabled is False
    assert request.tool_policy.allowed_tools == []
    assert request.repair_budget == 1
    assert request.timeout_s == 5.0


@pytest.mark.asyncio
async def test_scripted_runner_returns_completed_result_and_records_request():
    runner = ScriptedStructuredOutputRunner(
        [
            StructuredOutputRunResult(
                status="completed",
                structured_output={
                    "status": "completed",
                    "summary": "Keep the current candidate.",
                },
                raw_text='{"status":"completed","summary":"Keep the current candidate."}',
                stop_reason="stop",
                raw_output_visibility="private_trace",
                trace={"runner_mode": "scripted"},
            )
        ]
    )

    result = await runner.run(request=_request())

    assert result.status == "completed"
    assert result.structured_output == {
        "status": "completed",
        "summary": "Keep the current candidate.",
    }
    assert result.stop_reason == "stop"
    assert runner.call_count == 1
    assert runner.requests[0].run_id == "run-001"
    assert runner.requests[0].schema_name == "memory-maintenance-output"


@pytest.mark.asyncio
async def test_scripted_runner_fails_closed_when_tool_calls_are_enabled():
    runner = ScriptedStructuredOutputRunner([])

    result = await runner.run(request=_request(tool_calls_enabled=True))

    assert result.status == "failed"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED
    assert result.raw_output_visibility == "none"
    assert result.trace["runner_mode"] == "scripted"
    assert runner.call_count == 1


@pytest.mark.asyncio
async def test_scripted_runner_fails_when_queue_is_empty():
    runner = ScriptedStructuredOutputRunner([])

    result = await runner.run(request=_request())

    assert result.status == "failed"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_SCRIPTED_QUEUE_EMPTY
    assert result.message == "Scripted structured-output queue is empty."
    assert result.raw_output_visibility == "none"


class _FakeGateway:
    def __init__(self, *, text: str | None = None, exc: Exception | None = None):
        self._text = text
        self._exc = exc
        self.calls: list[dict] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._text, {"prompt_tokens": 3, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_story_structured_output_runner_returns_completed_result():
    runner = StoryStructuredOutputRunner(
        llm_gateway=_FakeGateway(
            text='{"status":"candidate_batch","summary":"Keep the current candidate."}'
        )
    )

    result = await runner.run(request=_request())

    assert result.status == "completed"
    assert result.structured_output == {
        "status": "candidate_batch",
        "summary": "Keep the current candidate.",
    }
    assert result.trace["runner_mode"] == "production"
    assert result.trace["schema_name"] == "memory-maintenance-output"


@pytest.mark.asyncio
async def test_story_structured_output_runner_maps_invalid_output_to_failed_result():
    runner = StoryStructuredOutputRunner(llm_gateway=_FakeGateway(text="not json"))

    result = await runner.run(request=_request())

    assert result.status == "failed"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT
    assert result.raw_output_visibility == "private_trace"


@pytest.mark.asyncio
async def test_story_structured_output_runner_maps_provider_error():
    runner = StoryStructuredOutputRunner(
        llm_gateway=_FakeGateway(exc=RuntimeError("provider down"))
    )

    result = await runner.run(request=_request())

    assert result.status == "failed"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR
    assert result.retryable is True
    assert result.raw_output_visibility == "none"


@pytest.mark.asyncio
async def test_story_structured_output_runner_maps_timeout():
    runner = StoryStructuredOutputRunner(
        llm_gateway=_FakeGateway(exc=TimeoutError("timed out"))
    )

    result = await runner.run(request=_request())

    assert result.status == "timeout"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT
    assert result.retryable is True


@pytest.mark.asyncio
async def test_story_structured_output_runner_maps_cancellation():
    runner = StoryStructuredOutputRunner(
        llm_gateway=_FakeGateway(exc=asyncio.CancelledError("cancelled"))
    )

    result = await runner.run(request=_request())

    assert result.status == "cancelled"
    assert result.reason_code == STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED
    assert result.retryable is True
