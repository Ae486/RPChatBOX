"""Handler for setup.stage_entry.read."""

from __future__ import annotations

from typing import Any

from rp.tools.setup_tool_contracts import SetupStageEntryReadInput

from .stage_entry_common import StageEntryToolBase


class StageEntryReadTool(StageEntryToolBase):
    def _dispatch_stage_entry_read(self, input_model: Any) -> Any:
        return self._stage_entry_read(input_model=input_model)

    def _stage_entry_read(
        self,
        input_model: SetupStageEntryReadInput,
    ) -> dict[str, Any]:
        _, stage_id, block = self._current_stage_entry_context(
            workspace_id=input_model.workspace_id,
            tool_name="setup.stage_entry.read",
        )
        entry = self._require_stage_entry(
            block=block,
            current_stage=stage_id,
            target_ref=input_model.target_ref,
            tool_name="setup.stage_entry.read",
        )
        return {
            "stage_id": stage_id.value,
            "entry": self._stage_entry_payload(
                stage_id=stage_id,
                entry=entry,
                include_sections=input_model.include_sections,
            ),
        }
