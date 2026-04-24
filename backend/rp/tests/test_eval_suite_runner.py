from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.suite import EvalSuiteRunner


@pytest.mark.asyncio
async def test_eval_suite_runner_runs_case_path_and_writes_summary(
    retrieval_session,
    monkeypatch,
    tmp_path,
):
    class _SchemaAutoRepairSetupLLMService:
        def __init__(self) -> None:
            self._round = 0

        async def chat_completion_stream(self, request):
            raise AssertionError("stream path not expected")

        async def chat_completion(self, request):
            import json

            self._round += 1
            system_prompt = request.messages[0].content or ""
            workspace_id = system_prompt.split('"workspace_id": "')[1].split('"')[0]
            if self._round == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_bad_patch",
                                        "type": "function",
                                        "function": {
                                            "name": "rp_setup__setup.patch.story_config",
                                            "arguments": json.dumps({"workspace_id": workspace_id}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            if self._round == 2:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_good_patch",
                                        "type": "function",
                                        "function": {
                                            "name": "rp_setup__setup.patch.story_config",
                                            "arguments": json.dumps(
                                                {
                                                    "workspace_id": workspace_id,
                                                    "patch": {"notes": "tight setup note"},
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Corrected the tool call and finished.",
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _SchemaAutoRepairSetupLLMService(),
    )

    suite = EvalSuiteRunner(retrieval_session)
    result = await suite.run_path(
        Path("H:/chatboxapp/backend/rp/eval/cases/setup/repair/story_config_schema_auto_repair_success.v1.json"),
        output_dir=tmp_path / "suite-output",
    )

    assert result.case_count == 1
    assert result.run_count == 1
    assert result.pass_count == 1
    assert (tmp_path / "suite-output" / "suite-summary.json").exists()


@pytest.mark.asyncio
async def test_eval_suite_runner_repeat_override_runs_case_multiple_times(
    retrieval_session,
    monkeypatch,
    tmp_path,
):
    class _SchemaAutoRepairSetupLLMService:
        def __init__(self) -> None:
            self._round = 0

        async def chat_completion_stream(self, request):
            raise AssertionError("stream path not expected")

        async def chat_completion(self, request):
            import json

            self._round += 1
            system_prompt = request.messages[0].content or ""
            workspace_id = system_prompt.split('"workspace_id": "')[1].split('"')[0]
            if self._round % 3 == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": f"call_bad_patch_{self._round}",
                                        "type": "function",
                                        "function": {
                                            "name": "rp_setup__setup.patch.story_config",
                                            "arguments": json.dumps({"workspace_id": workspace_id}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            if self._round % 3 == 2:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": f"call_good_patch_{self._round}",
                                        "type": "function",
                                        "function": {
                                            "name": "rp_setup__setup.patch.story_config",
                                            "arguments": json.dumps(
                                                {
                                                    "workspace_id": workspace_id,
                                                    "patch": {"notes": "tight setup note"},
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Corrected the tool call and finished.",
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _SchemaAutoRepairSetupLLMService(),
    )

    suite = EvalSuiteRunner(retrieval_session)
    result = await suite.run_path(
        Path("H:/chatboxapp/backend/rp/eval/cases/setup/repair/story_config_schema_auto_repair_success.v1.json"),
        output_dir=tmp_path / "suite-output",
        repeat_override=2,
    )

    assert result.case_count == 1
    assert result.run_count == 2
    assert result.pass_count == 2
    assert [item.attempt_index for item in result.items] == [1, 2]
