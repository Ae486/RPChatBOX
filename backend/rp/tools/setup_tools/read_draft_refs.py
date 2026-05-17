"""Read-only setup tool handlers."""

from __future__ import annotations

from typing import Any, Literal
import json

from pydantic import BaseModel

from rp.agent_runtime.contracts import (
    SetupDraftRefReadInput,
    SetupDraftRefReadItem,
    SetupDraftRefReadResult,
)
from rp.models.setup_drafts import SetupStageDraftBlock
from rp.models.setup_stage import SetupStageId
from rp.tools.setup_tool_contracts import SetupToolContractError

from .base import SetupToolFamilyBase


class ReadDraftRefsTool(SetupToolFamilyBase):
    def _dispatch_read_draft_refs(
        self,
        input_model: SetupDraftRefReadInput,
    ) -> SetupDraftRefReadResult:
        return self._read_draft_refs(input_model=input_model)

    def _read_draft_refs(
        self,
        *,
        input_model: SetupDraftRefReadInput,
    ) -> SetupDraftRefReadResult:
        if not input_model.refs:
            raise SetupToolContractError(
                code="setup_draft_refs_required",
                message="setup.read.draft_refs requires at least one draft ref.",
                error_code="SETUP_DRAFT_REFS_REQUIRED",
                details=self._error_details(
                    tool_name="setup.read.draft_refs",
                    failure_origin="validation",
                    repair_strategy="auto_repair",
                    required_fields=["refs"],
                ),
            )

        workspace = self._require_workspace(input_model.workspace_id)
        max_chars = max(1, min(int(input_model.max_chars or 4000), 20000))
        items: list[SetupDraftRefReadItem] = []
        missing_refs: list[str] = []
        for raw_ref in input_model.refs:
            ref = str(raw_ref or "").strip()
            if not ref:
                continue
            item = self._resolve_draft_ref(
                workspace=workspace,
                ref=ref,
                detail=input_model.detail,
                max_chars=max_chars,
            )
            items.append(item)
            if not item.found:
                missing_refs.append(ref)
        return SetupDraftRefReadResult(
            success=not missing_refs,
            items=items,
            missing_refs=missing_refs,
        )

    def _resolve_draft_ref(
        self,
        *,
        workspace,
        ref: str,
        detail: str,
        max_chars: int,
    ) -> SetupDraftRefReadItem:
        if ref == "draft:story_config":
            return self._draft_ref_item(
                ref=ref,
                block_type="story_config",
                title="Story Config Draft",
                model=workspace.story_config_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref == "draft:writing_contract":
            return self._draft_ref_item(
                ref=ref,
                block_type="writing_contract",
                title="Writing Contract Draft",
                model=workspace.writing_contract_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref == "draft:longform_blueprint":
            return self._draft_ref_item(
                ref=ref,
                block_type="longform_blueprint",
                title="Longform Blueprint Draft",
                model=workspace.longform_blueprint_draft,
                detail=detail,
                max_chars=max_chars,
            )
        if ref.startswith("draft:"):
            stage_key = ref.removeprefix("draft:").strip()
            stage_id = self._coerce_stage_id(stage_key)
            if stage_id is not None:
                return self._stage_draft_ref(
                    workspace=workspace,
                    ref=ref,
                    stage_id=stage_id,
                    detail=detail,
                    max_chars=max_chars,
                )
        if ref.startswith("stage:"):
            parts = ref.split(":")
            if len(parts) >= 3:
                stage_id = self._coerce_stage_id(parts[1])
                if stage_id is not None:
                    if len(parts) == 3:
                        return self._stage_draft_ref(
                            workspace=workspace,
                            ref=ref,
                            stage_id=stage_id,
                            detail=detail,
                            max_chars=max_chars,
                            entry_id=parts[2],
                        )
                    if len(parts) >= 4:
                        return self._stage_draft_ref(
                            workspace=workspace,
                            ref=ref,
                            stage_id=stage_id,
                            detail=detail,
                            max_chars=max_chars,
                            entry_id=parts[2],
                            section_id=":".join(parts[3:]),
                        )
        if ref.startswith("foundation:"):
            entry_id = ref.removeprefix("foundation:").strip()
            foundation_draft = workspace.foundation_draft
            entry = None
            if foundation_draft is not None:
                entry = next(
                    (
                        item
                        for item in foundation_draft.entries
                        if item.entry_id == entry_id
                    ),
                    None,
                )
            return self._draft_ref_item(
                ref=ref,
                block_type="foundation_entry",
                title=(
                    (entry.title or entry.path or entry.entry_id)
                    if entry is not None
                    else None
                ),
                model=entry,
                detail=detail,
                max_chars=max_chars,
            )
        return SetupDraftRefReadItem(ref=ref, found=False)

    def _stage_draft_ref(
        self,
        *,
        workspace,
        ref: str,
        stage_id: SetupStageId,
        detail: str,
        max_chars: int,
        entry_id: str | None = None,
        section_id: str | None = None,
    ) -> SetupDraftRefReadItem:
        block = workspace.draft_blocks.get(stage_id.value)
        if block is None:
            return SetupDraftRefReadItem(
                ref=ref, found=False, block_type=stage_id.value
            )
        if entry_id is None:
            payload = block.model_dump(mode="json", exclude_none=True)
            return SetupDraftRefReadItem(
                ref=ref,
                found=True,
                block_type=stage_id.value,
                title=stage_id.value.replace("_", " ").title(),
                summary=self._stage_block_summary(block),
                payload=(
                    self._bounded_payload(payload=payload, max_chars=max_chars)
                    if detail == "full"
                    else None
                ),
            )
        entry = next(
            (item for item in block.entries if item.entry_id == entry_id), None
        )
        if entry is None:
            return SetupDraftRefReadItem(
                ref=ref, found=False, block_type=stage_id.value
            )
        if section_id is None:
            payload = entry.model_dump(mode="json", exclude_none=True)
            return SetupDraftRefReadItem(
                ref=ref,
                found=True,
                block_type=stage_id.value,
                title=entry.title,
                summary=self._stage_entry_summary(entry),
                payload=(
                    self._bounded_payload(payload=payload, max_chars=max_chars)
                    if detail == "full"
                    else None
                ),
            )
        section = next(
            (item for item in entry.sections if item.section_id == section_id), None
        )
        if section is None:
            return SetupDraftRefReadItem(
                ref=ref, found=False, block_type=stage_id.value
            )
        payload = section.model_dump(mode="json", exclude_none=True)
        return SetupDraftRefReadItem(
            ref=ref,
            found=True,
            block_type=stage_id.value,
            title=section.title,
            summary=self._stage_section_summary(section),
            payload=(
                self._bounded_payload(payload=payload, max_chars=max_chars)
                if detail == "full"
                else None
            ),
        )

    @staticmethod
    def _coerce_stage_id(value: str | None) -> SetupStageId | None:
        if not value:
            return None
        try:
            return SetupStageId(value)
        except ValueError:
            return None

    @classmethod
    def _stage_block_summary(cls, block: SetupStageDraftBlock) -> str:
        parts = [
            cls._stage_entry_summary(entry) or entry.title
            for entry in block.entries[:3]
        ]
        if block.notes:
            parts.append(block.notes)
        return cls._join_preview(parts)

    @classmethod
    def _stage_entry_summary(cls, entry) -> str:
        summary = cls._coerce_preview_text(entry.summary)
        if summary:
            return summary
        for section in entry.sections:
            if section.retrieval_role == "summary":
                section_summary = cls._stage_section_summary(section)
                if section_summary:
                    return section_summary
        return cls._join_preview(
            [
                cls._coerce_preview_text(entry.title),
                cls._coerce_preview_text(entry.semantic_path),
            ]
        )

    @classmethod
    def _stage_section_summary(cls, section) -> str | None:
        content = section.content
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            items = content.get("items")
            if isinstance(items, list):
                preview = cls._coerce_preview_text(items)
                if preview:
                    return preview
            values = content.get("values")
            if isinstance(values, dict):
                preview = cls._coerce_preview_text(values)
                if preview:
                    return preview
        return cls._coerce_preview_text(section.title)

    def _draft_ref_item(
        self,
        *,
        ref: str,
        block_type: Literal[
            "story_config",
            "writing_contract",
            "foundation_entry",
            "longform_blueprint",
        ],
        title: str | None,
        model: BaseModel | None,
        detail: str,
        max_chars: int,
    ) -> SetupDraftRefReadItem:
        if model is None:
            return SetupDraftRefReadItem(ref=ref, found=False, block_type=block_type)
        payload = model.model_dump(mode="json", exclude_none=True)
        return SetupDraftRefReadItem(
            ref=ref,
            found=True,
            block_type=block_type,
            title=title,
            summary=self._draft_ref_summary(block_type=block_type, payload=payload),
            payload=(
                self._bounded_payload(payload=payload, max_chars=max_chars)
                if detail == "full"
                else None
            ),
        )

    @classmethod
    def _draft_ref_summary(
        cls,
        *,
        block_type: str,
        payload: dict[str, Any],
    ) -> str:
        if block_type == "story_config":
            return cls._join_preview(
                [
                    cls._prefixed_preview("model", payload.get("model_profile_ref")),
                    cls._prefixed_preview("worker", payload.get("worker_profile_ref")),
                    cls._prefixed_preview(
                        "policy", payload.get("post_write_policy_preset")
                    ),
                    cls._coerce_preview_text(payload.get("notes")),
                ]
            )
        if block_type == "writing_contract":
            return cls._join_preview(
                [
                    cls._prefixed_preview("pov", payload.get("pov_rules")),
                    cls._prefixed_preview("style", payload.get("style_rules")),
                    cls._prefixed_preview(
                        "constraints", payload.get("writing_constraints")
                    ),
                    cls._coerce_preview_text(payload.get("notes")),
                ]
            )
        if block_type == "longform_blueprint":
            return cls._join_preview(
                [
                    cls._coerce_preview_text(payload.get("premise")),
                    cls._coerce_preview_text(payload.get("central_conflict")),
                    cls._coerce_preview_text(payload.get("chapter_strategy")),
                ]
            )
        content = payload.get("content")
        if isinstance(content, dict):
            for key in ("summary", "description", "premise"):
                preview = cls._coerce_preview_text(content.get(key))
                if preview:
                    return preview
            for value in content.values():
                preview = cls._coerce_preview_text(value)
                if preview:
                    return preview
        return cls._join_preview(
            [
                cls._coerce_preview_text(payload.get("title")),
                cls._coerce_preview_text(payload.get("path")),
            ]
        )

    @staticmethod
    def _bounded_payload(*, payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(raw) <= max_chars:
            return payload
        return {
            "_truncated": True,
            "preview": raw[:max_chars],
        }

    @classmethod
    def _prefixed_preview(cls, label: str, value: Any) -> str | None:
        preview = cls._coerce_preview_text(value)
        if not preview:
            return None
        return f"{label}: {preview}"

    @staticmethod
    def _coerce_preview_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(parts[:3]) if parts else None
        if isinstance(value, dict):
            parts = [str(item).strip() for item in value.values() if str(item).strip()]
            return ", ".join(parts[:3]) if parts else None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _join_preview(parts: list[str | None]) -> str:
        return " | ".join(part for part in parts if part)[:500]
