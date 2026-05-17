"""Handler for setup.stage_entry.write."""

from __future__ import annotations

from typing import Any

from rp.models.setup_drafts import SetupStageDraftBlock
from rp.tools.setup_tool_contracts import SetupStageEntryWriteInput

from .stage_entry_common import StageEntryToolBase


class StageEntryWriteTool(StageEntryToolBase):
    def _dispatch_stage_entry_write(self, input_model: Any) -> Any:
        return self._stage_entry_write(input_model=input_model)

    def _stage_entry_write(
        self,
        input_model: SetupStageEntryWriteInput,
    ) -> dict[str, Any]:
        _, stage_id, block = self._current_stage_entry_context(
            workspace_id=input_model.workspace_id,
            tool_name="setup.stage_entry.write",
        )
        entry_id = self._unique_stage_entry_id(
            block=block,
            entry_type=input_model.entry_type,
            title=input_model.title,
        )
        entry = self._build_stage_entry(
            stage_id=stage_id,
            entry_id=entry_id,
            entry_type=input_model.entry_type,
            title=input_model.title,
            summary=input_model.summary,
            sections=input_model.sections,
            aliases=input_model.aliases,
            tags=input_model.tags,
        )
        updated_block = SetupStageDraftBlock(
            stage_id=stage_id,
            schema_metadata=block.schema_metadata,
            entries=[*block.entries, entry],
            notes=block.notes,
        )
        self._workspace_service.patch_stage_draft(
            workspace_id=input_model.workspace_id,
            stage_id=stage_id,
            draft=updated_block,
        )
        return {
            "success": True,
            "message": f"Created {stage_id.value} draft entry",
            "stage_id": stage_id.value,
            "updated_refs": [
                self._stage_entry_ref(stage_id=stage_id, entry_id=entry.entry_id)
            ],
            "entry": self._stage_entry_payload(
                stage_id=stage_id,
                entry=entry,
                include_sections=True,
            ),
        }
