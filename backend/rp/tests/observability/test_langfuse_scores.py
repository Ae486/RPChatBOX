from __future__ import annotations

from rp.observability.langfuse_scores import (
    emit_activation_trace_scores,
    emit_retrieval_trace_scores,
    emit_ragas_metric_scores,
    emit_setup_trace_scores,
)


class _FakeObservation:
    def __init__(self) -> None:
        self.scores: list[dict] = []

    def score_trace(self, **kwargs):
        self.scores.append(kwargs)


def test_emit_setup_trace_scores_emits_capability_and_attribution_scores():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Which POV and style rules do you want me to lock in?",
            "warnings": ["tool_failure_requires_user_input"],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.truth.write",
                }
            ],
            "tool_results": [
                {
                    "success": False,
                    "error_code": "SETUP_TOOL_FAILED",
                }
            ],
            "structured_payload": {
                "round_no": 2,
                "repair_route": "ask_user",
                "pending_obligation": {
                    "obligation_type": "ask_user_for_missing_info",
                },
                "last_failure": {
                    "failure_category": "ask_user",
                },
                "latest_response": {
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30,
                    }
                },
            },
        },
    )

    score_names = {item["name"] for item in observation.scores}
    assert "setup.finish_reason" in score_names
    assert "setup.metric.total_tokens" in score_names
    assert "setup.capability.task_completion" in score_names
    assert "setup.capability.task_completion.numeric" in score_names
    assert "setup.capability.clarification_gap_detection" in score_names
    assert "setup.attribution.tool_contract_execution" in score_names
    assert "setup.attribution.tool_contract_execution.numeric" in score_names
    assert "setup.attribution.token_efficiency" in score_names
    assert "setup.tool_selection_correct" in score_names
    assert "setup.tool_selection_correct.numeric" in score_names
    assert "setup.tool_result_value" in score_names
    assert "setup.tool_result_value.numeric" in score_names
    assert "setup.loop.noop_or_repeated_question" in score_names
    assert "setup.loop.noop_or_repeated_question.numeric" in score_names
    assert "setup.attribution.primary_suspects" in score_names
    assert "setup.attribution.optimization_candidates" in score_names
    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.capability.clarification_gap_detection"] == "pass"
    assert score_map["setup.attribution.tool_contract_execution"] == "warn"
    assert score_map["setup.attribution.tool_contract_execution.numeric"] == 0.5
    assert score_map["setup.tool_selection_correct"] == "warn"
    assert score_map["setup.tool_selection_correct.numeric"] == 0.5
    assert score_map["setup.tool_result_value"] == "warn"
    assert score_map["setup.tool_result_value.numeric"] == 0.5
    assert score_map["setup.loop.noop_or_repeated_question"] == "pass"
    assert score_map["setup.loop.noop_or_repeated_question.numeric"] == 1.0
    assert score_map["setup.attribution.primary_suspects"] == "tool_contract_execution"
    assert (
        score_map["setup.attribution.optimization_candidates"]
        == "tighten_tool_schema_and_error_messages"
    )
    assert score_map["setup.metric.total_tokens"] == 30
    assert score_map["setup.metric.tokens_per_tool_invocation"] == 30.0
    task_completion_comment = next(
        item["comment"]
        for item in observation.scores
        if item["name"] == "setup.capability.task_completion"
    )
    assert "finish_reason=awaiting_user_input" in task_completion_comment
    tool_selection_comment = next(
        item["comment"]
        for item in observation.scores
        if item["name"] == "setup.tool_selection_correct"
    )
    assert "selected_tools=['setup.truth.write']" in tool_selection_comment


def test_emit_setup_trace_scores_marks_tool_selection_pass_for_clarification_turn():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "你更想先锁定叙事口吻，还是先补主角的禁忌规则？",
            "warnings": [],
            "tool_invocations": [],
            "tool_results": [],
            "structured_payload": {
                "round_no": 1,
                "pending_obligation": {
                    "obligation_type": "ask_user_for_missing_info",
                },
                "working_plan": {
                    "missing_information": ["writing_contract:core_fields"],
                    "question_targets": ["writing_contract:core_fields"],
                },
                "request_context": {
                    "blocking_open_question_count": 1,
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_selection_correct"] == "pass"
    assert score_map["setup.tool_selection_correct.numeric"] == 1.0
    assert score_map["setup.tool_result_value"] == "not_applicable"
    assert score_map["setup.loop.noop_or_repeated_question"] == "pass"


def test_emit_setup_trace_scores_marks_tool_selection_fail_when_patch_goal_skips_tool_use():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "completed_text",
            "assistant_text": "我已经处理好了。",
            "warnings": [],
            "tool_invocations": [],
            "tool_results": [],
            "structured_payload": {
                "round_no": 2,
                "turn_goal": {
                    "goal_type": "patch_draft",
                },
                "working_plan": {
                    "patch_targets": ["writing_contract_draft"],
                    "question_targets": [],
                },
                "request_context": {
                    "blocking_open_question_count": 0,
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_selection_correct"] == "fail"
    assert score_map["setup.tool_selection_correct.numeric"] == 0.0
    assert score_map["setup.tool_result_value"] == "fail"
    assert score_map["setup.tool_result_value.numeric"] == 0.0
    assert score_map["setup.loop.noop_or_repeated_question"] == "fail"
    assert score_map["setup.loop.noop_or_repeated_question.numeric"] == 0.0


def test_emit_setup_trace_scores_marks_tool_result_value_pass_for_successful_patch():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "我已经先把 POV 和风格约束收敛好了，下一步只需要你确认一条额外限制。",
            "warnings": [],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.patch.writing_contract",
                }
            ],
            "tool_results": [
                {
                    "success": True,
                    "tool_name": "rp_setup__setup.patch.writing_contract",
                    "structured_payload": {
                        "content_payload": {
                            "cognitive_state_summary": {
                                "current_step": "writing_contract",
                            }
                        }
                    },
                }
            ],
            "structured_payload": {
                "round_no": 2,
                "latest_response": {
                    "usage": {
                        "total_tokens": 84,
                    }
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_selection_correct"] == "pass"
    assert score_map["setup.tool_selection_correct.numeric"] == 1.0
    assert score_map["setup.tool_result_value"] == "pass"
    assert score_map["setup.tool_result_value.numeric"] == 1.0
    assert score_map["setup.loop.noop_or_repeated_question"] == "pass"
    assert score_map["setup.loop.noop_or_repeated_question.numeric"] == 1.0
    assert score_map["setup.metric.tokens_per_tool_invocation"] == 84.0


def test_emit_setup_trace_scores_marks_tool_result_value_warn_for_success_without_observable_progress():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "continue_discussion",
            "assistant_text": "我先继续推进下一步。",
            "warnings": [],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.patch.story_config",
                }
            ],
            "tool_results": [
                {
                    "success": True,
                    "tool_name": "rp_setup__setup.patch.story_config",
                }
            ],
            "structured_payload": {
                "round_no": 2,
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_selection_correct"] == "pass"
    assert score_map["setup.tool_result_value"] == "warn"
    assert score_map["setup.tool_result_value.numeric"] == 0.5
    assert score_map["setup.loop.noop_or_repeated_question"] == "pass"


def test_emit_setup_trace_scores_marks_commit_goal_discussion_tool_as_selection_fail():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "I refreshed the discussion state, but commit is still not ready.",
            "warnings": [],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.discussion.update_state",
                }
            ],
            "tool_results": [
                {
                    "success": True,
                    "tool_name": "rp_setup__setup.discussion.update_state",
                    "structured_payload": {
                        "content_payload": {
                            "discussion_state": {
                                "updated": True,
                            }
                        }
                    },
                }
            ],
            "structured_payload": {
                "round_no": 2,
                "turn_goal": {
                    "goal_type": "prepare_commit_intent",
                },
                "working_plan": {
                    "discussion_actions": ["advance_current_step"],
                    "patch_targets": ["writing_contract_draft"],
                    "question_targets": [],
                },
                "request_context": {
                    "blocking_open_question_count": 0,
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_selection_correct"] == "fail"
    assert score_map["setup.tool_selection_correct.numeric"] == 0.0
    assert score_map["setup.tool_result_value"] == "pass"
    assert score_map["setup.loop.noop_or_repeated_question"] == "pass"


def test_emit_setup_trace_scores_marks_loop_warn_for_early_failed_repair_turn():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "continue_discussion",
            "assistant_text": "这个修复还没完成，我需要继续处理。",
            "warnings": ["tool_schema_validation_retry"],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.patch.story_config",
                }
            ],
            "tool_results": [
                {
                    "success": False,
                    "tool_name": "rp_setup__setup.patch.story_config",
                    "error_code": "SCHEMA_VALIDATION_FAILED",
                }
            ],
            "structured_payload": {
                "round_no": 2,
                "pending_obligation": {
                    "obligation_type": "repair_tool_call",
                },
                "completion_guard": {
                    "reason": "repair_obligation_unresolved",
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_result_value"] == "warn"
    assert score_map["setup.tool_result_value.numeric"] == 0.5
    assert score_map["setup.loop.noop_or_repeated_question"] == "warn"
    assert score_map["setup.loop.noop_or_repeated_question.numeric"] == 0.5


def test_emit_setup_trace_scores_marks_loop_noop_fail_for_unresolved_repair_loop():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "repair_obligation_unfulfilled",
            "assistant_text": "我得再想想。",
            "warnings": ["tool_schema_validation_retry"],
            "tool_invocations": [
                {
                    "tool_name": "rp_setup__setup.patch.story_config",
                }
            ],
            "tool_results": [
                {
                    "success": False,
                    "tool_name": "rp_setup__setup.patch.story_config",
                    "error_code": "SCHEMA_VALIDATION_FAILED",
                }
            ],
            "structured_payload": {
                "round_no": 4,
                "pending_obligation": {
                    "obligation_type": "repair_tool_call",
                },
                "completion_guard": {
                    "reason": "repair_obligation_unresolved",
                },
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.tool_result_value"] == "fail"
    assert score_map["setup.tool_result_value.numeric"] == 0.0
    assert score_map["setup.loop.noop_or_repeated_question"] == "fail"
    assert score_map["setup.loop.noop_or_repeated_question.numeric"] == 0.0


def test_emit_setup_trace_scores_prefers_report_diagnostics_when_provided():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Need one more setup detail.",
            "warnings": [],
            "structured_payload": {},
        },
        report={
            "failure_layer": "deterministic",
            "reason_codes": ["prompt.missing_step_targeting"],
            "primary_suspects": ["instruction_prompt_skill"],
            "secondary_suspects": ["decision_policy"],
            "recommended_next_action": "ask_for_missing_setup_inputs",
            "evidence_refs": ["artifact:tool_sequence"],
            "outcome_chain": {
                "transcript_status": "warn",
                "readiness_status": "fail",
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.failure_layer"] == "deterministic"
    assert score_map["setup.reason_codes"] == "prompt.missing_step_targeting"
    assert score_map["setup.attribution.primary_suspects"] == "instruction_prompt_skill"
    assert score_map["setup.attribution.secondary_suspects"] == "decision_policy"
    assert score_map["setup.recommended_next_action"] == "ask_for_missing_setup_inputs"
    assert score_map["setup.evidence_refs"] == "artifact:tool_sequence"
    assert score_map["setup.outcome_chain.transcript_status"] == "warn"
    assert score_map["setup.outcome_chain.readiness_status"] == "fail"


def test_emit_setup_trace_scores_marks_commit_blocked_from_block_commit_route():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "The current step is not ready for commit yet.",
            "warnings": [],
            "tool_invocations": [],
            "tool_results": [],
            "structured_payload": {
                "repair_route": "block_commit",
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.repair_route"] == "block_commit"
    assert score_map["setup.commit_blocked"] is True


def test_emit_setup_trace_scores_derives_commit_blocked_from_warning_signal():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Commit is still blocked by review readiness.",
            "warnings": ["commit_proposal_blocked"],
            "tool_invocations": [],
            "tool_results": [],
            "structured_payload": {},
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.repair_route"] == "block_commit"
    assert score_map["setup.commit_blocked"] is True


def test_emit_setup_trace_scores_derives_commit_blocked_from_pending_obligation():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Commit needs one more readiness pass.",
            "warnings": [],
            "tool_invocations": [],
            "tool_results": [],
            "structured_payload": {
                "pending_obligation": {
                    "obligation_type": "reassess_commit_readiness",
                }
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.repair_route"] == "block_commit"
    assert score_map["setup.commit_blocked"] is True


def test_emit_setup_trace_scores_reads_top_level_tool_error_codes_for_reason_codes():
    observation = _FakeObservation()

    emit_setup_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "awaiting_user_input",
            "assistant_text": "Need to resolve the write target before moving on.",
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
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert set(score_map["setup.reason_codes"].split(",")) == {
        "controller.commit_proposal_blocked",
        "tool_contract.truth_write_target_ref_mismatch",
    }


def test_emit_activation_trace_scores_emits_capability_and_attribution_scores():
    observation = _FakeObservation()

    emit_activation_trace_scores(
        observation,
        runtime_result={
            "finish_reason": "activation_completed",
            "activation_check": {
                "workspace_id": "workspace-1",
                "ready": True,
                "blocking_issues": [],
                "warnings": [],
                "handoff": {
                    "runtime_story_config": {"model_profile_ref": "model.default"},
                    "writer_contract": {"pov_rules": ["third_person_limited"]},
                    "foundation_commit_refs": ["commit-foundation-1"],
                    "blueprint_commit_ref": "commit-blueprint-1",
                    "archival_ready_refs": ["asset:1"],
                },
            },
            "activation_result": {
                "session_id": "session-1",
                "story_id": "story-1",
                "source_workspace_id": "workspace-1",
                "current_chapter_index": 1,
                "current_phase": "outline_drafting",
                "initial_outline_required": True,
            },
        },
    )

    score_names = {item["name"] for item in observation.scores}
    assert "activation.finish_reason" in score_names
    assert "activation.capability.readiness_gate" in score_names
    assert "activation.capability.session_bootstrap.numeric" in score_names
    assert "activation.attribution.bootstrap_execution" in score_names
    assert "activation.attribution.primary_suspects" in score_names
    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["activation.capability.readiness_gate"] == "pass"
    assert score_map["activation.capability.session_bootstrap.numeric"] == 1.0
    assert score_map["activation.attribution.primary_suspects"] == "none"


def test_emit_ragas_metric_scores_emits_status_and_numeric_metrics():
    observation = _FakeObservation()

    emit_ragas_metric_scores(
        observation,
        report={
            "status": "completed",
            "sample_count": 1,
            "metric_summary": {
                "context_precision": 0.88,
                "response_relevancy": 0.63,
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["retrieval.ragas.status"] == "completed"
    assert score_map["retrieval.ragas.sample_count"] == 1
    assert score_map["retrieval.ragas.context_precision"] == 0.88
    assert score_map["retrieval.ragas.response_relevancy"] == 0.63


def test_emit_retrieval_trace_scores_emits_operational_scores():
    observation = _FakeObservation()

    emit_retrieval_trace_scores(
        observation,
        query_payload={
            "query_id": "rq-1",
            "query_kind": "archival",
            "story_id": "story-1",
            "scope": "story",
            "top_k": 3,
        },
        result_payload={
            "hits": [{"hit_id": "chunk-1"}],
            "warnings": ["rerank_backend_failed:TimeoutError"],
            "trace": {
                "route": "retrieval.hybrid.rrf",
                "result_kind": "chunk",
                "reranker_name": "cross_encoder_hosted",
                "candidate_count": 6,
                "returned_count": 1,
                "retriever_routes": [
                    "retrieval.keyword.lexical",
                    "retrieval.semantic.python",
                ],
                "pipeline_stages": ["retrieve", "fusion", "rerank", "chunk_result_builder"],
                "timings": {"keyword_ms": 1.0, "semantic_ms": 2.0, "broker_ms": 9.5},
            },
        },
        observability_payload={
            "route": "retrieval.hybrid.rrf",
            "result_kind": "chunk",
            "reranker_name": "cross_encoder_hosted",
            "candidate_count": 6,
            "returned_count": 1,
            "retriever_routes": [
                "retrieval.keyword.lexical",
                "retrieval.semantic.python",
            ],
            "pipeline_stages": ["retrieve", "fusion", "rerank", "chunk_result_builder"],
            "warnings": ["rerank_backend_failed:TimeoutError"],
            "warning_buckets": [{"category": "rerank_backend_failed", "count": 1}],
            "timings": {"broker_ms": 9.5},
            "maintenance": {
                "failed_job_count": 2,
                "backfill_candidate_asset_ids": ["asset-a"],
            },
        },
    )

    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["retrieval.query_kind"] == "archival"
    assert score_map["retrieval.execution_status"] == "ok"
    assert score_map["retrieval.route"] == "retrieval.hybrid.rrf"
    assert score_map["retrieval.result_kind"] == "chunk"
    assert score_map["retrieval.hit_found"] is True
    assert score_map["retrieval.pipeline_health"] == "warn"
    assert score_map["retrieval.pipeline_health.numeric"] == 0.5
    assert score_map["retrieval.warning_categories"] == "rerank_backend_failed"
    assert score_map["retrieval.metric.top_k"] == 3
    assert score_map["retrieval.metric.candidate_count"] == 6
    assert score_map["retrieval.metric.returned_count"] == 1
    assert score_map["retrieval.metric.warning_count"] == 1
    assert score_map["retrieval.metric.retriever_route_count"] == 2
    assert score_map["retrieval.metric.failed_job_count"] == 2
    assert score_map["retrieval.metric.backfill_candidate_count"] == 1
    assert score_map["retrieval.metric.latency_ms"] == 9.5
