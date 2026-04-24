from __future__ import annotations

from pathlib import Path

import pytest

from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.eval.case_loader import load_case
from rp.eval.replay import load_replay
from rp.eval.runner import EvalRunner
from rp.tests.test_eval_setup_cognitive_cases import _TruthWriteAskUserLLMService
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service
import services.model_registry as model_registry_module


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / Path(*parts)
    )


def _seed_judge_model_registry() -> None:
    get_provider_registry_service.cache_clear()
    model_registry_module._model_registry_service = None
    provider_service = get_provider_registry_service()
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id="provider-eval",
            name="Eval Provider",
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
            is_enabled=True,
        )
    )
    model_service = get_model_registry_service()
    model_service.upsert_entry(
        ModelRegistryEntry(
            id="model-eval",
            provider_id="provider-eval",
            model_name="gpt-4o-mini",
            display_name="Eval Model",
            capabilities=["text", "tool"],
            is_enabled=True,
        )
    )


class _FakeJudgeLLMService:
    def __init__(self, *, response_payload: dict) -> None:
        self._response_payload = response_payload

    async def chat_completion(self, request):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": __import__("json").dumps(self._response_payload),
                    }
                }
            ]
        }

    def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")


@pytest.mark.asyncio
async def test_eval_runner_materializes_setup_subjective_hooks(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _TruthWriteAskUserLLMService(),
    )

    case = load_case(
        _case_path("setup", "repair", "writing_contract_ask_user_after_semantic_fail.v1.json")
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "skip"
    assert score.value == "pending"
    assert score.metadata["hook_id"] == "clarification_quality"
    assert score.metadata["rubric_ref"] == "setup/clarification-quality/v1"
    assert score.metadata["resolved_source"] == "runtime_result"
    assert "Which POV and style rules" in (score.metadata["target_preview"] or "")
    assert result.report["pending_judge_hook_ids"] == ["clarification_quality"]
    assert result.report["subjective_hook_summary"]["pending"] == 1
    assert result.report["subjective_hook_summary"]["artifact_count"] == 1
    judge_artifact = next(
        artifact for artifact in result.artifacts if artifact.kind == "subjective_hook_record"
    )
    assert judge_artifact.payload["hook_id"] == "clarification_quality"
    assert judge_artifact.payload["request"] is None
    assert judge_artifact.payload["judge"]["skip_reason"] is None


@pytest.mark.asyncio
async def test_eval_runner_materializes_retrieval_subjective_hooks(retrieval_session):
    case = load_case(
        _case_path("retrieval", "search", "query_trace_and_provenance.v1.json")
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "skip"
    assert score.metadata["hook_id"] == "retrieval_query_quality"
    assert score.metadata["rubric_ref"] == "retrieval/query-quality/v1"
    assert score.metadata["resolved_source"] == "retrieval_result"
    assert score.metadata["target_preview"] == "archive sunrise ledger"
    assert result.report["pending_judge_hook_ids"] == ["retrieval_query_quality"]
    assert result.report["subjective_hook_summary"]["judge_family_counts"] == {"llm_judge": 1}


@pytest.mark.asyncio
async def test_eval_runner_materializes_activation_subjective_hooks(retrieval_session):
    case = load_case(
        _case_path("activation", "bootstrap", "ready_workspace_activation.v1.json")
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "skip"
    assert score.metadata["hook_id"] == "activation_handoff_quality"
    assert score.metadata["rubric_ref"] == "activation/handoff-quality/v1"
    assert score.metadata["resolved_source"] == "activation_result"
    assert score.metadata["target_available"] is True
    assert "runtime_story_config" in (score.metadata["target_preview"] or "")
    assert result.report["pending_judge_hook_ids"] == ["activation_handoff_quality"]


@pytest.mark.asyncio
async def test_eval_runner_executes_setup_subjective_judge(
    retrieval_session,
    monkeypatch,
):
    _seed_judge_model_registry()
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _TruthWriteAskUserLLMService(),
    )
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _FakeJudgeLLMService(
            response_payload={
                "status": "pass",
                "label": "good",
                "score": 0.91,
                "explanation": "The question directly asks for the missing POV and style preferences.",
            }
        ),
    )

    case = load_case(
        _case_path("setup", "repair", "writing_contract_ask_user_after_semantic_fail.v1.json")
    )
    case.input.env_overrides.update(
        {
            "enable_subjective_judges": True,
            "judge_model_id": "model-eval",
            "judge_provider_id": "provider-eval",
        }
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "pass"
    assert score.value == 0.91
    assert score.label == "good"
    assert score.metadata["judge_model_id"] == "model-eval"
    assert score.metadata["judge_prompt_version"] == "llm-judge/v2"
    assert score.metadata["judge_response_schema_version"] == "judge-response/v2"
    assert score.metadata["judge_status_source"] == "model_status"
    assert score.metadata["judge_score_band"] == "pass"
    assert result.report["pending_judge_hook_ids"] == []
    assert result.report["subjective_hook_summary"]["executed"] == 1
    assert result.report["subjective_hook_summary"]["status_counts"] == {"pass": 1}
    assert result.report["subjective_hook_summary"]["average_numeric_score"] == 0.91
    assert result.report["subjective_hook_results"][0]["hook_id"] == "clarification_quality"
    assert result.report["subjective_hook_results"][0]["judge_prompt_version"] == "llm-judge/v2"
    assert result.report["subjective_hook_summary"]["artifact_count"] == 1
    judge_artifact = next(
        artifact for artifact in result.artifacts if artifact.kind == "subjective_hook_record"
    )
    assert result.report["subjective_hook_results"][0]["artifact_id"] == judge_artifact.artifact_id
    assert judge_artifact.payload["request"]["rubric"]["ref"] == "setup/clarification-quality/v1"
    assert judge_artifact.payload["response"]["status"] == "pass"
    assert judge_artifact.payload["judge"]["prompt_version"] == "llm-judge/v2"


@pytest.mark.asyncio
async def test_eval_runner_executes_retrieval_subjective_judge(
    retrieval_session,
    monkeypatch,
):
    _seed_judge_model_registry()
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _FakeJudgeLLMService(
            response_payload={
                "status": "warn",
                "label": "acceptable",
                "score": 0.62,
                "explanation": "The query is relevant but could include one more discriminating concept.",
            }
        ),
    )

    case = load_case(
        _case_path("retrieval", "search", "query_trace_and_provenance.v1.json")
    )
    case.input.env_overrides.update(
        {
            "enable_subjective_judges": True,
            "judge_model_id": "model-eval",
            "judge_provider_id": "provider-eval",
        }
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "warn"
    assert score.value == 0.62
    assert score.label == "acceptable"
    assert result.report["pending_judge_hook_ids"] == []
    assert result.report["subjective_hook_summary"]["executed"] == 1


@pytest.mark.asyncio
async def test_eval_runner_executes_activation_subjective_judge(
    retrieval_session,
    monkeypatch,
):
    _seed_judge_model_registry()
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _FakeJudgeLLMService(
            response_payload={
                "status": "pass",
                "label": "usable",
                "score": 0.79,
                "explanation": "The handoff includes concrete config, writer contract, and continuity refs for activation.",
            }
        ),
    )

    case = load_case(
        _case_path("activation", "bootstrap", "ready_workspace_activation.v1.json")
    )
    case.input.env_overrides.update(
        {
            "enable_subjective_judges": True,
            "judge_model_id": "model-eval",
            "judge_provider_id": "provider-eval",
        }
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "pass"
    assert score.value == 0.79
    assert score.label == "usable"
    assert score.metadata["hook_id"] == "activation_handoff_quality"
    assert score.metadata["judge_response_schema_version"] == "judge-response/v2"
    assert result.report["pending_judge_hook_ids"] == []
    assert result.report["subjective_hook_summary"]["executed"] == 1


@pytest.mark.asyncio
async def test_eval_runner_can_fallback_subjective_status_from_score_band(
    retrieval_session,
    monkeypatch,
):
    _seed_judge_model_registry()
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _FakeJudgeLLMService(
            response_payload={
                "status": "strong",
                "label": "strong",
                "score": 0.86,
                "explanation": "The query is concrete and well scoped.",
            }
        ),
    )

    case = load_case(
        _case_path("retrieval", "search", "query_trace_and_provenance.v1.json")
    )
    case.input.env_overrides.update(
        {
            "enable_subjective_judges": True,
            "judge_model_id": "model-eval",
            "judge_provider_id": "provider-eval",
        }
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    subjective_scores = [score for score in result.scores if score.kind == "llm"]
    assert len(subjective_scores) == 1
    score = subjective_scores[0]
    assert score.status == "pass"
    assert score.value == 0.86
    assert score.metadata["judge_status_source"] == "score_band_fallback"
    assert score.metadata["judge_score_band"] == "pass"
    assert result.report["subjective_hook_summary"]["status_counts"] == {"pass": 1}


@pytest.mark.asyncio
async def test_eval_runner_replay_persists_subjective_hook_artifacts(
    retrieval_session,
    monkeypatch,
    tmp_path,
):
    _seed_judge_model_registry()
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _FakeJudgeLLMService(
            response_payload={
                "status": "warn",
                "label": "acceptable",
                "score": 0.62,
                "explanation": "The query is relevant but could include one more discriminating concept.",
            }
        ),
    )

    case = load_case(
        _case_path("retrieval", "search", "query_trace_and_provenance.v1.json")
    )
    case.input.env_overrides.update(
        {
            "enable_subjective_judges": True,
            "judge_model_id": "model-eval",
            "judge_provider_id": "provider-eval",
            "save_replay_dir": str(tmp_path / "replays"),
        }
    )
    result = await EvalRunner(retrieval_session).run_case(case)

    replay_path = result.report.get("replay_path")
    assert replay_path is not None
    replay_payload = load_replay(replay_path)
    judge_artifact = next(
        artifact
        for artifact in replay_payload["artifacts"]
        if artifact["kind"] == "subjective_hook_record"
    )
    assert judge_artifact["payload"]["hook_id"] == "retrieval_query_quality"
    assert judge_artifact["payload"]["request"]["rubric"]["ref"] == "retrieval/query-quality/v1"
    assert judge_artifact["payload"]["response"]["score"] == 0.62
