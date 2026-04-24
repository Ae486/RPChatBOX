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
            metadata = dict(raw.get("metadata") or {})
            page_no, page_label = self._resolve_page_metadata(raw=raw, metadata=metadata)
            image_caption = self._resolve_image_caption(raw=raw, metadata=metadata)
            if page_no not in (None, "") and metadata.get("page_no") in (None, ""):
                metadata["page_no"] = page_no
            if page_label not in (None, "") and metadata.get("page_label") in (None, ""):
                metadata["page_label"] = page_label
            if image_caption not in (None, "") and metadata.get("image_caption") in (None, ""):
                metadata["image_caption"] = image_caption
            normalized.append(
                ParsedDocumentSection(
                    section_id=str(raw.get("section_id") or uuid4().hex),
                    title=str(raw.get("title")) if raw.get("title") is not None else None,
                    path=str(raw.get("path") or f"section.{index}"),
                    level=max(1, int(raw.get("level") or 1)),
                    text=text.strip(),
                    metadata=metadata,
                )
            )
        return normalized

    @staticmethod
    def _resolve_page_metadata(*, raw: dict[str, Any], metadata: dict[str, Any]) -> tuple[object | None, object | None]:
        raw_page = raw.get("page")
        metadata_page = metadata.get("page")
        page_no = Parser._first_non_empty(
            raw.get("page_no"),
            metadata.get("page_no"),
            Parser._read_mapping_value(raw_page, "no", "page_no", "page_number", "index"),
            Parser._read_mapping_value(metadata_page, "no", "page_no", "page_number", "index"),
        )
        page_label = Parser._first_non_empty(
            raw.get("page_label"),
            metadata.get("page_label"),
            Parser._read_mapping_value(raw_page, "label", "page_label", "display"),
            Parser._read_mapping_value(metadata_page, "label", "page_label", "display"),
        )
        return page_no, page_label

    @staticmethod
    def _resolve_image_caption(*, raw: dict[str, Any], metadata: dict[str, Any]) -> str | None:
        explicit = Parser._first_non_empty(
            raw.get("image_caption"),
            metadata.get("image_caption"),
            Parser._read_caption(raw.get("image")),
            Parser._read_caption(metadata.get("image")),
        )
        if explicit not in (None, ""):
            return str(explicit).strip() or None

        captions = Parser._collect_captions(raw.get("images"))
        captions.extend(Parser._collect_captions(metadata.get("images")))
        captions.extend(Parser._collect_captions(raw.get("figures")))
        captions.extend(Parser._collect_captions(metadata.get("figures")))
        deduped = list(dict.fromkeys(captions))
        if not deduped:
            return None
        return " | ".join(deduped[:2]).strip() or None

    @staticmethod
    def _collect_captions(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        captions: list[str] = []
        for item in value:
            caption = Parser._read_caption(item)
            if caption:
                captions.append(caption)
        return captions

    @staticmethod
    def _read_caption(value: Any) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        if isinstance(value, dict):
            for key in ("caption", "image_caption", "alt", "summary"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return None

    @staticmethod
    def _read_mapping_value(value: Any, *keys: str) -> Any:
        if not isinstance(value, dict):
            return None
        for key in keys:
            candidate = value.get(key)
            if candidate not in (None, ""):
                return candidate
        return None

    @staticmethod
    def _first_non_empty(*values: Any) -> Any:
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def render_payload_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if payload is None:
            return ""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
