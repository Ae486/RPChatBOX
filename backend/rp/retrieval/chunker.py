"""Chunk structured parsed documents into retrieval-ready chunks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from rp.models.retrieval_records import KnowledgeChunk, ParsedDocument


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Chunker:
    """Prefer section-aligned chunks and split only when sections are too large."""

    def __init__(self, *, max_chars: int = 900) -> None:
        self._max_chars = max_chars

    def chunk(
        self,
        document: ParsedDocument,
        *,
        story_id: str,
        asset_id: str,
        collection_id: str | None = None,
    ) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        created_at = _utcnow()
        chunk_index = 0

        for section in document.document_structure:
            for part_index, text in enumerate(self._split_text(section.text)):
                metadata = dict(section.metadata)
                metadata["section_id"] = section.section_id
                if part_index:
                    metadata["section_part"] = part_index
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"chunk_{uuid4().hex}",
                        story_id=story_id,
                        asset_id=asset_id,
                        parsed_document_id=document.parsed_document_id,
                        collection_id=collection_id,
                        chunk_index=chunk_index,
                        domain=str(metadata.get("domain") or "world_rule"),
                        domain_path=str(metadata.get("domain_path") or section.path),
                        title=section.title,
                        text=text,
                        token_count=self._estimate_token_count(text),
                        is_active=True,
                        metadata=metadata,
                        provenance_refs=[],
                        created_at=created_at,
                    )
                )
                chunk_index += 1

        return chunks

    def _split_text(self, text: str) -> Iterable[str]:
        stripped = text.strip()
        if len(stripped) <= self._max_chars:
            return [stripped]

        parts: list[str] = []
        current = ""
        for paragraph in (item.strip() for item in stripped.splitlines()):
            if not paragraph:
                continue
            if not current:
                current = paragraph
                continue
            candidate = f"{current}\n{paragraph}"
            if len(candidate) <= self._max_chars:
                current = candidate
                continue
            parts.append(current)
            current = paragraph
        if current:
            parts.append(current)
        if parts:
            return parts
        return [stripped[i : i + self._max_chars] for i in range(0, len(stripped), self._max_chars)]

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        return max(1, len(text.split()))
