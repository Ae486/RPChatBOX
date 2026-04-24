"""Unit tests for the setup-agent runtime executor."""
from __future__ import annotations

import json

import pytest

from rp.agent_runtime.contracts import RpAgentTurnInput, RuntimeProfile, RuntimeToolResult
from rp.agent_runtime.executor import RpAgentRuntimeExecutor


def _turn_input(
    *,
    stream: bool = False,
    user_prompt: str = "Please help with setup.",
    context_bundle: dict | None = None,
    tool_scope: list[str] | None = None,
) -> RpAgentTurnInput:
    runtime_context = {
        "system_prompt": "You are SetupAgent.",
        "current_step": "story_config",
        "context_packet": {
            "current_step": "story_config",
            "current_draft_snapshot": {"notes": ["existing"]},
            "user_prompt": user_prompt,
        },
        "open_question_count": 0,
        "blocking_open_question_count": 0,
        "open_question_texts": [],
        "last_proposal_status": None,
    }
    if context_bundle:
        runtime_context.update(context_bundle)
    return RpAgentTurnInput(
        profile_id="setup_agent",
        run_kind="interactive_agent_turn",
        story_id="story-1",
        workspace_id="workspace-1",
        model_id="model-1",
        provider_id="provider-1",
        stream=stream,
        user_visible_request=user_prompt,
        conversation_messages=[],
        context_bundle=runtime_context,
        tool_scope=tool_scope or ["setup.patch.story_config"],
        metadata={
            "model_name": "gpt-4o-mini",
            "provider": {
                "type": "openai",
                "api_key": "sk-test",
                "api_url": "https://example.com/v1",
                "custom_headers": {},
            },
        },
    )


def _profile() -> RuntimeProfile:
    return RuntimeProfile(
        profile_id="setup_agent",
        visible_tool_names=["setup.patch.story_config"],
        max_rounds=8,
        allow_stream=True,
        recovery_policy="setup_agent_v1",
        finish_policy="assistant_text_or_failure",
    )


def _tool_definition(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


class _FakeToolExecutor:
    def __init__(self, *, results: list[RuntimeToolResult] | None = None) -> None:
        self._results = list(results or [])
        self.calls = []

    def get_openai_tool_definitions(self, *, visible_tool_names: list[str]) -> list[dict]:
        return [
            _tool_definition(
                name
                if name.startswith("rp_setup__")
                else f"rp_setup__{name}"
            )
            for name in visible_tool_names
        ]

    async def execute_tool_call(self, call, *, visible_tool_names: list[str]) -> RuntimeToolResult:
        self.calls.append((call, list(visible_tool_names)))
        if self._results:
            return self._results.pop(0)
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=True,
            content_text='{"success": true}',
            error_code=None,
        )


class _FakeLangfuseObservation:
    def __init__(self, *, sink: list[dict], name: str) -> None:
        self._sink = sink
        self._name = name

    def __enter__(self):
        self._sink.append({"kind": "observation_enter", "name": self._name})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "observation_exit", "name": self._name})
        return False

    def update(self, **kwargs):
        self._sink.append({"kind": "observation_update", "name": self._name, "payload": kwargs})

    def score(self, **kwargs):
        self._sink.append({"kind": "score", "name": self._name, "payload": kwargs})

    def score_trace(self, **kwargs):
        self._sink.append({"kind": "score_trace", "name": self._name, "payload": kwargs})

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self._sink,
            name=str(kwargs.get("name") or "unknown"),
        )


class _FakeLangfuseService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self.events,
            name=str(kwargs.get("name") or "unknown"),
        )

    def propagate_attributes(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self.events,
            name="propagate",
        )


class _TextOnlyLLM:
    async def chat_completion(self, request):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Direct setup answer.",
                    }
                }
            ]
        }


class _ToolThenTextLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_patch",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.patch.story_config",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": "workspace-1",
                                                "patch": {"style_rules": ["tight"]},
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Tool succeeded and I finished the answer.",
                    }
                }
            ]
        }


class _SchemaRepairLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            arguments = {"workspace_id": "workspace-1"}
        elif self.round == 2:
            arguments = {
                "workspace_id": "workspace-1",
                "patch": {"style_rules": ["tight"]},
            }
        else:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Corrected the tool call and finished.",
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": f"call_{self.round}",
                                "type": "function",
                                "function": {
                                    "name": "rp_setup__setup.patch.story_config",
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    }
                }
            ]
        }


class _UnknownToolLLM:
    async def chat_completion(self, request):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_unknown",
                                "type": "function",
                                "function": {
                                    "name": "rp_setup__setup.unknown",
                                    "arguments": json.dumps({"workspace_id": "workspace-1"}),
                                },
                            }
                        ],
                    }
                }
            ]
        }


class _AskUserAfterFailureLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_ask_user",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.patch.story_config",
                                        "arguments": json.dumps({"workspace_id": "workspace-1"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I still need the missing story config details. Which style rules do you want me to lock in?",
                    }
                }
            ]
        }


class _ExplainInsteadOfRepairLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_bad_patch",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.patch.story_config",
                                        "arguments": json.dumps({"workspace_id": "workspace-1"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I know the patch field is missing, so I cannot continue yet.",
                    }
                }
            ]
        }


class _CommitTooEarlyThenQuestionLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_commit",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.proposal.commit",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": "workspace-1",
                                                "step_id": "story_config",
                                                "target_draft_refs": ["draft:story_config"],
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "We still have unresolved setup questions before commit. Which runtime preset do you want to use?",
                    }
                }
            ]
        }


class _TruthWriteFailureThenDiscussionLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion(self, request):
        self.round += 1
        if self.round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_truth_write",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.truth.write",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": "workspace-1",
                                                "step_id": "story_config",
                                                "truth_write": {
                                                    "write_id": "write-1",
                                                    "current_step": "story_config",
                                                    "block_type": "story_config",
                                                    "operation": "merge",
                                                    "payload": {"notes": "draft notes"},
                                                },
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The draft write is not stable yet. We should continue refining this setup detail before review.",
                    }
                }
            ]
        }


class _StreamToolLLM:
    def __init__(self) -> None:
        self.round = 0

    async def chat_completion_stream(self, request):
        self.round += 1
        if self.round == 1:
            yield 'data: {"type":"text_delta","delta":"Checking draft."}\n\n'
            yield (
                'data: {"type":"tool_call","tool_calls":[{"id":"call_patch","function":{"name":"rp_setup__setup.patch.story_config","arguments":"{\\"workspace_id\\":\\"workspace-1\\",\\"patch\\":{\\"style_rules\\":[\\"tight\\"]}}"}}]}\n\n'
            )
            yield 'data: {"type":"done"}\n\n'
            return
        yield 'data: {"type":"text_delta","delta":"Applied and finalized."}\n\n'
        yield 'data: {"type":"done"}\n\n'


class _StreamUsageLLM:
    async def chat_completion_stream(self, request):
        yield 'data: {"type":"text_delta","delta":"Streaming answer."}\n\n'
        yield 'data: {"type":"usage","prompt_tokens":11,"completion_tokens":7,"total_tokens":18}\n\n'
        yield 'data: {"type":"done"}\n\n'


@pytest.mark.asyncio
async def test_runtime_executor_returns_direct_answer_without_tools():
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(_turn_input(), _profile(), llm_service=_TextOnlyLLM())

    assert result.status == "completed"
    assert result.finish_reason == "completed_text"
    assert result.assistant_text == "Direct setup answer."
    assert result.tool_invocations == []
    assert result.tool_results == []


@pytest.mark.asyncio
async def test_runtime_executor_executes_tool_and_continues():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_patch",
                tool_name="rp_setup__setup.patch.story_config",
                success=True,
                content_text='{"success": true}',
                error_code=None,
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(_turn_input(), _profile(), llm_service=_ToolThenTextLLM())

    assert result.status == "completed"
    assert result.assistant_text == "Tool succeeded and I finished the answer."
    assert len(result.tool_invocations) == 1
    assert len(result.tool_results) == 1
    assert tool_executor.calls[0][0].tool_name == "rp_setup__setup.patch.story_config"


@pytest.mark.asyncio
async def test_runtime_executor_allows_one_schema_repair_retry():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_1",
                tool_name="rp_setup__setup.patch.story_config",
                success=False,
                content_text='{"error":{"code":"schema_validation_failed"}}',
                error_code="SCHEMA_VALIDATION_FAILED",
            ),
            RuntimeToolResult(
                call_id="call_2",
                tool_name="rp_setup__setup.patch.story_config",
                success=True,
                content_text='{"success": true}',
                error_code=None,
            ),
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(_turn_input(), _profile(), llm_service=_SchemaRepairLLM())

    assert result.status == "completed"
    assert result.assistant_text == "Corrected the tool call and finished."
    assert len(result.tool_results) == 2
    assert "tool_schema_validation_retry" in result.warnings


@pytest.mark.asyncio
async def test_runtime_executor_switches_to_ask_user_when_failure_requires_user_input():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_ask_user",
                tool_name="rp_setup__setup.patch.story_config",
                success=False,
                content_text=json.dumps(
                    {
                        "code": "schema_validation_failed",
                        "message": "Need user-selected style rules before patching story config.",
                        "details": {
                            "ask_user": True,
                            "errors": [{"type": "missing", "loc": ["patch"]}],
                        },
                    }
                ),
                error_code="SCHEMA_VALIDATION_FAILED",
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(),
        _profile(),
        llm_service=_AskUserAfterFailureLLM(),
    )

    assert result.status == "completed"
    assert result.finish_reason == "awaiting_user_input"
    assert "Which style rules do you want" in result.assistant_text
    assert "tool_failure_requires_user_input" in result.warnings


@pytest.mark.asyncio
async def test_runtime_executor_blocks_false_success_when_repair_obligation_is_unmet():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_bad_patch",
                tool_name="rp_setup__setup.patch.story_config",
                success=False,
                content_text=json.dumps(
                    {
                        "code": "schema_validation_failed",
                        "message": "Patch payload is missing.",
                        "details": {
                            "errors": [{"type": "missing", "loc": ["patch"]}],
                        },
                    }
                ),
                error_code="SCHEMA_VALIDATION_FAILED",
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(),
        _profile(),
        llm_service=_ExplainInsteadOfRepairLLM(),
    )

    assert result.status == "failed"
    assert result.finish_reason == "repair_obligation_unfulfilled"
    assert result.error is not None
    assert result.structured_payload["completion_guard"]["reason"] == "repair_obligation_unresolved"


@pytest.mark.asyncio
async def test_runtime_executor_blocks_commit_when_blocking_questions_remain():
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(
            user_prompt="Please commit this step.",
            tool_scope=["setup.proposal.commit"],
            context_bundle={
                "blocking_open_question_count": 1,
                "open_question_texts": ["Need runtime preset choice"],
            },
        ),
        _profile(),
        llm_service=_CommitTooEarlyThenQuestionLLM(),
    )

    assert result.status == "completed"
    assert result.finish_reason == "awaiting_user_input"
    assert tool_executor.calls == []
    assert "commit_proposal_blocked" in result.warnings


@pytest.mark.asyncio
async def test_runtime_executor_does_not_repropose_commit_after_rejection():
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(
            user_prompt="Try committing again.",
            tool_scope=["setup.proposal.commit"],
            context_bundle={
                "last_proposal_status": "rejected",
                "blocking_open_question_count": 0,
            },
        ),
        _profile(),
        llm_service=_CommitTooEarlyThenQuestionLLM(),
    )

    assert result.status == "completed"
    assert result.finish_reason == "awaiting_user_input"
    assert tool_executor.calls == []
    assert "commit_proposal_blocked" in result.warnings


@pytest.mark.asyncio
async def test_runtime_executor_blocks_commit_when_cognitive_state_is_invalidated():
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(
            user_prompt="Please commit this step.",
            tool_scope=["setup.proposal.commit"],
            context_bundle={
                "cognitive_state_summary": {
                    "current_step": "story_config",
                    "invalidated": True,
                    "invalidation_reasons": ["user_edit_delta"],
                }
            },
        ),
        _profile(),
        llm_service=_CommitTooEarlyThenQuestionLLM(),
    )

    assert result.status == "completed"
    assert result.finish_reason == "awaiting_user_input"
    assert tool_executor.calls == []
    assert "commit_proposal_blocked" in result.warnings


@pytest.mark.asyncio
async def test_runtime_executor_keeps_non_commit_tool_failure_in_recovery_semantics():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_truth_write",
                tool_name="rp_setup__setup.truth.write",
                success=False,
                content_text=json.dumps(
                    {
                        "code": "setup_tool_failed",
                        "message": "Draft truth write could not be applied yet.",
                        "details": {
                            "repair_strategy": "continue_discussion",
                        },
                    }
                ),
                error_code="SETUP_TOOL_FAILED",
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(tool_scope=["setup.truth.write"]),
        _profile(),
        llm_service=_TruthWriteFailureThenDiscussionLLM(),
    )

    assert result.status == "completed"
    assert result.finish_reason == "continue_discussion"
    assert result.structured_payload["turn_goal"]["goal_type"] == "recover_from_tool_failure"
    assert result.structured_payload["last_failure"]["failure_category"] == "continue_discussion"
    assert result.structured_payload["repair_route"] == "continue_discussion"


@pytest.mark.asyncio
async def test_runtime_executor_fails_fast_on_unknown_tool():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_unknown",
                tool_name="rp_setup__setup.unknown",
                success=False,
                content_text='{"error":{"code":"unknown_tool"}}',
                error_code="UNKNOWN_TOOL",
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(_turn_input(), _profile(), llm_service=_UnknownToolLLM())

    assert result.status == "failed"
    assert result.finish_reason == "tool_error_unrecoverable"
    assert result.error is not None
    assert result.error["type"] == "tool_error_unrecoverable"


@pytest.mark.asyncio
async def test_runtime_executor_stream_preserves_typed_event_order():
    tool_executor = _FakeToolExecutor(
        results=[
            RuntimeToolResult(
                call_id="call_patch",
                tool_name="rp_setup__setup.patch.story_config",
                success=True,
                content_text='{"success": true}',
                error_code=None,
            )
        ]
    )
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    chunks = []
    async for chunk in executor.run_stream(
        _turn_input(stream=True),
        _profile(),
        llm_service=_StreamToolLLM(),
    ):
        chunks.append(chunk)

    payloads = [json.loads(chunk[6:]) for chunk in chunks if chunk.startswith("data: ")]
    assert [payload["type"] for payload in payloads] == [
        "text_delta",
        "tool_call",
        "tool_started",
        "tool_result",
        "text_delta",
        "done",
    ]


@pytest.mark.asyncio
async def test_runtime_executor_emits_langfuse_generation_and_tool_observations(
    monkeypatch,
):
    fake_langfuse = _FakeLangfuseService()
    monkeypatch.setattr(
        "rp.agent_runtime.executor.get_langfuse_service",
        lambda: fake_langfuse,
    )
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(tool_scope=["setup.patch.story_config"]),
        _profile(),
        llm_service=_ToolThenTextLLM(),
    )

    assert result.finish_reason == "completed_text"
    assert any(
        item["kind"] == "observation_enter" and item["name"] == "rp.runtime.model_call"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "observation_enter"
        and item["name"] == "rp.runtime.tool:rp_setup__setup.patch.story_config"
        for item in fake_langfuse.events
    )


@pytest.mark.asyncio
async def test_runtime_executor_stream_preserves_usage_in_latest_response():
    tool_executor = _FakeToolExecutor()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    chunks = []
    async for chunk in executor.run_stream(
        _turn_input(stream=True, tool_scope=[]),
        _profile(),
        llm_service=_StreamUsageLLM(),
    ):
        chunks.append(chunk)

    assert chunks
    assert executor.last_result is not None
    latest_response = executor.last_result.structured_payload["latest_response"]
    assert latest_response["usage"]["prompt_tokens"] == 11
    assert latest_response["usage"]["completion_tokens"] == 7
    assert latest_response["usage"]["total_tokens"] == 18
