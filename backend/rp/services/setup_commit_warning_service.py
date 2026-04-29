"""Shared commit-warning collection for setup commit proposal paths."""
from __future__ import annotations

from typing import Any

from rp.models.setup_workspace import (
    CommitProposalStatus,
    QuestionSeverity,
    QuestionStatus,
    SetupStepId,
)


def collect_setup_commit_warning_codes(
    *,
    workspace: Any,
    runtime_state_service: Any | None,
    workspace_id: str,
    step_id: SetupStepId,
) -> list[str]:
    """Return lightweight readiness warnings without blocking explicit commit."""
    warnings = _cognitive_commit_warning_codes(
        runtime_state_service=runtime_state_service,
        workspace_id=workspace_id,
        step_id=step_id,
    )

    blocking_questions = [
        question
        for question in getattr(workspace, "open_questions", [])
        if _same_value(getattr(question, "step_id", None), step_id)
        and _same_value(getattr(question, "status", None), QuestionStatus.OPEN)
        and _same_value(getattr(question, "severity", None), QuestionSeverity.BLOCKING)
    ]
    if blocking_questions:
        warnings.append("blocking_questions_present")

    latest_proposal = _latest_step_proposal(workspace=workspace, step_id=step_id)
    if latest_proposal is not None and _same_value(
        getattr(latest_proposal, "status", None),
        CommitProposalStatus.REJECTED,
    ):
        warnings.append("previous_proposal_rejected")

    return list(dict.fromkeys(warnings))


def _cognitive_commit_warning_codes(
    *,
    runtime_state_service: Any | None,
    workspace_id: str,
    step_id: SetupStepId,
) -> list[str]:
    if runtime_state_service is None:
        return []
    snapshot = runtime_state_service.get_snapshot(
        workspace_id=workspace_id,
        step_id=step_id,
    )
    if snapshot is None:
        return []

    warnings: list[str] = []
    if snapshot.invalidated:
        warnings.append("cognitive_state_invalidated")

    truth_write = snapshot.active_truth_write
    if truth_write is None:
        return warnings
    if not truth_write.ready_for_review:
        warnings.append("truth_write_not_ready_for_review")
    if truth_write.remaining_open_issues:
        warnings.append("truth_write_open_issues_present")
    return warnings


def _latest_step_proposal(*, workspace: Any, step_id: SetupStepId) -> Any | None:
    proposals = [
        proposal
        for proposal in getattr(workspace, "commit_proposals", [])
        if _same_value(getattr(proposal, "step_id", None), step_id)
    ]
    if not proposals:
        return None
    return max(
        proposals,
        key=lambda item: (
            _datetime_key(getattr(item, "reviewed_at", None)),
            _datetime_key(getattr(item, "created_at", None)),
        ),
    )


def _same_value(left: Any, right: Any) -> bool:
    return _enum_value(left) == _enum_value(right)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _datetime_key(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    return 0.0
