"""Deterministic current-branch maintenance lock read model.

Lock v2 (REV-006 rev 2): the lock no longer blocks user operations. It survives
only as (1) a branch-scoped maintenance-exclusion read model — consulted by the
post-write trigger so a second maintenance run defers while another is in flight
on the same branch — and (2) the state visibility surface for debug/read models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from models.rp_memory_store import MemoryProposalRecord
from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.models.runtime.reason_codes import SchedulerReasonCode
from rp.models.runtime.workflow_job import RuntimeWorkflowJobStatus


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


@dataclass(frozen=True)
class RuntimeMaintenanceLockCause:
    """One persisted state row that currently keeps maintenance active."""

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
    """Current maintenance-exclusion state for one story/session/branch."""

    story_id: str
    session_id: str
    branch_head_id: str
    active: bool
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


def _require_text(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text
