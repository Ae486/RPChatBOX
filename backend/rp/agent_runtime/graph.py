"""LangGraph builder for the RP runtime loop."""
from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from .state import RpAgentRunState


def build_runtime_graph(
    *,
    prepare_input: Callable[[RpAgentRunState], RpAgentRunState],
    derive_turn_goal: Callable[[RpAgentRunState], RpAgentRunState],
    plan_step_slice: Callable[[RpAgentRunState], RpAgentRunState],
    build_model_request: Callable[[RpAgentRunState], RpAgentRunState],
    call_model: Callable[[RpAgentRunState], RpAgentRunState],
    inspect_model_output: Callable[[RpAgentRunState], RpAgentRunState],
    execute_tools: Callable[[RpAgentRunState], RpAgentRunState],
    apply_tool_results: Callable[[RpAgentRunState], RpAgentRunState],
    assess_progress: Callable[[RpAgentRunState], RpAgentRunState],
    reflect_if_needed: Callable[[RpAgentRunState], RpAgentRunState],
    finalize_success: Callable[[RpAgentRunState], RpAgentRunState],
    finalize_failure: Callable[[RpAgentRunState], RpAgentRunState],
    route_after_inspect: Callable[[RpAgentRunState], str],
    route_after_assess: Callable[[RpAgentRunState], str],
    route_after_reflect: Callable[[RpAgentRunState], str],
):
    """Compile the minimal runtime execution graph."""

    builder = StateGraph(RpAgentRunState)
    builder.add_node("prepare_input", prepare_input)
    builder.add_node("derive_turn_goal", derive_turn_goal)
    builder.add_node("plan_step_slice", plan_step_slice)
    builder.add_node("build_model_request", build_model_request)
    builder.add_node("call_model", call_model)
    builder.add_node("inspect_model_output", inspect_model_output)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("apply_tool_results", apply_tool_results)
    builder.add_node("assess_progress", assess_progress)
    builder.add_node("reflect_if_needed", reflect_if_needed)
    builder.add_node("finalize_success", finalize_success)
    builder.add_node("finalize_failure", finalize_failure)

    builder.add_edge(START, "prepare_input")
    builder.add_edge("prepare_input", "derive_turn_goal")
    builder.add_edge("derive_turn_goal", "plan_step_slice")
    builder.add_edge("plan_step_slice", "build_model_request")
    builder.add_edge("build_model_request", "call_model")
    builder.add_edge("call_model", "inspect_model_output")
    builder.add_conditional_edges(
        "inspect_model_output",
        route_after_inspect,
        {
            "execute_tools": "execute_tools",
            "reflect_if_needed": "reflect_if_needed",
            "finalize_success": "finalize_success",
            "finalize_failure": "finalize_failure",
        },
    )
    builder.add_edge("execute_tools", "apply_tool_results")
    builder.add_edge("apply_tool_results", "assess_progress")
    builder.add_conditional_edges(
        "assess_progress",
        route_after_assess,
        {
            "derive_turn_goal": "derive_turn_goal",
            "reflect_if_needed": "reflect_if_needed",
            "finalize_success": "finalize_success",
            "finalize_failure": "finalize_failure",
        },
    )
    builder.add_conditional_edges(
        "reflect_if_needed",
        route_after_reflect,
        {
            "derive_turn_goal": "derive_turn_goal",
            "finalize_success": "finalize_success",
            "finalize_failure": "finalize_failure",
        },
    )
    builder.add_edge("finalize_success", END)
    builder.add_edge("finalize_failure", END)
    return builder.compile()
