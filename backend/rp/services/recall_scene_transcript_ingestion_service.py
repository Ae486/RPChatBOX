"""Persist closed-scene transcripts into retrieval recall collections."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.memory_materialization import (
    SCENE_CLOSE_EVENT,
    SCENE_TRANSCRIPT_KIND,
    build_recall_materialization_metadata,
    build_recall_seed_section,
)
from rp.models.retrieval_records import IndexJob, SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StoryDiscussionEntry,
)
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SceneTranscriptPromotionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    story_id: str
    chapter_index: int
    scene_ref: str
    source_workspace_id: str
    discussion_entries: list[StoryDiscussionEntry] = Field(default_factory=list)
    accepted_segments: list[StoryArtifact] = Field(default_factory=list)


class _TranscriptSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["discussion", "accepted_segment"]
    source_id: str
    label: str
    text: str
    created_at: datetime


class RecallSceneTranscriptIngestionService:
    """Persist closed-scene transcript material through the retrieval-core path."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def build_promotion_input(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        scene_ref: str,
        source_workspace_id: str,
        discussion_entries: list[StoryDiscussionEntry],
        artifacts: list[StoryArtifact],
    ) -> SceneTranscriptPromotionInput:
        normalized_scene_ref = scene_ref.strip()
        if not normalized_scene_ref:
            raise ValueError(
                "scene transcript promotion requires a non-empty scene_ref"
            )
        self._raise_if_missing_scene_ref(
            discussion_entries=discussion_entries,
            artifacts=artifacts,
        )
        return SceneTranscriptPromotionInput(
            session_id=session_id,
            story_id=story_id,
            chapter_index=chapter_index,
            scene_ref=normalized_scene_ref,
            source_workspace_id=source_workspace_id,
            discussion_entries=[
                entry
                for entry in discussion_entries
                if (entry.scene_ref or "").strip() == normalized_scene_ref
            ],
            accepted_segments=[
                artifact
                for artifact in artifacts
                if (artifact.scene_ref or "").strip() == normalized_scene_ref
            ],
        )

    def ingest_scene_transcript(
        self,
        input_model: SceneTranscriptPromotionInput,
    ) -> str | None:
        normalized_scene_ref = input_model.scene_ref.strip()
        if not normalized_scene_ref:
            raise ValueError(
                "scene transcript promotion requires a non-empty scene_ref"
            )
        if normalized_scene_ref != input_model.scene_ref:
            input_model = input_model.model_copy(
                update={"scene_ref": normalized_scene_ref}
            )
        self._validate_scene_scoped_candidates(input_model=input_model)
        source_items = self._collect_source_items(input_model=input_model)
        if not source_items:
            return None
        transcript_text = self._render_transcript(source_items)
        if not transcript_text:
            return None

        collection = self._collection_service.ensure_story_collection(
            story_id=input_model.story_id,
            scope="story",
            collection_kind="recall",
        )
        asset_id = self._build_asset_id(
            session_id=input_model.session_id,
            chapter_index=input_model.chapter_index,
            scene_ref=input_model.scene_ref,
        )
        now = _utcnow()
        existing_asset = self._document_service.get_source_asset(asset_id)
        scene_digest = self._scene_digest(
            session_id=input_model.session_id,
            chapter_index=input_model.chapter_index,
            scene_ref=input_model.scene_ref,
        )[:16]
        section_path = f"recall.chapter.{input_model.chapter_index}.scene_transcript.{scene_digest}"
        metadata = build_recall_materialization_metadata(
            materialization_kind=SCENE_TRANSCRIPT_KIND,
            materialization_event=SCENE_CLOSE_EVENT,
            session_id=input_model.session_id,
            chapter_index=input_model.chapter_index,
            domain_path=section_path,
            extra={
                "scene_ref": input_model.scene_ref,
                "transcript_source_count": len(source_items),
                "transcript_includes_discussion": any(
                    item.source_kind == "discussion" for item in source_items
                ),
                "transcript_includes_accepted_segments": any(
                    item.source_kind == "accepted_segment" for item in source_items
                ),
            },
        )
        asset = SourceAsset(
            asset_id=asset_id,
            story_id=input_model.story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            workspace_id=input_model.source_workspace_id,
            step_id="active_story",
            commit_id=None,
            asset_kind="scene_transcript",
            source_ref=(
                f"story_session:{input_model.session_id}:chapter:{input_model.chapter_index}:"
                f"scene_ref:{input_model.scene_ref}"
            ),
            title=(
                f"Chapter {input_model.chapter_index} Scene Transcript "
                f"{input_model.scene_ref}"
            ),
            raw_excerpt=transcript_text[:280],
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["recall"],
            metadata={
                **metadata,
                "seed_sections": [
                    build_recall_seed_section(
                        section_id=f"scene_transcript:{scene_digest}",
                        title=(
                            f"Chapter {input_model.chapter_index} Scene Transcript "
                            f"{input_model.scene_ref}"
                        ),
                        path=section_path,
                        text=transcript_text,
                        metadata=metadata,
                        tags=[SCENE_TRANSCRIPT_KIND, "recall"],
                    )
                ],
            },
            created_at=existing_asset.created_at if existing_asset is not None else now,
            updated_at=now,
        )
        self._document_service.upsert_source_asset(asset)
        if existing_asset is None:
            job = self._ingestion_service.ingest_asset(
                story_id=input_model.story_id,
                asset_id=asset_id,
                collection_id=collection.collection_id,
            )
        else:
            job = self._ingestion_service.reindex_asset(
                story_id=input_model.story_id,
                asset_id=asset_id,
            )
        self._raise_if_job_failed(job=job, asset_id=asset_id)
        return asset_id

    @classmethod
    def _collect_source_items(
        cls,
        *,
        input_model: SceneTranscriptPromotionInput,
    ) -> list[_TranscriptSourceItem]:
        items: list[_TranscriptSourceItem] = []
        for entry in input_model.discussion_entries:
            if entry.role not in {"user", "assistant"}:
                continue
            content_text = entry.content_text.strip()
            if not content_text:
                continue
            items.append(
                _TranscriptSourceItem(
                    source_kind="discussion",
                    source_id=entry.entry_id,
                    label="User" if entry.role == "user" else "Assistant",
                    text=content_text,
                    created_at=entry.created_at,
                )
            )
        for artifact in input_model.accepted_segments:
            if not cls._is_eligible_story_segment(artifact):
                continue
            items.append(
                _TranscriptSourceItem(
                    source_kind="accepted_segment",
                    source_id=artifact.artifact_id,
                    label=f"Accepted Segment r{artifact.revision}",
                    text=artifact.content_text.strip(),
                    created_at=artifact.created_at,
                )
            )
        return sorted(
            items,
            key=lambda item: (
                item.created_at,
                0 if item.source_kind == "discussion" else 1,
                item.source_id,
            ),
        )

    @staticmethod
    def _render_transcript(source_items: list[_TranscriptSourceItem]) -> str:
        rendered_parts = [f"{item.label}: {item.text}" for item in source_items]
        return "\n\n".join(part for part in rendered_parts if part.strip())

    @classmethod
    def _raise_if_missing_scene_ref(
        cls,
        *,
        discussion_entries: list[StoryDiscussionEntry],
        artifacts: list[StoryArtifact],
    ) -> None:
        for entry in discussion_entries:
            if (
                entry.role in {"user", "assistant"}
                and entry.content_text.strip()
                and not (entry.scene_ref or "").strip()
            ):
                raise ValueError(
                    "scene transcript candidate missing scene_ref: "
                    f"discussion:{entry.entry_id}"
                )
        for artifact in artifacts:
            if (
                cls._is_eligible_story_segment(artifact)
                and not (artifact.scene_ref or "").strip()
            ):
                raise ValueError(
                    "scene transcript candidate missing scene_ref: "
                    f"artifact:{artifact.artifact_id}"
                )

    @classmethod
    def _validate_scene_scoped_candidates(
        cls,
        *,
        input_model: SceneTranscriptPromotionInput,
    ) -> None:
        scene_ref = input_model.scene_ref
        for entry in input_model.discussion_entries:
            if (
                entry.role not in {"user", "assistant"}
                or not entry.content_text.strip()
            ):
                continue
            if (entry.scene_ref or "").strip() != scene_ref:
                raise ValueError(
                    "scene transcript candidates mixed scene refs: "
                    f"discussion:{entry.entry_id}:{entry.scene_ref}"
                )
        for artifact in input_model.accepted_segments:
            if not cls._is_story_segment_candidate(artifact):
                continue
            if (artifact.scene_ref or "").strip() != scene_ref:
                raise ValueError(
                    "scene transcript candidates mixed scene refs: "
                    f"artifact:{artifact.artifact_id}:{artifact.scene_ref}"
                )

    @classmethod
    def _build_asset_id(
        cls,
        *,
        session_id: str,
        chapter_index: int,
        scene_ref: str,
    ) -> str:
        return (
            "recall_scene_transcript_"
            + cls._scene_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                scene_ref=scene_ref,
            )[:24]
        )

    @staticmethod
    def _scene_digest(*, session_id: str, chapter_index: int, scene_ref: str) -> str:
        identity = f"{session_id}\n{chapter_index}\n{scene_ref.strip()}"
        return sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_story_segment_candidate(artifact: StoryArtifact) -> bool:
        return artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT and bool(
            artifact.content_text.strip()
        )

    @classmethod
    def _is_eligible_story_segment(cls, artifact: StoryArtifact) -> bool:
        return cls._is_story_segment_candidate(artifact) and (
            artifact.status == StoryArtifactStatus.ACCEPTED
        )

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(
            f"recall_scene_transcript_ingestion_failed:{asset_id}:{error_detail}"
        )
