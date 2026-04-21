"""Phase-1 LangGraph workflow shell for setup turns."""
from __future__ import annotations

import json
from typing import AsyncIterator

from langgraph.graph import END, START, StateGraph

from rp.models.setup_agent import SetupAgentTurnRequest, SetupAgentTurnResponse
from rp.services.setup_agent_execution_service import SetupAgentExecutionService

from .checkpoints import (
    build_thread_config,
    open_async_checkpointed_graph,
    open_checkpointed_graph,
    require_snapshot_checkpoint_id,
    snapshot_checkpoint_id,
    snapshot_exists,
    snapshot_parent_checkpoint_id,
)
from .setup_graph_nodes import SetupGraphNodes
from .setup_graph_state import SetupGraphState


class SetupGraphRunner:
    """Graph-backed shell that preserves the current setup execution core."""

    def __init__(
        self,
        *,
        nodes: SetupGraphNodes,
        execution_service: SetupAgentExecutionService,
    ) -> None:
        self._nodes = nodes
        self._execution_service = execution_service

    async def run_turn(self, request: SetupAgentTurnRequest) -> SetupAgentTurnResponse:
        initial_state = self._initial_state(request=request, stream_mode=False)
        async with open_async_checkpointed_graph(self._compile_graph) as graph:
            prepared_state = await graph.ainvoke(
                initial_state,
                config=self._thread_config(request.workspace_id),
            )
            snapshot = await graph.aget_state(self._thread_config(request.workspace_id))
            final_state = dict(snapshot.values or {})
        self._raise_if_error(final_state)
        return SetupAgentTurnResponse(
            assistant_text=str(final_state.get("assistant_text") or ""),
        )

    async def run_turn_stream(self, request: SetupAgentTurnRequest) -> AsyncIterator[str]:
        initial_state = self._initial_state(request=request, stream_mode=True)
        async with open_async_checkpointed_graph(self._compile_graph) as graph:
            base_config = self._thread_config(request.workspace_id)
            prepared_state = await graph.ainvoke(initial_state, config=base_config)
            self._raise_if_error(prepared_state)
            checkpoint_id = require_snapshot_checkpoint_id(await graph.aget_state(base_config))

            text_parts: list[str] = []
            failed_payload: dict | None = None
            try:
                async for chunk in self._execution_service.run_turn_stream(request):
                    payload = self._parse_typed_payload(chunk)
                    if payload is not None:
                        if payload.get("type") == "text_delta":
                            text_parts.append(str(payload.get("delta") or ""))
                        elif payload.get("type") == "error":
                            failed_payload = payload
                    yield chunk
            except Exception as exc:
                await graph.aupdate_state(
                    self._thread_config(request.workspace_id, checkpoint_id=checkpoint_id),
                    values={
                        "assistant_text": "".join(text_parts),
                        "status": "failed",
                        "error": {
                            "message": str(exc),
                            "type": "setup_stream_failed",
                        },
                    },
                    as_node="finalize_stream",
                )
                raise
            else:
                update_values: SetupGraphState = {
                    "assistant_text": "".join(text_parts),
                    "status": "failed" if failed_payload else "completed",
                }
                runtime_result = self._execution_service.last_runtime_result
                if runtime_result is not None:
                    update_values["finish_reason"] = runtime_result.finish_reason
                    if runtime_result.warnings:
                        update_values["warnings"] = list(runtime_result.warnings)
                    if runtime_result.structured_payload:
                        update_values["response_payload"] = dict(
                            runtime_result.structured_payload
                        )
                if failed_payload is not None:
                    update_values["error"] = failed_payload.get("error") or {
                        "message": "stream_failed",
                        "type": "setup_stream_failed",
                    }
                await graph.aupdate_state(
                    self._thread_config(request.workspace_id, checkpoint_id=checkpoint_id),
                    values=update_values,
                    as_node="finalize_stream",
                )

    def get_runtime_debug(self, *, workspace_id: str) -> dict:
        with open_checkpointed_graph(self._compile_graph) as graph:
            config = self._thread_config(workspace_id)
            snapshot = graph.get_state(config)
            history = list(graph.get_state_history(config)) if snapshot_exists(snapshot) else []
        latest_snapshot = history[-1] if history else snapshot
        meaningful_snapshot = self._pick_meaningful_snapshot(
            snapshot=snapshot,
            history=history,
        )
        return {
            "thread_id": f"{workspace_id}:rp_setup",
            "namespace": "rp_setup",
            "latest_checkpoint": self._snapshot_detail(latest_snapshot),
            "latest_meaningful_checkpoint": self._snapshot_detail(meaningful_snapshot),
            "history": [self._snapshot_summary(item) for item in history[:10]],
        }

    def _compile_graph(self, checkpointer):
        builder = StateGraph(SetupGraphState)
        builder.add_node("load_workspace", self._nodes.load_workspace)
        builder.add_node("build_context", self._nodes.build_context)
        builder.add_node("run_turn", self._nodes.run_turn)
        builder.add_node("finalize_stream", self._nodes.finalize_stream)
        builder.add_edge(START, "load_workspace")
        builder.add_edge("load_workspace", "build_context")
        builder.add_conditional_edges(
            "build_context",
            self._route_after_build_context,
            {
                "run_turn": "run_turn",
                "finish": END,
            },
        )
        builder.add_edge("run_turn", END)
        return builder.compile(checkpointer=checkpointer)

    @staticmethod
    def _initial_state(
        *,
        request: SetupAgentTurnRequest,
        stream_mode: bool,
    ) -> SetupGraphState:
        # Each setup turn reuses the same LangGraph thread, so transient failure
        # fields must be cleared explicitly before the new run starts.
        return {
            "workspace_id": request.workspace_id,
            "target_step": request.target_step.value if request.target_step else None,
            "model_id": request.model_id,
            "provider_id": request.provider_id,
            "user_prompt": request.user_prompt,
            "history": [item.model_dump(mode="json") for item in request.history],
            "stream_mode": stream_mode,
            "context_packet": {},
            "assistant_text": "",
            "finish_reason": None,
            "warnings": [],
            "response_payload": {},
            "error": None,
            "status": "received",
        }

    @staticmethod
    def _thread_config(
        workspace_id: str,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        return build_thread_config(
            thread_id=workspace_id,
            namespace="rp_setup",
            checkpoint_id=checkpoint_id,
        )

    @staticmethod
    def _parse_typed_payload(line: str) -> dict | None:
        stripped = line.strip()
        if not stripped.startswith("data: "):
            return None
        payload = stripped[6:]
        if not payload or payload == "[DONE]":
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _route_after_build_context(state: SetupGraphState) -> str:
        return "finish" if state.get("stream_mode") else "run_turn"

    @staticmethod
    def _raise_if_error(state: SetupGraphState) -> None:
        error = state.get("error")
        if not error:
            return
        raise ValueError(str(error.get("message") or "Setup graph execution failed"))

    @staticmethod
    def _snapshot_summary(snapshot) -> dict:
        created_at = getattr(snapshot, "created_at", None)
        return {
            "checkpoint_id": snapshot_checkpoint_id(snapshot),
            "parent_checkpoint_id": snapshot_parent_checkpoint_id(snapshot),
            "created_at": (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at) if created_at is not None else None
            ),
            "status": (snapshot.values or {}).get("status"),
            "state_keys": sorted((snapshot.values or {}).keys()),
        }

    @staticmethod
    def _snapshot_detail(snapshot) -> dict:
        return {
            "checkpoint_id": snapshot_checkpoint_id(snapshot),
            "parent_checkpoint_id": snapshot_parent_checkpoint_id(snapshot),
            "status": (snapshot.values or {}).get("status"),
            "state": dict(snapshot.values or {}),
            "summary": SetupGraphRunner._snapshot_summary(snapshot),
        }

    @staticmethod
    def _pick_meaningful_snapshot(*, snapshot, history: list):
        for item in reversed(history):
            values = item.values or {}
            if (
                values.get("assistant_text")
                or values.get("response_payload")
                or values.get("error")
                or values.get("status") in {"completed", "failed", "artifact_persisted"}
            ):
                return item
        return snapshot
