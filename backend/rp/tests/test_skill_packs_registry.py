"""Unit tests for SetupAgent stage SkillPack registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from rp.agent_runtime.skill_packs import (
    STAGE_SKILL_PACKS,
    SkillPackRecord,
    get_skill_pack_for_stage,
    load_registry,
    render_skill_pack,
)
from rp.models.setup_stage import SetupStageId


REQUIRED_BODY_SECTIONS = (
    "## Specialist hat",
    "## Objectives",
    "## Forbidden",
    "## Facilitation principles",
    "## Recommended content skeleton",
    "## Clarification templates",
)


def test_character_design_skill_pack_is_registered():
    record = STAGE_SKILL_PACKS.get(SetupStageId.CHARACTER_DESIGN)
    assert record is not None
    assert isinstance(record, SkillPackRecord)
    assert record.name == "character-design.v1"
    assert record.stage_id is SetupStageId.CHARACTER_DESIGN
    assert record.description.strip()
    assert record.body.strip()


def test_get_skill_pack_for_stage_returns_record_for_character_design():
    record = get_skill_pack_for_stage(SetupStageId.CHARACTER_DESIGN)
    assert record is not None
    assert record.stage_id is SetupStageId.CHARACTER_DESIGN


def test_get_skill_pack_for_stage_returns_none_for_unregistered_stage():
    assert get_skill_pack_for_stage(SetupStageId.WORLD_BACKGROUND) is None
    assert get_skill_pack_for_stage(SetupStageId.PLOT_BLUEPRINT) is None
    assert get_skill_pack_for_stage(None) is None


def test_render_skill_pack_wraps_body_with_marker_block():
    record = STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]
    rendered = render_skill_pack(record)

    assert rendered.startswith("[Stage Skill Pack: character-design.v1]")
    assert rendered.endswith("[/Stage Skill Pack]")
    assert "You are" not in rendered


@pytest.mark.parametrize("section_header", REQUIRED_BODY_SECTIONS)
def test_render_skill_pack_contains_required_section_headers(section_header):
    record = STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]
    rendered = render_skill_pack(record)
    assert section_header in rendered


def test_render_skill_pack_contains_user_authority_forbidden_clauses():
    record = STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]
    rendered = render_skill_pack(record)

    assert "Stage advancement and commit are user-driven through the UI commit button" in rendered
    assert 'Do not declare the stage "ready" or "done"' in rendered


def test_render_skill_pack_contains_signature_skeleton_keywords():
    record = STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]
    rendered = render_skill_pack(record)

    assert "motivation.real" in rendered
    assert "world_fit" in rendered
    assert "extras" in rendered


def test_render_skill_pack_preserves_chinese_clarification_templates():
    record = STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]
    rendered = render_skill_pack(record)

    assert "角色 X 表面上想要 Y，但他真正怕失去的是什么？" in rendered
    assert "角色 X 与 Y 的关系" in rendered


def test_load_registry_skips_directory_without_skill_md(tmp_path: Path):
    (tmp_path / "empty_pack").mkdir()
    registry = load_registry(tmp_path)
    assert registry == {}


def test_load_registry_warns_and_skips_invalid_frontmatter(tmp_path, caplog):
    pack_dir = tmp_path / "broken_pack"
    pack_dir.mkdir()
    (pack_dir / "SKILL.md").write_text(
        "no frontmatter at all\n## body\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        registry = load_registry(tmp_path)

    assert registry == {}
    assert any("broken_pack" in record.message for record in caplog.records)


def test_load_registry_warns_and_skips_unknown_stage_id(tmp_path, caplog):
    pack_dir = tmp_path / "ghost_stage"
    pack_dir.mkdir()
    (pack_dir / "SKILL.md").write_text(
        "---\n"
        "name: ghost.v1\n"
        "stage_id: not_a_real_stage\n"
        "description: invalid\n"
        "---\n"
        "## Specialist hat\nbody\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        registry = load_registry(tmp_path)

    assert registry == {}
    assert any("ghost_stage" in record.message for record in caplog.records)


def test_load_registry_parses_valid_pack_with_block_description(tmp_path):
    pack_dir = tmp_path / "world_background"
    pack_dir.mkdir()
    (pack_dir / "SKILL.md").write_text(
        "---\n"
        "name: world-background.test\n"
        "stage_id: world_background\n"
        "description: |\n"
        "  Multi-line description.\n"
        "  Second line.\n"
        "---\n"
        "## Specialist hat\nA worldbuilder.\n",
        encoding="utf-8",
    )

    registry = load_registry(tmp_path)
    record = registry.get(SetupStageId.WORLD_BACKGROUND)
    assert record is not None
    assert record.name == "world-background.test"
    assert "Multi-line description." in record.description
    assert "Second line." in record.description
    assert record.body.startswith("## Specialist hat")
