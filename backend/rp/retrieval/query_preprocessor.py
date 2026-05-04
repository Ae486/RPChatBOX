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
    values = [
        str(item).strip()
        for item in raw
        if item is not None and not isinstance(item, bool) and str(item).strip()
    ]
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


_STRING_LIST_FILTER_KEYS = (
    "knowledge_collections",
    "mapped_targets",
    "materialization_kinds",
    "source_families",
    "source_types",
    "source_origins",
    "workspace_ids",
    "commit_ids",
    "scene_refs",
    "character_refs",
    "pov_character_refs",
    "foreshadow_refs",
    "foreshadow_statuses",
    "branch_ids",
    "canon_statuses",
)

_INT_LIST_FILTER_KEYS = ("chapter_indices",)


def _normalize_search_policy(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    policy = dict(raw)
    profile = policy.get("profile")
    if isinstance(profile, str):
        normalized_profile = profile.strip().lower()
        policy["profile"] = normalized_profile or "default"
    rerank = policy.get("rerank")
    if isinstance(rerank, str):
        normalized_rerank = rerank.strip().lower()
        policy["rerank"] = (
            normalized_rerank if normalized_rerank in {"auto", "on", "off"} else "auto"
        )
    context_budget = policy.get("context_budget")
    if isinstance(context_budget, dict):
        policy["context_budget"] = dict(context_budget)
    context = policy.get("context")
    if isinstance(context, dict):
        policy["context"] = dict(context)
    return policy


class DefaultQueryPreprocessor:
    """Apply stable, model-free normalization to retrieval queries."""

    def preprocess(self, query: RetrievalQuery) -> RetrievalQuery:
        filters = dict(query.filters or {})

        for filter_key in _STRING_LIST_FILTER_KEYS:
            if filter_key in filters:
                filters[filter_key] = _normalize_string_list(filters.get(filter_key))
        for filter_key in _INT_LIST_FILTER_KEYS:
            if filter_key in filters:
                filters[filter_key] = _normalize_int_list(filters.get(filter_key))
        if "search_policy" in filters:
            filters["search_policy"] = _normalize_search_policy(
                filters.get("search_policy")
            )
        intent = filters.get("intent")
        if isinstance(intent, str):
            normalized_intent = intent.strip().lower()
            filters["intent"] = (
                normalized_intent
                if normalized_intent
                in {
                    "fact_lookup",
                    "relation_lookup",
                    "broad_context",
                    "consistency_check",
                }
                else None
            )
        for boolean_filter_key in ("need_evidence", "need_relationship_view"):
            if boolean_filter_key in filters:
                filters[boolean_filter_key] = filters.get(boolean_filter_key) is True

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
