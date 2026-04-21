"""Shared helpers for retrieval search components."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from models.rp_retrieval_store import KnowledgeChunkRecord, KnowledgeCollectionRecord, SourceAssetRecord
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import RetrievalHit, RetrievalQuery


def coerce_domain(value: str | None) -> Domain:
    if value is None:
        return Domain.WORLD_RULE
    normalized = value.strip().lower()
    aliases = {
        "world": Domain.WORLD_RULE,
        "rule": Domain.WORLD_RULE,
        "chapter_plan": Domain.CHAPTER,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return Domain(normalized)
    except ValueError:
        return Domain.WORLD_RULE


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_list = [float(item) for item in left]
    right_list = [float(item) for item in right]
    if not left_list or not right_list or len(left_list) != len(right_list):
        return 0.0
    numerator = sum(a * b for a, b in zip(left_list, right_list, strict=False))
    left_norm = math.sqrt(sum(item * item for item in left_list))
    right_norm = math.sqrt(sum(item * item for item in right_list))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def query_vector_literal(vector: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(item):.12f}".rstrip("0").rstrip(".") for item in vector) + "]"


def build_filters_applied(query: RetrievalQuery) -> dict[str, Any]:
    return {
        "story_id": query.story_id,
        "domains": [domain.value for domain in query.domains],
        "scope": query.scope,
        "filters": query.filters,
    }


def row_matches_common_filters(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    collection: KnowledgeCollectionRecord | None,
    query: RetrievalQuery,
) -> bool:
    if query.story_id not in {"", "*"} and chunk.story_id != query.story_id:
        return False

    if query.domains and chunk.domain not in {domain.value for domain in query.domains}:
        return False

    collection_ids = list(query.filters.get("knowledge_collections") or [])
    if collection_ids and chunk.collection_id not in collection_ids:
        return False

    domain_path_prefix = query.filters.get("domain_path_prefix")
    if isinstance(domain_path_prefix, str) and domain_path_prefix:
        if not (chunk.domain_path or "").startswith(domain_path_prefix):
            return False

    mapped_targets = list(query.filters.get("mapped_targets") or [])
    if mapped_targets and not set(mapped_targets).intersection(set(asset.mapped_targets_json or [])):
        return False

    if query.query_kind == "archival" and not collection_ids:
        if collection is None or collection.collection_kind != "archival":
            return False
    if query.query_kind == "recall":
        if collection is None or collection.collection_kind != "recall":
            return False

    return bool(chunk.is_active)


def build_chunk_hit(
    *,
    query: RetrievalQuery,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    collection: KnowledgeCollectionRecord | None,
    score: float,
    rank: int,
) -> RetrievalHit:
    domain = coerce_domain(chunk.domain)
    return RetrievalHit(
        hit_id=f"{chunk.chunk_id}:{rank}",
        query_id=query.query_id,
        layer=Layer.RECALL.value if query.query_kind == "recall" else Layer.ARCHIVAL.value,
        domain=domain,
        domain_path=chunk.domain_path,
        knowledge_ref=ObjectRef(
            object_id=chunk.chunk_id,
            layer=Layer.RECALL if query.query_kind == "recall" else Layer.ARCHIVAL,
            domain=domain,
            domain_path=chunk.domain_path,
            scope=collection.scope if collection is not None else query.scope,
            revision=1,
        ),
        excerpt_text=chunk.text,
        score=round(float(score), 6),
        rank=rank,
        metadata={
            "asset_id": asset.asset_id,
            "asset_kind": asset.asset_kind,
            "title": chunk.title or asset.title,
            "collection_id": chunk.collection_id,
            "collection_kind": collection.collection_kind if collection is not None else None,
            "token_count": chunk.token_count,
            **dict(chunk.metadata_json or {}),
        },
        provenance_refs=list(chunk.provenance_refs_json or []),
    )
