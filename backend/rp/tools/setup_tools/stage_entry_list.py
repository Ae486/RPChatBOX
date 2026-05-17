"""Handler for setup.stage_entry.list."""

from __future__ import annotations

from typing import Any

from rp.tools.setup_tool_contracts import SetupStageEntryListInput

from .stage_entry_common import StageEntryToolBase


class StageEntryListTool(StageEntryToolBase):
    def _dispatch_stage_entry_list(self, input_model: Any) -> Any:
        return self._stage_entry_list(input_model=input_model)

    def _stage_entry_list(
        self,
        input_model: SetupStageEntryListInput,
    ) -> dict[str, Any]:
        _, stage_id, block = self._current_stage_entry_context(
            workspace_id=input_model.workspace_id,
            tool_name="setup.stage_entry.list",
        )
        query = (input_model.query or "").strip().lower()
        entry_type = (
            self._normalize_key(input_model.entry_type)
            if input_model.entry_type
            else None
        )
        items: list[dict[str, Any]] = []
        for entry in block.entries:
            if entry_type is not None and entry.entry_type != entry_type:
                continue
            if query and not self._entry_matches_query(entry, query):
                continue
            items.append(
                self._stage_entry_payload(
                    stage_id=stage_id,
                    entry=entry,
                    include_sections=input_model.include_sections,
                )
            )
            if len(items) >= input_model.limit:
                break
        return {
            "stage_id": stage_id.value,
            "entries": items,
        }
