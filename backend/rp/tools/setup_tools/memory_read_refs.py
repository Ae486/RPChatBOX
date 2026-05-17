"""Handler for setup.memory.read_refs."""

from __future__ import annotations

from typing import Any

from rp.tools.setup_tool_contracts import SetupToolContractError

from .base import SetupToolFamilyBase


class MemoryReadRefsTool(SetupToolFamilyBase):
    def _dispatch_memory_read_refs(self, input_model: Any) -> Any:
        if not input_model.refs:
            raise SetupToolContractError(
                code="setup_memory_refs_required",
                message="setup.memory.read_refs requires at least one ref.",
                error_code="SETUP_MEMORY_REFS_REQUIRED",
                details=self._error_details(
                    tool_name="setup.memory.read_refs",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["refs"],
                ),
            )
        workspace = self._require_workspace(input_model.workspace_id)
        return self._require_setup_memory_service().read_refs(
            workspace=workspace,
            refs=list(input_model.refs),
            detail=input_model.detail,
            max_chars=input_model.max_chars,
            context_packet=self._memory_context_packet(workspace=workspace),
            runtime_snapshot=self._memory_runtime_snapshot(workspace=workspace),
        )
