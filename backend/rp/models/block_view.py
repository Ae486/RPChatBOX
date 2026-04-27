"""Read-only Block envelope views over current RP memory stores."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.dsl import Domain, Layer


BlockSource = Literal[
    "core_state_store",
    "compatibility_mirror",
    "retrieval_store",
    "runtime_workspace_store",
]


class RpBlockView(BaseModel):
    """Stable read envelope for Core State objects and projection slots.

    This is intentionally a read model, not a new persistence model. It keeps
    exact Core State identity and raw payloads visible while callers migrate
    toward Block-shaped inspection without bypassing proposal/apply or writer
    packet boundaries.
    """

    model_config = ConfigDict(extra="forbid")

    block_id: str
    label: str
    layer: Layer
    domain: Domain
    domain_path: str
    scope: str
    revision: int = 1
    source: BlockSource
    payload_schema_ref: str | None = None
    data_json: Any = None
    items_json: list[Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
