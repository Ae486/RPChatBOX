"""Shared persist pipeline for Recall ingestion services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import build_recall_seed_section
from rp.models.retrieval_records import IndexJob, SourceAsset
from rp.models.setup_workspace import StoryMode


@dataclass(frozen=True)
class RecallSeedAssetSpec:
    story_id: str
    source_workspace_id: str
    collection_id: str
    asset_id: str
    asset_kind: str
    source_ref: str
    title: str
    raw_text: str
    metadata: dict[str, Any]
    section_id: str
    section_title: str
    section_path: str
    section_text: str
    section_tags: list[str]
    error_prefix: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_recall_collection(collection_service: Any, *, story_id: str) -> Any:
    return collection_service.ensure_story_collection(
        story_id=story_id,
        scope="story",
        collection_kind="recall",
    )


def dedupe_memory_source_refs(refs: list[MemorySourceRef]) -> list[MemorySourceRef]:
    deduped: list[MemorySourceRef] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref.source_type.casefold(), ref.source_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def branch_head_id(identity: MemoryRuntimeIdentity | None) -> str | None:
    if identity is None:
        return None
    return identity.branch_head_id


def persist_recall_seed_asset(
    *,
    document_service: Any,
    ingestion_service: Any,
    lifecycle_service: Any,
    spec: RecallSeedAssetSpec,
) -> str:
    now = _utcnow()
    existing_asset = document_service.get_source_asset(spec.asset_id)
    metadata = spec.metadata
    if existing_asset is not None:
        metadata = lifecycle_service.build_recomputed_metadata(
            existing_metadata=existing_asset.metadata,
            replacement_metadata=metadata,
        )
    asset = SourceAsset(
        asset_id=spec.asset_id,
        story_id=spec.story_id,
        mode=StoryMode.LONGFORM,
        collection_id=spec.collection_id,
        workspace_id=spec.source_workspace_id,
        step_id="active_story",
        commit_id=None,
        asset_kind=spec.asset_kind,
        source_ref=spec.source_ref,
        title=spec.title,
        raw_excerpt=spec.raw_text[:280],
        parse_status="queued",
        ingestion_status="queued",
        mapped_targets=["recall"],
        metadata={
            **metadata,
            "seed_sections": [
                build_recall_seed_section(
                    section_id=spec.section_id,
                    title=spec.section_title,
                    path=spec.section_path,
                    text=spec.section_text,
                    metadata=metadata,
                    tags=spec.section_tags,
                )
            ],
        },
        created_at=existing_asset.created_at if existing_asset is not None else now,
        updated_at=now,
    )
    document_service.upsert_source_asset(asset)
    if existing_asset is None:
        job = ingestion_service.ingest_asset(
            story_id=spec.story_id,
            asset_id=spec.asset_id,
            collection_id=spec.collection_id,
        )
    else:
        job = ingestion_service.reindex_asset(
            story_id=spec.story_id,
            asset_id=spec.asset_id,
        )
    _raise_if_job_failed(
        job=job,
        asset_id=spec.asset_id,
        error_prefix=spec.error_prefix,
    )
    return spec.asset_id


def _raise_if_job_failed(*, job: IndexJob, asset_id: str, error_prefix: str) -> None:
    if job.job_state == "completed":
        return
    error_detail = job.error_message or job.job_state
    raise RuntimeError(f"{error_prefix}:{asset_id}:{error_detail}")
