"""Unified retrieval broker for RP memory reads."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from time import perf_counter
from typing import Any
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from config import get_settings
from models.rp_retrieval_store import KnowledgeChunkRecord, SourceAssetRecord
from models.rp_story_store import RuntimeProfileSnapshotRecord
from rp.models.block_view import RpBlockView
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProvenanceResult,
    RetrievalHit,
    RetrievalQuery,
    RetrievalSearchResult,
    RetrievalTrace,
    StateReadResult,
    StateReadResultItem,
    SummaryEntry,
    SummaryReadResult,
    VersionListResult,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig
from rp.models.runtime_identity import RuntimeProfileSnapshotCompiledProfile
from rp.observability.langfuse_scores import emit_retrieval_trace_scores
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_backfill_service import CoreStateBackfillService
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state_read_service import CoreStateReadService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_repository import ProposalRepository
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.projection_read_service import ProjectionReadService
from rp.services.retrieval_observability_service import RetrievalObservabilityService
from rp.services.retrieval_runtime_config_service import RetrievalRuntimeConfigService
from rp.services.retrieval_service import RetrievalService
from rp.services.runtime_read_manifest_service import (
    BranchVisibilityResolver,
    RuntimeReadManifestServiceError,
    filter_hits_by_branch_visibility,
)
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.services.memory_object_mapper import normalize_projection_summary_id
from services.database import get_engine
from services.langfuse_service import get_langfuse_service


_RUNTIME_BRANCH_VISIBILITY_FILTER_KEYS = (
    "branch_id",
    "branch_ids",
    "branch_head_id",
    "branch_head_ids",
    "owning_branch_head_id",
    "owning_branch_head_ids",
    "selected_branch_head_ids",
)
_RUNTIME_BRANCH_VISIBILITY_IGNORED_FILTERS_KEY = (
    "_runtime_branch_visibility_ignored_filters"
)


class RetrievalBroker:
    """Route memory.search_* to the retrieval-core while keeping other surfaces stable."""

    def __init__(
        self,
        *,
        default_story_id: str | None = None,
        runtime_identity: MemoryRuntimeIdentity | dict[str, Any] | None = None,
        session: Session | None = None,
        retrieval_service_factory=None,
        core_state_read_service_factory=None,
        projection_read_service_factory=None,
        langfuse_service=None,
    ) -> None:
        self._default_story_id = default_story_id
        self._runtime_identity = self._normalize_runtime_identity(runtime_identity)
        self._session = session
        self._custom_retrieval_service_factory = retrieval_service_factory is not None
        self._retrieval_service_factory = retrieval_service_factory or (
            lambda session: RetrievalService(session)
        )
        self._core_state_read_service_factory = core_state_read_service_factory or (
            lambda session: self._build_core_state_read_service(session)
        )
        self._projection_read_service_factory = projection_read_service_factory or (
            lambda session: self._build_projection_read_service(session)
        )
        self._langfuse = langfuse_service or get_langfuse_service()

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        try:
            with self._session_scope() as session:
                service = self._core_state_read_service_factory(session)
                result = await service.get_state(input_model)
                return self._merge_state_result_from_blocks(
                    session=session,
                    input_model=input_model,
                    result=result,
                )
        except SQLAlchemyError as exc:
            items: list[StateReadResultItem] = []
            refs = list(input_model.refs)
            if not refs:
                domain = input_model.domain
                if domain is None:
                    raise ValueError(
                        "MemoryGetStateInput must include refs or domain"
                    ) from exc
                refs = [
                    ObjectRef(
                        object_id=f"{domain.value}.current",
                        layer=Layer.CORE_STATE_AUTHORITATIVE,
                        domain=domain,
                        domain_path=f"{domain.value}.current",
                        scope=input_model.scope,
                        revision=1,
                    )
                ]
            for ref in refs:
                items.append(StateReadResultItem(object_ref=ref, data={}, warnings=[]))
            return StateReadResult(
                items=items,
                version_refs=[
                    f"{item.object_ref.object_id}@{item.object_ref.revision or 1}"
                    for item in items
                ],
                warnings=[f"story_store_unavailable:{type(exc).__name__}"],
            )

    async def get_summary(
        self, input_model: MemoryGetSummaryInput
    ) -> SummaryReadResult:
        try:
            with self._session_scope() as session:
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

    def expand_hit(self, hit: RetrievalHit) -> dict[str, Any]:
        chunk_id = self._hit_chunk_id(hit)
        with self._session_scope() as session:
            chunk = session.get(KnowledgeChunkRecord, chunk_id)
            if chunk is None:
                raise ValueError(f"retrieval_hit_chunk_not_found:{chunk_id}")
            asset = session.get(SourceAssetRecord, chunk.asset_id)
            return {
                "chunk_id": chunk.chunk_id,
                "asset_id": chunk.asset_id,
                "parsed_document_id": chunk.parsed_document_id,
                "collection_id": chunk.collection_id,
                "domain": chunk.domain,
                "domain_path": chunk.domain_path,
                "chunk_index": chunk.chunk_index,
                "title": chunk.title or (asset.title if asset is not None else None),
                "text": chunk.text,
                "token_count": chunk.token_count,
                "layer": hit.layer,
                "metadata": deepcopy(chunk.metadata_json or {}),
                "provenance_refs": list(chunk.provenance_refs_json or []),
                "source_ref": (
                    asset.source_ref
                    if asset is not None
                    else hit.metadata.get("source_ref")
                ),
                "asset_kind": (
                    asset.asset_kind
                    if asset is not None
                    else hit.metadata.get("asset_kind")
                ),
            }

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
        with self._session_scope() as session:
            service = (
                self._projection_read_service_factory(session)
                if (input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION)
                else self._core_state_read_service_factory(session)
            )
            return await service.list_versions(input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        with self._session_scope() as session:
            service = (
                self._projection_read_service_factory(session)
                if (input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION)
                else self._core_state_read_service_factory(session)
            )
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
        normalized_filters = dict(filters)
        runtime_identity = self._effective_runtime_identity(normalized_filters)
        if runtime_identity is not None:
            normalized_filters = self._filters_without_runtime_branch_overrides(
                normalized_filters
            )
        if runtime_identity is not None:
            normalized_filters["runtime_identity"] = runtime_identity.model_dump(
                mode="json"
            )
        story_id = (
            runtime_identity.story_id
            if runtime_identity is not None
            else str(
                normalized_filters.get("story_id") or self._default_story_id or "*"
            )
        )
        return RetrievalQuery(
            query_id=f"rq_{uuid.uuid4().hex[:10]}",
            query_kind=query_kind,
            story_id=story_id,
            identity=runtime_identity,
            scope=scope,
            domains=list(domains),
            text_query=text_query,
            filters=normalized_filters,
            top_k=top_k,
            rerank=self._explicit_rerank_enabled(normalized_filters),
        )

    @staticmethod
    def _filters_without_runtime_branch_overrides(
        filters: dict[str, object],
    ) -> dict[str, object]:
        cleaned = dict(filters)
        ignored_filter_keys: list[str] = []
        for key in _RUNTIME_BRANCH_VISIBILITY_FILTER_KEYS:
            if key not in cleaned:
                continue
            ignored_filter_keys.append(key)
            cleaned.pop(key, None)
        if ignored_filter_keys:
            cleaned[_RUNTIME_BRANCH_VISIBILITY_IGNORED_FILTERS_KEY] = {
                "ignored_filter_keys": ignored_filter_keys,
                "reason": "runtime_identity_branch_visibility_is_authoritative",
            }
        return cleaned

    @staticmethod
    def _search_policy(filters: dict[str, object]) -> dict[str, object]:
        raw_policy = filters.get("search_policy")
        return dict(raw_policy) if isinstance(raw_policy, dict) else {}

    @classmethod
    def _explicit_rerank_enabled(cls, filters: dict[str, object]) -> bool:
        policy = cls._search_policy(filters)
        rerank = policy.get("rerank")
        if isinstance(rerank, str) and rerank.strip().lower() == "on":
            return True
        return False

    @classmethod
    def _rerank_policy_value(cls, filters: dict[str, object]) -> str:
        policy = cls._search_policy(filters)
        rerank = policy.get("rerank")
        if isinstance(rerank, str) and rerank.strip().lower() in {"on", "off", "auto"}:
            return rerank.strip().lower()
        return "auto"

    @classmethod
    def _profile_default_rerank_enabled(cls, filters: dict[str, object]) -> bool:
        policy = cls._search_policy(filters)
        profile = policy.get("profile")
        if not isinstance(profile, str):
            return False
        return profile.strip().lower() in {"longform", "roleplay", "trpg"}

    def _query_with_runtime_search_policy(
        self,
        *,
        query: RetrievalQuery,
        session: Session,
    ) -> RetrievalQuery:
        filters = dict(query.filters or {})
        policy_value = self._rerank_policy_value(filters)
        if policy_value == "on":
            return query.model_copy(update={"rerank": True})
        if policy_value == "off":
            return query.model_copy(update={"rerank": False})
        runtime_identity = query.identity or self._effective_runtime_identity(filters)
        if runtime_identity is not None:
            config = self._runtime_retrieval_config_for_identity(
                session=session,
                runtime_identity=runtime_identity,
            )
            return query.model_copy(
                update={
                    "rerank": bool(config.rerank_model_id or config.rerank_provider_id)
                    or self._profile_default_rerank_enabled(filters)
                }
            )
        if query.story_id in {"", "*"}:
            return query.model_copy(
                update={"rerank": self._profile_default_rerank_enabled(filters)}
            )
        config = RetrievalRuntimeConfigService(session).resolve_story_config(
            story_id=query.story_id
        )
        return query.model_copy(
            update={
                "rerank": bool(config.rerank_model_id or config.rerank_provider_id)
                or self._profile_default_rerank_enabled(filters)
            }
        )

    def _build_retrieval_service(
        self,
        *,
        session: Session,
        query: RetrievalQuery,
    ):
        runtime_identity = query.identity or self._effective_runtime_identity(
            dict(query.filters or {})
        )
        if runtime_identity is None or self._custom_retrieval_service_factory:
            return self._retrieval_service_factory(session)
        return RetrievalService(
            session,
            retrieval_runtime_config_service=_SnapshotPinnedRetrievalRuntimeConfigService(
                session=session,
                runtime_identity=runtime_identity,
            ),
        )

    def _build_core_state_read_service(self, session: Session) -> CoreStateReadService:
        story_session_service = StorySessionService(session)
        adapter = StorySessionCoreStateAdapter(
            story_session_service,
            default_story_id=self._default_story_id,
        )
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(
            get_settings().rp_memory_core_state_store_read_enabled
        )
        runtime_owned_read = self._runtime_identity is not None
        core_state_as_of_resolver = (
            CoreStateAsOfResolver(
                session=session,
                repository=core_state_store_repository,
            )
            if runtime_owned_read
            else None
        )
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
            store_read_enabled=store_read_enabled or runtime_owned_read,
            core_state_backfill_service=backfill_service,
            runtime_identity=self._runtime_identity,
            core_state_as_of_resolver=core_state_as_of_resolver,
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
            store_read_enabled=bool(
                get_settings().rp_memory_core_state_store_read_enabled
            ),
            core_state_backfill_service=CoreStateBackfillService(
                story_session_service=story_session_service,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
            ),
            runtime_identity=self._runtime_identity,
        )

    def _build_rp_block_read_service(self, session: Session) -> RpBlockReadService:
        story_session_service = StorySessionService(session)
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(
            get_settings().rp_memory_core_state_store_read_enabled
        )
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
            normalize_projection_summary_id(
                item.summary_id
            ): self._summary_entry_with_block_metadata(
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
        if self._runtime_identity is not None:
            return self._runtime_identity.session_id
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
        chapter_workspace_id = metadata.get(
            "chapter_workspace_id"
        ) or block.metadata.get("chapter_workspace_id")
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
                with self._session_scope() as session:
                    query = self._query_with_runtime_search_policy(
                        query=query,
                        session=session,
                    )
                    service = self._build_retrieval_service(
                        session=session,
                        query=query,
                    )
                    if search_kind == "documents":
                        result = await service.search_documents(query)
                    else:
                        result = await service.search_chunks(query)
                    result = self._filter_runtime_search_result(
                        session=session,
                        query=query,
                        result=result,
                    )
                    trace = result.trace
                    if trace is not None and "broker_ms" not in trace.timings:
                        trace.timings["broker_ms"] = round(
                            (perf_counter() - started) * 1000, 3
                        )
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

    def _filter_runtime_search_result(
        self,
        *,
        session: Session,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        runtime_identity = query.identity or self._effective_runtime_identity(
            dict(query.filters or {})
        )
        if runtime_identity is None:
            return result
        resolver = BranchVisibilityResolver(session)
        warnings = list(result.warnings)
        ignored_filter_keys = self._runtime_ignored_branch_filter_keys(query.filters)
        if ignored_filter_keys:
            warnings.append(
                "runtime_branch_filters_ignored:" + ",".join(ignored_filter_keys)
            )
        try:
            scope = resolver.build_scope(identity=runtime_identity)
        except RuntimeReadManifestServiceError as exc:
            warnings.append(f"runtime_branch_scope_unresolved:{exc.code}")
            trace = self._runtime_branch_scope_unresolved_trace(
                query=query,
                result=result,
                runtime_identity=runtime_identity,
                error_code=exc.code,
            )
            return result.model_copy(
                update={
                    "hits": [],
                    "warnings": warnings,
                    "trace": trace,
                }
            )
        filtered_hits, omitted_refs = filter_hits_by_branch_visibility(
            resolver=resolver,
            scope=scope,
            hits=list(result.hits),
        )
        if not omitted_refs:
            if warnings == result.warnings:
                return result
            return result.model_copy(update={"warnings": warnings})
        warnings.append(
            "runtime_branch_visibility_filtered:"
            + ",".join(str(item.get("ref_id") or "") for item in omitted_refs)
        )
        trace = result.trace
        if trace is not None:
            details = dict(trace.details or {})
            details["branch_visibility"] = {
                "active_branch_head_id": scope.active_branch_head_id,
                "visible_branch_head_ids": list(scope.visible_branch_head_ids),
                "turn_cutoff_by_branch": dict(scope.turn_cutoff_by_branch),
                "omitted_refs": omitted_refs,
            }
            trace = trace.model_copy(
                update={
                    "returned_count": len(filtered_hits),
                    "warnings": [
                        *list(trace.warnings),
                        "runtime_branch_visibility_filtered",
                    ],
                    "details": details,
                }
            )
        return result.model_copy(
            update={
                "hits": filtered_hits,
                "warnings": warnings,
                "trace": trace,
            }
        )

    @staticmethod
    def _runtime_ignored_branch_filter_keys(
        filters: dict[str, object] | None,
    ) -> list[str]:
        marker = dict(filters or {}).get(_RUNTIME_BRANCH_VISIBILITY_IGNORED_FILTERS_KEY)
        if not isinstance(marker, dict):
            return []
        raw_keys = marker.get("ignored_filter_keys")
        if not isinstance(raw_keys, list):
            return []
        return [str(key) for key in raw_keys if str(key)]

    @staticmethod
    def _runtime_branch_scope_unresolved_trace(
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
        runtime_identity: MemoryRuntimeIdentity,
        error_code: str,
    ) -> RetrievalTrace:
        details = {}
        if result.trace is not None:
            details = dict(result.trace.details or {})
        details["branch_visibility"] = {
            "status": "omitted_fail_closed",
            "reason": "runtime_branch_scope_unresolved",
            "error_code": error_code,
            "identity": runtime_identity.model_dump(mode="json"),
        }
        warnings = ["runtime_branch_scope_unresolved"]
        if result.trace is not None:
            warnings = [*list(result.trace.warnings), *warnings]
            return result.trace.model_copy(
                update={
                    "returned_count": 0,
                    "warnings": warnings,
                    "details": details,
                }
            )
        return RetrievalTrace(
            trace_id=f"trace_{query.query_id}_branch_scope_unresolved",
            query_id=query.query_id,
            route="retrieval.runtime_branch_visibility",
            result_kind="omitted_fail_closed",
            candidate_count=len(result.hits),
            returned_count=0,
            warnings=warnings,
            details=details,
        )

    @staticmethod
    def _normalize_runtime_identity(
        runtime_identity: object | None,
    ) -> MemoryRuntimeIdentity | None:
        if runtime_identity is None:
            return None
        if isinstance(runtime_identity, MemoryRuntimeIdentity):
            return runtime_identity
        if not isinstance(runtime_identity, dict):
            return None
        try:
            return MemoryRuntimeIdentity.model_validate(runtime_identity)
        except ValueError:
            return None

    def _effective_runtime_identity(
        self,
        filters: dict[str, object],
    ) -> MemoryRuntimeIdentity | None:
        if self._runtime_identity is not None:
            return self._runtime_identity
        return self._normalize_runtime_identity(filters.get("runtime_identity"))

    @contextmanager
    def _session_scope(self):
        if self._session is not None:
            yield self._session
            return
        with Session(get_engine()) as session:
            yield session

    @staticmethod
    def _hit_chunk_id(hit: RetrievalHit) -> str:
        for candidate in (
            hit.hit_id,
            hit.metadata.get("chunk_id"),
            hit.knowledge_ref.object_id if hit.knowledge_ref is not None else None,
        ):
            normalized = str(candidate or "").strip()
            if normalized:
                return normalized
        raise ValueError("retrieval_hit_chunk_id_missing")

    @staticmethod
    def _runtime_retrieval_config_for_identity(
        *,
        session: Session,
        runtime_identity: MemoryRuntimeIdentity,
    ) -> RetrievalRuntimeConfig:
        snapshot = session.get(
            RuntimeProfileSnapshotRecord,
            runtime_identity.runtime_profile_snapshot_id,
        )
        if snapshot is None:
            raise ValueError(
                "runtime_profile_snapshot_not_found:"
                f"{runtime_identity.runtime_profile_snapshot_id}"
            )
        compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
            snapshot.compiled_profile_json or {}
        )
        return compiled.retrieval_policy


class _SnapshotPinnedRetrievalRuntimeConfigService:
    """Resolve retrieval config from a pinned runtime profile snapshot."""

    def __init__(
        self,
        *,
        session: Session,
        runtime_identity: MemoryRuntimeIdentity,
    ) -> None:
        self._session = session
        self._runtime_identity = runtime_identity

    def resolve_story_config(self, *, story_id: str) -> RetrievalRuntimeConfig:
        if story_id not in {"", "*", self._runtime_identity.story_id}:
            raise ValueError(f"runtime_identity_story_mismatch:{story_id}")
        return RetrievalBroker._runtime_retrieval_config_for_identity(
            session=self._session,
            runtime_identity=self._runtime_identity,
        )
