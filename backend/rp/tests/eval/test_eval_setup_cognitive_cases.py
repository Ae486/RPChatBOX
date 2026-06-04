from __future__ import annotations

from pathlib import Path

import pytest

from rp.eval.case_loader import load_case
from rp.eval.runner import EvalRunner
from rp.eval.replay import load_replay


def _case_path(*parts: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "eval"
        / "cases"
        / "setup"
        / Path(*parts)
    )


def _all_setup_case_paths() -> list[Path]:
    return sorted(_case_path().rglob("*.json"))


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


class _ProviderFailureSetupLLMService:
    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        raise RuntimeError("provider upstream unavailable")


class _CharacterDesignSkillPackFacilitatorLLMService:
    """Stage-2 D-pilot mock that embodies the character-design SkillPack persona.

    The reply text doubles as the Stage-3 LLM-judge reference anchor for the
    `setup/persona-alignment/v1` / `setup/forbidden-compliance/v1` /
    `setup/facilitation-depth/v1` rubrics. It MUST:
      - speak as a senior dramatist eliciting the cast (no "You are X" framing),
      - probe `motivation.real` and `world_fit` rather than asking for the name,
      - use the SkillPack `## Clarification templates` Chinese template verbatim
        for the motivation-depth probe,
      - avoid any narrative prose / scene writing,
      - avoid claiming the stage is ready or proposing commit,
      - issue zero tool calls.
    """

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        text = (
            "在锁定林夕这位主角之前，先把他的内核多探一层。\n"
            "1) 动机深度：角色 X 表面上想要 Y，但他真正怕失去的是什么？请套用到林夕——"
            "他表面上想要救人/复仇/守护谁，但他真正害怕失去的、宁可妥协也不愿被夺走的是哪一样？\n"
            "2) 世界适配（world_fit）：在你 world_background 阶段确立的世界规则下，林夕"
            "做不到的事情是什么？哪一类处境最容易把这位'勇敢的少年'逼到最狼狈、最不像他自己？\n"
            "等你回答这两点，我再回头把性格、能力、声音节奏这些维度沿着他的真实驱动力补全。"
        )
        return _text_response(text)


class _PlotBlueprintAskUserLLMService:
    """Stage-4 hard-unload mock for the plot_blueprint stage.

    Used by `cases/setup/skill_pack/character_design/pack_unloaded_on_other_stage.v1.json`
    to verify that switching `target_stage` away from `character_design` produces
    `skill_pack_name = None` (hard-unload). The reply is intentionally a plot-blueprint
    facilitation question with zero tool calls.
    """

    async def chat_completion_stream(self, request):
        raise AssertionError("stream path not expected")

    async def chat_completion(self, request):
        return _text_response(
            "在排剧情骨架前，先确认两点：主线驱动事件是什么？哪一个转折点是你现在最想锁定的？"
        )


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


_PRE_EXISTING_FAILURE_CLUSTER_4 = (
    "Pre-existing failure (eval runner business assertions: 'failed' vs 'completed'). "
    "See .trellis/tasks/archive/2026-05/05-25-services-directory-reorganization/research/pre-existing-failures-19.md cluster 4. "
    "Tracked by T19 (coupled with `05-11-runtime-classifier-drift`) in .trellis/spec/guides/project-optimization-master-guide.md."
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_file", "llm_factory", "expected_report"),
    [
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
        pytest.param(
            _case_path("infra", "provider_request_failed_during_turn.v1.json"),
            _ProviderFailureSetupLLMService,
            {
                "finish_reason": None,
                "repair_route": None,
                "commit_blocked": False,
                "run_status": "failed",
                "failure_layer": "infra",
            },
            marks=pytest.mark.xfail(reason=_PRE_EXISTING_FAILURE_CLUSTER_4, strict=False),
        ),
        (
            _case_path(
                "skill_pack",
                "character_design",
                "pack_loaded_on_stage.v1.json",
            ),
            _CharacterDesignSkillPackFacilitatorLLMService,
            {
                "finish_reason": "awaiting_user_input",
                "repair_route": None,
                "commit_blocked": False,
            },
        ),
        (
            _case_path(
                "skill_pack",
                "character_design",
                "pack_unloaded_on_other_stage.v1.json",
            ),
            _PlotBlueprintAskUserLLMService,
            {
                "finish_reason": "awaiting_user_input",
                "repair_route": None,
                "commit_blocked": False,
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
        "rp.services.setup_agent.agent_execution_service.get_litellm_service",
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
        # SkillPack cases test persona / forbidden / facilitation alignment, not
        # runtime diagnostic remediation. The diagnostic_*  vocabulary (reason
        # codes, outcome chain, recommended_next_action) does not apply, so they
        # are exempted from the all-cases shape contract. See
        # `.trellis/spec/backend/rp-eval-expected-extensions.md` for the eval
        # field surface used by SkillPack cases instead.
        if case.category == "skill_pack":
            continue
        if not case.expected.expected_reason_codes:
            missing_reason_codes.append(case.case_id)
        if not case.expected.expected_outcome_chain:
            missing_outcome_chain.append(case.case_id)
        if not case.expected.expected_recommended_next_action:
            missing_next_actions.append(case.case_id)

    assert not missing_reason_codes, missing_reason_codes
    assert not missing_outcome_chain, missing_outcome_chain
    assert not missing_next_actions, missing_next_actions
