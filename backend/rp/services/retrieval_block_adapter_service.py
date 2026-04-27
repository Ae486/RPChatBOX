"""Read-only Block-compatible adapters over retrieval search hits."""

from __future__ import annotations

from copy import deepcopy
from typing import Sequence

from rp.models.block_view import RpBlockView
from rp.models.dsl import Layer
from rp.models.memory_crud import RetrievalHit


class RetrievalBlockAdapterService:
    """Project recall/archival retrieval hits into Block-compatible envelopes."""

    def build_block_views(self, *, hits: Sequence[RetrievalHit]) -> list[RpBlockView]:
        return [self._build_block_view(hit=hit) for hit in hits]

    def _build_block_view(self, *, hit: RetrievalHit) -> RpBlockView:
        knowledge_ref = (
            hit.knowledge_ref.model_dump(mode="json")
            if hit.knowledge_ref is not None
            else None
        )
        resolved_domain_path = hit.domain_path or (
            hit.knowledge_ref.domain_path if hit.knowledge_ref is not None else None
        )
        resolved_scope = (
            hit.knowledge_ref.scope
            if hit.knowledge_ref and hit.knowledge_ref.scope
            else None
        )
        resolved_revision = (
            hit.knowledge_ref.revision
            if hit.knowledge_ref and hit.knowledge_ref.revision is not None
            else None
        )
        return RpBlockView(
            block_id=self._block_id(hit),
            label=self._label(hit),
            layer=self._layer(hit.layer),
            domain=hit.domain,
            domain_path=resolved_domain_path or "",
            scope=resolved_scope or "retrieval",
            revision=int(resolved_revision or 1),
            source="retrieval_store",
            data_json={
                "excerpt_text": hit.excerpt_text,
                "score": hit.score,
                "rank": hit.rank,
                "knowledge_ref": knowledge_ref,
                "provenance_refs": list(hit.provenance_refs),
            },
            metadata={
                **deepcopy(hit.metadata),
                "route": "retrieval_store",
                "source": "retrieval_store",
                "hit_id": hit.hit_id,
                "query_id": hit.query_id,
                "score": hit.score,
                "rank": hit.rank,
                "knowledge_ref": knowledge_ref,
                "provenance_refs": list(hit.provenance_refs),
                "raw_domain_path": hit.domain_path,
                "raw_scope": hit.knowledge_ref.scope if hit.knowledge_ref else None,
                "raw_revision": hit.knowledge_ref.revision
                if hit.knowledge_ref
                else None,
            },
        )

    @staticmethod
    def _block_id(hit: RetrievalHit) -> str:
        return f"retrieval.{hit.layer}.{hit.query_id}.{hit.hit_id}"

    @staticmethod
    def _label(hit: RetrievalHit) -> str:
        if hit.knowledge_ref is not None and hit.knowledge_ref.object_id:
            return hit.knowledge_ref.object_id
        return hit.hit_id

    @staticmethod
    def _layer(layer_value: str) -> Layer:
        if layer_value == Layer.RECALL.value:
            return Layer.RECALL
        if layer_value == Layer.ARCHIVAL.value:
            return Layer.ARCHIVAL
        raise ValueError(f"Unsupported retrieval Block layer: {layer_value}")
