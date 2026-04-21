"""Unified retrieval broker for RP memory reads."""

from __future__ import annotations

from time import perf_counter
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProvenanceResult,
    RetrievalQuery,
    RetrievalSearchResult,
    StateReadResult,
    StateReadResultItem,
    SummaryEntry,
    SummaryReadResult,
    VersionListResult,
)
from rp.services.retrieval_service import RetrievalService
from services.database import get_engine


class RetrievalBroker:
    """Route memory.search_* to the retrieval-core while keeping other surfaces stable."""

    def __init__(
        self,
        *,
        default_story_id: str | None = None,
        retrieval_service_factory=None,
    ) -> None:
        self._default_story_id = default_story_id
        self._retrieval_service_factory = retrieval_service_factory or (lambda session: RetrievalService(session))

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        items: list[StateReadResultItem] = []
        refs = input_model.refs or [
            ObjectRef(
                object_id=f"{input_model.domain.value}.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=input_model.domain,
                domain_path=f"{input_model.domain.value}.current",
                scope=input_model.scope,
                revision=1,
            )
        ]
        for ref in refs:
            items.append(
                StateReadResultItem(
                    object_ref=ref,
                    data={
                        "object_id": ref.object_id,
                        "layer": ref.layer.value,
                        "domain": ref.domain.value,
                        "domain_path": ref.domain_path,
                        "scope": ref.scope,
                        "revision": ref.revision or 1,
                        "content": "State retrieval remains out of retrieval-core scope in Phase B",
                    },
                )
            )
        return StateReadResult(
            items=items,
            version_refs=[f"{item.object_ref.object_id}@{item.object_ref.revision or 1}" for item in items],
        )

    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult:
        items: list[SummaryEntry] = []
        if input_model.summary_ids:
            for summary_id in input_model.summary_ids:
                domain = self._domain_for_summary_id(summary_id)
                items.append(
                    SummaryEntry(
                        summary_id=summary_id,
                        domain=domain,
                        domain_path=summary_id,
                        summary_text=f"Summary projection for {summary_id} is not persisted yet",
                        metadata={"scope": input_model.scope, "route": "phase_b_placeholder"},
                    )
                )
        else:
            for domain in input_model.domains:
                summary_id = f"{domain.value}.current"
                items.append(
                    SummaryEntry(
                        summary_id=summary_id,
                        domain=domain,
                        domain_path=summary_id,
                        summary_text=f"Summary projection for {domain.value} is not persisted yet",
                        metadata={"scope": input_model.scope, "route": "phase_b_placeholder"},
                    )
                )
        return SummaryReadResult(items=items)

    async def search_recall(
        self,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        query = self._build_query(
            query_kind="recall",
            text_query=input_model.query,
            scope=input_model.scope,
            domains=input_model.domains,
            top_k=input_model.top_k,
            filters=input_model.filters,
        )
        return await self._search(query, search_kind="chunks")

    async def search_archival(
        self,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        filters = dict(input_model.filters)
        if input_model.knowledge_collections:
            filters["knowledge_collections"] = list(input_model.knowledge_collections)
        query = self._build_query(
            query_kind="archival",
            text_query=input_model.query,
            scope=None,
            domains=input_model.domains,
            top_k=input_model.top_k,
            filters=filters,
        )
        return await self._search(query, search_kind="chunks")

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        current_ref = (
            f"{input_model.target_ref.object_id}@{input_model.target_ref.revision or 1}"
        )
        versions = [current_ref]
        if input_model.include_audit:
            versions.append(f"{input_model.target_ref.object_id}@0")
        return VersionListResult(versions=versions, current_ref=current_ref)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        return ProvenanceResult(
            target_ref=input_model.target_ref,
            source_refs=[f"source:{input_model.target_ref.object_id}"],
            proposal_refs=[f"proposal:{input_model.target_ref.object_id}"],
            ingestion_refs=[f"ingestion:{input_model.target_ref.object_id}"],
        )

    @staticmethod
    def _domain_for_summary_id(summary_id: str) -> Domain:
        prefix = summary_id.split(".", 1)[0]
        aliases = {"world": "world_rule"}
        try:
            return Domain(aliases.get(prefix, prefix))
        except ValueError:
            return Domain.SCENE

    def _build_query(
        self,
        *,
        query_kind: str,
        text_query: str,
        scope: str | None,
        domains: list[Domain],
        top_k: int,
        filters: dict[str, object],
    ) -> RetrievalQuery:
        return RetrievalQuery(
            query_id=f"rq_{uuid.uuid4().hex[:10]}",
            query_kind=query_kind,
            story_id=str(filters.get("story_id") or self._default_story_id or "*"),
            scope=scope,
            domains=list(domains),
            text_query=text_query,
            filters=dict(filters),
            top_k=top_k,
            rerank=False,
        )

    async def _search(
        self,
        query: RetrievalQuery,
        *,
        search_kind: str,
    ) -> RetrievalSearchResult:
        started = perf_counter()
        try:
            with Session(get_engine()) as session:
                service = self._retrieval_service_factory(session)
                if search_kind == "documents":
                    result = await service.search_documents(query)
                else:
                    result = await service.search_chunks(query)
            trace = result.trace
            if trace is not None and "broker_ms" not in trace.timings:
                trace.timings["broker_ms"] = round((perf_counter() - started) * 1000, 3)
            return result
        except SQLAlchemyError as exc:
            return RetrievalSearchResult(
                query=query.text_query or "",
                hits=[],
                trace=None,
                warnings=[f"retrieval_store_unavailable:{type(exc).__name__}"],
            )
