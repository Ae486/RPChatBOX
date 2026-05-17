"""Editable setup draft source for session memory manifests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from rp.models.setup_drafts import (
    FoundationEntry,
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)

from .contracts import SetupSessionMemoryManifestItem
from .sources import join_search_text, make_freshness, preview_text


class EditableDraftMemorySource:
    """Derive refs from current editable setup drafts without storing payloads."""

    source_kind = "editable_draft"

    def build_items(
        self, *, workspace, **kwargs: Any
    ) -> list[SetupSessionMemoryManifestItem]:
        items: list[SetupSessionMemoryManifestItem] = []
        for block_key in sorted(workspace.draft_blocks):
            block = workspace.draft_blocks[block_key]
            items.extend(self._stage_block_items(workspace=workspace, block=block))
        items.extend(self._legacy_items(workspace=workspace))
        return items

    def _stage_block_items(
        self,
        *,
        workspace,
        block: SetupStageDraftBlock,
    ) -> list[SetupSessionMemoryManifestItem]:
        stage = block.stage_id.value
        items: list[SetupSessionMemoryManifestItem] = []
        for entry in block.entries:
            items.append(
                self._entry_item(workspace=workspace, stage=stage, entry=entry)
            )
            items.extend(
                self._section_item(
                    workspace=workspace,
                    stage=stage,
                    entry=entry,
                    section=section,
                )
                for section in entry.sections
            )
        return items

    def _entry_item(
        self,
        *,
        workspace,
        stage: str,
        entry: SetupDraftEntry,
    ) -> SetupSessionMemoryManifestItem:
        payload = entry.model_dump(mode="json", exclude_none=True)
        summary = entry.summary or self._entry_summary(entry)
        return SetupSessionMemoryManifestItem(
            ref=f"stage:{stage}:{entry.entry_id}",
            title=entry.title,
            summary=summary,
            source_kind="editable_draft",
            ref_kind="setup_fact_entry",
            stage=stage,
            block_type=stage,
            tags=list(dict.fromkeys([stage, entry.entry_type, *entry.tags])),
            search_text=join_search_text(
                [
                    stage,
                    entry.entry_id,
                    entry.entry_type,
                    entry.semantic_path,
                    entry.title,
                    entry.display_label,
                    entry.summary,
                    entry.aliases,
                    entry.tags,
                    payload,
                ]
            ),
            freshness=make_freshness(workspace=workspace, payload=payload),
            metadata={
                "entry_id": entry.entry_id,
                "entry_type": entry.entry_type,
                "semantic_path": entry.semantic_path,
            },
        )

    def _section_item(
        self,
        *,
        workspace,
        stage: str,
        entry: SetupDraftEntry,
        section: SetupDraftSection,
    ) -> SetupSessionMemoryManifestItem:
        payload = section.model_dump(mode="json", exclude_none=True)
        summary = self._section_summary(section)
        return SetupSessionMemoryManifestItem(
            ref=f"stage:{stage}:{entry.entry_id}:{section.section_id}",
            title=section.title,
            summary=summary,
            source_kind="editable_draft",
            ref_kind="setup_fact_section",
            stage=stage,
            block_type=stage,
            tags=list(
                dict.fromkeys([stage, entry.entry_type, *entry.tags, *section.tags])
            ),
            search_text=join_search_text(
                [
                    stage,
                    entry.entry_id,
                    section.section_id,
                    entry.semantic_path,
                    entry.title,
                    section.title,
                    section.kind.value,
                    section.retrieval_role,
                    entry.tags,
                    section.tags,
                    payload,
                ]
            ),
            freshness=make_freshness(workspace=workspace, payload=payload),
            metadata={
                "entry_id": entry.entry_id,
                "section_id": section.section_id,
                "entry_type": entry.entry_type,
                "semantic_path": f"{entry.semantic_path}.{section.section_id}",
            },
        )

    def _legacy_items(self, *, workspace) -> list[SetupSessionMemoryManifestItem]:
        items: list[SetupSessionMemoryManifestItem] = []
        if workspace.foundation_draft is not None:
            for entry in workspace.foundation_draft.entries:
                items.append(
                    self._legacy_foundation_entry(workspace=workspace, entry=entry)
                )
        return items

    def _legacy_foundation_entry(
        self,
        *,
        workspace,
        entry: FoundationEntry,
    ) -> SetupSessionMemoryManifestItem:
        payload = entry.model_dump(mode="json", exclude_none=True)
        title = entry.title or entry.path or entry.entry_id
        summary = self._legacy_summary(entry.content)
        return SetupSessionMemoryManifestItem(
            ref=f"foundation:{entry.entry_id}",
            title=title,
            summary=summary,
            source_kind="editable_draft",
            ref_kind="setup_fact_entry",
            stage="foundation",
            block_type="foundation_entry",
            tags=list(dict.fromkeys(["foundation", entry.domain, *entry.tags])),
            search_text=join_search_text(
                [
                    entry.entry_id,
                    entry.domain,
                    entry.path,
                    entry.title,
                    entry.tags,
                    entry.content,
                ]
            ),
            freshness=make_freshness(workspace=workspace, payload=payload),
            metadata={"entry_id": entry.entry_id, "semantic_path": entry.path},
        )

    @classmethod
    def _stage_block_summary(cls, block: SetupStageDraftBlock) -> str | None:
        parts = [cls._entry_summary(entry) for entry in block.entries[:3]]
        if block.notes:
            parts.append(block.notes)
        return cls._join(parts)

    @classmethod
    def _entry_summary(cls, entry: SetupDraftEntry) -> str | None:
        if entry.summary:
            return entry.summary
        for section in entry.sections:
            if section.retrieval_role == "summary":
                summary = cls._section_summary(section)
                if summary:
                    return summary
        return cls._join([entry.title, entry.semantic_path])

    @staticmethod
    def _section_summary(section: SetupDraftSection) -> str | None:
        content = section.content
        return (
            preview_text(content.get("text"))
            or preview_text(content.get("items"))
            or preview_text(content.get("values"))
            or preview_text(section.title)
        )

    @staticmethod
    def _legacy_summary(payload: dict[str, Any]) -> str | None:
        for key in ("summary", "description", "premise", "notes"):
            summary = preview_text(payload.get(key))
            if summary:
                return summary
        return preview_text(payload)

    @staticmethod
    def _model_payload(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _join(parts: list[str | None]) -> str | None:
        text = " | ".join(part for part in parts if part)
        return text or None
