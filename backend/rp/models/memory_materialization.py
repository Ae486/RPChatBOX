"""Canonical metadata builders for RP memory materialization intake."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


RECALL_LAYER = "recall"
ARCHIVAL_LAYER = "archival"
LONGFORM_STORY_RUNTIME_SOURCE_FAMILY = "longform_story_runtime"
SETUP_SOURCE_FAMILY = "setup_source"
HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT = "heavy_regression.chapter_close"
SCENE_CLOSE_EVENT = "scene_close"
SETUP_COMMIT_IMPORT_EVENT = "setup.commit_ingest"

CHAPTER_SUMMARY_KIND = "chapter_summary"
ACCEPTED_STORY_SEGMENT_KIND = "accepted_story_segment"
CONTINUITY_NOTE_KIND = "continuity_note"
SCENE_TRANSCRIPT_KIND = "scene_transcript"
CHARACTER_LONG_HISTORY_SUMMARY_KIND = "character_long_history_summary"
RETIRED_FORESHADOW_SUMMARY_KIND = "retired_foreshadow_summary"
FOUNDATION_ENTRY_SOURCE_TYPE = "foundation_entry"
LONGFORM_BLUEPRINT_SOURCE_TYPE = "longform_blueprint"
IMPORTED_ASSET_SOURCE_TYPE = "imported_asset"


def build_recall_materialization_metadata(
    *,
    materialization_kind: str,
    materialization_event: str,
    session_id: str,
    chapter_index: int,
    domain_path: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical Recall metadata and prevent caller-owned override drift."""

    normalized_kind = _require_non_blank(
        materialization_kind,
        field_name="materialization_kind",
    )
    normalized_event = _require_non_blank(
        materialization_event,
        field_name="materialization_event",
    )
    normalized_session_id = _require_non_blank(session_id, field_name="session_id")
    normalized_domain_path = _require_non_blank(
        domain_path,
        field_name="domain_path",
    )
    if chapter_index <= 0:
        raise ValueError("chapter_index must be positive")

    metadata = dict(extra or {})
    metadata.update(
        {
            "layer": RECALL_LAYER,
            "source_family": LONGFORM_STORY_RUNTIME_SOURCE_FAMILY,
            "materialization_event": normalized_event,
            "materialization_kind": normalized_kind,
            "materialized_to_recall": True,
            "source_type": normalized_kind,
            "session_id": normalized_session_id,
            "chapter_index": chapter_index,
            "domain": "chapter",
            "domain_path": normalized_domain_path,
        }
    )
    return metadata


def build_recall_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
) -> dict[str, Any]:
    """Build one retrieval-core seed section with canonical Recall metadata."""

    normalized_tags = _normalize_tags(tags)
    return {
        "section_id": _require_non_blank(section_id, field_name="section_id"),
        "title": _require_non_blank(title, field_name="title"),
        "path": _require_non_blank(path, field_name="path"),
        "level": 1,
        "text": text,
        "metadata": {
            **dict(metadata),
            "tags": normalized_tags,
        },
    }


def build_archival_source_metadata(
    *,
    source_type: str,
    import_event: str,
    workspace_id: str,
    commit_id: str,
    step_id: str,
    source_ref: str,
    domain: str,
    domain_path: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical Archival metadata and keep ownership fields memory-owned."""

    normalized_source_type = _require_non_blank(source_type, field_name="source_type")
    normalized_import_event = _require_non_blank(
        import_event,
        field_name="import_event",
    )
    normalized_workspace_id = _require_non_blank(
        workspace_id,
        field_name="workspace_id",
    )
    normalized_commit_id = _require_non_blank(commit_id, field_name="commit_id")
    normalized_step_id = _require_non_blank(step_id, field_name="step_id")
    normalized_source_ref = _require_non_blank(source_ref, field_name="source_ref")
    normalized_domain = _require_non_blank(domain, field_name="domain")
    normalized_domain_path = _require_non_blank(
        domain_path,
        field_name="domain_path",
    )

    metadata = dict(extra or {})
    metadata.update(
        {
            "layer": ARCHIVAL_LAYER,
            "source_family": SETUP_SOURCE_FAMILY,
            "import_event": normalized_import_event,
            "source_type": normalized_source_type,
            "source_origin": "setup_workspace",
            "materialized_to_archival": True,
            "materialized_to_recall": False,
            "authoritative_mutation": False,
            "workspace_id": normalized_workspace_id,
            "commit_id": normalized_commit_id,
            "step_id": normalized_step_id,
            "source_ref": normalized_source_ref,
            "domain": normalized_domain,
            "domain_path": normalized_domain_path,
        }
    )
    return metadata


def build_archival_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
    level: int = 1,
) -> dict[str, Any]:
    """Build one retrieval-core seed section with canonical Archival metadata."""

    normalized_tags = _normalize_tags(tags)
    return {
        "section_id": _require_non_blank(section_id, field_name="section_id"),
        "title": _require_non_blank(title, field_name="title"),
        "path": _require_non_blank(path, field_name="path"),
        "level": max(1, int(level)),
        "text": text,
        "metadata": {
            **dict(metadata),
            "tags": normalized_tags,
        },
    }


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalize_tags(tags: Sequence[str]) -> list[str]:
    normalized_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tags.append(normalized)
    return normalized_tags
