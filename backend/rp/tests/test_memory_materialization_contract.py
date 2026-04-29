"""Tests for canonical memory materialization intake metadata."""

from __future__ import annotations

from typing import Any

import pytest

from rp.models.memory_materialization import (
    CONTINUITY_NOTE_KIND,
    FOUNDATION_ENTRY_SOURCE_TYPE,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    SETUP_COMMIT_IMPORT_EVENT,
    build_archival_seed_section,
    build_archival_source_metadata,
    build_recall_materialization_metadata,
    build_recall_seed_section,
)


def test_build_recall_materialization_metadata_generates_canonical_fields():
    metadata = build_recall_materialization_metadata(
        materialization_kind=CONTINUITY_NOTE_KIND,
        materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
        session_id="session-1",
        chapter_index=2,
        domain_path="recall.chapter.2.continuity_note.note-1",
        extra={
            "note_index": 0,
            "layer": "runtime_workspace",
            "source_family": "wrong_source",
            "materialized_to_recall": False,
            "source_type": "wrong_type",
            "domain": "wrong_domain",
        },
    )

    assert metadata == {
        "note_index": 0,
        "layer": "recall",
        "source_family": "longform_story_runtime",
        "materialization_event": "heavy_regression.chapter_close",
        "materialization_kind": "continuity_note",
        "materialized_to_recall": True,
        "source_type": "continuity_note",
        "session_id": "session-1",
        "chapter_index": 2,
        "domain": "chapter",
        "domain_path": "recall.chapter.2.continuity_note.note-1",
    }


@pytest.mark.parametrize(
    ("field_name", "overrides"),
    [
        ("materialization_kind", {"materialization_kind": "  "}),
        ("materialization_event", {"materialization_event": ""}),
        ("session_id", {"session_id": "  "}),
        ("domain_path", {"domain_path": ""}),
    ],
)
def test_build_recall_materialization_metadata_rejects_blank_required_fields(
    field_name,
    overrides,
):
    values: dict[str, Any] = {
        "materialization_kind": CONTINUITY_NOTE_KIND,
        "materialization_event": HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
        "session_id": "session-1",
        "chapter_index": 1,
        "domain_path": "recall.chapter.1.continuity_note.note-1",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=field_name):
        build_recall_materialization_metadata(**values)


def test_build_recall_materialization_metadata_rejects_invalid_chapter_index():
    with pytest.raises(ValueError, match="chapter_index"):
        build_recall_materialization_metadata(
            materialization_kind=CONTINUITY_NOTE_KIND,
            materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
            session_id="session-1",
            chapter_index=0,
            domain_path="recall.chapter.0.continuity_note.note-1",
        )


def test_build_recall_seed_section_preserves_metadata_and_normalizes_tags():
    metadata = build_recall_materialization_metadata(
        materialization_kind=CONTINUITY_NOTE_KIND,
        materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
        session_id="session-1",
        chapter_index=1,
        domain_path="recall.chapter.1.continuity_note.note-1",
        extra={"note_index": 0},
    )

    section = build_recall_seed_section(
        section_id="continuity_note:note-1",
        title="Chapter 1 Continuity Note 1",
        path="recall.chapter.1.continuity_note.note-1",
        text="The envoy remembers the seal phrase.",
        metadata=metadata,
        tags=["continuity_note", "recall", "continuity_note", "  "],
    )

    assert section["metadata"] == {
        **metadata,
        "tags": ["continuity_note", "recall"],
    }


def test_build_archival_source_metadata_generates_canonical_fields():
    metadata = build_archival_source_metadata(
        source_type=FOUNDATION_ENTRY_SOURCE_TYPE,
        import_event=SETUP_COMMIT_IMPORT_EVENT,
        workspace_id="workspace-1",
        commit_id="commit-1",
        step_id="foundation",
        source_ref="setup_commit:commit-1:magic-law",
        domain="world_rule",
        domain_path="foundation.world.magic-law",
        extra={
            "title": "Magic Law",
            "layer": "recall",
            "source_family": "wrong_source",
            "materialized_to_archival": False,
            "materialized_to_recall": True,
            "authoritative_mutation": True,
            "source_type": "wrong_type",
            "source_ref": "wrong_ref",
            "domain": "character",
            "domain_path": "wrong.path",
        },
    )

    assert metadata == {
        "title": "Magic Law",
        "layer": "archival",
        "source_family": "setup_source",
        "import_event": "setup.commit_ingest",
        "source_type": "foundation_entry",
        "source_origin": "setup_workspace",
        "materialized_to_archival": True,
        "materialized_to_recall": False,
        "authoritative_mutation": False,
        "workspace_id": "workspace-1",
        "commit_id": "commit-1",
        "step_id": "foundation",
        "source_ref": "setup_commit:commit-1:magic-law",
        "domain": "world_rule",
        "domain_path": "foundation.world.magic-law",
    }


@pytest.mark.parametrize(
    ("field_name", "overrides"),
    [
        ("source_type", {"source_type": "  "}),
        ("import_event", {"import_event": ""}),
        ("workspace_id", {"workspace_id": " "}),
        ("commit_id", {"commit_id": ""}),
        ("step_id", {"step_id": ""}),
        ("source_ref", {"source_ref": ""}),
        ("domain", {"domain": " "}),
        ("domain_path", {"domain_path": ""}),
    ],
)
def test_build_archival_source_metadata_rejects_blank_required_fields(
    field_name,
    overrides,
):
    values: dict[str, Any] = {
        "source_type": FOUNDATION_ENTRY_SOURCE_TYPE,
        "import_event": SETUP_COMMIT_IMPORT_EVENT,
        "workspace_id": "workspace-1",
        "commit_id": "commit-1",
        "step_id": "foundation",
        "source_ref": "setup_commit:commit-1:magic-law",
        "domain": "world_rule",
        "domain_path": "foundation.world.magic-law",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=field_name):
        build_archival_source_metadata(**values)


def test_build_archival_seed_section_preserves_metadata_and_normalizes_tags():
    metadata = build_archival_source_metadata(
        source_type=FOUNDATION_ENTRY_SOURCE_TYPE,
        import_event=SETUP_COMMIT_IMPORT_EVENT,
        workspace_id="workspace-1",
        commit_id="commit-1",
        step_id="foundation",
        source_ref="setup_commit:commit-1:magic-law",
        domain="world_rule",
        domain_path="foundation.world.magic-law",
        extra={"title": "Magic Law"},
    )

    section = build_archival_seed_section(
        section_id="foundation:magic-law",
        title="Magic Law",
        path="magic-law",
        level=2,
        text="Magic cannot open dusk-sealed gates.",
        metadata=metadata,
        tags=["world", "archival", "world", "  "],
    )

    assert section["level"] == 2
    assert section["metadata"] == {
        **metadata,
        "tags": ["world", "archival"],
    }
