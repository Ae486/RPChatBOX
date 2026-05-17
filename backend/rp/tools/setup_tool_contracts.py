"""Input schemas and structured error contracts for setup local tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rp.models.setup_workspace import SetupStepId


class SetupRegisterAssetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    step_id: SetupStepId
    asset_kind: str
    source_ref: str
    title: str | None = None


class SetupStageEntrySectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    text: str
    retrieval_role: (
        Literal["summary", "detail", "rule", "relationship", "note"] | None
    ) = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", "text")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text


class SetupStageEntryListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str | None = None
    entry_type: str | None = None
    include_sections: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class SetupStageEntryReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    target_ref: str
    include_sections: bool = True


class SetupStageEntryWriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    entry_type: str
    title: str
    summary: str | None = None
    sections: list[SetupStageEntrySectionInput] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("entry_type", "title")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text


class SetupStageEntryChangesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_type: str | None = None
    title: str | None = None
    summary: str | None = None
    upsert_sections: list[SetupStageEntrySectionInput] = Field(default_factory=list)
    remove_section_titles: list[str] = Field(default_factory=list)
    add_aliases: list[str] = Field(default_factory=list)
    remove_aliases: list[str] = Field(default_factory=list)
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)

    @field_validator("entry_type", "title", "summary")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text


class SetupStageEntryEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    target_ref: str
    basis_fingerprint: str
    changes: SetupStageEntryChangesInput


class SetupStageEntryDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    target_ref: str
    basis_fingerprint: str
    reason: str | None = None


class SetupToolContractError(ValueError):
    """Structured setup-tool failure that runtime policies can interpret directly."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        error_code: str = "SETUP_TOOL_FAILED",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}
