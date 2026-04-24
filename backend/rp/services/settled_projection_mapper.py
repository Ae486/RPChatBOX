"""Mappings for Phase E3 settled projection slots."""

from __future__ import annotations


SETTLED_PROJECTION_SLOT_ORDER = [
    "foundation_digest",
    "blueprint_digest",
    "current_outline_digest",
    "recent_segment_digest",
    "current_state_digest",
]


def settled_projection_slots() -> list[str]:
    return list(SETTLED_PROJECTION_SLOT_ORDER)
