"""Diagnostic summaries for capability-first RP eval reporting."""

from __future__ import annotations

import json
from typing import Any

from .models import EvalRunResult


DiagnosticStatus = str


def build_diagnostics(
    *,
    result: EvalRunResult,
    assertion_summary: dict[str, int],
    hard_failures: list[str],
    repair_route: str | None,
    completion_guard_reason: str | None,
    last_failure_category: str | None,
    cognitive_state_invalidated: bool | None,
    remaining_open_issues: list[str],
    subjective_hook_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if result.case.scope == "setup":
        return _build_setup_diagnostics(
            result=result,
            assertion_summary=assertion_summary,
            hard_failures=hard_failures,
            repair_route=repair_route,
            completion_guard_reason=completion_guard_reason,
            last_failure_category=last_failure_category,
            cognitive_state_invalidated=cognitive_state_invalidated,
            remaining_open_issues=remaining_open_issues,
            subjective_hook_results=subjective_hook_results,
        )
    if result.case.scope == "activation":
        return _build_activation_diagnostics(
            result=result,
            assertion_summary=assertion_summary,
            hard_failures=hard_failures,
            subjective_hook_results=subjective_hook_results,
        )
    return {
        "diagnostic_version": "v1",
        "capabilities": {},
        "attribution": {
            "primary_suspects": [],
            "optimization_candidates": [],
            "dimensions": {},
        },
        "observability": {
            "supported_scope": result.case.scope,
            "diagnostic_mode": "not_implemented_for_scope",
        },
    }


def build_setup_diagnostic_projection(
    *,
    runtime_result: dict[str, Any],
    failure_layer: str | None = None,
    error_code: str | None = None,
    assertion_fail_total: int = 0,
    hard_failures: list[str] | None = None,
    subjective_hook_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hard_failures = list(hard_failures or [])
    subjective_hook_results = list(subjective_hook_results or [])
    structured_payload = runtime_result.get("structured_payload")
    if not isinstance(structured_payload, dict):
        structured_payload = {}
    warnings = runtime_result.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    tool_invocations = runtime_result.get("tool_invocations")
    if not isinstance(tool_invocations, list):
        tool_invocations = []
    tool_results = runtime_result.get("tool_results")
    if not isinstance(tool_results, list):
        tool_results = []
    assistant_text = str(runtime_result.get("assistant_text") or "")
    finish_reason = runtime_result.get("finish_reason")
    request_metrics = structured_payload.get("request_metrics")
    if not isinstance(request_metrics, dict):
        request_metrics = {}
    request_context = structured_payload.get("request_context")
    if not isinstance(request_context, dict):
        request_context = {}
    usage = _extract_usage(structured_payload.get("latest_response"))
    completion_guard = structured_payload.get("completion_guard")
    if not isinstance(completion_guard, dict):
        completion_guard = {}
    last_failure = structured_payload.get("last_failure")
    if not isinstance(last_failure, dict):
        last_failure = {}
    cognitive_summary = structured_payload.get("cognitive_state_summary")
    if not isinstance(cognitive_summary, dict):
        cognitive_summary = {}
    activation_check = runtime_result.get("activation_check")
    if not isinstance(activation_check, dict):
        activation_check = {}

    repair_route = structured_payload.get("repair_route")
    if repair_route is None and (
        "commit_proposal_blocked" in warnings
        or (structured_payload.get("pending_obligation") or {}).get("obligation_type")
        == "reassess_commit_readiness"
    ):
        repair_route = "block_commit"
    completion_guard_reason = str(completion_guard.get("reason") or "") or None
    last_failure_category = str(last_failure.get("failure_category") or "") or None
    cognitive_state_invalidated = (
        bool(cognitive_summary.get("invalidated"))
        if cognitive_summary.get("invalidated") is not None
        else None
    )
    remaining_open_issues = list(cognitive_summary.get("remaining_open_issues") or [])

    tool_failure_results = [
        item for item in tool_results if isinstance(item, dict) and not bool(item.get("success"))
    ]
    tool_success_results = [
        item for item in tool_results if isinstance(item, dict) and bool(item.get("success"))
    ]
    tool_failure_codes = [
        str(item.get("error_code") or "")
        for item in tool_failure_results
        if isinstance(item, dict)
    ]
    tool_names = [
        str(item.get("tool_name") or "")
        for item in tool_invocations
        if isinstance(item, dict) and item.get("tool_name")
    ]
    schema_retry_count = sum(
        1 for item in warnings if isinstance(item, str) and "tool_schema_validation" in item
    )
    clarification_hook = _find_subjective_hook(
        subjective_hook_results,
        rubric_ref="setup/clarification-quality/v1",
    )

    capabilities = {
        "task_completion": _capability_entry(
            status=_task_completion_status(
                failure_layer=failure_layer,
                finish_reason=finish_reason,
                fail_total=assertion_fail_total,
            ),
            summary=_task_completion_summary(
                failure_layer=failure_layer,
                finish_reason=finish_reason,
                fail_total=assertion_fail_total,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("finish_reason", finish_reason),
                    _fmt("failure_layer", failure_layer),
                    _fmt("assertion_fail_total", assertion_fail_total),
                ]
            ),
        ),
        "clarification_gap_detection": _capability_entry(
            status=_clarification_status(
                finish_reason=finish_reason,
                assistant_text=assistant_text,
                last_failure_category=last_failure_category,
                clarification_hook=clarification_hook,
            ),
            summary=_clarification_summary(
                finish_reason=finish_reason,
                clarification_hook=clarification_hook,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("finish_reason", finish_reason),
                    _fmt("assistant_text_chars", len(assistant_text)),
                    _fmt(
                        "clarification_hook_status",
                        clarification_hook.get("status") if clarification_hook else None,
                    ),
                    _fmt(
                        "clarification_hook_score",
                        clarification_hook.get("score") if clarification_hook else None,
                    ),
                ]
            ),
        ),
        "repair_recovery": _capability_entry(
            status=_repair_status(
                repair_route=repair_route,
                completion_guard_reason=completion_guard_reason,
                last_failure_category=last_failure_category,
                tool_failure_count=len(tool_failure_results),
                finish_reason=finish_reason,
            ),
            summary=_repair_summary(
                repair_route=repair_route,
                completion_guard_reason=completion_guard_reason,
                last_failure_category=last_failure_category,
                tool_failure_count=len(tool_failure_results),
            ),
            evidence=_compact_evidence(
                [
                    _fmt("repair_route", repair_route),
                    _fmt("completion_guard_reason", completion_guard_reason),
                    _fmt("last_failure_category", last_failure_category),
                    _fmt("tool_failure_count", len(tool_failure_results)),
                ]
            ),
        ),
        "commit_readiness_judgement": _capability_entry(
            status=_commit_status(
                warnings=warnings,
                tool_names=tool_names,
                request_context=request_context,
                remaining_open_issues=remaining_open_issues,
            ),
            summary=_commit_summary(
                warnings=warnings,
                tool_names=tool_names,
                request_context=request_context,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("commit_proposal_blocked", "commit_proposal_blocked" in warnings),
                    _fmt(
                        "commit_tool_invoked",
                        any(name.endswith("setup.proposal.commit") for name in tool_names),
                    ),
                    _fmt(
                        "blocking_open_question_count",
                        request_context.get("blocking_open_question_count"),
                    ),
                    _fmt("remaining_open_issue_count", len(remaining_open_issues)),
                ]
            ),
        ),
        "state_adaptation": _capability_entry(
            status=_state_adaptation_status(
                cognitive_state_invalidated=cognitive_state_invalidated,
                finish_reason=finish_reason,
                tool_names=tool_names,
            ),
            summary=_state_adaptation_summary(
                cognitive_state_invalidated=cognitive_state_invalidated,
                finish_reason=finish_reason,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("cognitive_state_invalidated", cognitive_state_invalidated),
                    _fmt("finish_reason", finish_reason),
                    _fmt("tool_invocation_count", len(tool_names)),
                ]
            ),
        ),
        "operational_efficiency": _capability_entry(
            status=_efficiency_status(
                round_no=structured_payload.get("round_no"),
                total_tokens=usage.get("total_tokens"),
                tool_invocation_count=len(tool_invocations),
            ),
            summary=_efficiency_summary(
                round_no=structured_payload.get("round_no"),
                total_tokens=usage.get("total_tokens"),
                tool_invocation_count=len(tool_invocations),
            ),
            evidence=_compact_evidence(
                [
                    _fmt("round_no", structured_payload.get("round_no")),
                    _fmt("total_tokens", usage.get("total_tokens")),
                    _fmt("tool_invocation_count", len(tool_invocations)),
                ]
            ),
        ),
    }

    dimensions = {
        "infra_model_provider": _dimension_entry(
            status="fail" if failure_layer == "infra" else "pass",
            summary=(
                f"Run failed before stable agent outcome; error_code={error_code or 'n/a'}"
                if failure_layer == "infra"
                else "No infra/model-provider failure detected in this run."
            ),
            evidence=_compact_evidence(
                [
                    _fmt("failure_layer", failure_layer),
                    _fmt("error_code", error_code),
                ]
            ),
        ),
        "tool_contract_execution": _dimension_entry(
            status=_tool_dimension_status(
                tool_failure_count=len(tool_failure_results),
                tool_failure_codes=tool_failure_codes,
                schema_retry_count=schema_retry_count,
                tool_success_count=len(tool_success_results),
                finish_reason=finish_reason,
                repair_route=repair_route,
            ),
            summary=_tool_dimension_summary(
                tool_failure_count=len(tool_failure_results),
                tool_failure_codes=tool_failure_codes,
                schema_retry_count=schema_retry_count,
                tool_success_count=len(tool_success_results),
                finish_reason=finish_reason,
                repair_route=repair_route,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("tool_invocation_count", len(tool_invocations)),
                    _fmt("tool_success_count", len(tool_success_results)),
                    _fmt("tool_failure_count", len(tool_failure_results)),
                    _fmt("tool_failure_codes", tool_failure_codes),
                    _fmt("schema_retry_count", schema_retry_count),
                ]
            ),
        ),
        "decision_policy": _dimension_entry(
            status=_decision_dimension_status(
                hard_failures=hard_failures,
                completion_guard_reason=completion_guard_reason,
                repair_route=repair_route,
                finish_reason=finish_reason,
                failure_layer=failure_layer,
            ),
            summary=_decision_dimension_summary(
                hard_failures=hard_failures,
                completion_guard_reason=completion_guard_reason,
                repair_route=repair_route,
                finish_reason=finish_reason,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("hard_failures", hard_failures[:4]),
                    _fmt("completion_guard_reason", completion_guard_reason),
                    _fmt("repair_route", repair_route),
                    _fmt("finish_reason", finish_reason),
                ]
            ),
        ),
        "structured_output_contract": _dimension_entry(
            status=_structured_dimension_status(
                finish_reason=finish_reason,
                assistant_text=assistant_text,
                schema_retry_count=schema_retry_count,
                failure_layer=failure_layer,
            ),
            summary=_structured_dimension_summary(
                finish_reason=finish_reason,
                assistant_text=assistant_text,
                schema_retry_count=schema_retry_count,
                failure_layer=failure_layer,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("finish_reason", finish_reason),
                    _fmt("assistant_text_chars", len(assistant_text)),
                    _fmt("schema_retry_count", schema_retry_count),
                ]
            ),
        ),
        "instruction_prompt_skill": _dimension_entry(
            status=_instruction_dimension_status(
                failure_layer=failure_layer,
                tool_failure_count=len(tool_failure_results),
                clarification_hook=clarification_hook,
                hard_failures=hard_failures,
            ),
            summary=_instruction_dimension_summary(
                failure_layer=failure_layer,
                tool_failure_count=len(tool_failure_results),
                clarification_hook=clarification_hook,
                hard_failures=hard_failures,
            ),
            evidence=_compact_evidence(
                [
                    _fmt(
                        "clarification_hook_status",
                        clarification_hook.get("status") if clarification_hook else None,
                    ),
                    _fmt(
                        "clarification_hook_score",
                        clarification_hook.get("score") if clarification_hook else None,
                    ),
                    _fmt("hard_failures", hard_failures[:4]),
                    _fmt("system_prompt_chars", request_metrics.get("system_prompt_chars")),
                ]
            ),
        ),
        "token_efficiency": _dimension_entry(
            status=_token_dimension_status(usage=usage),
            summary=_token_dimension_summary(usage=usage),
            evidence=_compact_evidence(
                [
                    _fmt("prompt_tokens", usage.get("prompt_tokens")),
                    _fmt("completion_tokens", usage.get("completion_tokens")),
                    _fmt("total_tokens", usage.get("total_tokens")),
                    _fmt("round_no", structured_payload.get("round_no")),
                ]
            ),
        ),
        "output_quality": _dimension_entry(
            status=_output_dimension_status(
                failure_layer=failure_layer,
                assistant_text=assistant_text,
                clarification_hook=clarification_hook,
                fail_total=assertion_fail_total,
            ),
            summary=_output_dimension_summary(
                failure_layer=failure_layer,
                assistant_text=assistant_text,
                clarification_hook=clarification_hook,
                fail_total=assertion_fail_total,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("assistant_text_chars", len(assistant_text)),
                    _fmt(
                        "clarification_hook_status",
                        clarification_hook.get("status") if clarification_hook else None,
                    ),
                    _fmt(
                        "clarification_hook_score",
                        clarification_hook.get("score") if clarification_hook else None,
                    ),
                    _fmt("assertion_fail_total", assertion_fail_total),
                ]
            ),
        ),
    }
    primary_suspects = _primary_suspects(dimensions=dimensions, failure_layer=failure_layer)
    reason_codes = _setup_reason_codes(
        failure_layer=failure_layer,
        error_code=error_code,
        finish_reason=finish_reason,
        warnings=warnings,
        tool_results=tool_results,
        repair_route=repair_route,
        completion_guard_reason=completion_guard_reason,
        last_failure_category=last_failure_category,
        cognitive_summary=cognitive_summary,
        activation_check=activation_check,
    )
    taxonomy_dimensions = _setup_taxonomy_dimensions(
        dimensions=dimensions,
        reason_codes=reason_codes,
        activation_check=activation_check,
        failure_layer=failure_layer,
    )
    secondary_suspects = _secondary_suspects(
        dimensions=dimensions,
        primary_suspects=primary_suspects,
    )
    evidence_refs = _setup_evidence_refs(
        reason_codes=reason_codes,
        activation_check=activation_check,
        cognitive_summary=cognitive_summary,
        tool_results=tool_results,
    )
    recommended_next_action = _setup_recommended_next_action(
        primary_suspects=primary_suspects,
        reason_codes=reason_codes,
    )
    outcome_chain = _setup_outcome_chain(
        capabilities=capabilities,
        activation_check=activation_check,
    )
    return {
        "capabilities": capabilities,
        "reason_codes": reason_codes,
        "outcome_chain": outcome_chain,
        "recommended_next_action": recommended_next_action,
        "attribution": {
            "primary_suspects": primary_suspects,
            "secondary_suspects": secondary_suspects,
            "optimization_candidates": _optimization_candidates(primary_suspects),
            "evidence_refs": evidence_refs,
            "recommended_next_action": recommended_next_action,
            "dimensions": dimensions,
            "taxonomy_dimensions": taxonomy_dimensions,
        },
        "observability": {
            "supported_scope": "setup",
            "request_metrics": {
                "system_prompt_chars": request_metrics.get("system_prompt_chars"),
                "user_prompt_chars": request_metrics.get("user_prompt_chars"),
                "conversation_message_count": request_metrics.get(
                    "conversation_message_count"
                ),
                "tool_scope_count": request_metrics.get("tool_scope_count"),
                "tool_scope": structured_payload.get("tool_scope") or [],
            },
            "usage": usage,
            "tooling": {
                "invocation_count": len(tool_invocations),
                "success_count": len(tool_success_results),
                "failure_count": len(tool_failure_results),
                "invoked_tool_names": tool_names,
            },
        },
    }


def build_activation_diagnostic_projection(
    *,
    runtime_result: dict[str, Any],
    failure_layer: str | None = None,
    error_code: str | None = None,
    assertion_fail_total: int = 0,
    hard_failures: list[str] | None = None,
    subjective_hook_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hard_failures = list(hard_failures or [])
    subjective_hook_results = list(subjective_hook_results or [])
    activation_check = runtime_result.get("activation_check")
    if not isinstance(activation_check, dict):
        activation_check = {}
    activation_result = runtime_result.get("activation_result")
    if not isinstance(activation_result, dict):
        activation_result = {}
    error_payload = runtime_result.get("error")
    if not isinstance(error_payload, dict):
        error_payload = {}

    finish_reason = runtime_result.get("finish_reason")
    ready = bool(activation_check.get("ready"))
    blocking_issues = activation_check.get("blocking_issues")
    if not isinstance(blocking_issues, list):
        blocking_issues = []
    warnings = activation_check.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    handoff = activation_check.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    runtime_story_config = handoff.get("runtime_story_config")
    if not isinstance(runtime_story_config, dict):
        runtime_story_config = {}
    writer_contract = handoff.get("writer_contract")
    if not isinstance(writer_contract, dict):
        writer_contract = {}
    foundation_commit_refs = handoff.get("foundation_commit_refs")
    if not isinstance(foundation_commit_refs, list):
        foundation_commit_refs = []
    archival_ready_refs = handoff.get("archival_ready_refs")
    if not isinstance(archival_ready_refs, list):
        archival_ready_refs = []
    has_handoff = bool(handoff)
    has_complete_handoff = bool(
        has_handoff
        and runtime_story_config
        and writer_contract
        and foundation_commit_refs
        and handoff.get("blueprint_commit_ref")
    )
    activation_success = bool(activation_result.get("session_id"))
    activation_hook = _find_subjective_hook(
        subjective_hook_results,
        rubric_ref="activation/handoff-quality/v1",
    )

    capabilities = {
        "readiness_gate": _capability_entry(
            status=_activation_readiness_gate_status(
                ready=ready,
                blocking_issues=blocking_issues,
                finish_reason=finish_reason,
            ),
            summary=_activation_readiness_gate_summary(
                ready=ready,
                blocking_issues=blocking_issues,
                finish_reason=finish_reason,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("ready", ready),
                    _fmt("blocking_issue_count", len(blocking_issues)),
                    _fmt("finish_reason", finish_reason),
                ]
            ),
        ),
        "handoff_integrity": _capability_entry(
            status=_activation_handoff_status(
                ready=ready,
                has_handoff=has_handoff,
                has_complete_handoff=has_complete_handoff,
                activation_hook=activation_hook,
            ),
            summary=_activation_handoff_summary(
                ready=ready,
                has_handoff=has_handoff,
                has_complete_handoff=has_complete_handoff,
                activation_hook=activation_hook,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("has_handoff", has_handoff),
                    _fmt("runtime_story_config_keys", sorted(runtime_story_config.keys())),
                    _fmt("writer_contract_keys", sorted(writer_contract.keys())),
                    _fmt("foundation_commit_ref_count", len(foundation_commit_refs)),
                    _fmt("archival_ready_ref_count", len(archival_ready_refs)),
                ]
            ),
        ),
        "session_bootstrap": _capability_entry(
            status=_activation_session_bootstrap_status(
                ready=ready,
                activation_success=activation_success,
                finish_reason=finish_reason,
            ),
            summary=_activation_session_bootstrap_summary(
                ready=ready,
                activation_success=activation_success,
                finish_reason=finish_reason,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("session_id", activation_result.get("session_id")),
                    _fmt("current_phase", activation_result.get("current_phase")),
                    _fmt("current_chapter_index", activation_result.get("current_chapter_index")),
                    _fmt("initial_outline_required", activation_result.get("initial_outline_required")),
                ]
            ),
        ),
    }

    dimensions = {
        "setup_readiness_contract": _dimension_entry(
            status=_activation_setup_readiness_dimension_status(
                ready=ready,
                blocking_issues=blocking_issues,
            ),
            summary=_activation_setup_readiness_dimension_summary(
                ready=ready,
                blocking_issues=blocking_issues,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("ready", ready),
                    _fmt("blocking_issues", blocking_issues[:4]),
                    _fmt("warning_count", len(warnings)),
                ]
            ),
        ),
        "activation_handoff_contract": _dimension_entry(
            status=_activation_handoff_contract_dimension_status(
                ready=ready,
                has_handoff=has_handoff,
                has_complete_handoff=has_complete_handoff,
                activation_hook=activation_hook,
            ),
            summary=_activation_handoff_contract_dimension_summary(
                ready=ready,
                has_handoff=has_handoff,
                has_complete_handoff=has_complete_handoff,
                activation_hook=activation_hook,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("has_handoff", has_handoff),
                    _fmt("blueprint_commit_ref", handoff.get("blueprint_commit_ref")),
                    _fmt("foundation_commit_ref_count", len(foundation_commit_refs)),
                    _fmt("archival_ready_ref_count", len(archival_ready_refs)),
                ]
            ),
        ),
        "bootstrap_execution": _dimension_entry(
            status=_activation_bootstrap_execution_dimension_status(
                ready=ready,
                activation_success=activation_success,
                finish_reason=finish_reason,
                failure_layer=failure_layer,
            ),
            summary=_activation_bootstrap_execution_dimension_summary(
                ready=ready,
                activation_success=activation_success,
                finish_reason=finish_reason,
                failure_layer=failure_layer,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("finish_reason", finish_reason),
                    _fmt("failure_layer", failure_layer),
                    _fmt("error_code", error_code or error_payload.get("type")),
                ]
            ),
        ),
        "deterministic_gate_policy": _dimension_entry(
            status=_activation_gate_policy_dimension_status(
                ready=ready,
                blocking_issues=blocking_issues,
                activation_success=activation_success,
                finish_reason=finish_reason,
                hard_failures=hard_failures,
            ),
            summary=_activation_gate_policy_dimension_summary(
                ready=ready,
                blocking_issues=blocking_issues,
                activation_success=activation_success,
                finish_reason=finish_reason,
                hard_failures=hard_failures,
            ),
            evidence=_compact_evidence(
                [
                    _fmt("ready", ready),
                    _fmt("blocking_issue_count", len(blocking_issues)),
                    _fmt("activation_success", activation_success),
                    _fmt("hard_failures", hard_failures[:4]),
                ]
            ),
        ),
    }
    primary_suspects = _activation_primary_suspects(
        dimensions=dimensions,
        failure_layer=failure_layer,
    )
    return {
        "capabilities": capabilities,
        "attribution": {
            "primary_suspects": primary_suspects,
            "optimization_candidates": _activation_optimization_candidates(primary_suspects),
            "dimensions": dimensions,
        },
        "observability": {
            "supported_scope": "activation",
            "activation": {
                "ready": ready,
                "blocking_issue_count": len(blocking_issues),
                "warning_count": len(warnings),
                "has_handoff": has_handoff,
                "foundation_commit_ref_count": len(foundation_commit_refs),
                "archival_ready_ref_count": len(archival_ready_refs),
                "activation_success": activation_success,
            },
        },
    }


def _build_setup_diagnostics(
    *,
    result: EvalRunResult,
    assertion_summary: dict[str, int],
    hard_failures: list[str],
    repair_route: str | None,
    completion_guard_reason: str | None,
    last_failure_category: str | None,
    cognitive_state_invalidated: bool | None,
    remaining_open_issues: list[str],
    subjective_hook_results: list[dict[str, Any]],
) -> dict[str, Any]:
    projection = build_setup_diagnostic_projection(
        runtime_result=result.runtime_result if isinstance(result.runtime_result, dict) else {},
        failure_layer=result.run.failure.layer if result.run.failure is not None else None,
        error_code=result.run.failure.code if result.run.failure is not None else None,
        assertion_fail_total=int(assertion_summary.get("fail", 0) or 0),
        hard_failures=hard_failures,
        subjective_hook_results=subjective_hook_results,
    )
    return {
        "diagnostic_version": "v1",
        **projection,
    }


def _build_activation_diagnostics(
    *,
    result: EvalRunResult,
    assertion_summary: dict[str, int],
    hard_failures: list[str],
    subjective_hook_results: list[dict[str, Any]],
) -> dict[str, Any]:
    projection = build_activation_diagnostic_projection(
        runtime_result=result.runtime_result if isinstance(result.runtime_result, dict) else {},
        failure_layer=result.run.failure.layer if result.run.failure is not None else None,
        error_code=result.run.failure.code if result.run.failure is not None else None,
        assertion_fail_total=int(assertion_summary.get("fail", 0) or 0),
        hard_failures=hard_failures,
        subjective_hook_results=subjective_hook_results,
    )
    return {
        "diagnostic_version": "v1",
        **projection,
    }


def _task_completion_status(
    *,
    failure_layer: str | None,
    finish_reason: Any,
    fail_total: int,
) -> DiagnosticStatus:
    if failure_layer == "infra":
        return "fail"
    if fail_total == 0 and finish_reason:
        return "pass"
    if fail_total > 0:
        return "fail"
    return "unknown"


def _task_completion_summary(
    *,
    failure_layer: str | None,
    finish_reason: Any,
    fail_total: int,
) -> str:
    if failure_layer == "infra":
        return "Setup turn never reached a stable agent outcome because infra/model-provider failed first."
    if fail_total == 0 and finish_reason:
        return f"Setup run reached the expected terminal outcome with finish_reason={finish_reason}."
    if fail_total > 0:
        return "Setup run completed with assertion failures, so capability outcome is not trustworthy."
    return "Task completion could not be judged from the current evidence."


def _clarification_status(
    *,
    finish_reason: Any,
    assistant_text: str,
    last_failure_category: str | None,
    clarification_hook: dict[str, Any] | None,
) -> DiagnosticStatus:
    if finish_reason != "awaiting_user_input" and last_failure_category != "ask_user" and clarification_hook is None:
        return "not_applicable"
    if finish_reason == "awaiting_user_input" and assistant_text.strip():
        if clarification_hook is not None and clarification_hook.get("status") == "fail":
            return "warn"
        return "pass"
    return "fail"


def _clarification_summary(
    *,
    finish_reason: Any,
    clarification_hook: dict[str, Any] | None,
) -> str:
    if finish_reason == "awaiting_user_input":
        if clarification_hook is not None and clarification_hook.get("status") in {"warn", "fail"}:
            return "Agent asked the user, but the judged clarification quality is not yet strong."
        return "Agent correctly switched into clarification mode and asked the user for missing information."
    if clarification_hook is None:
        return "Clarification behavior was not required in this run."
    return "Clarification was expected but the run did not end in a usable ask-user outcome."


def _repair_status(
    *,
    repair_route: str | None,
    completion_guard_reason: str | None,
    last_failure_category: str | None,
    tool_failure_count: int,
    finish_reason: Any,
) -> DiagnosticStatus:
    if not any(
        [
            repair_route,
            completion_guard_reason,
            last_failure_category,
            tool_failure_count,
        ]
    ):
        return "not_applicable"
    if finish_reason == "repair_obligation_unfulfilled" or completion_guard_reason == "repair_obligation_unresolved":
        return "fail"
    if repair_route in {"ask_user", "auto_repair", "continue_discussion", "block_commit"}:
        return "pass"
    if tool_failure_count > 0:
        return "warn"
    return "unknown"


def _repair_summary(
    *,
    repair_route: str | None,
    completion_guard_reason: str | None,
    last_failure_category: str | None,
    tool_failure_count: int,
) -> str:
    if completion_guard_reason == "repair_obligation_unresolved":
        return "A repair obligation was left unresolved, so recovery capability failed."
    if repair_route:
        return f"Recovery route selected as {repair_route}; repair semantics are observable."
    if tool_failure_count > 0 or last_failure_category:
        return "Failure recovery signals exist, but no explicit repair route summary was produced."
    return "No repair or recovery path was needed in this run."


def _commit_status(
    *,
    warnings: list[str],
    tool_names: list[str],
    request_context: dict[str, Any],
    remaining_open_issues: list[str],
) -> DiagnosticStatus:
    commit_tool_used = any(name.endswith("setup.proposal.commit") for name in tool_names)
    commit_blocked = "commit_proposal_blocked" in warnings
    blocking_count = int(request_context.get("blocking_open_question_count") or 0)
    if not commit_tool_used and not commit_blocked and blocking_count == 0 and not remaining_open_issues:
        return "not_applicable"
    if commit_blocked:
        return "pass"
    if commit_tool_used:
        return "pass"
    if blocking_count > 0 or remaining_open_issues:
        return "warn"
    return "unknown"


def _commit_summary(
    *,
    warnings: list[str],
    tool_names: list[str],
    request_context: dict[str, Any],
) -> str:
    if "commit_proposal_blocked" in warnings:
        return "Commit readiness guard blocked a premature commit proposal."
    if any(name.endswith("setup.proposal.commit") for name in tool_names):
        return "Agent chose to propose commit/review, so commit timing was actively exercised."
    if int(request_context.get("blocking_open_question_count") or 0) > 0:
        return "Blocking questions remained, but commit timing was not explicitly exercised."
    return "Commit readiness was not meaningfully exercised in this run."


def _state_adaptation_status(
    *,
    cognitive_state_invalidated: bool | None,
    finish_reason: Any,
    tool_names: list[str],
) -> DiagnosticStatus:
    if not cognitive_state_invalidated:
        return "not_applicable"
    if finish_reason in {"awaiting_user_input", "continue_discussion"} and not any(
        name.endswith("setup.proposal.commit") for name in tool_names
    ):
        return "pass"
    return "fail"


def _state_adaptation_summary(
    *,
    cognitive_state_invalidated: bool | None,
    finish_reason: Any,
) -> str:
    if not cognitive_state_invalidated:
        return "No invalidated cognitive state was present, so adaptation was not exercised."
    return f"Cognitive state was invalidated and the run ended with finish_reason={finish_reason}."


def _efficiency_status(
    *,
    round_no: Any,
    total_tokens: Any,
    tool_invocation_count: int,
) -> DiagnosticStatus:
    if round_no is None and total_tokens is None:
        return "unknown"
    round_value = int(round_no or 0)
    token_value = int(total_tokens or 0)
    if round_value <= 2 and token_value <= 4000 and tool_invocation_count <= 2:
        return "pass"
    if round_value <= 4 and token_value <= 12000 and tool_invocation_count <= 4:
        return "warn"
    return "fail"


def _efficiency_summary(
    *,
    round_no: Any,
    total_tokens: Any,
    tool_invocation_count: int,
) -> str:
    if round_no is None and total_tokens is None:
        return "No token or round metrics were available for efficiency analysis."
    return (
        f"Observed round_no={round_no}, total_tokens={total_tokens}, "
        f"tool_invocation_count={tool_invocation_count}."
    )


def _tool_dimension_status(
    *,
    tool_failure_count: int,
    tool_failure_codes: list[str],
    schema_retry_count: int,
    tool_success_count: int,
    finish_reason: Any,
    repair_route: str | None,
) -> DiagnosticStatus:
    if tool_failure_count > 0:
        recoverable_codes = {"SCHEMA_VALIDATION_FAILED", "SETUP_TOOL_FAILED"}
        hard_codes = {"UNKNOWN_TOOL", "TOOL_EXECUTION_FAILED", "UNAUTHORIZED_TOOL"}
        if any(code in hard_codes for code in tool_failure_codes):
            return "fail"
        if tool_failure_codes and all(code in recoverable_codes for code in tool_failure_codes):
            if finish_reason in {"awaiting_user_input", "continue_discussion", "completed_text"} and repair_route in {
                "ask_user",
                "continue_discussion",
                "auto_repair",
                "block_commit",
            }:
                return "warn"
        return "fail" if tool_success_count == 0 else "warn"
    if schema_retry_count > 0:
        return "warn"
    if tool_success_count > 0:
        return "pass"
    return "unknown"


def _tool_dimension_summary(
    *,
    tool_failure_count: int,
    tool_failure_codes: list[str],
    schema_retry_count: int,
    tool_success_count: int,
    finish_reason: Any,
    repair_route: str | None,
) -> str:
    if tool_failure_count > 0:
        recoverable_codes = {"SCHEMA_VALIDATION_FAILED", "SETUP_TOOL_FAILED"}
        if tool_failure_codes and all(code in recoverable_codes for code in tool_failure_codes):
            return (
                "Observed recoverable tool failures that were routed into semantic recovery; "
                "this points to degraded tool interaction, not necessarily a broken tool."
            )
        return f"Observed {tool_failure_count} failed tool results; tool contract quality is suspect."
    if schema_retry_count > 0:
        return "Tool schema validation had to retry, so tool contract is degraded but recovered."
    if tool_success_count > 0:
        return "Tool execution completed without visible failures."
    return "This run did not materially exercise tools."


def _decision_dimension_status(
    *,
    hard_failures: list[str],
    completion_guard_reason: str | None,
    repair_route: str | None,
    finish_reason: Any,
    failure_layer: str | None,
) -> DiagnosticStatus:
    if failure_layer == "infra":
        return "unknown"
    if completion_guard_reason == "repair_obligation_unresolved":
        return "fail"
    if any(
        failure_name in {
            "finish_is_awaiting_user_input",
            "repair_route_is_ask_user",
            "assistant_asks_for_preferences",
        }
        for failure_name in hard_failures
    ):
        return "fail"
    if finish_reason and (repair_route or finish_reason in {"completed_text", "awaiting_user_input", "continue_discussion"}):
        return "pass"
    return "warn"


def _decision_dimension_summary(
    *,
    hard_failures: list[str],
    completion_guard_reason: str | None,
    repair_route: str | None,
    finish_reason: Any,
) -> str:
    if completion_guard_reason == "repair_obligation_unresolved":
        return "Completion guard blocked a false success because decision policy left repair unfinished."
    if hard_failures:
        return f"Decision-facing assertions failed: {', '.join(hard_failures[:3])}."
    return f"Decision path resolved with finish_reason={finish_reason} and repair_route={repair_route}."


def _structured_dimension_status(
    *,
    finish_reason: Any,
    assistant_text: str,
    schema_retry_count: int,
    failure_layer: str | None,
) -> DiagnosticStatus:
    if failure_layer == "infra":
        return "fail"
    if finish_reason is None:
        return "fail"
    if schema_retry_count > 0:
        return "warn"
    if finish_reason == "awaiting_user_input" and not assistant_text.strip():
        return "fail"
    return "pass"


def _structured_dimension_summary(
    *,
    finish_reason: Any,
    assistant_text: str,
    schema_retry_count: int,
    failure_layer: str | None,
) -> str:
    if failure_layer == "infra":
        return "Structured outcome is unavailable because runtime failed before producing a stable result."
    if finish_reason is None:
        return "Structured outcome is missing finish_reason."
    if schema_retry_count > 0:
        return "Structured tool interaction required schema retry."
    if finish_reason == "awaiting_user_input" and not assistant_text.strip():
        return "Agent claimed it needs user input but produced no user-facing clarification."
    return "Structured outcome fields needed for setup diagnosis are present."


def _instruction_dimension_status(
    *,
    failure_layer: str | None,
    tool_failure_count: int,
    clarification_hook: dict[str, Any] | None,
    hard_failures: list[str],
) -> DiagnosticStatus:
    if failure_layer == "infra":
        return "unknown"
    if clarification_hook is not None and clarification_hook.get("status") == "fail":
        return "fail"
    if tool_failure_count == 0 and hard_failures:
        return "warn"
    if clarification_hook is not None and clarification_hook.get("status") == "warn":
        return "warn"
    if not hard_failures:
        return "pass"
    return "unknown"


def _instruction_dimension_summary(
    *,
    failure_layer: str | None,
    tool_failure_count: int,
    clarification_hook: dict[str, Any] | None,
    hard_failures: list[str],
) -> str:
    if failure_layer == "infra":
        return "Prompt/skill quality cannot be judged because infrastructure failed first."
    if clarification_hook is not None and clarification_hook.get("status") in {"warn", "fail"}:
        return "Subjective judge indicates the user-facing instruction/clarification quality needs improvement."
    if tool_failure_count == 0 and hard_failures:
        return "Outcome failed without obvious tool failure, so prompt/skill/policy quality is a plausible suspect."
    if not hard_failures:
        return "No clear prompt/skill quality issue surfaced in this run."
    return "Instruction quality evidence is inconclusive."


def _token_dimension_status(*, usage: dict[str, int | None]) -> DiagnosticStatus:
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        return "unknown"
    if total_tokens <= 4000:
        return "pass"
    if total_tokens <= 12000:
        return "warn"
    return "fail"


def _token_dimension_summary(*, usage: dict[str, int | None]) -> str:
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        return "Token usage is not currently available for this run."
    return (
        f"Observed prompt_tokens={usage.get('prompt_tokens')}, "
        f"completion_tokens={usage.get('completion_tokens')}, total_tokens={total_tokens}."
    )


def _output_dimension_status(
    *,
    failure_layer: str | None,
    assistant_text: str,
    clarification_hook: dict[str, Any] | None,
    fail_total: int,
) -> DiagnosticStatus:
    if failure_layer == "infra":
        return "fail"
    if clarification_hook is not None:
        hook_status = clarification_hook.get("status")
        if hook_status in {"pass", "warn", "fail"}:
            return hook_status
    if fail_total == 0 and assistant_text.strip():
        return "pass"
    if fail_total > 0:
        return "fail"
    return "unknown"


def _output_dimension_summary(
    *,
    failure_layer: str | None,
    assistant_text: str,
    clarification_hook: dict[str, Any] | None,
    fail_total: int,
) -> str:
    if failure_layer == "infra":
        return "No usable output was produced because runtime failed upstream."
    if clarification_hook is not None:
        return (
            f"Subjective output hook status={clarification_hook.get('status')} "
            f"score={clarification_hook.get('score')}."
        )
    if fail_total == 0 and assistant_text.strip():
        return "Agent produced a user-visible output and all deterministic assertions passed."
    if fail_total > 0:
        return "Output-facing assertions failed."
    return "Output quality evidence is inconclusive."


def _activation_readiness_gate_status(
    *,
    ready: bool,
    blocking_issues: list[str],
    finish_reason: Any,
) -> DiagnosticStatus:
    if ready:
        return "pass"
    if blocking_issues and finish_reason in {None, "activation_failed", "activation_checked"}:
        return "pass"
    return "fail"


def _activation_readiness_gate_summary(
    *,
    ready: bool,
    blocking_issues: list[str],
    finish_reason: Any,
) -> str:
    if ready:
        return "Activation readiness gate passed and the workspace is eligible for bootstrap."
    if blocking_issues:
        return (
            "Activation gate correctly exposed blocking issues and prevented bootstrap: "
            + "; ".join(blocking_issues[:3])
        )
    return f"Activation gate did not produce a usable readiness decision; finish_reason={finish_reason}."


def _activation_handoff_status(
    *,
    ready: bool,
    has_handoff: bool,
    has_complete_handoff: bool,
    activation_hook: dict[str, Any] | None,
) -> DiagnosticStatus:
    if not ready and not has_handoff:
        return "not_applicable"
    if has_complete_handoff:
        if activation_hook is not None and activation_hook.get("status") == "fail":
            return "warn"
        return "pass"
    if ready:
        return "fail"
    return "warn"


def _activation_handoff_summary(
    *,
    ready: bool,
    has_handoff: bool,
    has_complete_handoff: bool,
    activation_hook: dict[str, Any] | None,
) -> str:
    if not ready and not has_handoff:
        return "Workspace was not ready, so no activation handoff was expected."
    if has_complete_handoff:
        if activation_hook is not None and activation_hook.get("status") in {"warn", "fail"}:
            return "Handoff is structurally complete, but judged handoff quality still needs improvement."
        return "Activation handoff contains the minimum runtime config, writer contract, and continuity refs."
    if ready:
        return "Workspace was marked ready but the activation handoff is missing required fields."
    return "Partial handoff information exists, but readiness is not yet satisfied."


def _activation_session_bootstrap_status(
    *,
    ready: bool,
    activation_success: bool,
    finish_reason: Any,
) -> DiagnosticStatus:
    if activation_success:
        return "pass"
    if not ready and finish_reason in {None, "activation_failed", "activation_checked"}:
        return "not_applicable"
    return "fail"


def _activation_session_bootstrap_summary(
    *,
    ready: bool,
    activation_success: bool,
    finish_reason: Any,
) -> str:
    if activation_success:
        return "Activation successfully materialized a StorySession and chapter workspace."
    if not ready:
        return "Session bootstrap was not attempted because readiness gate did not pass."
    return f"Activation should have bootstrapped a session but did not; finish_reason={finish_reason}."


def _activation_setup_readiness_dimension_status(
    *,
    ready: bool,
    blocking_issues: list[str],
) -> DiagnosticStatus:
    if ready:
        return "pass"
    if blocking_issues:
        return "warn"
    return "fail"


def _activation_setup_readiness_dimension_summary(
    *,
    ready: bool,
    blocking_issues: list[str],
) -> str:
    if ready:
        return "Setup-side readiness contract supplied all required prerequisites for activation."
    if blocking_issues:
        return "Activation is blocked by upstream setup/retrieval readiness gaps."
    return "Activation failed readiness without exposing clear upstream blocking issues."


def _activation_handoff_contract_dimension_status(
    *,
    ready: bool,
    has_handoff: bool,
    has_complete_handoff: bool,
    activation_hook: dict[str, Any] | None,
) -> DiagnosticStatus:
    if not ready and not has_handoff:
        return "not_applicable"
    if has_complete_handoff:
        if activation_hook is not None and activation_hook.get("status") == "fail":
            return "warn"
        return "pass"
    if ready:
        return "fail"
    return "warn"


def _activation_handoff_contract_dimension_summary(
    *,
    ready: bool,
    has_handoff: bool,
    has_complete_handoff: bool,
    activation_hook: dict[str, Any] | None,
) -> str:
    if not ready and not has_handoff:
        return "No handoff contract was required because readiness did not pass."
    if has_complete_handoff:
        if activation_hook is not None and activation_hook.get("status") in {"warn", "fail"}:
            return "Handoff contract is present, but quality/judged usability is not ideal."
        return "Activation handoff contract is structurally complete."
    if ready:
        return "Ready workspace exposed an incomplete activation handoff contract."
    return "Handoff contract is partial while readiness remains blocked."


def _activation_bootstrap_execution_dimension_status(
    *,
    ready: bool,
    activation_success: bool,
    finish_reason: Any,
    failure_layer: str | None,
) -> DiagnosticStatus:
    if activation_success:
        return "pass"
    if failure_layer == "infra":
        return "fail"
    if not ready and finish_reason in {None, "activation_failed", "activation_checked"}:
        return "warn"
    return "fail"


def _activation_bootstrap_execution_dimension_summary(
    *,
    ready: bool,
    activation_success: bool,
    finish_reason: Any,
    failure_layer: str | None,
) -> str:
    if activation_success:
        return "Session bootstrap executed and persisted correctly."
    if failure_layer == "infra":
        return "Activation bootstrap failed due to infra/runtime execution problems."
    if not ready:
        return "Bootstrap execution was skipped because activation gate did not pass."
    return f"Bootstrap execution failed after readiness passed; finish_reason={finish_reason}."


def _activation_gate_policy_dimension_status(
    *,
    ready: bool,
    blocking_issues: list[str],
    activation_success: bool,
    finish_reason: Any,
    hard_failures: list[str],
) -> DiagnosticStatus:
    if hard_failures:
        return "fail"
    if ready and activation_success:
        return "pass"
    if not ready and blocking_issues and finish_reason in {None, "activation_failed", "activation_checked"}:
        return "pass"
    return "fail"


def _activation_gate_policy_dimension_summary(
    *,
    ready: bool,
    blocking_issues: list[str],
    activation_success: bool,
    finish_reason: Any,
    hard_failures: list[str],
) -> str:
    if hard_failures:
        return f"Activation-facing deterministic assertions failed: {', '.join(hard_failures[:3])}."
    if ready and activation_success:
        return "Deterministic gate and bootstrap path are consistent: ready workspace activated successfully."
    if not ready and blocking_issues:
        return "Deterministic gate correctly blocked activation until prerequisites are satisfied."
    return f"Activation gate behavior is inconsistent with observed outcome; finish_reason={finish_reason}."


def _primary_suspects(
    *,
    dimensions: dict[str, dict[str, Any]],
    failure_layer: str | None,
) -> list[str]:
    suspects: list[str] = []
    if failure_layer == "infra" or _dimension_status(dimensions, "infra_model_provider") == "fail":
        suspects.append("infra_model_provider")
        return suspects
    for name in (
        "tool_contract_execution",
        "decision_policy",
        "structured_output_contract",
        "instruction_prompt_skill",
        "token_efficiency",
    ):
        if _dimension_status(dimensions, name) == "fail":
            suspects.append(name)
    if not suspects:
        for name in (
            "decision_policy",
            "instruction_prompt_skill",
            "tool_contract_execution",
            "token_efficiency",
        ):
            if _dimension_status(dimensions, name) == "warn":
                suspects.append(name)
    return suspects[:3]


def _optimization_candidates(primary_suspects: list[str]) -> list[str]:
    mapping = {
        "infra_model_provider": "fix_provider_model_config_and_runtime_connectivity",
        "tool_contract_execution": "tighten_tool_schema_and_error_messages",
        "decision_policy": "adjust_runtime_policy_and_finish_guard_logic",
        "structured_output_contract": "strengthen_output_contract_and_schema_repair_prompts",
        "instruction_prompt_skill": "revise_system_prompt_step_instructions_and_skill_contract",
        "token_efficiency": "trim_context_and_reduce_redundant_rounds",
    }
    return [mapping[item] for item in primary_suspects if item in mapping]


def _activation_primary_suspects(
    *,
    dimensions: dict[str, dict[str, Any]],
    failure_layer: str | None,
) -> list[str]:
    suspects: list[str] = []
    if failure_layer == "infra":
        return ["bootstrap_execution"]
    for name in (
        "activation_handoff_contract",
        "bootstrap_execution",
        "deterministic_gate_policy",
        "setup_readiness_contract",
    ):
        if _dimension_status(dimensions, name) == "fail":
            suspects.append(name)
    if not suspects:
        for name in (
            "setup_readiness_contract",
            "activation_handoff_contract",
            "bootstrap_execution",
        ):
            if _dimension_status(dimensions, name) == "warn":
                suspects.append(name)
    return suspects[:3]


def _activation_optimization_candidates(primary_suspects: list[str]) -> list[str]:
    mapping = {
        "setup_readiness_contract": "complete_setup_commits_and_retrieval_readiness_before_activation",
        "activation_handoff_contract": "fill_activation_handoff_required_fields_and_refs",
        "bootstrap_execution": "fix_story_activation_bootstrap_and_session_persistence",
        "deterministic_gate_policy": "tighten_activation_gate_and_idempotence_rules",
    }
    return [mapping[item] for item in primary_suspects if item in mapping]


def _setup_reason_codes(
    *,
    failure_layer: str | None,
    error_code: str | None,
    finish_reason: Any,
    warnings: list[Any],
    tool_results: list[Any],
    repair_route: Any,
    completion_guard_reason: str | None,
    last_failure_category: str | None,
    cognitive_summary: dict[str, Any],
    activation_check: dict[str, Any],
) -> list[str]:
    codes: list[str] = []
    lower_error = str(error_code or "").strip().lower()
    if failure_layer == "infra":
        if any(token in lower_error for token in ("sql", "database", "store")):
            codes.append("infra.database_unavailable")
        else:
            codes.append("infra.provider_request_failed")

    warnings_text = [str(item or "") for item in warnings]
    tool_error_codes = _setup_tool_error_codes(tool_results)
    if "schema_validation_failed" in tool_error_codes or any(
        "tool_schema_validation" in item for item in warnings_text
    ):
        codes.append("tool_execution.schema_validation_failed")
    if "setup_truth_write_target_ref_mismatch" in tool_error_codes:
        codes.append("tool_contract.truth_write_target_ref_mismatch")
    if "setup_commit_blocked_truth_write_not_ready_for_review" in tool_error_codes:
        codes.append("controller.commit_proposal_blocked")
    if tool_error_codes and not any(
        code in {
            "schema_validation_failed",
            "setup_truth_write_target_ref_mismatch",
            "setup_commit_blocked_truth_write_not_ready_for_review",
        }
        for code in tool_error_codes
    ):
        codes.append("tool_execution.provider_execution_failed")

    if "commit_proposal_blocked" in warnings_text or repair_route == "block_commit":
        codes.append("controller.commit_proposal_blocked")
    if completion_guard_reason == "truth_write_not_ready_for_review":
        codes.append("controller.commit_proposal_blocked")
    if last_failure_category == "ask_user":
        codes.append("prompt.missing_step_targeting")
    if finish_reason == "completed_text" and (
        completion_guard_reason
        or "commit_proposal_blocked" in warnings_text
        or list(cognitive_summary.get("remaining_open_issues") or [])
    ):
        codes.append("prompt.premature_commit_language")

    if bool(cognitive_summary.get("invalidated")):
        for reason in cognitive_summary.get("invalidation_reasons") or []:
            if reason == "user_edit_delta":
                codes.append("cognition.invalidated_by_user_edit")
            elif reason == "proposal_rejected":
                codes.append("cognition.invalidated_by_proposal_reject")
            elif reason == "draft_changed_without_delta":
                codes.append("cognition.stale_snapshot_reused")

    ready = bool(activation_check.get("ready"))
    blocking_issues = activation_check.get("blocking_issues")
    if not isinstance(blocking_issues, list):
        blocking_issues = []
    if not ready and blocking_issues:
        codes.append("readiness.blocked_by_open_setup_prerequisites")
        if any("Retrieval ingestion not completed" in str(item or "") for item in blocking_issues):
            codes.append("retrieval_readiness.ingestion_not_completed")
    handoff = activation_check.get("handoff")
    if isinstance(handoff, dict) and ready and not _activation_handoff_complete(handoff):
        codes.append("activation.handoff_missing_required_fields")
    return sorted(dict.fromkeys(code for code in codes if code))


def _setup_tool_error_codes(tool_results: list[Any]) -> list[str]:
    codes: list[str] = []
    for item in tool_results:
        if not isinstance(item, dict) or bool(item.get("success")):
            continue
        structured_payload = item.get("structured_payload")
        if isinstance(structured_payload, dict):
            content_payload = structured_payload.get("content_payload")
            if isinstance(content_payload, dict):
                error = content_payload.get("error")
                if isinstance(error, dict) and error.get("code"):
                    codes.append(str(error.get("code")))
            error = structured_payload.get("error")
            if isinstance(error, dict) and error.get("code"):
                codes.append(str(error.get("code")))
            if structured_payload.get("code"):
                codes.append(str(structured_payload.get("code")))
        content_text = item.get("content_text")
        if isinstance(content_text, str) and content_text.strip().startswith("{"):
            try:
                payload = json.loads(content_text)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict) and error.get("code"):
                    codes.append(str(error.get("code")))
                if payload.get("code"):
                    codes.append(str(payload.get("code")))
    return [str(code) for code in codes if str(code).strip()]


def _setup_taxonomy_dimensions(
    *,
    dimensions: dict[str, dict[str, Any]],
    reason_codes: list[str],
    activation_check: dict[str, Any],
    failure_layer: str | None,
) -> dict[str, dict[str, Any]]:
    return {
        "prompt_instruction": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "prompt."),
            summary="Prompt / instruction alignment for step convergence and finish discipline.",
            evidence=list((dimensions.get("instruction_prompt_skill") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "prompt."),
        ),
        "model_behavior": _taxonomy_dimension_entry(
            status=_dimension_status(dimensions, "structured_output_contract") or "pass",
            summary="Model behavior against structured output and repair expectations.",
            evidence=list((dimensions.get("structured_output_contract") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "model."),
        ),
        "tool_contract": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "tool_contract."),
            summary="Tool argument and contract correctness.",
            evidence=list((dimensions.get("tool_contract_execution") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "tool_contract."),
        ),
        "tool_execution": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "tool_execution."),
            summary="Tool execution and recoverability after invocation.",
            evidence=list((dimensions.get("tool_contract_execution") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "tool_execution."),
        ),
        "deterministic_controller": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "controller."),
            summary="Deterministic controller and commit/readiness policy correctness.",
            evidence=list((dimensions.get("decision_policy") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "controller."),
        ),
        "runtime_private_cognition": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "cognition."),
            summary="Runtime-private cognition invalidation and reconciliation correctness.",
            evidence=list((dimensions.get("decision_policy") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "cognition."),
        ),
        "readiness_activation_gate": _taxonomy_dimension_entry(
            status="fail"
            if _codes_with_prefix(reason_codes, "readiness.") or _codes_with_prefix(reason_codes, "activation.")
            else ("warn" if activation_check else "pass"),
            summary="Readiness and activation-gate contract between setup outcome and activation bootstrap.",
            evidence=_compact_evidence(
                [
                    _fmt("ready", activation_check.get("ready") if isinstance(activation_check, dict) else None),
                    _fmt(
                        "blocking_issue_count",
                        len(activation_check.get("blocking_issues") or [])
                        if isinstance(activation_check, dict)
                        else None,
                    ),
                ]
            ),
            reason_codes=_codes_with_prefix(reason_codes, "readiness.") + _codes_with_prefix(reason_codes, "activation."),
        ),
        "retrieval_readiness": _taxonomy_dimension_entry(
            status=_taxonomy_status(reason_codes, "retrieval_readiness."),
            summary="Retrieval ingestion and archival readiness required by activation.",
            evidence=_compact_evidence(
                [
                    _fmt(
                        "archival_ready_ref_count",
                        len(((activation_check.get("handoff") or {}).get("archival_ready_refs") or []))
                        if isinstance(activation_check, dict)
                        else None,
                    )
                ]
            ),
            reason_codes=_codes_with_prefix(reason_codes, "retrieval_readiness."),
        ),
        "infra_provider": _taxonomy_dimension_entry(
            status="fail" if failure_layer == "infra" else "pass",
            summary="Infrastructure and provider stability for this run.",
            evidence=list((dimensions.get("infra_model_provider") or {}).get("evidence") or []),
            reason_codes=_codes_with_prefix(reason_codes, "infra."),
        ),
    }


def _taxonomy_dimension_entry(
    *,
    status: str,
    summary: str,
    evidence: list[str],
    reason_codes: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "reason_codes": sorted(dict.fromkeys(reason_codes)),
    }


def _taxonomy_status(reason_codes: list[str], prefix: str) -> str:
    return "fail" if _codes_with_prefix(reason_codes, prefix) else "pass"


def _codes_with_prefix(reason_codes: list[str], prefix: str) -> list[str]:
    return [code for code in reason_codes if str(code).startswith(prefix)]


def _secondary_suspects(
    *,
    dimensions: dict[str, dict[str, Any]],
    primary_suspects: list[str],
) -> list[str]:
    secondary: list[str] = []
    for name in (
        "instruction_prompt_skill",
        "tool_contract_execution",
        "decision_policy",
        "structured_output_contract",
        "token_efficiency",
    ):
        if name in primary_suspects:
            continue
        if _dimension_status(dimensions, name) == "warn":
            secondary.append(name)
    return secondary[:3]


def _setup_evidence_refs(
    *,
    reason_codes: list[str],
    activation_check: dict[str, Any],
    cognitive_summary: dict[str, Any],
    tool_results: list[Any],
) -> list[str]:
    refs = ["artifact:runtime_result"]
    if tool_results:
        refs.append("artifact:tool_sequence")
    if cognitive_summary:
        refs.append("artifact:cognitive_state_summary")
    if activation_check:
        refs.append("artifact:activation_check")
        if isinstance(activation_check.get("handoff"), dict):
            refs.append("artifact:activation_handoff_snapshot")
    if any(code.startswith("readiness.") for code in reason_codes):
        refs.append("artifact:readiness_snapshot")
    return refs


def _setup_recommended_next_action(
    *,
    primary_suspects: list[str],
    reason_codes: list[str],
) -> str | None:
    reason_mapping = {
        "tool_contract.truth_write_target_ref_mismatch": "tighten_truth_write_target_ref_validation_and_add_targeted_repair_prompt",
        "tool_execution.schema_validation_failed": "strengthen_tool_argument_schema_repair_and_retry_policy",
        "controller.commit_proposal_blocked": "tighten_commit_readiness_checks_and_review_block_messages",
        "cognition.invalidated_by_user_edit": "refresh_runtime_private_cognition_after_user_edit_before_next_commit_attempt",
        "cognition.invalidated_by_proposal_reject": "reset_rejected_proposal_state_and_force_refinement_path",
        "retrieval_readiness.ingestion_not_completed": "complete_retrieval_ingestion_before_marking_workspace_ready",
        "activation.handoff_missing_required_fields": "fill_activation_handoff_required_fields_and_refs",
        "infra.provider_request_failed": "fix_provider_model_config_and_runtime_connectivity",
        "infra.database_unavailable": "restore_database_connectivity_before_rerunning_setup_eval",
    }
    for reason_code in reason_codes:
        if reason_code in reason_mapping:
            return reason_mapping[reason_code]
    candidates = _optimization_candidates(primary_suspects)
    return candidates[0] if candidates else None


def _setup_outcome_chain(
    *,
    capabilities: dict[str, dict[str, Any]],
    activation_check: dict[str, Any],
) -> dict[str, str]:
    handoff = activation_check.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    ready = bool(activation_check.get("ready"))
    blocking_issues = activation_check.get("blocking_issues")
    if not isinstance(blocking_issues, list):
        blocking_issues = []
    handoff_complete = _activation_handoff_complete(handoff)
    readiness_status = "pass" if ready else ("warn" if blocking_issues else "fail")
    handoff_status = (
        "pass" if handoff_complete else ("warn" if ready or handoff else "fail")
    )
    bootstrap_status = "pass" if ready and handoff_complete else (
        "warn" if not ready and blocking_issues else "fail"
    )
    return {
        "transcript_status": str(
            (capabilities.get("clarification_gap_detection") or {}).get("status") or "fail"
        ),
        "cognition_status": str(
            (capabilities.get("state_adaptation") or {}).get("status") or "fail"
        ),
        "truth_status": str(
            (capabilities.get("commit_readiness_judgement") or {}).get("status") or "fail"
        ),
        "readiness_status": readiness_status,
        "activation_handoff_status": handoff_status,
        "runtime_bootstrap_readiness_status": bootstrap_status,
    }


def _activation_handoff_complete(handoff: dict[str, Any]) -> bool:
    runtime_story_config = handoff.get("runtime_story_config")
    writer_contract = handoff.get("writer_contract")
    foundation_commit_refs = handoff.get("foundation_commit_refs")
    return bool(
        isinstance(runtime_story_config, dict)
        and runtime_story_config
        and isinstance(writer_contract, dict)
        and writer_contract
        and isinstance(foundation_commit_refs, list)
        and foundation_commit_refs
        and handoff.get("blueprint_commit_ref")
    )


def _dimension_entry(
    *,
    status: DiagnosticStatus,
    summary: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
    }


def _capability_entry(
    *,
    status: DiagnosticStatus,
    summary: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
    }


def _extract_usage(latest_response: Any) -> dict[str, int | None]:
    usage_payload: dict[str, Any] | None = None
    if isinstance(latest_response, dict):
        usage = latest_response.get("usage")
        if isinstance(usage, dict):
            usage_payload = usage
    if not isinstance(usage_payload, dict):
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
    completion_tokens = int(usage_payload.get("completion_tokens") or 0)
    total_tokens = int(
        usage_payload.get("total_tokens") or (prompt_tokens + completion_tokens)
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _find_subjective_hook(
    hook_results: list[dict[str, Any]],
    *,
    rubric_ref: str,
) -> dict[str, Any] | None:
    for item in hook_results:
        if isinstance(item, dict) and item.get("rubric_ref") == rubric_ref:
            return item
    return None


def _fmt(label: str, value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    return f"{label}={value}"


def _compact_evidence(items: list[str | None]) -> list[str]:
    return [item for item in items if item]


def _dimension_status(dimensions: dict[str, dict[str, Any]], name: str) -> str | None:
    entry = dimensions.get(name) or {}
    status = entry.get("status")
    return str(status) if status is not None else None
