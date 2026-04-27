"""Runtime-private cross-turn cognitive state storage for SetupAgent."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_setup_store import SetupAgentRuntimeStateRecord
from rp.agent_runtime.contracts import (
    ChunkCandidate,
    DiscussionState,
    DraftTruthWrite,
    SetupContextCompactSummary,
    SetupCognitiveSourceBasis,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_workspace import CommitProposalStatus, SetupStepId
from rp.services.setup_context_governor import SetupContextGovernorService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupAgentRuntimeStateService:
    """Persist and reconcile runtime-private setup cognitive state across turns."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._context_governor = SetupContextGovernorService()

    def get_snapshot(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
    ) -> SetupCognitiveStateSnapshot | None:
        record = self._get_record(workspace_id=workspace_id, step_id=step_id)
        if record is None:
            return None
        return SetupCognitiveStateSnapshot.model_validate(record.snapshot_json)

    def save_snapshot(
        self,
        snapshot: SetupCognitiveStateSnapshot,
    ) -> SetupCognitiveStateSnapshot:
        step_id = SetupStepId(snapshot.current_step)
        record = self._get_record(
            workspace_id=snapshot.workspace_id,
            step_id=step_id,
        )
        now = _utcnow()
        payload = snapshot.model_dump(mode="json", exclude_none=True)
        if record is None:
            record = SetupAgentRuntimeStateRecord(
                runtime_state_id=uuid4().hex,
                workspace_id=snapshot.workspace_id,
                step_id=step_id.value,
                state_version=snapshot.state_version,
                snapshot_json=payload,
                created_at=now,
                updated_at=now,
            )
        else:
            record.state_version = snapshot.state_version
            record.snapshot_json = payload
            record.updated_at = now
        self._session.add(record)
        self._session.commit()
        return SetupCognitiveStateSnapshot.model_validate(record.snapshot_json)

    def replace_discussion_state(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
        discussion_state: DiscussionState,
    ) -> SetupCognitiveStateSnapshot:
        snapshot = self._ensure_snapshot(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        snapshot.discussion_state = discussion_state
        snapshot.invalidated = False
        snapshot.invalidation_reasons = []
        snapshot.source_basis = self._build_source_basis(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        return self.save_snapshot(snapshot)

    def upsert_chunk(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
        chunk: ChunkCandidate,
        action: str,
    ) -> SetupCognitiveStateSnapshot:
        snapshot = self._ensure_snapshot(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        existing_index = next(
            (
                index
                for index, item in enumerate(snapshot.chunk_candidates)
                if item.candidate_id == chunk.candidate_id
            ),
            None,
        )
        if action == "promote" and chunk.detail_level != "truth_candidate":
            chunk = chunk.model_copy(update={"detail_level": "truth_candidate"})

        if existing_index is None:
            snapshot.chunk_candidates.append(chunk)
        else:
            snapshot.chunk_candidates[existing_index] = chunk

        snapshot.invalidated = False
        snapshot.invalidation_reasons = []
        snapshot.source_basis = self._build_source_basis(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        return self.save_snapshot(snapshot)

    def record_truth_write(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
        truth_write: DraftTruthWrite,
    ) -> SetupCognitiveStateSnapshot:
        snapshot = self._ensure_snapshot(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        snapshot.active_truth_write = truth_write
        snapshot.invalidated = False
        snapshot.invalidation_reasons = []
        snapshot.source_basis = self._build_source_basis(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        return self.save_snapshot(snapshot)

    def reconcile_snapshot(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
    ) -> SetupCognitiveStateSnapshot | None:
        snapshot = self.get_snapshot(
            workspace_id=workspace.workspace_id,
            step_id=step_id,
        )
        if snapshot is None:
            return None

        source_basis = self._build_source_basis(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        reasons: list[str] = []
        if source_basis.pending_user_edit_delta_ids:
            reasons.append("user_edit_delta")
        if source_basis.last_proposal_status == CommitProposalStatus.REJECTED.value:
            reasons.append("proposal_rejected")

        basis_changed = (
            snapshot.source_basis.workspace_version != source_basis.workspace_version
            or snapshot.source_basis.draft_fingerprint != source_basis.draft_fingerprint
        )
        if basis_changed and not source_basis.pending_user_edit_delta_ids:
            reasons.append("draft_changed_without_delta")

        if reasons:
            snapshot = self._invalidate_snapshot(
                snapshot=snapshot,
                reasons=reasons,
                context_packet=context_packet,
            )

        snapshot.source_basis = source_basis
        return self.save_snapshot(snapshot)

    def summarize_for_prompt(
        self,
        snapshot: SetupCognitiveStateSnapshot | None,
    ) -> SetupCognitiveStateSummary | None:
        if snapshot is None:
            return None

        discussion_topic = None
        confirmed_points: list[str] = []
        open_questions: list[str] = []
        unresolved_conflicts: list[str] = []
        if snapshot.discussion_state is not None:
            discussion_topic = snapshot.discussion_state.discussion_topic
            confirmed_points = list(snapshot.discussion_state.confirmed_points[:6])
            open_questions = list(snapshot.discussion_state.open_questions[:4])
            unresolved_conflicts = list(snapshot.discussion_state.unresolved_conflicts[:4])

        candidate_titles = [item.title for item in snapshot.chunk_candidates[:6]]
        truth_write_status: str | None = None
        ready_for_review = False
        remaining_open_issues: list[str] = []
        if snapshot.active_truth_write is not None:
            truth_write_status = (
                "ready_for_review"
                if snapshot.active_truth_write.ready_for_review
                else "needs_refinement"
            )
            ready_for_review = snapshot.active_truth_write.ready_for_review
            remaining_open_issues = list(snapshot.active_truth_write.remaining_open_issues[:4])

        return SetupCognitiveStateSummary(
            current_step=snapshot.current_step,
            invalidated=snapshot.invalidated,
            invalidation_reasons=list(snapshot.invalidation_reasons),
            discussion_topic=discussion_topic,
            confirmed_points=confirmed_points,
            open_questions=open_questions,
            unresolved_conflicts=unresolved_conflicts,
            candidate_titles=candidate_titles,
            truth_write_status=truth_write_status,
            ready_for_review=ready_for_review,
            remaining_open_issues=remaining_open_issues,
            working_digest=snapshot.working_digest,
            tool_outcomes=list(snapshot.tool_outcomes),
            compact_summary=snapshot.compact_summary,
        )

    def persist_turn_governance(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
        working_digest: SetupWorkingDigest | None,
        tool_outcomes: list[SetupToolOutcome],
        compact_summary: SetupContextCompactSummary | None,
    ) -> SetupCognitiveStateSnapshot | None:
        snapshot = self.get_snapshot(
            workspace_id=workspace.workspace_id,
            step_id=step_id,
        )
        if (
            snapshot is None
            and working_digest is None
            and not tool_outcomes
            and compact_summary is None
        ):
            return None

        ensured_snapshot = self._ensure_snapshot(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        ensured_snapshot.working_digest = working_digest
        ensured_snapshot.tool_outcomes = self._context_governor.retain_tool_outcomes(
            existing=ensured_snapshot.tool_outcomes,
            latest_results=tool_outcomes,
        )
        ensured_snapshot.compact_summary = compact_summary
        ensured_snapshot.source_basis = self._build_source_basis(
            workspace=workspace,
            context_packet=context_packet,
            step_id=step_id,
        )
        return self.save_snapshot(ensured_snapshot)

    def _ensure_snapshot(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
    ) -> SetupCognitiveStateSnapshot:
        snapshot = self.get_snapshot(
            workspace_id=workspace.workspace_id,
            step_id=step_id,
        )
        if snapshot is not None:
            snapshot.source_basis = self._build_source_basis(
                workspace=workspace,
                context_packet=context_packet,
                step_id=step_id,
            )
            return snapshot
        return SetupCognitiveStateSnapshot(
            workspace_id=workspace.workspace_id,
            current_step=step_id.value,
            state_version=1,
            source_basis=self._build_source_basis(
                workspace=workspace,
                context_packet=context_packet,
                step_id=step_id,
            ),
        )

    def _invalidate_snapshot(
        self,
        *,
        snapshot: SetupCognitiveStateSnapshot,
        reasons: list[str],
        context_packet,
    ) -> SetupCognitiveStateSnapshot:
        unique_reasons = list(dict.fromkeys([*snapshot.invalidation_reasons, *reasons]))
        delta_targets = self._delta_targets(context_packet=context_packet)

        chunk_candidates: list[ChunkCandidate] = []
        for item in snapshot.chunk_candidates:
            updated = item
            unresolved_issues = list(item.unresolved_issues)
            affected_by_user_edit = self._chunk_affected_by_deltas(
                chunk=item,
                delta_targets=delta_targets,
            )
            if "proposal_rejected" in unique_reasons:
                if item.detail_level == "truth_candidate":
                    updated = updated.model_copy(update={"detail_level": "usable"})
                note = "Proposal was rejected; reconfirm before review."
                if note not in unresolved_issues:
                    unresolved_issues.append(note)

            if "user_edit_delta" in unique_reasons:
                if affected_by_user_edit:
                    if item.detail_level == "truth_candidate":
                        updated = updated.model_copy(update={"detail_level": "usable"})
                    note = "Affected by user edits; recheck before review."
                    if note not in unresolved_issues:
                        unresolved_issues.append(note)

            if "draft_changed_without_delta" in unique_reasons:
                note = "Draft changed outside the current turn; reconfirm before review."
                if note not in unresolved_issues:
                    unresolved_issues.append(note)

            if unresolved_issues != item.unresolved_issues:
                updated = updated.model_copy(update={"unresolved_issues": unresolved_issues})
            chunk_candidates.append(updated)

        active_truth_write = snapshot.active_truth_write
        if active_truth_write is not None:
            write_open_issues = list(active_truth_write.remaining_open_issues)
            for reason in unique_reasons:
                if reason == "user_edit_delta":
                    if not self._truth_write_affected_by_deltas(
                        truth_write=active_truth_write,
                        delta_targets=delta_targets,
                    ):
                        continue
                    note = "Latest draft changed after user edits."
                elif reason == "proposal_rejected":
                    note = "Previous proposal was rejected."
                else:
                    note = "Draft changed outside the current cognitive flow."
                if note not in write_open_issues:
                    write_open_issues.append(note)
            if write_open_issues != active_truth_write.remaining_open_issues:
                active_truth_write = active_truth_write.model_copy(
                    update={
                        "ready_for_review": False,
                        "remaining_open_issues": write_open_issues,
                    }
                )

        return snapshot.model_copy(
            update={
                "chunk_candidates": chunk_candidates,
                "active_truth_write": active_truth_write,
                "invalidated": True,
                "invalidation_reasons": unique_reasons,
            }
        )

    def _build_source_basis(
        self,
        *,
        workspace,
        context_packet,
        step_id: SetupStepId,
    ) -> SetupCognitiveSourceBasis:
        current_snapshot = getattr(context_packet, "current_draft_snapshot", {}) or {}
        delta_ids = [
            str(item.get("delta_id"))
            for item in (getattr(context_packet, "user_edit_deltas", None) or [])
            if isinstance(item, dict) and item.get("delta_id")
        ]
        latest_proposal = self._latest_step_proposal(workspace=workspace, step_id=step_id)
        return SetupCognitiveSourceBasis(
            workspace_version=int(workspace.version),
            draft_fingerprint=self._draft_fingerprint(current_snapshot),
            pending_user_edit_delta_ids=delta_ids,
            last_proposal_status=(
                latest_proposal.status.value if latest_proposal is not None else None
            ),
            current_step=step_id.value,
        )

    def _get_record(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
    ) -> SetupAgentRuntimeStateRecord | None:
        return self._session.exec(
            select(SetupAgentRuntimeStateRecord)
            .where(SetupAgentRuntimeStateRecord.workspace_id == workspace_id)
            .where(SetupAgentRuntimeStateRecord.step_id == step_id.value)
        ).first()

    @staticmethod
    def _latest_step_proposal(*, workspace, step_id: SetupStepId):
        proposals = [
            item for item in workspace.commit_proposals if item.step_id == step_id
        ]
        if not proposals:
            return None
        return max(proposals, key=lambda item: item.created_at)

    @staticmethod
    def _draft_fingerprint(current_snapshot: dict) -> str | None:
        if not current_snapshot:
            return None
        payload = json.dumps(current_snapshot, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _delta_targets(*, context_packet) -> dict[str, set[str]]:
        target_refs: set[str] = set()
        block_types: set[str] = set()
        for item in getattr(context_packet, "user_edit_deltas", None) or []:
            if not isinstance(item, dict):
                continue
            target_ref = item.get("target_ref")
            target_block = item.get("target_block")
            if target_ref:
                target_refs.add(str(target_ref))
            if target_block:
                block_types.add(str(target_block))
        return {
            "target_refs": target_refs,
            "block_types": block_types,
        }

    @staticmethod
    def _chunk_affected_by_deltas(
        *,
        chunk: ChunkCandidate,
        delta_targets: dict[str, set[str]],
    ) -> bool:
        if delta_targets["target_refs"] and chunk.target_ref is not None:
            return chunk.target_ref in delta_targets["target_refs"]
        return chunk.block_type in delta_targets["block_types"]

    @staticmethod
    def _truth_write_affected_by_deltas(
        *,
        truth_write: DraftTruthWrite,
        delta_targets: dict[str, set[str]],
    ) -> bool:
        if delta_targets["target_refs"] and truth_write.target_ref is not None:
            return truth_write.target_ref in delta_targets["target_refs"]
        return truth_write.block_type in delta_targets["block_types"]
