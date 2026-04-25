from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.case_loader import load_case
from rp.eval.graders.deterministic import evaluate_diagnostic_expectation_scores
from rp.eval.models import EvalCase, EvalFailure, EvalRun, EvalRunResult, EvalTrace
from rp.eval.reporting import attach_diagnostic_expectation_results, build_report
from rp.eval.runner import EvalRunner
from rp.tests.test_eval_setup_cognitive_cases import _TruthWriteAskUserLLMService


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / "setup"
        / Path(*parts)
    )


def _eval_case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / Path(*parts)
    )


@pytest.mark.asyncio
async def test_setup_eval_report_includes_capability_and_diagnostic_summary(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _TruthWriteAskUserLLMService(),
    )

    case = load_case(
        _case_path("repair", "writing_contract_ask_user_after_semantic_fail.v1.json")
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    diagnostics = result.report["diagnostics"]
    capabilities = diagnostics["capabilities"]
    attribution = diagnostics["attribution"]
    observability = diagnostics["observability"]

    assert capabilities["task_completion"]["status"] == "pass"
    assert capabilities["clarification_gap_detection"]["status"] == "pass"
    assert capabilities["repair_recovery"]["status"] == "pass"
    assert attribution["dimensions"]["infra_model_provider"]["status"] == "pass"
    assert attribution["dimensions"]["tool_contract_execution"]["status"] == "warn"
    assert attribution["dimensions"]["decision_policy"]["status"] == "pass"
    assert attribution["dimensions"]["structured_output_contract"]["status"] == "pass"
    assert "tool_contract_execution" in attribution["primary_suspects"]
    assert "tighten_tool_schema_and_error_messages" in attribution["optimization_candidates"]
    assert "tool_execution.provider_execution_failed" in diagnostics["reason_codes"]
    assert diagnostics["outcome_chain"]["transcript_status"] == "pass"
    assert diagnostics["recommended_next_action"] is not None
    assert {
        item["score_name"]: item["status"]
        for item in result.report["diagnostic_expectation_results"]
    } == {
        "diagnostic.reason_code_presence": "pass",
        "diagnostic.attribution_primary_suspect_alignment": "pass",
        "diagnostic.outcome_chain_alignment": "pass",
    }
    assert any(
        score.name == "diagnostic.reason_code_presence" and score.status == "pass"
        for score in result.scores
    )
    assert observability["usage"]["total_tokens"] == 2
    assert observability["request_metrics"]["system_prompt_chars"] is not None
    assert observability["tooling"]["failure_count"] == 1


@pytest.mark.asyncio
async def test_activation_eval_report_includes_capability_and_diagnostic_summary(
    retrieval_session,
):
    case = load_case(_eval_case_path("activation", "bootstrap", "ready_workspace_activation.v1.json"))
    result = await EvalRunner(retrieval_session).run_case(case)

    diagnostics = result.report["diagnostics"]
    capabilities = diagnostics["capabilities"]
    attribution = diagnostics["attribution"]
    observability = diagnostics["observability"]["activation"]

    assert capabilities["readiness_gate"]["status"] == "pass"
    assert capabilities["handoff_integrity"]["status"] == "pass"
    assert capabilities["session_bootstrap"]["status"] == "pass"
    assert attribution["dimensions"]["setup_readiness_contract"]["status"] == "pass"
    assert attribution["dimensions"]["bootstrap_execution"]["status"] == "pass"
    assert attribution["primary_suspects"] == []
    assert observability["ready"] is True
    assert observability["activation_success"] is True


@pytest.mark.asyncio
async def test_activation_eval_report_attributes_blocked_activation_to_setup_readiness(
    retrieval_session,
):
    case = load_case(_eval_case_path("activation", "gate", "missing_blueprint_blocks_activation.v1.json"))
    result = await EvalRunner(retrieval_session).run_case(case)

    diagnostics = result.report["diagnostics"]

    assert diagnostics["capabilities"]["readiness_gate"]["status"] == "pass"
    assert diagnostics["capabilities"]["session_bootstrap"]["status"] == "not_applicable"
    assert diagnostics["attribution"]["dimensions"]["setup_readiness_contract"]["status"] == "warn"
    assert diagnostics["attribution"]["primary_suspects"][0] == "setup_readiness_contract"


def test_build_report_diagnostics_prioritize_infra_failure():
    case = EvalCase.model_validate(
        {
            "case_id": "setup.diag.infra.v1",
            "title": "infra diag",
            "scope": "setup",
            "category": "repair",
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "input": {"request": {}, "workspace_seed": {}, "env_overrides": {}},
            "preconditions": {},
            "expected": {"deterministic_assertions": [], "subjective_hooks": []},
            "trace_hooks": {
                "capture_runtime_events": True,
                "capture_graph_debug": True,
                "capture_workspace_before_after": True,
            },
            "repeat": {"count": 1, "stop_on_first_hard_failure": False},
            "baseline": {"compare_by": [], "baseline_tags": ["main"]},
            "metadata": {},
        }
    )
    result = EvalRunResult(
        case=case,
        run=EvalRun(
            run_id="run-diag-infra-1",
            case_id=case.case_id,
            scope=case.scope,
            status="failed",
            runtime_target="setup_v2",
            trace_id="trace-diag-infra-1",
            failure=EvalFailure(
                layer="infra",
                code="APIError",
                message="provider failed",
                retryable=False,
                source="runner_exception",
            ),
        ),
        trace=EvalTrace(trace_id="trace-diag-infra-1"),
        runtime_result={"finish_reason": None, "assistant_text": "", "warnings": []},
        report={},
    )

    report = build_report(result)
    diagnostics = report["diagnostics"]

    assert diagnostics["capabilities"]["task_completion"]["status"] == "fail"
    assert diagnostics["attribution"]["dimensions"]["infra_model_provider"]["status"] == "fail"
    assert diagnostics["attribution"]["primary_suspects"] == ["infra_model_provider"]
    assert diagnostics["reason_codes"] == ["infra.provider_request_failed"]
    assert (
        diagnostics["attribution"]["optimization_candidates"][0]
        == "fix_provider_model_config_and_runtime_connectivity"
    )


def test_diagnostic_expectation_scores_fail_with_expected_vs_actual_detail():
    case = EvalCase.model_validate(
        {
            "case_id": "setup.diag.expected_mismatch.v1",
            "title": "diagnostic expectation mismatch",
            "scope": "setup",
            "category": "diagnostics",
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "expected": {
                "deterministic_assertions": [],
                "subjective_hooks": [],
                "expected_reason_codes": ["controller.commit_proposal_blocked"],
                "expected_primary_suspects": ["decision_policy"],
                "expected_outcome_chain": {"readiness_status": "pass"},
            },
        }
    )
    report = {
        "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
        "hard_failures": [],
        "diagnostics": {
            "reason_codes": ["tool_execution.provider_execution_failed"],
            "outcome_chain": {"readiness_status": "warn"},
            "attribution": {"primary_suspects": ["tool_contract_execution"]},
        },
    }

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-diag-mismatch",
        root_span_id=None,
        report=report,
    )
    attach_diagnostic_expectation_results(report, scores)

    assert [score.status for score in scores] == ["fail", "fail", "fail"]
    assert report["assertion_summary"]["fail"] == 3
    assert report["hard_failures"] == [
        "diagnostic.reason_code_presence",
        "diagnostic.attribution_primary_suspect_alignment",
        "diagnostic.outcome_chain_alignment",
    ]
    assert report["diagnostic_expectation_results"][0]["missing"] == [
        "controller.commit_proposal_blocked"
    ]
    assert report["diagnostic_expectation_results"][2]["mismatches"] == {
        "readiness_status": {"expected": "pass", "actual": "warn"}
    }

