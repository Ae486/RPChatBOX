"""Handler for setup.memory.open."""

from __future__ import annotations

from typing import Any

from rp.tools.setup_tool_contracts import SetupToolContractError

from .base import SetupToolFamilyBase


class MemoryOpenTool(SetupToolFamilyBase):
    def _dispatch_memory_open(self, input_model: Any) -> Any:
        if not str(input_model.ref or "").strip():
            raise SetupToolContractError(
                code="setup_memory_ref_required",
                message="setup.memory.open requires one ref.",
                error_code="SETUP_MEMORY_REF_REQUIRED",
                details=self._error_details(
                    tool_name="setup.memory.open",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["ref"],
                ),
            )
        workspace = self._require_workspace(input_model.workspace_id)
        return self._require_setup_memory_service().open_ref(
            workspace=workspace,
            ref=input_model.ref,
            max_chars=input_model.max_chars,
            context_packet=self._memory_context_packet(workspace=workspace),
            runtime_snapshot=self._memory_runtime_snapshot(workspace=workspace),
        )
