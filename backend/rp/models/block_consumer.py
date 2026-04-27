"""Active-story block consumer visibility models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.block_view import BlockSource
from rp.models.dsl import Domain, Layer


BlockConsumerKey = Literal[
    "story.orchestrator",
    "story.specialist",
    "story.writer_packet",
]

DEFAULT_BLOCK_CONSUMERS: tuple[BlockConsumerKey, ...] = (
    "story.orchestrator",
    "story.specialist",
    "story.writer_packet",
)


class RpBlockConsumerAttachmentView(BaseModel):
    """Lightweight Block identity snapshot for one consumer attachment."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    label: str
    layer: Layer
    domain: Domain
    domain_path: str
    scope: str
    revision: int
    source: BlockSource


class RpBlockConsumerStateView(BaseModel):
    """Read-only current visibility of one active-story Block consumer."""

    model_config = ConfigDict(extra="forbid")

    consumer_key: BlockConsumerKey
    session_id: str
    chapter_workspace_id: str | None = None
    dirty: bool = True
    dirty_reasons: list[str] = Field(default_factory=list)
    dirty_block_ids: list[str] = Field(default_factory=list)
    attached_blocks: list[RpBlockConsumerAttachmentView] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
