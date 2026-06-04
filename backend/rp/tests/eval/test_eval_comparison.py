from __future__ import annotations

import json

from rp.eval.comparison import (
    _aggregate_cases,
    compare_suite_outputs,
    evaluate_suite_thresholds,
    summarize_suite,
)


def test_summarize_suite_and_aggregate_cases_output_snapshot():
    payload = {
        "suite_id": "snapshot-suite",
        "items": [
            {
                "case_id": "setup.case.shared",
                "run_id": "run-1",
                "report": {
                    "case_id": "setup.case.shared",
                    "status": "failed",
                    "finish_reason": "awaiting_user_input",
                    "failure_layer": "controller",
                    "hard_failures": ["commit_blocked"],
                    "assertion_summary": {
                        "pass": 1,
                        "fail": 2,
                        "warn": 1,
                        "skip": 0,
                    },
                    "pending_judge_hook_ids": ["judge.pending"],
                    "primary_suspects": ["decision_policy"],
                    "reason_codes": ["controller.commit_proposal_blocked"],
                    "recommended_next_action": "ask_user_for_missing_foundation",
                    "outcome_chain": {
                        "transcript_status": "fail",
                        "commit_status": "blocked",
                    },
                    "diagnostic_expectation_results": [
                        {
                            "score_name": "diagnostic.reason_code_presence",
                            "status": "fail",
                        },
                        {
                            "score_name": "diagnostic.outcome_chain",
                            "status": "pass",
                        },
                    ],
                    "ragas": {
                        "status": "completed",
                        "metric_summary": {
                            "context_precision": 0.5,
                            "faithfulness": 0.8,
                        },
                    },
                    "subjective_hook_summary": {
                        "executed": 1,
                        "pending": 1,
                        "status_counts": {"warn": 1, "skip": 1},
                        "judge_family_counts": {"llm_judge": 2},
                    },
                    "subjective_hook_results": [
                        {
                            "hook_id": "judge.quality",
                            "rubric_ref": "setup/quality/v1",
                            "status": "warn",
                            "score": 0.75,
                        },
                        {
                            "hook_id": "judge.safety",
                            "rubric_ref": "setup/safety/v1",
                            "status": "skip",
                            "score": None,
                        },
                    ],
                },
            },
            {
                "case_id": "setup.case.shared",
                "run_id": "run-2",
                "report": {
                    "case_id": "setup.case.shared",
                    "status": "completed",
                    "finish_reason": "completed_text",
                    "failure_layer": "runtime",
                    "hard_failures": ["tool_timeout"],
                    "assertion_summary": {
                        "pass": 2,
                        "fail": 0,
                        "warn": 1,
                        "skip": 1,
                    },
                    "pending_judge_hook_ids": [],
                    "diagnostics": {
                        "reason_codes": ["prompt.missing_step_targeting"],
                        "recommended_next_action": "tighten_prompt_stage_targeting",
                        "outcome_chain": {
                            "transcript_status": "warn",
                            "commit_status": "pass",
                        },
                        "attribution": {
                            "primary_suspects": ["instruction_prompt_skill"],
                            "recommended_next_action": "ignored_attribution_action",
                        },
                    },
                    "diagnostic_expectation_results": [
                        {
                            "score_name": "diagnostic.outcome_chain",
                            "status": "fail",
                        }
                    ],
                    "ragas": {
                        "status": "failed",
                        "metric_summary": {
                            "context_precision": 0.7,
                            "faithfulness": 0.9,
                        },
                    },
                    "subjective_hook_summary": {
                        "executed": 1,
                        "pending": 0,
                        "status_counts": {"pass": 1},
                        "judge_family_counts": {"rule_judge": 1},
                    },
                    "subjective_hook_results": [
                        {
                            "hook_id": "judge.quality",
                            "rubric_ref": "setup/quality/v1",
                            "status": "pass",
                            "score": 0.95,
                        }
                    ],
                },
            },
            {
                "case_id": "setup.case.shared",
                "run_id": "run-3",
                "report": {
                    "case_id": "setup.case.shared",
                    "status": "completed",
                    "finish_reason": "upstream_error",
                    "failure_layer": "provider",
                    "hard_failures": [],
                    "assertion_summary": {
                        "pass": 0,
                        "fail": 1,
                        "warn": 0,
                        "skip": 1,
                    },
                    "pending_judge_hook_ids": ["judge.backup"],
                    "diagnostics": {
                        "reason_codes": ["provider.upstream_error"],
                        "outcome_chain": {
                            "transcript_status": None,
                            "commit_status": "unknown",
                        },
                        "attribution": {
                            "primary_suspects": ["provider_gateway"],
                            "recommended_next_action": "retry_with_backup_provider",
                        },
                    },
                    "diagnostic_expectation_results": [
                        {
                            "score_name": "diagnostic.provider_status",
                            "status": "fail",
                        }
                    ],
                    "ragas": {
                        "status": "skipped",
                        "metric_summary": {
                            "answer_relevancy": 0.6,
                            "context_precision": "n/a",
                        },
                    },
                    "subjective_hook_summary": {
                        "executed": 0,
                        "pending": 1,
                        "status_counts": {"skip": 1},
                        "judge_family_counts": {"llm_judge": 1},
                    },
                    "subjective_hook_results": [
                        {
                            "hook_id": "judge.backup",
                            "rubric_ref": "setup/quality/v1",
                            "status": "skip",
                            "score": 0.2,
                        }
                    ],
                },
            },
        ],
    }
    expected_aggregate = {
        "setup.case.shared": {
            "run_count": 3,
            "statuses": ["completed", "failed"],
            "finish_reasons": [
                "awaiting_user_input",
                "completed_text",
                "upstream_error",
            ],
            "failure_layers": ["controller", "provider", "runtime"],
            "assertion_fail_total": 3,
            "assertion_warn_total": 2,
            "hard_failure_total": 2,
            "hard_failures": ["commit_blocked", "tool_timeout"],
            "pending_judge_hook_count": 2,
            "executed_judge_hook_count": 2,
            "subjective_hook_statuses": {
                "judge.backup": ["skip"],
                "judge.quality": ["pass", "warn"],
                "judge.safety": ["skip"],
            },
            "subjective_hook_score_averages": {"judge.quality": 0.85},
            "subjective_rubric_scores": {"setup/quality/v1": 0.85},
            "subjective_average_score": 0.85,
            "primary_suspects": [
                "decision_policy",
                "instruction_prompt_skill",
                "provider_gateway",
            ],
            "reason_codes": [
                "controller.commit_proposal_blocked",
                "prompt.missing_step_targeting",
                "provider.upstream_error",
            ],
            "recommended_next_actions": [
                "ask_user_for_missing_foundation",
                "retry_with_backup_provider",
                "tighten_prompt_stage_targeting",
            ],
            "outcome_chain": {
                "commit_status": ["blocked", "pass", "unknown"],
                "transcript_status": ["fail", "unknown", "warn"],
            },
            "diagnostic_expectation_failures": [
                "diagnostic.outcome_chain",
                "diagnostic.provider_status",
                "diagnostic.reason_code_presence",
            ],
            "ragas_statuses": ["completed", "failed", "skipped"],
            "ragas_metric_averages": {
                "answer_relevancy": 0.6,
                "context_precision": 0.6,
                "faithfulness": 0.85,
            },
        }
    }
    expected_summary = {
        "suite_id": "snapshot-suite",
        "case_count": 1,
        "run_count": 3,
        "failed_run_count": 1,
        "assertion_fail_total": 3,
        "assertion_warn_total": 2,
        "hard_failure_total": 2,
        "repeat_case_ids": ["setup.case.shared"],
        "finish_reason_counts": {
            "awaiting_user_input": 1,
            "completed_text": 1,
            "upstream_error": 1,
        },
        "failure_layer_counts": {"controller": 1, "provider": 1, "runtime": 1},
        "pending_judge_hook_total": 2,
        "executed_judge_hook_total": 2,
        "judge_family_counts": {"llm_judge": 3, "rule_judge": 1},
        "subjective_status_counts": {"pass": 1, "skip": 2, "warn": 1},
        "subjective_average_score": 0.85,
        "rubric_summaries": {
            "setup/quality/v1": {
                "total": 3,
                "pending": 1,
                "executed": 2,
                "status_counts": {"pass": 1, "skip": 1, "warn": 1},
                "average_numeric_score": 0.85,
                "case_count": 1,
                "hook_ids": ["judge.backup", "judge.quality"],
            },
            "setup/safety/v1": {
                "total": 1,
                "pending": 1,
                "executed": 0,
                "status_counts": {"skip": 1},
                "average_numeric_score": None,
                "case_count": 1,
                "hook_ids": ["judge.safety"],
            },
        },
        "ragas_status_counts": {"completed": 1, "failed": 1, "skipped": 1},
        "ragas_metric_averages": {
            "answer_relevancy": 0.6,
            "context_precision": 0.6,
            "faithfulness": 0.85,
        },
        "diagnostic_summary": {
            "primary_suspects": {
                "decision_policy": 1,
                "instruction_prompt_skill": 1,
                "provider_gateway": 1,
            },
            "reason_codes": {
                "controller.commit_proposal_blocked": 1,
                "prompt.missing_step_targeting": 1,
                "provider.upstream_error": 1,
            },
            "recommended_next_actions": {
                "ask_user_for_missing_foundation": 1,
                "retry_with_backup_provider": 1,
                "tighten_prompt_stage_targeting": 1,
            },
            "diagnostic_expectation_failures": {
                "diagnostic.outcome_chain": 1,
                "diagnostic.provider_status": 1,
                "diagnostic.reason_code_presence": 1,
            },
            "outcome_chain": {
                "commit_status": {"blocked": 1, "pass": 1, "unknown": 1},
                "transcript_status": {"fail": 1, "unknown": 1, "warn": 1},
            },
        },
        "case_summaries": expected_aggregate,
    }

    summary = summarize_suite(payload)
    aggregate = _aggregate_cases(payload)

    assert summary == expected_summary
    assert aggregate == expected_aggregate
    assert json.dumps(summary) == json.dumps(expected_summary)
    assert json.dumps(aggregate) == json.dumps(expected_aggregate)


def test_compare_suite_outputs_detects_added_removed_and_changed_cases(tmp_path):
    baseline_dir = tmp_path / "baseline"
    current_dir = tmp_path / "current"
    baseline_dir.mkdir()
    current_dir.mkdir()

    (baseline_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "baseline",
                "items": [
                    {
                        "case_id": "setup.case.a",
                        "run_id": "run-a-1",
                        "report": {
                            "case_id": "setup.case.a",
                            "status": "completed",
                            "finish_reason": "completed_text",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 2, "fail": 0, "warn": 0, "skip": 0},
                            "reason_codes": ["prompt.missing_step_targeting"],
                            "primary_suspects": ["instruction_prompt_skill"],
                            "outcome_chain": {"transcript_status": "pass"},
                            "recommended_next_action": "ask_for_missing_setup_inputs",
                        },
                    },
                    {
                        "case_id": "setup.case.removed",
                        "run_id": "run-removed-1",
                        "report": {
                            "case_id": "setup.case.removed",
                            "status": "completed",
                            "finish_reason": "completed_text",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 1, "fail": 0, "warn": 0, "skip": 0},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (current_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "current",
                "items": [
                    {
                        "case_id": "setup.case.a",
                        "run_id": "run-a-2",
                        "report": {
                            "case_id": "setup.case.a",
                            "status": "completed",
                            "finish_reason": "awaiting_user_input",
                            "failure_layer": None,
                            "hard_failures": ["finish_reason_changed"],
                            "assertion_summary": {"pass": 1, "fail": 1, "warn": 0, "skip": 0},
                            "reason_codes": [
                                "prompt.missing_step_targeting",
                                "controller.commit_proposal_blocked",
                            ],
                            "primary_suspects": ["decision_policy"],
                            "outcome_chain": {"transcript_status": "warn"},
                            "recommended_next_action": "tighten_commit_readiness_checks_and_review_block_messages",
                            "diagnostic_expectation_results": [
                                {
                                    "score_name": "diagnostic.reason_code_presence",
                                    "status": "fail",
                                    "expected": ["readiness.blocked_by_open_setup_prerequisites"],
                                    "actual": ["prompt.missing_step_targeting"],
                                }
                            ],
                        },
                    },
                    {
                        "case_id": "setup.case.added",
                        "run_id": "run-added-1",
                        "report": {
                            "case_id": "setup.case.added",
                            "status": "completed",
                            "finish_reason": "completed_text",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 1, "fail": 0, "warn": 1, "skip": 0},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    comparison = compare_suite_outputs(current_dir, baseline_dir)

    assert comparison["added_case_ids"] == ["setup.case.added"]
    assert comparison["removed_case_ids"] == ["setup.case.removed"]
    assert len(comparison["changed_cases"]) == 1
    assert comparison["changed_cases"][0]["case_id"] == "setup.case.a"
    assert comparison["changed_cases"][0]["deltas"]["assertion_fail_total"] == 1
    assert comparison["changed_cases"][0]["deltas"]["reason_code_deltas"]["added"] == [
        "controller.commit_proposal_blocked"
    ]
    assert comparison["changed_cases"][0]["deltas"]["primary_suspect_deltas"] == {
        "added": ["decision_policy"],
        "removed": ["instruction_prompt_skill"],
    }
    assert comparison["changed_cases"][0]["deltas"][
        "diagnostic_expectation_failure_deltas"
    ]["added"] == ["diagnostic.reason_code_presence"]
    assert comparison["changed_cases"][0]["deltas"][
        "recommended_next_action_deltas"
    ] == {
        "added": ["tighten_commit_readiness_checks_and_review_block_messages"],
        "removed": ["ask_for_missing_setup_inputs"],
    }
    assert comparison["drift_summary"]["changed_case_count"] == 1
    assert comparison["drift_summary"]["changed_finish_reason_case_ids"] == ["setup.case.a"]
    assert comparison["drift_summary"]["changed_reason_code_case_ids"] == ["setup.case.a"]
    assert comparison["drift_summary"]["changed_primary_suspect_case_ids"] == [
        "setup.case.a"
    ]
    assert comparison["drift_summary"]["changed_recommended_next_action_case_ids"] == [
        "setup.case.a"
    ]
    assert comparison["drift_summary"]["changed_diagnostic_expectation_case_ids"] == [
        "setup.case.a"
    ]


def test_summarize_suite_and_thresholds_support_repeat_runs_and_soft_fail(tmp_path):
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "repeat-suite",
                "items": [
                    {
                        "case_id": "retrieval.case.repeat",
                        "run_id": "run-1",
                        "report": {
                            "case_id": "retrieval.case.repeat",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 4, "fail": 0, "warn": 1, "skip": 0},
                        },
                    },
                    {
                        "case_id": "retrieval.case.repeat",
                        "run_id": "run-2",
                        "report": {
                            "case_id": "retrieval.case.repeat",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": ["query_miss"],
                            "assertion_summary": {"pass": 3, "fail": 1, "warn": 0, "skip": 0},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_suite(suite_dir)
    thresholds = evaluate_suite_thresholds(
        suite_dir,
        allowed_soft_fail_case_ids={"retrieval.case.repeat"},
        max_fail=0,
        max_warn=2,
    )

    assert summary["run_count"] == 2
    assert summary["repeat_case_ids"] == ["retrieval.case.repeat"]
    assert summary["hard_failure_total"] == 1
    assert summary["case_summaries"]["retrieval.case.repeat"]["run_count"] == 2
    assert thresholds["passed"] is True
    assert thresholds["soft_failed_case_ids"] == ["retrieval.case.repeat"]
    assert thresholds["effective_fail_total"] == 0


def test_summarize_suite_and_compare_track_subjective_judge_metrics(tmp_path):
    baseline_dir = tmp_path / "baseline-judge"
    current_dir = tmp_path / "current-judge"
    baseline_dir.mkdir()
    current_dir.mkdir()

    (baseline_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "baseline-judge",
                "items": [
                    {
                        "case_id": "retrieval.case.subjective",
                        "run_id": "run-baseline-1",
                        "report": {
                            "case_id": "retrieval.case.subjective",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": [],
                            "pending_judge_hook_ids": ["retrieval_query_quality"],
                            "assertion_summary": {"pass": 4, "fail": 0, "warn": 0, "skip": 1},
                            "subjective_hook_summary": {
                                "executed": 0,
                                "pending": 1,
                                "status_counts": {"skip": 1},
                                "judge_family_counts": {"llm_judge": 1},
                            },
                            "subjective_hook_results": [
                                {
                                    "hook_id": "retrieval_query_quality",
                                    "rubric_ref": "retrieval/query-quality/v1",
                                    "status": "skip",
                                    "score": None,
                                }
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (current_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "current-judge",
                "items": [
                    {
                        "case_id": "retrieval.case.subjective",
                        "run_id": "run-current-1",
                        "report": {
                            "case_id": "retrieval.case.subjective",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": [],
                            "pending_judge_hook_ids": [],
                            "assertion_summary": {"pass": 4, "fail": 0, "warn": 1, "skip": 0},
                            "subjective_hook_summary": {
                                "executed": 1,
                                "pending": 0,
                                "status_counts": {"warn": 1},
                                "judge_family_counts": {"llm_judge": 1},
                            },
                            "subjective_hook_results": [
                                {
                                    "hook_id": "retrieval_query_quality",
                                    "rubric_ref": "retrieval/query-quality/v1",
                                    "status": "warn",
                                    "score": 0.62,
                                }
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    baseline_summary = summarize_suite(baseline_dir)
    current_summary = summarize_suite(current_dir)
    comparison = compare_suite_outputs(current_dir, baseline_dir)

    assert baseline_summary["pending_judge_hook_total"] == 1
    assert current_summary["executed_judge_hook_total"] == 1
    assert current_summary["subjective_average_score"] == 0.62
    assert current_summary["rubric_summaries"]["retrieval/query-quality/v1"]["executed"] == 1
    assert comparison["changed_cases"][0]["deltas"]["pending_judge_hook_count"] == -1
    assert comparison["changed_cases"][0]["deltas"]["executed_judge_hook_count"] == 1
    assert comparison["changed_cases"][0]["deltas"]["subjective_average_score"] == 0.62
    assert comparison["drift_summary"]["changed_pending_judge_case_ids"] == [
        "retrieval.case.subjective"
    ]
    assert comparison["drift_summary"]["changed_subjective_status_case_ids"] == [
        "retrieval.case.subjective"
    ]


def test_summarize_suite_and_compare_track_ragas_metrics(tmp_path):
    baseline_dir = tmp_path / "baseline-ragas"
    current_dir = tmp_path / "current-ragas"
    baseline_dir.mkdir()
    current_dir.mkdir()

    (baseline_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "baseline-ragas",
                "items": [
                    {
                        "case_id": "retrieval.case.ragas",
                        "run_id": "run-baseline-1",
                        "report": {
                            "case_id": "retrieval.case.ragas",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 4, "fail": 0, "warn": 0, "skip": 0},
                            "ragas": {
                                "status": "completed",
                                "metric_summary": {
                                    "context_precision": 0.61,
                                    "faithfulness": 0.77,
                                },
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (current_dir / "suite-summary.json").write_text(
        json.dumps(
            {
                "suite_id": "current-ragas",
                "items": [
                    {
                        "case_id": "retrieval.case.ragas",
                        "run_id": "run-current-1",
                        "report": {
                            "case_id": "retrieval.case.ragas",
                            "status": "completed",
                            "finish_reason": "retrieval_completed",
                            "failure_layer": None,
                            "hard_failures": [],
                            "assertion_summary": {"pass": 4, "fail": 0, "warn": 0, "skip": 0},
                            "ragas": {
                                "status": "completed",
                                "metric_summary": {
                                    "context_precision": 0.83,
                                    "faithfulness": 0.9,
                                },
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    baseline_summary = summarize_suite(baseline_dir)
    current_summary = summarize_suite(current_dir)
    comparison = compare_suite_outputs(current_dir, baseline_dir)

    assert baseline_summary["ragas_metric_averages"]["context_precision"] == 0.61
    assert current_summary["ragas_metric_averages"]["faithfulness"] == 0.9
    assert comparison["changed_cases"][0]["deltas"]["ragas_metric_deltas"] == {
        "context_precision": 0.22,
        "faithfulness": 0.13,
    }
    assert comparison["drift_summary"]["changed_ragas_case_ids"] == [
        "retrieval.case.ragas"
    ]


def test_summarize_suite_supports_replay_directories(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    (replay_dir / "sampled.json").write_text(
        json.dumps(
            {
                "source": {"kind": "sampled_retrieval_trace", "sample_id": "sample-1"},
                "case": {
                    "case_id": "retrieval.sampled.sample-1",
                    "scope": "retrieval",
                },
                "run": {
                    "run_id": "run-sampled-1",
                    "status": "completed",
                    "scope": "retrieval",
                },
                "report": {
                    "case_id": "retrieval.sampled.sample-1",
                    "status": "completed",
                    "finish_reason": "sampled_trace_loaded",
                    "failure_layer": None,
                    "hard_failures": [],
                    "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
                    "ragas": {
                        "status": "completed",
                        "metric_summary": {"response_relevancy": 0.63},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_suite(tmp_path)

    assert summary["run_count"] == 1
    assert summary["case_count"] == 1
    assert summary["finish_reason_counts"] == {"sampled_trace_loaded": 1}
    assert summary["ragas_metric_averages"]["response_relevancy"] == 0.63
