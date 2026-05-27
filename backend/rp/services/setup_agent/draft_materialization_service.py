"""Materialize writer drafts into stable revision anchor blocks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import (
    DraftDocumentBlock,
    DraftDocumentBlockKind,
    DraftDocumentRecord,
    DraftDocumentSourceFormat,
)


MATERIALIZATION_VERSION = "draft-materialization.v1"
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


@dataclass(frozen=True)
class _ParsedBlock:
    kind: DraftDocumentBlockKind
    text: str
    start: int
    end: int
    metadata: dict[str, object]


class DraftMaterializationService:
    """Convert writer markdown/plain text into deterministic block anchors."""

    def materialize_draft(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        output_text: str,
        source_format: DraftDocumentSourceFormat,
        source_output_ref: str | None = None,
    ) -> DraftDocumentRecord:
        normalized_draft_ref = _require_non_blank(draft_ref, field_name="draft_ref")
        normalized_output_ref = (
            _require_non_blank(source_output_ref, field_name="source_output_ref")
            if source_output_ref is not None
            else normalized_draft_ref
        )
        blocks = (
            _parse_markdown(output_text)
            if source_format == "markdown"
            else _parse_plain_text(output_text)
        )
        document_blocks = [
            self._build_block(
                draft_ref=normalized_draft_ref,
                order=order,
                parsed=parsed,
                source_format=source_format,
            )
            for order, parsed in enumerate(blocks)
        ]
        return DraftDocumentRecord(
            draft_document_id=_stable_id(
                "draftdoc",
                normalized_draft_ref,
                source_format,
                _hash_text(output_text),
            ),
            turn_id=identity.turn_id,
            draft_ref=normalized_draft_ref,
            source_output_ref=normalized_output_ref,
            source_format=source_format,
            blocks=document_blocks,
            materialization_version=MATERIALIZATION_VERSION,
            created_at=datetime.now(timezone.utc),
            metadata_json={
                "story_id": identity.story_id,
                "session_id": identity.session_id,
                "branch_head_id": identity.branch_head_id,
                "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
                "block_count": len(document_blocks),
                "source_text_hash": _hash_text(output_text),
            },
        )

    def _build_block(
        self,
        *,
        draft_ref: str,
        order: int,
        parsed: _ParsedBlock,
        source_format: DraftDocumentSourceFormat,
    ) -> DraftDocumentBlock:
        normalized_text = _normalize_anchor_text(parsed.text)
        text_hash = _hash_text(normalized_text)
        source_range = {"start": parsed.start, "end": parsed.end}
        metadata = {
            **parsed.metadata,
            "source_format": source_format,
            "normalized_text_hash": text_hash,
            "anchor_strategy": "draft_ref_order_normalized_text_hash",
        }
        return DraftDocumentBlock(
            block_id=_stable_id("draftblk", draft_ref, str(order), text_hash),
            order=order,
            block_kind=parsed.kind,
            text=parsed.text,
            markdown_source_range=source_range if source_format == "markdown" else None,
            source_range=source_range,
            selected_excerpt=_excerpt(parsed.text),
            selected_excerpt_hash=_hash_text(_normalize_anchor_text(_excerpt(parsed.text))),
            metadata_json=metadata,
        )


def _parse_markdown(text: str) -> list[_ParsedBlock]:
    lines = _scan_lines(text)
    blocks: list[_ParsedBlock] = []
    paragraph_parts: list[str] = []
    paragraph_start: int | None = None
    paragraph_end = 0
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_parts, paragraph_start, paragraph_end
        if paragraph_start is None:
            return
        block_text = "\n".join(part.rstrip() for part in paragraph_parts).strip()
        if block_text:
            blocks.append(
                _ParsedBlock(
                    kind="paragraph",
                    text=block_text,
                    start=paragraph_start,
                    end=paragraph_end,
                    metadata={},
                )
            )
        paragraph_parts = []
        paragraph_start = None
        paragraph_end = 0

    while index < len(lines):
        line, start, end = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            flush_paragraph()
            fence_token = fence.group(1)
            code_lines = [line]
            code_start = start
            code_end = end
            index += 1
            while index < len(lines):
                next_line, _, next_end = lines[index]
                code_lines.append(next_line)
                code_end = next_end
                if next_line.strip().startswith(fence_token[:3]):
                    index += 1
                    break
                index += 1
            blocks.append(
                _ParsedBlock(
                    kind="code",
                    text="\n".join(code_lines).strip(),
                    start=code_start,
                    end=code_end,
                    metadata={"fence": fence_token[:3]},
                )
            )
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            blocks.append(
                _ParsedBlock(
                    kind="heading",
                    text=heading.group(2).strip(),
                    start=start,
                    end=end,
                    metadata={"heading_level": len(heading.group(1))},
                )
            )
            index += 1
            continue

        list_item = _LIST_ITEM_RE.match(line)
        if list_item:
            flush_paragraph()
            blocks.append(
                _ParsedBlock(
                    kind="list_item",
                    text=list_item.group(1).strip(),
                    start=start,
                    end=end,
                    metadata={},
                )
            )
            index += 1
            continue

        blockquote = _BLOCKQUOTE_RE.match(line)
        if blockquote:
            flush_paragraph()
            quote_parts = [blockquote.group(1)]
            quote_start = start
            quote_end = end
            index += 1
            while index < len(lines):
                next_line, _, next_end = lines[index]
                next_quote = _BLOCKQUOTE_RE.match(next_line)
                if next_quote is None:
                    break
                quote_parts.append(next_quote.group(1))
                quote_end = next_end
                index += 1
            blocks.append(
                _ParsedBlock(
                    kind="blockquote",
                    text="\n".join(part.rstrip() for part in quote_parts).strip(),
                    start=quote_start,
                    end=quote_end,
                    metadata={},
                )
            )
            continue

        if paragraph_start is None:
            paragraph_start = start
        paragraph_parts.append(line)
        paragraph_end = end
        index += 1

    flush_paragraph()
    return blocks or _unknown_block_for_empty_text(text)


def _parse_plain_text(text: str) -> list[_ParsedBlock]:
    lines = _scan_lines(text)
    blocks: list[_ParsedBlock] = []
    parts: list[str] = []
    block_start: int | None = None
    block_end = 0

    def flush() -> None:
        nonlocal parts, block_start, block_end
        if block_start is None:
            return
        block_text = "\n".join(part.rstrip() for part in parts).strip()
        if block_text:
            blocks.append(
                _ParsedBlock(
                    kind="paragraph",
                    text=block_text,
                    start=block_start,
                    end=block_end,
                    metadata={"fallback_parser": "blank_line_paragraphs"},
                )
            )
        parts = []
        block_start = None
        block_end = 0

    for line, start, end in lines:
        if not line.strip():
            flush()
            continue
        if block_start is None:
            block_start = start
        parts.append(line)
        block_end = end
    flush()
    return blocks or _unknown_block_for_empty_text(text)


def _scan_lines(text: str) -> list[tuple[str, int, int]]:
    if not text:
        return []
    lines: list[tuple[str, int, int]] = []
    cursor = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        start = cursor
        end = cursor + len(raw_line)
        lines.append((line, start, end))
        cursor = end
    if text and not text.endswith(("\n", "\r")) and not lines:
        lines.append((text, 0, len(text)))
    return lines


def _unknown_block_for_empty_text(text: str) -> list[_ParsedBlock]:
    stripped = text.strip()
    if not stripped:
        return []
    start = text.find(stripped)
    return [
        _ParsedBlock(
            kind="unknown",
            text=stripped,
            start=max(start, 0),
            end=max(start, 0) + len(stripped),
            metadata={"fallback_parser": "unknown"},
        )
    ]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_anchor_text(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


def _excerpt(text: str, *, max_chars: int = 160) -> str:
    normalized = " ".join(text.strip().split())
    return normalized[:max_chars]


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
