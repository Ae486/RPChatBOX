"""Revision overlay contracts for longform draft materialization and review sidecars."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


DraftDocumentBlockKind = Literal[
    "paragraph",
    "heading",
    "list_item",
    "blockquote",
    "code",
    "unknown",
]
DraftDocumentSourceFormat = Literal["markdown", "plain_text"]
ReviewOverlayMode = Literal["viewing", "editing", "suggesting"]
ReviewOverlayStatus = Literal["active", "resolved", "stale", "archived"]
RevisionAnchorScope = Literal["inline", "single_block", "multi_block"]
RevisionCommentStatus = Literal["active", "resolved", "deleted"]
RevisionTrackedChangeKind = Literal["insert", "delete", "replace"]
RevisionTrackedChangeStatus = Literal["active", "accepted", "rejected", "deleted"]
RevisionRecordActor = Literal["user", "system"]
RewriteCandidateStatus = Literal["active", "discarded"]
LongformDraftSelectionSource = Literal["user_explicit_select"]
LongformDraftAdoptionSource = Literal["accept_and_continue"]


class DraftDocumentBlock(BaseModel):
    """Stable draft block used as the revision anchor substrate."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    order: int = Field(ge=0)
    block_kind: DraftDocumentBlockKind
    text: str
    markdown_source_range: dict[str, int] | None = None
    source_range: dict[str, int] | None = None
    selected_excerpt: str | None = None
    selected_excerpt_hash: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("block_id", "text")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("selected_excerpt", "selected_excerpt_hash")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class DraftDocumentRecord(BaseModel):
    """Materialized writer draft document bound to one runtime turn."""

    model_config = ConfigDict(extra="forbid")

    draft_document_id: str
    turn_id: str
    draft_ref: str
    source_output_ref: str
    source_format: DraftDocumentSourceFormat
    blocks: list[DraftDocumentBlock] = Field(default_factory=list)
    materialization_version: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "draft_document_id",
        "turn_id",
        "draft_ref",
        "source_output_ref",
        "materialization_version",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class ReviewOverlayRecord(BaseModel):
    """Current-turn review overlay sidecar for a materialized draft document."""

    model_config = ConfigDict(extra="forbid")

    overlay_id: str
    turn_id: str
    draft_ref: str
    draft_document_id: str
    mode: ReviewOverlayMode
    comment_refs: list[str] = Field(default_factory=list)
    tracked_change_refs: list[str] = Field(default_factory=list)
    selection_refs: list[str] = Field(default_factory=list)
    overlay_status: ReviewOverlayStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("overlay_id", "turn_id", "draft_ref", "draft_document_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("comment_refs", "tracked_change_refs", "selection_refs")
    @classmethod
    def _normalize_ref_list(
        cls,
        value: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        return [
            _require_non_blank(item, field_name=info.field_name or "ref")
            for item in value
        ]


class RevisionAnchorRef(BaseModel):
    """Block/range anchor owned by RP runtime with optional SuperDoc metadata."""

    model_config = ConfigDict(extra="forbid")

    anchor_scope: RevisionAnchorScope
    block_ids: list[str] = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    selected_excerpt_hash: str | None = None
    superdoc_anchor_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("block_ids")
    @classmethod
    def _require_block_ids(cls, value: list[str]) -> list[str]:
        return [_require_non_blank(item, field_name="block_ids") for item in value]

    @field_validator("selected_excerpt_hash", "superdoc_anchor_id")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _validate_anchor_shape(self) -> "RevisionAnchorRef":
        if self.anchor_scope in {"inline", "single_block"} and len(self.block_ids) != 1:
            raise ValueError(f"{self.anchor_scope} anchor requires exactly one block_id")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class RevisionCommentRecord(BaseModel):
    """User/system comment anchored to a draft document block range."""

    model_config = ConfigDict(extra="forbid")

    comment_id: str
    turn_id: str
    draft_ref: str
    overlay_id: str
    anchor_ref: RevisionAnchorRef
    selected_excerpt: str | None = None
    instruction_text: str
    status: RevisionCommentStatus = "active"
    created_by: RevisionRecordActor = "user"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("comment_id", "turn_id", "draft_ref", "overlay_id", "instruction_text")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("selected_excerpt")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="selected_excerpt")


class TrackedChangeRecord(BaseModel):
    """Tracked change suggestion anchored to draft document blocks."""

    model_config = ConfigDict(extra="forbid")

    tracked_change_id: str
    turn_id: str
    draft_ref: str
    overlay_id: str
    anchor_ref: RevisionAnchorRef
    change_kind: RevisionTrackedChangeKind
    original_text: str | None = None
    suggested_text: str | None = None
    status: RevisionTrackedChangeStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tracked_change_id", "turn_id", "draft_ref", "overlay_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("original_text", "suggested_text")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")


class ReplacementBlock(BaseModel):
    """Patch-shaped paragraph rewrite block placeholder for later composer slices."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    replacement_text: str
    order: int = Field(ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("block_id", "replacement_text")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class RewriteRequest(BaseModel):
    """Canonical rewrite request issued by the rewrite request builder."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: str
    turn_id: str
    draft_ref: str
    draft_document_id: str
    rewrite_scope: Literal["full", "paragraph"]
    global_instruction: str | None = None
    target_block_ids: list[str] = Field(default_factory=list)
    target_range_ref: dict[str, int] | None = None
    comment_refs: list[str] = Field(default_factory=list)
    tracked_change_refs: list[str] = Field(default_factory=list)
    include_full_draft_text: bool = False
    full_draft_text: str | None = None
    anchor_refs: list[RevisionAnchorRef] = Field(default_factory=list)
    comments: list[RevisionCommentRecord] = Field(default_factory=list)
    tracked_changes: list[TrackedChangeRecord] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "request_id",
        "session_id",
        "turn_id",
        "draft_ref",
        "draft_document_id",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("global_instruction", "full_draft_text")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("comment_refs", "tracked_change_refs", "target_block_ids")
    @classmethod
    def _normalize_ref_list(
        cls,
        value: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        return [
            _require_non_blank(item, field_name=info.field_name or "ref")
            for item in value
        ]

    @field_validator("anchor_refs", "comments", "tracked_changes")
    @classmethod
    def _normalize_nested_records(cls, value: list[Any]) -> list[Any]:
        return list(value)

    @model_validator(mode="after")
    def _validate_rewrite_contract(self) -> "RewriteRequest":
        if self.rewrite_scope == "full":
            if self.target_block_ids:
                raise ValueError("full rewrite does not accept target_block_ids")
            if self.global_instruction is not None and self.include_full_draft_text:
                raise ValueError("full rewrite with global_instruction must omit full draft text")
            if self.global_instruction is not None and self.full_draft_text is not None:
                raise ValueError("full rewrite with global_instruction must omit full_draft_text")
        if self.rewrite_scope == "paragraph":
            if not self.target_block_ids:
                raise ValueError("paragraph rewrite requires target_block_ids")
            if self.full_draft_text is None:
                raise ValueError("paragraph rewrite requires full_draft_text")
        return self


class ParagraphRewritePatch(BaseModel):
    """Placeholder paragraph patch contract for the later composer slice."""

    model_config = ConfigDict(extra="forbid")

    draft_ref: str
    target_block_ids: list[str]
    replacement_blocks: list[ReplacementBlock] = Field(default_factory=list)
    touched_comment_ids: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("draft_ref")
    @classmethod
    def _require_draft_ref(cls, value: str) -> str:
        return _require_non_blank(value, field_name="draft_ref")

    @field_validator("target_block_ids", "touched_comment_ids")
    @classmethod
    def _normalize_ref_list(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _require_non_blank(item, field_name=info.field_name or "ref")
            for item in value
        ]


class RewriteCandidateRecord(BaseModel):
    """Runtime-owned rewrite candidate kept outside canonical story truth."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    candidate_output_ref: str
    session_id: str
    turn_id: str
    draft_ref: str
    draft_document_id: str
    rewrite_request_id: str
    rewrite_scope: Literal["full", "paragraph"]
    status: RewriteCandidateStatus = "active"
    full_output_text: str | None = None
    candidate_draft_text: str | None = None
    paragraph_patch: ParagraphRewritePatch | None = None
    target_block_ids: list[str] = Field(default_factory=list)
    touched_comment_ids: list[str] = Field(default_factory=list)
    touched_tracked_change_ids: list[str] = Field(default_factory=list)
    source_ref_ids: list[str] = Field(default_factory=list)
    selected_output_ref: str | None = None
    adopted_output_ref: str | None = None
    canonical_truth: bool = False
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "candidate_id",
        "candidate_output_ref",
        "session_id",
        "turn_id",
        "draft_ref",
        "draft_document_id",
        "rewrite_request_id",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "full_output_text",
        "candidate_draft_text",
        "selected_output_ref",
        "adopted_output_ref",
    )
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "target_block_ids",
        "touched_comment_ids",
        "touched_tracked_change_ids",
        "source_ref_ids",
    )
    @classmethod
    def _normalize_ref_list(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _require_non_blank(item, field_name=info.field_name or "ref")
            for item in value
        ]

    @model_validator(mode="after")
    def _validate_candidate_contract(self) -> "RewriteCandidateRecord":
        if self.selected_output_ref is not None:
            raise ValueError("rewrite candidate must not set selected_output_ref")
        if self.adopted_output_ref is not None:
            raise ValueError("rewrite candidate must not set adopted_output_ref")
        if self.canonical_truth:
            raise ValueError("rewrite candidate must not be canonical truth")
        if self.rewrite_scope == "full":
            if self.full_output_text is None:
                raise ValueError("full rewrite candidate requires full_output_text")
            if self.paragraph_patch is not None or self.target_block_ids:
                raise ValueError("full rewrite candidate must not carry paragraph patch")
        if self.rewrite_scope == "paragraph":
            if self.paragraph_patch is None:
                raise ValueError("paragraph rewrite candidate requires paragraph_patch")
            if not self.target_block_ids:
                raise ValueError("paragraph rewrite candidate requires target_block_ids")
            if self.candidate_draft_text is None:
                raise ValueError(
                    "paragraph rewrite candidate requires candidate_draft_text"
                )
        return self


class LongformDraftSelectionReceipt(BaseModel):
    """Reversible longform candidate selection state for one review turn."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    turn_id: str
    draft_ref: str
    candidate_output_refs: list[str] = Field(default_factory=list)
    selected_output_ref: str
    selection_source: LongformDraftSelectionSource = "user_explicit_select"
    selected_at: datetime
    cleared_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("receipt_id", "turn_id", "draft_ref", "selected_output_ref")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("candidate_output_refs")
    @classmethod
    def _normalize_candidate_refs(cls, value: list[str]) -> list[str]:
        return [
            _require_non_blank(item, field_name="candidate_output_refs")
            for item in value
        ]

    @model_validator(mode="after")
    def _validate_selection_contract(self) -> "LongformDraftSelectionReceipt":
        if not self.candidate_output_refs:
            raise ValueError("selection receipt requires candidate_output_refs")
        if self.selected_output_ref not in self.candidate_output_refs:
            raise ValueError("selected_output_ref must be one of candidate_output_refs")
        if self.cleared_at is not None and self.cleared_at < self.selected_at:
            raise ValueError("cleared_at must be greater than or equal to selected_at")
        return self


class LongformDraftAdoptionReceipt(BaseModel):
    """Committed accept-and-continue receipt for a longform rewrite candidate."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    turn_id: str
    draft_ref: str
    candidate_output_refs: list[str] = Field(default_factory=list)
    adopted_output_ref: str
    adoption_source: LongformDraftAdoptionSource = "accept_and_continue"
    adopted_at: datetime
    selection_receipt_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "receipt_id",
        "turn_id",
        "draft_ref",
        "adopted_output_ref",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("selection_receipt_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="selection_receipt_id")

    @field_validator("candidate_output_refs")
    @classmethod
    def _normalize_candidate_refs(cls, value: list[str]) -> list[str]:
        return [
            _require_non_blank(item, field_name="candidate_output_refs")
            for item in value
        ]

    @model_validator(mode="after")
    def _validate_adoption_contract(self) -> "LongformDraftAdoptionReceipt":
        if not self.candidate_output_refs:
            raise ValueError("adoption receipt requires candidate_output_refs")
        if self.adopted_output_ref not in self.candidate_output_refs:
            raise ValueError("adopted_output_ref must be one of candidate_output_refs")
        return self


class ReviewOverlayInspectionRecord(BaseModel):
    """Read-only inspect/debug projection for one review overlay."""

    model_config = ConfigDict(extra="forbid")

    overlay: ReviewOverlayRecord
    comments: list[RevisionCommentRecord] = Field(default_factory=list)
    tracked_changes: list[TrackedChangeRecord] = Field(default_factory=list)
    active_comment_refs: list[str] = Field(default_factory=list)
    active_tracked_change_refs: list[str] = Field(default_factory=list)
    material_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized
