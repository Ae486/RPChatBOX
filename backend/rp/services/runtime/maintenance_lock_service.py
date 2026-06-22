"""Deterministic current-branch maintenance lock read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable

from sqlmodel import Session, select

from models.rp_memory_store import MemoryProposalRecord
from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.errors import RPError
from rp.models.runtime.reason_codes import SchedulerReasonCode
from rp.models.runtime.workflow_job import RuntimeWorkflowJobStatus


class RuntimeMaintenanceOperation(StrEnum):
    """Operation families guarded by the W5-A/S3 maintenance lock."""

    CORE_MEMORY_EDIT = "core_memory_edit"
    PROJECTION_EDIT = "projection_edit"
    MANUAL_ACCEPTED_PROSE_EDIT = "manual_accepted_prose_edit"
    STORY_PROGRESSION = "story_progression"
    ROLLBACK = "rollback"
    BRANCH_SWITCH = "branch_switch"
    BRANCH_CREATE = "branch_create"
    REWRITE = "rewrite"
    REGENERATE = "regenerate"
    CHAPTER_COMPLETE = "chapter_complete"
    STORY_EVOLUTION_OR_ARCHIVAL_EDIT = "story_evolution_or_archival_edit"
    INSPECT_DEBUG = "inspect_debug"
    PROPOSAL_ACCEPT = "proposal_accept"
    PROPOSAL_REJECT = "proposal_reject"
    PROPOSAL_DISCARD = "proposal_discard"
    PROPOSAL_EDIT = "proposal_edit"
    FAILED_WORKER_RETRY = "failed_worker_retry"
    RUNTIME_CONFIG_EDIT = "runtime_config_edit"


BLOCKED_DURING_MAINTENANCE: frozenset[RuntimeMaintenanceOperation] = frozenset(
    {
        RuntimeMaintenanceOperation.CORE_MEMORY_EDIT,
        RuntimeMaintenanceOperation.PROJECTION_EDIT,
        RuntimeMaintenanceOperation.MANUAL_ACCEPTED_PROSE_EDIT,
        RuntimeMaintenanceOperation.STORY_PROGRESSION,
        RuntimeMaintenanceOperation.ROLLBACK,
        RuntimeMaintenanceOperation.BRANCH_SWITCH,
        RuntimeMaintenanceOperation.BRANCH_CREATE,
        RuntimeMaintenanceOperation.REWRITE,
        RuntimeMaintenanceOperation.REGENERATE,
        RuntimeMaintenanceOperation.CHAPTER_COMPLETE,
        RuntimeMaintenanceOperation.STORY_EVOLUTION_OR_ARCHIVAL_EDIT,
    }
)

ALLOWED_DURING_MAINTENANCE: frozenset[RuntimeMaintenanceOperation] = frozenset(
    {
        RuntimeMaintenanceOperation.INSPECT_DEBUG,
        RuntimeMaintenanceOperation.PROPOSAL_ACCEPT,
        RuntimeMaintenanceOperation.PROPOSAL_REJECT,
        RuntimeMaintenanceOperation.PROPOSAL_DISCARD,
        RuntimeMaintenanceOperation.PROPOSAL_EDIT,
        RuntimeMaintenanceOperation.FAILED_WORKER_RETRY,
        RuntimeMaintenanceOperation.RUNTIME_CONFIG_EDIT,
    }
)

_JOB_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        RuntimeWorkflowJobStatus.COMPLETED.value,
        RuntimeWorkflowJobStatus.DEFERRED.value,
        RuntimeWorkflowJobStatus.FAILED.value,
        RuntimeWorkflowJobStatus.CANCELLED.value,
    }
)

_PROPOSAL_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "applied",
        "rejected",
        "discarded",
        "failed",
        "invalid",
        "superseded",
        "cancelled",
    }
)


class RuntimeMaintenanceLockError(RPError, ValueError):
    """Stable lock rejection with the central scheduler reason code."""

    def __init__(
        self,
        *,
        operation: RuntimeMaintenanceOperation,
        causes: Iterable["RuntimeMaintenanceLockCause"],
    ) -> None:
        self.code = SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
        self.operation = operation.value
        self.causes = tuple(causes)
        super().__init__(f"{self.code}:{operation.value}")


@dataclass(frozen=True)
class RuntimeMaintenanceLockCause:
    """One persisted state row that currently keeps maintenance locked."""

    reason_code: str
    source_kind: str
    source_id: str
    story_id: str
    session_id: str
    branch_head_id: str
    status: str
    turn_id: str | None = None
    operation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMaintenanceLockState:
    """Current lock state for one story/session/branch."""

    story_id: str
    session_id: str
    branch_head_id: str
    active: bool
    reason_code: str | None
    causes: tuple[RuntimeMaintenanceLockCause, ...]


@dataclass(frozen=True)
class RuntimeMaintenanceLockDecision:
    """Operation-level allow/block decision under the current lock state."""

    operation: RuntimeMaintenanceOperation
    allowed: bool
    reason_code: str | None
    causes: tuple[RuntimeMaintenanceLockCause, ...]


class RuntimeMaintenanceLockService:
    """Evaluate W5-A/S3 maintenance blockers without invoking workers or LLMs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def evaluate(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
    ) -> RuntimeMaintenanceLockState:
        story_id = _require_text(story_id, field_name="story_id")
        session_id = _require_text(session_id, field_name="session_id")
        branch_head_id = _require_text(branch_head_id, field_name="branch_head_id")
        causes = (
            *self._workflow_job_causes(
                story_id=story_id,
                session_id=session_id,
                branch_head_id=branch_head_id,
            ),
            *self._proposal_causes(
                story_id=story_id,
                session_id=session_id,
                branch_head_id=branch_head_id,
            ),
        )
        return RuntimeMaintenanceLockState(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            active=bool(causes),
            reason_code=(
                SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
                if causes
                else None
            ),
            causes=causes,
        )

    def check_operation(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        operation: RuntimeMaintenanceOperation | str,
    ) -> RuntimeMaintenanceLockDecision:
        normalized_operation = _coerce_operation(operation)
        state = self.evaluate(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
        )
        if not state.active or normalized_operation in ALLOWED_DURING_MAINTENANCE:
            return RuntimeMaintenanceLockDecision(
                operation=normalized_operation,
                allowed=True,
                reason_code=None,
                causes=state.causes,
            )
        if normalized_operation in BLOCKED_DURING_MAINTENANCE:
            causes = tuple(
                cause_with_operation(cause, normalized_operation)
                for cause in state.causes
            )
            return RuntimeMaintenanceLockDecision(
                operation=normalized_operation,
                allowed=False,
                reason_code=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
                causes=causes,
            )
        return RuntimeMaintenanceLockDecision(
            operation=normalized_operation,
            allowed=False,
            reason_code=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
            causes=state.causes,
        )

    def require_allowed(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        operation: RuntimeMaintenanceOperation | str,
    ) -> RuntimeMaintenanceLockDecision:
        decision = self.check_operation(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            operation=operation,
        )
        if not decision.allowed:
            raise RuntimeMaintenanceLockError(
                operation=decision.operation,
                causes=decision.causes,
            )
        return decision

    def _workflow_job_causes(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
    ) -> tuple[RuntimeMaintenanceLockCause, ...]:
        stmt = (
            select(RuntimeWorkflowJobRecord)
            .where(RuntimeWorkflowJobRecord.story_id == story_id)
            .where(RuntimeWorkflowJobRecord.session_id == session_id)
            .where(RuntimeWorkflowJobRecord.branch_head_id == branch_head_id)
            .where(RuntimeWorkflowJobRecord.required_for_turn_completion == True)  # noqa: E712
            .order_by(RuntimeWorkflowJobRecord.created_at.asc())
            .order_by(RuntimeWorkflowJobRecord.job_id.asc())
        )
        causes: list[RuntimeMaintenanceLockCause] = []
        for job in self._session.exec(stmt).all():
            if str(job.status or "").strip() in _JOB_TERMINAL_STATUSES:
                continue
            causes.append(
                RuntimeMaintenanceLockCause(
                    reason_code=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
                    source_kind="runtime_job",
                    source_id=job.job_id,
                    story_id=job.story_id,
                    session_id=job.session_id,
                    branch_head_id=job.branch_head_id,
                    turn_id=job.turn_id,
                    status=job.status,
                    metadata={
                        "job_kind": job.job_kind,
                        "job_category": job.job_category,
                        "creation_mode": job.creation_mode,
                        "anchor_turn_id": job.anchor_turn_id,
                        "worker_id": job.worker_id,
                    },
                )
            )
        return tuple(causes)

    def _proposal_causes(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
    ) -> tuple[RuntimeMaintenanceLockCause, ...]:
        stmt = (
            select(MemoryProposalRecord)
            .where(MemoryProposalRecord.story_id == story_id)
            .where(MemoryProposalRecord.session_id == session_id)
            .order_by(MemoryProposalRecord.created_at.asc())
            .order_by(MemoryProposalRecord.proposal_id.asc())
        )
        causes: list[RuntimeMaintenanceLockCause] = []
        for proposal in self._session.exec(stmt).all():
            status = str(proposal.status or "").strip()
            if status in _PROPOSAL_TERMINAL_STATUSES:
                continue
            proposal_branch_id = _proposal_branch_head_id(proposal)
            if proposal_branch_id != branch_head_id:
                continue
            causes.append(
                RuntimeMaintenanceLockCause(
                    reason_code=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
                    source_kind="proposal",
                    source_id=proposal.proposal_id,
                    story_id=proposal.story_id,
                    session_id=proposal.session_id or session_id,
                    branch_head_id=proposal_branch_id,
                    turn_id=_proposal_turn_id(proposal),
                    status=status,
                    metadata={
                        "policy_decision": proposal.policy_decision,
                        "domain": proposal.domain,
                        "domain_path": proposal.domain_path,
                        "submit_source": proposal.submit_source,
                        "trace_id": proposal.trace_id,
                    },
                )
            )
        return tuple(causes)


def cause_with_operation(
    cause: RuntimeMaintenanceLockCause,
    operation: RuntimeMaintenanceOperation,
) -> RuntimeMaintenanceLockCause:
    return RuntimeMaintenanceLockCause(
        reason_code=cause.reason_code,
        source_kind=cause.source_kind,
        source_id=cause.source_id,
        story_id=cause.story_id,
        session_id=cause.session_id,
        branch_head_id=cause.branch_head_id,
        status=cause.status,
        turn_id=cause.turn_id,
        operation=operation.value,
        metadata=dict(cause.metadata),
    )


def _proposal_branch_head_id(proposal: MemoryProposalRecord) -> str | None:
    identity = _proposal_identity(proposal)
    if not isinstance(identity, dict):
        return None
    text = str(identity.get("branch_head_id") or "").strip()
    return text or None


def _proposal_turn_id(proposal: MemoryProposalRecord) -> str | None:
    identity = _proposal_identity(proposal)
    if not isinstance(identity, dict):
        return None
    text = str(identity.get("turn_id") or "").strip()
    return text or None


def _proposal_identity(proposal: MemoryProposalRecord) -> dict[str, Any] | None:
    metadata = proposal.governance_metadata_json or {}
    if not isinstance(metadata, dict):
        return None
    identity = metadata.get("identity")
    return identity if isinstance(identity, dict) else None


def _coerce_operation(
    operation: RuntimeMaintenanceOperation | str,
) -> RuntimeMaintenanceOperation:
    if isinstance(operation, RuntimeMaintenanceOperation):
        return operation
    normalized = str(operation or "").strip()
    try:
        return RuntimeMaintenanceOperation(normalized)
    except ValueError as exc:
        raise ValueError(
            f"runtime_maintenance_operation_unknown:{normalized}"
        ) from exc


def _require_text(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text
