"""Typed retrieval-runtime contracts shared by Runtime Workspace retrieval flow."""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_blank(value, field_name=field_name)


def _normalize_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_non_blank(value, field_name=field_name)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


class RetrievalKnowledgeGapItem(BaseModel):
    """Structured knowledge-gap contract kept on retrieval usage records."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    gap_id: str | None = None
    query_text: str = Field(alias="query")
    gap_kind: str = Field(alias="status")
    mode_policy_resolution: str | None = None
    notes: str | None = Field(default=None, alias="impact")

    @field_validator("gap_id", "mode_policy_resolution", "notes")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        return _normalize_optional_text(
            value,
            field_name=info.field_name or "value",
        )

    @field_validator("query_text", "gap_kind")
    @classmethod
    def _normalize_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class WriterRetrievalSearchToolInput(BaseModel):
    """Thin writer-facing search tool contract for bounded retrieval."""

    model_config = ConfigDict(extra="forbid")

    query: str
    search_kind: str = "recall"

    @field_validator("query", "search_kind")
    @classmethod
    def _normalize_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class WriterRetrievalExpandToolInput(BaseModel):
    """Writer-facing expand tool contract using short ids only."""

    model_config = ConfigDict(extra="forbid")

    card_short_ids: list[str] = Field(default_factory=list)

    @field_validator("card_short_ids")
    @classmethod
    def _normalize_card_short_ids(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized = _normalize_text_list(values, field_name="card_short_ids")
        if not normalized:
            raise ValueError("card_short_ids must not be empty")
        return normalized


class WriterRetrievalUsageToolInput(BaseModel):
    """Writer-facing usage tool contract using only short ids."""

    model_config = ConfigDict(extra="forbid")

    used_card_short_ids: list[str] = Field(default_factory=list)
    used_expanded_short_ids: list[str] = Field(default_factory=list)
    missed_query_short_ids: list[str] = Field(default_factory=list)
    knowledge_gaps: list[RetrievalKnowledgeGapItem] = Field(default_factory=list)

    @field_validator(
        "used_card_short_ids",
        "used_expanded_short_ids",
        "missed_query_short_ids",
    )
    @classmethod
    def _normalize_short_id_lists(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        return _normalize_text_list(values, field_name=info.field_name or "values")


class RetrievalUsageRecordPayload(BaseModel):
    """Stable payload contract for Runtime Workspace retrieval usage material."""

    model_config = ConfigDict(extra="forbid")

    used_card_short_ids: list[str] = Field(default_factory=list)
    expanded_card_short_ids: list[str] = Field(default_factory=list)
    unused_card_short_ids: list[str] = Field(default_factory=list)
    used_card_material_ids: list[str] = Field(default_factory=list)
    used_expanded_chunk_material_ids: list[str] = Field(default_factory=list)
    unused_card_material_ids: list[str] = Field(default_factory=list)
    missed_query_short_ids: list[str] = Field(default_factory=list)
    missed_query_material_ids: list[str] = Field(default_factory=list)
    knowledge_gaps: list[RetrievalKnowledgeGapItem] = Field(default_factory=list)

    @field_validator(
        "used_card_short_ids",
        "expanded_card_short_ids",
        "unused_card_short_ids",
        "used_card_material_ids",
        "used_expanded_chunk_material_ids",
        "unused_card_material_ids",
        "missed_query_short_ids",
        "missed_query_material_ids",
    )
    @classmethod
    def _normalize_text_lists(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _normalize_text_list(
            values, field_name=info.field_name or "values"
        )
