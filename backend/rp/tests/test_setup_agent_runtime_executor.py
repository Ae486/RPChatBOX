"""Unit tests for the setup-agent runtime executor."""

from __future__ import annotations

import json

import pytest

from rp.agent_runtime.contracts import (
    RpAgentTurnInput,
    RuntimeProfile,
    RuntimeToolResult,
)
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
            "committed_summaries": ["world.magic.law"],
            "current_draft_snapshot": {"notes": ["existing"]},
            "prior_stage_handoffs": [
                {
                    "step_id": "foundation",
                    "commit_id": "commit-foundation-1",
                    "summary": "world.magic.law",
                    "committed_refs": ["draft:foundation"],
                    "spotlights": ["Magic Law"],
                    "chunk_descriptions": [
                        {
                            "chunk_ref": "foundation:magic-law",
                            "block_type": "foundation_entry",
                            "title": "Magic Law",
                            "description": "rule | world.magic.law - Public spellcasting is regulated by guild permits.",
                            "metadata": {
                                "domain": "rule",
                                "path": "world.magic.law",
                                "entry_id": "magic-law",
                            },
                        }
                    ],
                    "created_at": "2026-04-27T00:00:00Z",
                }
            ],
            "spotlights": ["Magic Law"],
            "user_prompt": user_prompt,
        },
        "open_question_count": 0,
        "blocking_open_question_count": 0,
        "open_question_texts": [],
        "has_prior_stage_handoffs": True,
        "prior_stage_handoff_count": 1,
        "prior_stage_handoff_steps": ["foundation"],
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

    def get_openai_tool_definitions(
        self, *, visible_tool_names: list[str]
    ) -> list[dict]:
        return [
            _tool_definition(
                name if name.startswith("rp_setup__") else f"rp_setup__{name}"
            )
            for name in visible_tool_names
        ]

    async def execute_tool_call(
        self, call, *, visible_tool_names: list[str]
    ) -> RuntimeToolResult:
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
        self._sink.append(
            {"kind": "observation_update", "name": self._name, "payload": kwargs}
        )

    def score(self, **kwargs):
        self._sink.append({"kind": "score", "name": self._name, "payload": kwargs})

    def score_trace(self, **kwargs):
        self._sink.append(
            {"kind": "score_trace", "name": self._name, "payload": kwargs}
        )

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


class _RecordingTextOnlyLLM:
    def __init__(self) -> None:
        self.requests = []

    async def chat_completion(self, request):
        self.requests.append(request)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Recorded direct answer.",
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
                                    "arguments": json.dumps(
                                        {"workspace_id": "workspace-1"}
                                    ),
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
                                        "arguments": json.dumps(
                                            {"workspace_id": "workspace-1"}
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
                                        "arguments": json.dumps(
                                            {"workspace_id": "workspace-1"}
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
                                                "target_draft_refs": [
                                                    "draft:story_config"
                                                ],
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
    assert result.structured_payload["working_digest"] is not None
    assert result.structured_payload["tool_outcomes"] == []
    assert result.structured_payload["compact_summary"] is None
    assert result.structured_payload["context_report"] is None
    assert result.structured_payload["continue_reason"] is None
    assert result.structured_payload["loop_trace"]
    assert result.structured_payload["loop_trace"][-1]["decision"]["finish_reason"] == "completed_text"


@pytest.mark.asyncio
async def test_runtime_executor_places_runtime_overlay_after_system_prompt():
    tool_executor = _FakeToolExecutor()
    llm = _RecordingTextOnlyLLM()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(
            context_bundle={
                "cognitive_state_summary": {
                    "current_step": "story_config",
                    "invalidated": False,
                    "invalidation_reasons": [],
                    "open_questions": ["Which preset should be used?"],
                },
                "working_digest": {
                    "current_goal": "Clarify setup",
                    "next_focus": "Lock runtime preset",
                    "open_questions": ["Which preset should be used?"],
                    "draft_refs": ["draft:story_config"],
                    "commit_blockers": [],
                },
                "tool_outcomes": [
                    {
                        "tool_name": "rp_setup__setup.read.step_context",
                        "success": True,
                        "summary": "Read current story config draft",
                        "updated_refs": ["draft:story_config"],
                        "relevance": "read",
                        "recorded_at": "2026-04-28T00:00:00Z",
                    }
                ],
                "compact_summary": {
                    "source_fingerprint": "fp-1",
                    "source_message_count": 4,
                    "summary_lines": ["Earlier draft discussion was compacted."],
                    "open_threads": ["Need exact preset name."],
                    "draft_refs": ["draft:story_config"],
                    "recovery_hints": [
                        {
                            "ref": "draft:story_config",
                            "reason": "Need exact draft detail.",
                        }
                    ],
                },
                "context_report": {
                    "context_profile": "compact",
                    "profile_reasons": [
                        "history_count_threshold",
                        "user_edit_threshold",
                    ],
                    "raw_history_count": 10,
                    "raw_history_chars": 3200,
                    "estimated_input_tokens": 900,
                    "previous_prompt_tokens": 1200,
                    "previous_total_tokens": 1600,
                    "user_edit_delta_count": 3,
                    "prior_stage_handoff_count": 1,
                    "raw_history_limit": 4,
                    "kept_history_count": 4,
                    "compacted_history_count": 6,
                    "retained_tool_outcome_count": 1,
                    "summary_strategy": "deterministic_prefix_summary",
                    "summary_action": "rebuilt",
                    "summary_line_count": 1,
                },
            }
        ),
        _profile(),
        llm_service=llm,
    )

    assert result.status == "completed"
    assert llm.requests
    request = llm.requests[0]
    messages = request.messages
    assert messages[0].role == "system"
    assert messages[0].content == "You are SetupAgent."
    assert messages[1].role == "system"
    assert "Runtime turn state follows as JSON." in messages[1].content
    assert "setup.read.draft_refs" in messages[1].content
    assert "context_packet" not in messages[1].content
    assert "context_report" not in messages[1].content
    assert messages[-1].role == "user"
    assert messages[-1].content == "Please help with setup."
    assert result.structured_payload["context_report"]["context_profile"] == "compact"


@pytest.mark.asyncio
async def test_runtime_executor_only_sends_tool_schemas_from_turn_scope():
    tool_executor = _FakeToolExecutor()
    llm = _RecordingTextOnlyLLM()
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        _turn_input(
            tool_scope=[
                "setup.read.workspace",
                "setup.patch.story_config",
            ]
        ),
        _profile(),
        llm_service=llm,
    )

    assert result.status == "completed"
    assert llm.requests
    tool_names = [item["function"]["name"] for item in (llm.requests[0].tools or [])]
    assert tool_names == [
        "rp_setup__setup.read.workspace",
        "rp_setup__setup.patch.story_config",
    ]


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

    result = await executor.run(
        _turn_input(), _profile(), llm_service=_ToolThenTextLLM()
    )

    assert result.status == "completed"
    assert result.assistant_text == "Tool succeeded and I finished the answer."
    assert len(result.tool_invocations) == 1
    assert len(result.tool_results) == 1
    assert tool_executor.calls[0][0].tool_name == "rp_setup__setup.patch.story_config"
    assert result.structured_payload["tool_outcomes"][0]["tool_name"] == (
        "rp_setup__setup.patch.story_config"
    )
    assert result.structured_payload["tool_outcomes"][0]["success"] is True
    continue_reasons = [
        item["decision"].get("continue_reason")
        for item in result.structured_payload["loop_trace"]
    ]
    assert "tool_call_batch_pending" in continue_reasons
    assert "tool_result_follow_up" in continue_reasons


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

    result = await executor.run(
        _turn_input(), _profile(), llm_service=_SchemaRepairLLM()
    )

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
    assert (
        result.structured_payload["completion_guard"]["reason"]
        == "repair_obligation_unresolved"
    )
    assert any(
        item["decision"].get("continue_reason") == "completion_guard_retry"
        for item in result.structured_payload["loop_trace"]
    )


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
    assert (
        result.structured_payload["turn_goal"]["goal_type"]
        == "recover_from_tool_failure"
    )
    assert (
        result.structured_payload["last_failure"]["failure_category"]
        == "continue_discussion"
    )
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

    result = await executor.run(
        _turn_input(), _profile(), llm_service=_UnknownToolLLM()
    )

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
    assert executor.last_result.structured_payload["loop_trace"]
