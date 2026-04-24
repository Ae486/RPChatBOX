from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.case_loader import load_case
from rp.eval.ragas_adapter import parse_ragas_metrics, result_to_records
from rp.eval.ragas_reporting import build_ragas_report, summarize_ragas_records
from rp.eval.ragas_samples import (
    build_ragas_dataset_payload,
    build_ragas_sample_from_eval_result,
    build_ragas_sample_from_replay_payload,
)
from rp.eval.runner import EvalRunner
from rp.eval.replay import SampledRetrievalTrace, build_sampled_retrieval_replay_payload


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / Path(*parts)
    )


@pytest.mark.asyncio
async def test_build_ragas_sample_from_eval_result_uses_retrieval_artifacts(retrieval_session):
    case = load_case(_case_path("retrieval", "search", "query_trace_and_provenance.v1.json"))
    result = await EvalRunner(retrieval_session).run_case(case)

    sample = build_ragas_sample_from_eval_result(result)

    assert sample.case_id == case.case_id
    assert sample.query == "archive sunrise ledger"
    assert len(sample.retrieved_contexts) >= 1
    assert sample.metadata["retrieval_route"]
    assert sample.metadata["returned_count"] >= 1
    assert sample.reference

    dataset_payload = build_ragas_dataset_payload([sample])
    assert dataset_payload[0]["user_input"] == "archive sunrise ledger"
    assert dataset_payload[0]["retrieved_contexts"]


def test_ragas_metric_parsing_and_record_summary_normalize_aliases():
    metrics = parse_ragas_metrics(["context_precision", "answer_relevancy", "faithfulness"])

    assert metrics == ("context_precision", "response_relevancy", "faithfulness")

    records = result_to_records(
        [
            {
                "context_precision": 0.75,
                "response_relevancy": 0.9,
                "faithfulness": 1.0,
            }
        ]
    )
    assert summarize_ragas_records(records=records, metric_names=list(metrics)) == {
        "context_precision": 0.75,
        "response_relevancy": 0.9,
        "faithfulness": 1.0,
    }


def test_build_ragas_report_exposes_metric_summary_and_sample_overview():
    report = build_ragas_report(
        enabled=True,
        available=True,
        status="completed",
        metric_names=("context_precision", "faithfulness"),
        samples=[],
        records=[
            {
                "context_precision": 0.66,
                "faithfulness": 0.91,
            }
        ],
        error=None,
    )

    assert report["status"] == "completed"
    assert report["metric_summary"]["context_precision"] == 0.66
    assert report["metric_summary"]["faithfulness"] == 0.91
    assert report["record_count"] == 1


def test_build_ragas_sample_from_sampled_replay_payload():
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

    sample = build_ragas_sample_from_replay_payload(replay_payload)

    assert sample.sample_id == "sample-1"
    assert sample.case_id == "retrieval.sampled.sample-1"
    assert sample.query == "archive sunrise ledger"
    assert sample.retrieved_contexts[0].startswith("Context:")
