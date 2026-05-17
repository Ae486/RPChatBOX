"""Exact readback for SetupAgent session memory refs."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rp.agent_runtime.contracts import SetupDraftRefReadInput, SetupDraftRefReadResult
from rp.services.setup_truth_index_service import SetupTruthIndexService

from .contracts import (
    SetupSessionMemoryManifest,
    SetupSessionMemoryManifestItem,
    SetupSessionMemoryContentBlock,
    SetupSessionMemoryOpenResult,
    SetupSessionMemoryReadItem,
    SetupSessionMemoryReadResult,
    SetupSessionMemorySectionIndexItem,
)
from .sources import preview_text


DraftRefReader = Callable[[SetupDraftRefReadInput], SetupDraftRefReadResult]


class SetupSessionMemoryReader:
    """Dispatch read_refs to the current authoritative source by manifest metadata."""

    def __init__(
        self,
        *,
        draft_ref_reader: DraftRefReader,
        truth_index_service: SetupTruthIndexService | None = None,
    ) -> None:
        self._draft_ref_reader = draft_ref_reader
        self._truth_index_service = truth_index_service or SetupTruthIndexService()

    def read_refs(
        self,
        *,
        workspace,
        manifest: SetupSessionMemoryManifest,
        refs: list[str],
        detail: str = "summary",
        max_chars: int = 4000,
    ) -> SetupSessionMemoryReadResult:
        bounded_chars = max(1, min(int(max_chars or 4000), 20000))
        item_by_ref = {item.ref: item for item in manifest.items}
        items: list[SetupSessionMemoryReadItem] = []
        missing: list[str] = []
        for raw_ref in refs:
            ref = str(raw_ref or "").strip()
            if not ref:
                continue
            manifest_item = item_by_ref.get(ref)
            if manifest_item is None:
                items.append(SetupSessionMemoryReadItem(ref=ref, found=False))
                missing.append(ref)
                continue
            read_item = self._read_one(
                workspace=workspace,
                manifest_item=manifest_item,
                detail=detail,
                max_chars=bounded_chars,
            )
            items.append(read_item)
            if not read_item.found:
                missing.append(ref)
        return SetupSessionMemoryReadResult(
            success=not missing,
            items=items,
            missing_refs=missing,
        )

    def open_ref(
        self,
        *,
        workspace,
        manifest: SetupSessionMemoryManifest,
        ref: str,
        max_chars: int = 4000,
    ) -> SetupSessionMemoryOpenResult:
        opened_ref = str(ref or "").strip()
        if not opened_ref:
            return self._open_error(
                ref=opened_ref,
                message="setup.memory.open requires one non-empty ref.",
            )
        item_by_ref = {item.ref: item for item in manifest.items}
        manifest_item = item_by_ref.get(opened_ref)
        if manifest_item is None:
            return self._open_error(
                ref=opened_ref,
                message=(
                    "未找到该 ref。请先使用 setup.memory.search 定位可打开的三级"
                    " entry ref 或四级 section ref。"
                ),
            )
        if manifest_item.ref_kind == "setup_fact_entry":
            sections = self._section_index_items(manifest=manifest, entry=manifest_item)
            return SetupSessionMemoryOpenResult(
                success=True,
                result_type="index",
                opened_ref=manifest_item.ref,
                opened_path=self._display_path(manifest_item),
                message=(
                    "当前打开的是三级条目索引，以下是该条目下的四级目录。"
                    "需要查看具体内容时，请继续 open 某个四级 ref。"
                ),
                sections=sections,
            )
        if manifest_item.ref_kind == "setup_fact_section":
            bounded_chars = max(1, min(int(max_chars or 4000), 20000))
            read_result = self.read_refs(
                workspace=workspace,
                manifest=manifest,
                refs=[manifest_item.ref],
                detail="full",
                max_chars=20000,
            )
            if not read_result.items or not read_result.items[0].found:
                return self._open_error(
                    ref=manifest_item.ref,
                    message="该 ref 存在于索引中，但当前来源已无法读取。请重新 search。",
                )
            read_item = read_result.items[0]
            content, content_truncated = self._clean_content_block(
                title=read_item.title or manifest_item.title,
                payload=read_item.payload,
                max_chars=bounded_chars,
            )
            return SetupSessionMemoryOpenResult(
                success=True,
                result_type="content",
                opened_ref=manifest_item.ref,
                opened_path=self._display_path(manifest_item),
                message="当前打开的是四级内容节点，以下内容可作为回答或写入草稿的事实依据。",
                content=content,
                truncated=bool(read_item.truncated or content_truncated),
            )
        return self._open_error(
            ref=manifest_item.ref,
            message="setup.memory.open 只支持三级 entry ref 或四级 section ref。",
        )

    def _read_one(
        self,
        *,
        workspace,
        manifest_item: SetupSessionMemoryManifestItem,
        detail: str,
        max_chars: int,
    ) -> SetupSessionMemoryReadItem:
        if manifest_item.source_kind == "editable_draft":
            return self._read_editable_draft(
                workspace=workspace,
                manifest_item=manifest_item,
                detail=detail,
                max_chars=max_chars,
            )
        if manifest_item.source_kind == "accepted_truth":
            return self._read_accepted_truth(
                workspace=workspace,
                manifest_item=manifest_item,
                detail=detail,
                max_chars=max_chars,
            )
        return self._read_metadata_source(
            manifest_item=manifest_item,
            detail=detail,
            max_chars=max_chars,
        )

    def _read_editable_draft(
        self,
        *,
        workspace,
        manifest_item: SetupSessionMemoryManifestItem,
        detail: str,
        max_chars: int,
    ) -> SetupSessionMemoryReadItem:
        result = self._draft_ref_reader(
            SetupDraftRefReadInput(
                workspace_id=workspace.workspace_id,
                step_id=workspace.current_step,
                stage_id=workspace.current_stage,
                refs=[manifest_item.ref],
                detail=detail,
                max_chars=max_chars,
            )
        )
        if not result.items or not result.items[0].found:
            return self._missing_from_manifest(manifest_item)
        item = result.items[0]
        payload, truncated = self._cap_payload(item.payload, max_chars=max_chars)
        return SetupSessionMemoryReadItem(
            ref=manifest_item.ref,
            found=True,
            source_kind=manifest_item.source_kind,
            ref_kind=manifest_item.ref_kind,
            title=item.title or manifest_item.title,
            summary=item.summary or manifest_item.summary,
            stage=manifest_item.stage,
            block_type=item.block_type or manifest_item.block_type,
            payload=payload if detail == "full" else None,
            truncated=truncated,
        )

    def _read_accepted_truth(
        self,
        *,
        workspace,
        manifest_item: SetupSessionMemoryManifestItem,
        detail: str,
        max_chars: int,
    ) -> SetupSessionMemoryReadItem:
        result = self._truth_index_service.read_refs(
            workspace=workspace,
            refs=[manifest_item.ref],
            detail=detail,
            max_chars=max_chars,
        )
        if not result.items or not result.items[0].found:
            return self._missing_from_manifest(manifest_item)
        item = result.items[0]
        payload, truncated = self._cap_payload(item.payload, max_chars=max_chars)
        return SetupSessionMemoryReadItem(
            ref=manifest_item.ref,
            found=True,
            source_kind=manifest_item.source_kind,
            ref_kind=manifest_item.ref_kind,
            title=item.title or manifest_item.title,
            summary=item.summary or manifest_item.summary,
            stage=item.stage_id.value
            if item.stage_id is not None
            else manifest_item.stage,
            block_type=manifest_item.block_type,
            payload=payload if detail == "full" else None,
            truncated=bool(item.truncated or truncated),
        )

    def _read_metadata_source(
        self,
        *,
        manifest_item: SetupSessionMemoryManifestItem,
        detail: str,
        max_chars: int,
    ) -> SetupSessionMemoryReadItem:
        payload, truncated = self._cap_payload(
            manifest_item.metadata, max_chars=max_chars
        )
        return SetupSessionMemoryReadItem(
            ref=manifest_item.ref,
            found=True,
            source_kind=manifest_item.source_kind,
            ref_kind=manifest_item.ref_kind,
            title=manifest_item.title,
            summary=manifest_item.summary,
            stage=manifest_item.stage,
            block_type=manifest_item.block_type,
            payload=payload if detail == "full" else None,
            truncated=truncated,
        )

    @staticmethod
    def _missing_from_manifest(
        manifest_item: SetupSessionMemoryManifestItem,
    ) -> SetupSessionMemoryReadItem:
        return SetupSessionMemoryReadItem(
            ref=manifest_item.ref,
            found=False,
            source_kind=manifest_item.source_kind,
            ref_kind=manifest_item.ref_kind,
            stage=manifest_item.stage,
            block_type=manifest_item.block_type,
        )

    @staticmethod
    def _cap_payload(
        payload: dict[str, Any] | None,
        *,
        max_chars: int,
    ) -> tuple[dict[str, Any] | None, bool]:
        if payload is None:
            return None, False
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(raw) <= max_chars:
            return payload, False
        return {"_truncated": True, "preview": raw[:max_chars]}, True

    @classmethod
    def _section_index_items(
        cls,
        *,
        manifest: SetupSessionMemoryManifest,
        entry: SetupSessionMemoryManifestItem,
    ) -> list[SetupSessionMemorySectionIndexItem]:
        entry_id = str(entry.metadata.get("entry_id") or "").strip()
        sections: list[SetupSessionMemorySectionIndexItem] = []
        for item in manifest.items:
            if item.ref_kind != "setup_fact_section":
                continue
            if item.source_kind != entry.source_kind:
                continue
            if str(item.stage or "") != str(entry.stage or ""):
                continue
            if str(item.metadata.get("entry_id") or "").strip() != entry_id:
                continue
            sections.append(
                SetupSessionMemorySectionIndexItem(
                    ref=item.ref,
                    path=cls._display_path(item),
                    title=item.title,
                    navigation_summary=preview_text(item.summary, max_chars=500),
                )
            )
        return sorted(sections, key=lambda item: item.ref)

    @staticmethod
    def _display_path(item: SetupSessionMemoryManifestItem) -> str | None:
        semantic_path = str(item.metadata.get("semantic_path") or "").strip()
        if semantic_path:
            return " / ".join(part for part in semantic_path.split(".") if part)
        parts = [item.stage, item.block_type, item.title]
        text = " / ".join(str(part) for part in parts if str(part or "").strip())
        return text or None

    @classmethod
    def _clean_content_block(
        cls,
        *,
        title: str | None,
        payload: dict[str, Any] | None,
        max_chars: int,
    ) -> tuple[SetupSessionMemoryContentBlock, bool]:
        bounded_chars = max(1, min(int(max_chars or 4000), 20000))
        if not payload:
            return SetupSessionMemoryContentBlock(type="unknown", title=title), False
        if payload.get("_truncated"):
            return (
                SetupSessionMemoryContentBlock(
                    type="truncated",
                    title=title,
                    preview=(
                        "Content exceeded the clean open limit. Open a narrower "
                        "section or increase max_chars."
                    ),
                ),
                True,
            )
        content = payload.get("content")
        section_title = str(payload.get("title") or title or "").strip() or None
        kind = str(payload.get("kind") or "").strip()
        if isinstance(content, dict):
            if kind == "text" or isinstance(content.get("text"), str):
                text, truncated = cls._bounded_text(
                    str(content.get("text") or ""),
                    max_chars=bounded_chars,
                )
                return SetupSessionMemoryContentBlock(
                    type="text",
                    title=section_title,
                    text=text,
                ), truncated
            if kind == "list" or isinstance(content.get("items"), list):
                items = list(content.get("items") or [])
                if cls._json_size(items) > bounded_chars:
                    return (
                        SetupSessionMemoryContentBlock(
                            type="truncated",
                            title=section_title,
                            preview=cls._bounded_json_preview(
                                items,
                                max_chars=bounded_chars,
                            ),
                        ),
                        True,
                    )
                return SetupSessionMemoryContentBlock(
                    type="list",
                    title=section_title,
                    items=items,
                ), False
            if kind == "key_value" or isinstance(content.get("values"), dict):
                values = dict(content.get("values") or {})
                if cls._json_size(values) > bounded_chars:
                    return (
                        SetupSessionMemoryContentBlock(
                            type="truncated",
                            title=section_title,
                            preview=cls._bounded_json_preview(
                                values,
                                max_chars=bounded_chars,
                            ),
                        ),
                        True,
                    )
                return SetupSessionMemoryContentBlock(
                    type="key_value",
                    title=section_title,
                    values=values,
                ), False
        preview, truncated = cls._bounded_preview_value(
            content if content is not None else payload.get("summary"),
            max_chars=bounded_chars,
        )
        return SetupSessionMemoryContentBlock(
            type="unknown",
            title=section_title,
            preview=preview,
        ), truncated

    @staticmethod
    def _bounded_text(text: str, *, max_chars: int) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True

    @classmethod
    def _bounded_preview_value(cls, value: Any, *, max_chars: int) -> tuple[str, bool]:
        if value is None:
            return "", False
        if isinstance(value, str):
            return cls._bounded_text(value, max_chars=max_chars)
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if len(raw) <= max_chars:
            return raw, False
        return raw[:max_chars], True

    @staticmethod
    def _bounded_json_preview(value: Any, *, max_chars: int) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return raw[:max_chars]

    @staticmethod
    def _json_size(value: Any) -> int:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _open_error(*, ref: str, message: str) -> SetupSessionMemoryOpenResult:
        return SetupSessionMemoryOpenResult(
            success=False,
            result_type="error",
            opened_ref=ref,
            message=message,
        )
