from __future__ import annotations

from typing import Any

from rp.eval.models import (
    EvalArtifact,
    EvalCase,
    EvalFailure,
    EvalInput,
    EvalRun,
    EvalRunResult,
    EvalRuntimeTarget,
    EvalScore,
    EvalTrace,
)
from rp.eval.reporting import (
    build_report,
    render_comparison_markdown,
    render_suite_markdown,
)


def _dict_key_order(value: Any) -> Any:
    if isinstance(value, dict):
        return [
            (key, _dict_key_order(item))
            for key, item in value.items()
        ]
    if isinstance(value, list):
        return [_dict_key_order(item) for item in value]
    return None


def test_render_suite_markdown_includes_core_sections():
    markdown = render_suite_markdown(
        summary={
            "run_count": 3,
            "case_count": 2,
            "failed_run_count": 1,
            "assertion_fail_total": 2,
            "assertion_warn_total": 1,
            "hard_failure_total": 1,
            "pending_judge_hook_total": 1,
            "executed_judge_hook_total": 2,
            "subjective_average_score": 0.755,
            "ragas_status_counts": {"completed": 2, "not_requested": 1},
            "ragas_metric_averages": {
                "context_precision": 0.81,
                "faithfulness": 0.92,
            },
            "subjective_status_counts": {"pass": 1, "warn": 1, "skip": 1},
            "rubric_summaries": {
                "setup/clarification-quality/v1": {
                    "total": 2,
                    "executed": 1,
                    "pending": 1,
                    "average_numeric_score": 0.82,
                    "case_count": 1,
                }
            },
            "repeat_case_ids": ["setup.case.repeat"],
            "finish_reason_counts": {"completed_text": 2, "activation_failed": 1},
            "failure_layer_counts": {"deterministic": 1},
            "diagnostic_summary": {
                "primary_suspects": {"decision_policy": 1},
                "reason_codes": {"controller.commit_proposal_blocked": 1},
                "recommended_next_actions": {
                    "tighten_commit_readiness_checks_and_review_block_messages": 1
                },
                "outcome_chain": {
                    "readiness_status": {"warn": 1},
                    "activation_handoff_status": {"fail": 1},
                },
            },
            "case_summaries": {
                "setup.case.repeat": {
                    "run_count": 2,
                    "assertion_fail_total": 1,
                    "assertion_warn_total": 0,
                    "hard_failure_total": 1,
                    "finish_reasons": ["completed_text", "awaiting_user_input"],
                }
            },
        },
        thresholds={
            "passed": False,
            "breaches": ["assertion_fail_total>0 (actual=2)"],
        },
    )

    assert "# RP Eval Suite Summary" in markdown
    assert "- threshold_passed: False" in markdown
    assert "## Repeat Cases" in markdown
    assert "setup.case.repeat" in markdown
    assert "assertion_fail_total>0 (actual=2)" in markdown
    assert "## Judge Status" in markdown
    assert "## RAGAS" in markdown
    assert "metric context_precision: 0.81" in markdown
    assert "pass: 1" in markdown
    assert "setup/clarification-quality/v1" in markdown
    assert "primary_suspects: decision_policy" in markdown
    assert "controller.commit_proposal_blocked=1" in markdown
    assert "readiness_status: warn=1" in markdown
    assert (
        "tighten_commit_readiness_checks_and_review_block_messages=1"
        in markdown
    )


def test_render_suite_markdown_full_string_snapshot():
    markdown = render_suite_markdown(
        summary={
            "run_count": 3,
            "case_count": 2,
            "failed_run_count": 1,
            "assertion_fail_total": 2,
            "assertion_warn_total": 1,
            "hard_failure_total": 1,
            "pending_judge_hook_total": 1,
            "executed_judge_hook_total": 2,
            "subjective_average_score": 0.755,
            "ragas_status_counts": {"completed": 2, "not_requested": 1},
            "ragas_metric_averages": {
                "context_precision": 0.81,
                "faithfulness": 0.92,
            },
            "subjective_status_counts": {"pass": 1, "warn": 1, "skip": 1},
            "rubric_summaries": {
                "setup/clarification-quality/v1": {
                    "total": 2,
                    "executed": 1,
                    "pending": 1,
                    "average_numeric_score": 0.82,
                    "case_count": 1,
                }
            },
            "repeat_case_ids": ["setup.case.repeat"],
            "finish_reason_counts": {"completed_text": 2, "activation_failed": 1},
            "failure_layer_counts": {"deterministic": 1},
            "diagnostic_summary": {
                "primary_suspects": {"decision_policy": 1},
                "reason_codes": {"controller.commit_proposal_blocked": 1},
                "recommended_next_actions": {
                    "tighten_commit_readiness_checks_and_review_block_messages": 1
                },
                "outcome_chain": {
                    "readiness_status": {"warn": 1},
                    "activation_handoff_status": {"fail": 1},
                },
            },
            "case_summaries": {
                "setup.case.repeat": {
                    "run_count": 2,
                    "assertion_fail_total": 1,
                    "assertion_warn_total": 0,
                    "hard_failure_total": 1,
                    "finish_reasons": ["completed_text", "awaiting_user_input"],
                }
            },
        },
        thresholds={
            "passed": False,
            "breaches": ["assertion_fail_total>0 (actual=2)"],
        },
    )

    assert markdown == """# RP Eval Suite Summary

- run_count: 3
- case_count: 2
- failed_run_count: 1
- assertion_fail_total: 2
- assertion_warn_total: 1
- hard_failure_total: 1
- pending_judge_hook_total: 1
- executed_judge_hook_total: 2
- subjective_average_score: 0.755
- threshold_passed: False

## Finish Reasons

- completed_text: 2
- activation_failed: 1

## Failure Layers

- deterministic: 1

## Judge Hooks

- none

## Judge Status

- pass: 1
- warn: 1
- skip: 1

## Judge Rubrics

- setup/clarification-quality/v1: total=2 executed=1 pending=1 avg_score=0.82 cases=1

## Diagnostics

- primary_suspects: decision_policy
- reason_codes: controller.commit_proposal_blocked=1
- diagnostic_expectation_failures: none
- outcome_chain:
  - readiness_status: warn=1
  - activation_handoff_status: fail=1
- recommended_next_actions: tighten_commit_readiness_checks_and_review_block_messages=1

## RAGAS

- status completed: 2
- status not_requested: 1
- metric context_precision: 0.81
- metric faithfulness: 0.92

## Repeat Cases

- setup.case.repeat

## Thresholds

- breach: assertion_fail_total>0 (actual=2)

## Top Cases

- setup.case.repeat: runs=2 fails=1 warns=0 pending_judge_hooks=0 finish_reasons=completed_text, awaiting_user_input
"""


def test_build_report_output_snapshot():
    case = EvalCase(
        case_id="retrieval.case.snapshot",
        title="Snapshot reporting case",
        scope="retrieval",
        category="reporting",
        runtime_target=EvalRuntimeTarget(
            entrypoint="rp.retrieval.run",
            graph_id="retrieval_graph",
        ),
        input=EvalInput(request={"query": "Can we commit?"}),
    )
    run = EvalRun(
        run_id="run-reporting-snapshot",
        case_id=case.case_id,
        scope=case.scope,
        status="failed",
        runtime_target="in_process:retrieval_graph",
        trace_id="trace-reporting-snapshot",
        failure=EvalFailure(
            layer="deterministic",
            code="completion_guard_failed",
            message="Commit proposal blocked by readiness guard.",
        ),
    )
    result = EvalRunResult(
        case=case,
        run=run,
        trace=EvalTrace(trace_id=run.trace_id),
        artifacts=[
            EvalArtifact(
                artifact_id="artifact-subjective-clarity",
                run_id=run.run_id,
                kind="subjective_hook_record",
                name="clarity hook",
                payload={"hook_id": "clarity-hook"},
            ),
            EvalArtifact(
                artifact_id="artifact-tool-sequence",
                run_id=run.run_id,
                kind="tool_sequence",
                name="tool sequence",
                payload={},
            ),
        ],
        scores=[
            EvalScore(
                score_id="score-code-pass",
                run_id=run.run_id,
                name="deterministic_pass",
                kind="code",
                status="pass",
                value_type="boolean",
                value=True,
            ),
            EvalScore(
                score_id="score-code-fail",
                run_id=run.run_id,
                name="commit_guard_failed",
                kind="code",
                status="fail",
                value_type="boolean",
                value=False,
                severity="error",
                explanation="Commit guard blocked the run.",
            ),
            EvalScore(
                score_id="score-llm-warn",
                run_id=run.run_id,
                name="clarity_score",
                kind="llm",
                status="warn",
                value_type="numeric",
                value=0.72,
                label="borderline",
                explanation=(
                    "The answer acknowledged the blocker but still sounded "
                    "commit-ready."
                ),
                metadata={
                    "hook_id": "clarity-hook",
                    "judge_family": "setup_judge",
                    "rubric_ref": "setup/clarification-quality/v1",
                    "rubric_title": "Clarification quality",
                    "judge_model_id": "gpt-judge-mini",
                    "judge_provider_id": "openai",
                    "judge_prompt_version": "v3",
                    "judge_response_schema_version": "v1",
                    "judge_status_source": "score_band",
                    "judge_score_source": "numeric",
                    "judge_score_band": "warn",
                    "judge_score_band_conflict": False,
                    "judge_strengths": ["names blocker"],
                    "judge_issues": ["premature commit wording"],
                    "target_available": True,
                    "resolved_source": "assistant_text",
                    "resolved_path": "runtime_result.assistant_text",
                },
            ),
            EvalScore(
                score_id="score-human-skip",
                run_id=run.run_id,
                name="human_review_score",
                kind="human",
                status="skip",
                value_type="numeric",
                value=None,
                label="pending",
                explanation="Human judge was not available.",
                metadata={
                    "hook_id": "human-review-hook",
                    "judge_family": "human_review",
                    "rubric_ref": "setup/human-review/v1",
                    "rubric_title": "Human review",
                    "judge_skip_reason": "not_configured",
                    "judge_status_source": "skip_reason",
                    "target_available": False,
                },
            ),
        ],
        runtime_result={
            "finish_reason": "completed_text",
            "warnings": ["commit_proposal_blocked"],
            "tool_invocations": [
                {"tool_name": "rp_setup__setup.proposal.commit"},
            ],
            "structured_payload": {
                "cognitive_state_summary": {
                    "invalidated": True,
                    "ready_for_review": False,
                    "invalidation_reasons": ["user_edit_delta"],
                    "remaining_open_issues": ["Need explicit user approval."],
                },
                "last_failure": {
                    "failure_category": "ask_user",
                    "message": "Missing explicit approval.",
                },
                "completion_guard": {
                    "reason": "truth_write_not_ready_for_review",
                },
                "pending_obligation": {
                    "obligation_type": "reassess_commit_readiness",
                },
            },
        },
    )

    expected = {
        "run_id": "run-reporting-snapshot",
        "case_id": "retrieval.case.snapshot",
        "scope": "retrieval",
        "status": "failed",
        "assertion_summary": {"pass": 1, "fail": 1, "warn": 1, "skip": 1},
        "hard_failures": ["commit_guard_failed"],
        "failure_layer": "deterministic",
        "finish_reason": "completed_text",
        "tool_calls": ["setup.proposal.commit"],
        "repair_route": "block_commit",
        "completion_guard_reason": "truth_write_not_ready_for_review",
        "last_failure_category": "ask_user",
        "last_failure_message": "Missing explicit approval.",
        "cognitive_state_invalidated": True,
        "cognitive_ready_for_review": False,
        "cognitive_invalidation_reasons": ["user_edit_delta"],
        "remaining_open_issues": ["Need explicit user approval."],
        "commit_blocked": True,
        "subjective_hook_summary": {
            "total": 2,
            "pending": 1,
            "executed": 1,
            "judge_family_counts": {"human_review": 1, "setup_judge": 1},
            "rubric_refs": [
                "setup/clarification-quality/v1",
                "setup/human-review/v1",
            ],
            "status_counts": {"skip": 1, "warn": 1},
            "average_numeric_score": 0.72,
            "rubric_summaries": {
                "setup/clarification-quality/v1": {
                    "total": 1,
                    "pending": 0,
                    "executed": 1,
                    "status_counts": {"warn": 1},
                    "average_numeric_score": 0.72,
                    "hook_ids": ["clarity-hook"],
                    "case_count": 1,
                },
                "setup/human-review/v1": {
                    "total": 1,
                    "pending": 1,
                    "executed": 0,
                    "status_counts": {"skip": 1},
                    "average_numeric_score": None,
                    "hook_ids": ["human-review-hook"],
                    "case_count": 1,
                },
            },
            "artifact_count": 1,
        },
        "subjective_hook_results": [
            {
                "hook_id": "clarity-hook",
                "artifact_id": "artifact-subjective-clarity",
                "judge_family": "setup_judge",
                "rubric_ref": "setup/clarification-quality/v1",
                "rubric_title": "Clarification quality",
                "status": "warn",
                "score": 0.72,
                "label": "borderline",
                "explanation": (
                    "The answer acknowledged the blocker but still sounded "
                    "commit-ready."
                ),
                "judge_model_id": "gpt-judge-mini",
                "judge_provider_id": "openai",
                "judge_prompt_version": "v3",
                "judge_response_schema_version": "v1",
                "judge_skip_reason": None,
                "judge_status_source": "score_band",
                "judge_score_source": "numeric",
                "judge_score_band": "warn",
                "judge_score_band_conflict": False,
                "judge_strengths": ["names blocker"],
                "judge_issues": ["premature commit wording"],
                "target_available": True,
                "resolved_source": "assistant_text",
                "resolved_path": "runtime_result.assistant_text",
            },
            {
                "hook_id": "human-review-hook",
                "artifact_id": None,
                "judge_family": "human_review",
                "rubric_ref": "setup/human-review/v1",
                "rubric_title": "Human review",
                "status": "skip",
                "score": None,
                "label": "pending",
                "explanation": "Human judge was not available.",
                "judge_model_id": None,
                "judge_provider_id": None,
                "judge_prompt_version": None,
                "judge_response_schema_version": None,
                "judge_skip_reason": "not_configured",
                "judge_status_source": "skip_reason",
                "judge_score_source": None,
                "judge_score_band": None,
                "judge_score_band_conflict": False,
                "judge_strengths": [],
                "judge_issues": [],
                "target_available": False,
                "resolved_source": None,
                "resolved_path": None,
            },
        ],
        "subjective_hook_artifact_ids": ["artifact-subjective-clarity"],
        "pending_judge_hook_ids": ["human-review-hook"],
        "end_reason_summary": "truth_write_not_ready_for_review",
        "ragas": None,
        "diagnostics": {
            "diagnostic_version": "v1",
            "capabilities": {},
            "attribution": {
                "primary_suspects": [],
                "optimization_candidates": [],
                "dimensions": {},
            },
            "observability": {
                "supported_scope": "retrieval",
                "diagnostic_mode": "not_implemented_for_scope",
            },
        },
        "reason_codes": [],
        "outcome_chain": {},
        "outcome_chain_display": [],
        "outcome_chain_stages": [],
        "primary_suspects": [],
        "secondary_suspects": [],
        "evidence_refs": [],
        "evidence_ref_details": [],
        "recommended_next_action": None,
        "activation_check": {},
        "activation_handoff_snapshot": None,
        "diagnostic_overview": {
            "failure_layer": {
                "value": "deterministic",
                "summary": (
                    "The run hit deterministic contract, readiness, or controller "
                    "assertions."
                ),
            },
            "reason_codes": [],
            "primary_suspects": [],
            "secondary_suspects": [],
            "recommended_next_action": None,
            "outcome_chain": [],
            "evidence_refs": [],
            "diagnostic_expectation_summary": None,
            "diagnostic_version": "v1",
        },
        "diagnostic_summary_text": (
            "failure_layer=deterministic | reason_codes=none | "
            "primary_suspects=none"
        ),
    }

    report = build_report(result)

    assert report == expected
    assert _dict_key_order(report) == _dict_key_order(expected)


def test_render_comparison_markdown_includes_drift_summary():
    markdown = render_comparison_markdown(
        comparison={
            "current": {
                "executed_judge_hook_total": 2,
                "subjective_average_score": 0.74,
                "ragas_metric_averages": {"context_precision": 0.84},
            },
            "baseline": {
                "executed_judge_hook_total": 1,
                "subjective_average_score": 0.91,
                "ragas_metric_averages": {"context_precision": 0.72},
            },
            "added_case_ids": ["retrieval.case.new"],
            "removed_case_ids": ["setup.case.old"],
            "changed_cases": [
                {
                    "case_id": "setup.case.changed",
                    "deltas": {
                        "run_count": 0,
                        "assertion_fail_total": 1,
                        "assertion_warn_total": 0,
                        "hard_failure_total": 1,
                        "pending_judge_hook_count": -1,
                        "executed_judge_hook_count": 1,
                        "subjective_average_score": -0.17,
                        "reason_code_deltas": {
                            "added": ["controller.commit_proposal_blocked"],
                            "removed": ["prompt.missing_step_targeting"],
                        },
                        "primary_suspect_deltas": {
                            "added": ["decision_policy"],
                            "removed": ["instruction_prompt_skill"],
                        },
                        "outcome_chain_deltas": {
                            "readiness_status": {
                                "added": ["warn"],
                                "removed": ["pass"],
                            }
                        },
                        "recommended_next_action_deltas": {
                            "added": [
                                "tighten_commit_readiness_checks_and_review_block_messages"
                            ],
                            "removed": ["ask_for_missing_setup_inputs"],
                        },
                        "ragas_metric_deltas": {"context_precision": 0.12},
                    },
                }
            ],
            "drift_summary": {
                "changed_case_count": 1,
                "changed_finish_reason_case_ids": ["setup.case.changed"],
                "changed_failure_layer_case_ids": [],
                "changed_hard_failure_case_ids": ["setup.case.changed"],
                "changed_pending_judge_case_ids": ["setup.case.changed"],
                "changed_executed_judge_case_ids": ["setup.case.changed"],
                "changed_subjective_status_case_ids": ["setup.case.changed"],
                "changed_subjective_score_case_ids": ["setup.case.changed"],
                "changed_ragas_case_ids": ["setup.case.changed"],
            },
        }
    )

    assert "# RP Eval Comparison" in markdown
    assert "retrieval.case.new" in markdown
    assert "setup.case.old" in markdown
    assert "finish_reason_drifts: setup.case.changed" in markdown
    assert "hard_failure_drifts: setup.case.changed" in markdown
    assert "pending_judge_drifts: setup.case.changed" in markdown
    assert "subjective_status_drifts: setup.case.changed" in markdown
    assert "ragas_drifts: setup.case.changed" in markdown
    assert "executed_hooks current=2 baseline=1" in markdown
    assert (
        "reason_code_deltas=added=controller.commit_proposal_blocked;"
        "removed=prompt.missing_step_targeting"
    ) in markdown
    assert "diagnostic_drift:" in markdown
    assert "outcome chain readiness_status(added=warn;removed=pass)" in markdown
