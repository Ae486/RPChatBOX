"""Handler for setup.memory.search."""

from __future__ import annotations

from typing import Any

from .base import SetupToolFamilyBase


class MemorySearchTool(SetupToolFamilyBase):
    def _dispatch_memory_search(self, input_model: Any) -> Any:
        workspace = self._require_workspace(input_model.workspace_id)
        return self._require_setup_memory_service().search(
            workspace=workspace,
            query=input_model.query,
            filters=input_model.filters,
            limit=input_model.limit,
            context_packet=self._memory_context_packet(workspace=workspace),
            runtime_snapshot=self._memory_runtime_snapshot(workspace=workspace),
        )
