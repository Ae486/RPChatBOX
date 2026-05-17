"""Service facade for SetupAgent session-scoped memory."""

from __future__ import annotations

from rp.agent_runtime.contracts import SetupDraftRefReadInput, SetupDraftRefReadResult
from rp.services.setup_truth_index_service import SetupTruthIndexService

from .contracts import (
    SetupSessionMemoryManifest,
    SetupSessionMemoryOpenResult,
    SetupSessionMemoryReadResult,
    SetupSessionMemorySearchFilters,
    SetupSessionMemorySearchResult,
)
from .manifest_builder import SetupSessionMemoryManifestBuilder
from .reader import DraftRefReader, SetupSessionMemoryReader
from .scorer import SetupSessionMemoryScorer


class SetupSessionMemoryService:
    """Build, search, and read session memory without owning durable truth."""

    def __init__(
        self,
        *,
        draft_ref_reader: DraftRefReader,
        truth_index_service: SetupTruthIndexService | None = None,
    ) -> None:
        self._truth_index_service = truth_index_service or SetupTruthIndexService()
        self._manifest_builder = SetupSessionMemoryManifestBuilder(
            truth_index_service=self._truth_index_service
        )
        self._scorer = SetupSessionMemoryScorer()
        self._reader = SetupSessionMemoryReader(
            draft_ref_reader=draft_ref_reader,
            truth_index_service=self._truth_index_service,
        )

    def build_manifest(
        self,
        *,
        workspace,
        context_packet=None,
        runtime_snapshot=None,
    ) -> SetupSessionMemoryManifest:
        return self._manifest_builder.build(
            workspace=workspace,
            context_packet=context_packet,
            runtime_snapshot=runtime_snapshot,
        )

    def search(
        self,
        *,
        workspace,
        query: str,
        filters: SetupSessionMemorySearchFilters | None = None,
        limit: int = 10,
        context_packet=None,
        runtime_snapshot=None,
    ) -> SetupSessionMemorySearchResult:
        manifest = self.build_manifest(
            workspace=workspace,
            context_packet=context_packet,
            runtime_snapshot=runtime_snapshot,
        )
        return SetupSessionMemorySearchResult(
            items=self._scorer.search(
                manifest=manifest,
                query=query,
                filters=filters,
                limit=limit,
            )
        )

    def read_refs(
        self,
        *,
        workspace,
        refs: list[str],
        detail: str = "summary",
        max_chars: int = 4000,
        context_packet=None,
        runtime_snapshot=None,
    ) -> SetupSessionMemoryReadResult:
        manifest = self.build_manifest(
            workspace=workspace,
            context_packet=context_packet,
            runtime_snapshot=runtime_snapshot,
        )
        return self._reader.read_refs(
            workspace=workspace,
            manifest=manifest,
            refs=refs,
            detail=detail,
            max_chars=max_chars,
        )

    def open_ref(
        self,
        *,
        workspace,
        ref: str,
        max_chars: int = 4000,
        context_packet=None,
        runtime_snapshot=None,
    ) -> SetupSessionMemoryOpenResult:
        manifest = self.build_manifest(
            workspace=workspace,
            context_packet=context_packet,
            runtime_snapshot=runtime_snapshot,
        )
        return self._reader.open_ref(
            workspace=workspace,
            manifest=manifest,
            ref=ref,
            max_chars=max_chars,
        )


def empty_draft_ref_reader(
    input_model: SetupDraftRefReadInput,
) -> SetupDraftRefReadResult:
    """Test/helper reader for service instances that only exercise manifest/search."""

    return SetupDraftRefReadResult(
        success=False,
        items=[],
        missing_refs=list(input_model.refs),
    )
