"""Persist accepted story prose into retrieval recall collections."""

from __future__ import annotations

from datetime import datetime, timezone

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import (
    ACCEPTED_STORY_SEGMENT_KIND,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    build_recall_materialization_metadata,
    build_recall_seed_section,
)
from rp.models.retrieval_records import IndexJob, SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from .recall_lifecycle_service import RecallLifecycleService
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecallDetailIngestionService:
    """Persist accepted longform story segments through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)
        self._lifecycle_service = RecallLifecycleService(session)

    def ingest_accepted_story_segments(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        accepted_segments: list[StoryArtifact],
        runtime_identity: MemoryRuntimeIdentity | None = None,
        source_refs: list[MemorySourceRef] | None = None,
    ) -> list[str]:
        collection = self._collection_service.ensure_story_collection(
            story_id=story_id,
            scope="story",
            collection_kind="recall",
        )
        persisted_asset_ids: list[str] = []
        seen_asset_ids: set[str] = set()

        for artifact in accepted_segments:
            if not self._is_eligible_story_segment(artifact):
                continue
            content_text = artifact.content_text.strip()
            asset_id = self._build_asset_id(artifact_id=artifact.artifact_id)
            if asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(asset_id)

            now = _utcnow()
            existing_asset = self._document_service.get_source_asset(asset_id)
            section_path = f"recall.chapter.{chapter_index}.accepted_segment.{artifact.artifact_id}"
            section_title = f"Accepted Story Segment r{artifact.revision}"
            metadata = build_recall_materialization_metadata(
                materialization_kind=ACCEPTED_STORY_SEGMENT_KIND,
                materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
                session_id=session_id,
                chapter_index=chapter_index,
                domain_path=section_path,
                identity=runtime_identity,
                source_refs=self._build_source_refs(
                    artifact=artifact,
                    source_refs=source_refs,
                ),
                scene_ref=artifact.scene_ref,
                extra={
                    "artifact_id": artifact.artifact_id,
                    "artifact_revision": artifact.revision,
                    "artifact_kind": artifact.artifact_kind.value,
                },
            )
            if existing_asset is not None:
                metadata = self._lifecycle_service.build_recomputed_metadata(
                    existing_metadata=existing_asset.metadata,
                    replacement_metadata=metadata,
                )
            source_asset = SourceAsset(
                asset_id=asset_id,
                story_id=story_id,
                mode=StoryMode.LONGFORM,
                collection_id=collection.collection_id,
                workspace_id=source_workspace_id,
                step_id="active_story",
                commit_id=None,
                asset_kind="accepted_story_segment",
                source_ref=(
                    f"story_session:{session_id}:chapter:{chapter_index}:"
                    f"artifact:{artifact.artifact_id}"
                ),
                title=(
                    f"Chapter {chapter_index} Accepted Segment r{artifact.revision}"
                ),
                raw_excerpt=content_text[:280],
                parse_status="queued",
                ingestion_status="queued",
                mapped_targets=["recall"],
                metadata={
                    **metadata,
                    "seed_sections": [
                        build_recall_seed_section(
                            section_id=f"accepted_story_segment:{artifact.artifact_id}",
                            title=section_title,
                            path=section_path,
                            text=content_text,
                            metadata=metadata,
                            tags=[ACCEPTED_STORY_SEGMENT_KIND, "recall"],
                        )
                    ],
                },
                created_at=existing_asset.created_at
                if existing_asset is not None
                else now,
                updated_at=now,
            )
            self._document_service.upsert_source_asset(source_asset)
            if existing_asset is None:
                job = self._ingestion_service.ingest_asset(
                    story_id=story_id,
                    asset_id=asset_id,
                    collection_id=collection.collection_id,
                )
            else:
                job = self._ingestion_service.reindex_asset(
                    story_id=story_id,
                    asset_id=asset_id,
                )
            self._raise_if_job_failed(job=job, asset_id=asset_id)
            persisted_asset_ids.append(asset_id)

        return persisted_asset_ids

    @staticmethod
    def _build_asset_id(*, artifact_id: str) -> str:
        return f"recall_detail_{artifact_id}"

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(f"recall_detail_ingestion_failed:{asset_id}:{error_detail}")

    @staticmethod
    def _build_source_refs(
        *,
        artifact: StoryArtifact,
        source_refs: list[MemorySourceRef] | None,
    ) -> list[MemorySourceRef]:
        refs = list(source_refs or [])
        refs.append(
            MemorySourceRef(
                source_type="story_artifact",
                source_id=artifact.artifact_id,
                layer="runtime_workspace",
                domain="chapter",
                entry_id=artifact.artifact_id,
                revision=artifact.revision,
                metadata={
                    "artifact_kind": artifact.artifact_kind.value,
                    "scene_ref": artifact.scene_ref,
                },
            )
        )
        deduped: list[MemorySourceRef] = []
        seen: set[tuple[str, str]] = set()
        for ref in refs:
            key = (ref.source_type.casefold(), ref.source_id.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ref)
        return deduped

    @staticmethod
    def _is_eligible_story_segment(artifact: StoryArtifact) -> bool:
        return (
            artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and artifact.status == StoryArtifactStatus.ACCEPTED
            and bool(artifact.content_text.strip())
        )
