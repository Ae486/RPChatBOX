"""Handler for setup.stage_entry.delete."""

from __future__ import annotations

from typing import Any

from rp.models.setup_drafts import SetupStageDraftBlock
from rp.tools.setup_tool_contracts import SetupStageEntryDeleteInput

from .stage_entry_common import StageEntryToolBase


class StageEntryDeleteTool(StageEntryToolBase):
    def _dispatch_stage_entry_delete(self, input_model: Any) -> Any:
        return self._stage_entry_delete(input_model=input_model)

    def _stage_entry_delete(
        self,
        input_model: SetupStageEntryDeleteInput,
    ) -> dict[str, Any]:
        _, stage_id, block = self._current_stage_entry_context(
            workspace_id=input_model.workspace_id,
            tool_name="setup.stage_entry.delete",
        )
        entry = self._require_stage_entry(
            block=block,
            current_stage=stage_id,
            target_ref=input_model.target_ref,
            tool_name="setup.stage_entry.delete",
        )
        self._require_entry_fingerprint(
            entry=entry,
            basis_fingerprint=input_model.basis_fingerprint,
            tool_name="setup.stage_entry.delete",
        )
        updated_block = SetupStageDraftBlock(
            stage_id=stage_id,
            schema_metadata=block.schema_metadata,
            entries=[item for item in block.entries if item.entry_id != entry.entry_id],
            notes=block.notes,
        )
        self._workspace_service.patch_stage_draft(
            workspace_id=input_model.workspace_id,
            stage_id=stage_id,
            draft=updated_block,
        )
        return {
            "success": True,
            "message": f"Deleted {stage_id.value} draft entry",
            "stage_id": stage_id.value,
            "removed_refs": [
                self._stage_entry_ref(stage_id=stage_id, entry_id=entry.entry_id)
            ],
            "reason": input_model.reason,
        }
