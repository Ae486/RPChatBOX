"""Compile active-story internal prompt context from current Block attachments."""

from __future__ import annotations

from copy import deepcopy

from rp.models.block_consumer import BlockConsumerKey
from rp.models.block_prompt_context import RpBlockPromptContextView
from rp.models.dsl import ObjectRef

from .memory_object_mapper import (
    resolve_authoritative_binding,
    resolve_projection_binding,
)
from .rp_block_read_service import RpBlockReadService
from .settled_projection_mapper import settled_projection_slots
from .story_block_consumer_state_service import StoryBlockConsumerStateService


class StoryBlockPromptContextService:
    """Bridge current Block attachments into internal agent-friendly prompt context."""

    def __init__(
        self,
        *,
        rp_block_read_service: RpBlockReadService,
        story_block_consumer_state_service: StoryBlockConsumerStateService,
    ) -> None:
        self._rp_block_read_service = rp_block_read_service
        self._story_block_consumer_state_service = story_block_consumer_state_service

    def build_consumer_context(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockPromptContextView | None:
        consumer = self._story_block_consumer_state_service.get_consumer(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        if consumer is None:
            return None

        all_blocks = {
            block.block_id: block
            for block in self._rp_block_read_service.list_core_state_blocks(
                session_id=session_id
            )
        }
        attached_blocks = []
        authoritative_state: dict[str, object] = {}
        projection_state: dict[str, list[str]] = {
            slot_name: [] for slot_name in settled_projection_slots()
        }
        missing_block_ids: list[str] = []

        for attachment in consumer.attached_blocks:
            block = all_blocks.get(attachment.block_id)
            if block is None:
                missing_block_ids.append(attachment.block_id)
                continue
            attached_blocks.append(block.model_copy(deep=True))

            authoritative_binding = resolve_authoritative_binding(
                ObjectRef(
                    object_id=block.label,
                    layer=block.layer,
                    domain=block.domain,
                    domain_path=block.domain_path,
                    scope=block.scope,
                    revision=block.revision,
                )
            )
            if authoritative_binding is not None:
                authoritative_state[authoritative_binding.backend_field] = deepcopy(
                    block.data_json
                )
                continue

            projection_binding = resolve_projection_binding(block.label)
            if projection_binding is not None:
                projection_state[projection_binding.slot_name] = [
                    str(item) for item in (block.items_json or []) if item is not None
                ]

        return RpBlockPromptContextView(
            consumer_key=consumer.consumer_key,
            session_id=session_id,
            chapter_workspace_id=consumer.chapter_workspace_id,
            dirty=consumer.dirty,
            dirty_reasons=list(consumer.dirty_reasons),
            dirty_block_ids=list(consumer.dirty_block_ids),
            last_synced_at=consumer.last_synced_at,
            authoritative_state=authoritative_state,
            projection_state=projection_state,
            attached_blocks=attached_blocks,
            metadata={
                **deepcopy(consumer.metadata),
                "missing_block_ids": missing_block_ids,
            },
        )
