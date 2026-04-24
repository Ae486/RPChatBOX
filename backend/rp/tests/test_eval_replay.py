from __future__ import annotations

from rp.eval.models import EvalCase, EvalRun, EvalRunResult, EvalTrace
from rp.eval.replay import (
    SampledRetrievalTrace,
    build_sampled_retrieval_replay_payload,
    load_replay,
    load_replay_case,
    save_replay,
    save_sampled_retrieval_replay,
)


def test_eval_replay_roundtrip(tmp_path):
    case = EvalCase.model_validate(
        {
            "case_id": "setup.replay.v1",
            "title": "replay",
            "scope": "setup",
            "category": "clarification",
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
            run_id="run-1",
            case_id=case.case_id,
            scope=case.scope,
            status="completed",
            runtime_target="setup_v2",
            trace_id="trace-1",
        ),
        trace=EvalTrace(trace_id="trace-1"),
        runtime_result={"finish_reason": "completed_text"},
        report={"status": "completed"},
    )

    replay_path = save_replay(tmp_path / "replays" / "case.json", result)
    payload = load_replay(replay_path)
    restored_case = load_replay_case(replay_path)

    assert payload["run"]["run_id"] == "run-1"
    assert restored_case.case_id == "setup.replay.v1"


def test_sampled_retrieval_replay_roundtrip(tmp_path):
    replay_path = save_sampled_retrieval_replay(
        tmp_path / "replays" / "sampled.json",
        SampledRetrievalTrace(
            sample_id="sample-1",
            query="archive sunrise ledger",
            retrieved_contexts=["Context: archive ledger sealed before sunrise."],
            response="The archive ledger is sealed before sunrise.",
            reference="The archive ledger is sealed before sunrise.",
            metadata={"story_id": "story-sampled"},
        ),
    )

    payload = load_replay(replay_path)
    restored_case = load_replay_case(replay_path)

    assert payload["source"]["kind"] == "sampled_retrieval_trace"
    assert payload["sampled_trace"]["query"] == "archive sunrise ledger"
    assert payload["report"]["finish_reason"] == "sampled_trace_loaded"
    assert restored_case.scope == "retrieval"
    assert restored_case.category == "sampled_trace"

