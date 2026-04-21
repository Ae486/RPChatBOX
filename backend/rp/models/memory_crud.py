"""Memory CRUD contracts for RP Phase A."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rp.models.dsl import Domain, ObjectRef


class MemoryGetStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refs: list[ObjectRef] = Field(default_factory=list)
    domain: Domain | None = None
    scope: str | None = None
    include_superseded: bool = False

    @model_validator(mode="after")
    def _require_refs_or_domain(self) -> "MemoryGetStateInput":
        if not self.refs and self.domain is None:
            raise ValueError("At least one of 'refs' or 'domain' must be provided")
        return self


class MemoryGetSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_ids: list[str] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    scope: str | None = None


class MemorySearchRecallInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    scope: str | None = None
    domains: list[Domain] = Field(default_factory=list)
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class MemorySearchArchivalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    knowledge_collections: list[str] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class MemoryListVersionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: ObjectRef
    include_audit: bool = False


class MemoryReadProvenanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: ObjectRef


class StateReadResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_ref: ObjectRef
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class StateReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StateReadResultItem] = Field(default_factory=list)
    version_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SummaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_id: str
    domain: Domain
    domain_path: str | None = None
    summary_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SummaryReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SummaryEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RetrievalQuery(BaseModel):
    """Shared retrieval query shape frozen for Phase A and reused later."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    query_kind: Literal["structured", "recall", "archival", "hybrid"]
    story_id: str
    scope: str | None = None
    domains: list[Domain] = Field(default_factory=list)
    text_query: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = 5
    rerank: bool = False
    required_refs: list[ObjectRef] = Field(default_factory=list)
    optional_refs: list[ObjectRef] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: str
    query_id: str
    layer: str
    domain: Domain
    domain_path: str | None = None
    knowledge_ref: ObjectRef | None = None
    excerpt_text: str
    score: float
    rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance_refs: list[str] = Field(default_factory=list)


class RetrievalTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    query_id: str
    route: str
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    candidate_count: int = 0
    returned_count: int = 0
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RetrievalSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[RetrievalHit] = Field(default_factory=list)
    trace: RetrievalTrace | None = None
    warnings: list[str] = Field(default_factory=list)


class UpsertRecordOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["upsert_record"] = "upsert_record"
    target_ref: ObjectRef
    record_data: dict[str, Any]


class PatchFieldsOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["patch_fields"] = "patch_fields"
    target_ref: ObjectRef
    field_patch: dict[str, Any]


class RemoveRecordOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["remove_record"] = "remove_record"
    target_ref: ObjectRef


class AppendEventOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["append_event"] = "append_event"
    target_ref: ObjectRef
    event_data: dict[str, Any]


class AddRelationOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["add_relation"] = "add_relation"
    target_ref: ObjectRef
    relation_data: dict[str, Any]


class RemoveRelationOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["remove_relation"] = "remove_relation"
    target_ref: ObjectRef


class SetStatusOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["set_status"] = "set_status"
    target_ref: ObjectRef
    status_value: str


StatePatchOperation = Annotated[
    UpsertRecordOp
    | PatchFieldsOp
    | RemoveRecordOp
    | AppendEventOp
    | AddRelationOp
    | RemoveRelationOp
    | SetStatusOp,
    Field(discriminator="kind"),
]


class ProposalSubmitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    mode: str
    domain: Domain
    domain_path: str | None = None
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef] = Field(default_factory=list)
    reason: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _ensure_operation_domains_match(self) -> "ProposalSubmitInput":
        for operation in self.operations:
            if operation.target_ref.domain != self.domain:
                raise ValueError(
                    "All operation target_ref.domain values must match the proposal domain"
                )
        return self


class ProposalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    status: Literal["pending"] = "pending"
    mode: str
    domain: Domain
    domain_path: str | None = None
    operation_kinds: list[str]
    created_at: datetime


class VersionListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versions: list[str] = Field(default_factory=list)
    current_ref: str | None = None


class ProvenanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: ObjectRef
    source_refs: list[str] = Field(default_factory=list)
    proposal_refs: list[str] = Field(default_factory=list)
    ingestion_refs: list[str] = Field(default_factory=list)


class ToolErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None
