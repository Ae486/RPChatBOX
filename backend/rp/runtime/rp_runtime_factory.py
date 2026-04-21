"""Shared dependency factory for RP runtime entrypoints."""
from __future__ import annotations

from config import get_settings
from sqlmodel import Session

from rp.agent_runtime.adapters import SetupRuntimeAdapter
from rp.agent_runtime.executor import RpAgentRuntimeExecutor
from rp.agent_runtime.tools import RuntimeToolExecutor
from rp.graphs.activation_graph_nodes import ActivationGraphNodes
from rp.graphs.activation_graph_runner import ActivationGraphRunner
from rp.graphs.setup_graph_nodes import SetupGraphNodes
from rp.graphs.setup_graph_runner import SetupGraphRunner
from rp.graphs.story_graph_nodes import StoryGraphNodes
from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.services.longform_orchestrator_service import LongformOrchestratorService
from rp.services.longform_regression_service import LongformRegressionService
from rp.services.longform_specialist_service import LongformSpecialistService
from rp.services.local_tool_provider_registry import LocalToolProviderRegistry
from rp.services.memory_os_service import MemoryOsService
from rp.services.minimal_retrieval_ingestion_service import MinimalRetrievalIngestionService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.recall_summary_ingestion_service import RecallSummaryIngestionService
from rp.services.setup_agent_execution_service import SetupAgentExecutionService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_runtime_controller import SetupRuntimeController
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_activation_service import StoryActivationService
from rp.services.story_runtime_controller import StoryRuntimeController
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.writing_packet_builder import WritingPacketBuilder
from rp.services.writing_worker_execution_service import WritingWorkerExecutionService
from rp.tools.memory_crud_provider import MemoryCrudToolProvider
from rp.tools.setup_tool_provider import SetupToolProvider
from services.mcp_manager import McpManager


class RpRuntimeFactory:
    """Centralize RP runtime dependency wiring before deeper graph migration."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _build_setup_workspace_service(self) -> SetupWorkspaceService:
        return SetupWorkspaceService(self._session)

    def _build_setup_context_builder(
        self,
        *,
        workspace_service: SetupWorkspaceService,
    ) -> SetupContextBuilder:
        return SetupContextBuilder(workspace_service)

    def _build_setup_runtime_controller(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilder,
    ) -> SetupRuntimeController:
        return SetupRuntimeController(
            workspace_service=workspace_service,
            context_builder=context_builder,
            retrieval_ingestion_service=MinimalRetrievalIngestionService(self._session),
        )

    def build_setup_runtime_controller(self) -> SetupRuntimeController:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        return self._build_setup_runtime_controller(
            workspace_service=workspace_service,
            context_builder=context_builder,
        )

    def _build_setup_mcp_manager(self, *, story_id: str) -> McpManager:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        registry = LocalToolProviderRegistry()
        registry.register(
            MemoryCrudToolProvider(
                memory_os_service=MemoryOsService(
                    retrieval_broker=RetrievalBroker(default_story_id=story_id)
                ),
                allowed_tools=SetupAgentExecutionService._READ_ONLY_MEMORY_TOOLS,
                provider_id="rp_memory",
                server_name="RP Memory",
            )
        )
        registry.register(
            SetupToolProvider(
                workspace_service=workspace_service,
                context_builder=context_builder,
            )
        )
        return McpManager(
            storage_path=None,
            local_tool_provider_registry=registry,
            register_default_local_providers=False,
        )

    def _build_setup_runtime_executor(self) -> RpAgentRuntimeExecutor:
        return RpAgentRuntimeExecutor(
            tool_executor_factory=lambda turn_input: RuntimeToolExecutor(
                mcp_manager=self._build_setup_mcp_manager(
                    story_id=str(turn_input.story_id or "")
                )
            )
        )

    @staticmethod
    def _use_setup_runtime_v2() -> bool:
        return bool(get_settings().rp_setup_agent_runtime_v2_enabled)

    def build_setup_agent_execution_service(self) -> SetupAgentExecutionService:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        runtime_executor = self._build_setup_runtime_executor() if self._use_setup_runtime_v2() else None
        adapter = SetupRuntimeAdapter() if runtime_executor is not None else None
        return SetupAgentExecutionService(
            workspace_service=workspace_service,
            context_builder=context_builder,
            runtime_executor=runtime_executor,
            adapter=adapter,
            mcp_manager_factory=lambda story_id: self._build_setup_mcp_manager(
                story_id=story_id
            ),
        )

    def build_setup_graph_runner(self) -> SetupGraphRunner:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        runtime_executor = self._build_setup_runtime_executor() if self._use_setup_runtime_v2() else None
        adapter = SetupRuntimeAdapter() if runtime_executor is not None else None
        execution_service = SetupAgentExecutionService(
            workspace_service=workspace_service,
            context_builder=context_builder,
            runtime_executor=runtime_executor,
            adapter=adapter,
            mcp_manager_factory=lambda story_id: self._build_setup_mcp_manager(
                story_id=story_id
            ),
        )
        return SetupGraphRunner(
            nodes=SetupGraphNodes(
                workspace_service=workspace_service,
                context_builder=context_builder,
                execution_service=execution_service,
            ),
            execution_service=execution_service,
        )

    def build_activation_graph_runner(self) -> ActivationGraphRunner:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        setup_controller = self._build_setup_runtime_controller(
            workspace_service=workspace_service,
            context_builder=context_builder,
        )
        story_session_service = StorySessionService(self._session)
        return ActivationGraphRunner(
            nodes=ActivationGraphNodes(
                workspace_service=workspace_service,
                setup_controller=setup_controller,
                story_session_service=story_session_service,
            ),
        )

    def build_story_turn_domain_service(self) -> StoryTurnDomainService:
        story_session_service = StorySessionService(self._session)
        orchestrator_service = LongformOrchestratorService()
        specialist_service = LongformSpecialistService()
        regression_service = LongformRegressionService(
            story_session_service=story_session_service,
            orchestrator_service=orchestrator_service,
            specialist_service=specialist_service,
            story_state_apply_service=StoryStateApplyService(),
            recall_summary_ingestion_service=RecallSummaryIngestionService(self._session),
        )
        writing_packet_builder = WritingPacketBuilder()
        writing_worker_execution_service = WritingWorkerExecutionService()
        turn_domain_service = StoryTurnDomainService(
            story_session_service=story_session_service,
            orchestrator_service=orchestrator_service,
            specialist_service=specialist_service,
            writing_packet_builder=writing_packet_builder,
            writing_worker_execution_service=writing_worker_execution_service,
            regression_service=regression_service,
        )
        return turn_domain_service

    def _build_story_activation_service(self) -> StoryActivationService:
        workspace_service = self._build_setup_workspace_service()
        context_builder = self._build_setup_context_builder(
            workspace_service=workspace_service
        )
        setup_controller = self._build_setup_runtime_controller(
            workspace_service=workspace_service,
            context_builder=context_builder,
        )
        story_activation_service = StoryActivationService(
            setup_controller=setup_controller,
            workspace_service=workspace_service,
            story_session_service=StorySessionService(self._session),
        )
        return story_activation_service

    def build_story_runtime_controller(self) -> StoryRuntimeController:
        story_session_service = StorySessionService(self._session)
        story_activation_service = self._build_story_activation_service()
        return StoryRuntimeController(
            story_session_service=story_session_service,
            story_activation_service=story_activation_service,
        )

    def build_story_graph_runner(self) -> StoryGraphRunner:
        return StoryGraphRunner(
            nodes=StoryGraphNodes(
                domain_service=self.build_story_turn_domain_service(),
            ),
        )
