"""Setup-facing facade over the real retrieval-core ingestion pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import select

from models.rp_setup_store import (
    SetupAcceptedCommitRecord,
    SetupImportedAssetRecord,
    SetupRetrievalIngestionJobRecord,
    SetupWorkspaceRecord,
)
from rp.models.memory_materialization import (
    FOUNDATION_ENTRY_SOURCE_TYPE,
    IMPORTED_ASSET_SOURCE_TYPE,
    LONGFORM_BLUEPRINT_SOURCE_TYPE,
    SETUP_COMMIT_IMPORT_EVENT,
    build_archival_seed_section,
    build_archival_source_metadata,
)
from rp.models.memory_graph_projection import GRAPH_JOB_REASON_ARCHIVAL_INGESTED
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.memory_graph_projection_service import MemoryGraphProjectionService
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MinimalRetrievalIngestionService:
    """Keep the setup commit contract stable while delegating to retrieval-core."""

    def __init__(
        self,
        session,
        *,
        graph_projection_service: MemoryGraphProjectionService | None = None,
    ):
        self._session = session
        self._collection_service = RetrievalCollectionService(session)
        self._document_service = RetrievalDocumentService(session)
        self._ingestion_service = RetrievalIngestionService(session)
        self._graph_projection_service = (
            graph_projection_service or MemoryGraphProjectionService(session)
        )

    def ingest_commit(self, *, workspace_id: str, commit_id: str) -> list[str]:
        workspace = self._session.get(SetupWorkspaceRecord, workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        commit = self._session.get(SetupAcceptedCommitRecord, commit_id)
        if commit is None or commit.workspace_id != workspace_id:
            raise ValueError(f"AcceptedCommit not found: {commit_id}")

        collection = self._collection_service.ensure_story_collection(
            story_id=workspace.story_id,
            scope="story",
            collection_kind="archival",
        )
        jobs = list(
            self._session.exec(
                select(SetupRetrievalIngestionJobRecord)
                .where(SetupRetrievalIngestionJobRecord.workspace_id == workspace_id)
                .where(SetupRetrievalIngestionJobRecord.commit_id == commit_id)
            ).all()
        )
        completed_ids: list[str] = []
        completed_asset_ids: list[str] = []
        for job in jobs:
            asset_id = self._run_single_job(
                workspace=workspace,
                commit=commit,
                collection_id=collection.collection_id,
                job=job,
            )
            completed_ids.append(job.job_id)
            if asset_id is not None:
                completed_asset_ids.append(asset_id)
        self._queue_graph_extraction_after_archival_ingestion(
            story_id=workspace.story_id,
            workspace_id=workspace.workspace_id,
            commit_id=commit.commit_id,
            source_asset_ids=completed_asset_ids,
        )
        self._session.commit()
        return completed_ids

    def _run_single_job(
        self,
        *,
        workspace: SetupWorkspaceRecord,
        commit: SetupAcceptedCommitRecord,
        collection_id: str,
        job: SetupRetrievalIngestionJobRecord,
    ) -> str | None:
        now = _utcnow()
        asset_record: SetupImportedAssetRecord | None = None
        title: str | None = None
        asset_kind = job.target_type
        source_ref = f"setup_commit:{commit.commit_id}:{job.target_ref}"
        mime_type: str | None = None
        storage_path: str | None = None
        mapped_targets: list[str] = []
        source_type = self._source_type_for_job(job)
        metadata_extra: dict[str, Any] = {
            "commit_id": commit.commit_id,
            "step_id": job.step_id,
            "target_type": job.target_type,
            "target_ref": job.target_ref,
        }

        if job.target_type == "asset":
            asset_record = self._session.get(SetupImportedAssetRecord, job.target_ref)
            if asset_record is not None:
                title = asset_record.title
                asset_kind = asset_record.asset_kind
                source_ref = asset_record.source_ref
                mime_type = asset_record.mime_type
                storage_path = asset_record.local_path
                mapped_targets = list(asset_record.mapped_targets_json or [])
                metadata_extra["asset_kind"] = asset_record.asset_kind
                metadata_extra["asset_parse_status"] = asset_record.parse_status
                metadata_extra["parsed_payload"] = asset_record.parsed_payload_json

        asset_id = (
            job.target_ref
            if job.target_type == "asset"
            else f"{commit.commit_id}:{job.target_type}:{job.target_ref}"
        )
        seed_sections = self._build_sections(
            commit=commit,
            job=job,
            asset_record=asset_record,
            source_ref=source_ref,
            source_type=source_type,
        )
        first_text = seed_sections[0].get("text") if seed_sections else None
        raw_excerpt = str(first_text)[:280] if first_text is not None else None
        first_metadata = seed_sections[0].get("metadata") if seed_sections else {}
        first_metadata = first_metadata if isinstance(first_metadata, dict) else {}
        domain = str(
            first_metadata.get("domain") or self._domain_from_targets(mapped_targets)
        )
        domain_path = str(first_metadata.get("domain_path") or source_ref)
        metadata = build_archival_source_metadata(
            source_type=source_type,
            import_event=SETUP_COMMIT_IMPORT_EVENT,
            workspace_id=workspace.workspace_id,
            commit_id=commit.commit_id,
            step_id=job.step_id,
            source_ref=source_ref,
            domain=domain,
            domain_path=domain_path,
            extra=metadata_extra,
        )
        metadata["seed_sections"] = seed_sections

        source_asset = SourceAsset(
            asset_id=asset_id,
            story_id=workspace.story_id,
            mode=StoryMode(workspace.mode),
            collection_id=collection_id,
            workspace_id=workspace.workspace_id,
            step_id=job.step_id,
            commit_id=commit.commit_id,
            asset_kind=asset_kind,
            source_ref=source_ref,
            title=title,
            storage_path=storage_path,
            mime_type=mime_type,
            raw_excerpt=raw_excerpt,
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=mapped_targets,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        self._document_service.upsert_source_asset(source_asset)
        self._session.flush()

        index_job = self._ingestion_service.ingest_asset(
            story_id=workspace.story_id,
            asset_id=asset_id,
            collection_id=collection_id,
        )

        job.index_job_id = index_job.job_id
        job.state = index_job.job_state
        job.warnings_json = list(index_job.warnings)
        job.error_message = index_job.error_message
        job.updated_at = _utcnow()
        job.completed_at = index_job.completed_at
        self._session.add(job)
        return asset_id if index_job.job_state == "completed" else None

    def _queue_graph_extraction_after_archival_ingestion(
        self,
        *,
        story_id: str,
        workspace_id: str,
        commit_id: str,
        source_asset_ids: list[str],
    ) -> None:
        if not source_asset_ids:
            return
        try:
            with self._session.begin_nested():
                self._graph_projection_service.queue_archival_extraction_jobs(
                    story_id=story_id,
                    source_asset_ids=source_asset_ids,
                    workspace_id=workspace_id,
                    commit_id=commit_id,
                    queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
                )
        except Exception:
            # Graph extraction is asynchronous maintenance. Queue failures must
            # not roll back setup commit ingestion or archival retrieval readiness.
            return

    def _build_sections(
        self,
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        asset_record: SetupImportedAssetRecord | None,
        source_ref: str,
        source_type: str,
    ) -> list[dict[str, object]]:
        if job.target_type == "foundation_entry":
            foundation = commit.snapshot_payload_json.get("foundation", {})
            if not foundation:
                foundation = commit.snapshot_payload_json.get(job.step_id, {})
            for entry in foundation.get("entries", []):
                if (entry.get("entry_id") or entry.get("path")) == job.target_ref:
                    return [
                        self._foundation_entry_to_section(
                            commit=commit,
                            job=job,
                            entry=entry,
                            source_ref=source_ref,
                            source_type=source_type,
                        )
                    ]
            return []
        if job.target_type == "blueprint":
            return self._blueprint_to_sections(
                commit=commit,
                job=job,
                blueprint=commit.snapshot_payload_json.get("longform_blueprint", {}),
                source_ref=source_ref,
                source_type=source_type,
            )
        if job.target_type == "asset" and asset_record is not None:
            return self._asset_to_sections(
                commit=commit,
                job=job,
                asset=asset_record,
                source_ref=source_ref,
                source_type=source_type,
            )
        return []

    def _foundation_entry_to_section(
        self,
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        entry: dict,
        source_ref: str,
        source_type: str,
    ) -> dict[str, object]:
        domain = self._coarse_domain_for_setup_entry(
            entry.get("domain"),
            entry_type=entry.get("entry_type"),
            semantic_path=entry.get("semantic_path"),
        )
        semantic_path = entry.get("semantic_path")
        if isinstance(semantic_path, str) and semantic_path.strip():
            domain_path = semantic_path.strip()
        else:
            domain_path = f"foundation.{entry.get('domain')}.{entry.get('path')}".strip(".")
        text = self._render_setup_entry_text(entry)
        title = entry.get("title") or entry.get("path") or entry.get("entry_id")
        metadata = self._build_archival_metadata(
            commit=commit,
            job=job,
            source_ref=source_ref,
            source_type=source_type,
            domain=domain,
            domain_path=domain_path,
            extra={
                "title": title,
                "source_refs": list(entry.get("source_refs", [])),
                "entry_commit_id": entry.get("commit_id"),
                "semantic_path": semantic_path,
            },
        )
        return build_archival_seed_section(
            section_id=str(entry.get("entry_id") or uuid4().hex),
            title=str(title or "foundation"),
            path=str(semantic_path or entry.get("path") or entry.get("entry_id") or "foundation"),
            level=1,
            text=text,
            metadata=metadata,
            tags=list(entry.get("tags", [])),
        )

    def _render_setup_entry_text(self, entry: dict) -> str:
        sections = entry.get("sections")
        if isinstance(sections, list) and sections:
            rendered_sections: list[str] = []
            for section in sections:
                if not isinstance(section, dict):
                    continue
                rendered = self._render_setup_section_text(section)
                if not rendered:
                    continue
                title = section.get("title")
                if isinstance(title, str) and title.strip():
                    rendered_sections.append(f"{title.strip()}\n{rendered}")
                else:
                    rendered_sections.append(rendered)
            if rendered_sections:
                return "\n\n".join(rendered_sections)

        content = entry.get("content")
        if isinstance(content, dict) and content:
            return self._render_payload_text(content)
        if isinstance(content, str) and content.strip():
            return content.strip()

        for fallback_key in ("summary", "title", "semantic_path", "path", "entry_id"):
            fallback_value = entry.get(fallback_key)
            if isinstance(fallback_value, str) and fallback_value.strip():
                return fallback_value.strip()
        return ""

    def _render_setup_section_text(self, section: dict) -> str:
        content = section.get("content")
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, dict):
            return ""

        kind = section.get("kind")
        if kind == "text":
            text = content.get("text")
            if isinstance(text, str):
                return text.strip()
        elif kind == "list":
            items = content.get("items")
            if isinstance(items, list):
                rendered_items: list[str] = []
                for item in items:
                    if isinstance(item, str) and item.strip():
                        rendered_items.append(f"- {item.strip()}")
                    elif isinstance(item, dict):
                        text = item.get("text") or item.get("title") or item.get("label")
                        if isinstance(text, str) and text.strip():
                            rendered_items.append(f"- {text.strip()}")
                        else:
                            rendered_items.append(f"- {self._render_payload_text(item)}")
                    elif item is not None:
                        rendered_items.append(f"- {item}")
                if rendered_items:
                    return "\n".join(rendered_items)
        elif kind == "key_value":
            values = content.get("values")
            if isinstance(values, dict):
                rendered_pairs: list[str] = []
                for key, value in values.items():
                    if isinstance(value, str):
                        rendered_value = value.strip()
                    else:
                        rendered_value = self._render_payload_text(value)
                    rendered_pairs.append(f"{key}: {rendered_value}")
                if rendered_pairs:
                    return "\n".join(rendered_pairs)

        return self._render_payload_text(content)

    def _blueprint_to_sections(
        self,
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        blueprint: dict,
        source_ref: str,
        source_type: str,
    ) -> list[dict[str, object]]:
        sections: list[dict[str, object]] = []
        for field_name in (
            "premise",
            "central_conflict",
            "protagonist_arc",
            "cast_plan",
            "chapter_strategy",
            "section_strategy",
            "ending_direction",
        ):
            value = blueprint.get(field_name)
            if value:
                domain_path = f"longform_blueprint.{field_name}"
                metadata = self._build_archival_metadata(
                    commit=commit,
                    job=job,
                    source_ref=source_ref,
                    source_type=source_type,
                    domain="chapter",
                    domain_path=domain_path,
                    extra={"title": field_name},
                )
                sections.append(
                    build_archival_seed_section(
                        section_id=f"blueprint:{field_name}",
                        title=field_name,
                        path=domain_path,
                        level=1,
                        text=str(value),
                        metadata=metadata,
                        tags=["blueprint"],
                    )
                )
        for chapter in blueprint.get("chapter_blueprints", []):
            text = "\n".join(
                part
                for part in (
                    chapter.get("purpose"),
                    "\n".join(chapter.get("major_beats", [])),
                    "\n".join(chapter.get("setup_payoff_targets", [])),
                )
                if part
            )
            if text:
                section_id = chapter.get("chapter_id") or uuid4().hex
                domain_path = f"longform_blueprint.chapter.{section_id}"
                metadata = self._build_archival_metadata(
                    commit=commit,
                    job=job,
                    source_ref=source_ref,
                    source_type=source_type,
                    domain="chapter",
                    domain_path=domain_path,
                    extra={"title": chapter.get("title")},
                )
                sections.append(
                    build_archival_seed_section(
                        section_id=str(section_id),
                        title=str(chapter.get("title") or section_id),
                        path=domain_path,
                        level=2,
                        text=text,
                        metadata=metadata,
                        tags=["blueprint", "chapter"],
                    )
                )
        return sections

    def _asset_to_sections(
        self,
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        asset: SetupImportedAssetRecord,
        source_ref: str,
        source_type: str,
    ) -> list[dict[str, object]]:
        payload = asset.parsed_payload_json
        if isinstance(payload, dict):
            sections = payload.get("sections")
            if isinstance(sections, list):
                normalized: list[dict[str, object]] = []
                for index, section in enumerate(sections):
                    if not isinstance(section, dict):
                        continue
                    text = section.get("text")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    path = str(section.get("path") or f"asset.section.{index}")
                    title = section.get("title")
                    raw_metadata_value = section.get("metadata")
                    raw_metadata: dict[str, Any] = (
                        raw_metadata_value
                        if isinstance(raw_metadata_value, dict)
                        else {}
                    )
                    domain = str(
                        raw_metadata.get("domain")
                        or self._domain_from_targets(asset.mapped_targets_json)
                    )
                    domain_path = str(raw_metadata.get("domain_path") or path)
                    tags = list(section.get("tags") or raw_metadata.get("tags") or [])
                    metadata = self._build_archival_metadata(
                        commit=commit,
                        job=job,
                        source_ref=source_ref,
                        source_type=source_type,
                        domain=domain,
                        domain_path=domain_path,
                        extra={
                            **raw_metadata,
                            "title": title,
                            "asset_id": asset.asset_id,
                            "asset_kind": asset.asset_kind,
                        },
                    )
                    normalized.append(
                        build_archival_seed_section(
                            section_id=str(
                                section.get("section_id") or f"{asset.asset_id}:{index}"
                            ),
                            title=str(title or path),
                            path=path,
                            level=int(section.get("level") or 1),
                            text=text,
                            metadata=metadata,
                            tags=tags,
                        )
                    )
                if normalized:
                    return normalized
        fallback_text = (
            self._render_payload_text(payload)
            if payload
            else (asset.title or asset.source_ref)
        )
        domain = self._domain_from_targets(asset.mapped_targets_json)
        domain_path = f"asset.{asset.asset_id}"
        metadata = self._build_archival_metadata(
            commit=commit,
            job=job,
            source_ref=source_ref,
            source_type=source_type,
            domain=domain,
            domain_path=domain_path,
            extra={
                "title": asset.title,
                "asset_id": asset.asset_id,
                "asset_kind": asset.asset_kind,
            },
        )
        return [
            build_archival_seed_section(
                section_id=asset.asset_id,
                title=str(asset.title or asset.source_ref),
                path=domain_path,
                level=1,
                text=fallback_text,
                metadata=metadata,
                tags=list(asset.mapped_targets_json or []),
            )
        ]

    @staticmethod
    def _source_type_for_job(job: SetupRetrievalIngestionJobRecord) -> str:
        if job.target_type == "foundation_entry":
            return FOUNDATION_ENTRY_SOURCE_TYPE
        if job.target_type == "blueprint":
            return LONGFORM_BLUEPRINT_SOURCE_TYPE
        if job.target_type == "asset":
            return IMPORTED_ASSET_SOURCE_TYPE
        return job.target_type

    @staticmethod
    def _build_archival_metadata(
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        source_ref: str,
        source_type: str,
        domain: str,
        domain_path: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_archival_source_metadata(
            source_type=source_type,
            import_event=SETUP_COMMIT_IMPORT_EVENT,
            workspace_id=job.workspace_id,
            commit_id=commit.commit_id,
            step_id=job.step_id,
            source_ref=source_ref,
            domain=domain,
            domain_path=domain_path,
            extra=extra,
        )

    @staticmethod
    def _render_payload_text(payload: object) -> str:
        if isinstance(payload, str):
            return payload
        if payload is None:
            return ""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _coarse_domain_for_setup_entry(
        domain: str | None,
        *,
        entry_type: str | None = None,
        semantic_path: str | None = None,
    ) -> str:
        if domain == "character" or entry_type in {"character", "relationship", "group"}:
            return "character"
        if domain == "chapter" or (semantic_path and "chapter" in semantic_path):
            return "chapter"
        if entry_type in {"plot_thread", "foreshadow"}:
            return entry_type
        return "world_rule"

    @staticmethod
    def _domain_from_targets(mapped_targets: list[str]) -> str:
        if any("character" in target for target in mapped_targets):
            return "character"
        if any(
            "chapter" in target or "blueprint" in target for target in mapped_targets
        ):
            return "chapter"
        return "world_rule"
