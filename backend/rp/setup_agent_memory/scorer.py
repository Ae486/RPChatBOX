"""Deterministic lexical scorer for setup-session memory."""

from __future__ import annotations

import re

from .contracts import (
    SetupSessionMemoryHit,
    SetupSessionMemoryManifest,
    SetupSessionMemoryManifestItem,
    SetupSessionMemorySearchFilters,
)
from .sources import preview_text


class SetupSessionMemoryScorer:
    """Rank manifest refs without embeddings, reranking, or large payloads."""

    _SOURCE_ORDER = {
        "editable_draft": 0,
        "accepted_truth": 1,
    }
    _REF_KIND_ORDER = {
        "setup_fact_entry": 0,
        "setup_fact_section": 1,
    }

    def search(
        self,
        *,
        manifest: SetupSessionMemoryManifest,
        query: str,
        filters: SetupSessionMemorySearchFilters | None = None,
        limit: int = 10,
    ) -> list[SetupSessionMemoryHit]:
        filters = filters or SetupSessionMemorySearchFilters()
        tokens = self._tokens(query)
        scored: list[tuple[int, SetupSessionMemoryManifestItem, str]] = []
        for item in manifest.items:
            if not self._matches_filters(item=item, filters=filters):
                continue
            score, reason = self._score_item(item=item, tokens=tokens)
            if tokens and score <= 0:
                continue
            scored.append((score, item, reason))
        scored.sort(
            key=lambda row: (
                -row[0],
                self._SOURCE_ORDER.get(row[1].source_kind, 99),
                self._REF_KIND_ORDER.get(row[1].ref_kind, 99),
                row[1].stage or "",
                row[1].ref,
            )
        )
        bounded_limit = max(1, min(int(limit or 10), 50))
        return [
            SetupSessionMemoryHit(
                ref=item.ref,
                title=item.title,
                path=self._display_path(item),
                scope=("section" if item.ref_kind == "setup_fact_section" else "entry"),
                navigation_summary=preview_text(item.summary, max_chars=500),
            )
            for score, item, reason in scored[:bounded_limit]
        ]

    @staticmethod
    def _tokens(query: str) -> list[str]:
        return [
            token
            for token in re.split(r"[\s\.:/_#-]+", str(query or "").lower())
            if token
        ]

    @staticmethod
    def _matches_filters(
        *,
        item: SetupSessionMemoryManifestItem,
        filters: SetupSessionMemorySearchFilters,
    ) -> bool:
        if filters.source_kinds and item.source_kind not in filters.source_kinds:
            return False
        if filters.ref_kinds and item.ref_kind not in filters.ref_kinds:
            return False
        if filters.stages and str(item.stage or "") not in set(filters.stages):
            return False
        if filters.block_types and str(item.block_type or "") not in set(
            filters.block_types
        ):
            return False
        return True

    @staticmethod
    def _score_item(
        *,
        item: SetupSessionMemoryManifestItem,
        tokens: list[str],
    ) -> tuple[int, str]:
        if not tokens:
            return 1, "empty_query"
        title = str(item.title or "").lower()
        summary = str(item.summary or "").lower()
        ref = item.ref.lower()
        tags = " ".join(item.tags).lower()
        score = 0
        reasons: list[str] = []
        for token in tokens:
            matched = False
            if token in ref:
                score += 4
                matched = True
                reasons.append(f"ref:{token}")
            if token in title:
                score += 6
                matched = True
                reasons.append(f"title:{token}")
            if token in tags:
                score += 3
                matched = True
                reasons.append(f"tag:{token}")
            if token in summary:
                score += 2
                matched = True
                reasons.append(f"summary:{token}")
            if token in item.search_text and not matched:
                score += 1
                reasons.append(f"text:{token}")
        return score, ",".join(dict.fromkeys(reasons)) or "no_match"

    @staticmethod
    def _display_path(item: SetupSessionMemoryManifestItem) -> str | None:
        semantic_path = str(item.metadata.get("semantic_path") or "").strip()
        if semantic_path:
            return " / ".join(part for part in semantic_path.split(".") if part)
        parts = [item.stage, item.block_type, item.title]
        text = " / ".join(str(part) for part in parts if str(part or "").strip())
        return text or None
