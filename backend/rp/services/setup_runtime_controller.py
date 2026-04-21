"""Deterministic controller for SetupAgent MVP workflows."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks
from sqlmodel import Session

from rp.models.setup_drafts import (
    FoundationEntry,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)
from rp.models.setup_handoff import (
    ActivationCheckResult,
    ActivationHandoff,
    RuntimeStoryConfigSeed,
    SetupContextBuilderInput,
    SetupToolResult,
    WriterContractSeed,
)
from rp.models.setup_workspace import (
    QuestionSeverity,
    SetupStepId,
    SetupWorkspace,
    SetupWorkspaceState,
    StoryMode,
)
from rp.services.minimal_retrieval_ingestion_service import MinimalRetrievalIngestionService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from services.database import get_engine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_retrieval_ingestion_in_background(
    *,
    workspace_id: str,
    commit_id: str,
) -> None:
    """Ingestion + readiness refresh on a fresh DB session (request-scoped session is already closed)."""
    with Session(get_engine()) as session:
        ingestion_service = MinimalRetrievalIngestionService(session)
        workspace_service = SetupWorkspaceService(session)
        try:
            ingestion_service.ingest_commit(
                workspace_id=workspace_id,
                commit_id=commit_id,
            )
        finally:
            workspace_service.refresh_readiness(workspace_id)


class SetupRuntimeController:
    """Deterministic control plane for setup patch/review/commit/readiness flows."""

    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilder,
        retrieval_ingestion_service: MinimalRetrievalIngestionService,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._retrieval_ingestion_service = retrieval_ingestion_service

    def create_workspace(self, *, story_id: str, mode: StoryMode) -> SetupWorkspace:
        return self._workspace_service.create_workspace(story_id=story_id, mode=mode)

    def read_workspace(self, *, workspace_id: str) -> SetupWorkspace | None:
        return self._workspace_service.get_workspace(workspace_id)

    def patch_story_config(
        self,
        *,
        workspace_id: str,
        patch: StoryConfigDraft,
    ) -> SetupToolResult:
        self._workspace_service.patch_story_config(workspace_id=workspace_id, patch=patch)
        return SetupToolResult(
            success=True,
            message="Updated story_config draft",
            updated_refs=["draft:story_config"],
        )

    def patch_writing_contract(
        self,
        *,
        workspace_id: str,
        patch: WritingContractDraft,
    ) -> SetupToolResult:
        self._workspace_service.patch_writing_contract(workspace_id=workspace_id, patch=patch)
        return SetupToolResult(
            success=True,
            message="Updated writing_contract draft",
            updated_refs=["draft:writing_contract"],
        )

    def patch_foundation_entry(
        self,
        *,
        workspace_id: str,
        entry: FoundationEntry,
    ) -> SetupToolResult:
        self._workspace_service.patch_foundation_entry(workspace_id=workspace_id, entry=entry)
        return SetupToolResult(
            success=True,
            message="Updated foundation draft entry",
            updated_refs=[f"foundation:{entry.entry_id}"],
        )

    def patch_longform_blueprint(
        self,
        *,
        workspace_id: str,
        patch: LongformBlueprintDraft,
    ) -> SetupToolResult:
        self._workspace_service.patch_longform_blueprint(
            workspace_id=workspace_id,
            patch=patch,
        )
        return SetupToolResult(
            success=True,
            message="Updated longform_blueprint draft",
            updated_refs=["draft:longform_blueprint"],
        )

    def raise_question(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        text: str,
        severity: QuestionSeverity,
    ) -> SetupToolResult:
        question = self._workspace_service.raise_question(
            workspace_id=workspace_id,
            step_id=step_id,
            text=text,
            severity=severity,
        )
        return SetupToolResult(
            success=True,
            message="Raised setup question",
            updated_refs=[f"question:{question.question_id}"],
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
        parse_status=None,
        parsed_payload: dict | None = None,
        parse_warnings: list[str] | None = None,
        mapped_targets: list[str] | None = None,
    ) -> SetupToolResult:
        asset = self._workspace_service.register_asset(
            workspace_id=workspace_id,
            step_id=step_id,
            asset_kind=asset_kind,
            source_ref=source_ref,
            title=title,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            local_path=local_path,
            parse_status=parse_status,
            parsed_payload=parsed_payload,
            parse_warnings=parse_warnings,
            mapped_targets=mapped_targets,
        )
        return SetupToolResult(
            success=True,
            message="Registered setup asset",
            updated_refs=[f"asset:{asset.asset_id}"],
        )

    def propose_commit(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        target_draft_refs: list[str],
        reason: str | None = None,
    ) -> SetupToolResult:
        proposal = self._workspace_service.propose_commit(
            workspace_id=workspace_id,
            step_id=step_id,
            target_draft_refs=target_draft_refs,
            reason=reason,
        )
        return SetupToolResult(
            success=True,
            message=proposal.review_message,
            updated_refs=[f"proposal:{proposal.proposal_id}"],
            warnings=list(proposal.unresolved_warnings),
        )

    def accept_commit(
        self,
        *,
        workspace_id: str,
        proposal_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> SetupToolResult:
        accepted_commit, pending_jobs = self._workspace_service.accept_commit(
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
        if background_tasks is not None:
            background_tasks.add_task(
                _run_retrieval_ingestion_in_background,
                workspace_id=workspace_id,
                commit_id=accepted_commit.commit_id,
            )
            return SetupToolResult(
                success=True,
                message="Accepted commit; retrieval ingestion scheduled in background",
                updated_refs=[
                    f"commit:{accepted_commit.commit_id}",
                    *[f"ingestion:{job.job_id}" for job in pending_jobs],
                ],
            )
        completed_job_ids = self._retrieval_ingestion_service.ingest_commit(
            workspace_id=workspace_id,
            commit_id=accepted_commit.commit_id,
        )
        self._workspace_service.refresh_readiness(workspace_id)
        return SetupToolResult(
            success=True,
            message="Accepted commit and completed retrieval ingestion",
            updated_refs=[
                f"commit:{accepted_commit.commit_id}",
                *[f"ingestion:{job_id}" for job_id in completed_job_ids],
            ],
        )

    def reject_commit(self, *, workspace_id: str, proposal_id: str) -> SetupToolResult:
        proposal = self._workspace_service.reject_commit(
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
        return SetupToolResult(
            success=True,
            message="Rejected commit proposal",
            updated_refs=[f"proposal:{proposal.proposal_id}"],
        )

    def read_step_context(
        self,
        *,
        workspace_id: str,
        current_step: SetupStepId,
        user_prompt: str,
        user_edit_delta_ids: list[str] | None = None,
        token_budget: int | None = None,
    ):
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            return None
        return self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace_id,
                current_step=current_step.value,
                user_prompt=user_prompt,
                user_edit_delta_ids=list(user_edit_delta_ids or []),
                token_budget=token_budget,
            )
        )

    def run_activation_check(self, *, workspace_id: str) -> ActivationCheckResult | None:
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            return None
        blocking_issues: list[str] = []
        warnings = list(workspace.readiness_status.warnings)
        required_steps = {
            SetupStepId.STORY_CONFIG,
            SetupStepId.WRITING_CONTRACT,
            SetupStepId.FOUNDATION,
            SetupStepId.LONGFORM_BLUEPRINT,
        }
        step_state_by_id = {step.step_id: step for step in workspace.step_states}
        for step_id in required_steps:
            if step_state_by_id.get(step_id) is None or step_state_by_id[step_id].state.value != "frozen":
                blocking_issues.append(f"Step not frozen: {step_id.value}")
        if workspace.story_config_draft is None:
            blocking_issues.append("story_config_draft missing")
        if workspace.writing_contract_draft is None:
            blocking_issues.append("writing_contract_draft missing")
        if not any(commit.step_id == SetupStepId.FOUNDATION for commit in workspace.accepted_commits):
            blocking_issues.append("foundation commit missing")
        if not any(commit.step_id == SetupStepId.LONGFORM_BLUEPRINT for commit in workspace.accepted_commits):
            blocking_issues.append("blueprint commit missing")

        required_job_states = [
            job
            for job in workspace.retrieval_ingestion_jobs
            if job.target_type in {"foundation_entry", "blueprint", "asset"}
        ]
        for job in required_job_states:
            if job.state.value != "completed":
                blocking_issues.append(f"Retrieval ingestion not completed: {job.job_id}")

        ready = not blocking_issues
        self._workspace_service.mark_workspace_state(
            workspace_id=workspace_id,
            state=(
                SetupWorkspaceState.READY_TO_ACTIVATE
                if ready
                else SetupWorkspaceState.DRAFTING
            ),
        )

        handoff = None
        if ready:
            handoff = ActivationHandoff(
                handoff_id=uuid4().hex,
                story_id=workspace.story_id,
                workspace_id=workspace.workspace_id,
                mode=workspace.mode,
                runtime_story_config=RuntimeStoryConfigSeed(
                    story_id=workspace.story_id,
                    mode=workspace.mode,
                    model_profile_ref=(
                        workspace.story_config_draft.model_profile_ref
                        if workspace.story_config_draft is not None
                        else None
                    ),
                    worker_profile_ref=(
                        workspace.story_config_draft.worker_profile_ref
                        if workspace.story_config_draft is not None
                        else None
                    ),
                    post_write_policy_preset=(
                        workspace.story_config_draft.post_write_policy_preset
                        if workspace.story_config_draft is not None
                        else None
                    ),
                ),
                writer_contract=WriterContractSeed(
                    pov_rules=(
                        list(workspace.writing_contract_draft.pov_rules)
                        if workspace.writing_contract_draft is not None
                        else []
                    ),
                    style_rules=(
                        list(workspace.writing_contract_draft.style_rules)
                        if workspace.writing_contract_draft is not None
                        else []
                    ),
                    writing_constraints=(
                        list(workspace.writing_contract_draft.writing_constraints)
                        if workspace.writing_contract_draft is not None
                        else []
                    ),
                    task_writing_rules=(
                        list(workspace.writing_contract_draft.task_writing_rules)
                        if workspace.writing_contract_draft is not None
                        else []
                    ),
                ),
                foundation_commit_refs=[
                    commit.commit_id
                    for commit in workspace.accepted_commits
                    if commit.step_id == SetupStepId.FOUNDATION
                ],
                blueprint_commit_ref=next(
                    (
                        commit.commit_id
                        for commit in reversed(workspace.accepted_commits)
                        if commit.step_id == SetupStepId.LONGFORM_BLUEPRINT
                    ),
                    None,
                ),
                archival_ready_refs=[
                    job.target_ref
                    for job in workspace.retrieval_ingestion_jobs
                    if job.state.value == "completed"
                ],
                created_at=_utcnow(),
            )
        return ActivationCheckResult(
            workspace_id=workspace_id,
            ready=ready,
            blocking_issues=blocking_issues,
            warnings=warnings,
            handoff=handoff,
        )
