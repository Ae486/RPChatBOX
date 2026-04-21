"""Backend-local provider exposing setup private tools to SetupAgent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from models.mcp_config import McpToolInfo
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
        serialization_service: MemoryCrudSerializationService | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._serialization_service = serialization_service or MemoryCrudSerializationService()
        self._schemas = {
            "setup.patch.story_config": SetupPatchStoryConfigInput,
            "setup.patch.writing_contract": SetupPatchWritingContractInput,
            "setup.patch.foundation_entry": SetupPatchFoundationEntryInput,
            "setup.patch.longform_blueprint": SetupPatchLongformBlueprintInput,
            "setup.question.raise": SetupRaiseQuestionInput,
            "setup.asset.register": SetupRegisterAssetInput,
            "setup.proposal.commit": SetupProposalCommitInput,
            "setup.read.workspace": SetupReadWorkspaceInput,
            "setup.read.step_context": SetupReadStepContextInput,
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
                    "Read a deterministic context packet for one setup step. Use when you need the current draft snapshot plus committed summaries. Do not use to mutate anything. Target object: SetupContextPacket. Important field: step_id.",
                    SetupReadStepContextInput,
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
            workspace = self._workspace_service.get_workspace(input_model.workspace_id)
            if workspace is None:
                raise ValueError(f"SetupWorkspace not found: {input_model.workspace_id}")
            return workspace
        if tool_name == "setup.read.step_context":
            workspace = self._workspace_service.get_workspace(input_model.workspace_id)
            if workspace is None:
                raise ValueError(f"SetupWorkspace not found: {input_model.workspace_id}")
            packet = self._context_builder.build(
                SetupContextBuilderInput(
                    mode=workspace.mode.value,
                    workspace_id=input_model.workspace_id,
                    current_step=input_model.step_id.value,
                    user_prompt="",
                    user_edit_delta_ids=[],
                    token_budget=None,
                )
            )
            return packet
        raise ValueError(f"Unknown setup tool: {tool_name}")

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
        workspace = self._workspace_service.get_workspace(input_model.workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {input_model.workspace_id}")

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
