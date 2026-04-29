"""Shared helpers for retrieval search components."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from models.rp_retrieval_store import (
    KnowledgeChunkRecord,
    KnowledgeCollectionRecord,
    SourceAssetRecord,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import RetrievalHit, RetrievalQuery

_ASSET_METADATA_FALLBACK_FIELDS = (
    "layer",
    "source_family",
    "source_type",
    "source_origin",
    "materialization_event",
    "materialization_kind",
    "materialized_to_recall",
    "materialized_to_archival",
    "authoritative_mutation",
    "workspace_id",
    "chapter_index",
    "scene_ref",
    "scene_refs",
    "character_refs",
    "pov_character_ref",
    "pov_character_refs",
    "mentioned_character_refs",
    "foreshadow_ref",
    "foreshadow_refs",
    "foreshadow_status",
    "foreshadow_statuses",
    "branch_id",
    "branch_ids",
    "canon_status",
    "canon_statuses",
    "superseded_by",
    "artifact_id",
    "artifact_revision",
)


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
    return (
        "["
        + ",".join(f"{float(item):.12f}".rstrip("0").rstrip(".") for item in vector)
        + "]"
    )


def build_filters_applied(query: RetrievalQuery) -> dict[str, Any]:
    return {
        "story_id": query.story_id,
        "domains": [domain.value for domain in query.domains],
        "scope": query.scope,
        "filters": query.filters,
        "top_k": query.top_k,
        "rerank": query.rerank,
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
    if mapped_targets and not set(mapped_targets).intersection(
        set(asset.mapped_targets_json or [])
    ):
        return False

    if query.query_kind == "archival" and not collection_ids:
        if collection is None or collection.collection_kind != "archival":
            return False
    if query.query_kind == "archival":
        if not _matches_archival_source_filters(
            chunk=chunk,
            asset=asset,
            query=query,
        ):
            return False
    if query.query_kind == "recall":
        if collection is None or collection.collection_kind != "recall":
            return False
        if not _matches_recall_source_family_filters(
            chunk=chunk,
            asset=asset,
            query=query,
        ):
            return False

    return bool(chunk.is_active)


def chunk_view_priority(metadata: dict[str, Any] | None) -> int:
    if not isinstance(metadata, dict):
        return 0
    try:
        return int(metadata.get("chunk_view_priority") or 0)
    except (TypeError, ValueError):
        return 0


def _merge_asset_metadata_fallbacks(
    *,
    metadata: dict[str, Any],
    asset: SourceAssetRecord,
) -> None:
    asset_metadata = asset.metadata_json or {}
    if not isinstance(asset_metadata, dict):
        return
    for field_name in _ASSET_METADATA_FALLBACK_FIELDS:
        if field_name in metadata:
            continue
        if field_name not in asset_metadata:
            continue
        metadata[field_name] = asset_metadata[field_name]


def _metadata_value_with_asset_fallback(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    field_name: str,
) -> Any:
    chunk_metadata = chunk.metadata_json or {}
    if isinstance(chunk_metadata, dict) and field_name in chunk_metadata:
        return chunk_metadata[field_name]
    asset_metadata = asset.metadata_json or {}
    if isinstance(asset_metadata, dict) and field_name in asset_metadata:
        return asset_metadata[field_name]
    return None


def _metadata_or_asset_column_value(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    field_name: str,
) -> Any:
    value = _metadata_value_with_asset_fallback(
        chunk=chunk,
        asset=asset,
        field_name=field_name,
    )
    if value is not None:
        return value
    if field_name == "workspace_id":
        return asset.workspace_id
    if field_name == "commit_id":
        return asset.commit_id
    return None


def _matches_any_filter_value(value: Any, allowed_values: list[object]) -> bool:
    if not allowed_values:
        return True
    if value is None:
        return False
    allowed_set = {str(item) for item in allowed_values}
    if isinstance(value, list):
        return any(str(item) in allowed_set for item in value)
    if isinstance(value, tuple | set):
        return any(str(item) in allowed_set for item in value)
    return str(value) in allowed_set


def _matches_any_metadata_field(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    field_names: tuple[str, ...],
    allowed_values: list[object],
) -> bool:
    return any(
        _matches_any_filter_value(
            _metadata_value_with_asset_fallback(
                chunk=chunk,
                asset=asset,
                field_name=field_name,
            ),
            allowed_values,
        )
        for field_name in field_names
    )


def _matches_recall_source_family_filters(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    query: RetrievalQuery,
) -> bool:
    filter_fields: dict[str, tuple[str, ...]] = {
        "materialization_kinds": ("materialization_kind",),
        "source_families": ("source_family",),
        "chapter_indices": ("chapter_index",),
        "scene_refs": ("scene_ref", "scene_refs"),
        "character_refs": (
            "character_refs",
            "mentioned_character_refs",
            "pov_character_ref",
            "pov_character_refs",
        ),
        "pov_character_refs": ("pov_character_ref", "pov_character_refs"),
        "foreshadow_refs": ("foreshadow_ref", "foreshadow_refs"),
        "foreshadow_statuses": ("foreshadow_status", "foreshadow_statuses"),
        "branch_ids": ("branch_id", "branch_ids"),
        "canon_statuses": ("canon_status", "canon_statuses"),
    }
    for filter_key, metadata_fields in filter_fields.items():
        allowed_values = list(query.filters.get(filter_key) or [])
        if not allowed_values:
            continue
        if not _matches_any_metadata_field(
            chunk=chunk,
            asset=asset,
            field_names=metadata_fields,
            allowed_values=allowed_values,
        ):
            return False
    return True


def _matches_archival_source_filters(
    *,
    chunk: KnowledgeChunkRecord,
    asset: SourceAssetRecord,
    query: RetrievalQuery,
) -> bool:
    filter_fields = {
        "source_types": "source_type",
        "source_families": "source_family",
        "source_origins": "source_origin",
        "workspace_ids": "workspace_id",
        "commit_ids": "commit_id",
    }
    for filter_key, metadata_field in filter_fields.items():
        allowed_values = list(query.filters.get(filter_key) or [])
        if not allowed_values:
            continue
        value = _metadata_or_asset_column_value(
            chunk=chunk,
            asset=asset,
            field_name=metadata_field,
        )
        if not _matches_any_filter_value(value, allowed_values):
            return False
    return True


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
    metadata = dict(chunk.metadata_json or {})
    _merge_asset_metadata_fallbacks(metadata=metadata, asset=asset)
    metadata["asset_id"] = asset.asset_id
    metadata["asset_kind"] = asset.asset_kind
    metadata["title"] = chunk.title or asset.title
    metadata["domain"] = chunk.domain
    metadata["domain_path"] = chunk.domain_path
    metadata["collection_id"] = chunk.collection_id
    metadata["collection_kind"] = (
        collection.collection_kind if collection is not None else None
    )
    metadata["token_count"] = chunk.token_count
    metadata["section_id"] = metadata.get("section_id")
    metadata["section_part"] = int(metadata.get("section_part") or 0)
    metadata["parent_section_part"] = int(
        metadata.get("parent_section_part") or metadata["section_part"]
    )
    metadata["view_part"] = int(metadata.get("view_part") or metadata["section_part"])
    metadata["chunk_view"] = str(metadata.get("chunk_view") or "primary")
    metadata["chunk_size"] = str(metadata.get("chunk_size") or "default")
    metadata["chunk_pass"] = int(metadata.get("chunk_pass") or 0)
    metadata["chunk_view_priority"] = chunk_view_priority(metadata)
    metadata["chunk_family_id"] = metadata.get("chunk_family_id") or (
        f"{metadata['section_id']}:{metadata['parent_section_part']}"
        if metadata.get("section_id") is not None
        else chunk.chunk_id
    )
    metadata["char_start"] = metadata.get("char_start")
    metadata["char_end"] = metadata.get("char_end")
    metadata["source_ref"] = metadata.get("source_ref") or asset.source_ref
    metadata["commit_id"] = metadata.get("commit_id") or asset.commit_id
    metadata["workspace_id"] = metadata.get("workspace_id") or asset.workspace_id
    return RetrievalHit(
        hit_id=chunk.chunk_id,
        query_id=query.query_id,
        layer=Layer.RECALL.value
        if query.query_kind == "recall"
        else Layer.ARCHIVAL.value,
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
        metadata=metadata,
        provenance_refs=list(chunk.provenance_refs_json or []),
    )
