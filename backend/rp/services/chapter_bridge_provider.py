"""Deterministic provider that builds longform chapter bridge sidecars."""

from __future__ import annotations

from uuid import uuid4

from rp.models.longform_chapter_contracts import ChapterBridgeMaterial
from rp.models.memory_contract_registry import MemoryRuntimeIdentity


class ChapterBridgeProvider:
    """Build a minimal bridge from adopted output, accepted outline, and chapter goal."""

    def build_bridge_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        from_chapter_index: int,
        to_chapter_index: int,
        adopted_output_ref: str | None,
        accepted_outline_ref: str | None = None,
        chapter_goal_ref: str | None = None,
        adopted_output_text: str | None = None,
        source_refs: list[str] | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> ChapterBridgeMaterial:
        summary_text = _excerpt(adopted_output_text)
        continuity_refs = [
            ref
            for ref in (
                adopted_output_ref,
                accepted_outline_ref,
                chapter_goal_ref,
            )
            if isinstance(ref, str) and ref.strip()
        ]
        return ChapterBridgeMaterial(
            bridge_id=f"chapter_bridge_{uuid4().hex}",
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            source_chapter_index=from_chapter_index,
            target_chapter_index=to_chapter_index,
            adopted_output_ref=adopted_output_ref,
            accepted_outline_ref=accepted_outline_ref,
            chapter_goal_ref=chapter_goal_ref,
            continuity_refs=continuity_refs,
            summary_text=summary_text,
            source_refs=list(source_refs or []),
            metadata_json=dict(metadata_json or {}),
        )


def _excerpt(value: str | None, *, limit: int = 400) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
