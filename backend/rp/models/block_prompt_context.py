"""Structured Block-backed prompt context for active-story internal agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rp.models.block_consumer import BlockConsumerKey
from rp.models.block_view import RpBlockView


class RpBlockPromptContextView(BaseModel):
    """Internal compile view derived from attached Core State Block envelopes."""

    model_config = ConfigDict(extra="forbid")

    consumer_key: BlockConsumerKey
    session_id: str
    chapter_workspace_id: str | None = None
    dirty: bool = True
    dirty_reasons: list[str] = Field(default_factory=list)
    dirty_block_ids: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    authoritative_state: dict[str, Any] = Field(default_factory=dict)
    projection_state: dict[str, list[str]] = Field(default_factory=dict)
    attached_blocks: list[RpBlockView] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
