"""Provider-neutral serialization helpers for selected context sources."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rp.context_engineering.contracts import (
    ContextSection,
    ContextSourceItem,
    ContextStability,
)


def serialize_source_item_content(item: ContextSourceItem) -> str:
    """Serialize one model-visible item without leaking excluded surfaces."""

    if item.visibility != "model_visible":
        return ""
    if item.text is not None and str(item.text).strip():
        return str(item.text)
    if item.payload:
        return json.dumps(item.payload, ensure_ascii=False, sort_keys=True, default=str)
    return ""


def build_section_for_items(
    *,
    section_id: str,
    slot: str,
    title: str,
    items: Sequence[ContextSourceItem],
    stability: ContextStability,
) -> ContextSection:
    """Build a deterministic section from already-selected items."""

    content_parts = [
        serialize_source_item_content(item)
        for item in items
        if item.visibility == "model_visible"
    ]
    content = "\n\n".join(part for part in content_parts if part)
    return ContextSection(
        section_id=section_id,
        slot=slot,
        title=title,
        content=content,
        source_item_ids=[item.source_item_id for item in items],
        stability=stability,
    )
