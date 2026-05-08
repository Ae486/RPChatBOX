"""SetupAgent stage SkillPack registry."""

from __future__ import annotations

from rp.agent_runtime.skill_packs.registry import (
    STAGE_SKILL_PACKS,
    SkillPackRecord,
    get_skill_pack_for_stage,
    load_registry,
    render_skill_pack,
)

__all__ = [
    "STAGE_SKILL_PACKS",
    "SkillPackRecord",
    "get_skill_pack_for_stage",
    "load_registry",
    "render_skill_pack",
]
