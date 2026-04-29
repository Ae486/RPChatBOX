"""Build a compact RAG-oriented view from retrieval hits."""

from __future__ import annotations

import time
from typing import Any

from rp.models.memory_crud import RetrievalSearchResult

from .context_rendering import build_rag_excerpt


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _budget_from_trace(result: RetrievalSearchResult) -> dict[str, Any]:
    if result.trace is None:
        return {}
    filters_applied = dict(result.trace.filters_applied or {})
    filters = filters_applied.get("filters")
    if not isinstance(filters, dict):
        return {}
    policy = filters.get("search_policy")
    if not isinstance(policy, dict):
        return {}
    context_budget = policy.get("context_budget")
    return dict(context_budget) if isinstance(context_budget, dict) else {}


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _token_estimate(*, metadata: dict, text: str) -> int:
    metadata_tokens = _positive_int(metadata.get("token_count"))
    if metadata_tokens is not None:
        return metadata_tokens
    return max(1, len(text.split()))


def _budget_limit_map(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    limits: dict[str, int] = {}
    for key, value in raw.items():
        limit = _positive_int(value)
        if limit is not None:
            limits[str(key)] = limit
    return limits


class RagContextBuilder:
    """Keep Phase B rag context thin and chunk-centric."""

    def build(self, result: RetrievalSearchResult) -> RetrievalSearchResult:
        started = time.perf_counter()
        budget = _budget_from_trace(result)
        max_tokens = _positive_int(budget.get("max_tokens"))
        source_family_limits = _budget_limit_map(budget.get("per_source_family"))
        domain_limits = _budget_limit_map(budget.get("per_domain"))
        used_tokens = 0
        used_source_family_tokens: dict[str, int] = {}
        used_domain_tokens: dict[str, int] = {}
        seen_assets: set[str] = set()
        compact_hits = []
        selected_trace: list[dict[str, object]] = []
        excluded_trace: list[dict[str, object]] = []
        for hit in result.hits:
            metadata = dict(hit.metadata)
            asset_id = str(metadata.get("asset_id") or "")
            key = asset_id or hit.hit_id
            if key in seen_assets:
                excluded_trace.append({"hit_id": hit.hit_id, "reason": "duplicate_asset"})
                continue
            token_estimate = _token_estimate(metadata=metadata, text=hit.excerpt_text)
            source_family = str(metadata.get("source_family") or "")
            domain = str(metadata.get("domain") or hit.domain.value or "")
            if max_tokens is not None and used_tokens + token_estimate > max_tokens:
                excluded_trace.append({"hit_id": hit.hit_id, "reason": "token_budget"})
                continue
            source_family_limit = source_family_limits.get(source_family)
            if (
                source_family_limit is not None
                and used_source_family_tokens.get(source_family, 0) + token_estimate
                > source_family_limit
            ):
                excluded_trace.append(
                    {"hit_id": hit.hit_id, "reason": "source_family_budget"}
                )
                continue
            domain_limit = domain_limits.get(domain)
            if (
                domain_limit is not None
                and used_domain_tokens.get(domain, 0) + token_estimate > domain_limit
            ):
                excluded_trace.append({"hit_id": hit.hit_id, "reason": "domain_budget"})
                continue
            seen_assets.add(key)
            used_tokens += token_estimate
            if source_family:
                used_source_family_tokens[source_family] = (
                    used_source_family_tokens.get(source_family, 0) + token_estimate
                )
            if domain:
                used_domain_tokens[domain] = used_domain_tokens.get(domain, 0) + token_estimate
            excerpt, header_lines, normalized_summary = build_rag_excerpt(
                context_header=str(metadata.get("context_header") or "") or None,
                title=str(metadata.get("title") or metadata.get("document_title") or "") or None,
                domain_path=str(metadata.get("domain_path") or "") or None,
                source_ref=str(metadata.get("source_ref") or "") or None,
                document_summary=str(metadata.get("document_summary") or "") or None,
                page_no=metadata.get("page_no"),
                page_label=metadata.get("page_label"),
                image_caption=str(metadata.get("image_caption") or "") or None,
                snippet=hit.excerpt_text,
            )
            compact_hits.append(
                hit.model_copy(
                    update={
                        "excerpt_text": excerpt,
                        "metadata": {
                            **metadata,
                            "result_kind": "rag",
                            "rag_context_header": " | ".join(header_lines),
                            "rag_document_summary": normalized_summary,
                        },
                    }
                )
            )
            selected_trace.append(
                {
                    "hit_id": hit.hit_id,
                    "source_family": source_family or None,
                    "domain": domain or None,
                    "estimated_tokens": token_estimate,
                    "reason": "within_budget",
                }
            )

        trace = result.trace
        if trace is not None:
            details = dict(trace.details or {})
            details["context_budget"] = {
                "max_tokens": max_tokens,
                "selected": selected_trace,
                "excluded": excluded_trace,
            }
            trace = trace.model_copy(
                update={
                    "result_kind": "rag",
                    "returned_count": len(compact_hits),
                    "pipeline_stages": _dedupe_preserve_order(
                        [*(trace.pipeline_stages or []), "rag_context_builder"]
                    ),
                    "timings": {
                        **dict(trace.timings or {}),
                        "rag_context_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                    "details": details,
                }
            )
        return result.model_copy(update={"hits": compact_hits, "trace": trace})
