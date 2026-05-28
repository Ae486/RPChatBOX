"""Shared validation policy for story turn commands."""

from __future__ import annotations

from rp.models.story_runtime import LongformChapterPhase, LongformTurnCommandKind

_PHASE_RULES: dict[LongformChapterPhase, set[LongformTurnCommandKind]] = {
    LongformChapterPhase.OUTLINE_DRAFTING: {
        LongformTurnCommandKind.GENERATE_OUTLINE,
        LongformTurnCommandKind.DISCUSS_OUTLINE,
    },
    LongformChapterPhase.OUTLINE_REVIEW: {
        LongformTurnCommandKind.DISCUSS_OUTLINE,
        LongformTurnCommandKind.ACCEPT_OUTLINE,
    },
    LongformChapterPhase.SEGMENT_DRAFTING: {
        LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        LongformTurnCommandKind.DISCUSS_OUTLINE,
        LongformTurnCommandKind.COMPLETE_CHAPTER,
    },
    LongformChapterPhase.SEGMENT_REVIEW: {
        LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        LongformTurnCommandKind.DISCUSS_OUTLINE,
    },
    LongformChapterPhase.CHAPTER_REVIEW: {
        LongformTurnCommandKind.COMPLETE_CHAPTER,
        LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        LongformTurnCommandKind.DISCUSS_OUTLINE,
    },
    LongformChapterPhase.CHAPTER_COMPLETED: set(),
}


def validate_story_command(
    *,
    phase: LongformChapterPhase,
    command_kind: LongformTurnCommandKind,
) -> None:
    allowed = _PHASE_RULES.get(phase, set())
    if (
        command_kind == LongformTurnCommandKind.COMPLETE_CHAPTER
        and phase == LongformChapterPhase.SEGMENT_DRAFTING
    ):
        return
    if command_kind not in allowed:
        raise ValueError(
            f"Command {command_kind.value} is not allowed during phase {phase.value}"
        )
