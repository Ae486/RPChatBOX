"""SetupAgent execution layer with legacy fallback and runtime-v2 support."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Callable

from models.chat import ChatCompletionRequest, ChatMessage
from models.mcp_config import McpToolInfo
from rp.agent_runtime.adapters import SetupRuntimeAdapter
from rp.agent_runtime.contracts import RpAgentTurnResult
from rp.agent_runtime.executor import RpAgentRuntimeExecutor
from rp.models.setup_agent import (
    SetupAgentDialogueMessage,
    SetupAgentTurnRequest,
    SetupAgentTurnResponse,
)
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.services.local_tool_provider_registry import LocalToolProviderRegistry
from rp.services.memory_os_service import MemoryOsService
from rp.services.setup_agent_prompt_service import SetupAgentPromptService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.memory_crud_provider import MemoryCrudToolProvider
from rp.tools.setup_tool_provider import SetupToolProvider
from services.litellm_service import LiteLLMService, get_litellm_service
from services.mcp_manager import McpManager
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service
from services.tool_runtime_service import ToolRuntimeService

logger = logging.getLogger(__name__)


class _SetupToolRuntimeLLMAdapter:
    """Tool runtime adapter over LiteLLM for setup-specific execution."""

    def __init__(self, llm_service: LiteLLMService) -> None:
        self._llm_service = llm_service

    async def chat_completion(self, request: ChatCompletionRequest):
        return await self._llm_service.chat_completion(request)

    def chat_completion_stream(self, request: ChatCompletionRequest):
        return self._llm_service.chat_completion_stream(request)


class SetupAgentExecutionService:
    """Execute one SetupAgent turn against SetupWorkspace and setup tools."""

    _READ_ONLY_MEMORY_TOOLS = {
        "memory.get_state",
        "memory.get_summary",
        "memory.search_recall",
        "memory.search_archival",
        "memory.list_versions",
        "memory.read_provenance",
    }

    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilder,
        prompt_service: SetupAgentPromptService | None = None,
        llm_service: LiteLLMService | None = None,
        runtime_executor: RpAgentRuntimeExecutor | None = None,
        adapter: SetupRuntimeAdapter | None = None,
        mcp_manager_factory: Callable[[str], McpManager] | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._prompt_service = prompt_service or SetupAgentPromptService()
        self._llm_service = llm_service or get_litellm_service()
        self._runtime_executor = runtime_executor
        self._adapter = adapter
        self._mcp_manager_factory = (
            mcp_manager_factory
            or (lambda story_id: self._build_setup_mcp_manager(story_id=story_id))
        )
        self._last_runtime_result: RpAgentTurnResult | None = None

    @property
    def last_runtime_result(self) -> RpAgentTurnResult | None:
        return self._last_runtime_result

    async def run_turn(self, request: SetupAgentTurnRequest) -> SetupAgentTurnResponse:
        workspace = self._require_workspace(request.workspace_id)
        provider = self._resolve_provider(model_id=request.model_id, provider_id=request.provider_id)
        model_name = self._resolve_model_name(model_id=request.model_id, fallback_provider_id=request.provider_id)
        logger.info(
            "[SETUP_AGENT] run_turn_start workspace_id=%s story_id=%s model_id=%s provider_id=%s model=%s target_step=%s history_count=%s",
            request.workspace_id,
            workspace.story_id,
            request.model_id,
            request.provider_id or "",
            model_name,
            (request.target_step or workspace.current_step).value,
            len(request.history),
        )
        if self._runtime_executor is not None and self._adapter is not None:
            result = await self._run_turn_v2(
                request=request,
                workspace=workspace,
                model_name=model_name,
                provider=provider,
            )
            logger.info(
                "[SETUP_AGENT] run_turn_done workspace_id=%s model_id=%s finish_reason=%s assistant_chars=%s",
                request.workspace_id,
                request.model_id,
                result.finish_reason,
                len(result.assistant_text),
            )
            return self._adapter.to_turn_response(result)

        chat_request = self._build_chat_request(
            request=request,
            workspace=workspace,
            provider=provider,
            model_name=model_name,
            stream=False,
        )
        tool_runtime = ToolRuntimeService(
            mcp_manager=self._mcp_manager_factory(workspace.story_id)
        )
        response = await tool_runtime.chat_completion(
            chat_request,
            llm_service=_SetupToolRuntimeLLMAdapter(self._llm_service),
        )
        choices = response.get("choices") or []
        assistant_message = choices[0].get("message") if choices else {}
        logger.info(
            "[SETUP_AGENT] run_turn_done workspace_id=%s model_id=%s assistant_chars=%s",
            request.workspace_id,
            request.model_id,
            len(str((assistant_message or {}).get("content") or "")),
        )
        self._last_runtime_result = RpAgentTurnResult(
            status="completed",
            finish_reason="legacy_tool_runtime",
            assistant_text=str((assistant_message or {}).get("content") or ""),
            structured_payload={"response": response},
        )
        return SetupAgentTurnResponse(
            assistant_text=str((assistant_message or {}).get("content") or ""),
        )

    async def run_turn_stream(self, request: SetupAgentTurnRequest) -> AsyncIterator[str]:
        workspace = self._require_workspace(request.workspace_id)
        provider = self._resolve_provider(model_id=request.model_id, provider_id=request.provider_id)
        model_name = self._resolve_model_name(model_id=request.model_id, fallback_provider_id=request.provider_id)
        logger.info(
            "[SETUP_AGENT] run_turn_stream_start workspace_id=%s story_id=%s model_id=%s provider_id=%s model=%s target_step=%s history_count=%s",
            request.workspace_id,
            workspace.story_id,
            request.model_id,
            request.provider_id or "",
            model_name,
            (request.target_step or workspace.current_step).value,
            len(request.history),
        )
        if self._runtime_executor is not None and self._adapter is not None:
            async for chunk in self._run_turn_stream_v2(
                request=request,
                workspace=workspace,
                model_name=model_name,
                provider=provider,
            ):
                yield chunk
            return

        chat_request = self._build_chat_request(
            request=request,
            workspace=workspace,
            provider=provider,
            model_name=model_name,
            stream=True,
        )
        tool_runtime = ToolRuntimeService(
            mcp_manager=self._mcp_manager_factory(workspace.story_id)
        )
        chunk_count = 0
        try:
            async for chunk in tool_runtime.chat_completion_stream(
                chat_request,
                llm_service=_SetupToolRuntimeLLMAdapter(self._llm_service),
            ):
                chunk_count += 1
                yield chunk
        except Exception:
            logger.exception(
                "[SETUP_AGENT] run_turn_stream_error workspace_id=%s model_id=%s chunk_count=%s",
                request.workspace_id,
                request.model_id,
                chunk_count,
            )
            raise
        finally:
            logger.info(
                "[SETUP_AGENT] run_turn_stream_end workspace_id=%s model_id=%s chunk_count=%s",
                request.workspace_id,
                request.model_id,
                chunk_count,
            )

    def _build_chat_request(
        self,
        *,
        request: SetupAgentTurnRequest,
        workspace,
        provider,
        model_name: str,
        stream: bool,
    ) -> ChatCompletionRequest:
        context_packet = self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace.workspace_id,
                current_step=(request.target_step or workspace.current_step).value,
                user_prompt=request.user_prompt,
                user_edit_delta_ids=[],
                token_budget=None,
            )
        )
        system_prompt = self._prompt_service.build_system_prompt(
            mode=workspace.mode,
            current_step=request.target_step or workspace.current_step,
            context_packet=context_packet,
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            *self._history_to_chat_messages(request.history),
            ChatMessage(role="user", content=request.user_prompt),
        ]
        return ChatCompletionRequest(
            model=model_name,
            model_id=request.model_id,
            messages=messages,
            stream=stream,
            stream_event_mode="typed" if stream else None,
            provider_id=request.provider_id,
            provider=provider,
            enable_tools=True,
        )

    @staticmethod
    def _history_to_chat_messages(history: list[SetupAgentDialogueMessage]) -> list[ChatMessage]:
        return [ChatMessage(role=item.role, content=item.content) for item in history]

    def _build_setup_mcp_manager(self, *, story_id: str) -> McpManager:
        registry = LocalToolProviderRegistry()
        registry.register(
            MemoryCrudToolProvider(
                memory_os_service=MemoryOsService(
                    retrieval_broker=RetrievalBroker(default_story_id=story_id)
                ),
                allowed_tools=self._READ_ONLY_MEMORY_TOOLS,
                provider_id="rp_memory",
                server_name="RP Memory",
            )
        )
        registry.register(
            SetupToolProvider(
                workspace_service=self._workspace_service,
                context_builder=self._context_builder,
            )
        )
        return McpManager(
            storage_path=None,
            local_tool_provider_registry=registry,
            register_default_local_providers=False,
        )

    def _resolve_model_name(self, *, model_id: str, fallback_provider_id: str | None) -> str:
        entry = get_model_registry_service().get_entry(model_id)
        if entry is None:
            raise ValueError(f"Model not found: {model_id}")
        if fallback_provider_id and entry.provider_id != fallback_provider_id:
            raise ValueError(
                f"Model {model_id} does not belong to provider {fallback_provider_id}"
            )
        if not entry.is_enabled:
            raise ValueError(f"Model is disabled: {model_id}")
        return entry.model_name

    def _resolve_provider(self, *, model_id: str, provider_id: str | None):
        entry = get_model_registry_service().get_entry(model_id)
        if entry is None:
            raise ValueError(f"Model not found: {model_id}")
        resolved_provider_id = provider_id or entry.provider_id
        provider_entry = get_provider_registry_service().get_entry(resolved_provider_id)
        if provider_entry is None:
            raise ValueError(f"Provider not found: {resolved_provider_id}")
        if not provider_entry.is_enabled:
            raise ValueError(f"Provider is disabled: {resolved_provider_id}")
        return provider_entry.to_runtime_provider()

    def _require_workspace(self, workspace_id: str):
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        return workspace

    async def _run_turn_v2(
        self,
        *,
        request: SetupAgentTurnRequest,
        workspace,
        model_name: str,
        provider,
    ) -> RpAgentTurnResult:
        context_packet = self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace.workspace_id,
                current_step=(request.target_step or workspace.current_step).value,
                user_prompt=request.user_prompt,
                user_edit_delta_ids=[],
                token_budget=None,
            )
        )
        turn_input = self._adapter.build_turn_input(
            request=request,
            workspace=workspace,
            context_packet=context_packet,
            model_name=model_name,
            provider=provider,
        )
        profile = self._adapter.build_runtime_profile()
        result = await self._runtime_executor.run(
            turn_input.model_copy(update={"stream": False}),
            profile,
            llm_service=self._llm_service,
        )
        self._last_runtime_result = result
        return result

    async def _run_turn_stream_v2(
        self,
        *,
        request: SetupAgentTurnRequest,
        workspace,
        model_name: str,
        provider,
    ) -> AsyncIterator[str]:
        context_packet = self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace.workspace_id,
                current_step=(request.target_step or workspace.current_step).value,
                user_prompt=request.user_prompt,
                user_edit_delta_ids=[],
                token_budget=None,
            )
        )
        turn_input = self._adapter.build_turn_input(
            request=request,
            workspace=workspace,
            context_packet=context_packet,
            model_name=model_name,
            provider=provider,
        ).model_copy(update={"stream": True})
        profile = self._adapter.build_runtime_profile()
        async for chunk in self._runtime_executor.run_stream(
            turn_input,
            profile,
            llm_service=self._llm_service,
        ):
            yield chunk
        self._last_runtime_result = self._runtime_executor.last_result
