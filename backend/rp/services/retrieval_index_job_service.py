"""Index job lifecycle service for retrieval-core."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import select

from models.rp_retrieval_store import IndexJobRecord
from rp.models.retrieval_records import IndexJob


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetrievalIndexJobService:
    """Persist lightweight ingest and reindex jobs."""

    def __init__(self, session) -> None:
        self._session = session

    def submit_ingest_job(
        self,
        *,
        story_id: str,
        asset_id: str,
        collection_id: str | None = None,
    ) -> IndexJob:
        now = _utcnow()
        record = IndexJobRecord(
            job_id=f"index_{uuid4().hex}",
            story_id=story_id,
            asset_id=asset_id,
            collection_id=collection_id,
            job_kind="ingest",
            job_state="queued",
            target_refs_json=[f"asset:{asset_id}"],
            warnings_json=[],
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        self._session.add(record)
        return self._record_to_model(record)

    def submit_reindex_job(
        self,
        *,
        story_id: str,
        target_refs: list[str],
        collection_id: str | None = None,
    ) -> IndexJob:
        now = _utcnow()
        asset_ref = next((item.split("asset:", 1)[1] for item in target_refs if item.startswith("asset:")), None)
        record = IndexJobRecord(
            job_id=f"index_{uuid4().hex}",
            story_id=story_id,
            asset_id=asset_ref,
            collection_id=collection_id,
            job_kind="reindex",
            job_state="queued",
            target_refs_json=list(target_refs),
            warnings_json=[],
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        self._session.add(record)
        return self._record_to_model(record)

    def get_job(self, job_id: str) -> IndexJob | None:
        record = self._session.get(IndexJobRecord, job_id)
        return self._record_to_model(record) if record is not None else None

    def list_story_jobs(self, story_id: str) -> list[IndexJob]:
        stmt = select(IndexJobRecord).where(IndexJobRecord.story_id == story_id)
        return [self._record_to_model(record) for record in self._session.exec(stmt).all()]

    def update_job_state(
        self,
        *,
        job_id: str,
        state: str,
        warnings: list[str] | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> IndexJob:
        record = self._session.get(IndexJobRecord, job_id)
        if record is None:
            raise ValueError(f"IndexJob not found: {job_id}")
        record.job_state = state
        record.warnings_json = list(warnings or [])
        record.error_message = error_message
        record.updated_at = _utcnow()
        if started_at is not None:
            record.started_at = started_at
        if completed_at is not None:
            record.completed_at = completed_at
        self._session.add(record)
        return self._record_to_model(record)

    @staticmethod
    def _record_to_model(record: IndexJobRecord) -> IndexJob:
        return IndexJob.model_validate(
            {
                "job_id": record.job_id,
                "story_id": record.story_id,
                "asset_id": record.asset_id,
                "collection_id": record.collection_id,
                "job_kind": record.job_kind,
                "job_state": record.job_state,
                "target_refs": record.target_refs_json,
                "warnings": record.warnings_json,
                "error_message": record.error_message,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
            }
        )
