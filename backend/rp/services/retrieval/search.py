"""Search broker for RP retrieval recall and archival reads."""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from models.rp_retrieval_store import KnowledgeChunkRecord, SourceAssetRecord
from models.rp_story_store import RuntimeProfileSnapshotRecord
from rp.models.dsl import Domain
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import (
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalHit,
    RetrievalQuery,
    RetrievalSearchResult,
    RetrievalTrace,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig
from rp.models.runtime_identity import RuntimeProfileSnapshotCompiledProfile
from rp.observability.langfuse_scores import emit_retrieval_trace_scores
from rp.services.runtime.read_manifest_service import (
    BranchVisibilityResolver,
    RuntimeReadManifestServiceError,
    filter_hits_by_branch_visibility,
)
from services.langfuse_service import get_langfuse_service

from .context import RetrievalBrokerContext
from .observability_service import RetrievalObservabilityService
from .runtime_config_service import RetrievalRuntimeConfigService
from .service import RetrievalService


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


class SearchBroker:
    """Own recall/archival search and the private retrieval search engine."""

    def __init__(
        self,
        *,
        context: RetrievalBrokerContext,
        retrieval_service_factory=None,
        langfuse_service=None,
    ) -> None:
        self._context = context
        self._custom_retrieval_service_factory = retrieval_service_factory is not None
        self._retrieval_service_factory = retrieval_service_factory or (
            lambda session: RetrievalService(session)
        )
        self._langfuse = langfuse_service or get_langfuse_service()

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
        with self._context.session_scope() as session:
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
        runtime_identity = self._context.effective_runtime_identity(normalized_filters)
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
                normalized_filters.get("story_id")
                or self._context.default_story_id
                or "*"
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
        runtime_identity = query.identity or self._context.effective_runtime_identity(
            filters
        )
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
        runtime_identity = query.identity or self._context.effective_runtime_identity(
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
                with self._context.session_scope() as session:
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
        runtime_identity = query.identity or self._context.effective_runtime_identity(
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
        return SearchBroker._runtime_retrieval_config_for_identity(
            session=self._session,
            runtime_identity=self._runtime_identity,
        )
