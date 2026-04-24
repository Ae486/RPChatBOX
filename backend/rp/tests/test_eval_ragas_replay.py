from __future__ import annotations

from rp.eval.ragas_replay import attach_ragas_report_to_replay, run_ragas_on_replay_payload
from rp.eval.replay import SampledRetrievalTrace, build_sampled_retrieval_replay_payload


def test_run_ragas_on_sampled_replay_payload(retrieval_session, monkeypatch):
    replay_payload = build_sampled_retrieval_replay_payload(
        SampledRetrievalTrace(
            sample_id="sample-1",
            query="archive sunrise ledger",
            retrieved_contexts=["Context: archive ledger sealed before sunrise."],
            response="The archive ledger is sealed before sunrise.",
            reference="The archive ledger is sealed before sunrise.",
            metadata={"story_id": "story-sampled"},
        )
    )
    monkeypatch.setattr("rp.eval.ragas_replay.ragas_available", lambda: True)
    monkeypatch.setattr(
        "rp.eval.ragas_replay.resolve_metric_objects",
        lambda metrics, **kwargs: ["metric"],
    )
    monkeypatch.setattr(
        "rp.eval.ragas_replay.resolve_ragas_runtime_bindings",
        lambda **kwargs: type(
            "_Runtime",
            (),
            {
                "llm": object(),
                "embeddings": None,
                "metadata": {"story_id": "story-sampled"},
            },
        )(),
    )
    monkeypatch.setattr(
        "rp.eval.ragas_replay.run_ragas_evaluation",
        lambda **kwargs: [{"response_relevancy": 0.63}],
    )

    report = run_ragas_on_replay_payload(
        session=retrieval_session,
        replay_payload=replay_payload,
        env_overrides={"enable_ragas": True, "ragas_metrics": ["response_relevancy"]},
    )

    assert report["status"] == "completed"
    assert report["metric_summary"]["response_relevancy"] == 0.63


def test_attach_ragas_report_to_replay_updates_report_and_sampled_trace():
    replay_payload = build_sampled_retrieval_replay_payload(
        SampledRetrievalTrace(
            sample_id="sample-1",
            query="archive sunrise ledger",
            retrieved_contexts=["Context: archive ledger sealed before sunrise."],
        )
    )
    report = {
        "status": "completed",
        "metric_summary": {"context_precision": 0.81},
    }

    updated = attach_ragas_report_to_replay(
        replay_payload=replay_payload,
        report=report,
    )

    assert updated["report"]["ragas"]["status"] == "completed"
    assert updated["sampled_trace"]["ragas_report"]["metric_summary"]["context_precision"] == 0.81
