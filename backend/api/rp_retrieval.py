"""Retrieval maintenance and observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from rp.models.memory_graph_projection import (
    GRAPH_EXTRACTION_SCHEMA_VERSION,
    GRAPH_JOB_REASON_MANUAL_REBUILD,
    GRAPH_TAXONOMY_VERSION,
)
from rp.services.memory_graph_projection_service import MemoryGraphProjectionService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_maintenance_service import RetrievalMaintenanceService
from services.database import get_session

router = APIRouter()


class RetrievalStoryReindexRequest(BaseModel):
    collection_id: str | None = None
    collection_kind: str | None = None


class RetrievalRetryFailedJobsRequest(BaseModel):
    collection_id: str | None = None
    collection_kind: str | None = None
    limit: int | None = None


class MemoryGraphRebuildRequest(BaseModel):
    source_asset_ids: list[str] | None = None
    workspace_id: str | None = None
    commit_id: str | None = None
    queued_reason: str | None = None
    extraction_schema_version: str | None = None
    taxonomy_version: str | None = None


class MemoryGraphRetryRequest(BaseModel):
    limit: int | None = None


def _maintenance_service(
    session: Session = Depends(get_session),
) -> RetrievalMaintenanceService:
    return RetrievalMaintenanceService(session)


def _graph_projection_service(
    session: Session = Depends(get_session),
) -> MemoryGraphProjectionService:
    return MemoryGraphProjectionService(session)


def _ingestion_service(
    session: Session = Depends(get_session),
) -> RetrievalIngestionService:
    return RetrievalIngestionService(session)


def _collection_not_found(collection_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Retrieval collection not found: {collection_id}",
                "code": "retrieval_collection_not_found",
            }
        },
    )


def _job_failed(exc: Exception, *, code: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": {"message": str(exc), "code": code}},
    )


def _graph_request_failed(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_graph_projection_request_invalid",
            }
        },
    )


@router.get("/api/rp/retrieval/stories/{story_id}/maintenance")
async def get_retrieval_story_maintenance(
    story_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    return service.get_story_snapshot(story_id=story_id).model_dump(mode="json")


@router.get("/api/rp/retrieval/stories/{story_id}/graph/maintenance")
async def get_memory_graph_story_maintenance(
    story_id: str,
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    return service.get_maintenance_snapshot(story_id=story_id).model_dump(mode="json")


@router.get("/api/rp/retrieval/stories/{story_id}/graph/nodes")
async def list_memory_graph_nodes(
    story_id: str,
    entity_type: list[str] | None = Query(default=None),
    source_layer: list[str] | None = Query(default=None),
    source_status: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    try:
        return service.list_nodes(
            story_id=story_id,
            entity_types=entity_type,
            source_layers=source_layer,
            source_statuses=source_status,
            limit=limit,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise _graph_request_failed(exc) from exc


@router.get("/api/rp/retrieval/stories/{story_id}/graph/edges")
async def list_memory_graph_edges(
    story_id: str,
    relation_type: list[str] | None = Query(default=None),
    node_id: list[str] | None = Query(default=None),
    source_layer: list[str] | None = Query(default=None),
    source_status: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    try:
        return service.list_edges(
            story_id=story_id,
            relation_types=relation_type,
            node_ids=node_id,
            source_layers=source_layer,
            source_statuses=source_status,
            limit=limit,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise _graph_request_failed(exc) from exc


@router.get("/api/rp/retrieval/stories/{story_id}/graph/evidence")
async def list_memory_graph_evidence(
    story_id: str,
    node_id: list[str] | None = Query(default=None),
    edge_id: list[str] | None = Query(default=None),
    source_layer: list[str] | None = Query(default=None),
    source_asset_id: list[str] | None = Query(default=None),
    chunk_id: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=0, le=500),
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    try:
        return service.list_evidence(
            story_id=story_id,
            node_ids=node_id,
            edge_ids=edge_id,
            source_layers=source_layer,
            source_asset_ids=source_asset_id,
            chunk_ids=chunk_id,
            limit=limit,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise _graph_request_failed(exc) from exc


@router.get("/api/rp/retrieval/stories/{story_id}/graph/neighborhood")
async def get_memory_graph_neighborhood(
    story_id: str,
    node_id: str | None = Query(default=None),
    max_depth: int = Query(default=1, ge=0, le=2),
    max_nodes: int = Query(default=50, ge=0, le=200),
    max_edges: int = Query(default=75, ge=0, le=300),
    entity_type: list[str] | None = Query(default=None),
    relation_type: list[str] | None = Query(default=None),
    source_layer: list[str] | None = Query(default=None),
    source_status: list[str] | None = Query(default=None),
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    try:
        return service.get_neighborhood(
            story_id=story_id,
            node_id=node_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            entity_types=entity_type,
            relation_types=relation_type,
            source_layers=source_layer,
            source_statuses=source_status,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise _graph_request_failed(exc) from exc


@router.post("/api/rp/retrieval/stories/{story_id}/graph/rebuild")
async def rebuild_memory_graph_story(
    story_id: str,
    payload: MemoryGraphRebuildRequest,
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    try:
        jobs = service.rebuild_story_graph(
            story_id=story_id,
            source_asset_ids=payload.source_asset_ids,
            workspace_id=payload.workspace_id,
            commit_id=payload.commit_id,
            queued_reason=payload.queued_reason or GRAPH_JOB_REASON_MANUAL_REBUILD,
            extraction_schema_version=(
                payload.extraction_schema_version or GRAPH_EXTRACTION_SCHEMA_VERSION
            ),
            taxonomy_version=payload.taxonomy_version or GRAPH_TAXONOMY_VERSION,
        )
    except ValueError as exc:
        raise _graph_request_failed(exc) from exc
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.post("/api/rp/retrieval/stories/{story_id}/graph/retry")
async def retry_memory_graph_story_jobs(
    story_id: str,
    payload: MemoryGraphRetryRequest,
    service: MemoryGraphProjectionService = Depends(_graph_projection_service),
):
    jobs = service.retry_failed_jobs(story_id=story_id, limit=payload.limit)
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.get("/api/rp/retrieval/collections/{collection_id}/maintenance")
async def get_retrieval_collection_maintenance(
    collection_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    snapshot = service.get_collection_snapshot(collection_id=collection_id)
    if snapshot is None:
        raise _collection_not_found(collection_id)
    return snapshot.model_dump(mode="json")


@router.post("/api/rp/retrieval/stories/{story_id}/reindex")
async def reindex_retrieval_story(
    story_id: str,
    payload: RetrievalStoryReindexRequest,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    jobs = service.reindex_story(
        story_id=story_id,
        collection_id=payload.collection_id,
        collection_kind=payload.collection_kind,
    )
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.post("/api/rp/retrieval/collections/{collection_id}/reindex")
async def reindex_retrieval_collection(
    collection_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    snapshot = service.get_collection_snapshot(collection_id=collection_id)
    if snapshot is None:
        raise _collection_not_found(collection_id)
    jobs = service.reindex_collection(collection_id=collection_id)
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.post("/api/rp/retrieval/stories/{story_id}/backfill")
async def backfill_retrieval_story_embeddings(
    story_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    jobs = service.backfill_story_embeddings(story_id=story_id)
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.post("/api/rp/retrieval/collections/{collection_id}/backfill")
async def backfill_retrieval_collection_embeddings(
    collection_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    snapshot = service.get_collection_snapshot(collection_id=collection_id)
    if snapshot is None:
        raise _collection_not_found(collection_id)
    jobs = service.backfill_collection_embeddings(collection_id=collection_id)
    return {"object": "list", "data": [job.model_dump(mode="json") for job in jobs]}


@router.post("/api/rp/retrieval/stories/{story_id}/retry-failed")
async def retry_failed_retrieval_story_jobs(
    story_id: str,
    payload: RetrievalRetryFailedJobsRequest,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    result = service.retry_story_failed_jobs(
        story_id=story_id,
        collection_id=payload.collection_id,
        collection_kind=payload.collection_kind,
        limit=payload.limit,
    )
    return result.model_dump(mode="json")


@router.post("/api/rp/retrieval/collections/{collection_id}/retry-failed")
async def retry_failed_retrieval_collection_jobs(
    collection_id: str,
    payload: RetrievalRetryFailedJobsRequest,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    snapshot = service.get_collection_snapshot(collection_id=collection_id)
    if snapshot is None:
        raise _collection_not_found(collection_id)
    result = service.retry_collection_failed_jobs(
        collection_id=collection_id,
        limit=payload.limit,
    )
    return result.model_dump(mode="json")


@router.post("/api/rp/retrieval/jobs/{job_id}/retry")
async def retry_retrieval_job(
    job_id: str,
    service: RetrievalIngestionService = Depends(_ingestion_service),
):
    try:
        job = service.retry_failed_job(job_id=job_id)
    except ValueError as exc:
        raise _job_failed(exc, code="retrieval_job_retry_failed") from exc
    return job.model_dump(mode="json")
