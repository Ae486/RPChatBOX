from __future__ import annotations

from rp.eval.reporting import render_comparison_markdown, render_suite_markdown


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
