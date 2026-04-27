from __future__ import annotations

import json
from pathlib import Path

import pytest

from rp.agent_runtime.contracts import SetupCognitiveStateSnapshot
from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.eval.case_loader import load_case
from rp.eval.models import EvalCase
from rp.eval.runner import EvalRunner
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / Path(*parts)
    )


class _CommitProposalLLMService:
    def __init__(self) -> None:
        self._chat_round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._chat_round += 1
        system_prompt = request.messages[0].content or ""
        workspace_id = system_prompt.split('"workspace_id": "')[1].split('"')[0]
        if self._chat_round == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_commit",
                                    "type": "function",
                                    "function": {
                                        "name": "rp_setup__setup.proposal.commit",
                                        "arguments": json.dumps(
                                            {
                                                "workspace_id": workspace_id,
                                                "step_id": "writing_contract",
                                                "target_draft_refs": ["draft:writing_contract"],
                                                "reason": "The writing contract is coherent enough for review.",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I prepared a review proposal.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


class _StreamCommitProposalLLMService:
    def __init__(self) -> None:
        self._chat_round = 0

    async def chat_completion_stream(self, request):
        self._chat_round += 1
        system_prompt = request.messages[0].content or ""
        workspace_id = system_prompt.split('"workspace_id": "')[1].split('"')[0]
        if self._chat_round == 1:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "tool_call",
                        "tool_calls": [
                            {
                                "id": "call_commit_stream",
                                "type": "function",
                                "function": {
                                    "name": "rp_setup__setup.proposal.commit",
                                    "arguments": json.dumps(
                                        {
                                            "workspace_id": workspace_id,
                                            "step_id": "writing_contract",
                                            "target_draft_refs": ["draft:writing_contract"],
                                            "reason": "The writing contract is coherent enough for review.",
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            yield 'data: {"type":"done"}\n\n'
            return

        yield 'data: {"type":"text_delta","delta":"I prepared a review proposal."}\n\n'
        yield 'data: {"type":"done"}\n\n'

    async def chat_completion(self, request):
        raise AssertionError("non-stream path not expected")


class _DiscussionOnlyLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "We should reconcile the selected user edit before moving to commit.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@pytest.mark.asyncio
async def test_eval_runner_executes_setup_case_and_creates_proposal(
    retrieval_session,
    monkeypatch,
):
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module

    model_registry_module._model_registry_service = None

    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()
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

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CommitProposalLLMService(),
    )

    case = EvalCase.model_validate(
        {
            "case_id": "setup.commit_proposal.writing_contract.ready.v1",
            "title": "Writing contract ready proposal",
            "scope": "setup",
            "category": "commit_proposal",
            "tags": ["mvp", "deterministic"],
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "input": {
                "request": {
                    "workspace_id": "workspace-case-1",
                    "model_id": "model-eval",
                    "provider_id": "provider-eval",
                    "user_prompt": "如果已经足够，请发起 review。",
                    "history": [],
                },
                "workspace_seed": {
                    "story_id": "story-eval-1",
                    "mode": "longform",
                    "current_step": "writing_contract",
                    "drafts": {
                        "writing_contract": {
                            "pov_rules": ["third_person_limited"],
                            "style_rules": ["restrained"],
                            "writing_constraints": ["avoid exposition dumps"],
                        }
                    },
                },
                "env_overrides": {},
            },
            "preconditions": {},
            "expected": {
                "deterministic_assertions": [
                    {
                        "assertion_id": "proposal_created",
                        "source": "workspace_truth",
                        "type": "equals",
                        "path": "commit_proposals[-1].status",
                        "expected": "pending_review",
                        "severity": "error",
                    }
                ],
                "subjective_hooks": [],
            },
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

    runner = EvalRunner(retrieval_session)
    result = await runner.run_case(case)

    assert result.run.status == "completed"
    assert result.runtime_result["finish_reason"] == "completed_text"
    assert result.runtime_result["tool_invocations"][0]["tool_name"] == "rp_setup__setup.proposal.commit"
    assert any(score.name == "proposal_created" and score.status == "pass" for score in result.scores)
    workspace_after = next(
        artifact for artifact in result.artifacts if artifact.kind == "workspace_after"
    )
    assert workspace_after.payload["commit_proposals"][-1]["status"] == "pending_review"
    assert result.report["assertion_summary"]["fail"] == 0


@pytest.mark.asyncio
async def test_eval_runner_http_mode_uses_real_setup_turn_route(
    retrieval_session,
    monkeypatch,
):
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module

    model_registry_module._model_registry_service = None

    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id="provider-eval-http",
            name="Eval Provider HTTP",
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
            is_enabled=True,
        )
    )
    model_service.upsert_entry(
        ModelRegistryEntry(
            id="model-eval-http",
            provider_id="provider-eval-http",
            model_name="gpt-4o-mini",
            display_name="Eval Model HTTP",
            capabilities=["text", "tool"],
            is_enabled=True,
        )
    )

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CommitProposalLLMService(),
    )

    case = EvalCase.model_validate(
        {
            "case_id": "setup.commit_proposal.writing_contract.http.v1",
            "title": "Writing contract ready proposal via setup API route",
            "scope": "setup",
            "category": "commit_proposal",
            "tags": ["mvp", "deterministic", "http"],
            "runtime_target": {
                "mode": "http",
                "entrypoint": "/api/rp/setup/workspaces/{workspace_id}/turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "input": {
                "request": {
                    "workspace_id": "workspace-case-http-1",
                    "model_id": "model-eval-http",
                    "provider_id": "provider-eval-http",
                    "user_prompt": "如果已经足够，请发起 review。",
                    "history": [],
                },
                "workspace_seed": {
                    "story_id": "story-eval-http-1",
                    "mode": "longform",
                    "current_step": "writing_contract",
                    "drafts": {
                        "writing_contract": {
                            "pov_rules": ["third_person_limited"],
                            "style_rules": ["restrained"],
                            "writing_constraints": ["avoid exposition dumps"],
                        }
                    },
                },
                "env_overrides": {},
            },
            "preconditions": {},
            "expected": {
                "deterministic_assertions": [
                    {
                        "assertion_id": "proposal_created_http",
                        "source": "workspace_truth",
                        "type": "equals",
                        "path": "commit_proposals[-1].status",
                        "expected": "pending_review",
                        "severity": "error",
                    }
                ],
                "subjective_hooks": [],
            },
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

    runner = EvalRunner(retrieval_session)
    result = await runner.run_case(case)

    assert result.run.status == "completed"
    assert result.runtime_result["finish_reason"] == "completed_text"
    assert result.runtime_result["tool_invocations"][0]["tool_name"] == "rp_setup__setup.proposal.commit"
    assert any(
        score.name == "proposal_created_http" and score.status == "pass"
        for score in result.scores
    )
    assert result.report["assertion_summary"]["fail"] == 0


@pytest.mark.asyncio
async def test_eval_runner_http_stream_mode_uses_real_setup_turn_stream_route(
    retrieval_session,
    monkeypatch,
):
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module

    model_registry_module._model_registry_service = None

    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id="provider-eval-http-stream",
            name="Eval Provider HTTP Stream",
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
            is_enabled=True,
        )
    )
    model_service.upsert_entry(
        ModelRegistryEntry(
            id="model-eval-http-stream",
            provider_id="provider-eval-http-stream",
            model_name="gpt-4o-mini",
            display_name="Eval Model HTTP Stream",
            capabilities=["text", "tool"],
            is_enabled=True,
        )
    )

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _StreamCommitProposalLLMService(),
    )

    case = EvalCase.model_validate(
        {
            "case_id": "setup.commit_proposal.writing_contract.http.stream.v1",
            "title": "Writing contract ready proposal via setup stream API route",
            "scope": "setup",
            "category": "commit_proposal",
            "tags": ["mvp", "deterministic", "http", "stream"],
            "runtime_target": {
                "mode": "http",
                "entrypoint": "/api/rp/setup/workspaces/{workspace_id}/turn/stream",
                "graph_id": "setup_v2",
                "stream": True,
            },
            "input": {
                "request": {
                    "workspace_id": "workspace-case-http-stream-1",
                    "model_id": "model-eval-http-stream",
                    "provider_id": "provider-eval-http-stream",
                    "user_prompt": "如果已经足够，请发起 review。",
                    "history": [],
                },
                "workspace_seed": {
                    "story_id": "story-eval-http-stream-1",
                    "mode": "longform",
                    "current_step": "writing_contract",
                    "drafts": {
                        "writing_contract": {
                            "pov_rules": ["third_person_limited"],
                            "style_rules": ["restrained"],
                            "writing_constraints": ["avoid exposition dumps"],
                        }
                    },
                },
                "env_overrides": {},
            },
            "preconditions": {},
            "expected": {
                "deterministic_assertions": [
                    {
                        "assertion_id": "proposal_created_http_stream",
                        "source": "workspace_truth",
                        "type": "equals",
                        "path": "commit_proposals[-1].status",
                        "expected": "pending_review",
                        "severity": "error",
                    }
                ],
                "subjective_hooks": [],
            },
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

    runner = EvalRunner(retrieval_session)
    result = await runner.run_case(case)

    event_types = [event.type for event in result.trace.events]

    assert result.run.status == "completed"
    assert result.runtime_result["finish_reason"] == "completed_text"
    assert result.runtime_result["tool_invocations"][0]["tool_name"] == "rp_setup__setup.proposal.commit"
    assert "runtime_event.tool_call" in event_types
    assert "runtime_event.tool_result" in event_types
    assert any(
        score.name == "proposal_created_http_stream" and score.status == "pass"
        for score in result.scores
    )
    assert result.report["assertion_summary"]["fail"] == 0


@pytest.mark.asyncio
async def test_eval_runner_can_seed_cognitive_state_and_expose_eval_artifacts(
    retrieval_session,
    monkeypatch,
):
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module

    model_registry_module._model_registry_service = None

    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id="provider-eval-2",
            name="Eval Provider 2",
            type="openai",
            api_key="sk-test",
            api_url="https://example.com/v1",
            custom_headers={},
            is_enabled=True,
        )
    )
    model_service.upsert_entry(
        ModelRegistryEntry(
            id="model-eval-2",
            provider_id="provider-eval-2",
            model_name="gpt-4o-mini",
            display_name="Eval Model 2",
            capabilities=["text", "tool"],
            is_enabled=True,
        )
    )

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _DiscussionOnlyLLMService(),
    )

    case = EvalCase.model_validate(
        {
            "case_id": "setup.cognitive_state.seeded.foundation.v1",
            "title": "Seeded cognitive state is visible to eval",
            "scope": "setup",
            "category": "cognitive_state",
            "runtime_target": {
                "mode": "in_process",
                "entrypoint": "setup_graph_runner.run_turn",
                "graph_id": "setup_v2",
                "stream": False,
            },
            "input": {
                "request": {
                    "workspace_id": "workspace-case-2",
                    "model_id": "model-eval-2",
                    "provider_id": "provider-eval-2",
                    "target_step": "foundation",
                    "user_prompt": "继续讨论。",
                    "history": [],
                },
                "workspace_seed": {
                    "story_id": "story-eval-2",
                    "mode": "longform",
                    "current_step": "foundation",
                    "cognitive_states": [
                        SetupCognitiveStateSnapshot(
                            workspace_id="workspace-case-2",
                            current_step="foundation",
                            state_version=1,
                            invalidated=True,
                            invalidation_reasons=["user_edit_delta"],
                            source_basis={
                                "workspace_version": 1,
                                "draft_fingerprint": None,
                                "pending_user_edit_delta_ids": ["delta-1"],
                                "last_proposal_status": None,
                                "current_step": "foundation",
                            },
                        ).model_dump(mode="json", exclude_none=True)
                    ],
                },
                "env_overrides": {},
            },
            "preconditions": {},
            "expected": {
                "deterministic_assertions": [
                    {
                        "assertion_id": "cognitive_state_invalidated",
                        "source": "runtime_result",
                        "type": "equals",
                        "path": "structured_payload.cognitive_state_summary.invalidated",
                        "expected": True,
                        "severity": "error",
                    }
                ],
                "subjective_hooks": [],
            },
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

    runner = EvalRunner(retrieval_session)
    result = await runner.run_case(case)

    artifact_kinds = {artifact.kind for artifact in result.artifacts}

    assert result.run.status == "completed"
    assert result.report["cognitive_state_invalidated"] is True
    assert "cognitive_state_summary" in artifact_kinds
    assert "cognitive_state" in artifact_kinds
    assert any(
        score.name == "cognitive_state_invalidated" and score.status == "pass"
        for score in result.scores
    )


def test_materialize_isolated_case_merges_retrieval_runtime_overrides(retrieval_session):
    runner = EvalRunner(retrieval_session)
    case = load_case(str(_case_path("retrieval", "search", "query_trace_and_provenance.v1.json")))
    case = case.model_copy(
        deep=True,
        update={
            "input": case.input.model_copy(
                deep=True,
                update={
                    "env_overrides": {
                        **case.input.env_overrides,
                        "retrieval_embedding_model_id": "embed-model-id",
                        "retrieval_embedding_provider_id": "embed-provider-id",
                        "retrieval_rerank_model_id": "rerank-model-id",
                        "retrieval_rerank_provider_id": "rerank-provider-id",
                    }
                },
            )
        },
    )

    isolated = runner._materialize_isolated_case(case)
    story_config = isolated.input.workspace_seed["drafts"]["story_config"]

    assert isolated.input.workspace_seed["story_id"].startswith("story-case-retrieval-trace-001--run-")
    assert story_config["retrieval_embedding_model_id"] == "embed-model-id"
    assert story_config["retrieval_embedding_provider_id"] == "embed-provider-id"
    assert story_config["retrieval_rerank_model_id"] == "rerank-model-id"
    assert story_config["retrieval_rerank_provider_id"] == "rerank-provider-id"

