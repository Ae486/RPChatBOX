"""Manifest builder for SetupAgent session memory."""

from __future__ import annotations

from rp.services.setup_truth_index_service import SetupTruthIndexService

from .contracts import SetupSessionMemoryManifest, SetupSessionMemoryManifestItem
from .draft_source import EditableDraftMemorySource
from .truth_source import AcceptedTruthMemorySource


class SetupSessionMemoryManifestBuilder:
    """Build a deterministic manifest from current setup-session sources."""

    def __init__(
        self,
        *,
        truth_index_service: SetupTruthIndexService | None = None,
    ) -> None:
        self._sources = (
            EditableDraftMemorySource(),
            AcceptedTruthMemorySource(truth_index_service),
        )

    def build(
        self,
        *,
        workspace,
        context_packet=None,
        runtime_snapshot=None,
    ) -> SetupSessionMemoryManifest:
        items: list[SetupSessionMemoryManifestItem] = []
        for source in self._sources:
            items.extend(
                source.build_items(
                    workspace=workspace,
                    context_packet=context_packet,
                    runtime_snapshot=runtime_snapshot,
                )
            )
        return SetupSessionMemoryManifest(
            workspace_id=workspace.workspace_id,
            workspace_version=getattr(workspace, "version", None),
            items=sorted(items, key=self._sort_key),
        )

    @staticmethod
    def _sort_key(item: SetupSessionMemoryManifestItem) -> tuple[int, str, str]:
        source_order = {
            "editable_draft": 0,
            "accepted_truth": 1,
        }
        return (source_order.get(item.source_kind, 99), item.stage or "", item.ref)
