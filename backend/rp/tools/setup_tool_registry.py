"""Registered provider-visible setup tool metadata."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from models.mcp_config import McpToolInfo
from rp.setup_agent_memory.contracts import (
    SetupSessionMemoryOpenInput,
    SetupSessionMemoryReadInput,
    SetupSessionMemorySearchInput,
)

from .setup_tool_contracts import (
    SetupRegisterAssetInput,
    SetupStageEntryDeleteInput,
    SetupStageEntryEditInput,
    SetupStageEntryListInput,
    SetupStageEntryReadInput,
    SetupStageEntryWriteInput,
)


@dataclass(frozen=True)
class SetupToolRegistration:
    name: str
    description: str
    input_model: type[BaseModel]


SETUP_TOOL_REGISTRY: tuple[SetupToolRegistration, ...] = (
    SetupToolRegistration(
        name="setup.asset.register",
        description="Register a setup-scoped asset reference. Use when the user provides a relevant reference document or asset. Do not use for Memory OS mutation. Target object: ImportedAssetRaw. Important field: source_ref.",
        input_model=SetupRegisterAssetInput,
    ),
    SetupToolRegistration(
        name="setup.memory.search",
        description="Search SetupAgent session-scoped setup fact index for small candidate refs from editable draft and accepted setup truth. Returns navigation refs and navigation_summary only; this is not fact content. Use setup.memory.open on a chosen ref before relying on exact details. Read-only; not RP Memory OS and not long-term user memory.",
        input_model=SetupSessionMemorySearchInput,
    ),
    SetupToolRegistration(
        name="setup.memory.open",
        description="Open one setup memory ref. Opening a level-3 entry ref returns its level-4 section directory, not content. Opening a level-4 section ref returns clean structured fact content. Read-only; setup fact sources are editable draft and accepted setup truth.",
        input_model=SetupSessionMemoryOpenInput,
    ),
    SetupToolRegistration(
        name="setup.memory.read_refs",
        description="Compatibility/internal readback for bounded payloads from current DB-backed setup sources. Agent-facing guidance should prefer setup.memory.search plus setup.memory.open.",
        input_model=SetupSessionMemoryReadInput,
    ),
    SetupToolRegistration(
        name="setup.stage_entry.list",
        description="List editable entries from the current canonical setup stage draft block. The backend resolves the current stage from the workspace; the model must not pass stage_id. Use for world_background, character_design, and plot_blueprint draft review before read/edit/delete.",
        input_model=SetupStageEntryListInput,
    ),
    SetupToolRegistration(
        name="setup.stage_entry.read",
        description="Read one editable entry from the current canonical setup stage draft block by stage:<stage_id>:<entry_id> ref. The backend verifies the ref stage matches the workspace current stage; the model must not pass stage_id.",
        input_model=SetupStageEntryReadInput,
    ),
    SetupToolRegistration(
        name="setup.stage_entry.write",
        description="Create one editable entry in the current canonical setup stage draft block. The model provides only content fields such as entry_type, title, summary, and text sections; the backend owns current_stage, entry_id, section_id, semantic_path, and internal section shape.",
        input_model=SetupStageEntryWriteInput,
    ),
    SetupToolRegistration(
        name="setup.stage_entry.edit",
        description="Edit one editable entry in the current canonical setup stage draft block using a current basis_fingerprint. The backend verifies the target ref stage matches the workspace current stage; the model must not pass stage_id.",
        input_model=SetupStageEntryEditInput,
    ),
    SetupToolRegistration(
        name="setup.stage_entry.delete",
        description="Delete one editable entry from the current canonical setup stage draft block using a current basis_fingerprint. The backend verifies the target ref stage matches the workspace current stage; the model must not pass stage_id.",
        input_model=SetupStageEntryDeleteInput,
    ),
)


def build_setup_tool_schema_map() -> dict[str, type[BaseModel]]:
    return {entry.name: entry.input_model for entry in SETUP_TOOL_REGISTRY}


def build_setup_tool_infos(
    *,
    provider_id: str,
    server_name: str,
) -> list[McpToolInfo]:
    return [
        McpToolInfo(
            server_id=provider_id,
            server_name=server_name,
            name=entry.name,
            description=entry.description,
            input_schema=entry.input_model.model_json_schema(),
        )
        for entry in SETUP_TOOL_REGISTRY
    ]
