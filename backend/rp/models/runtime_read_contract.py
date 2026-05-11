"""Shared runtime read contracts for branch visibility and packet manifests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


class RuntimeBranchReadScope(BaseModel):
    """Resolved runtime-visible branch lineage for one exact memory identity."""

    model_config = ConfigDict(extra="forbid")

    story_id: str
    session_id: str
    active_branch_head_id: str
    active_turn_id: str | None = None
    selected_turn_id: str | None = None
    visible_branch_head_ids: list[str] = Field(default_factory=list)
    turn_cutoff_by_branch: dict[str, str | None] = Field(default_factory=dict)
    hidden_turn_ids_by_branch: dict[str, list[str]] = Field(default_factory=dict)
    include_story_global: bool = True

    @field_validator("story_id", "session_id", "active_branch_head_id")
    @classmethod
    def _normalize_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("active_turn_id", "selected_turn_id")
    @classmethod
    def _normalize_optional_turn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name="turn_id")

    @field_validator("visible_branch_head_ids")
    @classmethod
    def _normalize_visible_branch_ids(cls, value: list[str]) -> list[str]:
        return [
            _require_non_blank(item, field_name="visible_branch_head_id")
            for item in value
        ]

    @field_validator("turn_cutoff_by_branch")
    @classmethod
    def _normalize_turn_cutoffs(
        cls,
        value: dict[str, str | None],
    ) -> dict[str, str | None]:
        normalized: dict[str, str | None] = {}
        for branch_head_id, turn_id in value.items():
            normalized_branch_id = _require_non_blank(
                branch_head_id,
                field_name="turn_cutoff_by_branch",
            )
            normalized_turn_id = (
                None
                if turn_id is None
                else _require_non_blank(turn_id, field_name="turn_cutoff_by_branch")
            )
            normalized[normalized_branch_id] = normalized_turn_id
        return normalized

    @field_validator("hidden_turn_ids_by_branch")
    @classmethod
    def _normalize_hidden_turn_ids(
        cls,
        value: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for branch_head_id, turn_ids in value.items():
            normalized_branch_id = _require_non_blank(
                branch_head_id,
                field_name="hidden_turn_ids_by_branch",
            )
            normalized[normalized_branch_id] = [
                _require_non_blank(turn_id, field_name="hidden_turn_ids_by_branch")
                for turn_id in turn_ids
            ]
        return normalized


class RuntimeReadManifest(BaseModel):
    """Deterministic packet-visible read trace for one runtime-owned packet build."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    identity: MemoryRuntimeIdentity
    active_branch_lineage: list[str] = Field(default_factory=list)
    branch_scope: dict[str, Any] = Field(default_factory=dict)
    runtime_profile_snapshot_id: str
    policy_versions: dict[str, str] = Field(default_factory=dict)
    visible_refs: list[dict[str, Any]] = Field(default_factory=list)
    selected_refs: list[dict[str, Any]] = Field(default_factory=list)
    omitted_refs: list[dict[str, Any]] = Field(default_factory=list)
    packet_sections: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_card_refs: list[str] = Field(default_factory=list)
    expanded_chunk_refs: list[str] = Field(default_factory=list)
    retrieval_miss_refs: list[str] = Field(default_factory=list)
    writer_usage_refs: list[str] = Field(default_factory=list)
    token_usage_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("manifest_id", "runtime_profile_snapshot_id")
    @classmethod
    def _normalize_manifest_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "active_branch_lineage",
        "retrieval_card_refs",
        "expanded_chunk_refs",
        "retrieval_miss_refs",
        "writer_usage_refs",
    )
    @classmethod
    def _normalize_string_lists(
        cls, value: list[str], info: ValidationInfo
    ) -> list[str]:
        field_name = info.field_name or "value"
        return [_require_non_blank(item, field_name=field_name) for item in value]
