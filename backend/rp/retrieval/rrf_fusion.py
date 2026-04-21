"""Reciprocal rank fusion helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def reciprocal_rank_fusion(
    rankings: list[list[dict[str, Any]]],
    *,
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    merged: dict[str, dict[str, Any]] = {}

    for ranking in rankings:
        for index, item in enumerate(ranking, start=1):
            key = str(item["hit_id"])
            scores[key] += 1.0 / (k + index)
            existing = merged.get(key)
            if existing is None or float(item.get("score") or 0.0) > float(existing.get("score") or 0.0):
                merged[key] = dict(item)

    for key, value in merged.items():
        value["score"] = scores[key]

    return sorted(merged.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)
