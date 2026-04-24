"""Structured observability views for retrieval query execution."""

from __future__ import annotations

from collections import OrderedDict

from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult
from rp.models.retrieval_observability import (
    RetrievalObservabilityHitView,
    RetrievalObservabilityMaintenanceView,
    RetrievalObservabilityView,
    RetrievalWarningBucket,
)
from .retrieval_maintenance_service import RetrievalMaintenanceService

_EXCERPT_PREVIEW_CHARS = 240


class RetrievalObservabilityService:
    """Build a stable retrieval observability view from query result + maintenance state."""

    def __init__(
        self,
        session=None,
        *,
        maintenance_service: RetrievalMaintenanceService | None = None,
    ) -> None:
        self._session = session
        self._maintenance_service = (
            maintenance_service
            or (RetrievalMaintenanceService(session) if session is not None else None)
        )

    def build_view(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
        include_story_snapshot: bool = True,
        max_hits: int = 5,
    ) -> RetrievalObservabilityView:
        trace = result.trace
        warnings = list(result.warnings)
        if trace is not None:
            warnings = list(dict.fromkeys([*warnings, *(trace.warnings or [])]))

        return RetrievalObservabilityView(
            query_id=query.query_id,
            story_id=query.story_id,
            query_kind=query.query_kind,
            text_query=query.text_query,
            top_k=query.top_k,
            route=trace.route if trace is not None else None,
            result_kind=trace.result_kind if trace is not None else None,
            retriever_routes=list(trace.retriever_routes if trace is not None else []),
            pipeline_stages=list(trace.pipeline_stages if trace is not None else []),
            reranker_name=trace.reranker_name if trace is not None else None,
            candidate_count=trace.candidate_count if trace is not None else len(result.hits),
            returned_count=trace.returned_count if trace is not None else len(result.hits),
            filters_applied=dict(trace.filters_applied if trace is not None else {}),
            timings=dict(trace.timings if trace is not None else {}),
            warnings=warnings,
            warning_buckets=self._build_warning_buckets(warnings),
            details=dict(trace.details if trace is not None else {}),
            top_hits=self._build_hit_views(result=result, max_hits=max_hits),
            maintenance=self._build_maintenance_view(query=query) if include_story_snapshot else None,
        )

    def _build_warning_buckets(self, warnings: list[str]) -> list[RetrievalWarningBucket]:
        buckets: OrderedDict[str, list[str]] = OrderedDict()
        for warning in warnings:
            category = self._warning_category(warning)
            buckets.setdefault(category, []).append(warning)
        return [
            RetrievalWarningBucket(
                category=category,
                count=len(items),
                warnings=items,
            )
            for category, items in buckets.items()
        ]

    @staticmethod
    def _warning_category(warning: str) -> str:
        normalized = str(warning or "").strip()
        if not normalized:
            return "unknown"
        return normalized.split(":", 1)[0]

    def _build_hit_views(
        self,
        *,
        result: RetrievalSearchResult,
        max_hits: int,
    ) -> list[RetrievalObservabilityHitView]:
        views: list[RetrievalObservabilityHitView] = []
        for hit in result.hits[:max_hits]:
            metadata = dict(hit.metadata)
            page_no = metadata.get("page_no")
            views.append(
                RetrievalObservabilityHitView(
                    hit_id=hit.hit_id,
                    rank=hit.rank,
                    score=float(hit.score),
                    domain=hit.domain.value,
                    domain_path=hit.domain_path,
                    asset_id=str(metadata.get("asset_id") or "") or None,
                    collection_id=str(metadata.get("collection_id") or "") or None,
                    title=str(metadata.get("title") or "") or None,
                    page_no=int(page_no) if page_no not in (None, "") else None,
                    page_label=str(metadata.get("page_label") or "") or None,
                    page_ref=str(metadata.get("page_ref") or "") or None,
                    image_caption=str(metadata.get("image_caption") or "") or None,
                    contextual_text_version=str(metadata.get("contextual_text_version") or "") or None,
                    excerpt_preview=hit.excerpt_text[:_EXCERPT_PREVIEW_CHARS],
                )
            )
        return views

    def _build_maintenance_view(
        self,
        *,
        query: RetrievalQuery,
    ) -> RetrievalObservabilityMaintenanceView | None:
        if self._maintenance_service is None:
            return None
        snapshot = self._maintenance_service.get_story_snapshot(story_id=query.story_id)
        return RetrievalObservabilityMaintenanceView(
            story_id=snapshot.story_id,
            collection_count=snapshot.collection_count,
            asset_count=snapshot.asset_count,
            active_chunk_count=snapshot.active_chunk_count,
            active_embedding_count=snapshot.active_embedding_count,
            backfill_candidate_asset_ids=list(snapshot.backfill_candidate_asset_ids),
            failed_job_count=snapshot.failed_job_count,
            retryable_job_ids=list(snapshot.retryable_job_ids),
            recent_job_count=len(snapshot.recent_jobs),
        )
