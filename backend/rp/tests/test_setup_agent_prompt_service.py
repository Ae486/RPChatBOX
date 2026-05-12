"""Unit tests for SetupAgentPromptService SkillPack integration."""

from __future__ import annotations

import pytest

from rp.agent_runtime.contracts import SetupCapabilityGuidanceFragment
from rp.agent_runtime.profiles import (
    SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS,
    SETUP_AGENT_VISIBLE_TOOLS,
    build_setup_agent_capability_plan,
)
from rp.models.setup_handoff import SetupContextPacket
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.services.setup_agent_prompt_service import SetupAgentPromptService


def _packet(
    *,
    current_stage: SetupStageId | None,
    current_step: SetupStepId = SetupStepId.FOUNDATION,
) -> SetupContextPacket:
    return SetupContextPacket(
        workspace_id="ws-test",
        current_step=current_step.value,
        current_stage=current_stage,
        user_prompt="hi",
    )


CHARACTER_DESIGN_LEGACY_OVERLAY_PROSE = (
    "Focus on stable character, relationship, group, and role facts."
)
PROMPT_TOOL_NAME_CANDIDATES = {
    *SETUP_AGENT_VISIBLE_TOOLS,
    *SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS,
    "proposal.submit",
}


def test_character_design_stage_loads_skill_pack_into_system_prompt():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.CHARACTER_DESIGN)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.CHARACTER_DESIGN,
        context_packet=packet,
    )

    assert "[Stage Skill Pack: character-design.v1]" in prompt
    assert "[/Stage Skill Pack]" in prompt
    assert "## Specialist hat" in prompt


def test_character_design_stage_inserts_specialist_hat_preamble():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.CHARACTER_DESIGN)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.CHARACTER_DESIGN,
        context_packet=packet,
    )

    assert "For this turn, you operate in the 角色设定 stage." in prompt
    assert (
        "While in this stage, take on the perspective of the Specialist hat" in prompt
    )
    assert "never break the SetupAgent operating envelope above" in prompt


def test_character_design_stage_short_circuits_legacy_stage_overlay_prose():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.CHARACTER_DESIGN)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.CHARACTER_DESIGN,
        context_packet=packet,
    )

    assert CHARACTER_DESIGN_LEGACY_OVERLAY_PROSE not in prompt


def test_character_design_stage_keeps_single_setup_agent_identity_declaration():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.CHARACTER_DESIGN)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.CHARACTER_DESIGN,
        context_packet=packet,
    )

    assert prompt.count("You are SetupAgent") == 1
    assert "You are a senior dramatist" not in prompt


def test_no_skill_pack_when_current_stage_is_none_uses_capability_guidance():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=None, current_step=SetupStepId.FOUNDATION)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=None,
        context_packet=packet,
    )

    assert "[Stage Skill Pack" not in prompt
    assert "Active capability guidance:" in prompt
    assert "setup.patch.foundation_entry" in prompt
    assert "proposal.submit" not in prompt


@pytest.mark.parametrize(
    "stage_id",
    [
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.PLOT_BLUEPRINT,
        SetupStageId.WRITER_CONFIG,
        SetupStageId.WORKER_CONFIG,
        SetupStageId.OVERVIEW,
        SetupStageId.ACTIVATE,
        SetupStageId.RP_INTERACTION_CONTRACT,
        SetupStageId.TRPG_RULES,
    ],
)
def test_non_character_design_stages_do_not_load_any_skill_pack(stage_id):
    service = SetupAgentPromptService()
    packet = _packet(current_stage=stage_id)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=stage_id,
        context_packet=packet,
    )

    assert "[Stage Skill Pack" not in prompt
    assert "For this turn, you operate in the" not in prompt


def test_world_background_prompt_exposes_stage_truth_write_hint():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.WORLD_BACKGROUND)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.WORLD_BACKGROUND,
        context_packet=packet,
    )

    assert "For canonical stage setup.truth.write calls" in prompt
    assert "Use the setup.world_background.* tools" not in prompt
    assert "setup.world_background.write_entry" not in prompt
    assert "setup.world_background.edit_entry" not in prompt
    assert "setup.world_background.delete_entry" not in prompt
    assert (
        "Preferred entry_type values for this stage: world_rule, location, faction, race, history."
        in prompt
    )


@pytest.mark.parametrize(
    "stage_id",
    [
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.PLOT_BLUEPRINT,
        SetupStageId.WRITER_CONFIG,
        SetupStageId.WORKER_CONFIG,
        SetupStageId.OVERVIEW,
        SetupStageId.ACTIVATE,
        SetupStageId.RP_INTERACTION_CONTRACT,
        SetupStageId.TRPG_RULES,
    ],
)
def test_non_character_design_stage_prompt_has_no_skill_pack_residue(stage_id):
    service = SetupAgentPromptService()
    packet = _packet(current_stage=stage_id)

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=stage_id,
        context_packet=packet,
    )

    assert "[Stage Skill Pack" not in prompt
    assert "For this turn, you operate in the" not in prompt
    assert "Active capability guidance:" in prompt


def test_prompt_mentions_only_active_capability_tools_for_world_background():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.WORLD_BACKGROUND)
    plan = build_setup_agent_capability_plan(
        SetupStepId.FOUNDATION.value,
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.WORLD_BACKGROUND,
        context_packet=packet,
        capability_plan=plan,
    )

    mentioned_tools = {
        tool_name for tool_name in PROMPT_TOOL_NAME_CANDIDATES if tool_name in prompt
    }
    assert mentioned_tools.issubset(set(plan.active_tool_names))
    assert "setup.read.draft_refs" in mentioned_tools
    assert "setup.truth.write" in mentioned_tools
    assert "setup.world_background.write_entry" not in mentioned_tools
    assert "proposal.submit" not in mentioned_tools


def test_prompt_filters_inactive_guidance_from_supplied_capability_plan():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.WORLD_BACKGROUND)
    plan = build_setup_agent_capability_plan(
        SetupStepId.FOUNDATION.value,
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )
    bad_plan = plan.model_copy(
        update={
            "prompt_guidance_fragments": [
                *plan.prompt_guidance_fragments,
                SetupCapabilityGuidanceFragment(
                    fragment_id="bad.world_background",
                    tool_names=["setup.world_background.write_entry"],
                    text="Use setup.world_background.write_entry directly.",
                ),
            ]
        },
        deep=True,
    )

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.WORLD_BACKGROUND,
        context_packet=packet,
        capability_plan=bad_plan,
    )

    assert "setup.world_background.write_entry" not in prompt


def test_system_prompt_contains_only_stable_context_packet_not_runtime_artifact_data():
    service = SetupAgentPromptService()
    packet = _packet(current_stage=SetupStageId.WORLD_BACKGROUND)
    plan = build_setup_agent_capability_plan(
        SetupStepId.FOUNDATION.value,
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )

    prompt = service.build_system_prompt(
        mode=StoryMode.LONGFORM,
        current_step=SetupStepId.FOUNDATION,
        current_stage=SetupStageId.WORLD_BACKGROUND,
        context_packet=packet,
        capability_plan=plan,
    )

    assert '"workspace_id": "ws-test"' in prompt
    assert '"current_stage": "world_background"' in prompt
    assert "context_report" not in prompt
    assert "raw_history_limit" not in prompt
    assert "history_count_threshold" not in prompt
    assert "working_digest" not in prompt
    assert "tool_outcomes" not in prompt
    assert "source_fingerprint" not in prompt
    assert "summary_lines" not in prompt
    assert "loop_trace" not in prompt
    assert "continue_reason" not in prompt
    assert "raw_tool_retry_process" not in prompt
