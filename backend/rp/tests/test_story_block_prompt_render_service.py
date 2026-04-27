"""Tests for deterministic Block prompt overlay rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from rp.models.block_prompt_context import RpBlockPromptContextView
from rp.models.block_view import RpBlockView
from rp.models.dsl import Domain, Layer
from rp.services.story_block_prompt_render_service import StoryBlockPromptRenderService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_story_block_prompt_render_service_renders_deterministic_overlay():
    service = StoryBlockPromptRenderService()
    rendered = service.render_prompt_overlay(
        context=RpBlockPromptContextView(
            consumer_key="story.orchestrator",
            session_id="session-1",
            chapter_workspace_id="chapter-1",
            dirty=True,
            dirty_reasons=["never_synced"],
            dirty_block_ids=["block-b"],
            last_synced_at=_utcnow(),
            attached_blocks=[
                RpBlockView(
                    block_id="block-b",
                    label="projection.current_outline_digest",
                    layer=Layer.CORE_STATE_PROJECTION,
                    domain=Domain.CHAPTER,
                    domain_path="projection.current_outline_digest",
                    scope="chapter",
                    revision=4,
                    source="core_state_store",
                    items_json=["Outline A"],
                ),
                RpBlockView(
                    block_id="block-a",
                    label="chapter.current",
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=Domain.CHAPTER,
                    domain_path="chapter.current",
                    scope="story",
                    revision=3,
                    source="core_state_store",
                    data_json={"title": "Chapter One", "current_chapter": 1},
                ),
            ],
        )
    )

    assert rendered.startswith("[BLOCK_PROMPT_CONTEXT]")
    assert "consumer=story.orchestrator" in rendered
    assert "dirty=true" in rendered
    assert rendered.index('label="chapter.current"') < rendered.index(
        'label="projection.current_outline_digest"'
    )
    assert '{"current_chapter": 1, "title": "Chapter One"}' in rendered
    assert '["Outline A"]' in rendered
    assert rendered.endswith("[/BLOCK_PROMPT_CONTEXT]")
