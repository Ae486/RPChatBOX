"""Unified RP runtime executor backed by a LangGraph agent loop."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Callable

from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig
from services.langfuse_service import get_langfuse_service

from .contracts import (
    RpAgentTurnInput,
    RpAgentTurnResult,
    RuntimeProfile,
    RuntimeToolCall,
    RuntimeToolResult,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
    SetupPendingObligation,
    SetupReflectionTicket,
    SetupTurnGoal,
    SetupWorkingPlan,
)
from .events import RuntimeEvent, TypedSseEventAdapter
from .graph import build_runtime_graph
from .policies import (
    CompletionGuardPolicy,
    FinishPolicy,
    ReflectionTriggerPolicy,
    RepairDecisionPolicy,
    ToolFailureClassifier,
)
from .state import RpAgentRunState
from .tools import RuntimeToolExecutor

_SENTINEL = object()


class RpAgentRuntimeExecutor:
    """Execute one agent turn on the shared runtime graph."""

    def __init__(
        self,
        *,
        tool_executor_factory: Callable[[RpAgentTurnInput], RuntimeToolExecutor],
        event_adapter: TypedSseEventAdapter | None = None,
    ) -> None:
        self._tool_executor_factory = tool_executor_factory
        self._event_adapter = event_adapter or TypedSseEventAdapter()
        self._last_result: RpAgentTurnResult | None = None

    @property
    def last_result(self) -> RpAgentTurnResult | None:
        return self._last_result

    async def run(
        self,
        turn_input: RpAgentTurnInput,
        profile: RuntimeProfile,
        *,
        llm_service: Any,
    ) -> RpAgentTurnResult:
        driver = _RuntimeRunDriver(
            llm_service=llm_service,
            tool_executor=self._tool_executor_factory(turn_input),
            profile=profile,
        )
        result = await driver.run(turn_input)
        self._last_result = result
        return result

    async def run_stream(
        self,
        turn_input: RpAgentTurnInput,
        profile: RuntimeProfile,
        *,
        llm_service: Any,
    ) -> AsyncIterator[str]:
        driver = _RuntimeRunDriver(
            llm_service=llm_service,
            tool_executor=self._tool_executor_factory(turn_input),
            profile=profile,
        )
        async for event in driver.run_stream(turn_input):
            yield self._event_adapter.to_sse_line(event)
        self._last_result = driver.last_result


class _RuntimeRunDriver:
    """Per-run LangGraph driver and node implementation."""

    def __init__(
        self,
        *,
        llm_service: Any,
        tool_executor: RuntimeToolExecutor,
        profile: RuntimeProfile,
    ) -> None:
        self._llm_service = llm_service
        self._tool_executor = tool_executor
        self._profile = profile
        self._langfuse = get_langfuse_service()
        self._event_queue: asyncio.Queue[RuntimeEvent | object] | None = None
        self._event_sequence_no = 0
        self.last_result: RpAgentTurnResult | None = None

    async def run(self, turn_input: RpAgentTurnInput) -> RpAgentTurnResult:
        graph = self._build_graph()
        final_state = await graph.ainvoke(self._initial_state(turn_input))
        self.last_result = self._state_to_result(final_state)
        return self.last_result

    async def run_stream(
        self,
        turn_input: RpAgentTurnInput,
    ) -> AsyncIterator[RuntimeEvent]:
        self._event_queue = asyncio.Queue()

        async def _runner() -> None:
            try:
                graph = self._build_graph()
                final_state = await graph.ainvoke(self._initial_state(turn_input))
                self.last_result = self._state_to_result(final_state)
            except Exception as exc:  # pragma: no cover - defensive safety net
                error = {"message": str(exc), "type": "runtime_execution_failed"}
                await self._emit_event(
                    run_id=turn_input.workspace_id or turn_input.session_id or turn_input.profile_id,
                    event_type="error",
                    payload={"error": error},
                )
                await self._emit_event(
                    run_id=turn_input.workspace_id or turn_input.session_id or turn_input.profile_id,
                    event_type="done",
                    payload={},
                )
                self.last_result = RpAgentTurnResult(
                    status="failed",
                    finish_reason="runtime_execution_failed",
                    assistant_text="",
                    error=error,
                )
            finally:
                if self._event_queue is not None:
                    await self._event_queue.put(_SENTINEL)

        task = asyncio.create_task(_runner())
        try:
            while True:
                item = await self._event_queue.get()
                if item is _SENTINEL:
                    break
                yield item
        finally:
            await task

    def _build_graph(self):
        return build_runtime_graph(
            prepare_input=self._prepare_input,
            derive_turn_goal=self._derive_turn_goal,
            plan_step_slice=self._plan_step_slice,
            build_model_request=self._build_model_request,
            call_model=self._call_model,
            inspect_model_output=self._inspect_model_output,
            execute_tools=self._execute_tools,
            apply_tool_results=self._apply_tool_results,
            assess_progress=self._assess_progress,
            reflect_if_needed=self._reflect_if_needed,
            finalize_success=self._finalize_success,
            finalize_failure=self._finalize_failure,
            route_after_inspect=self._route_after_inspect,
            route_after_assess=self._route_after_assess,
            route_after_reflect=self._route_after_reflect,
        )

    def _initial_state(self, turn_input: RpAgentTurnInput) -> RpAgentRunState:
        return {
            "run_id": uuid.uuid4().hex,
            "profile_id": turn_input.profile_id,
            "run_kind": turn_input.run_kind,
            "status": "received",
            "round_no": 0,
            "stream_mode": turn_input.stream,
            "turn_input": turn_input.model_dump(mode="json", exclude_none=True),
            "normalized_messages": [],
            "tool_definitions": [],
            "pending_tool_calls": [],
            "tool_invocations": [],
            "tool_results": [],
            "latest_tool_batch": [],
            "assistant_text": "",
            "warnings": [],
            "finish_reason": None,
            "error": None,
            "turn_goal": None,
            "working_plan": None,
            "pending_obligation": None,
            "last_failure": None,
            "reflection_ticket": None,
            "completion_guard": None,
            "cognitive_state": self._context_bundle(turn_input).get("cognitive_state"),
            "cognitive_state_summary": self._context_bundle(turn_input).get(
                "cognitive_state_summary"
            ),
            "repair_route": None,
            "next_action": "build_model_request",
            "schema_retry_count": 0,
            "error_event_emitted": False,
        }

    def _prepare_input(self, state: RpAgentRunState) -> RpAgentRunState:
        turn_input = self._turn_input(state)
        normalized_messages: list[dict[str, Any]] = []
        system_prompt = str(turn_input.context_bundle.get("system_prompt") or "")
        if system_prompt:
            normalized_messages.append(
                ChatMessage(role="system", content=system_prompt).model_dump(
                    mode="json",
                    exclude_none=True,
                )
            )
        for message in turn_input.conversation_messages:
            normalized_messages.append(self._normalize_message_dict(message))
        normalized_messages.append(
            ChatMessage(
                role="user",
                content=turn_input.user_visible_request or "",
            ).model_dump(mode="json", exclude_none=True)
        )
        return {
            "status": "prepared",
            "normalized_messages": normalized_messages,
        }

    def _derive_turn_goal(self, state: RpAgentRunState) -> RpAgentRunState:
        turn_input = self._turn_input(state)
        context_bundle = self._context_bundle(turn_input)
        current_step = str(context_bundle.get("current_step") or "unknown_step")
        pending_obligation = self._pending_obligation(state)
        cognitive_state_summary = self._cognitive_state_summary(state)
        user_prompt = str(turn_input.user_visible_request or "").strip()
        current_snapshot = self._context_packet(state).get("current_draft_snapshot") or {}

        if pending_obligation is not None and pending_obligation.unresolved:
            if pending_obligation.obligation_type == "repair_tool_call":
                goal = SetupTurnGoal(
                    current_step=current_step,
                    goal_type="recover_from_tool_failure",
                    goal_summary=(
                        f"Repair the failed tool call for {pending_obligation.tool_name or 'setup tool'}."
                    ),
                    success_criteria=[
                        "Emit a corrected tool call or convert the turn into a targeted user question.",
                        "Clear the current repair obligation before finishing.",
                    ],
                )
            elif pending_obligation.obligation_type == "ask_user_for_missing_info":
                goal = SetupTurnGoal(
                    current_step=current_step,
                    goal_type="clarify_user_intent",
                    goal_summary="Ask the user for the missing information required to continue setup.",
                    success_criteria=[
                        "Ask one targeted user-facing clarification question.",
                        "Do not pretend the step is complete yet.",
                    ],
                )
            elif pending_obligation.obligation_type == "reconcile_after_user_edit":
                goal = SetupTurnGoal(
                    current_step=current_step,
                    goal_type="reconcile_after_user_edit",
                    goal_summary=(
                        "Reconcile the discussion state against the latest user-edited draft "
                        "before making more commit-oriented moves."
                    ),
                    success_criteria=[
                        "Refresh the discussion map from the latest draft context.",
                        "Do not treat stale truth candidates as ready for review.",
                    ],
                )
            elif pending_obligation.obligation_type == "continue_after_tool_failure":
                goal = SetupTurnGoal(
                    current_step=current_step,
                    goal_type="recover_from_tool_failure",
                    goal_summary=(
                        "Recover from the most recent tool failure and continue advancing the "
                        "same setup objective instead of switching to commit preparation."
                    ),
                    success_criteria=[
                        "Address the failed tool outcome in the current topic.",
                        "Continue discussion, ask the user, or retry with a better action as appropriate.",
                    ],
                )
            else:
                goal = SetupTurnGoal(
                    current_step=current_step,
                    goal_type="prepare_commit_intent",
                    goal_summary="Reassess whether the step is truly ready for review or commit.",
                    success_criteria=[
                        "Do not propose commit while unresolved blockers remain.",
                        "Continue discussion or ask a targeted question instead of forcing commit.",
                    ],
                )
        elif cognitive_state_summary is not None and cognitive_state_summary.invalidated:
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="reconcile_after_user_edit",
                goal_summary=(
                    "The current discussion state is stale relative to the latest draft or "
                    "rejection feedback. Reconcile it before proposing commit."
                ),
                success_criteria=[
                    "Update the discussion map or chunk candidates to match the latest draft.",
                    "Do not call setup.proposal.commit while the cognitive state is invalidated.",
                ],
            )
        elif self._user_requests_commit(user_prompt):
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="prepare_commit_intent",
                goal_summary="Check whether the current step is converged enough for a commit proposal.",
                success_criteria=[
                    "Verify there are no unresolved blocking questions.",
                    "Only call setup.proposal.commit when the step is actually ready.",
                ],
            )
        elif not current_snapshot:
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="fill_missing_step_fields",
                goal_summary="Fill the minimum missing fields for the current setup step.",
                success_criteria=[
                    "Identify the highest-priority missing information.",
                    "Either patch the draft or ask the user for the missing inputs.",
                ],
            )
        elif (
            cognitive_state_summary is not None
            and cognitive_state_summary.candidate_titles
            and cognitive_state_summary.truth_write_status is None
        ):
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="write_draft_truth",
                goal_summary=(
                    "A chunk candidate is emerging; decide whether one candidate should now be "
                    "written into the draft."
                ),
                success_criteria=[
                    "Only call setup.truth.write when one candidate is stable enough.",
                    "Keep unresolved issues visible instead of pretending the draft is finalized.",
                ],
            )
        elif (
            cognitive_state_summary is not None
            and cognitive_state_summary.candidate_titles
        ):
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="refine_chunk_candidate",
                goal_summary="Refine the current chunk candidates until they are truly usable.",
                success_criteria=[
                    "Clarify open issues on the active chunk candidates.",
                    "Promote only candidates that are specific enough to support draft writing.",
                ],
            )
        else:
            goal = SetupTurnGoal(
                current_step=current_step,
                goal_type="brainstorm_and_clarify",
                goal_summary="Advance the current setup discussion toward a more converged state.",
                success_criteria=[
                    "Prefer concrete progress over vague discussion.",
                    "Keep the turn aligned with the current setup step.",
                ],
            )

        return {
            "status": "goal_derived",
            "turn_goal": goal.model_dump(mode="json", exclude_none=True),
        }

    def _plan_step_slice(self, state: RpAgentRunState) -> RpAgentRunState:
        goal_payload = state.get("turn_goal") or {}
        goal = SetupTurnGoal.model_validate(goal_payload)
        context_packet = self._context_packet(state)
        context_bundle = self._context_bundle(self._turn_input(state))
        pending_obligation = self._pending_obligation(state)
        cognitive_state_summary = self._cognitive_state_summary(state)

        missing_information = list(
            pending_obligation.required_fields if pending_obligation is not None else []
        )
        if not missing_information and not context_packet.get("current_draft_snapshot"):
            missing_information.append(f"{goal.current_step}:core_fields")
        for question_text in context_bundle.get("open_question_texts") or []:
            text = str(question_text or "").strip()
            if text and text not in missing_information:
                missing_information.append(text)

        discussion_actions: list[str] = []
        if cognitive_state_summary is not None and cognitive_state_summary.invalidated:
            discussion_actions.append("reconcile_discussion_state_from_latest_draft")
        if missing_information:
            discussion_actions.append("resolve_missing_information")
        if (
            cognitive_state_summary is not None
            and cognitive_state_summary.unresolved_conflicts
        ):
            discussion_actions.append("resolve_unresolved_conflicts")
        if not discussion_actions:
            discussion_actions.append("advance_current_step")

        plan = SetupWorkingPlan(
            missing_information=missing_information,
            discussion_actions=discussion_actions,
            candidate_targets=(
                list(cognitive_state_summary.candidate_titles)
                if cognitive_state_summary is not None
                else []
            ),
            draft_write_targets=(
                self._patch_targets_for_step(goal.current_step)
                if (
                    cognitive_state_summary is not None
                    and cognitive_state_summary.candidate_titles
                )
                else []
            ),
            patch_targets=self._patch_targets_for_step(goal.current_step),
            question_targets=list(missing_information),
            commit_readiness_checks=self._commit_readiness_checks(goal.current_step),
            current_priority=(
                goal.goal_summary
                if goal.goal_type not in {"patch_draft", "brainstorm_and_clarify"}
                else f"Advance {goal.current_step} with the highest-value patch."
            ),
        )
        return {
            "status": "planned",
            "working_plan": plan.model_dump(mode="json", exclude_none=True),
        }

    def _build_model_request(self, state: RpAgentRunState) -> RpAgentRunState:
        turn_input = self._turn_input(state)
        visible_tool_names = self._visible_tool_names(turn_input)
        tool_definitions = (
            self._tool_executor.get_openai_tool_definitions(
                visible_tool_names=visible_tool_names
            )
            if self._profile.supports_tools
            else []
        )
        provider_payload = turn_input.metadata.get("provider") or {}
        provider = (
            ProviderConfig.model_validate(provider_payload)
            if provider_payload
            else None
        )
        request = ChatCompletionRequest(
            model=str(turn_input.metadata.get("model_name") or turn_input.model_id),
            model_id=turn_input.model_id,
            messages=self._build_request_messages(state),
            stream=bool(state.get("stream_mode")),
            stream_event_mode="typed" if state.get("stream_mode") else None,
            provider_id=turn_input.provider_id,
            provider=provider,
            enable_tools=bool(tool_definitions),
            tools=tool_definitions or None,
            tool_choice="auto" if tool_definitions else None,
        )
        return {
            "status": "model_request_built",
            "round_no": int(state.get("round_no") or 0) + 1,
            "tool_definitions": tool_definitions,
            "latest_request": request.model_dump(mode="json", exclude_none=True),
        }

    async def _call_model(self, state: RpAgentRunState) -> RpAgentRunState:
        request = ChatCompletionRequest.model_validate(state["latest_request"])
        if state.get("stream_mode"):
            return await self._call_model_stream(state, request)
        return await self._call_model_non_stream(request)

    async def _call_model_non_stream(
        self,
        request: ChatCompletionRequest,
    ) -> RpAgentRunState:
        with self._langfuse.start_as_current_observation(
            name="rp.runtime.model_call",
            as_type="generation",
            model=request.model,
            input={
                "messages": request.model_dump(mode="json").get("messages", []),
                "tool_count": len(request.tools or []),
                "stream": False,
            },
            model_parameters={
                "stream": False,
                "tool_choice": request.tool_choice,
            },
        ) as generation:
            response = self._coerce_response_dict(
                await self._llm_service.chat_completion(request)
            )
            generation.update(
                output=self._extract_message_payload(response),
                usage_details=(
                    dict(response.get("usage"))
                    if isinstance(response.get("usage"), dict)
                    else None
                ),
            )
        return {
            "status": "model_called",
            "latest_response": response,
        }

    async def _call_model_stream(
        self,
        state: RpAgentRunState,
        request: ChatCompletionRequest,
    ) -> RpAgentRunState:
        accumulated_tool_calls: dict[int, dict[str, Any]] = {}
        accumulated_text = ""
        error_payload: dict[str, Any] | None = None
        usage_details: dict[str, int] | None = None
        run_id = str(state["run_id"])
        with self._langfuse.start_as_current_observation(
            name="rp.runtime.model_call.stream",
            as_type="generation",
            model=request.model,
            input={
                "messages": request.model_dump(mode="json").get("messages", []),
                "tool_count": len(request.tools or []),
                "stream": True,
            },
            model_parameters={
                "stream": True,
                "tool_choice": request.tool_choice,
            },
        ) as generation:
            async for line in self._llm_service.chat_completion_stream(request):
                payload = self._parse_sse_payload(line)
                if payload is None:
                    continue

                event_type = str(payload.get("type") or "")
                if event_type == "done":
                    break
                if event_type in {"thinking_delta", "text_delta"}:
                    if event_type == "text_delta":
                        accumulated_text += str(payload.get("delta") or "")
                    await self._emit_event(
                        run_id=run_id,
                        event_type=event_type,
                        payload={"delta": str(payload.get("delta") or "")},
                    )
                    continue
                if event_type == "tool_call":
                    raw_calls = payload.get("tool_calls", [])
                    self._merge_stream_tool_calls(accumulated_tool_calls, raw_calls)
                    await self._emit_event(
                        run_id=run_id,
                        event_type="tool_call",
                        payload={"tool_calls": raw_calls if isinstance(raw_calls, list) else []},
                    )
                    continue
                if event_type == "error":
                    error_payload = payload.get("error") or {
                        "message": "model_stream_failed",
                        "type": "model_stream_failed",
                    }
                    await self._emit_event(
                        run_id=run_id,
                        event_type="error",
                        payload={"error": error_payload},
                    )
                    break
                if event_type == "usage":
                    usage_details = {
                        "prompt_tokens": int(payload.get("prompt_tokens") or 0),
                        "completion_tokens": int(payload.get("completion_tokens") or 0),
                        "total_tokens": int(payload.get("total_tokens") or 0),
                    }

                passthrough_payload = dict(payload)
                passthrough_payload.pop("type", None)
                await self._emit_event(
                    run_id=run_id,
                    event_type=event_type,
                    payload=passthrough_payload,
                )

            generation.update(
                output={
                    "content": accumulated_text or None,
                    "tool_calls": self._finalize_stream_tool_calls(accumulated_tool_calls),
                    "error": error_payload,
                },
                usage_details=usage_details,
            )

        response_message = {
            "content": accumulated_text or None,
            "tool_calls": self._finalize_stream_tool_calls(accumulated_tool_calls),
        }
        latest_response: dict[str, Any] = {"message": response_message}
        if usage_details is not None:
            latest_response["usage"] = usage_details
        update: RpAgentRunState = {
            "status": "model_called",
            "latest_response": latest_response,
            "assistant_text": accumulated_text,
        }
        if error_payload is not None:
            update["error"] = error_payload
            update["finish_reason"] = "upstream_error"
            update["error_event_emitted"] = True
        return update

    def _inspect_model_output(self, state: RpAgentRunState) -> RpAgentRunState:
        message_payload = self._extract_message_payload(state.get("latest_response") or {})
        assistant_text = str(message_payload.get("content") or "")
        runtime_tool_calls = [
            RuntimeToolCall(
                call_id=self._tool_call_id(call),
                tool_name=self._tool_name(call),
                arguments=self._tool_arguments(call),
                source_round=int(state.get("round_no") or 0),
            )
            for call in message_payload.get("tool_calls", [])
            if isinstance(call, dict)
        ]
        normalized_messages = list(state.get("normalized_messages", []))
        if assistant_text and not runtime_tool_calls:
            normalized_messages.append(
                ChatMessage(role="assistant", content=assistant_text).model_dump(
                    mode="json",
                    exclude_none=True,
                )
            )
        update: RpAgentRunState = {
            "status": "model_inspected",
            "assistant_text": assistant_text,
            "normalized_messages": normalized_messages,
            "pending_tool_calls": [
                call.model_dump(mode="json", exclude_none=True)
                for call in runtime_tool_calls
            ],
            "completion_guard": None,
        }
        if state.get("error"):
            update["next_action"] = "finalize_failure"
            return update
        if runtime_tool_calls and self._contains_blocked_commit_proposal(state, runtime_tool_calls):
            context_bundle = self._context_bundle(self._turn_input(state))
            reflection_ticket = ReflectionTriggerPolicy.blocked_commit_ticket(
                context_bundle=context_bundle,
                cognitive_state_summary=self._cognitive_state_summary(state),
            )
            update["pending_tool_calls"] = []
            update["pending_obligation"] = SetupPendingObligation(
                obligation_type="reassess_commit_readiness",
                reason=str(
                    (reflection_ticket or {}).get("summary")
                    or "Commit readiness must be reassessed before proposing commit."
                ),
                tool_name="setup.proposal.commit",
            ).model_dump(mode="json", exclude_none=True)
            update["reflection_ticket"] = reflection_ticket
            update["warnings"] = list(state.get("warnings", [])) + ["commit_proposal_blocked"]
            update["next_action"] = "reflect_if_needed"
            return update
        if runtime_tool_calls:
            update["reflection_ticket"] = None
            update["next_action"] = "execute_tools"
            return update
        decision = CompletionGuardPolicy.assess(
            assistant_text=assistant_text,
            pending_obligation=self._pending_obligation(state),
            reflection_ticket=self._reflection_ticket(state),
            cognitive_state_summary=self._cognitive_state_summary(state),
        )
        update["completion_guard"] = decision.get("completion_guard")
        if "pending_obligation" in decision:
            update["pending_obligation"] = decision.get("pending_obligation")
        if "reflection_ticket" in decision:
            update["reflection_ticket"] = decision.get("reflection_ticket")
        if decision.get("allow_finalize"):
            update["finish_reason"] = str(
                decision.get("finish_reason")
                or FinishPolicy.completed_text_finish_reason(assistant_text)
            )
            update["next_action"] = "finalize_success"
            return update
        update["next_action"] = "reflect_if_needed"
        return update

    async def _execute_tools(self, state: RpAgentRunState) -> RpAgentRunState:
        turn_input = self._turn_input(state)
        visible_tool_names = self._visible_tool_names(turn_input)
        call_batch = [
            RuntimeToolCall.model_validate(item)
            for item in state.get("pending_tool_calls", [])
        ]
        aggregated_invocations = list(state.get("tool_invocations", []))
        aggregated_results = list(state.get("tool_results", []))
        latest_batch: list[dict[str, Any]] = []
        run_id = str(state["run_id"])

        for call in call_batch:
            aggregated_invocations.append(call.model_dump(mode="json", exclude_none=True))
            await self._emit_event(
                run_id=run_id,
                event_type="tool_started",
                payload={"call_id": call.call_id, "tool_name": call.tool_name},
            )
            with self._langfuse.start_as_current_observation(
                name=f"rp.runtime.tool:{call.tool_name}",
                as_type="tool",
                input={
                    "tool_name": call.tool_name,
                    "arguments": dict(call.arguments),
                    "visible_tool_names": list(visible_tool_names),
                },
            ) as tool_observation:
                result = await self._tool_executor.execute_tool_call(
                    call,
                    visible_tool_names=visible_tool_names,
                )
                tool_observation.update(
                    output={
                        "success": result.success,
                        "tool_name": result.tool_name,
                        "error_code": result.error_code,
                        "content_text": result.content_text,
                        "structured_payload": result.structured_payload,
                    }
                )
            latest_batch.append(result.model_dump(mode="json", exclude_none=True))
            aggregated_results.append(result.model_dump(mode="json", exclude_none=True))
            if result.success:
                await self._emit_event(
                    run_id=run_id,
                    event_type="tool_result",
                    payload={
                        "call_id": result.call_id,
                        "tool_name": result.tool_name,
                        "result": result.content_text,
                    },
                )
            else:
                await self._emit_event(
                    run_id=run_id,
                    event_type="tool_error",
                    payload={
                        "call_id": result.call_id,
                        "tool_name": result.tool_name,
                        "error": result.content_text,
                    },
                )
                if ToolFailureClassifier.classify(result) == "unrecoverable":
                    break

        return {
            "status": "tools_executed",
            "tool_invocations": aggregated_invocations,
            "tool_results": aggregated_results,
            "latest_tool_batch": latest_batch,
        }

    def _apply_tool_results(self, state: RpAgentRunState) -> RpAgentRunState:
        normalized_messages = list(state.get("normalized_messages", []))
        tool_calls = [
            RuntimeToolCall.model_validate(item)
            for item in state.get("pending_tool_calls", [])
        ]
        cognitive_state = state.get("cognitive_state")
        cognitive_state_summary = state.get("cognitive_state_summary")
        if tool_calls:
            normalized_messages.append(
                ChatMessage(
                    role="assistant",
                    content=state.get("assistant_text") or "",
                    tool_calls=[
                        self._runtime_tool_call_to_openai(call)
                        for call in tool_calls
                    ],
                ).model_dump(mode="json", exclude_none=True)
            )
        for item in state.get("latest_tool_batch", []):
            result = RuntimeToolResult.model_validate(item)
            normalized_messages.append(
                ChatMessage(
                    role="tool",
                    name=result.tool_name,
                    tool_call_id=result.call_id,
                    content=result.content_text,
                ).model_dump(mode="json", exclude_none=True)
            )
            content_payload = (
                result.structured_payload.get("content_payload")
                if isinstance(result.structured_payload, dict)
                else None
            )
            if isinstance(content_payload, dict):
                if isinstance(content_payload.get("cognitive_state_snapshot"), dict):
                    cognitive_state = content_payload["cognitive_state_snapshot"]
                if isinstance(content_payload.get("cognitive_state_summary"), dict):
                    cognitive_state_summary = content_payload["cognitive_state_summary"]
        return {
            "status": "tool_results_applied",
            "normalized_messages": normalized_messages,
            "pending_tool_calls": [],
            "cognitive_state": cognitive_state,
            "cognitive_state_summary": cognitive_state_summary,
        }

    def _assess_progress(self, state: RpAgentRunState) -> RpAgentRunState:
        latest_batch = [
            RuntimeToolResult.model_validate(item)
            for item in state.get("latest_tool_batch", [])
        ]
        if not latest_batch:
            decision = CompletionGuardPolicy.assess(
                assistant_text=str(state.get("assistant_text") or ""),
                pending_obligation=self._pending_obligation(state),
                reflection_ticket=self._reflection_ticket(state),
                cognitive_state_summary=self._cognitive_state_summary(state),
            )
            update: RpAgentRunState = {
                "status": "assessed",
                "completion_guard": decision.get("completion_guard"),
            }
            if "pending_obligation" in decision:
                update["pending_obligation"] = decision.get("pending_obligation")
            if "reflection_ticket" in decision:
                update["reflection_ticket"] = decision.get("reflection_ticket")
            if decision.get("allow_finalize"):
                update["next_action"] = "finalize_success"
                update["finish_reason"] = str(
                    decision.get("finish_reason")
                    or FinishPolicy.completed_text_finish_reason(
                        str(state.get("assistant_text") or "")
                    )
                )
                return update
            update["next_action"] = "reflect_if_needed"
            return update

        decision = RepairDecisionPolicy.assess(
            profile=self._profile,
            tool_results=latest_batch,
            schema_retry_count=int(state.get("schema_retry_count") or 0),
            round_no=int(state.get("round_no") or 0),
        )
        warnings = list(state.get("warnings", []))
        if decision.get("warning"):
            warnings.append(str(decision["warning"]))

        if decision["action"] == "continue":
            update: RpAgentRunState = {
                "status": "assessed",
                "next_action": (
                    "reflect_if_needed"
                    if decision.get("reflection_ticket") is not None
                    else "derive_turn_goal"
                ),
                "warnings": warnings,
                "schema_retry_count": decision.get(
                    "schema_retry_count",
                    int(state.get("schema_retry_count") or 0),
                ),
                "pending_obligation": decision.get("pending_obligation"),
                "reflection_ticket": decision.get("reflection_ticket"),
                "completion_guard": decision.get("completion_guard"),
                "repair_route": (
                    decision.get("last_failure", {}).get("failure_category")
                    if isinstance(decision.get("last_failure"), dict)
                    else state.get("repair_route")
                ),
            }
            if "last_failure" in decision:
                update["last_failure"] = decision.get("last_failure")
            return update

        return {
            "status": "failed",
            "next_action": "finalize_failure",
            "finish_reason": str(decision.get("finish_reason") or "runtime_failed"),
            "warnings": warnings,
            "error": decision.get("error"),
            "last_failure": decision.get("last_failure"),
        }

    def _reflect_if_needed(self, state: RpAgentRunState) -> RpAgentRunState:
        decision = ReflectionTriggerPolicy.assess(
            profile=self._profile,
            reflection_ticket=self._reflection_ticket(state),
            pending_obligation=self._pending_obligation(state),
            schema_retry_count=int(state.get("schema_retry_count") or 0),
            round_no=int(state.get("round_no") or 0),
        )
        warnings = list(state.get("warnings", []))
        if decision.get("warning"):
            warnings.append(str(decision["warning"]))

        if decision["action"] == "continue":
            return {
                "status": "reflected",
                "next_action": "derive_turn_goal",
                "warnings": warnings,
                "reflection_ticket": None,
            }

        return {
            "status": "failed",
            "next_action": "finalize_failure",
            "finish_reason": str(decision.get("finish_reason") or "runtime_failed"),
            "warnings": warnings,
            "error": decision.get("error"),
            "reflection_ticket": None,
        }

    async def _finalize_success(self, state: RpAgentRunState) -> RpAgentRunState:
        await self._emit_event(
            run_id=str(state["run_id"]),
            event_type="done",
            payload={},
        )
        return {
            "status": "completed",
            "finish_reason": state.get("finish_reason")
            or FinishPolicy.completed_text_finish_reason(
                str(state.get("assistant_text") or "")
            ),
        }

    async def _finalize_failure(self, state: RpAgentRunState) -> RpAgentRunState:
        error = state.get("error") or {
            "message": "runtime_failed",
            "type": str(state.get("finish_reason") or "runtime_failed"),
        }
        if not state.get("error_event_emitted"):
            await self._emit_event(
                run_id=str(state["run_id"]),
                event_type="error",
                payload={"error": error},
            )
        await self._emit_event(
            run_id=str(state["run_id"]),
            event_type="done",
            payload={},
        )
        return {
            "status": "failed",
            "error": error,
            "finish_reason": str(state.get("finish_reason") or "runtime_failed"),
            "error_event_emitted": True,
        }

    @staticmethod
    def _route_after_inspect(state: RpAgentRunState) -> str:
        return str(state.get("next_action") or "finalize_success")

    @staticmethod
    def _route_after_assess(state: RpAgentRunState) -> str:
        return str(state.get("next_action") or "finalize_failure")

    @staticmethod
    def _route_after_reflect(state: RpAgentRunState) -> str:
        return str(state.get("next_action") or "finalize_failure")

    async def _emit_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self._event_queue is None:
            return
        self._event_sequence_no += 1
        await self._event_queue.put(
            RuntimeEvent(
                type=event_type,
                run_id=run_id,
                sequence_no=self._event_sequence_no,
                payload=payload,
            )
        )

    def _state_to_result(self, state: RpAgentRunState) -> RpAgentTurnResult:
        error = state.get("error")
        status = "failed" if error else "completed"
        turn_input = self._turn_input(state)
        context_bundle = self._context_bundle(turn_input)
        return RpAgentTurnResult(
            status=status,
            finish_reason=str(
                state.get("finish_reason")
                or (
                    "runtime_failed"
                    if error
                    else FinishPolicy.completed_text_finish_reason(
                        str(state.get("assistant_text") or "")
                    )
                )
            ),
            assistant_text=str(state.get("assistant_text") or ""),
            tool_invocations=[
                RuntimeToolCall.model_validate(item)
                for item in state.get("tool_invocations", [])
            ],
            tool_results=[
                RuntimeToolResult.model_validate(item)
                for item in state.get("tool_results", [])
            ],
            warnings=list(state.get("warnings", [])),
            structured_payload={
                "profile_id": state.get("profile_id"),
                "round_no": state.get("round_no"),
                "tool_invocation_count": len(state.get("tool_invocations", [])),
                "tool_result_count": len(state.get("tool_results", [])),
                "tool_scope": list(turn_input.tool_scope),
                "request_metrics": {
                    "system_prompt_chars": len(
                        str(context_bundle.get("system_prompt") or "")
                    ),
                    "user_prompt_chars": len(
                        str(turn_input.user_visible_request or "")
                    ),
                    "conversation_message_count": len(
                        turn_input.conversation_messages
                    ),
                    "tool_scope_count": len(turn_input.tool_scope),
                },
                "request_context": {
                    "current_step": context_bundle.get("current_step"),
                    "step_readiness": context_bundle.get("step_readiness"),
                    "open_question_count": context_bundle.get("open_question_count"),
                    "blocking_open_question_count": context_bundle.get(
                        "blocking_open_question_count"
                    ),
                    "last_proposal_status": context_bundle.get("last_proposal_status"),
                    "cognitive_state_invalidated": context_bundle.get(
                        "cognitive_state_invalidated"
                    ),
                },
                "latest_tool_batch": list(state.get("latest_tool_batch", [])),
                "latest_response": state.get("latest_response") or {},
                "turn_goal": state.get("turn_goal"),
                "working_plan": state.get("working_plan"),
                "pending_obligation": state.get("pending_obligation"),
                "last_failure": state.get("last_failure"),
                "reflection_ticket": state.get("reflection_ticket"),
                "completion_guard": state.get("completion_guard"),
                "cognitive_state": state.get("cognitive_state"),
                "cognitive_state_summary": state.get("cognitive_state_summary"),
                "repair_route": state.get("repair_route"),
            },
            error=error,
        )

    @staticmethod
    def _turn_input(state: RpAgentRunState) -> RpAgentTurnInput:
        return RpAgentTurnInput.model_validate(state["turn_input"])

    def _visible_tool_names(self, turn_input: RpAgentTurnInput) -> list[str]:
        return list(turn_input.tool_scope or self._profile.visible_tool_names)

    def _build_request_messages(self, state: RpAgentRunState) -> list[ChatMessage]:
        base_messages = [
            ChatMessage.model_validate(message)
            for message in state.get("normalized_messages", [])
        ]
        overlay_message = self._runtime_overlay_message(state)
        if overlay_message is None:
            return base_messages
        if base_messages and base_messages[0].role == "system":
            return [base_messages[0], overlay_message, *base_messages[1:]]
        return [overlay_message, *base_messages]

    def _runtime_overlay_message(self, state: RpAgentRunState) -> ChatMessage | None:
        payload = {
            "turn_goal": state.get("turn_goal"),
            "working_plan": state.get("working_plan"),
            "pending_obligation": state.get("pending_obligation"),
            "last_failure": state.get("last_failure"),
            "reflection_ticket": state.get("reflection_ticket"),
            "cognitive_state_summary": state.get("cognitive_state_summary"),
        }
        if all(value in (None, {}, []) for value in payload.values()):
            return None

        return ChatMessage(
            role="system",
            content=(
                "Runtime turn state follows as JSON. Treat it as internal execution guidance.\n"
                "Use it to decide whether you must repair a tool call, ask the user for missing "
                "information, continue discussion, reconcile stale setup state, or avoid "
                "proposing commit yet.\n"
                "If pending_obligation is repair_tool_call, do not stop with explanation alone.\n"
                "If pending_obligation is ask_user_for_missing_info, your next visible reply must ask "
                "the missing question explicitly.\n"
                "If reflection_ticket says block_commit, do not call setup.proposal.commit in this turn.\n"
                "If cognitive_state_summary.invalidated is true, refresh discussion/chunk state before commit.\n"
                f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            ),
        )

    @staticmethod
    def _context_bundle(turn_input: RpAgentTurnInput) -> dict[str, Any]:
        return (
            dict(turn_input.context_bundle)
            if isinstance(turn_input.context_bundle, dict)
            else {}
        )

    def _context_packet(self, state: RpAgentRunState) -> dict[str, Any]:
        context_bundle = self._context_bundle(self._turn_input(state))
        packet = context_bundle.get("context_packet")
        return dict(packet) if isinstance(packet, dict) else {}

    @staticmethod
    def _user_requests_commit(user_prompt: str) -> bool:
        lowered = user_prompt.lower()
        return any(keyword in lowered for keyword in ("commit", "review", "freeze"))

    @staticmethod
    def _patch_targets_for_step(current_step: str) -> list[str]:
        return {
            "story_config": ["story_config_draft"],
            "writing_contract": ["writing_contract_draft"],
            "foundation": ["foundation_draft.entries"],
            "longform_blueprint": ["longform_blueprint_draft"],
        }.get(current_step, ["current_step_draft"])

    @staticmethod
    def _commit_readiness_checks(current_step: str) -> list[str]:
        return [
            f"{current_step}:blocking_questions_closed",
            f"{current_step}:draft_is_converged",
            f"{current_step}:user_feedback_addressed",
        ]

    @staticmethod
    def _pending_obligation(state: RpAgentRunState) -> SetupPendingObligation | None:
        payload = state.get("pending_obligation")
        if not isinstance(payload, dict):
            return None
        return SetupPendingObligation.model_validate(payload)

    @staticmethod
    def _reflection_ticket(state: RpAgentRunState) -> SetupReflectionTicket | None:
        payload = state.get("reflection_ticket")
        if not isinstance(payload, dict):
            return None
        return SetupReflectionTicket.model_validate(payload)

    @staticmethod
    def _cognitive_state(state: RpAgentRunState) -> SetupCognitiveStateSnapshot | None:
        payload = state.get("cognitive_state")
        if not isinstance(payload, dict):
            return None
        return SetupCognitiveStateSnapshot.model_validate(payload)

    @staticmethod
    def _cognitive_state_summary(state: RpAgentRunState) -> SetupCognitiveStateSummary | None:
        payload = state.get("cognitive_state_summary")
        if not isinstance(payload, dict):
            return None
        return SetupCognitiveStateSummary.model_validate(payload)

    def _contains_blocked_commit_proposal(
        self,
        state: RpAgentRunState,
        runtime_tool_calls: list[RuntimeToolCall],
    ) -> bool:
        if not any(self._is_commit_proposal_tool(call.tool_name) for call in runtime_tool_calls):
            return False
        context_bundle = self._context_bundle(self._turn_input(state))
        return (
            ReflectionTriggerPolicy.blocked_commit_ticket(
                context_bundle=context_bundle,
                cognitive_state_summary=self._cognitive_state_summary(state),
            )
            is not None
        )

    @staticmethod
    def _is_commit_proposal_tool(tool_name: str) -> bool:
        return tool_name.endswith("setup.proposal.commit")

    @staticmethod
    def _normalize_message_dict(message: dict[str, Any]) -> dict[str, Any]:
        return ChatMessage.model_validate(
            {
                "role": message.get("role"),
                "content": message.get("content"),
                "name": message.get("name"),
                "tool_calls": message.get("tool_calls"),
                "tool_call_id": message.get("tool_call_id"),
            }
        ).model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _coerce_response_dict(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            return response.model_dump(exclude_none=True)
        if isinstance(response, dict):
            return response
        raise TypeError(f"Unsupported chat completion response type: {type(response)!r}")

    @staticmethod
    def _extract_message_payload(response: dict[str, Any]) -> dict[str, Any]:
        message = response.get("message")
        if isinstance(message, dict):
            return message
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                nested = choice.get("message")
                if isinstance(nested, dict):
                    return nested
        return {}

    @staticmethod
    def _runtime_tool_call_to_openai(call: RuntimeToolCall) -> dict[str, Any]:
        return {
            "id": call.call_id,
            "type": "function",
            "function": {
                "name": call.tool_name,
                "arguments": json.dumps(
                    call.arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        }

    @staticmethod
    def _merge_stream_tool_calls(
        accumulators: dict[int, dict[str, Any]],
        raw_calls: Any,
    ) -> None:
        if not isinstance(raw_calls, list):
            return

        for position, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, dict):
                continue

            index = raw_call.get("index")
            key = index if isinstance(index, int) else position
            current = accumulators.setdefault(key, {"type": "function", "function": {}})

            for field, value in raw_call.items():
                if field in {"index", "function"}:
                    continue
                if value is None:
                    continue
                if isinstance(value, str) and not value:
                    continue
                current[field] = value

            raw_function = raw_call.get("function")
            if not isinstance(raw_function, dict):
                continue

            current_function = current.setdefault("function", {})
            for field, value in raw_function.items():
                if field == "arguments":
                    if isinstance(value, str):
                        existing = current_function.get("arguments")
                        current_function["arguments"] = (
                            (existing if isinstance(existing, str) else "") + value
                        )
                    elif value is not None:
                        current_function["arguments"] = value
                    continue
                if value is None:
                    continue
                if isinstance(value, str) and not value:
                    continue
                current_function[field] = value

    @staticmethod
    def _finalize_stream_tool_calls(
        accumulators: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [accumulators[key] for key in sorted(accumulators)]

    @staticmethod
    def _tool_call_id(call: dict[str, Any]) -> str:
        existing = call.get("id")
        if existing:
            return str(existing)
        generated = f"call_{uuid.uuid4().hex[:8]}"
        call["id"] = generated
        return generated

    @staticmethod
    def _tool_name(call: dict[str, Any]) -> str:
        function = call.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return ""

    @staticmethod
    def _tool_arguments(call: dict[str, Any]) -> dict[str, Any]:
        function = call.get("function")
        raw_args = function.get("arguments", "{}") if isinstance(function, dict) else "{}"
        if isinstance(raw_args, dict):
            return raw_args
        if not isinstance(raw_args, str):
            return {}
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_sse_payload(line: str) -> dict[str, Any] | None:
        if not line.startswith("data: "):
            return None
        data_str = line[6:].strip()
        if not data_str or data_str == "[DONE]":
            return None
        try:
            return json.loads(data_str)
        except json.JSONDecodeError:
            return None
