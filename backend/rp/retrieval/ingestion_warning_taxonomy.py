"""Helpers for stable retrieval ingestion warning codes."""

from __future__ import annotations

import re
from collections.abc import Iterable

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _normalize_token(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "unknown"
    normalized = _SAFE_TOKEN_RE.sub("_", text)
    return normalized.strip("_") or "unknown"


def ingestion_warning(stage: str, code: str, *details: object) -> str:
    tokens = ["ingestion", _normalize_token(stage), _normalize_token(code)]
    tokens.extend(_normalize_token(detail) for detail in details if str(detail).strip())
    return ":".join(tokens)


def normalize_component_warnings(stage: str, warnings: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for warning in warnings:
        if not warning:
            continue
        parts = [part for part in str(warning).split(":") if part]
        if not parts:
            continue
        normalized.append(ingestion_warning(stage, parts[0], *parts[1:]))
    return normalized
