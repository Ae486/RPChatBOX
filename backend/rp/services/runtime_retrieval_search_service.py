"""Runtime LLM-facing retrieval search service.

This service owns the writer-first RAG tool boundary: callers provide a clean
query expression, while backend policy decides which memory sources to search
and how to serialize the results for model consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Any, Protocol

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import (
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalSearchResult,
)
from rp.models.retrieval_runtime_contracts import (
    RuntimeRetrievalResultItem,
    RuntimeRetrievalSearchInput,
    RuntimeRetrievalSearchOutput,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterial

DEFAULT_RUNTIME_RETRIEVAL_FINAL_TOP_K = 5


class _RuntimeRetrievalCardServiceProtocol(Protocol):
    async def search_recall_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchRecallInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]: ...

    async def search_archival_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchArchivalInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]: ...


@dataclass(frozen=True)
class RuntimeRetrievalSearchExecution:
    """Search output plus internal Runtime Workspace material side effects."""

    output: RuntimeRetrievalSearchOutput
    materials: list[RuntimeWorkspaceMaterial] = field(default_factory=list)
    miss_materials: list[RuntimeWorkspaceMaterial] = field(default_factory=list)


@dataclass(frozen=True)
class _RankedMaterial:
    material: RuntimeWorkspaceMaterial
    route_index: int
    route_rank: int
    fusion_score: float


class RuntimeRetrievalSearchService:
    """Compose recall and archival searches behind one clean RAG output."""

    def __init__(
        self,
        *,
        runtime_retrieval_card_service: _RuntimeRetrievalCardServiceProtocol,
        final_top_k: int = DEFAULT_RUNTIME_RETRIEVAL_FINAL_TOP_K,
    ) -> None:
        self._runtime_retrieval_card_service = runtime_retrieval_card_service
        self._final_top_k = max(1, int(final_top_k))

    async def search_for_writer(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: RuntimeRetrievalSearchInput,
        actor: str,
        attempt_index: int = 1,
    ) -> RuntimeRetrievalSearchExecution:
        """Search writer-visible runtime sources and return model-clean results."""

        normalized = RuntimeRetrievalSearchInput.model_validate(input_model)
        (
            recall_result,
            recall_cards,
            recall_miss,
        ) = await self._runtime_retrieval_card_service.search_recall_to_cards(
            identity=identity,
            input_model=MemorySearchRecallInput(
                query=self._effective_query(normalized),
                scope="story",
                top_k=self._final_top_k,
            ),
            actor=actor,
            attempt_index=attempt_index,
        )
        (
            archival_result,
            archival_cards,
            archival_miss,
        ) = await self._runtime_retrieval_card_service.search_archival_to_cards(
            identity=identity,
            input_model=MemorySearchArchivalInput(
                query=self._effective_query(normalized),
                top_k=self._final_top_k,
            ),
            actor=actor,
            attempt_index=attempt_index,
        )
        warnings = self._dedupe_text(
            [
                *list(getattr(recall_result, "warnings", [])),
                *list(getattr(archival_result, "warnings", [])),
            ]
        )
        materials = [*recall_cards, *archival_cards]
        ranked = self._rank_materials(
            route_materials=[recall_cards, archival_cards],
        )
        results = [
            self._result_item_from_material(item.material)
            for item in ranked[: self._final_top_k]
        ]
        if not results:
            warnings = self._dedupe_text([*warnings, "runtime_retrieval_no_results"])
        return RuntimeRetrievalSearchExecution(
            output=RuntimeRetrievalSearchOutput(
                query=normalized.query,
                results=results,
                warnings=warnings,
            ),
            materials=materials,
            miss_materials=[
                material
                for material in (recall_miss, archival_miss)
                if material is not None
            ],
        )

    @staticmethod
    def _effective_query(input_model: RuntimeRetrievalSearchInput) -> str:
        parts = [
            input_model.query,
            *input_model.lexical_anchors,
            *input_model.semantic_predicates,
        ]
        return " ".join(RuntimeRetrievalSearchService._dedupe_text(parts))

    @staticmethod
    def _rank_materials(
        *,
        route_materials: list[list[RuntimeWorkspaceMaterial]],
    ) -> list[_RankedMaterial]:
        ranked: list[_RankedMaterial] = []
        for route_index, materials in enumerate(route_materials):
            for route_rank, material in enumerate(materials, start=1):
                ranked.append(
                    _RankedMaterial(
                        material=material,
                        route_index=route_index,
                        route_rank=route_rank,
                        fusion_score=1.0 / (60.0 + route_rank),
                    )
                )
        return sorted(
            ranked,
            key=lambda item: (
                -item.fusion_score,
                item.route_index,
                item.route_rank,
                item.material.material_id,
            ),
        )

    @classmethod
    def _result_item_from_material(
        cls,
        material: RuntimeWorkspaceMaterial,
    ) -> RuntimeRetrievalResultItem:
        payload = dict(material.payload or {})
        metadata = payload.get("metadata")
        metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
        summary = cls._stored_summary(payload=payload)
        text = cls._first_text(
            payload.get("text"),
            payload.get("excerpt"),
            summary,
            payload.get("summary"),
        )
        excerpt = None if summary is not None else cls._bounded_text(text)
        return RuntimeRetrievalResultItem(
            result_id=str(material.short_id or material.material_id),
            title=cls._first_text(
                payload.get("title"),
                metadata_dict.get("entry_title"),
                metadata_dict.get("document_title"),
            ),
            summary=summary,
            excerpt=excerpt,
            text=text,
            section=cls._first_text(
                metadata_dict.get("section_title"),
                metadata_dict.get("retrieval_role"),
            ),
        )

    @staticmethod
    def _stored_summary(*, payload: dict[str, Any]) -> str | None:
        if not payload.get("summary_source"):
            return None
        summary = payload.get("summary")
        if not isinstance(summary, str):
            return None
        return summary.strip() or None

    @staticmethod
    def _first_text(*values: object) -> str | None:
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if normalized:
                return normalized
        return None

    @staticmethod
    def _bounded_text(value: str | None, *, limit: int = 600) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip()

    @staticmethod
    def _dedupe_text(values: Sequence[object]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized
