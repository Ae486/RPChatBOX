"""Handler for setup.asset.register."""

from __future__ import annotations

from typing import Any

from rp.models.setup_handoff import SetupToolResult

from .base import SetupToolFamilyBase


class AssetRegisterTool(SetupToolFamilyBase):
    def _dispatch_asset_register(self, input_model: Any) -> SetupToolResult:
        asset = self._workspace_service.register_asset(
            workspace_id=input_model.workspace_id,
            step_id=input_model.step_id,
            asset_kind=input_model.asset_kind,
            source_ref=input_model.source_ref,
            title=input_model.title,
        )
        return SetupToolResult(
            success=True,
            message="Registered setup asset",
            updated_refs=[f"asset:{asset.asset_id}"],
        )
