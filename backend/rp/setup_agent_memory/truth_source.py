"""Accepted setup truth source adapter for session memory manifests."""

from __future__ import annotations

from typing import Any

from rp.services.setup_truth_index_service import SetupTruthIndexService

from .contracts import SetupSessionMemoryManifestItem
from .sources import join_search_text, make_freshness


class AcceptedTruthMemorySource:
    """Mirror committed truth-index rows as session-memory candidates."""

    source_kind = "accepted_truth"

    def __init__(
        self, truth_index_service: SetupTruthIndexService | None = None
    ) -> None:
        self._truth_index_service = truth_index_service or SetupTruthIndexService()

    def build_items(
        self, *, workspace, **kwargs: Any
    ) -> list[SetupSessionMemoryManifestItem]:
        index = self._truth_index_service.rebuild(workspace=workspace)
        items: list[SetupSessionMemoryManifestItem] = []
        for row in index.rows:
            if row.row_type not in {"entry", "section"}:
                continue
            payload = row.model_dump(mode="json", exclude_none=True)
            items.append(
                SetupSessionMemoryManifestItem(
                    ref=row.ref,
                    title=row.section_title or row.title,
                    summary=row.summary or row.preview_text,
                    source_kind="accepted_truth",
                    ref_kind=(
                        "setup_fact_section"
                        if row.row_type == "section"
                        else "setup_fact_entry"
                    ),
                    stage=row.stage_id.value,
                    block_type=row.entry_type or row.row_type,
                    tags=list(dict.fromkeys([row.stage_id.value, *row.tags])),
                    search_text=join_search_text(
                        [
                            row.ref,
                            row.stage_id.value,
                            row.semantic_path,
                            row.entry_type,
                            row.title,
                            row.display_label,
                            row.summary,
                            row.aliases,
                            row.tags,
                            row.section_title,
                            row.preview_text,
                        ]
                    ),
                    freshness=make_freshness(workspace=workspace, payload=payload),
                    metadata={
                        "commit_id": row.commit_id,
                        "row_type": row.row_type,
                        "entry_id": row.entry_id,
                        "section_id": row.section_id,
                        "semantic_path": row.semantic_path,
                    },
                )
            )
        return items
