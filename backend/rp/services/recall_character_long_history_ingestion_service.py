"""Persist chapter-close per-character history summaries into Recall Memory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from rp.models.memory_materialization import (
    CHARACTER_LONG_HISTORY_SUMMARY_KIND,
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
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecallCharacterLongHistoryIngestionService:
    """Persist authoritative character snapshots as chapter-close Recall assets."""

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def ingest_character_summaries(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        character_state_digest: dict[str, Any],
        chapter_summary_text: str | None,
        continuity_notes: list[str],
        accepted_segments: list[StoryArtifact],
    ) -> list[str]:
        if not character_state_digest:
            return []

        collection = self._collection_service.ensure_story_collection(
            story_id=story_id,
            scope="story",
            collection_kind="recall",
        )
        normalized_summary = self._normalize_optional_text(chapter_summary_text)
        normalized_notes = self._normalize_continuity_notes(continuity_notes)
        eligible_segments = self._list_eligible_segments(accepted_segments)
        persisted_asset_ids: list[str] = []

        for character_key, character_snapshot in self._iter_character_snapshots(
            character_state_digest
        ):
            # The authoritative snapshot is the producer root. If the snapshot is
            # empty, supporting context alone must not create a historical record.
            if self._is_empty_snapshot(character_snapshot):
                continue

            matched_segments = self._match_segments_for_character(
                character_key=character_key,
                accepted_segments=eligible_segments,
            )
            asset_id = self._build_asset_id(
                session_id=session_id,
                chapter_index=chapter_index,
                character_key=character_key,
            )
            now = _utcnow()
            existing_asset = self._document_service.get_source_asset(asset_id)
            key_digest = self._identity_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                character_key=character_key,
            )[:16]
            section_path = (
                f"recall.chapter.{chapter_index}.character_long_history.{key_digest}"
            )
            rendered_text = self._render_summary_text(
                character_key=character_key,
                character_snapshot=character_snapshot,
                chapter_summary_text=normalized_summary,
                continuity_notes=normalized_notes,
                accepted_segments=matched_segments,
            )
            metadata = build_recall_materialization_metadata(
                materialization_kind=CHARACTER_LONG_HISTORY_SUMMARY_KIND,
                materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
                session_id=session_id,
                chapter_index=chapter_index,
                domain_path=section_path,
                extra={
                    "character_key": character_key,
                    "includes_chapter_summary": normalized_summary is not None,
                    "continuity_note_count": len(normalized_notes),
                    "accepted_segment_evidence_count": len(matched_segments),
                },
            )
            asset = SourceAsset(
                asset_id=asset_id,
                story_id=story_id,
                mode=StoryMode.LONGFORM,
                collection_id=collection.collection_id,
                workspace_id=source_workspace_id,
                step_id="active_story",
                commit_id=None,
                asset_kind="character_long_history_summary",
                source_ref=(
                    f"story_session:{session_id}:chapter:{chapter_index}:"
                    f"character:{key_digest}"
                ),
                title=(
                    f"Chapter {chapter_index} Character History Summary: "
                    f"{character_key}"
                ),
                raw_excerpt=rendered_text[:280],
                parse_status="queued",
                ingestion_status="queued",
                mapped_targets=["recall"],
                metadata={
                    **metadata,
                    "seed_sections": [
                        build_recall_seed_section(
                            section_id=f"character_long_history_summary:{key_digest}",
                            title=(
                                f"Chapter {chapter_index} Character History Summary: "
                                f"{character_key}"
                            ),
                            path=section_path,
                            text=rendered_text,
                            metadata=metadata,
                            tags=[
                                CHARACTER_LONG_HISTORY_SUMMARY_KIND,
                                "recall",
                                character_key,
                            ],
                        )
                    ],
                },
                created_at=existing_asset.created_at
                if existing_asset is not None
                else now,
                updated_at=now,
            )
            self._document_service.upsert_source_asset(asset)
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

    @classmethod
    def _iter_character_snapshots(
        cls,
        character_state_digest: dict[str, Any],
    ) -> list[tuple[str, Any]]:
        items: list[tuple[str, Any]] = []
        for raw_key, snapshot in character_state_digest.items():
            character_key = cls._normalize_character_key(raw_key)
            if not character_key:
                continue
            items.append((character_key, snapshot))
        items.sort(key=lambda item: item[0])
        return items

    @staticmethod
    def _normalize_character_key(raw_key: object) -> str:
        if not isinstance(raw_key, str):
            return ""
        return raw_key.strip()

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @classmethod
    def _normalize_continuity_notes(cls, notes: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for note in notes:
            normalized = cls._normalize_optional_text(note)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    @staticmethod
    def _is_empty_snapshot(snapshot: Any) -> bool:
        if snapshot is None:
            return True
        if isinstance(snapshot, str):
            return not snapshot.strip()
        if isinstance(snapshot, (dict, list, tuple, set)):
            return len(snapshot) == 0
        return False

    @classmethod
    def _list_eligible_segments(
        cls,
        accepted_segments: list[StoryArtifact],
    ) -> list[StoryArtifact]:
        return sorted(
            (
                artifact
                for artifact in accepted_segments
                if cls._is_eligible_story_segment(artifact)
            ),
            key=lambda item: (item.created_at, item.artifact_id),
        )

    @classmethod
    def _match_segments_for_character(
        cls,
        *,
        character_key: str,
        accepted_segments: list[StoryArtifact],
    ) -> list[StoryArtifact]:
        normalized_key = character_key.casefold()
        matched: list[StoryArtifact] = []
        seen_artifact_ids: set[str] = set()
        for artifact in accepted_segments:
            if artifact.artifact_id in seen_artifact_ids:
                continue
            if normalized_key not in artifact.content_text.casefold():
                continue
            seen_artifact_ids.add(artifact.artifact_id)
            matched.append(artifact)
        return matched

    @classmethod
    def _render_summary_text(
        cls,
        *,
        character_key: str,
        character_snapshot: Any,
        chapter_summary_text: str | None,
        continuity_notes: list[str],
        accepted_segments: list[StoryArtifact],
    ) -> str:
        lines = [
            f"Character long-history summary: {character_key}",
            "",
            "Authoritative character snapshot:",
            cls._render_snapshot_text(character_snapshot),
        ]
        if chapter_summary_text is not None:
            lines.extend(["", "Chapter-close summary:", chapter_summary_text])
        if continuity_notes:
            lines.extend(["", "Continuity notes:"])
            lines.extend(f"- {note}" for note in continuity_notes)
        if accepted_segments:
            # Evidence matching stays heuristic, but it must remain deterministic.
            lines.extend(["", "Accepted chapter evidence:"])
            lines.extend(
                (
                    f"- Artifact {artifact.artifact_id} "
                    f"(revision {artifact.revision}): "
                    f"{cls._normalize_segment_text(artifact.content_text)}"
                )
                for artifact in accepted_segments
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _render_snapshot_text(snapshot: Any) -> str:
        if isinstance(snapshot, str):
            return snapshot.strip()
        return json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _normalize_segment_text(content_text: str) -> str:
        return " ".join(content_text.split())

    @classmethod
    def _build_asset_id(
        cls,
        *,
        session_id: str,
        chapter_index: int,
        character_key: str,
    ) -> str:
        return (
            "recall_character_long_history_"
            + cls._identity_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                character_key=character_key,
            )[:24]
        )

    @staticmethod
    def _identity_digest(
        *,
        session_id: str,
        chapter_index: int,
        character_key: str,
    ) -> str:
        identity = f"{session_id}\n{chapter_index}\n{character_key}"
        return sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(
            f"recall_character_long_history_ingestion_failed:{asset_id}:{error_detail}"
        )

    @staticmethod
    def _is_eligible_story_segment(artifact: StoryArtifact) -> bool:
        return (
            artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and artifact.status == StoryArtifactStatus.ACCEPTED
            and bool(artifact.content_text.strip())
        )
