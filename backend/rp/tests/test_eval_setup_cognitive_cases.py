from __future__ import annotations

import json
from pathlib import Path

import pytest

from rp.eval.case_loader import load_case
from rp.eval.runner import EvalRunner
from rp.eval.replay import load_replay


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "cases"
        / "setup"
        / Path(*parts)
    )


def _all_setup_case_paths() -> list[Path]:
    return sorted(_case_path().rglob("*.json"))


def _extract_workspace_id(request) -> str:
    system_prompt = request.messages[0].content or ""
    return system_prompt.split('"workspace_id": "')[1].split('"')[0]


class _SchemaAutoRepairSetupLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            arguments = {"workspace_id": workspace_id}
            return _tool_call_response(
                call_id="call_bad_patch",
                tool_name="rp_setup__setup.patch.story_config",
                arguments=arguments,
            )
        if self._round == 2:
            arguments = {
                "workspace_id": workspace_id,
                "patch": {"notes": "tight setup note"},
            }
            return _tool_call_response(
                call_id="call_good_patch",
                tool_name="rp_setup__setup.patch.story_config",
                arguments=arguments,
            )
        return _text_response("Corrected the tool call and finished.")


class _TruthWriteAskUserLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_truth_write",
                tool_name="rp_setup__setup.truth.write",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "writing_contract",
                    "truth_write": {
                        "write_id": "truth-write-empty",
                        "current_step": "writing_contract",
                        "block_type": "writing_contract",
                        "operation": "merge",
                        "payload": {},
                    },
                },
            )
        return _text_response(
            "I still need your concrete writing preferences. Which POV and style rules do you want me to lock in?"
        )


class _ExplainInsteadOfRepairSetupLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_bad_patch",
                tool_name="rp_setup__setup.patch.story_config",
                arguments={"workspace_id": workspace_id},
            )
        return _text_response(
            "I know the patch field is missing, so I cannot continue yet."
        )


class _CommitBlockedQuestionLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_commit",
                tool_name="rp_setup__setup.proposal.commit",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "foundation",
                    "target_draft_refs": ["foundation:world_rule_1"],
                },
            )
        return _text_response(
            "We still need to resolve this setup detail before review. Which final rule do you want me to lock in?"
        )


class _RejectedProposalDiscussionLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_commit_again",
                tool_name="rp_setup__setup.proposal.commit",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "story_config",
                    "target_draft_refs": ["draft:story_config"],
                },
            )
        return _text_response(
            "The last proposal was rejected, so I should continue refining the step before another review."
        )


class _UserEditInvalidationLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        return _text_response(
            "I saw the latest edit. Which final tone note should I keep before moving back toward review?"
        )


class _ProposalRejectedInvalidationLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        return _text_response(
            "The last review was rejected. Which runtime preference do you want me to revise before I propose review again?"
        )


class _TruthWriteTargetRefAutoRepairLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_truth_write_bad_target",
                tool_name="rp_setup__setup.truth.write",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "writing_contract",
                    "truth_write": {
                        "write_id": "truth-write-bad-target",
                        "current_step": "writing_contract",
                        "block_type": "writing_contract",
                        "target_ref": "draft:story_config",
                        "operation": "merge",
                        "payload": {
                            "notes": "Use sparse, intimate narration."
                        }
                    }
                },
            )
        if self._round == 2:
            return _tool_call_response(
                call_id="call_truth_write_good_target",
                tool_name="rp_setup__setup.truth.write",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "writing_contract",
                    "truth_write": {
                        "write_id": "truth-write-good-target",
                        "current_step": "writing_contract",
                        "block_type": "writing_contract",
                        "target_ref": "draft:writing_contract",
                        "operation": "merge",
                        "payload": {
                            "notes": "Use sparse, intimate narration."
                        },
                        "ready_for_review": True,
                        "remaining_open_issues": []
                    }
                },
            )
        return _text_response("I repaired the target and wrote the contract update cleanly.")


class _TruthWriteCreateConflictLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_truth_write_create_conflict",
                tool_name="rp_setup__setup.truth.write",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "story_config",
                    "truth_write": {
                        "write_id": "truth-write-create-conflict",
                        "current_step": "story_config",
                        "block_type": "story_config",
                        "target_ref": "draft:story_config",
                        "operation": "create",
                        "payload": {
                            "notes": "Fresh config block"
                        }
                    }
                },
            )
        return _text_response(
            "That block already has content. Do you want me to merge the new note into the existing story config instead?"
        )


class _TruthWriteReplaceMissingLLMService:
    def __init__(self) -> None:
        self._round = 0

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        self._round += 1
        workspace_id = _extract_workspace_id(request)
        if self._round == 1:
            return _tool_call_response(
                call_id="call_truth_write_replace_missing",
                tool_name="rp_setup__setup.truth.write",
                arguments={
                    "workspace_id": workspace_id,
                    "step_id": "foundation",
                    "truth_write": {
                        "write_id": "truth-write-replace-missing",
                        "current_step": "foundation",
                        "block_type": "foundation_entry",
                        "target_ref": "foundation:missing_entry",
                        "operation": "replace",
                        "payload": {
                            "entry_id": "missing_entry",
                            "domain": "world",
                            "path": "world.missing_entry",
                            "title": "Missing Entry",
                            "tags": ["world"],
                            "source_refs": [],
                            "content": {
                                "summary": "Replacement payload"
                            }
                        }
                    }
                },
            )
        return _text_response(
            "That foundation target does not exist yet. Do you want me to create it as a new entry instead?"
        )


class _ProviderFailureSetupLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        raise RuntimeError("provider upstream unavailable")


def _tool_call_response(*, call_id: str, tool_name: str, arguments: dict):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _text_response(text: str):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text,
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_file", "llm_factory", "expected_report"),
    [
        (
            _case_path("repair", "story_config_schema_auto_repair_success.v1.json"),
            _SchemaAutoRepairSetupLLMService,
            {"finish_reason": "completed_text", "repair_route": "auto_repair", "commit_blocked": False},
        ),
        (
            _case_path("repair", "writing_contract_ask_user_after_semantic_fail.v1.json"),
            _TruthWriteAskUserLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": "ask_user", "commit_blocked": False},
        ),
        (
            _case_path("guard", "repair_obligation_false_success_blocked.v1.json"),
            _ExplainInsteadOfRepairSetupLLMService,
            {"finish_reason": "repair_obligation_unfulfilled", "repair_route": "auto_repair", "commit_blocked": False},
        ),
        (
            _case_path("commit", "blocked_truth_write_not_ready.v1.json"),
            _CommitBlockedQuestionLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": "block_commit", "commit_blocked": True},
        ),
        (
            _case_path("commit", "blocked_truth_write_open_issues.v1.json"),
            _CommitBlockedQuestionLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": "block_commit", "commit_blocked": True},
        ),
        (
            _case_path("commit", "rejected_proposal_back_to_discussion.v1.json"),
            _RejectedProposalDiscussionLLMService,
            {"finish_reason": "continue_discussion", "repair_route": "block_commit", "commit_blocked": True},
        ),
        (
            _case_path("cognitive", "invalidate_after_user_edit.v1.json"),
            _UserEditInvalidationLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": None, "commit_blocked": False},
        ),
        (
            _case_path("cognitive", "invalidate_after_proposal_reject.v1.json"),
            _ProposalRejectedInvalidationLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": None, "commit_blocked": False},
        ),
        (
            _case_path("repair", "truth_write_target_ref_auto_repair_success.v1.json"),
            _TruthWriteTargetRefAutoRepairLLMService,
            {"finish_reason": "completed_text", "repair_route": "continue_discussion", "commit_blocked": False},
        ),
        (
            _case_path("repair", "truth_write_create_requires_empty_target.v1.json"),
            _TruthWriteCreateConflictLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": "continue_discussion", "commit_blocked": False},
        ),
        (
            _case_path("repair", "truth_write_replace_requires_existing_target.v1.json"),
            _TruthWriteReplaceMissingLLMService,
            {"finish_reason": "awaiting_user_input", "repair_route": "continue_discussion", "commit_blocked": False},
        ),
        (
            _case_path("infra", "provider_request_failed_during_turn.v1.json"),
            _ProviderFailureSetupLLMService,
            {
                "finish_reason": None,
                "repair_route": None,
                "commit_blocked": False,
                "run_status": "failed",
                "failure_layer": "infra",
            },
        ),
    ],
)
async def test_eval_setup_cognitive_cases_from_files(
    retrieval_session,
    monkeypatch,
    tmp_path,
    case_file: Path,
    llm_factory,
    expected_report: dict,
):
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: llm_factory(),
    )

    case = load_case(case_file)
    if case.case_id == "setup.repair.story_config.schema_auto_repair_success.v1":
        case.input.env_overrides["save_replay_dir"] = str(tmp_path / "replays")

    runner = EvalRunner(retrieval_session)
    result = await runner.run_case(case)

    assert result.run.status == expected_report.get("run_status", result.run.status)
    assert result.report["finish_reason"] == expected_report["finish_reason"]
    assert result.report["repair_route"] == expected_report["repair_route"]
    assert result.report["commit_blocked"] == expected_report["commit_blocked"]
    if "failure_layer" in expected_report:
        assert result.report["failure_layer"] == expected_report["failure_layer"]
    assert result.report["assertion_summary"]["fail"] == 0

    if case.case_id == "setup.repair.story_config.schema_auto_repair_success.v1":
        replay_path = result.report.get("replay_path")
        assert replay_path is not None
        replay_payload = load_replay(replay_path)
        assert replay_payload["case"]["case_id"] == case.case_id


def test_all_setup_case_files_define_diagnostic_expectations():
    missing_reason_codes: list[str] = []
    missing_outcome_chain: list[str] = []
    missing_next_actions: list[str] = []

    for case_path in _all_setup_case_paths():
        case = load_case(case_path)
        if not case.expected.expected_reason_codes:
            missing_reason_codes.append(case.case_id)
        if not case.expected.expected_outcome_chain:
            missing_outcome_chain.append(case.case_id)
        if not case.expected.expected_recommended_next_action:
            missing_next_actions.append(case.case_id)

    assert not missing_reason_codes, missing_reason_codes
    assert not missing_outcome_chain, missing_outcome_chain
    assert not missing_next_actions, missing_next_actions
