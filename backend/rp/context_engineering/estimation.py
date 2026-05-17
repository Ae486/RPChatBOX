"""Deterministic approximate token estimation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from rp.context_engineering.contracts import ContextSourceItem
from rp.context_engineering.policies import DEFAULT_CONTEXT_ESTIMATE_CHARS_PER_TOKEN


def estimate_text_tokens(
    text: str | None,
    *,
    chars_per_token: int = DEFAULT_CONTEXT_ESTIMATE_CHARS_PER_TOKEN,
) -> int:
    """Estimate text tokens with a deterministic ceil(chars / N) heuristic."""

    if not text:
        return 0
    divisor = max(int(chars_per_token or DEFAULT_CONTEXT_ESTIMATE_CHARS_PER_TOKEN), 1)
    return int(math.ceil(len(text) / divisor))


def estimate_payload_tokens(
    payload: Mapping[str, Any],
    *,
    chars_per_token: int = DEFAULT_CONTEXT_ESTIMATE_CHARS_PER_TOKEN,
) -> int:
    """Estimate structured payload tokens using sorted JSON."""

    if not payload:
        return 0
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return estimate_text_tokens(raw, chars_per_token=chars_per_token)


def estimate_source_item_tokens(item: ContextSourceItem) -> int:
    """Estimate a source item, respecting adapter-provided estimates first."""

    if item.estimated_tokens is not None:
        return max(int(item.estimated_tokens), 0)
    return estimate_text_tokens(item.text) + estimate_payload_tokens(item.payload)


def estimate_source_items_tokens(items: Sequence[ContextSourceItem]) -> int:
    """Sum approximate token estimates for a list of source items."""

    return sum(estimate_source_item_tokens(item) for item in items)
