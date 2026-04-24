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
    assert "setup.attribution.primary_suspects" in score_names
    assert "setup.attribution.optimization_candidates" in score_names
    score_map = {item["name"]: item["value"] for item in observation.scores}
    assert score_map["setup.capability.clarification_gap_detection"] == "pass"
    assert score_map["setup.attribution.tool_contract_execution"] == "warn"
    assert score_map["setup.attribution.tool_contract_execution.numeric"] == 0.5
    assert score_map["setup.attribution.primary_suspects"] == "tool_contract_execution"
    assert (
        score_map["setup.attribution.optimization_candidates"]
        == "tighten_tool_schema_and_error_messages"
    )
    assert score_map["setup.metric.total_tokens"] == 30
    task_completion_comment = next(
        item["comment"]
        for item in observation.scores
        if item["name"] == "setup.capability.task_completion"
    )
    assert "finish_reason=awaiting_user_input" in task_completion_comment


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
