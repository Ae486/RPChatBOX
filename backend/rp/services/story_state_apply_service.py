"""Apply specialist patch proposals into the authoritative state map."""

from __future__ import annotations

from typing import Any


class StoryStateApplyService:
    """Minimal runtime state applier for longform MVP."""

    _ALLOWED_KEYS = {
        "chapter_digest",
        "narrative_progress",
        "timeline_spine",
        "active_threads",
        "foreshadow_registry",
        "character_state_digest",
    }

    def apply(
        self,
        *,
        state_map: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(state_map)
        for key, value in patch.items():
            if key not in self._ALLOWED_KEYS:
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**dict(merged.get(key) or {}), **value}
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = [*list(merged.get(key) or []), *value]
            else:
                merged[key] = value
        return merged
