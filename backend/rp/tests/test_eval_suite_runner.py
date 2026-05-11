from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.suite import EvalSuiteRunner
from rp.tests.test_eval_setup_cognitive_cases import (
    _CharacterDesignSkillPackFacilitatorLLMService,
)


_PILOT_CASE_PATH = (
    Path(__file__).resolve().parents[1]
    / "eval"
    / "cases"
    / "setup"
    / "skill_pack"
    / "character_design"
    / "pack_loaded_on_stage.v1.json"
)


@pytest.mark.asyncio
async def test_eval_suite_runner_runs_case_path_and_writes_summary(
    retrieval_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CharacterDesignSkillPackFacilitatorLLMService(),
    )

    suite = EvalSuiteRunner(retrieval_session)
    result = await suite.run_path(
        _PILOT_CASE_PATH,
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
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: _CharacterDesignSkillPackFacilitatorLLMService(),
    )

    suite = EvalSuiteRunner(retrieval_session)
    result = await suite.run_path(
        _PILOT_CASE_PATH,
        output_dir=tmp_path / "suite-output",
        repeat_override=2,
    )

    assert result.case_count == 1
    assert result.run_count == 2
    assert result.pass_count == 2
    assert [item.attempt_index for item in result.items] == [1, 2]
