"""Shared helpers for setup tool family handlers."""

from __future__ import annotations

from typing import Any, Protocol

from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import SetupStepId
from rp.services.setup_agent_runtime_state_service import (
    SetupAgentRuntimeStateService,
)
from rp.services.setup_truth_index_service import SetupTruthIndexService
from rp.setup_agent_memory.service import SetupSessionMemoryService
from rp.services.setup_workspace_service import SetupWorkspaceService


class SetupContextBuilderLike(Protocol):
    def build(self, input_model: SetupContextBuilderInput) -> Any: ...


def setup_tool_error_details(
    *,
    tool_name: str,
    failure_origin: str,
    repair_strategy: str,
    required_fields: list[str] | None = None,
    transient_retry: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "tool_name": tool_name,
        "failure_origin": failure_origin,
        "repair_strategy": repair_strategy,
    }
    if required_fields is not None:
        details["required_fields"] = required_fields
    if transient_retry:
        details["transient_retry"] = True
    if extra:
        details.update(extra)
    return details


class SetupToolFamilyBase:
    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilderLike,
        runtime_state_service: SetupAgentRuntimeStateService,
        truth_index_service: SetupTruthIndexService,
        setup_memory_service: SetupSessionMemoryService | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._runtime_state_service = runtime_state_service
        self._truth_index_service = truth_index_service
        self._setup_memory_service = setup_memory_service

    def _require_workspace(self, workspace_id: str):
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        return workspace

    def _build_context_packet(
        self,
        *,
        workspace_id: str,
        step_id: SetupStepId,
        stage_id: SetupStageId | None = None,
        user_edit_delta_ids: list[str] | None = None,
    ):
        workspace = self._require_workspace(workspace_id)
        current_stage = stage_id
        if current_stage is None and step_id == workspace.current_step:
            current_stage = workspace.current_stage
        return self._context_builder.build(
            SetupContextBuilderInput(
                mode=workspace.mode.value,
                workspace_id=workspace_id,
                current_step=step_id.value,
                current_stage=(
                    current_stage.value if current_stage is not None else None
                ),
                user_prompt="",
                user_edit_delta_ids=list(user_edit_delta_ids or []),
                token_budget=None,
            )
        )

    def _error_details(
        self,
        *,
        tool_name: str,
        failure_origin: str,
        repair_strategy: str,
        required_fields: list[str] | None = None,
        transient_retry: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return setup_tool_error_details(
            tool_name=tool_name,
            failure_origin=failure_origin,
            repair_strategy=repair_strategy,
            required_fields=required_fields,
            transient_retry=transient_retry,
            extra=extra,
        )

    def _memory_context_packet(self, *, workspace):
        return self._build_context_packet(
            workspace_id=workspace.workspace_id,
            step_id=workspace.current_step,
            stage_id=workspace.current_stage,
        )

    def _memory_runtime_snapshot(self, *, workspace):
        return self._runtime_state_service.get_snapshot(
            workspace_id=workspace.workspace_id,
            step_id=workspace.current_step,
        )

    def _require_setup_memory_service(self) -> SetupSessionMemoryService:
        if self._setup_memory_service is None:
            raise ValueError("Setup session memory service is not configured.")
        return self._setup_memory_service

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
            "cognitive_state_snapshot": snapshot.model_dump(
                mode="json", exclude_none=True
            ),
            "cognitive_state_summary": (
                summary.model_dump(mode="json", exclude_none=True)
                if summary is not None
                else None
            ),
        }

    @staticmethod
    def _coerce_stage_id(value: str | None) -> SetupStageId | None:
        if not value:
            return None
        try:
            return SetupStageId(value)
        except ValueError:
            return None

    @staticmethod
    def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = SetupToolFamilyBase._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

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
