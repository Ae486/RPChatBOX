"""Shared source helpers for SetupAgent session memory."""

from __future__ import annotations

from typing import Any, Protocol

from .contracts import (
    SetupSessionMemoryFreshness,
    SetupSessionMemoryManifestItem,
    SetupSessionMemorySourceKind,
)
from .fingerprints import fingerprint_payload


class SetupSessionMemorySource(Protocol):
    """Source adapter that emits small searchable manifest items."""

    source_kind: SetupSessionMemorySourceKind

    def build_items(
        self, *, workspace, **kwargs: Any
    ) -> list[SetupSessionMemoryManifestItem]: ...


def make_freshness(*, workspace, payload: Any) -> SetupSessionMemoryFreshness:
    return SetupSessionMemoryFreshness(
        workspace_version=getattr(workspace, "version", None),
        fingerprint=fingerprint_payload(payload),
        status="current",
    )


def join_search_text(parts: list[Any]) -> str:
    flat: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            flat.extend(str(item) for item in part if str(item or "").strip())
            continue
        if isinstance(part, dict):
            flat.extend(str(item) for item in part.values() if str(item or "").strip())
            continue
        text = str(part).strip()
        if text:
            flat.append(text)
    return " ".join(flat).lower()


def preview_text(value: Any, *, max_chars: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, dict):
        text = ", ".join(
            str(item).strip() for item in value.values() if str(item).strip()
        )
    else:
        text = str(value).strip()
    return text[:max_chars] if text else None
