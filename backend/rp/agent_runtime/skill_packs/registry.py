"""SkillPack registry for SetupAgent stage-local prompt prose.

Each SkillPack is a leaf directory under ``skill_packs/`` containing one
``SKILL.md`` file with YAML-like frontmatter delimited by ``---`` markers
followed by a markdown body. The registry is loaded once at import time
and keyed by ``SetupStageId``. SkillPacks intentionally never carry tool
whitelists; tool scope is owned by ``build_setup_agent_tool_scope``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from rp.models.setup_stage import SetupStageId

logger = logging.getLogger(__name__)


_FRONTMATTER_DELIMITER = "---"
_REQUIRED_FRONTMATTER_KEYS = ("name", "stage_id", "description")
_SKILL_FILENAME = "SKILL.md"


class SkillPackRecord(BaseModel):
    """In-memory representation of a parsed SKILL.md file."""

    model_config = ConfigDict(extra="forbid")

    name: str
    stage_id: SetupStageId
    description: str = ""
    body: str


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return ``(frontmatter_block, body)`` for a SKILL.md document.

    Raises ``ValueError`` when the leading ``---`` markers are missing.
    """

    stripped = text.lstrip("﻿")
    if not stripped.startswith(_FRONTMATTER_DELIMITER):
        raise ValueError("missing leading frontmatter delimiter")
    remainder = stripped[len(_FRONTMATTER_DELIMITER) :]
    if remainder.startswith("\r\n"):
        remainder = remainder[2:]
    elif remainder.startswith("\n"):
        remainder = remainder[1:]
    else:
        raise ValueError("frontmatter delimiter must be followed by a newline")

    closing = re.search(r"(?m)^---\s*$", remainder)
    if closing is None:
        raise ValueError("missing closing frontmatter delimiter")

    frontmatter_block = remainder[: closing.start()]
    body = remainder[closing.end() :]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return frontmatter_block, body


def _parse_frontmatter(block: str) -> dict[str, str]:
    """Parse the minimal ``key: value`` / ``key: |`` frontmatter dialect."""

    result: dict[str, str] = {}
    current_key: str | None = None
    block_lines: list[str] = []
    block_indent: int | None = None

    def _flush_block() -> None:
        nonlocal current_key, block_lines, block_indent
        if current_key is None:
            return
        joined = "\n".join(block_lines).rstrip()
        result[current_key] = joined
        current_key = None
        block_lines = []
        block_indent = None

    for raw_line in block.splitlines():
        if current_key is not None:
            stripped = raw_line.lstrip(" \t")
            indent = len(raw_line) - len(stripped)
            if not stripped:
                block_lines.append("")
                continue
            if block_indent is None:
                if indent == 0:
                    _flush_block()
                else:
                    block_indent = indent
                    block_lines.append(stripped)
                    continue
            if indent >= block_indent:
                block_lines.append(raw_line[block_indent:])
                continue
            _flush_block()

        line = raw_line.rstrip()
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {raw_line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"empty frontmatter key in line: {raw_line!r}")
        if value == "|":
            current_key = key
            block_lines = []
            block_indent = None
            continue
        result[key] = value

    _flush_block()
    return result


def _build_record(pack_dir: Path) -> SkillPackRecord | None:
    skill_path = pack_dir / _SKILL_FILENAME
    if not skill_path.is_file():
        return None
    try:
        text = skill_path.read_text(encoding="utf-8")
        frontmatter_block, body = _split_frontmatter(text)
        frontmatter = _parse_frontmatter(frontmatter_block)
        for key in _REQUIRED_FRONTMATTER_KEYS:
            if not frontmatter.get(key):
                raise ValueError(f"missing required frontmatter key: {key}")
        stage_value = frontmatter["stage_id"]
        try:
            stage_id = SetupStageId(stage_value)
        except ValueError as exc:
            raise ValueError(f"unknown stage_id: {stage_value!r}") from exc
        return SkillPackRecord(
            name=frontmatter["name"],
            stage_id=stage_id,
            description=frontmatter.get("description", ""),
            body=body.strip(),
        )
    except Exception:
        logger.warning(
            "Skipping SkillPack at %s: failed to parse SKILL.md",
            pack_dir,
            exc_info=True,
        )
        return None


def load_registry(
    base_dir: Path | None = None,
) -> dict[SetupStageId, SkillPackRecord]:
    """Scan ``base_dir`` for SkillPack directories and return the registry.

    Defaults to the directory containing this module so import-time loading
    finds the on-disk packs without further configuration.
    """

    root = base_dir if base_dir is not None else Path(__file__).resolve().parent
    if not root.is_dir():
        return {}

    registry: dict[SetupStageId, SkillPackRecord] = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        record = _build_record(child)
        if record is None:
            continue
        if record.stage_id in registry:
            logger.warning(
                "Duplicate SkillPack for stage %s at %s; keeping first",
                record.stage_id.value,
                child,
            )
            continue
        registry[record.stage_id] = record
    return registry


STAGE_SKILL_PACKS: dict[SetupStageId, SkillPackRecord] = load_registry()


def render_skill_pack(record: SkillPackRecord) -> str:
    """Render one SkillPack record as a ``[Stage Skill Pack: ...]`` block."""

    return (
        f"[Stage Skill Pack: {record.name}]\n{record.body.strip()}\n[/Stage Skill Pack]"
    )


def get_skill_pack_for_stage(
    stage_id: SetupStageId | None,
) -> SkillPackRecord | None:
    """Return the SkillPack registered for ``stage_id`` if any."""

    if stage_id is None:
        return None
    return STAGE_SKILL_PACKS.get(stage_id)
