"""Factory wiring tests for the setup runtime-v2 execution path."""
from __future__ import annotations

from models.chat import ProviderConfig
from rp.agent_runtime.contracts import RpAgentTurnResult
from rp.models.setup_agent import SetupAgentDialogueMessage, SetupAgentTurnRequest
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from rp.agent_runtime.adapters import SetupRuntimeAdapter
from rp.services.setup_agent_execution_service import SetupAgentExecutionService
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService


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


def test_setup_agent_execution_service_v2_builds_governed_history_for_compact_turn(
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

    turn_input, context_packet = service._build_runtime_v2_turn_input(
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

    assert context_packet.context_profile == "compact"
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
    assert turn_input.context_bundle["context_report"]["summary_strategy"] == "deterministic_prefix_summary"
    assert turn_input.context_bundle["context_report"]["summary_action"] == "rebuilt"


def test_setup_agent_execution_service_v2_surfaces_previous_usage_pressure(
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

    turn_input, context_packet = service._build_runtime_v2_turn_input(
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
    assert "observed_usage_threshold" in report["profile_reasons"]
    assert report["previous_prompt_tokens"] == 1901
    assert report["previous_total_tokens"] == 1909


def test_setup_agent_execution_service_v2_does_not_share_observed_usage_across_workspaces(
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

    turn_input, context_packet = service._build_runtime_v2_turn_input(
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


def test_setup_agent_execution_service_v2_uses_target_step_for_tool_scope(
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

    turn_input, _ = service._build_runtime_v2_turn_input(
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


def test_setup_agent_execution_service_prepare_runtime_v2_launch_sets_stream_flag(
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
    prepared = service._prepare_runtime_v2_launch(
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
