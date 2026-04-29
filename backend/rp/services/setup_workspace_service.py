"""Persistence and aggregate operations for SetupWorkspace."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_setup_store import (
    SetupAcceptedCommitRecord,
    SetupCommitProposalRecord,
    SetupDraftBlockRecord,
    SetupImportedAssetRecord,
    SetupOpenQuestionRecord,
    SetupPendingUserEditDeltaRecord,
    SetupRetrievalIngestionJobRecord,
    SetupStepAssetBindingRecord,
    SetupStepStateRecord,
    SetupWorkspaceRecord,
)
from rp.models.setup_drafts import (
    FoundationDraft,
    FoundationEntry,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)
from rp.models.setup_workspace import (
    AcceptedCommit,
    AcceptedCommitSnapshot,
    CommitProposal,
    CommitProposalStatus,
    ImportedAssetParseStatus,
    ImportedAssetRaw,
    OpenQuestion,
    PendingUserEditDelta,
    QuestionSeverity,
    QuestionStatus,
    ReadinessStatus,
    RetrievalIngestionJob,
    RetrievalIngestionState,
    SetupStepId,
    SetupStepLifecycleState,
    SetupStepReadiness,
    SetupStepState,
    SetupWorkspace,
    SetupWorkspaceState,
    StepAssetBinding,
    StoryMode,
    UserEditChangeItem,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupWorkspaceService:
    """Database-backed aggregate service for SetupWorkspace."""

    _STEP_ORDER = (
        SetupStepId.FOUNDATION,
        SetupStepId.LONGFORM_BLUEPRINT,
        SetupStepId.WRITING_CONTRACT,
        SetupStepId.STORY_CONFIG,
    )
    _BLOCK_TYPE_BY_STEP = {
        SetupStepId.STORY_CONFIG: "story_config",
        SetupStepId.WRITING_CONTRACT: "writing_contract",
        SetupStepId.FOUNDATION: "foundation",
        SetupStepId.LONGFORM_BLUEPRINT: "longform_blueprint",
    }
    _STEP_BY_BLOCK_TYPE = {
        "story_config": SetupStepId.STORY_CONFIG,
        "writing_contract": SetupStepId.WRITING_CONTRACT,
        "foundation": SetupStepId.FOUNDATION,
        "longform_blueprint": SetupStepId.LONGFORM_BLUEPRINT,
    }

    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def create_workspace(self, *, story_id: str, mode: StoryMode) -> SetupWorkspace:
        existing = self._session.exec(
            select(SetupWorkspaceRecord).where(SetupWorkspaceRecord.story_id == story_id)
        ).first()
        if existing is not None:
            raise ValueError(f"SetupWorkspace already exists for story_id={story_id}")

        now = _utcnow()
        workspace_id = uuid4().hex
        workspace = SetupWorkspaceRecord(
            workspace_id=workspace_id,
            story_id=story_id,
            mode=mode.value,
            workspace_state=SetupWorkspaceState.DRAFTING.value,
            current_step=SetupStepId.FOUNDATION.value,
            readiness_json=self._default_readiness_json(),
            activated_story_session_id=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(workspace)
        for step in self._STEP_ORDER:
            self._session.add(
                SetupStepStateRecord(
                    id=self._step_record_id(workspace_id, step),
                    workspace_id=workspace_id,
                    step_id=step.value,
                    state=SetupStepLifecycleState.DISCUSSING.value,
                    updated_at=now,
                )
            )
        self._session.commit()
        return self.get_workspace(workspace_id)

    def list_workspaces(self) -> list[SetupWorkspace]:
        statement = select(SetupWorkspaceRecord).order_by(SetupWorkspaceRecord.updated_at.desc())
        return [self._assemble_workspace(record) for record in self._session.exec(statement).all()]

    def get_workspace(self, workspace_id: str) -> SetupWorkspace | None:
        workspace_record = self._session.get(SetupWorkspaceRecord, workspace_id)
        if workspace_record is None:
            return None
        return self._assemble_workspace(workspace_record)

    def patch_story_config(
        self,
        *,
        workspace_id: str,
        patch: StoryConfigDraft,
    ) -> SetupWorkspace:
        return self._upsert_block(
            workspace_id=workspace_id,
            step_id=SetupStepId.STORY_CONFIG,
            block_type="story_config",
            payload=patch.model_dump(mode="json", exclude_none=True),
        )

    def patch_writing_contract(
        self,
        *,
        workspace_id: str,
        patch: WritingContractDraft,
    ) -> SetupWorkspace:
        return self._upsert_block(
            workspace_id=workspace_id,
            step_id=SetupStepId.WRITING_CONTRACT,
            block_type="writing_contract",
            payload=patch.model_dump(mode="json", exclude_none=True),
        )

    def patch_foundation_entry(
        self,
        *,
        workspace_id: str,
        entry: FoundationEntry,
    ) -> SetupWorkspace:
        current = self._load_draft_block(
            workspace_id=workspace_id,
            block_type="foundation",
            model=FoundationDraft,
        ) or FoundationDraft()
        entries = {item.entry_id: item for item in current.entries}
        entries[entry.entry_id] = entry
        payload = FoundationDraft(entries=list(entries.values())).model_dump(
            mode="json",
            exclude_none=True,
        )
        return self._upsert_block(
            workspace_id=workspace_id,
            step_id=SetupStepId.FOUNDATION,
            block_type="foundation",
            payload=payload,
        )

    def patch_longform_blueprint(
        self,
        *,
        workspace_id: str,
        patch: LongformBlueprintDraft,
    ) -> SetupWorkspace:
        return self._upsert_block(
            workspace_id=workspace_id,
            step_id=SetupStepId.LONGFORM_BLUEPRINT,
            block_type="longform_blueprint",
            payload=patch.model_dump(mode="json", exclude_none=True),
        )

    def raise_question(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        text: str,
        severity: QuestionSeverity,
    ) -> OpenQuestion:
        workspace = self._require_workspace_record(workspace_id)
        now = _utcnow()
        record = SetupOpenQuestionRecord(
            question_id=uuid4().hex,
            workspace_id=workspace_id,
            step_id=step_id.value,
            text=text,
            severity=severity.value,
            status=QuestionStatus.OPEN.value,
            created_at=now,
        )
        self._session.add(record)
        self._touch_workspace(workspace, now)
        self._session.commit()
        return OpenQuestion.model_validate(
            {
                "question_id": record.question_id,
                "step_id": record.step_id,
                "text": record.text,
                "severity": record.severity,
                "status": record.status,
                "resolution_note": record.resolution_note,
                "created_at": record.created_at,
                "resolved_at": record.resolved_at,
            }
        )

    def register_asset(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        asset_kind: str,
        source_ref: str,
        title: str | None = None,
        mime_type: str | None = None,
        file_size_bytes: int | None = None,
        local_path: str | None = None,
        parse_status: ImportedAssetParseStatus = ImportedAssetParseStatus.STAGED,
        parsed_payload: dict | None = None,
        parse_warnings: list[str] | None = None,
        mapped_targets: list[str] | None = None,
    ) -> ImportedAssetRaw:
        workspace = self._require_workspace_record(workspace_id)
        now = _utcnow()
        asset_id = uuid4().hex
        targets = list(mapped_targets or [])
        if not targets:
            targets = [self._BLOCK_TYPE_BY_STEP[step_id]]
        record = SetupImportedAssetRecord(
            asset_id=asset_id,
            workspace_id=workspace_id,
            step_id=step_id.value,
            asset_kind=asset_kind,
            source_ref=source_ref,
            title=title,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            local_path=local_path,
            parse_status=parse_status.value,
            parsed_payload_json=parsed_payload,
            parse_warnings_json=list(parse_warnings or []),
            mapped_targets_json=targets,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.add(
            SetupStepAssetBindingRecord(
                binding_id=uuid4().hex,
                workspace_id=workspace_id,
                step_id=step_id.value,
                asset_id=asset_id,
                binding_role="primary",
                target_block=self._BLOCK_TYPE_BY_STEP[step_id],
                target_path=None,
                created_at=now,
            )
        )
        self._touch_workspace(workspace, now)
        self._session.commit()
        return ImportedAssetRaw.model_validate(
            {
                "asset_id": record.asset_id,
                "step_id": record.step_id,
                "asset_kind": record.asset_kind,
                "source_ref": record.source_ref,
                "title": record.title,
                "mime_type": record.mime_type,
                "file_size_bytes": record.file_size_bytes,
                "parse_status": record.parse_status,
                "parsed_payload": record.parsed_payload_json,
                "parse_warnings": record.parse_warnings_json,
                "mapped_targets": record.mapped_targets_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    def propose_commit(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        target_draft_refs: list[str],
        reason: str | None = None,
        unresolved_warnings: list[str] | None = None,
    ) -> CommitProposal:
        workspace = self._require_workspace_record(workspace_id)
        step_record = self._require_step_state_record(workspace_id, step_id)
        now = _utcnow()
        proposal = SetupCommitProposalRecord(
            proposal_id=uuid4().hex,
            workspace_id=workspace_id,
            step_id=step_id.value,
            status=CommitProposalStatus.PENDING_REVIEW.value,
            target_block_types_json=[self._BLOCK_TYPE_BY_STEP[step_id]],
            target_draft_refs_json=list(target_draft_refs),
            review_message=f"Review requested for {step_id.value}",
            reason=reason,
            unresolved_warnings_json=list(unresolved_warnings or []),
            suggested_ingestion_targets_json=self._suggest_ingestion_targets(
                workspace_id=workspace_id,
                step_id=step_id,
            ),
            created_at=now,
        )
        self._session.add(proposal)
        step_record.state = SetupStepLifecycleState.REVIEW_PENDING.value
        step_record.review_round += 1
        step_record.last_proposal_id = proposal.proposal_id
        step_record.updated_at = now
        self._session.add(step_record)
        self._touch_workspace(workspace, now)
        self._refresh_readiness_record(workspace)
        self._session.commit()
        return self._record_to_commit_proposal(proposal)

    def accept_commit(
        self,
        *,
        workspace_id: str,
        proposal_id: str,
    ) -> tuple[AcceptedCommit, list[RetrievalIngestionJob]]:
        workspace = self._require_workspace_record(workspace_id)
        proposal = self._require_commit_proposal_record(workspace_id, proposal_id)
        now = _utcnow()
        step_id = SetupStepId(proposal.step_id)
        snapshot_payload = self._build_snapshot_payload(
            workspace_id=workspace_id,
            block_types=proposal.target_block_types_json,
        )
        commit_id = uuid4().hex
        accepted_record = SetupAcceptedCommitRecord(
            commit_id=commit_id,
            workspace_id=workspace_id,
            proposal_id=proposal_id,
            step_id=step_id.value,
            committed_refs_json=proposal.target_draft_refs_json or [f"{step_id.value}:{commit_id}"],
            snapshot_payload_json=snapshot_payload,
            summary_tier_0=self._build_summary_tier_0(step_id, snapshot_payload),
            summary_tier_1=self._build_summary_tier_1(step_id, snapshot_payload),
            summary_tier_2=self._build_summary_tier_2(step_id, snapshot_payload),
            spotlights_json=self._build_spotlights(step_id, snapshot_payload),
            created_at=now,
        )
        self._session.add(accepted_record)
        proposal.status = CommitProposalStatus.ACCEPTED.value
        proposal.reviewed_at = now
        self._session.add(proposal)
        step_record = self._require_step_state_record(workspace_id, step_id)
        step_record.state = SetupStepLifecycleState.FROZEN.value
        step_record.last_commit_id = commit_id
        step_record.updated_at = now
        self._session.add(step_record)
        for block_type in proposal.target_block_types_json:
            block_record = self._get_draft_block_record(workspace_id, block_type)
            if block_record is not None:
                block_record.last_commit_id = commit_id
                block_record.updated_at = now
                self._session.add(block_record)
        job_records = self._create_ingestion_job_records(
            workspace_id=workspace_id,
            commit_id=commit_id,
            step_id=step_id,
            snapshot_payload=snapshot_payload,
            created_at=now,
        )
        for job_record in job_records:
            self._session.add(job_record)
        self._advance_current_step(workspace, step_id)
        self._touch_workspace(workspace, now)
        self._refresh_readiness_record(workspace)
        self._session.commit()
        return (
            self._record_to_accepted_commit(accepted_record),
            [self._record_to_ingestion_job(record) for record in job_records],
        )

    def reject_commit(
        self,
        *,
        workspace_id: str,
        proposal_id: str,
    ) -> CommitProposal:
        workspace = self._require_workspace_record(workspace_id)
        proposal = self._require_commit_proposal_record(workspace_id, proposal_id)
        now = _utcnow()
        proposal.status = CommitProposalStatus.REJECTED.value
        proposal.reviewed_at = now
        self._session.add(proposal)
        step_id = SetupStepId(proposal.step_id)
        step_record = self._require_step_state_record(workspace_id, step_id)
        step_record.state = SetupStepLifecycleState.DISCUSSING.value
        step_record.updated_at = now
        self._session.add(step_record)
        self._touch_workspace(workspace, now)
        self._refresh_readiness_record(workspace)
        self._session.commit()
        return self._record_to_commit_proposal(proposal)

    def refresh_readiness(self, workspace_id: str) -> SetupWorkspace:
        workspace = self._require_workspace_record(workspace_id)
        self._refresh_readiness_record(workspace)
        self._session.add(workspace)
        self._session.commit()
        return self.get_workspace(workspace_id)

    def mark_workspace_state(
        self,
        *,
        workspace_id: str,
        state: SetupWorkspaceState,
    ) -> SetupWorkspace:
        record = self._require_workspace_record(workspace_id)
        record.workspace_state = state.value
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.commit()
        return self.get_workspace(workspace_id)

    def mark_activated_story_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
    ) -> SetupWorkspace:
        record = self._require_workspace_record(workspace_id)
        now = _utcnow()
        record.workspace_state = SetupWorkspaceState.ACTIVATED.value
        record.activated_story_session_id = session_id
        record.activated_at = now
        record.updated_at = now
        self._session.add(record)
        self._session.commit()
        return self.get_workspace(workspace_id)

    def get_pending_ingestion_jobs(
        self,
        *,
        workspace_id: str,
        commit_id: str,
    ) -> list[SetupRetrievalIngestionJobRecord]:
        statement = (
            select(SetupRetrievalIngestionJobRecord)
            .where(SetupRetrievalIngestionJobRecord.workspace_id == workspace_id)
            .where(SetupRetrievalIngestionJobRecord.commit_id == commit_id)
            .where(SetupRetrievalIngestionJobRecord.state != RetrievalIngestionState.COMPLETED.value)
        )
        return list(self._session.exec(statement).all())

    def update_ingestion_job(
        self,
        *,
        job_id: str,
        state: RetrievalIngestionState,
        index_job_id: str | None = None,
        warnings: list[str] | None = None,
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> SetupRetrievalIngestionJobRecord:
        record = self._session.get(SetupRetrievalIngestionJobRecord, job_id)
        if record is None:
            raise ValueError(f"RetrievalIngestionJob not found: {job_id}")
        record.state = state.value
        if index_job_id is not None:
            record.index_job_id = index_job_id
        if warnings is not None:
            record.warnings_json = list(warnings)
        record.error_message = error_message
        record.updated_at = _utcnow()
        record.completed_at = completed_at
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def _assemble_workspace(self, workspace_record: SetupWorkspaceRecord) -> SetupWorkspace:
        step_records = list(
            self._session.exec(
                select(SetupStepStateRecord).where(
                    SetupStepStateRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        block_records = list(
            self._session.exec(
                select(SetupDraftBlockRecord).where(
                    SetupDraftBlockRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        asset_records = list(
            self._session.exec(
                select(SetupImportedAssetRecord).where(
                    SetupImportedAssetRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        binding_records = list(
            self._session.exec(
                select(SetupStepAssetBindingRecord).where(
                    SetupStepAssetBindingRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        ingestion_records = list(
            self._session.exec(
                select(SetupRetrievalIngestionJobRecord).where(
                    SetupRetrievalIngestionJobRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        proposal_records = list(
            self._session.exec(
                select(SetupCommitProposalRecord).where(
                    SetupCommitProposalRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        commit_records = list(
            self._session.exec(
                select(SetupAcceptedCommitRecord).where(
                    SetupAcceptedCommitRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        delta_records = list(
            self._session.exec(
                select(SetupPendingUserEditDeltaRecord).where(
                    SetupPendingUserEditDeltaRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        question_records = list(
            self._session.exec(
                select(SetupOpenQuestionRecord).where(
                    SetupOpenQuestionRecord.workspace_id == workspace_record.workspace_id
                )
            ).all()
        )
        blocks = {record.block_type: record for record in block_records}
        return SetupWorkspace(
            workspace_id=workspace_record.workspace_id,
            story_id=workspace_record.story_id,
            mode=StoryMode(workspace_record.mode),
            workspace_state=SetupWorkspaceState(workspace_record.workspace_state),
            current_step=SetupStepId(workspace_record.current_step),
            step_states=[
                self._record_to_step_state(record)
                for record in sorted(
                    step_records,
                    key=lambda item: self._STEP_ORDER.index(SetupStepId(item.step_id)),
                )
            ],
            story_config_draft=self._parse_block(blocks.get("story_config"), StoryConfigDraft),
            writing_contract_draft=self._parse_block(
                blocks.get("writing_contract"),
                WritingContractDraft,
            ),
            foundation_draft=self._parse_block(blocks.get("foundation"), FoundationDraft),
            longform_blueprint_draft=self._parse_block(
                blocks.get("longform_blueprint"),
                LongformBlueprintDraft,
            ),
            imported_assets=[self._record_to_imported_asset(record) for record in asset_records],
            step_asset_bindings=[self._record_to_step_asset_binding(record) for record in binding_records],
            retrieval_ingestion_jobs=[
                self._record_to_ingestion_job(record) for record in ingestion_records
            ],
            commit_proposals=[
                self._record_to_commit_proposal(record) for record in proposal_records
            ],
            accepted_commits=[
                self._record_to_accepted_commit(record) for record in commit_records
            ],
            pending_user_edit_deltas=[
                self._record_to_pending_delta(record) for record in delta_records
            ],
            open_questions=[self._record_to_open_question(record) for record in question_records],
            readiness_status=ReadinessStatus.model_validate(workspace_record.readiness_json),
            version=workspace_record.version,
            created_at=workspace_record.created_at,
            updated_at=workspace_record.updated_at,
            activated_at=workspace_record.activated_at,
            activated_story_session_id=workspace_record.activated_story_session_id,
        )

    def _upsert_block(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        block_type: str,
        payload: dict,
    ) -> SetupWorkspace:
        workspace = self._require_workspace_record(workspace_id)
        now = _utcnow()
        block_record = self._get_draft_block_record(workspace_id, block_type)
        if block_record is None:
            block_record = SetupDraftBlockRecord(
                draft_block_id=uuid4().hex,
                workspace_id=workspace_id,
                step_id=step_id.value,
                block_type=block_type,
                payload_json=payload,
                created_at=now,
                updated_at=now,
            )
        else:
            block_record.payload_json = payload
            block_record.current_revision += 1
            block_record.updated_at = now
            block_record.step_id = step_id.value
        self._session.add(block_record)
        step_record = self._require_step_state_record(workspace_id, step_id)
        step_record.state = SetupStepLifecycleState.DISCUSSING.value
        step_record.discussion_round += 1
        step_record.updated_at = now
        self._session.add(step_record)
        self._touch_workspace(workspace, now)
        self._refresh_readiness_record(workspace)
        self._session.commit()
        return self.get_workspace(workspace_id)

    def _touch_workspace(self, workspace: SetupWorkspaceRecord, now: datetime) -> None:
        workspace.updated_at = now
        workspace.version += 1
        self._session.add(workspace)

    def _advance_current_step(
        self,
        workspace: SetupWorkspaceRecord,
        current_step: SetupStepId,
    ) -> None:
        for step in self._STEP_ORDER:
            step_record = self._require_step_state_record(workspace.workspace_id, step)
            if step_record.state != SetupStepLifecycleState.FROZEN.value:
                workspace.current_step = step.value
                return
        workspace.current_step = current_step.value

    def _refresh_readiness_record(self, workspace: SetupWorkspaceRecord) -> None:
        blocks = {
            record.block_type: record
            for record in self._session.exec(
                select(SetupDraftBlockRecord).where(
                    SetupDraftBlockRecord.workspace_id == workspace.workspace_id
                )
            ).all()
        }
        step_records = list(
            self._session.exec(
                select(SetupStepStateRecord).where(
                    SetupStepStateRecord.workspace_id == workspace.workspace_id
                )
            ).all()
        )
        readiness: dict[str, str] = {}
        warnings: list[str] = []
        for record in step_records:
            step_id = SetupStepId(record.step_id)
            if record.state == SetupStepLifecycleState.FROZEN.value:
                readiness[step_id.value] = SetupStepReadiness.FROZEN.value
                continue
            if record.state == SetupStepLifecycleState.REVIEW_PENDING.value:
                readiness[step_id.value] = SetupStepReadiness.READY_FOR_REVIEW.value
                continue
            block_type = self._BLOCK_TYPE_BY_STEP[step_id]
            has_content = self._draft_block_has_content(blocks.get(block_type))
            readiness[step_id.value] = (
                SetupStepReadiness.READY_FOR_COMMIT.value
                if has_content
                else SetupStepReadiness.NOT_READY.value
            )
            if not has_content:
                warnings.append(f"Step {step_id.value} has no draft content yet")
        workspace.readiness_json = {
            "step_readiness": readiness,
            "blocking_issues": [],
            "warnings": warnings,
        }
        self._session.add(workspace)

    def _draft_block_has_content(self, record: SetupDraftBlockRecord | None) -> bool:
        if record is None:
            return False
        payload = record.payload_json or {}
        if record.block_type == "foundation":
            return bool(payload.get("entries"))
        if record.block_type == "writing_contract":
            return any(bool(value) for value in payload.values())
        if record.block_type == "story_config":
            return any(value is not None for value in payload.values())
        if record.block_type == "longform_blueprint":
            return any(bool(value) for value in payload.values())
        return bool(payload)

    def _default_readiness_json(self) -> dict:
        return {
            "step_readiness": {
                step.value: SetupStepReadiness.NOT_READY.value for step in self._STEP_ORDER
            },
            "blocking_issues": [],
            "warnings": [],
        }

    def _load_draft_block(self, workspace_id: str, block_type: str, model):
        record = self._get_draft_block_record(workspace_id, block_type)
        if record is None:
            return None
        return model.model_validate(record.payload_json or {})

    def _get_draft_block_record(
        self,
        workspace_id: str,
        block_type: str,
    ) -> SetupDraftBlockRecord | None:
        return self._session.exec(
            select(SetupDraftBlockRecord)
            .where(SetupDraftBlockRecord.workspace_id == workspace_id)
            .where(SetupDraftBlockRecord.block_type == block_type)
        ).first()

    def _require_workspace_record(self, workspace_id: str) -> SetupWorkspaceRecord:
        record = self._session.get(SetupWorkspaceRecord, workspace_id)
        if record is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        return record

    def _require_step_state_record(
        self,
        workspace_id: str,
        step_id: SetupStepId,
    ) -> SetupStepStateRecord:
        record = self._session.get(SetupStepStateRecord, self._step_record_id(workspace_id, step_id))
        if record is None:
            raise ValueError(
                f"SetupStepState not found: workspace_id={workspace_id}, step_id={step_id.value}"
            )
        return record

    def _require_commit_proposal_record(
        self,
        workspace_id: str,
        proposal_id: str,
    ) -> SetupCommitProposalRecord:
        record = self._session.get(SetupCommitProposalRecord, proposal_id)
        if record is None or record.workspace_id != workspace_id:
            raise ValueError(f"CommitProposal not found: {proposal_id}")
        return record

    def _build_snapshot_payload(
        self,
        *,
        workspace_id: str,
        block_types: list[str],
    ) -> dict:
        payload: dict[str, dict] = {}
        for block_type in block_types:
            record = self._get_draft_block_record(workspace_id, block_type)
            if record is not None:
                payload[block_type] = dict(record.payload_json or {})
        return payload

    def _build_summary_tier_0(self, step_id: SetupStepId, snapshot_payload: dict) -> str:
        if step_id == SetupStepId.FOUNDATION:
            entry_count = len(snapshot_payload.get("foundation", {}).get("entries", []))
            return f"Committed {entry_count} foundation entries"
        if step_id == SetupStepId.LONGFORM_BLUEPRINT:
            return "Committed longform blueprint"
        if step_id == SetupStepId.WRITING_CONTRACT:
            return "Committed writing contract"
        return f"Committed {step_id.value}"

    def _build_summary_tier_1(self, step_id: SetupStepId, snapshot_payload: dict) -> str:
        if step_id == SetupStepId.FOUNDATION:
            entries = snapshot_payload.get("foundation", {}).get("entries", [])
            paths = [entry.get("path") for entry in entries if entry.get("path")]
            return ", ".join(paths[:5]) or "Foundation updated"
        if step_id == SetupStepId.LONGFORM_BLUEPRINT:
            blueprint = snapshot_payload.get("longform_blueprint", {})
            return blueprint.get("premise") or "Blueprint updated"
        if step_id == SetupStepId.WRITING_CONTRACT:
            contract = snapshot_payload.get("writing_contract", {})
            return ", ".join(contract.get("style_rules", [])[:3]) or "Writing rules updated"
        config = snapshot_payload.get("story_config", {})
        return config.get("notes") or "Story config updated"

    def _build_summary_tier_2(self, step_id: SetupStepId, snapshot_payload: dict) -> str:
        return self._build_summary_tier_1(step_id, snapshot_payload)

    def _build_spotlights(self, step_id: SetupStepId, snapshot_payload: dict) -> list[str]:
        if step_id == SetupStepId.FOUNDATION:
            return [
                entry.get("title") or entry.get("path")
                for entry in snapshot_payload.get("foundation", {}).get("entries", [])
                if entry.get("title") or entry.get("path")
            ][:5]
        if step_id == SetupStepId.LONGFORM_BLUEPRINT:
            return [
                chapter.get("title") or chapter.get("chapter_id")
                for chapter in snapshot_payload.get("longform_blueprint", {}).get(
                    "chapter_blueprints",
                    [],
                )
                if chapter.get("title") or chapter.get("chapter_id")
            ][:5]
        return []

    def _suggest_ingestion_targets(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
    ) -> list[str]:
        targets: list[str] = []
        if step_id == SetupStepId.FOUNDATION:
            foundation = self._load_draft_block(workspace_id, "foundation", FoundationDraft)
            if foundation is not None:
                targets.extend(entry.entry_id for entry in foundation.entries)
        elif step_id == SetupStepId.LONGFORM_BLUEPRINT:
            targets.append("longform_blueprint")
        asset_records = self._session.exec(
            select(SetupImportedAssetRecord)
            .where(SetupImportedAssetRecord.workspace_id == workspace_id)
            .where(SetupImportedAssetRecord.step_id == step_id.value)
            .where(SetupImportedAssetRecord.parse_status == ImportedAssetParseStatus.PARSED.value)
        ).all()
        targets.extend(record.asset_id for record in asset_records)
        return targets

    def _create_ingestion_job_records(
        self,
        *,
        workspace_id: str,
        commit_id: str,
        step_id: SetupStepId,
        snapshot_payload: dict,
        created_at: datetime,
    ) -> list[SetupRetrievalIngestionJobRecord]:
        records: list[SetupRetrievalIngestionJobRecord] = []
        if step_id == SetupStepId.FOUNDATION:
            for entry in snapshot_payload.get("foundation", {}).get("entries", []):
                records.append(
                    SetupRetrievalIngestionJobRecord(
                        job_id=uuid4().hex,
                        workspace_id=workspace_id,
                        commit_id=commit_id,
                        step_id=step_id.value,
                        target_type="foundation_entry",
                        target_ref=entry.get("entry_id") or entry.get("path") or uuid4().hex,
                        state=RetrievalIngestionState.QUEUED.value,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
        elif step_id == SetupStepId.LONGFORM_BLUEPRINT:
            records.append(
                SetupRetrievalIngestionJobRecord(
                    job_id=uuid4().hex,
                    workspace_id=workspace_id,
                    commit_id=commit_id,
                    step_id=step_id.value,
                    target_type="blueprint",
                    target_ref="longform_blueprint",
                    state=RetrievalIngestionState.QUEUED.value,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        asset_records = self._session.exec(
            select(SetupImportedAssetRecord)
            .where(SetupImportedAssetRecord.workspace_id == workspace_id)
            .where(SetupImportedAssetRecord.step_id == step_id.value)
            .where(SetupImportedAssetRecord.parse_status == ImportedAssetParseStatus.PARSED.value)
        ).all()
        for record in asset_records:
            records.append(
                SetupRetrievalIngestionJobRecord(
                    job_id=uuid4().hex,
                    workspace_id=workspace_id,
                    commit_id=commit_id,
                    step_id=step_id.value,
                    target_type="asset",
                    target_ref=record.asset_id,
                    state=RetrievalIngestionState.QUEUED.value,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        return records

    @classmethod
    def _step_record_id(cls, workspace_id: str, step_id: SetupStepId) -> str:
        return f"{workspace_id}:{step_id.value}"

    @staticmethod
    def _parse_block(record: SetupDraftBlockRecord | None, model):
        if record is None:
            return None
        return model.model_validate(record.payload_json or {})

    @staticmethod
    def _record_to_step_state(record: SetupStepStateRecord) -> SetupStepState:
        return SetupStepState.model_validate(
            {
                "step_id": record.step_id,
                "state": record.state,
                "discussion_round": record.discussion_round,
                "review_round": record.review_round,
                "last_proposal_id": record.last_proposal_id,
                "last_commit_id": record.last_commit_id,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_imported_asset(record: SetupImportedAssetRecord) -> ImportedAssetRaw:
        return ImportedAssetRaw.model_validate(
            {
                "asset_id": record.asset_id,
                "step_id": record.step_id,
                "asset_kind": record.asset_kind,
                "source_ref": record.source_ref,
                "title": record.title,
                "mime_type": record.mime_type,
                "file_size_bytes": record.file_size_bytes,
                "parse_status": record.parse_status,
                "parsed_payload": record.parsed_payload_json,
                "parse_warnings": record.parse_warnings_json,
                "mapped_targets": record.mapped_targets_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_step_asset_binding(record: SetupStepAssetBindingRecord) -> StepAssetBinding:
        return StepAssetBinding.model_validate(
            {
                "binding_id": record.binding_id,
                "step_id": record.step_id,
                "asset_id": record.asset_id,
                "binding_role": record.binding_role,
                "target_block": record.target_block,
                "target_path": record.target_path,
            }
        )

    @staticmethod
    def _record_to_ingestion_job(record: SetupRetrievalIngestionJobRecord) -> RetrievalIngestionJob:
        return RetrievalIngestionJob.model_validate(
            {
                "job_id": record.job_id,
                "commit_id": record.commit_id,
                "step_id": record.step_id,
                "target_type": record.target_type,
                "target_ref": record.target_ref,
                "index_job_id": record.index_job_id,
                "state": record.state,
                "warnings": record.warnings_json,
                "error_message": record.error_message,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "completed_at": record.completed_at,
            }
        )

    @staticmethod
    def _record_to_commit_proposal(record: SetupCommitProposalRecord) -> CommitProposal:
        return CommitProposal.model_validate(
            {
                "proposal_id": record.proposal_id,
                "step_id": record.step_id,
                "status": record.status,
                "target_block_types": record.target_block_types_json,
                "target_draft_refs": record.target_draft_refs_json,
                "review_message": record.review_message,
                "reason": record.reason,
                "unresolved_warnings": record.unresolved_warnings_json,
                "suggested_ingestion_targets": record.suggested_ingestion_targets_json,
                "created_at": record.created_at,
                "reviewed_at": record.reviewed_at,
            }
        )

    @staticmethod
    def _record_to_accepted_commit(record: SetupAcceptedCommitRecord) -> AcceptedCommit:
        snapshots = [
            AcceptedCommitSnapshot(
                block_type=block_type,
                source_draft_ref=None,
                payload=payload,
            )
            for block_type, payload in (record.snapshot_payload_json or {}).items()
        ]
        return AcceptedCommit.model_validate(
            {
                "commit_id": record.commit_id,
                "proposal_id": record.proposal_id,
                "step_id": record.step_id,
                "committed_refs": record.committed_refs_json,
                "snapshots": [item.model_dump(mode="json") for item in snapshots],
                "summary_tier_0": record.summary_tier_0,
                "summary_tier_1": record.summary_tier_1,
                "summary_tier_2": record.summary_tier_2,
                "spotlights": record.spotlights_json,
                "created_at": record.created_at,
            }
        )

    @staticmethod
    def _record_to_pending_delta(record: SetupPendingUserEditDeltaRecord) -> PendingUserEditDelta:
        return PendingUserEditDelta.model_validate(
            {
                "delta_id": record.delta_id,
                "step_id": record.step_id,
                "target_block": record.target_block,
                "target_ref": record.target_ref,
                "changes": [UserEditChangeItem.model_validate(item).model_dump(mode="json") for item in record.changes_json],
                "created_at": record.created_at,
                "consumed_at": record.consumed_at,
            }
        )

    @staticmethod
    def _record_to_open_question(record: SetupOpenQuestionRecord) -> OpenQuestion:
        return OpenQuestion.model_validate(
            {
                "question_id": record.question_id,
                "step_id": record.step_id,
                "text": record.text,
                "severity": record.severity,
                "status": record.status,
                "resolution_note": record.resolution_note,
                "created_at": record.created_at,
                "resolved_at": record.resolved_at,
            }
        )
