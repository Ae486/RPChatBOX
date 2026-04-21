"""Phase-1 LangGraph workflow shell for story turns."""
from __future__ import annotations

import json
from typing import AsyncIterator

from langgraph.graph import END, START, StateGraph

from rp.models.story_runtime import (
    LongformTurnCommandKind,
    LongformTurnRequest,
    LongformTurnResponse,
)

from .checkpoints import (
    build_thread_config,
    open_async_checkpointed_graph,
    open_checkpointed_graph,
    require_snapshot_checkpoint_id,
    snapshot_checkpoint_id,
    snapshot_exists,
    snapshot_parent_checkpoint_id,
)
from .story_graph_nodes import StoryGraphNodes
from .story_graph_state import StoryGraphState


class StoryGraphRunner:
    """Graph-backed shell that preserves the current story execution core."""

    _SPECIAL_COMMANDS = {
        LongformTurnCommandKind.ACCEPT_OUTLINE,
        LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        LongformTurnCommandKind.COMPLETE_CHAPTER,
    }

    def __init__(self, *, nodes: StoryGraphNodes) -> None:
        self._nodes = nodes

    async def run_turn(self, request: LongformTurnRequest) -> LongformTurnResponse:
        initial_state = self._initial_state(request=request, stream_mode=False)
        async with open_async_checkpointed_graph(self._compile_graph) as graph:
            prepared_state = await graph.ainvoke(
                initial_state,
                config=self._thread_config(request.session_id),
            )
            snapshot = await graph.aget_state(self._thread_config(request.session_id))
            final_state = dict(snapshot.values or {})
        self._raise_if_error(final_state)
        return LongformTurnResponse.model_validate(final_state.get("response_payload") or {})

    async def run_turn_stream(self, request: LongformTurnRequest) -> AsyncIterator[str]:
        if request.command_kind in self._SPECIAL_COMMANDS:
            response = await self.run_turn(request)
            if response.assistant_text:
                yield self._typed({"type": "text_delta", "delta": response.assistant_text})
            yield self._typed({"type": "done"})
            return
        initial_state = self._initial_state(request=request, stream_mode=True)
        async with open_async_checkpointed_graph(self._compile_graph) as graph:
            base_config = self._thread_config(request.session_id)
            prepared_state = await graph.ainvoke(initial_state, config=base_config)
            self._raise_if_error(prepared_state)
            checkpoint_id = require_snapshot_checkpoint_id(await graph.aget_state(base_config))

            current_state = (
                await graph.aget_state(
                self._thread_config(request.session_id, checkpoint_id=checkpoint_id)
                )
            ).values
            text_parts: list[str] = []
            try:
                async for chunk in self._nodes.writer_run_stream(current_state):
                    payload = self._parse_typed_payload(chunk)
                    if payload is not None:
                        if payload.get("type") == "done":
                            break
                        if payload.get("type") == "error":
                            await graph.aupdate_state(
                                self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                                values={
                                    "assistant_text": "".join(text_parts),
                                    "status": "failed",
                                    "error": payload.get("error")
                                    or {
                                        "message": "story_stream_failed",
                                        "type": "story_turn_failed",
                                    },
                                },
                                as_node="finalize_turn",
                            )
                            yield chunk
                            yield self._typed({"type": "done"})
                            return
                    delta = self._nodes.extract_text_delta(chunk)
                    if delta:
                        text_parts.append(delta)
                    yield chunk

                new_config = await graph.aupdate_state(
                    self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                    {
                        "assistant_text": "".join(text_parts),
                        "status": "writer_completed",
                    },
                    as_node="writer_run",
                )
                snapshot = await graph.aget_state(new_config)
                checkpoint_id = require_snapshot_checkpoint_id(snapshot)
                current_state = dict(snapshot.values or {})
                current_state = self._nodes.persist_generated_artifact(current_state)
                new_config = await graph.aupdate_state(
                    self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                    current_state,
                    as_node="persist_generated_artifact",
                )
                snapshot = await graph.aget_state(new_config)
                checkpoint_id = require_snapshot_checkpoint_id(snapshot)
                current_state = dict(snapshot.values or {})
                regression_update = await self._nodes.post_write_regression(current_state)
                current_state = {**current_state, **regression_update}
                await graph.aupdate_state(
                    self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                    regression_update,
                    as_node="post_write_regression",
                )
                await graph.aupdate_state(
                    self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                    values={
                        "assistant_text": "".join(text_parts),
                        "response_payload": current_state.get("response_payload") or {},
                        "status": "completed",
                    },
                    as_node="finalize_turn",
                )
                yield self._typed({"type": "done"})
            except Exception as exc:
                await graph.aupdate_state(
                    self._thread_config(request.session_id, checkpoint_id=checkpoint_id),
                    values={
                        "assistant_text": "".join(text_parts),
                        "status": "failed",
                        "error": {
                            "message": str(exc),
                            "type": "story_turn_failed",
                        },
                    },
                    as_node="finalize_turn",
                )
                yield self._typed(
                    {
                        "type": "error",
                        "error": {
                            "message": str(exc),
                            "type": "story_turn_failed",
                        },
                    }
                )
                yield self._typed({"type": "done"})

    def get_runtime_debug(self, *, session_id: str) -> dict:
        with open_checkpointed_graph(self._compile_graph) as graph:
            config = self._thread_config(session_id)
            snapshot = graph.get_state(config)
            history = list(graph.get_state_history(config)) if snapshot_exists(snapshot) else []
        latest_snapshot = history[-1] if history else snapshot
        meaningful_snapshot = self._pick_meaningful_snapshot(
            snapshot=snapshot,
            history=history,
        )
        return {
            "thread_id": f"{session_id}:rp_story",
            "namespace": "rp_story",
            "latest_checkpoint": self._snapshot_detail(latest_snapshot),
            "latest_meaningful_checkpoint": self._snapshot_detail(meaningful_snapshot),
            "history": [self._snapshot_summary(item) for item in history[:10]],
        }

    def _compile_graph(self, checkpointer):
        builder = StateGraph(StoryGraphState)
        builder.add_node("load_session_and_chapter", self._nodes.load_session_and_chapter)
        builder.add_node("validate_command", self._nodes.validate_command)
        builder.add_node("prepare_generation_inputs", self._nodes.prepare_generation_inputs)
        builder.add_node("orchestrator_plan", self._nodes.orchestrator_plan)
        builder.add_node("specialist_analyze", self._nodes.specialist_analyze)
        builder.add_node("build_packet", self._nodes.build_packet)
        builder.add_node("writer_run", self._nodes.writer_run)
        builder.add_node("persist_generated_artifact", self._nodes.persist_generated_artifact)
        builder.add_node("post_write_regression", self._nodes.post_write_regression)
        builder.add_node("accept_outline", self._nodes.accept_outline)
        builder.add_node("accept_pending_segment", self._nodes.accept_pending_segment)
        builder.add_node("complete_chapter", self._nodes.complete_chapter)
        builder.add_node("finalize_turn", self._nodes.finalize_turn)
        builder.add_edge(START, "load_session_and_chapter")
        builder.add_edge("load_session_and_chapter", "validate_command")
        builder.add_conditional_edges(
            "validate_command",
            self._route_after_validate,
            {
                "accept_outline": "accept_outline",
                "accept_pending_segment": "accept_pending_segment",
                "complete_chapter": "complete_chapter",
                "prepare_generation_inputs": "prepare_generation_inputs",
            },
        )
        builder.add_edge("accept_outline", END)
        builder.add_edge("accept_pending_segment", END)
        builder.add_edge("complete_chapter", END)
        builder.add_edge("prepare_generation_inputs", "orchestrator_plan")
        builder.add_edge("orchestrator_plan", "specialist_analyze")
        builder.add_edge("specialist_analyze", "build_packet")
        builder.add_conditional_edges(
            "build_packet",
            self._route_after_build_packet,
            {
                "writer_run": "writer_run",
                "finish": END,
            },
        )
        builder.add_edge("writer_run", "persist_generated_artifact")
        builder.add_edge("persist_generated_artifact", "post_write_regression")
        builder.add_edge("post_write_regression", END)
        return builder.compile(checkpointer=checkpointer)

    @staticmethod
    def _initial_state(
        *,
        request: LongformTurnRequest,
        stream_mode: bool,
    ) -> StoryGraphState:
        # Each story turn reuses the same LangGraph thread, so transient runtime
        # fields must be cleared before the new execution starts.
        return {
            "session_id": request.session_id,
            "command_kind": request.command_kind.value,
            "model_id": request.model_id,
            "provider_id": request.provider_id,
            "user_prompt": request.user_prompt,
            "target_artifact_id": request.target_artifact_id,
            "stream_mode": stream_mode,
            "pending_artifact_id": None,
            "accepted_segment_ids": [],
            "plan": {},
            "specialist_bundle": {},
            "writing_packet": {},
            "artifact_id": None,
            "artifact_kind": None,
            "warnings": [],
            "assistant_text": "",
            "response_payload": {},
            "error": None,
            "status": "received",
        }

    @staticmethod
    def _thread_config(
        session_id: str,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        return build_thread_config(
            thread_id=session_id,
            namespace="rp_story",
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
    def _raise_if_error(state: StoryGraphState) -> None:
        error = state.get("error")
        if not error:
            return
        raise ValueError(str(error.get("message") or "Story graph execution failed"))

    @staticmethod
    def _typed(payload: dict) -> str:
        return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    @staticmethod
    def _route_after_validate(state: StoryGraphState) -> str:
        command_kind = state.get("command_kind")
        if command_kind == LongformTurnCommandKind.ACCEPT_OUTLINE.value:
            return "accept_outline"
        if command_kind == LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT.value:
            return "accept_pending_segment"
        if command_kind == LongformTurnCommandKind.COMPLETE_CHAPTER.value:
            return "complete_chapter"
        return "prepare_generation_inputs"

    @staticmethod
    def _route_after_build_packet(state: StoryGraphState) -> str:
        return "finish" if state.get("stream_mode") else "writer_run"

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
            "summary": StoryGraphRunner._snapshot_summary(snapshot),
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
