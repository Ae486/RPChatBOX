"""Setup-facing facade over the real retrieval-core ingestion pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import select

from models.rp_setup_store import (
    SetupAcceptedCommitRecord,
    SetupImportedAssetRecord,
    SetupRetrievalIngestionJobRecord,
    SetupWorkspaceRecord,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MinimalRetrievalIngestionService:
    """Keep the setup commit contract stable while delegating to retrieval-core."""

    def __init__(self, session):
        self._session = session
        self._collection_service = RetrievalCollectionService(session)
        self._document_service = RetrievalDocumentService(session)
        self._ingestion_service = RetrievalIngestionService(session)

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
        for job in jobs:
            self._run_single_job(
                workspace=workspace,
                commit=commit,
                collection_id=collection.collection_id,
                job=job,
            )
            completed_ids.append(job.job_id)
        self._session.commit()
        return completed_ids

    def _run_single_job(
        self,
        *,
        workspace: SetupWorkspaceRecord,
        commit: SetupAcceptedCommitRecord,
        collection_id: str,
        job: SetupRetrievalIngestionJobRecord,
    ) -> None:
        now = _utcnow()
        asset_record: SetupImportedAssetRecord | None = None
        title: str | None = None
        asset_kind = job.target_type
        source_ref = f"setup_commit:{commit.commit_id}:{job.target_ref}"
        mime_type: str | None = None
        storage_path: str | None = None
        mapped_targets: list[str] = []
        metadata: dict[str, object] = {
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
                metadata["asset_parse_status"] = asset_record.parse_status
                metadata["parsed_payload"] = asset_record.parsed_payload_json

        asset_id = (
            job.target_ref
            if job.target_type == "asset"
            else f"{commit.commit_id}:{job.target_type}:{job.target_ref}"
        )
        seed_sections = self._build_sections(commit=commit, job=job, asset_record=asset_record)
        raw_excerpt = seed_sections[0]["text"][:280] if seed_sections else None
        metadata["seed_sections"] = seed_sections
        if seed_sections:
            first_metadata = seed_sections[0].get("metadata") or {}
            metadata.setdefault("domain", first_metadata.get("domain"))
            metadata.setdefault("domain_path", first_metadata.get("domain_path"))

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

    def _build_sections(
        self,
        *,
        commit: SetupAcceptedCommitRecord,
        job: SetupRetrievalIngestionJobRecord,
        asset_record: SetupImportedAssetRecord | None,
    ) -> list[dict[str, object]]:
        if job.target_type == "foundation_entry":
            foundation = commit.snapshot_payload_json.get("foundation", {})
            for entry in foundation.get("entries", []):
                if (entry.get("entry_id") or entry.get("path")) == job.target_ref:
                    return [self._foundation_entry_to_section(entry)]
            return []
        if job.target_type == "blueprint":
            return self._blueprint_to_sections(commit.snapshot_payload_json.get("longform_blueprint", {}))
        if job.target_type == "asset" and asset_record is not None:
            return self._asset_to_sections(asset_record)
        return []

    def _foundation_entry_to_section(self, entry: dict) -> dict[str, object]:
        domain = self._coarse_domain_for_foundation(entry.get("domain"))
        domain_path = f"foundation.{entry.get('domain')}.{entry.get('path')}".strip(".")
        text = self._render_payload_text(entry.get("content", {}))
        title = entry.get("title") or entry.get("path") or entry.get("entry_id")
        return {
            "section_id": entry.get("entry_id") or uuid4().hex,
            "title": title,
            "path": entry.get("path") or entry.get("entry_id") or "foundation",
            "level": 1,
            "text": text,
            "metadata": {
                "domain": domain,
                "domain_path": domain_path,
                "title": title,
                "tags": list(entry.get("tags", [])),
                "source_refs": list(entry.get("source_refs", [])),
                "commit_id": entry.get("commit_id"),
            },
        }

    def _blueprint_to_sections(self, blueprint: dict) -> list[dict[str, object]]:
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
                sections.append(
                    {
                        "section_id": f"blueprint:{field_name}",
                        "title": field_name,
                        "path": f"longform_blueprint.{field_name}",
                        "level": 1,
                        "text": str(value),
                        "metadata": {
                            "domain": "chapter",
                            "domain_path": f"longform_blueprint.{field_name}",
                            "title": field_name,
                            "tags": ["blueprint"],
                            "commit_id": blueprint.get("commit_id"),
                        },
                    }
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
                sections.append(
                    {
                        "section_id": section_id,
                        "title": chapter.get("title") or section_id,
                        "path": f"longform_blueprint.chapter.{section_id}",
                        "level": 2,
                        "text": text,
                        "metadata": {
                            "domain": "chapter",
                            "domain_path": f"longform_blueprint.chapter.{section_id}",
                            "title": chapter.get("title"),
                            "tags": ["blueprint", "chapter"],
                        },
                    }
                )
        return sections

    def _asset_to_sections(self, asset: SetupImportedAssetRecord) -> list[dict[str, object]]:
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
                    normalized.append(
                        {
                            "section_id": str(section.get("section_id") or f"{asset.asset_id}:{index}"),
                            "title": title,
                            "path": path,
                            "level": int(section.get("level") or 1),
                            "text": text,
                            "metadata": {
                                "domain": self._domain_from_targets(asset.mapped_targets_json),
                                "domain_path": path,
                                "title": title,
                                "tags": list(section.get("tags", [])),
                                "commit_id": asset.asset_id,
                            },
                        }
                    )
                if normalized:
                    return normalized
        fallback_text = self._render_payload_text(payload) if payload else (asset.title or asset.source_ref)
        return [
            {
                "section_id": asset.asset_id,
                "title": asset.title,
                "path": f"asset.{asset.asset_id}",
                "level": 1,
                "text": fallback_text,
                "metadata": {
                    "domain": self._domain_from_targets(asset.mapped_targets_json),
                    "domain_path": f"asset.{asset.asset_id}",
                    "title": asset.title,
                    "tags": list(asset.mapped_targets_json or []),
                    "commit_id": asset.asset_id,
                },
            }
        ]

    @staticmethod
    def _render_payload_text(payload: object) -> str:
        if isinstance(payload, str):
            return payload
        if payload is None:
            return ""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _coarse_domain_for_foundation(domain: str | None) -> str:
        if domain == "character":
            return "character"
        return "world_rule"

    @staticmethod
    def _domain_from_targets(mapped_targets: list[str]) -> str:
        if any("character" in target for target in mapped_targets):
            return "character"
        if any("chapter" in target or "blueprint" in target for target in mapped_targets):
            return "chapter"
        return "world_rule"
