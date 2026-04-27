"""Deterministically render attached Block context for internal agent prompts."""

from __future__ import annotations

import json

from rp.models.block_prompt_context import RpBlockPromptContextView


class StoryBlockPromptRenderService:
    """Render Block-backed prompt context into a stable internal prompt overlay."""

    def render_prompt_overlay(
        self,
        *,
        context: RpBlockPromptContextView,
    ) -> str:
        sorted_blocks = sorted(
            context.attached_blocks,
            key=lambda block: (block.layer.value, block.label, block.block_id),
        )
        lines = [
            "[BLOCK_PROMPT_CONTEXT]",
            f"consumer={context.consumer_key}",
            f"session_id={context.session_id}",
            f"chapter_workspace_id={context.chapter_workspace_id or ''}",
            f"dirty={str(context.dirty).lower()}",
            f"dirty_reasons={json.dumps(context.dirty_reasons, ensure_ascii=False)}",
            f"dirty_block_ids={json.dumps(context.dirty_block_ids, ensure_ascii=False)}",
            f"attached_block_count={len(sorted_blocks)}",
        ]
        for block in sorted_blocks:
            lines.extend(
                [
                    (
                        f'<block block_id="{block.block_id}"'
                        f' label="{block.label}"'
                        f' layer="{block.layer.value}"'
                        f' domain="{block.domain.value}"'
                        f' domain_path="{block.domain_path}"'
                        f' scope="{block.scope}"'
                        f' revision="{block.revision}"'
                        f' source="{block.source}">'
                    ),
                    self._render_block_payload(block.data_json, block.items_json),
                    "</block>",
                ]
            )
        lines.append("[/BLOCK_PROMPT_CONTEXT]")
        return "\n".join(lines)

    @staticmethod
    def _render_block_payload(data_json, items_json) -> str:
        if items_json is not None:
            return json.dumps(items_json, ensure_ascii=False, sort_keys=True)
        return json.dumps(data_json, ensure_ascii=False, sort_keys=True)
