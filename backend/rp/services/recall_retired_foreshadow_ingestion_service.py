"""Persist chapter-close retired foreshadow summaries into Recall Memory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from rp.models.memory_materialization import (
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    RETIRED_FORESHADOW_SUMMARY_KIND,
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


class RecallRetiredForeshadowIngestionService:
    """Persist authoritative retired foreshadow snapshots as chapter-close Recall assets."""

    _TERMINAL_STATUSES = {"resolved", "retired", "closed"}
    _TEXT_FIELDS = (
        "summary",
        "title",
        "label",
        "description",
        "resolution",
        "resolution_summary",
    )

    def __init__(self, session) -> None:
        self._document_service = RetrievalDocumentService(session)
        self._collection_service = RetrievalCollectionService(session)
        self._ingestion_service = RetrievalIngestionService(session)

    def ingest_retired_foreshadow_summaries(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        foreshadow_registry: list[dict[str, Any]],
        chapter_summary_text: str | None,
        continuity_notes: list[str],
        accepted_segments: list[StoryArtifact],
    ) -> list[str]:
        if not foreshadow_registry:
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

        for (
            foreshadow_id,
            terminal_status,
            foreshadow_snapshot,
        ) in self._iter_terminal_snapshots(foreshadow_registry):
            matched_segments = self._match_segments_for_foreshadow(
                foreshadow_id=foreshadow_id,
                foreshadow_snapshot=foreshadow_snapshot,
                accepted_segments=eligible_segments,
            )
            asset_id = self._build_asset_id(
                session_id=session_id,
                chapter_index=chapter_index,
                foreshadow_id=foreshadow_id,
            )
            now = _utcnow()
            existing_asset = self._document_service.get_source_asset(asset_id)
            key_digest = self._identity_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                foreshadow_id=foreshadow_id,
            )[:16]
            section_path = (
                f"recall.chapter.{chapter_index}.retired_foreshadow.{key_digest}"
            )
            rendered_text = self._render_summary_text(
                foreshadow_id=foreshadow_id,
                terminal_status=terminal_status,
                foreshadow_snapshot=foreshadow_snapshot,
                chapter_summary_text=normalized_summary,
                continuity_notes=normalized_notes,
                accepted_segments=matched_segments,
            )
            metadata = build_recall_materialization_metadata(
                materialization_kind=RETIRED_FORESHADOW_SUMMARY_KIND,
                materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
                session_id=session_id,
                chapter_index=chapter_index,
                domain_path=section_path,
                extra={
                    "foreshadow_id": foreshadow_id,
                    "terminal_status": terminal_status,
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
                asset_kind="retired_foreshadow_summary",
                source_ref=(
                    f"story_session:{session_id}:chapter:{chapter_index}:"
                    f"foreshadow:{key_digest}"
                ),
                title=(
                    f"Chapter {chapter_index} Retired Foreshadow Summary: "
                    f"{foreshadow_id}"
                ),
                raw_excerpt=rendered_text[:280],
                parse_status="queued",
                ingestion_status="queued",
                mapped_targets=["recall"],
                metadata={
                    **metadata,
                    "seed_sections": [
                        build_recall_seed_section(
                            section_id=f"retired_foreshadow_summary:{key_digest}",
                            title=(
                                f"Chapter {chapter_index} Retired Foreshadow Summary: "
                                f"{foreshadow_id}"
                            ),
                            path=section_path,
                            text=rendered_text,
                            metadata=metadata,
                            tags=[
                                RETIRED_FORESHADOW_SUMMARY_KIND,
                                "recall",
                                foreshadow_id,
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
    def _iter_terminal_snapshots(
        cls,
        foreshadow_registry: list[dict[str, Any]],
    ) -> list[tuple[str, str, dict[str, Any]]]:
        latest_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for item in foreshadow_registry:
            if not isinstance(item, dict):
                continue
            foreshadow_id = cls._normalize_foreshadow_id(item.get("foreshadow_id"))
            if not foreshadow_id:
                continue
            terminal_status = cls._resolve_terminal_status(item)
            if terminal_status is None:
                continue
            latest_by_id[foreshadow_id] = (terminal_status, dict(item))
        return [
            (foreshadow_id, terminal_status, snapshot)
            for foreshadow_id, (terminal_status, snapshot) in sorted(
                latest_by_id.items(),
                key=lambda item: item[0],
            )
        ]

    @staticmethod
    def _normalize_foreshadow_id(raw_value: object) -> str:
        if not isinstance(raw_value, str):
            return ""
        return raw_value.strip()

    @classmethod
    def _resolve_terminal_status(cls, snapshot: dict[str, Any]) -> str | None:
        for field_name in ("status", "state"):
            raw_value = snapshot.get(field_name)
            if not isinstance(raw_value, str):
                continue
            normalized = raw_value.strip().casefold()
            if normalized in cls._TERMINAL_STATUSES:
                return normalized
        return None

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
    def _match_segments_for_foreshadow(
        cls,
        *,
        foreshadow_id: str,
        foreshadow_snapshot: dict[str, Any],
        accepted_segments: list[StoryArtifact],
    ) -> list[StoryArtifact]:
        candidate_terms = cls._candidate_terms(
            foreshadow_id=foreshadow_id,
            foreshadow_snapshot=foreshadow_snapshot,
        )
        if not candidate_terms:
            return []
        matched: list[StoryArtifact] = []
        seen_artifact_ids: set[str] = set()
        for artifact in accepted_segments:
            if artifact.artifact_id in seen_artifact_ids:
                continue
            normalized_content = artifact.content_text.casefold()
            if not any(term in normalized_content for term in candidate_terms):
                continue
            seen_artifact_ids.add(artifact.artifact_id)
            matched.append(artifact)
        return matched

    @classmethod
    def _candidate_terms(
        cls,
        *,
        foreshadow_id: str,
        foreshadow_snapshot: dict[str, Any],
    ) -> list[str]:
        raw_terms = [foreshadow_id]
        for field_name in cls._TEXT_FIELDS:
            raw_value = foreshadow_snapshot.get(field_name)
            if isinstance(raw_value, str):
                raw_terms.append(raw_value)

        normalized_terms: list[str] = []
        seen: set[str] = set()
        for raw_term in raw_terms:
            normalized = cls._normalize_optional_text(raw_term)
            if normalized is None:
                continue
            lowered = normalized.casefold()
            if len(lowered) < 8 or lowered in seen:
                continue
            seen.add(lowered)
            normalized_terms.append(lowered)
        return normalized_terms

    @classmethod
    def _render_summary_text(
        cls,
        *,
        foreshadow_id: str,
        terminal_status: str,
        foreshadow_snapshot: dict[str, Any],
        chapter_summary_text: str | None,
        continuity_notes: list[str],
        accepted_segments: list[StoryArtifact],
    ) -> str:
        lines = [
            f"Retired foreshadow summary: {foreshadow_id}",
            "",
            f"Terminal status: {terminal_status}",
            "",
            "Authoritative terminal foreshadow snapshot:",
            cls._render_snapshot_text(foreshadow_snapshot),
        ]
        if chapter_summary_text is not None:
            lines.extend(["", "Chapter-close summary:", chapter_summary_text])
        if continuity_notes:
            lines.extend(["", "Continuity notes:"])
            lines.extend(f"- {note}" for note in continuity_notes)
        if accepted_segments:
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
    def _render_snapshot_text(snapshot: dict[str, Any]) -> str:
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
        foreshadow_id: str,
    ) -> str:
        return (
            "recall_retired_foreshadow_"
            + cls._identity_digest(
                session_id=session_id,
                chapter_index=chapter_index,
                foreshadow_id=foreshadow_id,
            )[:24]
        )

    @staticmethod
    def _identity_digest(
        *,
        session_id: str,
        chapter_index: int,
        foreshadow_id: str,
    ) -> str:
        identity = f"{session_id}\n{chapter_index}\n{foreshadow_id}"
        return sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _raise_if_job_failed(*, job: IndexJob, asset_id: str) -> None:
        if job.job_state == "completed":
            return
        error_detail = job.error_message or job.job_state
        raise RuntimeError(
            f"recall_retired_foreshadow_ingestion_failed:{asset_id}:{error_detail}"
        )

    @staticmethod
    def _is_eligible_story_segment(artifact: StoryArtifact) -> bool:
        return (
            artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and artifact.status == StoryArtifactStatus.ACCEPTED
            and bool(artifact.content_text.strip())
        )
