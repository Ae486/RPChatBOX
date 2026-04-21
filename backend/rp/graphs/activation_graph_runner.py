"""Phase-1 LangGraph workflow shell for activation."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from rp.models.story_runtime import StoryActivationResult

from .activation_graph_nodes import ActivationGraphNodes
from .activation_graph_state import ActivationGraphState
from .checkpoints import (
    build_thread_config,
    open_checkpointed_graph,
    require_snapshot_checkpoint_id,
)


class ActivationGraphRunner:
    """Graph-backed shell that preserves the current activation execution core."""

    def __init__(
        self,
        *,
        nodes: ActivationGraphNodes,
    ) -> None:
        self._nodes = nodes

    def activate_workspace(self, *, workspace_id: str) -> StoryActivationResult:
        initial_state: ActivationGraphState = {
            "workspace_id": workspace_id,
            "status": "received",
        }
        with open_checkpointed_graph(self._compile_graph) as graph:
            prepared_state = graph.invoke(
                initial_state,
                config=self._thread_config(workspace_id),
            )
            self._raise_if_error(prepared_state)
            final_state = graph.get_state(self._thread_config(workspace_id)).values
        self._raise_if_error(final_state)
        return StoryActivationResult.model_validate(final_state.get("activation_result") or {})

    def _compile_graph(self, checkpointer):
        builder = StateGraph(ActivationGraphState)
        builder.add_node("load_workspace", self._nodes.load_workspace)
        builder.add_node("run_activation_check", self._nodes.run_activation_check)
        builder.add_node("seed_story_session", self._nodes.seed_story_session)
        builder.add_node("seed_first_chapter_workspace", self._nodes.seed_first_chapter_workspace)
        builder.add_node("mark_workspace_activated", self._nodes.mark_workspace_activated)
        builder.add_node("finalize_activation", self._nodes.finalize_activation)
        builder.add_edge(START, "load_workspace")
        builder.add_edge("load_workspace", "run_activation_check")
        builder.add_edge("run_activation_check", "seed_story_session")
        builder.add_edge("seed_story_session", "seed_first_chapter_workspace")
        builder.add_edge("seed_first_chapter_workspace", "mark_workspace_activated")
        builder.add_edge("mark_workspace_activated", END)
        return builder.compile(checkpointer=checkpointer)

    @staticmethod
    def _thread_config(
        workspace_id: str,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        return build_thread_config(
            thread_id=workspace_id,
            namespace="rp_activation",
            checkpoint_id=checkpoint_id,
        )

    @staticmethod
    def _raise_if_error(state: ActivationGraphState) -> None:
        error = state.get("error")
        if not error:
            return
        raise ValueError(str(error.get("message") or "Activation graph execution failed"))
