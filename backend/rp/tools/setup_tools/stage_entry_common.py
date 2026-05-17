"""Shared helpers for current-stage setup.stage_entry tools."""

from __future__ import annotations

from typing import Any, Literal
import hashlib
import json
import re

from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupDraftSectionKind,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.tools.setup_tool_contracts import (
    SetupStageEntryChangesInput,
    SetupStageEntrySectionInput,
    SetupToolContractError,
)

from .base import SetupToolFamilyBase


WRITABLE_STAGE_ENTRY_STAGES: tuple[SetupStageId, ...] = (
    SetupStageId.WORLD_BACKGROUND,
    SetupStageId.CHARACTER_DESIGN,
    SetupStageId.PLOT_BLUEPRINT,
)


class StageEntryToolBase(SetupToolFamilyBase):
    def _current_stage_entry_context(
        self,
        *,
        workspace_id: str,
        tool_name: str,
    ):
        workspace = self._require_workspace(workspace_id)
        stage_id = workspace.current_stage
        if stage_id not in WRITABLE_STAGE_ENTRY_STAGES:
            allowed = [stage.value for stage in WRITABLE_STAGE_ENTRY_STAGES]
            current = stage_id.value if stage_id is not None else None
            raise SetupToolContractError(
                code="stage_entry_stage_not_writable",
                message=(
                    "setup.stage_entry tools only write the current "
                    "world_background, character_design, or plot_blueprint stage."
                ),
                details=self._error_details(
                    tool_name=tool_name,
                    failure_origin="validation",
                    repair_strategy="continue_discussion",
                    extra={"current_stage": current, "allowed_stages": allowed},
                ),
            )
        block = workspace.draft_blocks.get(
            stage_id.value,
            SetupStageDraftBlock(stage_id=stage_id),
        )
        return workspace, stage_id, block

    def _require_stage_entry(
        self,
        *,
        block: SetupStageDraftBlock,
        current_stage: SetupStageId,
        target_ref: str,
        tool_name: str,
    ) -> SetupDraftEntry:
        entry_id = self._entry_id_from_stage_ref(
            target_ref=target_ref,
            current_stage=current_stage,
            tool_name=tool_name,
        )
        for entry in block.entries:
            if entry.entry_id == entry_id:
                return entry
        raise SetupToolContractError(
            code="stage_entry_not_found",
            message=f"Current-stage draft entry not found: {target_ref}",
            details=self._error_details(
                tool_name=tool_name,
                failure_origin="validation",
                repair_strategy="continue_discussion",
                required_fields=["target_ref"],
                extra={"current_stage": current_stage.value},
            ),
        )

    def _entry_id_from_stage_ref(
        self,
        *,
        target_ref: str,
        current_stage: SetupStageId,
        tool_name: str,
    ) -> str:
        prefix = "stage:"
        if not target_ref.startswith(prefix):
            self._raise_stage_ref_invalid(
                tool_name=tool_name,
                message=(
                    "target_ref must look like "
                    f"'stage:{current_stage.value}:<entry_id>'"
                ),
                current_stage=current_stage,
            )
        parts = target_ref.split(":")
        if len(parts) != 3:
            self._raise_stage_ref_invalid(
                tool_name=tool_name,
                message=(
                    "target_ref must be an entry ref exactly like "
                    f"'stage:{current_stage.value}:<entry_id>'; section refs are "
                    "not valid for setup.stage_entry tools"
                ),
                current_stage=current_stage,
            )
        ref_stage = parts[1].strip()
        entry_id = parts[2].strip()
        if ref_stage != current_stage.value:
            raise SetupToolContractError(
                code="stage_entry_target_stage_mismatch",
                message=(
                    "target_ref stage must match the workspace current stage; "
                    f"current={current_stage.value}, target={ref_stage or '<empty>'}"
                ),
                details=self._error_details(
                    tool_name=tool_name,
                    failure_origin="validation",
                    repair_strategy="read_current_state",
                    required_fields=["target_ref"],
                    extra={
                        "current_stage": current_stage.value,
                        "target_stage": ref_stage,
                    },
                ),
            )
        if not entry_id:
            self._raise_stage_ref_invalid(
                tool_name=tool_name,
                message="target_ref is missing entry_id",
                current_stage=current_stage,
            )
        return entry_id

    def _build_stage_entry(
        self,
        *,
        stage_id: SetupStageId,
        entry_id: str,
        entry_type: str,
        title: str,
        summary: str | None,
        sections: list[SetupStageEntrySectionInput],
        aliases: list[str],
        tags: list[str],
    ) -> SetupDraftEntry:
        type_key = self._normalize_key(entry_type)
        return SetupDraftEntry(
            entry_id=entry_id,
            entry_type=type_key,
            semantic_path=self._stage_entry_semantic_path(
                stage_id=stage_id,
                entry_type=type_key,
                entry_id=entry_id,
            ),
            title=title.strip(),
            summary=summary.strip()
            if isinstance(summary, str) and summary.strip()
            else None,
            aliases=self._dedupe_strings(aliases),
            tags=self._dedupe_strings([stage_id.value, type_key, *tags]),
            sections=self._stage_entry_sections(
                summary=summary,
                sections=sections,
            ),
        )

    def _apply_stage_entry_changes(
        self,
        *,
        stage_id: SetupStageId,
        entry: SetupDraftEntry,
        changes: SetupStageEntryChangesInput,
    ) -> SetupDraftEntry:
        entry_type = (
            self._normalize_key(changes.entry_type)
            if changes.entry_type is not None
            else entry.entry_type
        )
        title = changes.title if changes.title is not None else entry.title
        summary = changes.summary if changes.summary is not None else entry.summary
        return SetupDraftEntry(
            entry_id=entry.entry_id,
            entry_type=entry_type,
            semantic_path=self._stage_entry_semantic_path(
                stage_id=stage_id,
                entry_type=entry_type,
                entry_id=entry.entry_id,
            ),
            title=title,
            display_label=entry.display_label,
            summary=summary,
            aliases=self._remove_strings(
                self._dedupe_strings([*entry.aliases, *changes.add_aliases]),
                changes.remove_aliases,
            ),
            tags=self._remove_strings(
                self._dedupe_strings(
                    [*entry.tags, stage_id.value, entry_type, *changes.add_tags]
                ),
                changes.remove_tags,
            ),
            sections=self._patch_stage_entry_sections(
                existing=list(entry.sections),
                summary=summary,
                upsert_sections=changes.upsert_sections,
                remove_titles=changes.remove_section_titles,
            ),
        )

    def _stage_entry_sections(
        self,
        *,
        summary: str | None,
        sections: list[SetupStageEntrySectionInput],
    ) -> list[SetupDraftSection]:
        result: list[SetupDraftSection] = []
        used_ids: set[str] = set()
        if isinstance(summary, str) and summary.strip():
            result.append(
                SetupDraftSection(
                    section_id="summary",
                    title="Summary",
                    kind=SetupDraftSectionKind.TEXT,
                    content={"text": summary.strip()},
                    retrieval_role="summary",
                    tags=["summary"],
                )
            )
            used_ids.add("summary")
        for section_input in sections:
            section = self._section_input_to_draft_section(
                section_input=section_input,
                used_ids=used_ids,
            )
            result.append(section)
            used_ids.add(section.section_id)
        return result

    def _patch_stage_entry_sections(
        self,
        *,
        existing: list[SetupDraftSection],
        summary: str | None,
        upsert_sections: list[SetupStageEntrySectionInput],
        remove_titles: list[str],
    ) -> list[SetupDraftSection]:
        sections = {item.section_id: item for item in existing}
        for title in remove_titles:
            sections.pop(self._section_id_for_title(title), None)
        if isinstance(summary, str) and summary.strip():
            sections["summary"] = SetupDraftSection(
                section_id="summary",
                title="Summary",
                kind=SetupDraftSectionKind.TEXT,
                content={"text": summary.strip()},
                retrieval_role="summary",
                tags=["summary"],
            )
        for section_input in upsert_sections:
            section_id = self._section_id_for_title(section_input.title)
            section = self._section_input_to_draft_section(
                section_input=section_input,
                used_ids=set(sections) - {section_id},
            )
            sections[section.section_id] = section
        return list(sections.values())

    def _section_input_to_draft_section(
        self,
        *,
        section_input: SetupStageEntrySectionInput,
        used_ids: set[str],
    ) -> SetupDraftSection:
        section_id = self._unique_section_id(
            base=self._section_id_for_title(section_input.title),
            used_ids=used_ids,
        )
        return SetupDraftSection(
            section_id=section_id,
            title=section_input.title.strip(),
            kind=SetupDraftSectionKind.TEXT,
            content={"text": section_input.text.strip()},
            retrieval_role=section_input.retrieval_role
            or self._infer_retrieval_role(section_input.title),
            tags=self._dedupe_strings(section_input.tags),
        )

    def _require_entry_fingerprint(
        self,
        *,
        entry: SetupDraftEntry,
        basis_fingerprint: str,
        tool_name: str,
    ) -> None:
        current = self._entry_fingerprint(entry)
        if basis_fingerprint != current:
            raise SetupToolContractError(
                code="stage_entry_basis_fingerprint_mismatch",
                message=(
                    "Current-stage entry changed after it was read; "
                    "read it again before editing."
                ),
                details=self._error_details(
                    tool_name=tool_name,
                    failure_origin="validation",
                    repair_strategy="read_current_state",
                    required_fields=["basis_fingerprint"],
                    extra={"current_fingerprint": current},
                ),
            )

    @classmethod
    def _stage_entry_payload(
        cls,
        *,
        stage_id: SetupStageId,
        entry: SetupDraftEntry,
        include_sections: bool,
    ) -> dict[str, Any]:
        payload = entry.model_dump(mode="json", exclude_none=True)
        if not include_sections:
            payload.pop("sections", None)
        payload["target_ref"] = cls._stage_entry_ref(
            stage_id=stage_id,
            entry_id=entry.entry_id,
        )
        payload["basis_fingerprint"] = cls._entry_fingerprint(entry)
        return payload

    @staticmethod
    def _entry_fingerprint(entry: SetupDraftEntry) -> str:
        payload = json.dumps(
            entry.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _stage_entry_ref(*, stage_id: SetupStageId, entry_id: str) -> str:
        return f"stage:{stage_id.value}:{entry_id}"

    @staticmethod
    def _stage_entry_semantic_path(
        *,
        stage_id: SetupStageId,
        entry_type: str,
        entry_id: str,
    ) -> str:
        return f"{stage_id.value}.{entry_type}.{entry_id}"

    def _unique_stage_entry_id(
        self,
        *,
        block: SetupStageDraftBlock,
        entry_type: str,
        title: str,
    ) -> str:
        type_key = self._normalize_key(entry_type)
        title_slug = self._slugify(title)
        base = (
            f"{type_key}_{title_slug}"
            if title_slug
            else f"{type_key}_{self._hash_slug(title)}"
        )
        existing = {entry.entry_id for entry in block.entries}
        candidate = base
        index = 2
        while candidate in existing:
            candidate = f"{base}_{index}"
            index += 1
        return candidate

    @staticmethod
    def _entry_matches_query(entry: SetupDraftEntry, query: str) -> bool:
        haystack = " ".join(
            [
                entry.entry_id,
                entry.entry_type,
                entry.semantic_path,
                entry.title,
                entry.summary or "",
                " ".join(entry.aliases),
                " ".join(entry.tags),
            ]
        ).lower()
        return query in haystack

    @classmethod
    def _normalize_key(cls, value: str | None) -> str:
        return cls._slugify(value or "") or cls._hash_slug(value or "")

    @staticmethod
    def _slugify(value: str) -> str:
        text = value.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return re.sub(r"_+", "_", text).strip("_")

    @staticmethod
    def _hash_slug(value: str) -> str:
        return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]

    @staticmethod
    def _unique_section_id(*, base: str, used_ids: set[str]) -> str:
        section_id = base or "section"
        candidate = section_id
        index = 2
        while candidate in used_ids:
            candidate = f"{section_id}_{index}"
            index += 1
        return candidate

    @classmethod
    def _section_id_for_title(cls, title: str) -> str:
        return cls._slugify(title) or f"section_{cls._hash_slug(title)}"

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @classmethod
    def _remove_strings(cls, values: list[str], remove: list[str]) -> list[str]:
        removals = set(cls._dedupe_strings(remove))
        return [value for value in values if value not in removals]

    @staticmethod
    def _infer_retrieval_role(
        title: str,
    ) -> Literal["summary", "detail", "rule", "relationship", "note"]:
        text = title.lower()
        if "summary" in text or "概要" in text or "概述" in text:
            return "summary"
        if any(
            token in text for token in ("rule", "law", "taboo", "禁", "规则", "法律")
        ):
            return "rule"
        if any(token in text for token in ("relation", "relationship", "关系", "外交")):
            return "relationship"
        if "note" in text or "备注" in text:
            return "note"
        return "detail"

    def _raise_stage_ref_invalid(
        self,
        *,
        tool_name: str,
        message: str,
        current_stage: SetupStageId,
    ) -> None:
        raise SetupToolContractError(
            code="stage_entry_target_ref_invalid",
            message=message,
            details=self._error_details(
                tool_name=tool_name,
                failure_origin="validation",
                repair_strategy="auto_repair",
                required_fields=["target_ref"],
                extra={"current_stage": current_stage.value},
            ),
        )
