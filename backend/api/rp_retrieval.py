"""Retrieval maintenance and observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

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


def _maintenance_service(
    session: Session = Depends(get_session),
) -> RetrievalMaintenanceService:
    return RetrievalMaintenanceService(session)


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


@router.get("/api/rp/retrieval/stories/{story_id}/maintenance")
async def get_retrieval_story_maintenance(
    story_id: str,
    service: RetrievalMaintenanceService = Depends(_maintenance_service),
):
    return service.get_story_snapshot(story_id=story_id).model_dump(mode="json")


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
