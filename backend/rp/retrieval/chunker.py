"""Chunk structured parsed documents into retrieval-ready chunks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from rp.models.retrieval_records import KnowledgeChunk, ParsedDocument

from .context_rendering import (
    build_context_header,
    build_contextual_text,
    format_page_reference,
    truncate_summary,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _ChunkSlice:
    text: str
    start_char: int
    end_char: int
    section_part: int
    parent_section_part: int
    view_part: int
    chunk_view: str
    chunk_size: str
    chunk_pass: int
    chunking_strategy: str


class Chunker:
    """Prefer section-aligned chunks and add a smaller secondary view when helpful."""

    def __init__(
        self,
        *,
        max_chars: int = 900,
        secondary_max_chars: int | None = None,
        secondary_overlap_chars: int = 120,
        secondary_trigger_chars: int | None = None,
    ) -> None:
        self._max_chars = max_chars
        if secondary_max_chars is None:
            secondary_max_chars = max_chars // 2 if max_chars >= 400 else max_chars
        self._secondary_max_chars = max(1, secondary_max_chars)
        self._secondary_overlap_chars = max(
            0,
            min(secondary_overlap_chars, max(0, self._secondary_max_chars - 1)),
        )
        self._secondary_trigger_chars = secondary_trigger_chars or max(
            self._secondary_max_chars + max(40, self._secondary_overlap_chars),
            int(self._secondary_max_chars * 1.25),
        )
        self._secondary_enabled = max_chars >= 400 and 0 < self._secondary_max_chars < max_chars

    def chunk(
        self,
        document: ParsedDocument,
        *,
        story_id: str,
        asset_id: str,
        collection_id: str | None = None,
        source_ref: str | None = None,
        commit_id: str | None = None,
        asset_title: str | None = None,
        asset_summary: str | None = None,
    ) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        created_at = _utcnow()
        chunk_index = 0
        document_title = self._document_title(document=document, asset_title=asset_title)
        document_summary = self._document_summary(
            document=document,
            asset_title=document_title,
            asset_summary=asset_summary,
        )

        for section in document.document_structure:
            for slice_item in self._iter_chunk_slices(section.text):
                metadata = dict(section.metadata)
                metadata["title"] = section.title
                metadata["domain"] = str(metadata.get("domain") or "world_rule")
                metadata["domain_path"] = str(metadata.get("domain_path") or section.path)
                metadata["section_id"] = section.section_id
                metadata["section_part"] = slice_item.section_part
                metadata["parent_section_part"] = slice_item.parent_section_part
                metadata["view_part"] = slice_item.view_part
                metadata["chunk_view"] = slice_item.chunk_view
                metadata["chunk_size"] = slice_item.chunk_size
                metadata["chunk_pass"] = slice_item.chunk_pass
                metadata["chunking_strategy"] = slice_item.chunking_strategy
                metadata["chunk_view_priority"] = 0 if slice_item.chunk_view == "primary" else 1
                metadata["chunk_family_id"] = f"{section.section_id}:{slice_item.parent_section_part}"
                metadata["char_start"] = slice_item.start_char
                metadata["char_end"] = slice_item.end_char
                metadata["source_ref"] = source_ref
                metadata["commit_id"] = commit_id
                metadata["document_title"] = document_title
                metadata["document_summary"] = document_summary
                metadata["page_ref"] = format_page_reference(
                    page_no=metadata.get("page_no"),
                    page_label=metadata.get("page_label"),
                )
                metadata["context_header"] = build_context_header(
                    document_title=document_title,
                    section_title=section.title,
                    domain_path=str(metadata["domain_path"]),
                )
                metadata["contextual_text_version"] = (
                    "v2"
                    if any(metadata.get(field_name) not in (None, "") for field_name in ("page_no", "page_label", "image_caption"))
                    else "v1"
                )
                metadata["contextual_text"] = build_contextual_text(
                    context_header=str(metadata["context_header"] or "") or None,
                    document_summary=document_summary,
                    chunk_text=slice_item.text,
                    page_no=metadata.get("page_no"),
                    page_label=metadata.get("page_label"),
                    image_caption=str(metadata.get("image_caption") or "") or None,
                )
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"chunk_{uuid4().hex}",
                        story_id=story_id,
                        asset_id=asset_id,
                        parsed_document_id=document.parsed_document_id,
                        collection_id=collection_id,
                        chunk_index=chunk_index,
                        domain=str(metadata["domain"]),
                        domain_path=str(metadata["domain_path"]),
                        title=section.title,
                        text=slice_item.text,
                        token_count=self._estimate_token_count(slice_item.text),
                        is_active=True,
                        metadata=metadata,
                        provenance_refs=[],
                        created_at=created_at,
                    )
                )
                chunk_index += 1

        return chunks

    def _iter_chunk_slices(self, text: str) -> list[_ChunkSlice]:
        primary_slices = self._split_primary_text(text)
        if not primary_slices:
            return []

        slices = list(primary_slices)
        if not self._secondary_enabled:
            return slices

        for primary_slice in primary_slices:
            slices.extend(self._split_secondary_text(primary_slice))
        return slices

    @staticmethod
    def _document_title(*, document: ParsedDocument, asset_title: str | None) -> str | None:
        if asset_title and asset_title.strip():
            return asset_title.strip()
        for section in document.document_structure:
            if section.title and section.title.strip():
                return section.title.strip()
        return None

    @staticmethod
    def _document_summary(
        *,
        document: ParsedDocument,
        asset_title: str | None,
        asset_summary: str | None,
    ) -> str | None:
        normalized_asset_summary = truncate_summary(asset_summary)
        if normalized_asset_summary:
            return normalized_asset_summary

        section_titles = [
            section.title.strip()
            for section in document.document_structure
            if section.title and section.title.strip()
        ]
        if section_titles:
            prefix = f"{asset_title}: " if asset_title else ""
            summary = prefix + " | ".join(section_titles[:3])
            return truncate_summary(summary)

        for section in document.document_structure:
            text = section.text.strip()
            if text:
                return truncate_summary(text)
        return asset_title

    def _split_primary_text(self, text: str) -> list[_ChunkSlice]:
        stripped = text.strip()
        if not stripped:
            return []
        if len(stripped) <= self._max_chars:
            return [
                _ChunkSlice(
                    text=stripped,
                    start_char=0,
                    end_char=len(stripped),
                    section_part=0,
                    parent_section_part=0,
                    view_part=0,
                    chunk_view="primary",
                    chunk_size="default",
                    chunk_pass=0,
                    chunking_strategy="section_aligned",
                )
            ]

        parts: list[_ChunkSlice] = []
        current = ""
        current_start = 0
        normalized_cursor = 0
        for paragraph in (item.strip() for item in stripped.splitlines()):
            if not paragraph:
                continue
            paragraph_start = normalized_cursor
            paragraph_end = paragraph_start + len(paragraph)
            if not current:
                current = paragraph
                current_start = paragraph_start
                normalized_cursor = paragraph_end + 1
                continue
            candidate = f"{current}\n{paragraph}"
            if len(candidate) <= self._max_chars:
                current = candidate
                normalized_cursor = paragraph_end + 1
                continue
            parts.append(
                _ChunkSlice(
                    text=current,
                    start_char=current_start,
                    end_char=current_start + len(current),
                    section_part=len(parts),
                    parent_section_part=len(parts),
                    view_part=len(parts),
                    chunk_view="primary",
                    chunk_size="default",
                    chunk_pass=0,
                    chunking_strategy="section_aligned",
                )
            )
            current = paragraph
            current_start = paragraph_start
            normalized_cursor = paragraph_end + 1
        if current:
            parts.append(
                _ChunkSlice(
                    text=current,
                    start_char=current_start,
                    end_char=current_start + len(current),
                    section_part=len(parts),
                    parent_section_part=len(parts),
                    view_part=len(parts),
                    chunk_view="primary",
                    chunk_size="default",
                    chunk_pass=0,
                    chunking_strategy="section_aligned",
                )
            )
        if parts:
            return self._normalize_primary_slices(parts)

        return self._fixed_primary_slices(stripped, start_char=0, start_index=0)

    def _split_secondary_text(self, primary_slice: _ChunkSlice) -> list[_ChunkSlice]:
        if len(primary_slice.text) <= self._secondary_trigger_chars:
            return []

        step = self._secondary_max_chars - self._secondary_overlap_chars
        if step <= 0:
            return []

        secondary_slices: list[_ChunkSlice] = []
        start = 0
        while start < len(primary_slice.text):
            end = min(len(primary_slice.text), start + self._secondary_max_chars)
            window_text = primary_slice.text[start:end].strip()
            if window_text:
                leading_trim = len(primary_slice.text[start:end]) - len(primary_slice.text[start:end].lstrip())
                normalized_start = primary_slice.start_char + start + leading_trim
                normalized_end = normalized_start + len(window_text)
                if window_text != primary_slice.text:
                    secondary_slices.append(
                        _ChunkSlice(
                            text=window_text,
                            start_char=normalized_start,
                            end_char=normalized_end,
                            section_part=primary_slice.section_part,
                            parent_section_part=primary_slice.section_part,
                            view_part=len(secondary_slices),
                            chunk_view="secondary",
                            chunk_size="small",
                            chunk_pass=1,
                            chunking_strategy="sliding_window",
                        )
                    )
            if end >= len(primary_slice.text):
                break
            start += step

        return secondary_slices

    def _normalize_primary_slices(self, slices: list[_ChunkSlice]) -> list[_ChunkSlice]:
        normalized: list[_ChunkSlice] = []
        for slice_item in slices:
            if len(slice_item.text) <= self._max_chars:
                normalized.append(
                    _ChunkSlice(
                        text=slice_item.text,
                        start_char=slice_item.start_char,
                        end_char=slice_item.end_char,
                        section_part=len(normalized),
                        parent_section_part=len(normalized),
                        view_part=len(normalized),
                        chunk_view="primary",
                        chunk_size="default",
                        chunk_pass=0,
                        chunking_strategy=slice_item.chunking_strategy,
                    )
                )
                continue
            normalized.extend(
                self._fixed_primary_slices(
                    slice_item.text,
                    start_char=slice_item.start_char,
                    start_index=len(normalized),
                )
            )
        return normalized

    def _fixed_primary_slices(
        self,
        text: str,
        *,
        start_char: int,
        start_index: int,
    ) -> list[_ChunkSlice]:
        parts: list[_ChunkSlice] = []
        for offset, start in enumerate(range(0, len(text), self._max_chars)):
            end = min(len(text), start + self._max_chars)
            part_index = start_index + offset
            parts.append(
                _ChunkSlice(
                    text=text[start:end],
                    start_char=start_char + start,
                    end_char=start_char + end,
                    section_part=part_index,
                    parent_section_part=part_index,
                    view_part=part_index,
                    chunk_view="primary",
                    chunk_size="default",
                    chunk_pass=0,
                    chunking_strategy="fixed_slice",
                )
            )
        return parts

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        return max(1, len(text.split()))
