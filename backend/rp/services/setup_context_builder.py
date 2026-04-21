"""Setup context packet assembly for the SetupAgent MVP."""
from __future__ import annotations

from rp.models.setup_handoff import SetupContextBuilderInput, SetupContextPacket
from rp.models.setup_workspace import SetupStepId
from rp.services.setup_workspace_service import SetupWorkspaceService


class SetupContextBuilder:
    """Build a stable setup context packet from SetupWorkspace state."""

    def __init__(self, workspace_service: SetupWorkspaceService):
        self._workspace_service = workspace_service

    def build(self, input_model: SetupContextBuilderInput) -> SetupContextPacket:
        workspace = self._workspace_service.get_workspace(input_model.workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {input_model.workspace_id}")
        current_step = SetupStepId(input_model.current_step)
        committed_summaries = self._collect_committed_summaries(workspace)
        current_draft_snapshot = self._current_draft_snapshot(workspace, current_step)
        step_asset_preview = [
            {
                "asset_id": asset.asset_id,
                "asset_kind": asset.asset_kind,
                "title": asset.title,
                "parse_status": asset.parse_status.value,
                "mapped_targets": list(asset.mapped_targets),
            }
            for asset in workspace.imported_assets
            if asset.step_id == current_step
        ]
        delta_ids = set(input_model.user_edit_delta_ids)
        user_edit_deltas = [
            {
                "delta_id": delta.delta_id,
                "target_block": delta.target_block,
                "target_ref": delta.target_ref,
                "changes": [item.model_dump(mode="json", exclude_none=True) for item in delta.changes],
            }
            for delta in workspace.pending_user_edit_deltas
            if (not delta_ids and delta.step_id == current_step and delta.consumed_at is None)
            or delta.delta_id in delta_ids
        ]
        spotlights = []
        for commit in workspace.accepted_commits:
            spotlights.extend(commit.spotlights)
        return SetupContextPacket(
            workspace_id=workspace.workspace_id,
            current_step=current_step.value,
            committed_summaries=committed_summaries,
            current_draft_snapshot=current_draft_snapshot,
            step_asset_preview=step_asset_preview,
            user_prompt=input_model.user_prompt,
            user_edit_deltas=user_edit_deltas,
            spotlights=spotlights[:10],
        )

    @staticmethod
    def _collect_committed_summaries(workspace) -> list[str]:
        summaries: list[str] = []
        for commit in workspace.accepted_commits:
            if commit.summary_tier_1:
                summaries.append(commit.summary_tier_1)
            elif commit.summary_tier_0:
                summaries.append(commit.summary_tier_0)
        return summaries[-10:]

    @staticmethod
    def _current_draft_snapshot(workspace, current_step: SetupStepId) -> dict:
        if current_step == SetupStepId.STORY_CONFIG and workspace.story_config_draft is not None:
            return workspace.story_config_draft.model_dump(mode="json", exclude_none=True)
        if (
            current_step == SetupStepId.WRITING_CONTRACT
            and workspace.writing_contract_draft is not None
        ):
            return workspace.writing_contract_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        if current_step == SetupStepId.FOUNDATION and workspace.foundation_draft is not None:
            return workspace.foundation_draft.model_dump(mode="json", exclude_none=True)
        if (
            current_step == SetupStepId.LONGFORM_BLUEPRINT
            and workspace.longform_blueprint_draft is not None
        ):
            return workspace.longform_blueprint_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        return {}

