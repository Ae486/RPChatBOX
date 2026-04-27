"""Factory wiring tests for the setup runtime default and fallback paths."""
from __future__ import annotations

from config import get_settings
from models.chat import ProviderConfig
from rp.models.setup_agent import SetupAgentDialogueMessage, SetupAgentTurnRequest
from rp.models.setup_workspace import StoryMode
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from rp.agent_runtime.adapters import SetupRuntimeAdapter
from rp.services.setup_agent_execution_service import SetupAgentExecutionService
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService


def test_setup_runtime_v2_default_uses_new_runtime(retrieval_session, monkeypatch):
    monkeypatch.delenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", raising=False)
    monkeypatch.delenv(
        "CHATBOX_BACKEND_RP_SETUP_AGENT_RUNTIME_V2_ENABLED",
        raising=False,
    )
    get_settings.cache_clear()

    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()
    runner = RpRuntimeFactory(retrieval_session).build_setup_graph_runner()

    assert service._runtime_executor is not None
    assert service._adapter is not None
    assert runner._execution_service._runtime_executor is not None
    assert runner._execution_service._adapter is not None

    get_settings.cache_clear()


def test_setup_runtime_v2_flag_disabled_uses_legacy_service(retrieval_session, monkeypatch):
    monkeypatch.setenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", "false")
    get_settings.cache_clear()

    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()
    runner = RpRuntimeFactory(retrieval_session).build_setup_graph_runner()

    assert service._runtime_executor is None
    assert service._adapter is None
    assert runner._execution_service._runtime_executor is None
    assert runner._execution_service._adapter is None

    get_settings.cache_clear()


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

    assert len(turn_input.conversation_messages) == 4
    assert turn_input.context_bundle["governance_metadata"]["compacted_history_count"] == 6
    assert turn_input.context_bundle["compact_summary"] is not None
