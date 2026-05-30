"""Canonical setup stage modules and mode plans."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SetupStageId(StrEnum):
    """User-facing setup stages that define the canonical setup lifecycle."""

    WORLD_BACKGROUND = "world_background"
    CHARACTER_DESIGN = "character_design"
    PLOT_BLUEPRINT = "plot_blueprint"
    WRITER_CONFIG = "writer_config"
    WORKER_CONFIG = "worker_config"
    OVERVIEW = "overview"
    ACTIVATE = "activate"
    RP_INTERACTION_CONTRACT = "rp_interaction_contract"
    TRPG_RULES = "trpg_rules"


class SetupDraftSectionTemplate(BaseModel):
    """Lightweight stage-module hint for expected draft sections."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    kind: str
    retrieval_role: str = "detail"
    tags: list[str] = Field(default_factory=list)


class SetupStageModule(BaseModel):
    """Reusable setup stage module definition."""

    model_config = ConfigDict(extra="forbid")

    stage_id: SetupStageId
    display_name: str
    draft_block_type: str
    default_entry_types: list[str] = Field(default_factory=list)
    default_section_templates: list[SetupDraftSectionTemplate] = Field(default_factory=list)
    allow_commit: bool = True
    discussion_stage: bool = True


class SetupModeStagePlan(BaseModel):
    """Ordered stage plan for one setup mode."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    stage_ids: list[SetupStageId]


SETUP_STAGE_MODULES: dict[SetupStageId, SetupStageModule] = {
    SetupStageId.WORLD_BACKGROUND: SetupStageModule(
        stage_id=SetupStageId.WORLD_BACKGROUND,
        display_name="世界观背景",
        draft_block_type=SetupStageId.WORLD_BACKGROUND.value,
        default_entry_types=["world_rule", "location", "faction", "race", "history"],
        default_section_templates=[
            SetupDraftSectionTemplate(section_id="summary", title="概要", kind="text"),
            SetupDraftSectionTemplate(section_id="details", title="细节", kind="text"),
        ],
    ),
    SetupStageId.CHARACTER_DESIGN: SetupStageModule(
        stage_id=SetupStageId.CHARACTER_DESIGN,
        display_name="角色设定",
        draft_block_type=SetupStageId.CHARACTER_DESIGN.value,
        default_entry_types=["character", "relationship", "group"],
        default_section_templates=[
            SetupDraftSectionTemplate(section_id="summary", title="概要", kind="text"),
            SetupDraftSectionTemplate(
                section_id="relationships",
                title="关系",
                kind="list",
                retrieval_role="relationship",
            ),
        ],
    ),
    SetupStageId.PLOT_BLUEPRINT: SetupStageModule(
        stage_id=SetupStageId.PLOT_BLUEPRINT,
        display_name="伏笔剧情设计",
        draft_block_type=SetupStageId.PLOT_BLUEPRINT.value,
        default_entry_types=["plot_thread", "foreshadow", "chapter_plan"],
    ),
    SetupStageId.WRITER_CONFIG: SetupStageModule(
        stage_id=SetupStageId.WRITER_CONFIG,
        display_name="作家配置",
        draft_block_type=SetupStageId.WRITER_CONFIG.value,
        default_entry_types=["style_rule", "pov_rule", "writing_constraint"],
    ),
    SetupStageId.WORKER_CONFIG: SetupStageModule(
        stage_id=SetupStageId.WORKER_CONFIG,
        display_name="worker配置",
        draft_block_type=SetupStageId.WORKER_CONFIG.value,
        default_entry_types=["worker_policy", "tool_policy", "handoff_rule"],
    ),
    SetupStageId.OVERVIEW: SetupStageModule(
        stage_id=SetupStageId.OVERVIEW,
        display_name="全览",
        draft_block_type=SetupStageId.OVERVIEW.value,
        default_entry_types=[],
        allow_commit=False,
        discussion_stage=False,
    ),
    SetupStageId.ACTIVATE: SetupStageModule(
        stage_id=SetupStageId.ACTIVATE,
        display_name="activate",
        draft_block_type=SetupStageId.ACTIVATE.value,
        default_entry_types=[],
        allow_commit=False,
        discussion_stage=False,
    ),
    SetupStageId.RP_INTERACTION_CONTRACT: SetupStageModule(
        stage_id=SetupStageId.RP_INTERACTION_CONTRACT,
        display_name="互动契约",
        draft_block_type=SetupStageId.RP_INTERACTION_CONTRACT.value,
        default_entry_types=["interaction_rule", "player_agency_rule"],
    ),
    SetupStageId.TRPG_RULES: SetupStageModule(
        stage_id=SetupStageId.TRPG_RULES,
        display_name="TRPG规则",
        draft_block_type=SetupStageId.TRPG_RULES.value,
        default_entry_types=["rule", "mechanic", "table"],
    ),
}


LONGFORM_STAGE_PLAN: tuple[SetupStageId, ...] = (
    SetupStageId.WORLD_BACKGROUND,
    SetupStageId.CHARACTER_DESIGN,
    SetupStageId.PLOT_BLUEPRINT,
    SetupStageId.WRITER_CONFIG,
    SetupStageId.WORKER_CONFIG,
    SetupStageId.OVERVIEW,
    SetupStageId.ACTIVATE,
)


MODE_STAGE_PLANS: dict[str, tuple[SetupStageId, ...]] = {
    "longform": LONGFORM_STAGE_PLAN,
    "roleplay": (
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.CHARACTER_DESIGN,
        SetupStageId.RP_INTERACTION_CONTRACT,
        SetupStageId.WRITER_CONFIG,
        SetupStageId.WORKER_CONFIG,
        SetupStageId.OVERVIEW,
        SetupStageId.ACTIVATE,
    ),
    "trpg": (
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.CHARACTER_DESIGN,
        SetupStageId.TRPG_RULES,
        SetupStageId.WRITER_CONFIG,
        SetupStageId.WORKER_CONFIG,
        SetupStageId.OVERVIEW,
        SetupStageId.ACTIVATE,
    ),
}


def get_stage_module(stage_id: SetupStageId) -> SetupStageModule:
    """Return the registered module for a canonical setup stage."""

    return SETUP_STAGE_MODULES[stage_id]


def get_mode_stage_plan(mode: str) -> SetupModeStagePlan:
    """Return the ordered setup stage plan for a story mode."""

    stage_ids = MODE_STAGE_PLANS.get(str(mode))
    if stage_ids is None:
        raise ValueError(f"Unsupported setup mode for stage plan: {mode}")
    return SetupModeStagePlan(mode=str(mode), stage_ids=list(stage_ids))


def is_setup_stage_id(value: str) -> bool:
    """Return whether a stored lifecycle id is a canonical setup stage id."""

    try:
        SetupStageId(value)
    except ValueError:
        return False
    return True
