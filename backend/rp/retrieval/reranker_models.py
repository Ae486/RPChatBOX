"""Internal models for retrieval rerank candidates and backend results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rp.models.memory_crud import RetrievalHit


class RerankCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: str
    query_id: str
    base_score: float
    original_rank: int
    title: str | None = None
    domain: str | None = None
    domain_path: str | None = None
    page_ref: str | None = None
    document_title: str | None = None
    document_summary: str | None = None
    image_caption: str | None = None
    source_ref: str | None = None
    context_header: str | None = None
    excerpt_text: str
    contextual_text: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_hit(cls, hit: RetrievalHit) -> "RerankCandidate":
        metadata = dict(hit.metadata)
        contextual_text = metadata.get("contextual_text")
        return cls(
            hit_id=hit.hit_id,
            query_id=hit.query_id,
            base_score=float(hit.score),
            original_rank=int(hit.rank),
            title=str(metadata.get("title") or "") or None,
            domain=str(metadata.get("domain") or hit.domain.value) or None,
            domain_path=str(metadata.get("domain_path") or hit.domain_path or "") or None,
            page_ref=str(metadata.get("page_ref") or "") or None,
            document_title=str(metadata.get("document_title") or metadata.get("title") or "") or None,
            document_summary=str(metadata.get("document_summary") or "") or None,
            image_caption=str(metadata.get("image_caption") or "") or None,
            source_ref=str(metadata.get("source_ref") or "") or None,
            context_header=str(metadata.get("context_header") or "") or None,
            excerpt_text=hit.excerpt_text,
            contextual_text=str(contextual_text).strip() if isinstance(contextual_text, str) and contextual_text.strip() else None,
            metadata=metadata,
        )


class RerankBackendItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: str
    relevance_score: float
    rank: int


class RerankBackendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend_name: str
    model_id: str | None = None
    model_name: str | None = None
    provider_id: str | None = None
    resolution_source: str | None = None
    rerank_ms: float = 0.0
    expected_count: int = 0
    items: list[RerankBackendItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def has_usable_items(self) -> bool:
        if not self.items:
            return False
        if self.expected_count <= 0:
            return True
        return len(self.items) >= self.expected_count
