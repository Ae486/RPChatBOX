"""Backend-local provider exposing setup private tools to SetupAgent."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from models.mcp_config import McpToolInfo
from rp.agent_runtime.contracts import (
    ChunkCandidate,
    DiscussionState,
    DraftTruthWrite,
    SetupDraftRefReadInput,
    SetupDraftRefReadItem,
    SetupDraftRefReadResult,
)
from rp.models.setup_drafts import (
    FoundationEntry,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)
from rp.models.setup_handoff import SetupToolResult
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_workspace import (
    CommitProposalStatus,
    QuestionSeverity,
    QuestionStatus,
    SetupStepId,
)
from rp.services.memory_crud_serialization_service import MemoryCrudSerializationService
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService


class SetupPatchStoryConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    patch: StoryConfigDraft


class SetupPatchWritingContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    patch: WritingContractDraft


class SetupPatchFoundationEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    entry: FoundationEntry


class SetupPatchLongformBlueprintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    patch: LongformBlueprintDraft


class SetupRaiseQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    text: str
    severity: QuestionSeverity


class SetupRegisterAssetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    asset_kind: str
    source_ref: str
    title: str | None = None


class SetupProposalCommitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    target_draft_refs: list[str]
    reason: str | None = None


class SetupReadWorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str


class SetupReadStepContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    user_edit_delta_ids: list[str] = Field(default_factory=list)


class SetupDiscussionUpdateStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    user_edit_delta_ids: list[str] = Field(default_factory=list)
    discussion_state: DiscussionState


class SetupChunkUpsertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    user_edit_delta_ids: list[str] = Field(default_factory=list)
    action: Literal["create", "refine", "promote"]
    chunk: ChunkCandidate


class SetupTruthWriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    user_edit_delta_ids: list[str] = Field(default_factory=list)
    truth_write: DraftTruthWrite


class SetupToolContractError(ValueError):
    """Structured setup-tool failure that runtime policies can interpret directly."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        error_code: str = "SETUP_TOOL_FAILED",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class SetupToolProvider:
    """Expose setup private contract tools for the SetupAgent execution layer."""

    provider_id = "rp_setup"
    server_name = "RP Setup"

    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilder,
        runtime_state_service: SetupAgentRuntimeStateService,
        serialization_service: MemoryCrudSerializationService | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._runtime_state_service = runtime_state_service
        self._serialization_service = serialization_service or MemoryCrudSerializationService()
        self._schemas = {
            "setup.discussion.update_state": SetupDiscussionUpdateStateInput,
            "setup.chunk.upsert": SetupChunkUpsertInput,
            "setup.truth.write": SetupTruthWriteInput,
            "setup.patch.story_config": SetupPatchStoryConfigInput,
            "setup.patch.writing_contract": SetupPatchWritingContractInput,
            "setup.patch.foundation_entry": SetupPatchFoundationEntryInput,
            "setup.patch.longform_blueprint": SetupPatchLongformBlueprintInput,
            "setup.question.raise": SetupRaiseQuestionInput,
            "setup.asset.register": SetupRegisterAssetInput,
            "setup.proposal.commit": SetupProposalCommitInput,
            "setup.read.workspace": SetupReadWorkspaceInput,
            "setup.read.step_context": SetupReadStepContextInput,
            "setup.read.draft_refs": SetupDraftRefReadInput,
        }

    def list_tools(self) -> list[McpToolInfo]:
        return [
            McpToolInfo(
                server_id=self.provider_id,
                server_name=self.server_name,
                name=tool_name,
                description=description,
                input_schema=model.model_json_schema(),
            )
            for tool_name, description, model in (
                (
                    "setup.discussion.update_state",
                    "Update the runtime-private discussion state for the current setup step. Use when you have clarified confirmed points, open questions, conflicts, or candidate directions. Optionally pass selected user_edit_delta_ids when reconciling against specific user edits. Do not use this to mutate SetupWorkspace drafts directly. Target object: DiscussionState. Important field: discussion_state.",
                    SetupDiscussionUpdateStateInput,
                ),
                (
                    "setup.chunk.upsert",
                    "Create, refine, or promote one chunk candidate distilled from discussion. Use when a specific setup block is becoming structured enough to track as a truth candidate. Optionally pass selected user_edit_delta_ids when the chunk is being reconciled after user edits. Do not use this as the final draft write. Target object: ChunkCandidate. Important fields: action, chunk.",
                    SetupChunkUpsertInput,
                ),
                (
                    "setup.truth.write",
                    "Lower one runtime-private draft truth write intent into the current setup draft via the existing patch/controller chain. Use only when one chunk is stable enough to land in draft. Optionally pass selected user_edit_delta_ids when writing a truth update that responds to specific user edits. Do not use this for commit proposal directly. Target object: DraftTruthWrite. Important field: truth_write.",
                    SetupTruthWriteInput,
                ),
                (
                    "setup.patch.story_config",
                    "Update the story_config draft. Use when converging model/runtime preferences. Do not use for mode changes. Target object: StoryConfigDraft. Important field: patch. Example: set notes or post_write_policy_preset.",
                    SetupPatchStoryConfigInput,
                ),
                (
                    "setup.patch.writing_contract",
                    "Update the writing_contract draft. Use when clarifying POV/style/constraints. Do not use to store one giant prompt blob. Target object: WritingContractDraft. Important field: patch.",
                    SetupPatchWritingContractInput,
                ),
                (
                    "setup.patch.foundation_entry",
                    "Create or update one foundation entry. Use for stable world/character/rule facts. Do not use for loose brainstorming notes. Target object: FoundationDraft entry. Important field: entry.",
                    SetupPatchFoundationEntryInput,
                ),
                (
                    "setup.patch.longform_blueprint",
                    "Update the longform_blueprint draft. Use for premise/conflict/arc/chapter plan convergence. Do not use for active prose generation. Target object: LongformBlueprintDraft. Important field: patch.",
                    SetupPatchLongformBlueprintInput,
                ),
                (
                    "setup.question.raise",
                    "Create an open setup question. Use when an ambiguity is blocking or needs explicit user decision. Do not use for generic filler text. Target object: OpenQuestion. Important field: text.",
                    SetupRaiseQuestionInput,
                ),
                (
                    "setup.asset.register",
                    "Register a setup-scoped asset reference. Use when the user provides a relevant reference document or asset. Do not use for Memory OS mutation. Target object: ImportedAssetRaw. Important field: source_ref.",
                    SetupRegisterAssetInput,
                ),
                (
                    "setup.proposal.commit",
                    "Create a commit proposal for the current step when the draft is sufficiently converged. Do not call this before clarifying critical ambiguities. Target object: CommitProposal. Important field: target_draft_refs.",
                    SetupProposalCommitInput,
                ),
                (
                    "setup.read.workspace",
                    "Read the current SetupWorkspace state. Use when you need the latest draft/truth view. Do not use as a substitute for current-step reasoning every turn. Target object: SetupWorkspace. Important field: workspace_id.",
                    SetupReadWorkspaceInput,
                ),
                (
                    "setup.read.step_context",
                    "Read a deterministic context packet for one setup step. Use when you need the current draft snapshot plus committed summaries and optionally selected user edit deltas. Do not use to mutate anything. Target object: SetupContextPacket. Important field: step_id.",
                    SetupReadStepContextInput,
                ),
                (
                    "setup.read.draft_refs",
                    "Read exact current-step setup draft details by compact-summary refs. Use after compaction when recovery_hints point to draft:story_config, draft:writing_contract, draft:longform_blueprint, or foundation:<entry_id>. Read-only; never use for prior-stage raw discussion or Memory OS state.",
                    SetupDraftRefReadInput,
                ),
            )
        ]

    async def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._schemas.get(tool_name)
        if model is None:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="unknown_tool",
                    message=f"Unknown setup tool: {tool_name}",
                ),
                "error_code": "UNKNOWN_TOOL",
            }
        try:
            input_model = model.model_validate(arguments)
            result = await self._dispatch(tool_name=tool_name, input_model=input_model)
            return {
                "success": True,
                "content": self._serialization_service.serialize_result(result),
                "error_code": None,
            }
        except SetupToolContractError as exc:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code=exc.code,
                    message=str(exc),
                    retryable=exc.retryable,
                    details=exc.details,
                ),
                "error_code": exc.error_code,
            }
        except ValidationError as exc:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="schema_validation_failed",
                    message="Setup tool arguments failed validation",
                    details=self._validation_error_details(
                        tool_name=tool_name,
                        arguments=arguments,
                        exc=exc,
                    ),
                ),
                "error_code": "SCHEMA_VALIDATION_FAILED",
            }
        except ValueError as exc:
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="setup_tool_failed",
                    message=str(exc),
                    details=self._error_details(
                        tool_name=tool_name,
                        failure_origin="domain",
                        repair_strategy="continue_discussion",
                    ),
                ),
                "error_code": "SETUP_TOOL_FAILED",
            }
        except Exception as exc:  # pragma: no cover - defensive surface
            self._workspace_service.rollback()
            return {
                "success": False,
                "content": self._serialization_service.serialize_error(
                    code="execution_error",
                    message=f"Setup tool execution failed: {exc}",
                    retryable=True,
                    details=self._error_details(
                        tool_name=tool_name,
                        failure_origin="execution",
                        repair_strategy="continue_discussion",
                        transient_retry=True,
                    ),
                ),
                "error_code": "EXECUTION_ERROR",
            }

    async def _dispatch(self, *, tool_name: str, input_model: Any) -> Any:
        if tool_name == "setup.discussion.update_state":
            workspace = self._require_workspace(input_model.workspace_id)
            context_packet = self._build_context_packet(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                user_edit_delta_ids=list(input_model.user_edit_delta_ids),
            )
            snapshot = self._runtime_state_service.replace_discussion_state(
                workspace=workspace,
                context_packet=context_packet,
                step_id=input_model.step_id,
                discussion_state=input_model.discussion_state,
            )
            return self._cognitive_tool_result(
                message="Updated discussion state",
                updated_refs=["cognitive:discussion_state"],
                snapshot=snapshot,
            )
        if tool_name == "setup.chunk.upsert":
            workspace = self._require_workspace(input_model.workspace_id)
            context_packet = self._build_context_packet(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                user_edit_delta_ids=list(input_model.user_edit_delta_ids),
            )
            snapshot = self._runtime_state_service.upsert_chunk(
                workspace=workspace,
                context_packet=context_packet,
                step_id=input_model.step_id,
                chunk=input_model.chunk,
                action=input_model.action,
            )
            return self._cognitive_tool_result(
                message="Upserted chunk candidate",
                updated_refs=[f"cognitive:chunk:{input_model.chunk.candidate_id}"],
                snapshot=snapshot,
            )
        if tool_name == "setup.truth.write":
            workspace = self._require_workspace(input_model.workspace_id)
            updated_refs = self._apply_truth_write(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                truth_write=input_model.truth_write,
            )
            refreshed_workspace = self._require_workspace(input_model.workspace_id)
            context_packet = self._build_context_packet(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                user_edit_delta_ids=list(input_model.user_edit_delta_ids),
            )
            snapshot = self._runtime_state_service.record_truth_write(
                workspace=refreshed_workspace,
                context_packet=context_packet,
                step_id=input_model.step_id,
                truth_write=input_model.truth_write,
            )
            return self._cognitive_tool_result(
                message="Wrote draft truth into setup draft",
                updated_refs=updated_refs,
                snapshot=snapshot,
            )
        if tool_name == "setup.patch.story_config":
            self._workspace_service.patch_story_config(
                workspace_id=input_model.workspace_id,
                patch=input_model.patch,
            )
            return SetupToolResult(
                success=True,
                message="Updated story_config draft",
                updated_refs=["draft:story_config"],
            )
        if tool_name == "setup.patch.writing_contract":
            self._workspace_service.patch_writing_contract(
                workspace_id=input_model.workspace_id,
                patch=input_model.patch,
            )
            return SetupToolResult(
                success=True,
                message="Updated writing_contract draft",
                updated_refs=["draft:writing_contract"],
            )
        if tool_name == "setup.patch.foundation_entry":
            self._workspace_service.patch_foundation_entry(
                workspace_id=input_model.workspace_id,
                entry=input_model.entry,
            )
            return SetupToolResult(
                success=True,
                message="Updated foundation draft entry",
                updated_refs=[f"foundation:{input_model.entry.entry_id}"],
            )
        if tool_name == "setup.patch.longform_blueprint":
            self._workspace_service.patch_longform_blueprint(
                workspace_id=input_model.workspace_id,
                patch=input_model.patch,
            )
            return SetupToolResult(
                success=True,
                message="Updated longform_blueprint draft",
                updated_refs=["draft:longform_blueprint"],
            )
        if tool_name == "setup.question.raise":
            question = self._workspace_service.raise_question(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                text=input_model.text,
                severity=input_model.severity,
            )
            return SetupToolResult(
                success=True,
                message="Raised setup question",
                updated_refs=[f"question:{question.question_id}"],
            )
        if tool_name == "setup.asset.register":
            asset = self._workspace_service.register_asset(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                asset_kind=input_model.asset_kind,
                source_ref=input_model.source_ref,
                title=input_model.title,
            )
            return SetupToolResult(
                success=True,
                message="Registered setup asset",
                updated_refs=[f"asset:{asset.asset_id}"],
            )
        if tool_name == "setup.proposal.commit":
            self._ensure_commit_targets_present(input_model=input_model)
            self._ensure_commit_allowed(input_model=input_model)
            proposal = self._workspace_service.propose_commit(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                target_draft_refs=input_model.target_draft_refs,
                reason=input_model.reason,
            )
            return SetupToolResult(
                success=True,
                message=proposal.review_message,
                updated_refs=[f"proposal:{proposal.proposal_id}"],
                warnings=proposal.unresolved_warnings,
            )
        if tool_name == "setup.read.workspace":
            return self._require_workspace(input_model.workspace_id)
        if tool_name == "setup.read.step_context":
            return self._build_context_packet(
                workspace_id=input_model.workspace_id,
                step_id=input_model.step_id,
                user_edit_delta_ids=list(input_model.user_edit_delta_ids),
            )
        if tool_name == "setup.read.draft_refs":
            return self._read_draft_refs(input_model=input_model)
        raise ValueError(f"Unknown setup tool: {tool_name}")

    def _read_draft_refs(
        self,
        *,
        input_model: SetupDraftRefReadInput,
    ) -> SetupDraftRefReadResult:
        if not input_model.refs:
            raise SetupToolContractError(
                code="setup_draft_refs_required",
                message="setup.read.draft_refs requires at least one draft ref.",
                error_code="SETUP_DRAFT_REFS_REQUIRED",
                details=self._error_details(
                    tool_name="setup.read.draft_refs",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["refs"],
                ),
            )

        workspace = self._require_workspace(input_model.workspace_id)
        max_chars = max(1, min(int(input_model.max_chars or 4000), 20000))
        items: list[SetupDraftRefReadItem] = []
        missing_refs: list[str] = []
        for raw_ref in input_model.refs:
            ref = str(raw_ref or "").strip()
            if not ref:
                continue
            item = self._resolve_draft_ref(
                workspace=workspace,
                ref=ref,
                detail=input_model.detail,
                max_chars=max_chars,
            )
            items.append(item)
            if not item.found:
                missing_refs.append(ref)
        return SetupDraftRefReadResult(
            success=not missing_refs,
            items=items,
            missing_refs=missing_refs,
        )

    def _resolve_draft_ref(
        self,
        *,
        workspace,
        ref: str,
        detail: str,
        max_chars: int,
    ) -> SetupDraftRefReadItem:
        if ref == "draft:story_config":
            return self._draft_ref_item(
                ref=ref,
                block_type="story_config",
                title="Story Config Draft",
                model=workspace.story_config_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref == "draft:writing_contract":
            return self._draft_ref_item(
                ref=ref,
                block_type="writing_contract",
                title="Writing Contract Draft",
                model=workspace.writing_contract_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref == "draft:longform_blueprint":
            return self._draft_ref_item(
                ref=ref,
                block_type="longform_blueprint",
                title="Longform Blueprint Draft",
                model=workspace.longform_blueprint_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref.startswith("foundation:"):
            entry_id = ref.removeprefix("foundation:").strip()
            foundation_draft = workspace.foundation_draft
            entry = None
            if foundation_draft is not None:
                entry = next(
                    (item for item in foundation_draft.entries if item.entry_id == entry_id),
                    None,
                )
            return self._draft_ref_item(
                ref=ref,
                block_type="foundation_entry",
                title=(
                    (entry.title or entry.path or entry.entry_id)
                    if entry is not None
                    else None
                ),
                model=entry,
                detail=detail,
                max_chars=max_chars,
            )
        return SetupDraftRefReadItem(ref=ref, found=False)

    def _draft_ref_item(
        self,
        *,
        ref: str,
        block_type: Literal[
            "story_config",
            "writing_contract",
            "foundation_entry",
            "longform_blueprint",
        ],
        title: str | None,
        model: BaseModel | None,
        detail: str,
        max_chars: int,
    ) -> SetupDraftRefReadItem:
        if model is None:
            return SetupDraftRefReadItem(ref=ref, found=False, block_type=block_type)
        payload = model.model_dump(mode="json", exclude_none=True)
        return SetupDraftRefReadItem(
            ref=ref,
            found=True,
            block_type=block_type,
            title=title,
            summary=self._draft_ref_summary(block_type=block_type, payload=payload),
            payload=(
                self._bounded_payload(payload=payload, max_chars=max_chars)
                if detail == "full"
                else None
            ),
        )

    @classmethod
    def _draft_ref_summary(
        cls,
        *,
        block_type: str,
        payload: dict[str, Any],
    ) -> str:
        if block_type == "story_config":
            return cls._join_preview(
                [
                    cls._prefixed_preview("model", payload.get("model_profile_ref")),
                    cls._prefixed_preview("worker", payload.get("worker_profile_ref")),
                    cls._prefixed_preview("policy", payload.get("post_write_policy_preset")),
                    cls._coerce_preview_text(payload.get("notes")),
                ]
            )
        if block_type == "writing_contract":
            return cls._join_preview(
                [
                    cls._prefixed_preview("pov", payload.get("pov_rules")),
                    cls._prefixed_preview("style", payload.get("style_rules")),
                    cls._prefixed_preview("constraints", payload.get("writing_constraints")),
                    cls._coerce_preview_text(payload.get("notes")),
                ]
            )
        if block_type == "longform_blueprint":
            return cls._join_preview(
                [
                    cls._coerce_preview_text(payload.get("premise")),
                    cls._coerce_preview_text(payload.get("central_conflict")),
                    cls._coerce_preview_text(payload.get("chapter_strategy")),
                ]
            )
        content = payload.get("content")
        if isinstance(content, dict):
            for key in ("summary", "description", "premise"):
                preview = cls._coerce_preview_text(content.get(key))
                if preview:
                    return preview
            for value in content.values():
                preview = cls._coerce_preview_text(value)
                if preview:
                    return preview
        return cls._join_preview(
            [
                cls._coerce_preview_text(payload.get("title")),
                cls._coerce_preview_text(payload.get("path")),
            ]
        )

    @staticmethod
    def _bounded_payload(*, payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(raw) <= max_chars:
            return payload
        return {
            "_truncated": True,
            "preview": raw[:max_chars],
        }

    @classmethod
    def _prefixed_preview(cls, label: str, value: Any) -> str | None:
        preview = cls._coerce_preview_text(value)
        if not preview:
            return None
        return f"{label}: {preview}"

    @staticmethod
    def _coerce_preview_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(parts[:3]) if parts else None
        if isinstance(value, dict):
            parts = [str(item).strip() for item in value.values() if str(item).strip()]
            return ", ".join(parts[:3]) if parts else None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _join_preview(parts: list[str | None]) -> str:
        return " | ".join(part for part in parts if part)[:500]

    def _ensure_commit_targets_present(self, *, input_model: SetupProposalCommitInput) -> None:
        if input_model.target_draft_refs:
            return
        raise SetupToolContractError(
            code="setup_commit_missing_targets",
            message="Commit proposal requires at least one target draft ref.",
            details=self._error_details(
                tool_name="setup.proposal.commit",
                failure_origin="validation",
                repair_strategy="auto_repair",
                required_fields=["target_draft_refs"],
            ),
        )

    def _ensure_commit_allowed(self, *, input_model: SetupProposalCommitInput) -> None:
        workspace = self._require_workspace(input_model.workspace_id)
        self._ensure_commit_not_blocked_by_cognitive_state(
            workspace_id=input_model.workspace_id,
            step_id=input_model.step_id,
        )

        blocking_questions = [
            question
            for question in workspace.open_questions
            if question.step_id == input_model.step_id
            and question.status == QuestionStatus.OPEN
            and question.severity == QuestionSeverity.BLOCKING
        ]
        if blocking_questions:
            raise SetupToolContractError(
                code="setup_commit_blocked",
                message=(
                    "Commit proposal is blocked because the current step still has "
                    "blocking open questions."
                ),
                details=self._error_details(
                    tool_name="setup.proposal.commit",
                    failure_origin="policy",
                    repair_strategy="block_commit",
                    block_commit=True,
                    extra={
                        "blocking_open_question_count": len(blocking_questions),
                        "blocking_open_question_ids": [
                            question.question_id for question in blocking_questions
                        ],
                    },
                ),
            )

        latest_proposal = self._latest_step_proposal(
            workspace=workspace,
            step_id=input_model.step_id,
        )
        if latest_proposal is not None and latest_proposal.status == CommitProposalStatus.REJECTED:
            raise SetupToolContractError(
                code="setup_commit_rejected_previously",
                message=(
                    "Commit proposal is blocked because the previous proposal for this step "
                    "was rejected and discussion must continue first."
                ),
                details=self._error_details(
                    tool_name="setup.proposal.commit",
                    failure_origin="policy",
                    repair_strategy="block_commit",
                    block_commit=True,
                    extra={
                        "last_proposal_id": latest_proposal.proposal_id,
                        "last_proposal_status": latest_proposal.status.value,
                    },
                ),
            )

    def _validation_error_details(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        exc: ValidationError,
    ) -> dict[str, Any]:
        errors = exc.errors()
        return self._error_details(
            tool_name=tool_name,
            failure_origin="validation",
            repair_strategy="auto_repair",
            required_fields=self._required_fields_from_errors(errors),
            extra={
                "errors": errors,
                "provided_fields": sorted(arguments.keys()) if isinstance(arguments, dict) else [],
            },
        )

    @staticmethod
    def _required_fields_from_errors(errors: list[dict[str, Any]]) -> list[str]:
        required_fields: list[str] = []
        for item in errors:
            error_type = str(item.get("type") or "")
            if "missing" not in error_type:
                continue
            loc = item.get("loc")
            if isinstance(loc, (list, tuple)):
                field = ".".join(
                    str(part)
                    for part in loc
                    if part not in {"body", "arguments"}
                )
            elif loc:
                field = str(loc)
            else:
                field = ""
            if field and field not in required_fields:
                required_fields.append(field)
        return required_fields

    @staticmethod
    def _error_details(
        *,
        tool_name: str,
        failure_origin: str,
        repair_strategy: str,
        required_fields: list[str] | None = None,
        block_commit: bool = False,
        transient_retry: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = {
            "tool_name": tool_name,
            "failure_origin": failure_origin,
            "repair_strategy": repair_strategy,
            "required_fields": list(required_fields or []),
            "ask_user": repair_strategy == "ask_user",
            "block_commit": block_commit,
            "transient_retry": transient_retry,
        }
        if extra:
            details.update(extra)
        return details

    def _ensure_commit_not_blocked_by_cognitive_state(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
    ) -> None:
        snapshot = self._runtime_state_service.get_snapshot(
            workspace_id=workspace_id,
            step_id=step_id,
        )
        if snapshot is None:
            return

        if snapshot.invalidated:
            raise SetupToolContractError(
                code="setup_commit_blocked_by_invalidated_cognitive_state",
                message=(
                    "Commit proposal is blocked because the current cognitive state is stale "
                    "and must be reconciled against the latest draft first."
                ),
                details=self._error_details(
                    tool_name="setup.proposal.commit",
                    failure_origin="policy",
                    repair_strategy="block_commit",
                    block_commit=True,
                    extra={
                        "invalidation_reasons": list(snapshot.invalidation_reasons),
                    },
                ),
            )

        truth_write = snapshot.active_truth_write
        if truth_write is None:
            return
        if not truth_write.ready_for_review:
            raise SetupToolContractError(
                code="setup_commit_blocked_truth_write_not_ready_for_review",
                message=(
                    "Commit proposal is blocked because the current draft truth write has not "
                    "explicitly entered review-ready state yet."
                ),
                details=self._error_details(
                    tool_name="setup.proposal.commit",
                    failure_origin="policy",
                    repair_strategy="block_commit",
                    block_commit=True,
                    extra={
                        "ready_for_review": truth_write.ready_for_review,
                    },
                ),
            )

        if not truth_write.remaining_open_issues:
            return

        raise SetupToolContractError(
            code="setup_commit_blocked_by_truth_write_issues",
            message=(
                "Commit proposal is blocked because the current draft truth write still has "
                "open issues that must be resolved first."
            ),
            details=self._error_details(
                tool_name="setup.proposal.commit",
                failure_origin="policy",
                repair_strategy="block_commit",
                block_commit=True,
                extra={
                    "remaining_open_issues": list(truth_write.remaining_open_issues),
                },
            ),
        )

    def _apply_truth_write(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        truth_write: DraftTruthWrite,
    ) -> list[str]:
        workspace = self._require_workspace(workspace_id)
        expected_step = self._step_for_truth_block_type(truth_write.block_type)
        if expected_step != step_id:
            raise SetupToolContractError(
                code="setup_truth_write_step_mismatch",
                message="Truth write block_type does not match the target setup step.",
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["truth_write.block_type", "step_id"],
                ),
            )

        if truth_write.block_type == "story_config":
            patch = self._build_singleton_truth_write_payload(
                truth_write=truth_write,
                current_model=workspace.story_config_draft,
                model_cls=StoryConfigDraft,
                fixed_target_ref="draft:story_config",
            )
            self._validate_truth_write_semantics(
                block_type=truth_write.block_type,
                payload_model=patch,
            )
            self._workspace_service.patch_story_config(workspace_id=workspace_id, patch=patch)
            return ["draft:story_config"]

        if truth_write.block_type == "writing_contract":
            patch = self._build_singleton_truth_write_payload(
                truth_write=truth_write,
                current_model=workspace.writing_contract_draft,
                model_cls=WritingContractDraft,
                fixed_target_ref="draft:writing_contract",
            )
            self._validate_truth_write_semantics(
                block_type=truth_write.block_type,
                payload_model=patch,
            )
            self._workspace_service.patch_writing_contract(workspace_id=workspace_id, patch=patch)
            return ["draft:writing_contract"]

        if truth_write.block_type == "foundation_entry":
            entry = self._build_foundation_truth_write_entry(
                truth_write=truth_write,
                workspace=workspace,
            )
            self._validate_truth_write_semantics(
                block_type=truth_write.block_type,
                payload_model=entry,
            )
            self._workspace_service.patch_foundation_entry(workspace_id=workspace_id, entry=entry)
            return [f"foundation:{entry.entry_id}"]

        if truth_write.block_type == "longform_blueprint":
            patch = self._build_singleton_truth_write_payload(
                truth_write=truth_write,
                current_model=workspace.longform_blueprint_draft,
                model_cls=LongformBlueprintDraft,
                fixed_target_ref="draft:longform_blueprint",
            )
            self._validate_truth_write_semantics(
                block_type=truth_write.block_type,
                payload_model=patch,
            )
            self._workspace_service.patch_longform_blueprint(workspace_id=workspace_id, patch=patch)
            return ["draft:longform_blueprint"]

        raise SetupToolContractError(
            code="setup_truth_write_unknown_block_type",
            message=f"Unsupported truth write block_type: {truth_write.block_type}",
            details=self._error_details(
                tool_name="setup.truth.write",
                failure_origin="validation",
                repair_strategy="auto_repair",
                required_fields=["truth_write.block_type"],
            ),
        )

    def _build_context_packet(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        user_edit_delta_ids: list[str] | None = None,
    ):
        workspace = self._require_workspace(workspace_id)
        return self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace_id,
                current_step=step_id.value,
                user_prompt="",
                user_edit_delta_ids=list(user_edit_delta_ids or []),
                token_budget=None,
            )
        )

    def _build_singleton_truth_write_payload(
        self,
        *,
        truth_write: DraftTruthWrite,
        current_model: Any,
        model_cls: Any,
        fixed_target_ref: str,
    ):
        if truth_write.target_ref is not None and truth_write.target_ref != fixed_target_ref:
            raise SetupToolContractError(
                code="setup_truth_write_target_ref_mismatch",
                message=(
                    f"Truth write target_ref must be {fixed_target_ref!r} for "
                    f"{truth_write.block_type}."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["truth_write.target_ref"],
                ),
            )

        existing_payload = (
            current_model.model_dump(mode="json", exclude_none=True)
            if current_model is not None
            else {}
        )
        has_existing = self._has_meaningful_payload(existing_payload)

        if truth_write.operation == "create" and has_existing:
            raise SetupToolContractError(
                code="setup_truth_write_create_requires_empty_target",
                message="Truth write create cannot target a draft block that already has content.",
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="continue_discussion",
                    required_fields=["truth_write.operation"],
                ),
            )

        if truth_write.operation == "merge":
            merged_payload = self._deep_merge(existing_payload, truth_write.payload)
            return model_cls.model_validate(merged_payload)

        return model_cls.model_validate(truth_write.payload)

    def _build_foundation_truth_write_entry(
        self,
        *,
        truth_write: DraftTruthWrite,
        workspace,
    ) -> FoundationEntry:
        entry = FoundationEntry.model_validate(truth_write.payload)
        expected_target_ref = f"foundation:{entry.entry_id}"
        if truth_write.target_ref is not None and truth_write.target_ref != expected_target_ref:
            raise SetupToolContractError(
                code="setup_truth_write_target_ref_mismatch",
                message=(
                    f"Truth write target_ref must be {expected_target_ref!r} for "
                    "this foundation entry."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["truth_write.target_ref"],
                ),
            )

        existing_entry = None
        foundation_draft = workspace.foundation_draft
        if foundation_draft is not None:
            existing_entry = next(
                (item for item in foundation_draft.entries if item.entry_id == entry.entry_id),
                None,
            )

        if truth_write.operation == "create" and existing_entry is not None:
            raise SetupToolContractError(
                code="setup_truth_write_create_requires_empty_target",
                message="Truth write create cannot target an existing foundation entry.",
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="continue_discussion",
                    required_fields=["truth_write.operation"],
                ),
            )

        if truth_write.operation == "replace" and existing_entry is None:
            raise SetupToolContractError(
                code="setup_truth_write_replace_requires_existing_target",
                message="Truth write replace requires the target foundation entry to already exist.",
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="validation",
                    repair_strategy="continue_discussion",
                    required_fields=["truth_write.operation", "truth_write.target_ref"],
                ),
            )

        if truth_write.operation == "merge" and existing_entry is not None:
            merged_payload = self._deep_merge(
                existing_entry.model_dump(mode="json", exclude_none=True),
                truth_write.payload,
            )
            return FoundationEntry.model_validate(merged_payload)

        return entry

    @staticmethod
    def _has_meaningful_payload(payload: dict[str, Any]) -> bool:
        for value in payload.values():
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, list) and value:
                return True
            if value not in (None, "", [], {}):
                return True
        return False

    @staticmethod
    def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = SetupToolProvider._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _validate_truth_write_semantics(
        self,
        *,
        block_type: str,
        payload_model: Any,
    ) -> None:
        if block_type == "story_config":
            model = payload_model
            has_value = any(
                bool(value)
                for value in (
                    model.model_profile_ref,
                    model.worker_profile_ref,
                    model.post_write_policy_preset,
                    model.notes,
                )
            )
            if has_value:
                return
            raise SetupToolContractError(
                code="setup_truth_write_requires_user_input",
                message=(
                    "Story config truth write still lacks user-confirmed configuration "
                    "content and should be clarified first."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="semantic_validation",
                    repair_strategy="ask_user",
                    required_fields=["truth_write.payload"],
                ),
            )

        if block_type == "writing_contract":
            model = payload_model
            has_value = any(
                (
                    model.pov_rules,
                    model.style_rules,
                    model.writing_constraints,
                    model.task_writing_rules,
                    bool(model.notes),
                )
            )
            if has_value:
                return
            raise SetupToolContractError(
                code="setup_truth_write_requires_user_input",
                message=(
                    "Writing contract truth write still lacks concrete user-facing writing "
                    "preferences and should ask the user first."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="semantic_validation",
                    repair_strategy="ask_user",
                    required_fields=["truth_write.payload"],
                ),
            )

        if block_type == "foundation_entry":
            model = payload_model
            has_content = bool(model.content)
            if has_content:
                return
            raise SetupToolContractError(
                code="setup_truth_write_requires_user_input",
                message=(
                    "Foundation entry truth write is structurally valid but still lacks the "
                    "actual fact content that must be confirmed with the user."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="semantic_validation",
                    repair_strategy="ask_user",
                    required_fields=["truth_write.payload.content"],
                ),
            )

        if block_type == "longform_blueprint":
            model = payload_model
            has_value = any(
                (
                    model.premise,
                    model.central_conflict,
                    model.protagonist_arc,
                    model.cast_plan,
                    model.chapter_strategy,
                    model.section_strategy,
                    model.ending_direction,
                    model.chapter_blueprints,
                )
            )
            if has_value:
                return
            raise SetupToolContractError(
                code="setup_truth_write_requires_user_input",
                message=(
                    "Longform blueprint truth write still lacks concrete blueprint content "
                    "and should be clarified with the user first."
                ),
                details=self._error_details(
                    tool_name="setup.truth.write",
                    failure_origin="semantic_validation",
                    repair_strategy="ask_user",
                    required_fields=["truth_write.payload"],
                ),
            )

    def _cognitive_tool_result(
        self,
        *,
        message: str,
        updated_refs: list[str],
        snapshot,
    ) -> dict[str, Any]:
        summary = self._runtime_state_service.summarize_for_prompt(snapshot)
        return {
            "success": True,
            "message": message,
            "updated_refs": updated_refs,
            "cognitive_state_snapshot": snapshot.model_dump(mode="json", exclude_none=True),
            "cognitive_state_summary": (
                summary.model_dump(mode="json", exclude_none=True)
                if summary is not None
                else None
            ),
        }

    def _require_workspace(self, workspace_id: str):
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        return workspace

    @staticmethod
    def _step_for_truth_block_type(block_type: str) -> SetupStepId:
        mapping = {
            "story_config": SetupStepId.STORY_CONFIG,
            "writing_contract": SetupStepId.WRITING_CONTRACT,
            "foundation_entry": SetupStepId.FOUNDATION,
            "longform_blueprint": SetupStepId.LONGFORM_BLUEPRINT,
        }
        if block_type not in mapping:
            raise ValueError(f"Unsupported truth write block_type: {block_type}")
        return mapping[block_type]

    @staticmethod
    def _latest_step_proposal(*, workspace, step_id: SetupStepId):
        proposals = [
            proposal
            for proposal in workspace.commit_proposals
            if proposal.step_id == step_id
        ]
        if not proposals:
            return None
        return max(
            proposals,
            key=lambda item: (
                SetupToolProvider._datetime_key(item.reviewed_at),
                SetupToolProvider._datetime_key(item.created_at),
            ),
        )

    @staticmethod
    def _datetime_key(value) -> float:
        if value is None:
            return 0.0
        if hasattr(value, "timestamp"):
            return float(value.timestamp())
        return 0.0
