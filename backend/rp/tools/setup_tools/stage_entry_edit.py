"""Handler for setup.stage_entry.edit."""

from __future__ import annotations

from typing import Any

from rp.models.setup_drafts import SetupStageDraftBlock
from rp.tools.setup_tool_contracts import SetupStageEntryEditInput

from .stage_entry_common import StageEntryToolBase


class StageEntryEditTool(StageEntryToolBase):
    def _dispatch_stage_entry_edit(self, input_model: Any) -> Any:
        return self._stage_entry_edit(input_model=input_model)

    def _stage_entry_edit(
        self,
        input_model: SetupStageEntryEditInput,
    ) -> dict[str, Any]:
        _, stage_id, block = self._current_stage_entry_context(
            workspace_id=input_model.workspace_id,
            tool_name="setup.stage_entry.edit",
        )
        entry = self._require_stage_entry(
            block=block,
            current_stage=stage_id,
            target_ref=input_model.target_ref,
            tool_name="setup.stage_entry.edit",
        )
        self._require_entry_fingerprint(
            entry=entry,
            basis_fingerprint=input_model.basis_fingerprint,
            tool_name="setup.stage_entry.edit",
        )
        updated_entry = self._apply_stage_entry_changes(
            stage_id=stage_id,
            entry=entry,
            changes=input_model.changes,
        )
        updated_block = SetupStageDraftBlock(
            stage_id=stage_id,
            schema_metadata=block.schema_metadata,
            entries=[
                updated_entry if item.entry_id == entry.entry_id else item
                for item in block.entries
            ],
            notes=block.notes,
        )
        self._workspace_service.patch_stage_draft(
            workspace_id=input_model.workspace_id,
            stage_id=stage_id,
            draft=updated_block,
        )
        return {
            "success": True,
            "message": f"Edited {stage_id.value} draft entry",
            "stage_id": stage_id.value,
            "updated_refs": [
                self._stage_entry_ref(
                    stage_id=stage_id,
                    entry_id=updated_entry.entry_id,
                )
            ],
            "entry": self._stage_entry_payload(
                stage_id=stage_id,
                entry=updated_entry,
                include_sections=True,
            ),
        }
