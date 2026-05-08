"""Writing runtime packet models for active-story packet assembly."""

from __future__ import annotations

from typing import Any, Literal

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


class PacketSection(BaseModel):
    """Structured packet section that can still be flattened for legacy consumers."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    label: str
    source_kind: str
    source_ref_ids: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("section_id", "label", "source_kind")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name or 'value'} must be non-empty")
        return normalized

    @field_validator("source_ref_ids")
    @classmethod
    def _normalize_source_ref_ids(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_values.append(normalized)
        return normalized_values

    @field_validator("items")
    @classmethod
    def _normalize_items(cls, values: list[str]) -> list[str]:
        return [normalized for value in values if (normalized := value.strip())]

    def to_legacy_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section_id": self.section_id,
            "label": self.label,
            "source_kind": self.source_kind,
            "source_ref_ids": list(self.source_ref_ids),
            "items": list(self.items),
        }
        if self.metadata_json:
            payload["metadata_json"] = dict(self.metadata_json)
        return payload


class WritingPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    identity: MemoryRuntimeIdentity | None = None
    session_id: str
    branch_head_id: str | None = None
    turn_id: str | None = None
    chapter_workspace_id: str
    output_kind: Literal["chapter_outline", "discussion_message", "story_segment"]
    phase: str
    operation_mode: Literal["writing", "rewrite", "discussion"] = "writing"
    system_sections: list[str] = Field(default_factory=list)
    writer_contract: dict[str, Any] = Field(default_factory=dict)
    core_view_sections: list[PacketSection] = Field(default_factory=list)
    recent_raw_turn_sections: list[PacketSection] = Field(default_factory=list)
    mode_sidecar_sections: list[PacketSection] = Field(default_factory=list)
    retrieval_card_sections: list[PacketSection] = Field(default_factory=list)
    review_overlay_sections: list[PacketSection] = Field(default_factory=list)
    context_sections: list[dict[str, Any]] = Field(default_factory=list)
    user_instruction: str
    packet_summary_metadata: dict[str, Any] = Field(default_factory=dict)
    trace_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def ordered_sections(self) -> list[PacketSection]:
        return [
            *self.core_view_sections,
            *self.recent_raw_turn_sections,
            *self.mode_sidecar_sections,
            *self.retrieval_card_sections,
            *self.review_overlay_sections,
        ]

    def flattened_context_sections(self) -> list[dict[str, Any]]:
        return [section.to_legacy_dict() for section in self.ordered_sections()]

    @model_validator(mode="after")
    def _backfill_legacy_context_sections(self) -> WritingPacket:
        if not self.context_sections:
            self.context_sections = self.flattened_context_sections()
        if self.identity is not None:
            if self.branch_head_id is None:
                self.branch_head_id = self.identity.branch_head_id
            if self.turn_id is None:
                self.turn_id = self.identity.turn_id
        return self
