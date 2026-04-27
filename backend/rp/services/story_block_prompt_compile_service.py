"""Cached compile service for active-story Block-backed prompt overlays."""

from __future__ import annotations

from rp.models.block_consumer import BlockConsumerKey
from rp.models.block_prompt_compile import RpBlockPromptCompileView

from .story_block_consumer_state_service import StoryBlockConsumerStateService
from .story_block_prompt_context_service import StoryBlockPromptContextService
from .story_block_prompt_render_service import StoryBlockPromptRenderService


_BLOCK_PROMPT_CONSUMERS: tuple[BlockConsumerKey, ...] = (
    "story.orchestrator",
    "story.specialist",
)


class StoryBlockPromptCompileService:
    """Compile or reuse active-story internal Block prompt overlays lazily."""

    def __init__(
        self,
        *,
        story_block_prompt_context_service: StoryBlockPromptContextService,
        story_block_prompt_render_service: StoryBlockPromptRenderService,
        story_block_consumer_state_service: StoryBlockConsumerStateService,
    ) -> None:
        self._story_block_prompt_context_service = story_block_prompt_context_service
        self._story_block_prompt_render_service = story_block_prompt_render_service
        self._story_block_consumer_state_service = story_block_consumer_state_service

    def compile_consumer_prompt(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockPromptCompileView | None:
        if consumer_key not in _BLOCK_PROMPT_CONSUMERS:
            return None
        context = self._story_block_prompt_context_service.build_consumer_context(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        if context is None:
            return None
        record = self._story_block_consumer_state_service.get_consumer_record(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        current_revision_map = {
            block.block_id: int(block.revision) for block in context.attached_blocks
        }
        compiled_revisions = dict(record.last_compiled_revisions_json or {}) if record else {}
        detached_block_ids = sorted(
            block_id
            for block_id in compiled_revisions
            if block_id not in current_revision_map
        )
        changed_block_ids = [
            block.block_id
            for block in context.attached_blocks
            if compiled_revisions.get(block.block_id) != int(block.revision)
        ]
        compile_reasons: list[str] = []
        if record is None or record.last_compiled_at is None:
            compile_reasons.append("never_compiled")
        else:
            if changed_block_ids:
                compile_reasons.append("compiled_block_revision_changed")
            if detached_block_ids:
                compile_reasons.append("compiled_block_detached")
            if (
                context.chapter_workspace_id
                != record.last_compiled_chapter_workspace_id
            ):
                compile_reasons.append("compiled_chapter_workspace_changed")
            if not record.last_compiled_prompt_overlay:
                compile_reasons.append("cached_overlay_missing")
            if (
                record.last_synced_at is not None
                and record.last_compiled_at < record.last_synced_at
            ):
                compile_reasons.append("consumer_sync_state_changed")
        if not compile_reasons and record is not None:
            return RpBlockPromptCompileView(
                context=context,
                prompt_overlay=str(record.last_compiled_prompt_overlay or ""),
                compile_mode="reused",
                compiled_at=record.last_compiled_at,
                metadata={
                    "changed_block_ids": changed_block_ids,
                    "detached_block_ids": detached_block_ids,
                },
            )

        prompt_overlay = self._story_block_prompt_render_service.render_prompt_overlay(
            context=context
        )
        record = self._story_block_consumer_state_service.mark_consumer_compiled(
            session_id=session_id,
            consumer_key=consumer_key,
            attached_blocks=context.attached_blocks,
            chapter_workspace_id=context.chapter_workspace_id,
            prompt_overlay=prompt_overlay,
        )
        return RpBlockPromptCompileView(
            context=context,
            prompt_overlay=prompt_overlay,
            compile_mode="rebuilt",
            compile_reasons=compile_reasons,
            compiled_at=record.last_compiled_at if record is not None else None,
            metadata={
                "changed_block_ids": changed_block_ids,
                "detached_block_ids": detached_block_ids,
            },
        )
