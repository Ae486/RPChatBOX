"""Persistence repository for Phase E memory proposals and apply receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_memory_store import (
    MemoryApplyReceiptRecord,
    MemoryApplyTargetLinkRecord,
    MemoryProposalRecord,
)
from rp.models.dsl import Domain, ObjectRef
from rp.models.memory_crud import ProposalReceipt, ProposalSubmitInput


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProposalRepository:
    """Persist proposal and apply metadata for authoritative governance."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def create_proposal(
        self,
        *,
        input_model: ProposalSubmitInput,
        status: str,
        policy_decision: str | None,
        submit_source: str,
        session_id: str | None = None,
        chapter_workspace_id: str | None = None,
    ) -> ProposalReceipt:
        now = _utcnow()
        record = MemoryProposalRecord(
            proposal_id=f"proposal_{uuid4().hex[:12]}",
            story_id=input_model.story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            mode=input_model.mode,
            domain=input_model.domain.value,
            domain_path=input_model.domain_path,
            status=status,
            policy_decision=policy_decision,
            submit_source=submit_source,
            operations_json=[operation.model_dump(mode="json") for operation in input_model.operations],
            base_refs_json=[ref.model_dump(mode="json") for ref in input_model.base_refs],
            reason=input_model.reason,
            trace_id=input_model.trace_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_receipt(record)

    def get_proposal_record(self, proposal_id: str) -> MemoryProposalRecord | None:
        return self._session.get(MemoryProposalRecord, proposal_id)

    def get_proposal_receipt(self, proposal_id: str) -> ProposalReceipt:
        return self._to_receipt(self._require_proposal_record(proposal_id))

    def get_proposal_input(self, proposal_id: str) -> ProposalSubmitInput:
        record = self._require_proposal_record(proposal_id)
        return ProposalSubmitInput.model_validate(
            {
                "story_id": record.story_id,
                "mode": record.mode,
                "domain": Domain(record.domain),
                "domain_path": record.domain_path,
                "operations": record.operations_json,
                "base_refs": record.base_refs_json,
                "reason": record.reason,
                "trace_id": record.trace_id,
            }
        )

    def update_proposal_status(
        self,
        proposal_id: str,
        *,
        status: str,
        error_message: str | None = None,
        applied_at: datetime | None = None,
    ) -> ProposalReceipt:
        record = self._require_proposal_record(proposal_id)
        record.status = status
        record.error_message = error_message
        record.applied_at = applied_at
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return self._to_receipt(record)

    def create_apply_receipt(
        self,
        *,
        proposal_id: str,
        story_id: str,
        session_id: str | None,
        chapter_workspace_id: str | None,
        target_refs: list[ObjectRef],
        revision_after: dict[str, int],
        before_snapshot: dict,
        after_snapshot: dict,
        warnings: list[str],
        apply_backend: str = "adapter_backed",
    ) -> MemoryApplyReceiptRecord:
        record = MemoryApplyReceiptRecord(
            apply_id=f"apply_{uuid4().hex[:12]}",
            proposal_id=proposal_id,
            story_id=story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            target_refs_json=[ref.model_dump(mode="json") for ref in target_refs],
            revision_after_json=dict(revision_after),
            before_snapshot_json=dict(before_snapshot),
            after_snapshot_json=dict(after_snapshot),
            warnings_json=list(warnings),
            apply_backend=apply_backend,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def create_apply_target_link(
        self,
        *,
        apply_id: str,
        proposal_id: str,
        story_id: str,
        session_id: str | None,
        object_id: str,
        domain: str,
        domain_path: str,
        scope: str,
        revision: int,
        authoritative_object_id: str,
        authoritative_revision_id: str,
    ) -> MemoryApplyTargetLinkRecord:
        record = self.get_apply_target_link(
            apply_id=apply_id,
            object_id=object_id,
            revision=revision,
        )
        if record is None:
            record = MemoryApplyTargetLinkRecord(
                apply_target_link_id=f"apply_link_{uuid4().hex[:12]}",
                apply_id=apply_id,
                proposal_id=proposal_id,
                story_id=story_id,
                session_id=session_id,
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
                scope=scope,
                revision=revision,
                authoritative_object_id=authoritative_object_id,
                authoritative_revision_id=authoritative_revision_id,
            )
            self._session.add(record)
            self._session.flush()
            return record

        record.proposal_id = proposal_id
        record.story_id = story_id
        record.session_id = session_id
        record.domain = domain
        record.domain_path = domain_path
        record.scope = scope
        record.authoritative_object_id = authoritative_object_id
        record.authoritative_revision_id = authoritative_revision_id
        self._session.add(record)
        self._session.flush()
        return record

    def get_apply_target_link(
        self,
        *,
        apply_id: str,
        object_id: str,
        revision: int,
    ) -> MemoryApplyTargetLinkRecord | None:
        stmt = (
            select(MemoryApplyTargetLinkRecord)
            .where(MemoryApplyTargetLinkRecord.apply_id == apply_id)
            .where(MemoryApplyTargetLinkRecord.object_id == object_id)
            .where(MemoryApplyTargetLinkRecord.revision == revision)
        )
        return self._session.exec(stmt).first()

    def list_apply_target_links_for_apply(self, apply_id: str) -> list[MemoryApplyTargetLinkRecord]:
        stmt = (
            select(MemoryApplyTargetLinkRecord)
            .where(MemoryApplyTargetLinkRecord.apply_id == apply_id)
            .order_by(MemoryApplyTargetLinkRecord.object_id.asc())
        )
        return list(self._session.exec(stmt).all())

    def get_apply_target_link_for_target(
        self,
        *,
        session_id: str | None,
        object_id: str,
        revision: int,
    ) -> MemoryApplyTargetLinkRecord | None:
        stmt = (
            select(MemoryApplyTargetLinkRecord)
            .where(MemoryApplyTargetLinkRecord.object_id == object_id)
            .where(MemoryApplyTargetLinkRecord.revision == revision)
        )
        if session_id is not None:
            stmt = stmt.where(MemoryApplyTargetLinkRecord.session_id == session_id)
        stmt = stmt.order_by(MemoryApplyTargetLinkRecord.created_at.desc())
        return self._session.exec(stmt).first()

    def list_apply_receipts_for_proposal(self, proposal_id: str) -> list[MemoryApplyReceiptRecord]:
        stmt = (
            select(MemoryApplyReceiptRecord)
            .where(MemoryApplyReceiptRecord.proposal_id == proposal_id)
            .order_by(MemoryApplyReceiptRecord.created_at.asc())
        )
        return list(self._session.exec(stmt).all())

    def list_apply_receipts_for_story(
        self,
        story_id: str,
        *,
        session_id: str | None = None,
    ) -> list[MemoryApplyReceiptRecord]:
        stmt = (
            select(MemoryApplyReceiptRecord)
            .where(MemoryApplyReceiptRecord.story_id == story_id)
            .order_by(MemoryApplyReceiptRecord.created_at.asc())
        )
        if session_id is not None:
            stmt = stmt.where(MemoryApplyReceiptRecord.session_id == session_id)
        return list(self._session.exec(stmt).all())

    def list_apply_receipts_for_target(
        self,
        *,
        story_id: str,
        target_ref: ObjectRef,
        session_id: str | None = None,
    ) -> list[MemoryApplyReceiptRecord]:
        receipts: list[MemoryApplyReceiptRecord] = []
        for record in self.list_apply_receipts_for_story(
            story_id,
            session_id=session_id,
        ):
            if any(item.get("object_id") == target_ref.object_id for item in record.target_refs_json):
                receipts.append(record)
        return receipts

    def list_proposals_for_story(self, story_id: str) -> list[MemoryProposalRecord]:
        stmt = (
            select(MemoryProposalRecord)
            .where(MemoryProposalRecord.story_id == story_id)
            .order_by(MemoryProposalRecord.created_at.asc())
        )
        return list(self._session.exec(stmt).all())

    def latest_revision_for_target(
        self,
        *,
        story_id: str,
        target_ref: ObjectRef,
        session_id: str | None = None,
    ) -> int:
        latest_revision = target_ref.revision or 1
        for record in self.list_apply_receipts_for_story(
            story_id,
            session_id=session_id,
        ):
            revision = record.revision_after_json.get(target_ref.object_id)
            if revision is None:
                continue
            latest_revision = max(latest_revision, revision)
        return latest_revision

    def _require_proposal_record(self, proposal_id: str) -> MemoryProposalRecord:
        record = self.get_proposal_record(proposal_id)
        if record is None:
            raise ValueError(f"Proposal not found: {proposal_id}")
        return record

    @staticmethod
    def _to_receipt(record: MemoryProposalRecord) -> ProposalReceipt:
        return ProposalReceipt(
            proposal_id=record.proposal_id,
            status=record.status,
            mode=record.mode,
            domain=Domain(record.domain),
            domain_path=record.domain_path,
            operation_kinds=[item.get("kind", "") for item in record.operations_json],
            created_at=record.created_at,
        )
