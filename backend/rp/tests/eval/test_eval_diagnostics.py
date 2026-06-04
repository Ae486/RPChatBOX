from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.case_loader import load_case
from rp.eval.diagnostics import build_setup_diagnostic_projection
from rp.eval.graders.deterministic import evaluate_diagnostic_expectation_scores
from rp.eval.models import (
    EvalArtifact,
    EvalCase,
    EvalFailure,
    EvalRun,
    EvalRunResult,
    EvalTrace,
)
from rp.eval.reporting import (
    attach_diagnostic_expectation_results,
    build_report,
    render_text_summary,
)
from rp.eval.runner import EvalRunner
from rp.tests.eval.test_eval_setup_cognitive_cases import (
    _ProviderFailureSetupLLMService,
)


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "eval"
        / "cases"
        / "setup"
        / Path(*parts)
    )


def _eval_case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "eval"
        / "cases"
        / Path(*parts)
    )


@pytest.mark.asyncio
async def test_setup_eval_infra_provider_failure_case_surfaces_diagnostic_contract(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "rp.services.setup_agent.agent_execution_service.get_litellm_service",
        lambda: _ProviderFailureSetupLLMService(),
    )

    case = load_case(
        _case_path("infra", "provider_request_failed_during_turn.v1.json")
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    assert result.run.status == "failed"
    assert result.run.failure is not None
    assert result.run.failure.layer == "infra"
    assert result.report["failure_layer"] == "infra"
    assert result.report["reason_codes"] == [
        "infra.provider_request_failed",
        "readiness.blocked_by_open_setup_prerequisites",
    ]
    assert result.report["primary_suspects"] == ["infra_model_provider"]
    assert (
        result.report["recommended_next_action"]
        == "fix_provider_model_config_and_runtime_connectivity"
    )
    assert {
        item["score_name"]: item["status"]
        for item in result.report["diagnostic_expectation_results"]
    } == {
        "diagnostic.reason_code_presence": "pass",
        "diagnostic.attribution_primary_suspect_alignment": "pass",
        "diagnostic.outcome_chain_alignment": "pass",
        "diagnostic.recommended_next_action_alignment": "pass",
    }


def test_setup_diagnostic_projection_reads_top_level_tool_error_fields():
    diagnostics = build_setup_diagnostic_projection(
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Need to repair the truth write before continuing.",
            "warnings": [],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.truth.write",
                }
            ],
            "tool_results": [
                {
                    "success": False,
                    "error_code": "setup_commit_blocked_truth_write_not_ready_for_review",
                },
                {
                    "success": False,
                    "code": "setup_truth_write_target_ref_mismatch",
                },
            ],
            "structured_payload": {},
        }
    )

    assert set(diagnostics["reason_codes"]) == {
        "controller.commit_proposal_blocked",
        "tool_contract.truth_write_target_ref_mismatch",
    }


def test_build_setup_diagnostic_projection_output_snapshot():
    runtime_result = {
        "finish_reason": "awaiting_user_input",
        "assistant_text": (
            "I found an unresolved setup concern and need your confirmation before commit."
        ),
        "warnings": [
            "commit_proposal_blocked",
            "tool_schema_validation failed for setup.stage_entry.write",
        ],
        "tool_invocations": [
            {"tool_name": "rp_setup__setup.stage_entry.write"},
            {"tool_name": "rp_setup__setup.proposal.commit"},
            {"tool_name": "rp_setup__setup.memory.open"},
        ],
        "tool_results": [
            {
                "success": True,
                "tool_name": "rp_setup__setup.memory.open",
            },
            {
                "success": False,
                "tool_name": "rp_setup__setup.proposal.commit",
                "error_code": "setup_commit_blocked_truth_write_not_ready_for_review",
                "structured_payload": {
                    "content_payload": {
                        "error": {"code": "schema_validation_failed"}
                    }
                },
            },
            {
                "success": False,
                "tool_name": "rp_setup__setup.stage_entry.write",
                "code": "setup_truth_write_target_ref_mismatch",
            },
        ],
        "structured_payload": {
            "round_no": 3,
            "tool_scope": ["setup.stage_entry.write", "setup.proposal.commit"],
            "request_metrics": {
                "system_prompt_chars": 1200,
                "user_prompt_chars": 240,
                "conversation_message_count": 6,
                "tool_scope_count": 2,
            },
            "request_context": {
                "blocking_open_question_count": 2,
            },
            "latest_response": {
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 250,
                    "total_tokens": 1250,
                }
            },
            "completion_guard": {"reason": "truth_write_not_ready_for_review"},
            "last_failure": {"failure_category": "ask_user"},
            "cognitive_state_summary": {
                "invalidated": True,
                "remaining_open_issues": [
                    "missing protagonist goal",
                    "unclear tone",
                ],
                "invalidation_reasons": ["user_edit_delta"],
            },
            "pending_obligation": {
                "obligation_type": "reassess_commit_readiness"
            },
        },
        "activation_check": {
            "ready": False,
            "blocking_issues": [
                "Retrieval ingestion not completed for seed material"
            ],
        },
    }

    diagnostics = build_setup_diagnostic_projection(
        runtime_result=runtime_result,
        failure_layer="assertion",
        error_code="E_DIAGNOSTIC_ASSERTION",
        assertion_fail_total=2,
        hard_failures=["missing_required_question", "premature_commit_attempt"],
        subjective_hook_results=[
            {
                "rubric_ref": "setup/clarification-quality/v1",
                "status": "fail",
                "score": 0.25,
                "summary": "The ask is too vague for the blocked setup state.",
            }
        ],
    )

    assert diagnostics == {
        "capabilities": {
            "task_completion": {
                "status": "fail",
                "summary": (
                    "Setup run completed with assertion failures, so capability "
                    "outcome is not trustworthy."
                ),
                "evidence": [
                    "finish_reason=awaiting_user_input",
                    "failure_layer=assertion",
                    "assertion_fail_total=2",
                ],
            },
            "clarification_gap_detection": {
                "status": "warn",
                "summary": (
                    "Agent asked the user, but the judged clarification quality "
                    "is not yet strong."
                ),
                "evidence": [
                    "finish_reason=awaiting_user_input",
                    "assistant_text_chars=77",
                    "clarification_hook_status=fail",
                    "clarification_hook_score=0.25",
                ],
            },
            "repair_recovery": {
                "status": "pass",
                "summary": (
                    "Recovery route selected as block_commit; repair semantics "
                    "are observable."
                ),
                "evidence": [
                    "repair_route=block_commit",
                    "completion_guard_reason=truth_write_not_ready_for_review",
                    "last_failure_category=ask_user",
                    "tool_failure_count=2",
                ],
            },
            "commit_readiness_judgement": {
                "status": "pass",
                "summary": (
                    "Commit readiness guard blocked a premature commit proposal."
                ),
                "evidence": [
                    "commit_proposal_blocked=True",
                    "commit_tool_invoked=True",
                    "blocking_open_question_count=2",
                    "remaining_open_issue_count=2",
                ],
            },
            "state_adaptation": {
                "status": "fail",
                "summary": (
                    "Cognitive state was invalidated and the run ended with "
                    "finish_reason=awaiting_user_input."
                ),
                "evidence": [
                    "cognitive_state_invalidated=True",
                    "finish_reason=awaiting_user_input",
                    "tool_invocation_count=3",
                ],
            },
            "operational_efficiency": {
                "status": "warn",
                "summary": (
                    "Observed round_no=3, total_tokens=1250, "
                    "tool_invocation_count=3."
                ),
                "evidence": [
                    "round_no=3",
                    "total_tokens=1250",
                    "tool_invocation_count=3",
                ],
            },
        },
        "reason_codes": [
            "cognition.invalidated_by_user_edit",
            "controller.commit_proposal_blocked",
            "prompt.missing_step_targeting",
            "readiness.blocked_by_open_setup_prerequisites",
            "retrieval_readiness.ingestion_not_completed",
            "tool_contract.truth_write_target_ref_mismatch",
            "tool_execution.schema_validation_failed",
        ],
        "outcome_chain": {
            "transcript_status": "warn",
            "cognition_status": "fail",
            "truth_status": "pass",
            "readiness_status": "warn",
            "activation_handoff_status": "fail",
            "runtime_bootstrap_readiness_status": "warn",
        },
        "recommended_next_action": (
            "refresh_runtime_private_cognition_after_user_edit_before_next_commit_attempt"
        ),
        "attribution": {
            "primary_suspects": ["instruction_prompt_skill"],
            "secondary_suspects": [
                "tool_contract_execution",
                "structured_output_contract",
            ],
            "optimization_candidates": [
                "revise_system_prompt_step_instructions_and_skill_contract"
            ],
            "evidence_refs": [
                "artifact:runtime_result",
                "artifact:tool_sequence",
                "artifact:cognitive_state_summary",
                "artifact:activation_check",
                "artifact:readiness_snapshot",
            ],
            "recommended_next_action": (
                "refresh_runtime_private_cognition_after_user_edit_before_next_commit_attempt"
            ),
            "dimensions": {
                "infra_model_provider": {
                    "status": "pass",
                    "summary": (
                        "No infra/model-provider failure detected in this run."
                    ),
                    "evidence": [
                        "failure_layer=assertion",
                        "error_code=E_DIAGNOSTIC_ASSERTION",
                    ],
                },
                "tool_contract_execution": {
                    "status": "warn",
                    "summary": (
                        "Observed 2 failed tool results; tool contract quality is "
                        "suspect."
                    ),
                    "evidence": [
                        "tool_invocation_count=3",
                        "tool_success_count=1",
                        "tool_failure_count=2",
                        (
                            "tool_failure_codes="
                            "['setup_commit_blocked_truth_write_not_ready_for_review', '']"
                        ),
                        "schema_retry_count=1",
                    ],
                },
                "decision_policy": {
                    "status": "pass",
                    "summary": (
                        "Decision-facing assertions failed: "
                        "missing_required_question, premature_commit_attempt."
                    ),
                    "evidence": [
                        (
                            "hard_failures="
                            "['missing_required_question', 'premature_commit_attempt']"
                        ),
                        "completion_guard_reason=truth_write_not_ready_for_review",
                        "repair_route=block_commit",
                        "finish_reason=awaiting_user_input",
                    ],
                },
                "structured_output_contract": {
                    "status": "warn",
                    "summary": "Structured tool interaction required schema retry.",
                    "evidence": [
                        "finish_reason=awaiting_user_input",
                        "assistant_text_chars=77",
                        "schema_retry_count=1",
                    ],
                },
                "instruction_prompt_skill": {
                    "status": "fail",
                    "summary": (
                        "Subjective judge indicates the user-facing "
                        "instruction/clarification quality needs improvement."
                    ),
                    "evidence": [
                        "clarification_hook_status=fail",
                        "clarification_hook_score=0.25",
                        (
                            "hard_failures="
                            "['missing_required_question', 'premature_commit_attempt']"
                        ),
                        "system_prompt_chars=1200",
                    ],
                },
                "token_efficiency": {
                    "status": "pass",
                    "summary": (
                        "Observed prompt_tokens=1000, completion_tokens=250, "
                        "total_tokens=1250."
                    ),
                    "evidence": [
                        "prompt_tokens=1000",
                        "completion_tokens=250",
                        "total_tokens=1250",
                        "round_no=3",
                    ],
                },
                "output_quality": {
                    "status": "fail",
                    "summary": "Subjective output hook status=fail score=0.25.",
                    "evidence": [
                        "assistant_text_chars=77",
                        "clarification_hook_status=fail",
                        "clarification_hook_score=0.25",
                        "assertion_fail_total=2",
                    ],
                },
            },
            "taxonomy_dimensions": {
                "prompt_instruction": {
                    "status": "fail",
                    "summary": (
                        "Prompt / instruction alignment for step convergence "
                        "and finish discipline."
                    ),
                    "evidence": [
                        "clarification_hook_status=fail",
                        "clarification_hook_score=0.25",
                        (
                            "hard_failures="
                            "['missing_required_question', 'premature_commit_attempt']"
                        ),
                        "system_prompt_chars=1200",
                    ],
                    "reason_codes": ["prompt.missing_step_targeting"],
                },
                "model_behavior": {
                    "status": "warn",
                    "summary": (
                        "Model behavior against structured output and repair "
                        "expectations."
                    ),
                    "evidence": [
                        "finish_reason=awaiting_user_input",
                        "assistant_text_chars=77",
                        "schema_retry_count=1",
                    ],
                    "reason_codes": [],
                },
                "tool_contract": {
                    "status": "fail",
                    "summary": "Tool argument and contract correctness.",
                    "evidence": [
                        "tool_invocation_count=3",
                        "tool_success_count=1",
                        "tool_failure_count=2",
                        (
                            "tool_failure_codes="
                            "['setup_commit_blocked_truth_write_not_ready_for_review', '']"
                        ),
                        "schema_retry_count=1",
                    ],
                    "reason_codes": [
                        "tool_contract.truth_write_target_ref_mismatch"
                    ],
                },
                "tool_execution": {
                    "status": "fail",
                    "summary": (
                        "Tool execution and recoverability after invocation."
                    ),
                    "evidence": [
                        "tool_invocation_count=3",
                        "tool_success_count=1",
                        "tool_failure_count=2",
                        (
                            "tool_failure_codes="
                            "['setup_commit_blocked_truth_write_not_ready_for_review', '']"
                        ),
                        "schema_retry_count=1",
                    ],
                    "reason_codes": ["tool_execution.schema_validation_failed"],
                },
                "deterministic_controller": {
                    "status": "fail",
                    "summary": (
                        "Deterministic controller and commit/readiness policy "
                        "correctness."
                    ),
                    "evidence": [
                        (
                            "hard_failures="
                            "['missing_required_question', 'premature_commit_attempt']"
                        ),
                        "completion_guard_reason=truth_write_not_ready_for_review",
                        "repair_route=block_commit",
                        "finish_reason=awaiting_user_input",
                    ],
                    "reason_codes": ["controller.commit_proposal_blocked"],
                },
                "runtime_private_cognition": {
                    "status": "fail",
                    "summary": (
                        "Runtime-private cognition invalidation and "
                        "reconciliation correctness."
                    ),
                    "evidence": [
                        (
                            "hard_failures="
                            "['missing_required_question', 'premature_commit_attempt']"
                        ),
                        "completion_guard_reason=truth_write_not_ready_for_review",
                        "repair_route=block_commit",
                        "finish_reason=awaiting_user_input",
                    ],
                    "reason_codes": ["cognition.invalidated_by_user_edit"],
                },
                "readiness_activation_gate": {
                    "status": "fail",
                    "summary": (
                        "Readiness and activation-gate contract between setup "
                        "outcome and activation bootstrap."
                    ),
                    "evidence": [
                        "ready=False",
                        "blocking_issue_count=1",
                    ],
                    "reason_codes": [
                        "readiness.blocked_by_open_setup_prerequisites"
                    ],
                },
                "retrieval_readiness": {
                    "status": "fail",
                    "summary": (
                        "Retrieval ingestion and archival readiness required by "
                        "activation."
                    ),
                    "evidence": ["archival_ready_ref_count=0"],
                    "reason_codes": [
                        "retrieval_readiness.ingestion_not_completed"
                    ],
                },
                "infra_provider": {
                    "status": "pass",
                    "summary": (
                        "Infrastructure and provider stability for this run."
                    ),
                    "evidence": [
                        "failure_layer=assertion",
                        "error_code=E_DIAGNOSTIC_ASSERTION",
                    ],
                    "reason_codes": [],
                },
            },
        },
        "observability": {
            "supported_scope": "setup",
            "request_metrics": {
                "system_prompt_chars": 1200,
                "user_prompt_chars": 240,
                "conversation_message_count": 6,
                "tool_scope_count": 2,
                "tool_scope": [
                    "setup.stage_entry.write",
                    "setup.proposal.commit",
                ],
            },
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 250,
                "total_tokens": 1250,
            },
            "tooling": {
                "invocation_count": 3,
                "success_count": 1,
                "failure_count": 2,
                "invoked_tool_names": [
                    "rp_setup__setup.stage_entry.write",
                    "rp_setup__setup.proposal.commit",
                    "rp_setup__setup.memory.open",
                ],
            },
        },
    }


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
        artifacts=[
            EvalArtifact(
                artifact_id="run-diag-infra-1:artifact:tool_sequence",
                run_id="run-diag-infra-1",
                kind="tool_sequence",
                name="Tool sequence",
            )
        ],
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


def test_diagnostic_expectation_scores_include_stage_alignment():
    case = EvalCase.model_validate(
        {
            "case_id": "setup.diag.stage_alignment.v1",
            "title": "stage alignment",
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
                "expected_target_stage": "character_design",
                "expected_effective_stage": "character_design",
            },
        }
    )
    report = {
        "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
        "hard_failures": [],
        "diagnostics": {},
    }

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-diag-stage",
        root_span_id="run-diag-stage:root",
        report=report,
        run_metadata={"target_stage": "character_design"},
        trace_root_attributes={"setup_stage": "character_design"},
    )
    attach_diagnostic_expectation_results(report, scores)

    assert {score.name: score.status for score in scores} == {
        "diagnostic.target_stage_alignment": "pass",
        "diagnostic.effective_stage_alignment": "pass",
    }
    assert report["diagnostic_expectation_summary"] == {
        "total": 2,
        "pass": 2,
        "fail": 0,
        "warn": 0,
        "skip": 0,
    }
    assert report["diagnostic_expectation_results"] == [
        {
            "score_name": "diagnostic.target_stage_alignment",
            "status": "pass",
            "expected": "character_design",
            "actual": "character_design",
            "missing": None,
            "mismatches": None,
            "violations": None,
            "source": "run.metadata.target_stage",
            "explanation": "expected='character_design' actual='character_design'",
        },
        {
            "score_name": "diagnostic.effective_stage_alignment",
            "status": "pass",
            "expected": "character_design",
            "actual": "character_design",
            "missing": None,
            "mismatches": None,
            "violations": None,
            "source": "trace.root.attributes.setup_stage",
            "explanation": "expected='character_design' actual='character_design'",
        },
    ]


def _minimal_skill_pack_case(expected_overrides: dict) -> EvalCase:
    """Build a minimal scoped EvalCase only for diagnostic-expectation tests."""

    base_expected = {"deterministic_assertions": [], "subjective_hooks": []}
    base_expected.update(expected_overrides)
    return EvalCase.model_validate(
        {
            "case_id": "setup.diag.skill_pack_extension.v1",
            "title": "diagnostic field extension",
            "scope": "setup",
            "category": "diagnostics",
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "expected": base_expected,
        }
    )


@pytest.mark.parametrize(
    ("expected", "actual", "status"),
    [
        ("character-design.v1", "character-design.v1", "pass"),
        ("character-design.v1", "plot-blueprint.v1", "fail"),
        ("character-design.v1", None, "fail"),
    ],
)
def test_diagnostic_expectation_scores_check_skill_pack_name(expected, actual, status):
    case = _minimal_skill_pack_case({"expected_skill_pack_name": expected})

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-skill-pack-name",
        root_span_id="run-skill-pack-name:root",
        report={
            "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
            "hard_failures": [],
            "diagnostics": {},
        },
        run_metadata={},
        trace_root_attributes={"skill_pack_name": actual},
    )

    assert {score.name: score.status for score in scores} == {
        "diagnostic.skill_pack_name_alignment": status,
    }


@pytest.mark.parametrize(
    ("expected", "actual", "status"),
    [
        ("completed_text", "completed_text", "pass"),
        ("completed_text", "awaiting_user_input", "fail"),
        ("completed_text", None, "fail"),
    ],
)
def test_diagnostic_expectation_scores_check_finish_reason(expected, actual, status):
    case = _minimal_skill_pack_case({"expected_finish_reason": expected})

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-finish-reason",
        root_span_id="run-finish-reason:root",
        report={
            "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
            "hard_failures": [],
            "diagnostics": {},
            "finish_reason": actual,
        },
        run_metadata={},
        trace_root_attributes={},
    )

    assert {score.name: score.status for score in scores} == {
        "diagnostic.finish_reason_alignment": status,
    }


@pytest.mark.parametrize(
    ("expected_contains", "tool_calls", "status"),
    [
        (["setup.truth.write"], ["setup.truth.write"], "pass"),
        (["setup.truth.write"], ["setup.truth.write", "setup.discussion.update_state"], "pass"),
        (["setup.truth.write"], ["setup.discussion.update_state"], "fail"),
        (["setup.truth.write"], [], "fail"),
    ],
)
def test_diagnostic_expectation_scores_check_tool_calls_contains(
    expected_contains, tool_calls, status
):
    case = _minimal_skill_pack_case(
        {"expected_tool_calls_contains": expected_contains}
    )

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-tools-contains",
        root_span_id="run-tools-contains:root",
        report={
            "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
            "hard_failures": [],
            "diagnostics": {},
            "tool_calls": tool_calls,
        },
        run_metadata={},
        trace_root_attributes={},
    )

    assert {score.name: score.status for score in scores} == {
        "diagnostic.tool_calls_contains_alignment": status,
    }


@pytest.mark.parametrize(
    ("expected_excludes", "tool_calls", "status"),
    [
        (["setup.proposal.commit"], ["setup.truth.write"], "pass"),
        (["setup.proposal.commit"], [], "pass"),
        (["setup.proposal.commit"], ["setup.proposal.commit"], "fail"),
        (["setup.proposal.commit"], ["setup.truth.write", "setup.proposal.commit"], "fail"),
    ],
)
def test_diagnostic_expectation_scores_check_tool_calls_excludes(
    expected_excludes, tool_calls, status
):
    case = _minimal_skill_pack_case(
        {"expected_tool_calls_excludes": expected_excludes}
    )

    scores = evaluate_diagnostic_expectation_scores(
        case=case,
        run_id="run-tools-excludes",
        root_span_id="run-tools-excludes:root",
        report={
            "assertion_summary": {"pass": 0, "fail": 0, "warn": 0, "skip": 0},
            "hard_failures": [],
            "diagnostics": {},
            "tool_calls": tool_calls,
        },
        run_metadata={},
        trace_root_attributes={},
    )

    assert {score.name: score.status for score in scores} == {
        "diagnostic.tool_calls_excludes_alignment": status,
    }


def test_render_text_summary_includes_diagnostic_context():
    case = EvalCase.model_validate(
        {
            "case_id": "setup.diag.render_summary.v1",
            "title": "render summary",
            "scope": "setup",
            "category": "diagnostics",
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
        }
    )
    result = EvalRunResult(
        case=case,
        run=EvalRun(
            run_id="run-render-summary-1",
            case_id=case.case_id,
            scope=case.scope,
            status="completed",
            runtime_target="setup_v2",
            trace_id="trace-render-summary-1",
        ),
        trace=EvalTrace(trace_id="trace-render-summary-1"),
        runtime_result={},
        report={
            "status": "completed",
            "case_id": case.case_id,
            "assertion_summary": {"pass": 3, "fail": 1, "warn": 0, "skip": 0},
            "failure_layer": "deterministic",
            "finish_reason": "awaiting_user_input",
            "repair_route": "ask_user",
            "end_reason_summary": "repair_route:ask_user",
            "reason_codes": ["prompt.missing_step_targeting"],
            "primary_suspects": ["instruction_prompt_skill"],
            "recommended_next_action": "ask_for_missing_setup_inputs",
            "diagnostic_expectation_summary": {"total": 2, "pass": 1, "fail": 1, "warn": 0, "skip": 0},
        },
    )

    summary = render_text_summary(result)

    assert "failure_layer=deterministic" in summary
    assert "reason_codes=prompt.missing_step_targeting" in summary
    assert "primary_suspects=instruction_prompt_skill" in summary
    assert "next_action=ask_for_missing_setup_inputs" in summary
    assert "diagnostic_expectations=1/2 fail=1" in summary

