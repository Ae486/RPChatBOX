"""Unified retrieval broker for RP memory reads."""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from config import get_settings
from rp.models.block_view import RpBlockView
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
from rp.observability.langfuse_scores import emit_retrieval_trace_scores
from rp.services.builder_projection_context_service import BuilderProjectionContextService
from rp.services.chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from rp.services.core_state_backfill_service import CoreStateBackfillService
from rp.services.core_state_read_service import CoreStateReadService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_repository import ProposalRepository
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.projection_read_service import ProjectionReadService
from rp.services.retrieval_observability_service import RetrievalObservabilityService
from rp.services.retrieval_service import RetrievalService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.services.memory_object_mapper import normalize_projection_summary_id
from services.database import get_engine
from services.langfuse_service import get_langfuse_service


class RetrievalBroker:
    """Route memory.search_* to the retrieval-core while keeping other surfaces stable."""

    def __init__(
        self,
        *,
        default_story_id: str | None = None,
        retrieval_service_factory=None,
        core_state_read_service_factory=None,
        projection_read_service_factory=None,
        langfuse_service=None,
    ) -> None:
        self._default_story_id = default_story_id
        self._retrieval_service_factory = retrieval_service_factory or (lambda session: RetrievalService(session))
        self._core_state_read_service_factory = core_state_read_service_factory or (
            lambda session: self._build_core_state_read_service(session)
        )
        self._projection_read_service_factory = projection_read_service_factory or (
            lambda session: self._build_projection_read_service(session)
        )
        self._langfuse = langfuse_service or get_langfuse_service()

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        try:
            with Session(get_engine()) as session:
                service = self._core_state_read_service_factory(session)
                result = await service.get_state(input_model)
                return self._merge_state_result_from_blocks(
                    session=session,
                    input_model=input_model,
                    result=result,
                )
        except SQLAlchemyError as exc:
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
                items.append(StateReadResultItem(object_ref=ref, data={}, warnings=[]))
            return StateReadResult(
                items=items,
                version_refs=[f"{item.object_ref.object_id}@{item.object_ref.revision or 1}" for item in items],
                warnings=[f"story_store_unavailable:{type(exc).__name__}"],
            )

    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult:
        try:
            with Session(get_engine()) as session:
                service = self._projection_read_service_factory(session)
                result = await service.get_summary(input_model)
                return self._merge_summary_result_from_blocks(
                    session=session,
                    input_model=input_model,
                    result=result,
                )
        except SQLAlchemyError as exc:
            return SummaryReadResult(
                items=[],
                warnings=[f"story_store_unavailable:{type(exc).__name__}"],
            )

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
        with Session(get_engine()) as session:
            service = self._projection_read_service_factory(session) if (
                input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION
            ) else self._core_state_read_service_factory(session)
            return await service.list_versions(input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        with Session(get_engine()) as session:
            service = self._projection_read_service_factory(session) if (
                input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION
            ) else self._core_state_read_service_factory(session)
            return await service.read_provenance(input_model)

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

    def _build_core_state_read_service(self, session: Session) -> CoreStateReadService:
        story_session_service = StorySessionService(session)
        adapter = StorySessionCoreStateAdapter(
            story_session_service,
            default_story_id=self._default_story_id,
        )
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(get_settings().rp_memory_core_state_store_read_enabled)
        backfill_service = CoreStateBackfillService(
            story_session_service=story_session_service,
            proposal_repository=proposal_repository,
            core_state_store_repository=core_state_store_repository,
        )
        return CoreStateReadService(
            adapter=adapter,
            version_history_read_service=VersionHistoryReadService(
                adapter=adapter,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
                store_read_enabled=store_read_enabled,
            ),
            provenance_read_service=ProvenanceReadService(
                adapter=adapter,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
                store_read_enabled=store_read_enabled,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
            core_state_backfill_service=backfill_service,
        )

    def _build_projection_read_service(self, session: Session) -> ProjectionReadService:
        story_session_service = StorySessionService(session)
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        return ProjectionReadService(
            adapter=ChapterWorkspaceProjectionAdapter(
                story_session_service,
                default_story_id=self._default_story_id,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=bool(get_settings().rp_memory_core_state_store_read_enabled),
            core_state_backfill_service=CoreStateBackfillService(
                story_session_service=story_session_service,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
            ),
        )

    def _build_rp_block_read_service(self, session: Session) -> RpBlockReadService:
        story_session_service = StorySessionService(session)
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(get_settings().rp_memory_core_state_store_read_enabled)
        projection_state_service = ProjectionStateService(
            story_session_service=story_session_service,
            adapter=ChapterWorkspaceProjectionAdapter(
                story_session_service,
                default_story_id=self._default_story_id,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        builder_projection_context_service = BuilderProjectionContextService(
            projection_state_service
        )
        core_state_adapter = StorySessionCoreStateAdapter(
            story_session_service,
            default_story_id=self._default_story_id,
        )
        version_history_read_service = VersionHistoryReadService(
            adapter=core_state_adapter,
            proposal_repository=proposal_repository,
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        memory_inspection_read_service = MemoryInspectionReadService(
            story_session_service=story_session_service,
            builder_projection_context_service=builder_projection_context_service,
            proposal_repository=proposal_repository,
            version_history_read_service=version_history_read_service,
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        return RpBlockReadService(
            story_session_service=story_session_service,
            builder_projection_context_service=builder_projection_context_service,
            core_state_store_repository=core_state_store_repository,
            memory_inspection_read_service=memory_inspection_read_service,
            store_read_enabled=store_read_enabled,
        )

    def _merge_state_result_from_blocks(
        self,
        *,
        session: Session,
        input_model: MemoryGetStateInput,
        result: StateReadResult,
    ) -> StateReadResult:
        # Only explicit refs can safely resolve unmapped authoritative identities.
        if not input_model.refs:
            return result
        unresolved_indexes = [
            index
            for index, item in enumerate(result.items)
            if self._state_item_needs_block_resolution(item)
        ]
        if not unresolved_indexes:
            return result
        session_id = self._current_session_id(session)
        if session_id is None:
            return result

        block_service = self._build_rp_block_read_service(session)
        blocks = block_service.list_authoritative_blocks(session_id=session_id)
        blocks_by_identity = {
            self._authoritative_identity_from_block(block): block for block in blocks
        }
        items = list(result.items)
        version_refs = list(result.version_refs)

        for index in unresolved_indexes:
            current_item = items[index]
            block = blocks_by_identity.get(
                self._authoritative_identity_from_ref(current_item.object_ref)
            )
            if block is None:
                continue
            items[index] = self._state_item_from_block(
                block=block,
                warnings=current_item.warnings,
            )
            version_refs[index] = (
                f"{items[index].object_ref.object_id}@"
                f"{items[index].object_ref.revision or 1}"
            )

        return result.model_copy(update={"items": items, "version_refs": version_refs})

    def _merge_summary_result_from_blocks(
        self,
        *,
        session: Session,
        input_model: MemoryGetSummaryInput,
        result: SummaryReadResult,
    ) -> SummaryReadResult:
        session_id = self._current_session_id(session)
        if session_id is None:
            return result

        block_service = self._build_rp_block_read_service(session)
        blocks = block_service.list_projection_blocks(session_id=session_id)
        if not blocks:
            return result
        blocks_by_summary_id = {
            normalize_projection_summary_id(block.label): block for block in blocks
        }
        item_by_summary_id = {
            normalize_projection_summary_id(item.summary_id): self._summary_entry_with_block_metadata(
                item=item,
                block=blocks_by_summary_id.get(
                    normalize_projection_summary_id(item.summary_id)
                ),
                requested_scope=input_model.scope,
            )
            for item in result.items
        }

        if input_model.summary_ids:
            items = []
            resolved_from_blocks: set[str] = set()
            for raw_summary_id in input_model.summary_ids:
                summary_id = normalize_projection_summary_id(raw_summary_id)
                item = item_by_summary_id.get(summary_id)
                if item is not None:
                    items.append(item)
                    continue
                block = blocks_by_summary_id.get(summary_id)
                if block is None:
                    continue
                items.append(
                    self._summary_entry_from_block(
                        block=block,
                        requested_scope=input_model.scope,
                    )
                )
                resolved_from_blocks.add(summary_id)
            warnings = self._strip_summary_resolution_warnings(
                warnings=result.warnings,
                resolved_summary_ids=resolved_from_blocks,
            )
            return result.model_copy(update={"items": items, "warnings": warnings})

        ordered_items = [
            item_by_summary_id[normalize_projection_summary_id(item.summary_id)]
            for item in result.items
        ]
        return result.model_copy(update={"items": ordered_items})

    def _current_session_id(self, session: Session) -> str | None:
        if not self._default_story_id:
            return None
        current_session = StorySessionService(session).get_latest_session_for_story(
            self._default_story_id
        )
        if current_session is None:
            return None
        return current_session.session_id

    @staticmethod
    def _state_item_needs_block_resolution(item: StateReadResultItem) -> bool:
        return any(
            warning.startswith("phase_e_authoritative_ref_not_materialized:")
            for warning in item.warnings
        )

    @staticmethod
    def _authoritative_identity_from_ref(ref: ObjectRef) -> tuple[str, str, str]:
        return (
            ref.object_id,
            ref.domain_path or ref.object_id,
            ref.scope or "story",
        )

    @staticmethod
    def _authoritative_identity_from_block(block: RpBlockView) -> tuple[str, str, str]:
        return (block.label, block.domain_path, block.scope or "story")

    @classmethod
    def _state_item_from_block(
        cls,
        *,
        block: RpBlockView,
        warnings: list[str],
    ) -> StateReadResultItem:
        payload = block.data_json if isinstance(block.data_json, dict) else {}
        return StateReadResultItem(
            object_ref=ObjectRef(
                object_id=block.label,
                layer=block.layer,
                domain=block.domain,
                domain_path=block.domain_path,
                scope=block.scope,
                revision=int(block.revision),
            ),
            data=deepcopy(payload),
            warnings=[
                warning
                for warning in warnings
                if not warning.startswith("phase_e_authoritative_ref_not_materialized:")
            ],
        )

    @classmethod
    def _summary_entry_with_block_metadata(
        cls,
        *,
        item: SummaryEntry,
        block: RpBlockView | None,
        requested_scope: str | None,
    ) -> SummaryEntry:
        if block is None:
            return item
        return item.model_copy(
            update={
                "summary_id": block.label,
                "domain": block.domain,
                "domain_path": block.domain_path,
                "metadata": cls._summary_metadata(
                    existing=item.metadata,
                    block=block,
                    requested_scope=requested_scope,
                ),
            }
        )

    @classmethod
    def _summary_entry_from_block(
        cls,
        *,
        block: RpBlockView,
        requested_scope: str | None,
    ) -> SummaryEntry:
        raw_value: Any = block.items_json
        if raw_value is None:
            raw_value = block.data_json
        return SummaryEntry(
            summary_id=block.label,
            domain=block.domain,
            domain_path=block.domain_path,
            summary_text=cls._stringify_summary_value(raw_value),
            metadata=cls._summary_metadata(
                existing=None,
                block=block,
                requested_scope=requested_scope,
            ),
        )

    @staticmethod
    def _summary_metadata(
        *,
        existing: dict[str, Any] | None,
        block: RpBlockView,
        requested_scope: str | None,
    ) -> dict[str, Any]:
        metadata = dict(existing or {})
        metadata["block_id"] = block.block_id
        metadata["source"] = block.source
        metadata["source_row_id"] = block.metadata.get("source_row_id")
        metadata["revision"] = int(block.revision)
        metadata["payload_schema_ref"] = block.payload_schema_ref
        metadata["block_route"] = block.metadata.get("route")
        metadata["scope"] = metadata.get("scope") or requested_scope or block.scope
        metadata["session_id"] = metadata.get("session_id") or block.metadata.get(
            "session_id"
        )
        chapter_workspace_id = metadata.get("chapter_workspace_id") or block.metadata.get(
            "chapter_workspace_id"
        )
        if chapter_workspace_id is not None:
            metadata["chapter_workspace_id"] = chapter_workspace_id
        slot_name = metadata.get("slot_name") or block.metadata.get("source_field")
        if slot_name is not None:
            metadata["slot_name"] = slot_name
        return metadata

    @staticmethod
    def _stringify_summary_value(raw_value: Any) -> str:
        if raw_value is None:
            return ""
        if isinstance(raw_value, list):
            return "\n".join(str(item) for item in raw_value if item is not None)
        return str(raw_value)

    @staticmethod
    def _strip_summary_resolution_warnings(
        *,
        warnings: list[str],
        resolved_summary_ids: set[str],
    ) -> list[str]:
        if not resolved_summary_ids:
            return list(warnings)
        stripped: list[str] = []
        for warning in warnings:
            if not warning.startswith("phase_e_projection_summary_not_materialized:"):
                stripped.append(warning)
                continue
            summary_id = warning.split(":", 1)[1]
            if summary_id not in resolved_summary_ids:
                stripped.append(warning)
        return stripped

    async def _search(
        self,
        query: RetrievalQuery,
        *,
        search_kind: str,
    ) -> RetrievalSearchResult:
        observation_name = f"rp.retrieval.search_{query.query_kind}"
        with self._langfuse.start_as_current_observation(
            name=observation_name,
            as_type="chain",
            input={
                "query": query.model_dump(mode="json"),
                "search_kind": search_kind,
            },
        ) as observation:
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
                    observability = RetrievalObservabilityService(session).build_view(
                        query=query,
                        result=result,
                        include_story_snapshot=False,
                        max_hits=3,
                    )
                output = {
                    "status": "ok",
                    "search_kind": search_kind,
                    "observability": observability.model_dump(mode="json"),
                }
                observation.update(output=output)
                emit_retrieval_trace_scores(
                    observation,
                    query_payload=query.model_dump(mode="json"),
                    result_payload=result.model_dump(mode="json"),
                    observability_payload=output["observability"],
                )
                return result
            except SQLAlchemyError as exc:
                result = RetrievalSearchResult(
                    query=query.text_query or "",
                    hits=[],
                    trace=None,
                    warnings=[f"retrieval_store_unavailable:{type(exc).__name__}"],
                )
                observability = RetrievalObservabilityService().build_view(
                    query=query,
                    result=result,
                    include_story_snapshot=False,
                    max_hits=0,
                )
                output = {
                    "status": "fallback",
                    "search_kind": search_kind,
                    "observability": observability.model_dump(mode="json"),
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "code": "retrieval_store_unavailable",
                    },
                }
                observation.update(output=output)
                emit_retrieval_trace_scores(
                    observation,
                    query_payload=query.model_dump(mode="json"),
                    result_payload=result.model_dump(mode="json"),
                    observability_payload=output["observability"],
                    failure_layer="infra",
                    error_code="retrieval_store_unavailable",
                )
                return result
            except Exception as exc:
                observation.update(
                    output={
                        "status": "error",
                        "search_kind": search_kind,
                        "query_id": query.query_id,
                        "story_id": query.story_id,
                        "query_kind": query.query_kind,
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    }
                )
                emit_retrieval_trace_scores(
                    observation,
                    query_payload=query.model_dump(mode="json"),
                    result_payload={"hits": [], "warnings": [], "trace": None},
                    observability_payload=None,
                    failure_layer="retrieval",
                    error_code=type(exc).__name__,
                )
                raise
