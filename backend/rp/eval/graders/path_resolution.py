"""Shared path resolution helpers for eval graders."""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"([^\[\]]+)|\[(\-?\d+)\]")


def _select_source_payload(
    source: str,
    *,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> Any:
    mapping = {
        "runtime_result": runtime_result,
        "runtime_events": runtime_events,
        "workspace_truth": workspace_after or {},
        "workspace_before": workspace_before or {},
        "graph_debug": graph_debug or {},
        "activation_result": runtime_result,
        "retrieval_result": runtime_result,
        "retrieval_truth": workspace_after or {},
        "session_truth": workspace_after or {},
    }
    return mapping.get(source, {})


def _resolve_path(source_payload: Any, path: str) -> tuple[Any, bool]:
    current = source_payload
    for segment in path.split("."):
        if segment == "":
            continue
        for name, index in _iter_segment_tokens(segment):
            if name is not None:
                if isinstance(current, dict) and name in current:
                    current = current[name]
                else:
                    return None, False
            elif index is not None:
                if not isinstance(current, list):
                    return None, False
                try:
                    current = current[index]
                except IndexError:
                    return None, False
    return current, True


def _iter_segment_tokens(segment: str):
    for name, index in _TOKEN_RE.findall(segment):
        if name:
            yield name, None
        else:
            yield None, int(index)
