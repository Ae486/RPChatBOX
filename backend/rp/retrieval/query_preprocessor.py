"""Deterministic query preprocessing for retrieval requests."""

from __future__ import annotations

from collections.abc import Iterable

from rp.models.memory_crud import RetrievalQuery


def _dedupe_preserve_order(values: Iterable[object]) -> list[object]:
    seen: set[object] = set()
    ordered: list[object] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _normalize_string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    values = [str(item).strip() for item in raw if str(item).strip()]
    return [str(item) for item in _dedupe_preserve_order(values)]


def _normalize_int_list(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            values.append(item)
            continue
        if isinstance(item, str):
            normalized = item.strip()
            if not normalized:
                continue
            try:
                values.append(int(normalized))
            except ValueError:
                continue
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class DefaultQueryPreprocessor:
    """Apply stable, model-free normalization to retrieval queries."""

    def preprocess(self, query: RetrievalQuery) -> RetrievalQuery:
        filters = dict(query.filters or {})

        if "knowledge_collections" in filters:
            filters["knowledge_collections"] = _normalize_string_list(
                filters.get("knowledge_collections")
            )
        if "mapped_targets" in filters:
            filters["mapped_targets"] = _normalize_string_list(
                filters.get("mapped_targets")
            )
        if "materialization_kinds" in filters:
            filters["materialization_kinds"] = _normalize_string_list(
                filters.get("materialization_kinds")
            )
        if "source_families" in filters:
            filters["source_families"] = _normalize_string_list(
                filters.get("source_families")
            )
        if "chapter_indices" in filters:
            filters["chapter_indices"] = _normalize_int_list(
                filters.get("chapter_indices")
            )

        domain_path_prefix = filters.get("domain_path_prefix")
        if isinstance(domain_path_prefix, str):
            normalized_prefix = domain_path_prefix.strip()
            filters["domain_path_prefix"] = normalized_prefix or None

        normalized_story_id = query.story_id.strip() if query.story_id.strip() else "*"
        normalized_scope = (
            query.scope.strip()
            if isinstance(query.scope, str) and query.scope.strip()
            else query.scope
        )
        normalized_text = (
            query.text_query.strip()
            if isinstance(query.text_query, str)
            else query.text_query
        )

        return query.model_copy(
            update={
                "story_id": normalized_story_id,
                "scope": normalized_scope,
                "domains": list(_dedupe_preserve_order(query.domains)),
                "text_query": normalized_text or None,
                "filters": filters,
                "top_k": max(1, int(query.top_k)),
            }
        )
