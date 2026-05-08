"""Focused tests for R1 draft materialization and anchor contracts."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import DraftDocumentBlock, DraftDocumentRecord
from rp.services.draft_materialization_service import DraftMaterializationService


def test_markdown_materialization_keeps_stable_block_ids_for_unchanged_draft():
    service = DraftMaterializationService()
    markdown = "# Opening\n\nThe storm arrived at dusk.\n\n- The seal broke\n- Mira ran"

    first = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:turn-1:writer-output",
        source_output_ref="artifact:writer-output-1",
        output_text=markdown,
        source_format="markdown",
    )
    second = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:turn-1:writer-output",
        source_output_ref="artifact:writer-output-1",
        output_text=markdown,
        source_format="markdown",
    )

    assert [block.block_id for block in first.blocks] == [
        block.block_id for block in second.blocks
    ]
    assert first.draft_document_id == second.draft_document_id
    assert first.turn_id == "turn-1"
    assert first.source_output_ref == "artifact:writer-output-1"


def test_markdown_first_pass_parser_splits_heading_list_and_paragraph_blocks():
    record = DraftMaterializationService().materialize_draft(
        identity=_identity(),
        draft_ref="draft:markdown-basic",
        output_text=(
            "# Chapter One\n\n"
            "The hall smelled of rain.\n"
            "Mira kept walking.\n\n"
            "1. Light the lamp\n"
            "- Close the gate\n"
        ),
        source_format="markdown",
    )

    assert [block.block_kind for block in record.blocks] == [
        "heading",
        "paragraph",
        "list_item",
        "list_item",
    ]
    assert record.blocks[0].text == "Chapter One"
    assert record.blocks[1].text == "The hall smelled of rain.\nMira kept walking."
    assert record.blocks[2].text == "Light the lamp"
    for block in record.blocks:
        assert block.markdown_source_range is not None
        assert block.source_range is not None
        assert block.source_range["start"] < block.source_range["end"]
        assert block.selected_excerpt
        assert block.selected_excerpt_hash


def test_plain_text_fallback_uses_blank_line_paragraphs_not_raw_line_anchors():
    record = DraftMaterializationService().materialize_draft(
        identity=_identity(),
        draft_ref="draft:plain-text",
        output_text=(
            "First paragraph line one.\n"
            "First paragraph line two.\n\n"
            "Second paragraph."
        ),
        source_format="plain_text",
    )

    assert [block.block_kind for block in record.blocks] == ["paragraph", "paragraph"]
    assert record.blocks[0].text == (
        "First paragraph line one.\nFirst paragraph line two."
    )
    assert record.blocks[0].markdown_source_range is None
    assert record.blocks[0].source_range == {"start": 0, "end": 52}
    assert record.blocks[0].metadata_json["fallback_parser"] == "blank_line_paragraphs"


def test_same_draft_and_unchanged_text_keep_block_id_stable():
    service = DraftMaterializationService()
    first = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:stable",
        output_text="One settled paragraph.",
        source_format="plain_text",
    )
    second = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:stable",
        output_text="One settled paragraph.",
        source_format="plain_text",
    )

    assert first.blocks[0].block_id == second.blocks[0].block_id
    assert (
        first.blocks[0].metadata_json["normalized_text_hash"]
        == second.blocks[0].metadata_json["normalized_text_hash"]
    )


def test_changed_text_changes_block_id_but_keeps_excerpt_and_source_fallback_metadata():
    service = DraftMaterializationService()
    original = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:changed",
        output_text="The room was quiet.",
        source_format="plain_text",
    )
    changed = service.materialize_draft(
        identity=_identity(),
        draft_ref="draft:changed",
        output_text="The room was painfully quiet.",
        source_format="plain_text",
    )

    original_block = original.blocks[0]
    changed_block = changed.blocks[0]
    assert original_block.block_id != changed_block.block_id
    assert original_block.source_range == {"start": 0, "end": 19}
    assert changed_block.source_range == {"start": 0, "end": 29}
    assert original_block.selected_excerpt == "The room was quiet."
    assert changed_block.selected_excerpt == "The room was painfully quiet."
    assert original_block.selected_excerpt_hash
    assert changed_block.selected_excerpt_hash
    assert original_block.metadata_json["anchor_strategy"] == (
        "draft_ref_order_normalized_text_hash"
    )


def test_revision_overlay_dtos_use_factory_defaults_not_shared_mutable_state():
    first_block = DraftDocumentBlock(
        block_id="block-1",
        order=0,
        block_kind="paragraph",
        text="First",
    )
    second_block = DraftDocumentBlock(
        block_id="block-2",
        order=1,
        block_kind="paragraph",
        text="Second",
    )
    first_block.metadata_json["marker"] = "first"

    assert second_block.metadata_json == {}

    first_record = DraftDocumentRecord(
        draft_document_id="doc-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        source_output_ref="artifact-1",
        source_format="markdown",
        materialization_version="test",
        created_at=_now_for_test(),
    )
    second_record = DraftDocumentRecord(
        draft_document_id="doc-2",
        turn_id="turn-1",
        draft_ref="draft-2",
        source_output_ref="artifact-2",
        source_format="plain_text",
        materialization_version="test",
        created_at=_now_for_test(),
    )
    first_record.blocks.append(first_block)
    first_record.metadata_json["marker"] = "first"

    assert second_record.blocks == []
    assert second_record.metadata_json == {}


def test_draft_block_rejects_blank_anchor_text():
    try:
        DraftDocumentBlock(
            block_id="block-blank",
            order=0,
            block_kind="paragraph",
            text=" ",
        )
    except ValidationError as exc:
        assert "text" in str(exc)
    else:
        raise AssertionError("blank draft block text should fail validation")


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-1"),
        session_id=overrides.get("session_id", "session-1"),
        branch_head_id=overrides.get("branch_head_id", "branch-1"),
        turn_id=overrides.get("turn_id", "turn-1"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-1",
        ),
    )


def _now_for_test():
    return datetime.now(timezone.utc)
