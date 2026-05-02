"""Factory wiring tests for the setup runtime-v2 execution path."""
from __future__ import annotations

import json
from typing import Any

import pytest

from models.chat import ProviderConfig
from rp.agent_runtime.contracts import (
    RpAgentTurnResult,
    RuntimeToolResult,
    SetupWorkingDigest,
)
from rp.agent_runtime.executor import RpAgentRuntimeExecutor
from rp.agent_runtime.tools import RuntimeToolExecutor
from rp.models.setup_drafts import FoundationEntry
from rp.models.setup_agent import SetupAgentDialogueMessage, SetupAgentTurnRequest
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from rp.agent_runtime.adapters import SetupRuntimeAdapter
from rp.services.setup_agent_execution_service import SetupAgentExecutionService
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


_RECOVERED_MAGIC_LAW_DETAIL = "Public spellcasting requires guild permits."


def _messages_text(messages: list[Any]) -> str:
    return "\n".join(str(message.content or "") for message in messages)


class _SetupProviderBackedToolExecutor(RuntimeToolExecutor):
    """Small test adapter that routes runtime setup calls into SetupToolProvider."""

    def __init__(self, *, provider: SetupToolProvider) -> None:
        self._provider = provider
        self.calls: list[tuple[Any, list[str]]] = []

    def get_openai_tool_definitions(
        self, *, visible_tool_names: list[str]
    ) -> list[dict[str, Any]]:
        allowed = set(visible_tool_names)
        return [
            tool.to_openai_tool()
            for tool in self._provider.list_tools()
            if (
                tool.name in allowed
                or tool.qualified_name in allowed
                or tool.raw_qualified_name in allowed
            )
        ]

    async def execute_tool_call(
        self,
        call,
        *,
        visible_tool_names: list[str],
    ) -> RuntimeToolResult:
        self.calls.append((call, list(visible_tool_names)))
        raw_name = str(call.tool_name).removeprefix("rp_setup__")
        if raw_name not in visible_tool_names:
            return RuntimeToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                content_text=json.dumps(
                    {"error": {"code": "unknown_tool", "message": raw_name}},
                    sort_keys=True,
                ),
                error_code="UNKNOWN_TOOL",
            )
        result = await self._provider.call_tool(
            tool_name=raw_name,
            arguments=dict(call.arguments),
        )
        content_text = str(result.get("content") or "")
        content_payload = json.loads(content_text) if content_text else None
        structured_payload = {
            "server_id": self._provider.provider_id,
            "tool_name": raw_name,
            "qualified_name": f"rp_setup__{raw_name}",
            "raw_qualified_name": raw_name,
        }
        if content_payload is not None:
            structured_payload["content_payload"] = content_payload
        return RuntimeToolResult(
            call_id=call.call_id,
            tool_name=f"rp_setup__{raw_name}",
            success=bool(result.get("success")),
            content_text=content_text,
            error_code=(
                str(result.get("error_code")) if result.get("error_code") else None
            ),
            structured_payload=structured_payload,
        )


class _DraftRefRecoveryLLM:
    def __init__(self, *, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.requests: list[Any] = []
        self.round = 0
        self.recovered_from_tool_result = False
        self.recovered_detail: str | None = None

    async def chat_completion(self, request):
        self.round += 1
        self.requests.append(request)
        if self.round == 1:
            visible_text = _messages_text(request.messages)
            assert _RECOVERED_MAGIC_LAW_DETAIL not in visible_text
            assert "OLD_RAW_HISTORY_OUTSIDE_SUMMARY_WINDOW" not in visible_text
            assert "foundation:magic-law" in visible_text
            assert "recovery_hints" in visible_text
            assert (
                "If compact_summary recovery_hints point to draft refs"
                in visible_text
            )
            assert any(
                "setup.read.draft_refs" in item["function"]["name"]
                for item in (request.tools or [])
            )
            draft_ref_schema = next(
                item
                for item in (request.tools or [])
                if item["function"]["name"] == "rp_setup__setup.read.draft_refs"
            )
            assert "refs" in draft_ref_schema["function"]["parameters"]["required"]
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_read_magic_law",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.read.draft_refs",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": self.workspace_id,
                                                "step_id": "longform_blueprint",
                                                "refs": ["foundation:magic-law"],
                                                "detail": "full",
                                                "max_chars": 1200,
                                            },
                                            sort_keys=True,
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        self.recovered_detail = self._recovered_detail_from_tool_messages(
            request.messages
        )
        self.recovered_from_tool_result = (
            self.recovered_detail == _RECOVERED_MAGIC_LAW_DETAIL
        )
        assert self.recovered_from_tool_result
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Recovered foundation:magic-law from draft readback: "
                            f"{self.recovered_detail}"
                        ),
                    }
                }
            ]
        }

    @staticmethod
    def _recovered_detail_from_tool_messages(messages: list[Any]) -> str | None:
        for message in messages:
            if message.role != "tool":
                continue
            payload = json.loads(str(message.content or "{}"))
            for item in payload.get("items") or []:
                if item.get("ref") != "foundation:magic-law" or not item.get("found"):
                    continue
                draft_payload = item.get("payload") or {}
                content = draft_payload.get("content") or {}
                if isinstance(content, dict) and content.get("summary"):
                    return str(content["summary"])
        return None


class _CompactPromptLLM:
    def __init__(self, *, invalid_json: bool = False) -> None:
        self.invalid_json = invalid_json
        self.requests: list[Any] = []

    async def chat_completion(self, request):
        self.requests.append(request)
        visible_text = _messages_text(request.messages)
        assert "SetupStageCompactPrompt" in visible_text
        assert request.tools is None
        prompt_payload = json.loads(str(request.messages[1].content or "{}"))
        draft_refs = list(prompt_payload.get("draft_refs") or [])
        if self.invalid_json:
            content = "not json"
        else:
            content = json.dumps(
                {
                    "summary_lines": ["Prompt-pass compacted older setup discussion."],
                    "confirmed_points": ["Keep compact as context engineering."],
                    "open_threads": ["Need next setup focus."],
                    "rejected_directions": ["Do not add a separate compact agent."],
                    "draft_refs": draft_refs,
                    "recovery_hints": [
                        {
                            "ref": draft_refs[0],
                            "reason": "Recover exact draft detail if needed.",
                            "detail": "Use setup.read.draft_refs.",
                        }
                    ]
                    if draft_refs
                    else [],
                    "must_not_infer": ["Do not infer old raw discussion details."],
                },
                sort_keys=True,
            )
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        }


def test_setup_runtime_factory_always_uses_runtime_v2(retrieval_session):
    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()
    runner = RpRuntimeFactory(retrieval_session).build_setup_graph_runner()

    assert service._runtime_executor is not None
    assert service._adapter is not None
    assert runner._execution_service._runtime_executor is not None
    assert runner._execution_service._adapter is not None


def test_setup_agent_execution_service_uses_standard_context_budget_for_small_turn():
    request = SetupAgentTurnRequest(
        workspace_id="workspace-1",
        model_id="model-1",
        user_prompt="Help me continue setup.",
        history=[
            SetupAgentDialogueMessage(role="user", content="short"),
            SetupAgentDialogueMessage(role="assistant", content="short reply"),
        ],
        user_edit_delta_ids=[],
    )

    assert (
        SetupAgentExecutionService._context_token_budget(request)
        == SetupAgentExecutionService._STANDARD_CONTEXT_TOKEN_BUDGET
    )


def test_setup_agent_execution_service_switches_to_compact_budget_for_large_turn():
    request = SetupAgentTurnRequest(
        workspace_id="workspace-1",
        model_id="model-1",
        user_prompt="Continue with a compact context.",
        history=[
            SetupAgentDialogueMessage(role="user", content="x" * 2500),
            SetupAgentDialogueMessage(role="assistant", content="y" * 2000),
        ],
        user_edit_delta_ids=["delta-1", "delta-2", "delta-3"],
    )

    assert (
        SetupAgentExecutionService._context_token_budget(request)
        == SetupAgentExecutionService._COMPACT_CONTEXT_TOKEN_BUDGET
    )


def test_setup_agent_execution_service_reports_estimated_token_pressure():
    request = SetupAgentTurnRequest(
        workspace_id="workspace-1",
        model_id="model-1",
        user_prompt="x" * 7200,
        history=[],
        user_edit_delta_ids=[],
    )

    estimated_tokens = SetupAgentExecutionService._estimate_input_tokens(request)
    reasons = SetupAgentExecutionService._context_profile_reasons(
        request,
        estimated_input_tokens=estimated_tokens,
    )

    assert (
        SetupAgentExecutionService._context_token_budget(
            request,
            estimated_input_tokens=estimated_tokens,
        )
        == SetupAgentExecutionService._COMPACT_CONTEXT_TOKEN_BUDGET
    )
    assert "estimated_input_tokens_threshold" in reasons
    assert "history_chars_threshold" not in reasons


def test_setup_agent_execution_service_reports_observed_usage_pressure():
    request = SetupAgentTurnRequest(
        workspace_id="workspace-1",
        model_id="model-1",
        user_prompt="short",
        history=[],
        user_edit_delta_ids=[],
    )
    previous_usage = {
        "prompt_tokens": 1900,
        "completion_tokens": 10,
        "total_tokens": 1910,
    }

    reasons = SetupAgentExecutionService._context_profile_reasons(
        request,
        previous_usage=previous_usage,
    )

    assert (
        SetupAgentExecutionService._context_token_budget(
            request,
            previous_usage=previous_usage,
        )
        == SetupAgentExecutionService._COMPACT_CONTEXT_TOKEN_BUDGET
    )
    assert "observed_usage_threshold" in reasons


@pytest.mark.asyncio
async def test_setup_agent_execution_service_v2_builds_governed_history_for_compact_turn(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    llm = _CompactPromptLLM()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
        llm_service=llm,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-governed-history-1",
        mode=StoryMode.LONGFORM,
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Continue setup with a compact history.",
        history=[
            SetupAgentDialogueMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=f"history message {index}",
            )
            for index in range(10)
        ],
        user_edit_delta_ids=["delta-1", "delta-2", "delta-3"],
    )

    turn_input, context_packet = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    compact_request_text = _messages_text(llm.requests[0].messages)
    assert context_packet.context_profile == "compact"
    assert len(llm.requests) == 1
    assert "history message 0" in compact_request_text
    assert "history message 5" in compact_request_text
    assert "history message 6" not in compact_request_text
    assert llm.requests[0].tools is None
    assert len(turn_input.conversation_messages) == 4
    assert turn_input.conversation_messages[0]["content"] == "history message 6"
    assert turn_input.conversation_messages[-1]["content"] == "history message 9"
    assert "setup.patch.foundation_entry" in turn_input.tool_scope
    assert "setup.patch.story_config" not in turn_input.tool_scope
    assert "setup.patch.longform_blueprint" not in turn_input.tool_scope
    assert turn_input.context_bundle["governance_metadata"]["raw_history_limit"] == 4
    assert turn_input.context_bundle["governance_metadata"]["kept_history_count"] == 4
    assert turn_input.context_bundle["governance_metadata"]["compacted_history_count"] == 6
    assert turn_input.context_bundle["compact_summary"] is not None
    assert turn_input.context_bundle["context_report"] is not None
    assert turn_input.context_bundle["context_report"]["context_profile"] == "compact"
    assert "history_count_threshold" in turn_input.context_bundle["context_report"]["profile_reasons"]
    assert "user_edit_threshold" in turn_input.context_bundle["context_report"]["profile_reasons"]
    assert turn_input.context_bundle["context_report"]["estimated_input_tokens"] is not None
    assert turn_input.context_bundle["context_report"].get("previous_prompt_tokens") is None
    assert turn_input.context_bundle["context_report"]["summary_strategy"] == "compact_prompt_summary"
    assert turn_input.context_bundle["context_report"]["summary_action"] == "rebuilt"


@pytest.mark.asyncio
async def test_setup_agent_runtime_v2_recovers_compacted_draft_ref_detail(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    compact_llm = _CompactPromptLLM()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
        llm_service=compact_llm,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-compact-draft-ref-recovery-1",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="magic-law",
            domain="rule",
            path="world.magic.law",
            title="Magic Law",
            tags=["law", "magic"],
            content={"summary": _RECOVERED_MAGIC_LAW_DETAIL},
        ),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)
    assert workspace is not None
    seed_packet = context_builder.build(
        SetupContextBuilderInput(
            mode=workspace.mode.value,
            workspace_id=workspace.workspace_id,
            current_step=SetupStepId.LONGFORM_BLUEPRINT.value,
            user_prompt="",
            user_edit_delta_ids=[],
            token_budget=SetupAgentExecutionService._COMPACT_CONTEXT_TOKEN_BUDGET,
        )
    )
    runtime_state_service.persist_turn_governance(
        workspace=workspace,
        context_packet=seed_packet,
        step_id=SetupStepId.LONGFORM_BLUEPRINT,
        working_digest=SetupWorkingDigest(
            current_goal="Continue blueprint planning from compact refs.",
            next_focus="Recover the exact magic-law constraint before using it.",
            draft_refs=["foundation:magic-law"],
        ),
        tool_outcomes=[],
        compact_summary=None,
    )
    old_raw_marker = "OLD_RAW_HISTORY_OUTSIDE_SUMMARY_WINDOW"
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Use the recovered magic-law detail in the blueprint plan.",
        target_step=SetupStepId.LONGFORM_BLUEPRINT,
        history=[
            SetupAgentDialogueMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=(
                    f"{old_raw_marker} compact candidate {index}"
                    if index == 0
                    else f"compact candidate history {index}"
                ),
            )
            for index in range(12)
        ],
        user_edit_delta_ids=["delta-1", "delta-2", "delta-3"],
    )

    turn_input, context_packet = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    compact_summary = turn_input.context_bundle["compact_summary"]
    assert context_packet.context_profile == "compact"
    assert len(compact_llm.requests) == 1
    assert len(turn_input.conversation_messages) == 4
    assert all(
        old_raw_marker not in str(message.get("content") or "")
        for message in turn_input.conversation_messages
    )
    assert compact_summary is not None
    assert compact_summary["draft_refs"] == ["foundation:magic-law"]
    assert compact_summary["recovery_hints"][0]["ref"] == "foundation:magic-law"
    assert _RECOVERED_MAGIC_LAW_DETAIL not in json.dumps(
        turn_input.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
    )

    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    tool_executor = _SetupProviderBackedToolExecutor(provider=provider)
    llm = _DraftRefRecoveryLLM(workspace_id=workspace.workspace_id)
    executor = RpAgentRuntimeExecutor(tool_executor_factory=lambda _: tool_executor)

    result = await executor.run(
        turn_input,
        adapter.build_runtime_profile(),
        llm_service=llm,
    )

    assert result.status == "completed"
    assert result.assistant_text.endswith(_RECOVERED_MAGIC_LAW_DETAIL)
    assert llm.recovered_detail == _RECOVERED_MAGIC_LAW_DETAIL
    assert llm.recovered_from_tool_result is True
    assert tool_executor.calls[0][0].tool_name == "rp_setup__setup.read.draft_refs"
    assert result.tool_results[0].success is True
    assert _RECOVERED_MAGIC_LAW_DETAIL in result.tool_results[0].content_text
    assert result.structured_payload["compact_summary"]["draft_refs"] == [
        "foundation:magic-law"
    ]


@pytest.mark.asyncio
async def test_setup_agent_execution_service_v2_surfaces_previous_usage_pressure(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    llm = _CompactPromptLLM()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
        llm_service=llm,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-observed-usage-1",
        mode=StoryMode.LONGFORM,
    )
    service._record_runtime_usage(
        workspace_id=workspace.workspace_id,
        step_id=workspace.current_step,
        result=RpAgentTurnResult(
            status="completed",
            finish_reason="completed_text",
            assistant_text="Previous answer.",
            structured_payload={
                "latest_response": {
                    "usage": {
                        "prompt_tokens": 1901,
                        "completion_tokens": 8,
                        "total_tokens": 1909,
                    }
                }
            },
        ),
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Continue setup.",
        history=[],
        user_edit_delta_ids=[],
    )

    turn_input, context_packet = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    report = turn_input.context_bundle["context_report"]
    assert context_packet.context_profile == "compact"
    assert len(llm.requests) == 0
    assert "observed_usage_threshold" in report["profile_reasons"]
    assert report["previous_prompt_tokens"] == 1901
    assert report["previous_total_tokens"] == 1909


@pytest.mark.asyncio
async def test_setup_agent_execution_service_v2_does_not_share_observed_usage_across_workspaces(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
    )
    noisy_workspace = workspace_service.create_workspace(
        story_id="story-observed-usage-noisy",
        mode=StoryMode.LONGFORM,
    )
    target_workspace = workspace_service.create_workspace(
        story_id="story-observed-usage-target",
        mode=StoryMode.LONGFORM,
    )
    service._record_runtime_usage(
        workspace_id=noisy_workspace.workspace_id,
        step_id=noisy_workspace.current_step,
        result=RpAgentTurnResult(
            status="completed",
            finish_reason="completed_text",
            assistant_text="Previous answer.",
            structured_payload={
                "latest_response": {
                    "usage": {
                        "prompt_tokens": 2200,
                        "completion_tokens": 8,
                        "total_tokens": 2600,
                    }
                }
            },
        ),
    )
    request = SetupAgentTurnRequest(
        workspace_id=target_workspace.workspace_id,
        model_id="model-1",
        user_prompt="Continue setup.",
        history=[],
        user_edit_delta_ids=[],
    )

    turn_input, context_packet = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=target_workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    report = turn_input.context_bundle["context_report"]
    assert context_packet.context_profile == "standard"
    assert "observed_usage_threshold" not in report["profile_reasons"]
    assert report.get("previous_prompt_tokens") is None
    assert report.get("previous_total_tokens") is None


@pytest.mark.asyncio
async def test_setup_agent_execution_service_v2_uses_target_step_for_tool_scope(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-tool-scope-override-1",
        mode=StoryMode.LONGFORM,
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Adjust story config.",
        target_step=SetupStepId.STORY_CONFIG,
        history=[],
        user_edit_delta_ids=[],
    )

    turn_input, _ = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    assert "setup.patch.story_config" in turn_input.tool_scope
    assert "setup.patch.foundation_entry" not in turn_input.tool_scope


def test_setup_agent_execution_service_prepare_turn_launch_reuses_shared_preflight(
    retrieval_session,
    monkeypatch,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-launch-preflight-1",
        mode=StoryMode.LONGFORM,
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Adjust story config.",
        target_step=SetupStepId.STORY_CONFIG,
        history=[],
        user_edit_delta_ids=[],
    )
    provider = ProviderConfig(
        type="openai",
        api_key="sk-test",
        api_url="https://example.com/v1",
        custom_headers={},
    )
    seen_model_ids: list[str] = []

    monkeypatch.setattr(
        service,
        "_ensure_agent_model_compatible",
        lambda model_id: seen_model_ids.append(model_id),
    )
    monkeypatch.setattr(
        service,
        "_resolve_provider",
        lambda *, model_id, provider_id: provider,
    )
    monkeypatch.setattr(
        service,
        "_resolve_model_name",
        lambda *, model_id, fallback_provider_id: "gpt-4o-mini",
    )

    launch = service._prepare_turn_launch(request)

    assert seen_model_ids == ["model-1"]
    assert launch.workspace.workspace_id == workspace.workspace_id
    assert launch.current_step == SetupStepId.STORY_CONFIG
    assert launch.model_name == "gpt-4o-mini"
    assert launch.provider == provider


@pytest.mark.asyncio
async def test_setup_agent_execution_service_prepare_runtime_v2_launch_sets_stream_flag(
    retrieval_session,
    monkeypatch,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-runtime-launch-1",
        mode=StoryMode.LONGFORM,
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Continue foundation.",
        target_step=SetupStepId.FOUNDATION,
        history=[],
        user_edit_delta_ids=[],
    )
    provider = ProviderConfig(
        type="openai",
        api_key="sk-test",
        api_url="https://example.com/v1",
        custom_headers={},
    )
    monkeypatch.setattr(service, "_ensure_agent_model_compatible", lambda model_id: None)
    monkeypatch.setattr(
        service,
        "_resolve_provider",
        lambda *, model_id, provider_id: provider,
    )
    monkeypatch.setattr(
        service,
        "_resolve_model_name",
        lambda *, model_id, fallback_provider_id: "gpt-4o-mini",
    )

    launch = service._prepare_turn_launch(request)
    prepared = await service._prepare_runtime_v2_launch(
        adapter=adapter,
        launch=launch,
        stream=True,
    )

    assert prepared.turn_input.stream is True
    assert prepared.turn_input.context_bundle["current_step"] == "foundation"
    assert "setup.patch.foundation_entry" in prepared.turn_input.tool_scope
    assert "setup.patch.story_config" not in prepared.turn_input.tool_scope
    assert prepared.context_packet.workspace_id == workspace.workspace_id
    assert prepared.profile.profile_id == "setup_agent"


@pytest.mark.asyncio
async def test_setup_agent_execution_service_v2_falls_back_when_compact_prompt_fails(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    adapter = SetupRuntimeAdapter()
    llm = _CompactPromptLLM(invalid_json=True)
    service = SetupAgentExecutionService(
        workspace_service=workspace_service,
        context_builder=context_builder,
        adapter=adapter,
        runtime_executor=None,
        runtime_state_service=runtime_state_service,
        llm_service=llm,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-compact-prompt-fallback-1",
        mode=StoryMode.LONGFORM,
    )
    request = SetupAgentTurnRequest(
        workspace_id=workspace.workspace_id,
        model_id="model-1",
        user_prompt="Continue with a compact history.",
        history=[
            SetupAgentDialogueMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=f"fallback history message {index}",
            )
            for index in range(10)
        ],
        user_edit_delta_ids=["delta-1", "delta-2", "delta-3"],
    )

    turn_input, context_packet = await service._build_runtime_v2_turn_input(
        adapter=adapter,
        request=request,
        workspace=workspace,
        model_name="gpt-4o-mini",
        provider=ProviderConfig(
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
        ),
    )

    report = turn_input.context_bundle["context_report"]
    compact_summary = turn_input.context_bundle["compact_summary"]
    assert context_packet.context_profile == "compact"
    assert len(llm.requests) == 1
    assert report["summary_strategy"] == "deterministic_prefix_summary"
    assert report["summary_action"] == "rebuilt"
    assert report["fallback_reason"] is not None
    assert compact_summary is not None
    assert compact_summary["summary_lines"][0].startswith("User: fallback history")
