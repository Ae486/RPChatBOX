from __future__ import annotations

from rp.eval.langfuse_sync import (
    sync_comparison_to_langfuse,
    sync_replay_to_langfuse,
    sync_suite_summary_to_langfuse,
)


class _FakeLangfuseObservation:
    def __init__(self, *, sink: list[dict], name: str) -> None:
        self._sink = sink
        self._name = name

    def __enter__(self):
        self._sink.append({"kind": "observation_enter", "name": self._name})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "observation_exit", "name": self._name})
        return False

    def update(self, **kwargs):
        self._sink.append({"kind": "observation_update", "name": self._name, "payload": kwargs})

    def score_trace(self, **kwargs):
        self._sink.append({"kind": "score_trace", "name": self._name, "payload": kwargs})


class _FakeLangfuseContext:
    def __init__(self, *, sink: list[dict], payload: dict) -> None:
        self._sink = sink
        self._payload = payload

    def __enter__(self):
        self._sink.append({"kind": "propagate_enter", "payload": self._payload})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "propagate_exit", "payload": self._payload})
        return False


class _FakeLangfuseService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def propagate_attributes(self, **kwargs):
        return _FakeLangfuseContext(sink=self.events, payload=kwargs)

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self.events,
            name=str(kwargs.get("name") or "unknown"),
        )


def test_sync_suite_summary_to_langfuse_emits_summary_scores(monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    monkeypatch.setattr(
        "rp.eval.langfuse_sync.get_langfuse_service",
        lambda: fake_langfuse,
    )

    sync_suite_summary_to_langfuse(
        suite_payload={"suite_id": "suite-1"},
        summary={
            "suite_id": "suite-1",
            "run_count": 3,
            "case_count": 2,
            "failed_run_count": 1,
            "assertion_fail_total": 2,
            "assertion_warn_total": 1,
            "hard_failure_total": 1,
            "pending_judge_hook_total": 1,
            "executed_judge_hook_total": 2,
            "repeat_case_ids": ["retrieval.case.repeat"],
            "ragas_metric_averages": {"context_precision": 0.81},
        },
        thresholds={"passed": False, "breaches": ["assertion_fail_total>0"]},
    )

    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.suite.run_count"
        and item["payload"]["value"] == 3
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.suite.threshold_passed"
        and item["payload"]["value"] is False
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.suite.ragas.context_precision"
        and item["payload"]["value"] == 0.81
        for item in fake_langfuse.events
    )


def test_sync_comparison_to_langfuse_emits_drift_scores(monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    monkeypatch.setattr(
        "rp.eval.langfuse_sync.get_langfuse_service",
        lambda: fake_langfuse,
    )

    sync_comparison_to_langfuse(
        comparison={
            "current": {
                "suite_id": "current-suite",
                "ragas_metric_averages": {"context_precision": 0.84},
            },
            "baseline": {
                "suite_id": "baseline-suite",
                "ragas_metric_averages": {"context_precision": 0.72},
            },
            "drift_summary": {
                "changed_case_count": 1,
                "changed_finish_reason_case_ids": ["setup.case.changed"],
                "changed_failure_layer_case_ids": [],
                "changed_hard_failure_case_ids": ["setup.case.changed"],
                "changed_pending_judge_case_ids": [],
                "changed_executed_judge_case_ids": [],
                "changed_subjective_status_case_ids": [],
                "changed_subjective_score_case_ids": [],
                "changed_ragas_case_ids": ["retrieval.case.changed"],
            },
        }
    )

    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.compare.changed_case_count"
        and item["payload"]["value"] == 1
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.compare.changed_ragas_case_ids.count"
        and item["payload"]["value"] == 1
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "eval.compare.current.ragas.context_precision"
        and item["payload"]["value"] == 0.84
        for item in fake_langfuse.events
    )


def test_sync_replay_to_langfuse_emits_retrieval_and_ragas_scores(monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    monkeypatch.setattr(
        "rp.eval.langfuse_sync.get_langfuse_service",
        lambda: fake_langfuse,
    )

    sync_replay_to_langfuse(
        replay_payload={
            "case": {
                "case_id": "retrieval.search.query_trace_and_provenance.v1",
                "scope": "retrieval",
            },
            "run": {
                "run_id": "run-1",
                "scope": "retrieval",
                "metadata": {
                    "story_id": "story-1",
                    "workspace_id": "workspace-1",
                },
            },
            "runtime_result": {
                "finish_reason": "retrieval_completed",
                "query_input": {
                    "query_id": "rq-1",
                    "query_kind": "archival",
                    "story_id": "story-1",
                    "scope": "story",
                    "text_query": "ritual after dusk",
                    "top_k": 2,
                },
                "query_result": {
                    "query": "ritual after dusk",
                    "hits": [{"hit_id": "chunk-1"}],
                    "warnings": ["rerank_backend_failed:TimeoutError"],
                    "trace": {
                        "route": "retrieval.hybrid.rrf",
                        "result_kind": "chunk",
                        "retriever_routes": ["retrieval.keyword.lexical", "retrieval.semantic.python"],
                        "pipeline_stages": ["retrieve", "fusion", "rerank"],
                        "candidate_count": 5,
                        "returned_count": 1,
                        "timings": {"broker_ms": 8.5},
                    },
                },
            },
            "report": {
                "finish_reason": "retrieval_completed",
                "ragas": {
                    "status": "completed",
                    "sample_count": 1,
                    "metric_summary": {"response_relevancy": 0.63},
                },
            },
        }
    )

    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.execution_status"
        and item["payload"]["value"] == "ok"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.route"
        and item["payload"]["value"] == "retrieval.hybrid.rrf"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.metric.returned_count"
        and item["payload"]["value"] == 1
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.warning_categories"
        and item["payload"]["value"] == "rerank_backend_failed"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.ragas.status"
        and item["payload"]["value"] == "completed"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "retrieval.ragas.response_relevancy"
        and item["payload"]["value"] == 0.63
        for item in fake_langfuse.events
    )
