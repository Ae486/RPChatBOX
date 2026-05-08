"""Turn-scoped runtime workflow job ledger service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)


CREATION_TIME_OBLIGATION_KINDS: tuple[RuntimeWorkflowJobKind, ...] = (
    RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
    RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeWorkflowJobServiceError(ValueError):
    """Stable runtime workflow job error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class TurnSettlementEvaluation:
    """Structured settlement decision derived only from turn acceptance + jobs."""

    eligible: bool
    settlement_reason: str | None
    required_job_ids: tuple[str, ...]
    blocking_job_ids: tuple[str, ...]


class RuntimeWorkflowJobService:
    """Own the durable, turn-scoped workflow job ledger."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_creation_time_obligations(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        source_ref_ids: Iterable[str] = (),
        trace_refs: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> list[RuntimeWorkflowJobRecord]:
        """Create required post-write obligations exactly once per turn.

        This method is intentionally thin and deterministic because the owner
        boundary is the turn-domain finalize transaction. Post-write graph nodes
        may call it for idempotent recovery, but the first registration belongs
        to `StoryTurnDomainService.persist_generated_artifact(...)`.
        """

        return [
            self.ensure_job(
                identity=identity,
                job_kind=job_kind,
                job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
                creation_mode=(
                    RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION
                ),
                required_for_turn_completion=True,
                source_ref_ids=source_ref_ids,
                trace_refs=trace_refs,
                metadata={
                    **dict(metadata or {}),
                    "obligation_owner": "story_turn_domain.persist_generated_artifact",
                },
            )
            for job_kind in CREATION_TIME_OBLIGATION_KINDS
        ]

    def ensure_job(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        job_kind: RuntimeWorkflowJobKind,
        job_category: RuntimeWorkflowJobCategory,
        creation_mode: RuntimeWorkflowJobCreationMode,
        required_for_turn_completion: bool,
        source_ref_ids: Iterable[str] = (),
        result_ref_ids: Iterable[str] = (),
        trace_refs: Iterable[str] = (),
        worker_id: str | None = None,
        parent_job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWorkflowJobRecord:
        turn = self._require_turn(identity)
        idempotency_key = _job_idempotency_key(
            turn_id=identity.turn_id,
            job_kind=job_kind,
            creation_mode=creation_mode,
        )
        existing = self._get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        now = _utcnow()
        record = RuntimeWorkflowJobRecord(
            job_id=f"runtime-job:{uuid4().hex}",
            turn_id=identity.turn_id,
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            job_kind=job_kind.value,
            job_category=job_category.value,
            status=RuntimeWorkflowJobStatus.PENDING.value,
            creation_mode=creation_mode.value,
            required_for_turn_completion=required_for_turn_completion,
            worker_id=_optional_text(worker_id),
            parent_job_id=_optional_text(parent_job_id),
            idempotency_key=idempotency_key,
            source_ref_ids_json=_unique_non_blank(source_ref_ids),
            result_ref_ids_json=_unique_non_blank(result_ref_ids),
            trace_refs_json=_unique_non_blank(trace_refs),
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.add(turn)
        self._session.flush()
        return record

    def mark_job_running(
        self,
        *,
        job_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWorkflowJobRecord:
        job = self._require_job(job_id)
        if _is_terminal_status(job.status):
            return job
        now = _utcnow()
        job.status = RuntimeWorkflowJobStatus.RUNNING.value
        job.attempt_count += 1
        job.started_at = job.started_at or now
        job.updated_at = now
        job.metadata_json = {
            **dict(job.metadata_json or {}),
            **dict(metadata or {}),
            "running_reason": _require_non_blank(reason, field_name="reason"),
        }
        self._session.add(job)
        self._session.flush()
        return job

    def mark_job_completed(
        self,
        *,
        job_id: str,
        reason: str,
        result_ref_ids: Iterable[str] = (),
        trace_refs: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWorkflowJobRecord:
        job = self._require_job(job_id)
        if _is_terminal_status(job.status):
            return job
        now = _utcnow()
        job.status = RuntimeWorkflowJobStatus.COMPLETED.value
        job.completion_reason = _require_non_blank(reason, field_name="reason")
        job.completed_at = now
        job.updated_at = now
        job.result_ref_ids_json = _merge_unique_non_blank(
            job.result_ref_ids_json,
            result_ref_ids,
        )
        job.trace_refs_json = _merge_unique_non_blank(
            job.trace_refs_json,
            trace_refs,
        )
        job.metadata_json = {
            **dict(job.metadata_json or {}),
            **dict(metadata or {}),
        }
        self._session.add(job)
        self._session.flush()
        return job

    def mark_job_deferred(
        self,
        *,
        job_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeWorkflowJobRecord:
        job = self._require_job(job_id)
        if _is_terminal_status(job.status):
            return job
        now = _utcnow()
        job.status = RuntimeWorkflowJobStatus.DEFERRED.value
        job.completion_reason = _require_non_blank(reason, field_name="reason")
        job.completed_at = now
        job.updated_at = now
        job.metadata_json = {
            **dict(job.metadata_json or {}),
            **dict(metadata or {}),
        }
        self._session.add(job)
        self._session.flush()
        return job

    def list_jobs_for_turn(
        self,
        *,
        turn_id: str,
    ) -> list[RuntimeWorkflowJobRecord]:
        stmt = (
            select(RuntimeWorkflowJobRecord)
            .where(RuntimeWorkflowJobRecord.turn_id == turn_id)
            .order_by(RuntimeWorkflowJobRecord.created_at.asc())
            .order_by(RuntimeWorkflowJobRecord.job_id.asc())
        )
        return list(self._session.exec(stmt).all())

    def mark_required_jobs_deferred(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        reason: str,
        job_kinds: Iterable[RuntimeWorkflowJobKind] = CREATION_TIME_OBLIGATION_KINDS,
        metadata: dict[str, Any] | None = None,
    ) -> list[RuntimeWorkflowJobRecord]:
        normalized_reason = _require_non_blank(reason, field_name="reason")
        jobs_by_kind = {
            job.job_kind: job for job in self.list_jobs_for_turn(turn_id=identity.turn_id)
        }
        updated: list[RuntimeWorkflowJobRecord] = []
        now = _utcnow()
        for job_kind in job_kinds:
            job = jobs_by_kind.get(job_kind.value)
            if job is None:
                continue
            if job.status in {
                RuntimeWorkflowJobStatus.COMPLETED.value,
                RuntimeWorkflowJobStatus.FAILED.value,
                RuntimeWorkflowJobStatus.CANCELLED.value,
                RuntimeWorkflowJobStatus.DEFERRED.value,
            }:
                updated.append(job)
                continue
            job.status = RuntimeWorkflowJobStatus.DEFERRED.value
            job.completion_reason = normalized_reason
            job.completed_at = now
            job.updated_at = now
            job.metadata_json = {
                **dict(job.metadata_json or {}),
                **dict(metadata or {}),
            }
            self._session.add(job)
            updated.append(job)
        self._session.flush()
        return updated

    def mark_required_jobs_completed(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        reason: str,
        job_kinds: Iterable[RuntimeWorkflowJobKind] = CREATION_TIME_OBLIGATION_KINDS,
        metadata: dict[str, Any] | None = None,
    ) -> list[RuntimeWorkflowJobRecord]:
        normalized_reason = _require_non_blank(reason, field_name="reason")
        jobs_by_kind = {
            job.job_kind: job for job in self.list_jobs_for_turn(turn_id=identity.turn_id)
        }
        updated: list[RuntimeWorkflowJobRecord] = []
        for job_kind in job_kinds:
            job = jobs_by_kind.get(job_kind.value)
            if job is None:
                continue
            updated.append(
                self.mark_job_completed(
                    job_id=job.job_id,
                    reason=normalized_reason,
                    metadata=metadata,
                )
            )
        return updated

    def all_required_jobs_terminal(
        self,
        *,
        turn_id: str,
    ) -> bool:
        required = [
            job
            for job in self.list_jobs_for_turn(turn_id=turn_id)
            if job.required_for_turn_completion
        ]
        if not required:
            return False
        terminal = {
            RuntimeWorkflowJobStatus.COMPLETED.value,
            RuntimeWorkflowJobStatus.DEFERRED.value,
        }
        return all(job.status in terminal for job in required)

    def required_jobs_have_deferred(
        self,
        *,
        turn_id: str,
    ) -> bool:
        return any(
            job.required_for_turn_completion
            and job.status == RuntimeWorkflowJobStatus.DEFERRED.value
            for job in self.list_jobs_for_turn(turn_id=turn_id)
        )

    def evaluate_turn_settlement(
        self,
        *,
        turn_id: str,
    ) -> TurnSettlementEvaluation:
        turn = self._session.get(StoryTurnRecord, turn_id)
        if turn is None:
            raise RuntimeWorkflowJobServiceError(
                "runtime_workflow_turn_not_found",
                turn_id,
            )
        required_jobs = [
            job
            for job in self.list_jobs_for_turn(turn_id=turn_id)
            if job.required_for_turn_completion
        ]
        required_job_ids = tuple(job.job_id for job in required_jobs)
        if turn.acceptance_state not in {"accepted", "auto_accepted"}:
            return TurnSettlementEvaluation(
                eligible=False,
                settlement_reason=None,
                required_job_ids=required_job_ids,
                blocking_job_ids=(),
            )
        if not required_jobs:
            return TurnSettlementEvaluation(
                eligible=False,
                settlement_reason=None,
                required_job_ids=(),
                blocking_job_ids=(),
            )
        blocking_jobs = [
            job
            for job in required_jobs
            if job.status not in _SETTLEMENT_TERMINAL_STATUSES
        ]
        if blocking_jobs:
            return TurnSettlementEvaluation(
                eligible=False,
                settlement_reason=None,
                required_job_ids=required_job_ids,
                blocking_job_ids=tuple(job.job_id for job in blocking_jobs),
            )
        settlement_reason = (
            "required_jobs_deferred_by_policy"
            if any(
                job.status != RuntimeWorkflowJobStatus.COMPLETED.value
                for job in required_jobs
            )
            else "all_required_jobs_completed"
        )
        return TurnSettlementEvaluation(
            eligible=True,
            settlement_reason=settlement_reason,
            required_job_ids=required_job_ids,
            blocking_job_ids=(),
        )

    def _require_turn(self, identity: MemoryRuntimeIdentity) -> StoryTurnRecord:
        record = self._session.get(StoryTurnRecord, identity.turn_id)
        if record is None:
            raise RuntimeWorkflowJobServiceError(
                "runtime_workflow_turn_not_found",
                identity.turn_id,
            )
        if (
            record.story_id != identity.story_id
            or record.session_id != identity.session_id
            or record.branch_head_id != identity.branch_head_id
            or record.runtime_profile_snapshot_id
            != identity.runtime_profile_snapshot_id
        ):
            raise RuntimeWorkflowJobServiceError(
                "runtime_workflow_identity_mismatch",
                identity.turn_id,
            )
        return record

    def _get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> RuntimeWorkflowJobRecord | None:
        stmt = select(RuntimeWorkflowJobRecord).where(
            RuntimeWorkflowJobRecord.idempotency_key == idempotency_key
        )
        return self._session.exec(stmt).first()

    def _require_job(self, job_id: str) -> RuntimeWorkflowJobRecord:
        normalized_job_id = _require_non_blank(job_id, field_name="job_id")
        record = self._session.get(RuntimeWorkflowJobRecord, normalized_job_id)
        if record is None:
            raise RuntimeWorkflowJobServiceError(
                "runtime_workflow_job_not_found",
                normalized_job_id,
            )
        return record


def _job_idempotency_key(
    *,
    turn_id: str,
    job_kind: RuntimeWorkflowJobKind,
    creation_mode: RuntimeWorkflowJobCreationMode,
) -> str:
    return f"{turn_id}:{creation_mode.value}:{job_kind.value}"


def _optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _unique_non_blank(values: Iterable[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values


def _merge_unique_non_blank(
    existing: Iterable[str],
    incoming: Iterable[str],
) -> list[str]:
    return _unique_non_blank([*list(existing), *list(incoming)])


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise RuntimeWorkflowJobServiceError(
            "runtime_workflow_required_field_blank",
            field_name,
        )
    return normalized


_SETTLEMENT_TERMINAL_STATUSES: set[str] = {
    RuntimeWorkflowJobStatus.COMPLETED.value,
    RuntimeWorkflowJobStatus.DEFERRED.value,
}


def _is_terminal_status(status: str) -> bool:
    return status in {
        RuntimeWorkflowJobStatus.COMPLETED.value,
        RuntimeWorkflowJobStatus.FAILED.value,
        RuntimeWorkflowJobStatus.CANCELLED.value,
        RuntimeWorkflowJobStatus.DEFERRED.value,
    }
