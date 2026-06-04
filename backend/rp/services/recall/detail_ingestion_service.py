"""Persist accepted story prose into retrieval recall collections."""

from __future__ import annotations

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import (
    ACCEPTED_STORY_SEGMENT_KIND,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    build_recall_materialization_metadata,
)
from rp.models.story_runtime import (
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from ._ingestion_pipeline import (
    RecallSeedAssetSpec,
    dedupe_memory_source_refs,
    ensure_recall_collection,
    persist_recall_seed_asset,
)
from .lifecycle_service import RecallLifecycleService
from ..retrieval.collection_service import RetrievalCollectionService
from ..retrieval.document_service import RetrievalDocumentService
from ..retrieval.ingestion_service import RetrievalIngestionService


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
        collection = ensure_recall_collection(
            self._collection_service,
            story_id=story_id,
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
            persist_recall_seed_asset(
                document_service=self._document_service,
                ingestion_service=self._ingestion_service,
                lifecycle_service=self._lifecycle_service,
                spec=RecallSeedAssetSpec(
                    asset_id=asset_id,
                    story_id=story_id,
                    collection_id=collection.collection_id,
                    source_workspace_id=source_workspace_id,
                    asset_kind="accepted_story_segment",
                    source_ref=(
                        f"story_session:{session_id}:chapter:{chapter_index}:"
                        f"artifact:{artifact.artifact_id}"
                    ),
                    title=(
                        f"Chapter {chapter_index} Accepted Segment r{artifact.revision}"
                    ),
                    raw_text=content_text,
                    metadata=metadata,
                    section_id=f"accepted_story_segment:{artifact.artifact_id}",
                    section_title=section_title,
                    section_path=section_path,
                    section_text=content_text,
                    section_tags=[ACCEPTED_STORY_SEGMENT_KIND, "recall"],
                    error_prefix="recall_detail_ingestion_failed",
                ),
            )
            persisted_asset_ids.append(asset_id)

        return persisted_asset_ids

    @staticmethod
    def _build_asset_id(*, artifact_id: str) -> str:
        return f"recall_detail_{artifact_id}"

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
        return dedupe_memory_source_refs(refs)

    @staticmethod
    def _is_eligible_story_segment(artifact: StoryArtifact) -> bool:
        return (
            artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and artifact.status == StoryArtifactStatus.ACCEPTED
            and bool(artifact.content_text.strip())
        )
