"""Deterministic source fingerprinting helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from rp.context_engineering.contracts import ContextArtifact, ContextSourceItem


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r"\s+", " ", str(text)).strip()


def canonical_source_item_payload(item: ContextSourceItem) -> dict[str, Any]:
    """Return the stable fingerprint payload for one source item."""

    return {
        "source_item_id": item.source_item_id,
        "source_family": item.source_family,
        "source_scope": item.source_scope,
        "sequence_index": item.sequence_index,
        "source_ref": item.source_ref,
        "text": _normalize_text(item.text),
        "payload": item.payload,
        "recovery_refs": list(item.recovery_refs),
    }


def fingerprint_source_items(items: Sequence[ContextSourceItem]) -> str:
    """Hash source items without estimates, timestamps, trace, or prior artifacts."""

    payload = [canonical_source_item_payload(item) for item in items]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_valid_prefix_artifact(
    *,
    previous_artifact: ContextArtifact,
    dropped_items: Sequence[ContextSourceItem],
) -> bool:
    """Return true when an artifact fingerprint matches a dropped prefix."""

    count = int(previous_artifact.source_item_count or 0)
    if count <= 0 or count > len(dropped_items):
        return False
    prefix = list(dropped_items[:count])
    return fingerprint_source_items(prefix) == previous_artifact.source_fingerprint
