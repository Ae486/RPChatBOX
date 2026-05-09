"""Runtime config control-plane contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RuntimeConfigPatchSource = Literal[
    "runtime_config_panel",
    "migration",
    "system_default",
]


class RuntimeConfigPatchRequest(BaseModel):
    """Structured runtime config patch request.

    `runtime_story_config` is retained as a compatibility patch envelope for the
    existing API/client path. The structured fields are the L1 control surface
    and are stored on the existing StorySession runtime config before compiling
    a new immutable RuntimeProfileSnapshot.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    actor_id: str | None = None
    expected_active_snapshot_id: str | None = None
    worker_overrides: dict[str, Any] = Field(default_factory=dict)
    permission_overrides: dict[str, Any] = Field(default_factory=dict)
    retrieval_policy_patch: dict[str, Any] = Field(default_factory=dict)
    context_policy_patch: dict[str, Any] = Field(default_factory=dict)
    packet_policy_patch: dict[str, Any] = Field(default_factory=dict)
    model_profile_patch: dict[str, Any] = Field(default_factory=dict)
    scheduling_policy_patch: dict[str, Any] = Field(default_factory=dict)
    budget_latency_policy_patch: dict[str, Any] = Field(default_factory=dict)
    runtime_story_config: dict[str, Any] = Field(default_factory=dict)
    source: RuntimeConfigPatchSource = "runtime_config_panel"
    reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RuntimeConfigPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    previous_snapshot_id: str | None
    changed_fields: list[str] = Field(default_factory=list)
    next_runtime_story_config: dict[str, Any] = Field(default_factory=dict)


class RuntimeConfigControlReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    story_id: str
    session_id: str
    previous_snapshot_id: str | None
    published_snapshot_id: str
    changed_fields: list[str]
    actor_id: str | None
    source: RuntimeConfigPatchSource
    reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
