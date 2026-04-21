"""Structured parser for retrieval ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from rp.models.retrieval_records import ParsedDocument, ParsedDocumentSection, SourceAsset


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Parser:
    """Prefer setup-seeded structure and only fall back to raw text parsing."""

    def parse(self, asset: SourceAsset) -> ParsedDocument:
        parser_kind = "fallback"
        structure: list[ParsedDocumentSection] = []
        warnings: list[str] = []

        seed_sections = asset.metadata.get("seed_sections")
        if isinstance(seed_sections, list) and seed_sections:
            parser_kind = "seed_sections"
            structure = self._normalize_sections(seed_sections)
        else:
            payload_sections = self._sections_from_parsed_payload(asset.metadata.get("parsed_payload"))
            if payload_sections:
                parser_kind = "structured_payload"
                structure = payload_sections

        if not structure and asset.storage_path:
            storage_path = Path(asset.storage_path)
            if storage_path.exists():
                try:
                    structure = [
                        ParsedDocumentSection(
                            section_id=f"{asset.asset_id}:raw",
                            title=asset.title,
                            path=asset.source_ref,
                            level=1,
                            text=storage_path.read_text(encoding="utf-8", errors="ignore"),
                            metadata={
                                "domain": asset.metadata.get("domain") or "world_rule",
                                "domain_path": asset.metadata.get("domain_path") or asset.source_ref,
                                "source": "storage_path",
                            },
                        )
                    ]
                    parser_kind = "raw_file"
                except OSError as exc:
                    warnings.append(f"raw_file_read_failed:{exc}")

        if not structure:
            fallback_text = asset.raw_excerpt or asset.title or asset.source_ref
            structure = [
                ParsedDocumentSection(
                    section_id=f"{asset.asset_id}:fallback",
                    title=asset.title,
                    path=asset.source_ref,
                    level=1,
                    text=fallback_text,
                    metadata={
                        "domain": asset.metadata.get("domain") or "world_rule",
                        "domain_path": asset.metadata.get("domain_path") or asset.source_ref,
                        "source": "fallback",
                    },
                )
            ]

        now = _utcnow()
        return ParsedDocument(
            parsed_document_id=f"pd_{asset.asset_id}_{uuid4().hex[:8]}",
            asset_id=asset.asset_id,
            parser_kind=parser_kind,
            document_structure=structure,
            parse_warnings=warnings,
            created_at=now,
            updated_at=now,
        )

    def _sections_from_parsed_payload(self, payload: Any) -> list[ParsedDocumentSection]:
        if not isinstance(payload, dict):
            return []
        sections = payload.get("sections")
        if not isinstance(sections, list):
            return []
        return self._normalize_sections(sections)

    def _normalize_sections(self, sections: list[Any]) -> list[ParsedDocumentSection]:
        normalized: list[ParsedDocumentSection] = []
        for index, raw in enumerate(sections):
            if not isinstance(raw, dict):
                continue
            text = raw.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            normalized.append(
                ParsedDocumentSection(
                    section_id=str(raw.get("section_id") or uuid4().hex),
                    title=str(raw.get("title")) if raw.get("title") is not None else None,
                    path=str(raw.get("path") or f"section.{index}"),
                    level=max(1, int(raw.get("level") or 1)),
                    text=text.strip(),
                    metadata=dict(raw.get("metadata") or {}),
                )
            )
        return normalized

    @staticmethod
    def render_payload_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if payload is None:
            return ""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
