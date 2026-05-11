"""Provider that builds longform chapter bridge sidecars."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from models.chat import ChatMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rp.models.longform_chapter_contracts import ChapterBridgeMaterial
from rp.models.memory_contract_registry import MemoryRuntimeIdentity

from .story_llm_gateway import StoryLlmGateway


class ChapterBridgeSummaryPayload(BaseModel):
    """Structured provider output used to persist chapter bridge summaries."""

    model_config = ConfigDict(extra="forbid")

    summary_text: str
    continuity_notes: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)

    @field_validator("summary_text")
    @classmethod
    def _require_summary_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary_text must be non-empty")
        return normalized

    @field_validator("continuity_notes", "open_threads")
    @classmethod
    def _normalize_text_lists(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output


class ChapterBridgeProvider:
    """Build deterministic or model-backed bridge material for the next chapter."""

    def __init__(
        self,
        *,
        llm_gateway: StoryLlmGateway | None = None,
    ) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()

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
        covered_beat_ids: list[str] | None = None,
        continuity_notes: list[str] | None = None,
        open_threads: list[str] | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> ChapterBridgeMaterial:
        summary_payload = ChapterBridgeSummaryPayload(
            summary_text=_excerpt(adopted_output_text) or "No adopted chapter prose.",
            continuity_notes=list(continuity_notes or []),
            open_threads=list(open_threads or []),
        )
        return self._build_bridge_material(
            identity=identity,
            from_chapter_index=from_chapter_index,
            to_chapter_index=to_chapter_index,
            adopted_output_ref=adopted_output_ref,
            accepted_outline_ref=accepted_outline_ref,
            chapter_goal_ref=chapter_goal_ref,
            source_refs=source_refs,
            covered_beat_ids=covered_beat_ids,
            summary_payload=summary_payload,
            metadata_json={
                **dict(metadata_json or {}),
                "summary_provider": "deterministic_excerpt_fallback",
                "summary_generation_mode": "sync_fallback",
            },
        )

    async def build_bridge_material_with_summary(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        from_chapter_index: int,
        to_chapter_index: int,
        adopted_output_ref: str | None,
        accepted_outline_ref: str | None = None,
        chapter_goal_ref: str | None = None,
        chapter_goal: str | None = None,
        adopted_output_text: str | None = None,
        accepted_segment_texts: list[str] | None = None,
        covered_beat_ids: list[str] | None = None,
        covered_beats: list[dict[str, Any]] | None = None,
        source_refs: list[str] | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> ChapterBridgeMaterial:
        normalized_segment_texts = _normalize_text_list(accepted_segment_texts or [])
        if model_id and normalized_segment_texts:
            summary_payload = await self._generate_summary_payload(
                model_id=model_id,
                provider_id=provider_id,
                chapter_index=from_chapter_index,
                chapter_goal=chapter_goal,
                accepted_outline_ref=accepted_outline_ref,
                covered_beat_ids=_normalize_text_list(covered_beat_ids or []),
                covered_beats=list(covered_beats or []),
                accepted_segment_texts=normalized_segment_texts,
            )
            provider_metadata: dict[str, object] = {
                "summary_provider": "story_llm_gateway",
                "summary_generation_mode": "async_llm",
                "summary_model_id": model_id,
                "summary_provider_id": provider_id,
            }
        else:
            summary_payload = ChapterBridgeSummaryPayload(
                summary_text=_excerpt(adopted_output_text) or "No adopted chapter prose.",
                continuity_notes=[],
                open_threads=[],
            )
            provider_metadata = {
                "summary_provider": "deterministic_excerpt_fallback",
                "summary_generation_mode": "async_fallback",
                "summary_model_id": model_id,
                "summary_provider_id": provider_id,
            }
        return self._build_bridge_material(
            identity=identity,
            from_chapter_index=from_chapter_index,
            to_chapter_index=to_chapter_index,
            adopted_output_ref=adopted_output_ref,
            accepted_outline_ref=accepted_outline_ref,
            chapter_goal_ref=chapter_goal_ref,
            source_refs=source_refs,
            covered_beat_ids=covered_beat_ids,
            summary_payload=summary_payload,
            metadata_json={
                **dict(metadata_json or {}),
                **provider_metadata,
            },
        )

    async def _generate_summary_payload(
        self,
        *,
        model_id: str,
        provider_id: str | None,
        chapter_index: int,
        chapter_goal: str | None,
        accepted_outline_ref: str | None,
        covered_beat_ids: list[str],
        covered_beats: list[dict[str, Any]],
        accepted_segment_texts: list[str],
    ) -> ChapterBridgeSummaryPayload:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You build chapter bridge summaries for a longform runtime.\n"
                    "Return JSON only with keys summary_text, continuity_notes, open_threads.\n"
                    "summary_text must be concise and focus on continuation into the next chapter.\n"
                    "Do not write prose for the user. Do not include markdown fences."
                ),
            ),
            ChatMessage(
                role="user",
                content=self._summary_prompt(
                    chapter_index=chapter_index,
                    chapter_goal=chapter_goal,
                    accepted_outline_ref=accepted_outline_ref,
                    covered_beat_ids=covered_beat_ids,
                    covered_beats=covered_beats,
                    accepted_segment_texts=accepted_segment_texts,
                ),
            ),
        ]
        text, _usage = await self._llm_gateway.complete_text_with_usage(
            model_id=model_id,
            provider_id=provider_id,
            messages=messages,
            temperature=0.3,
            max_tokens=700,
        )
        try:
            payload = StoryLlmGateway.extract_json_object(text)
            return ChapterBridgeSummaryPayload.model_validate(payload)
        except (ValueError, ValidationError, json.JSONDecodeError):
            return ChapterBridgeSummaryPayload(summary_text=_excerpt(text) or "No summary.")

    @staticmethod
    def _summary_prompt(
        *,
        chapter_index: int,
        chapter_goal: str | None,
        accepted_outline_ref: str | None,
        covered_beat_ids: list[str],
        covered_beats: list[dict[str, Any]],
        accepted_segment_texts: list[str],
    ) -> str:
        beat_lines = []
        for beat in covered_beats:
            beat_id = str(beat.get("beat_id") or "").strip()
            title = str(beat.get("title") or "").strip()
            goal = str(beat.get("goal") or "").strip()
            parts = [part for part in (beat_id, title, goal) if part]
            if parts:
                beat_lines.append(" | ".join(parts))
        segment_blocks = [
            f"[segment {index + 1}]\n{text}"
            for index, text in enumerate(accepted_segment_texts)
            if text
        ]
        return "\n\n".join(
            block
            for block in (
                f"chapter_index: {chapter_index}",
                f"chapter_goal: {chapter_goal}" if chapter_goal else "",
                (
                    f"accepted_outline_ref: {accepted_outline_ref}"
                    if accepted_outline_ref
                    else ""
                ),
                (
                    "covered_beat_ids: " + ", ".join(covered_beat_ids)
                    if covered_beat_ids
                    else ""
                ),
                (
                    "covered_beats:\n- " + "\n- ".join(beat_lines)
                    if beat_lines
                    else ""
                ),
                (
                    "accepted_segments:\n" + "\n\n".join(segment_blocks)
                    if segment_blocks
                    else ""
                ),
            )
            if block
        )

    @staticmethod
    def _build_bridge_material(
        *,
        identity: MemoryRuntimeIdentity,
        from_chapter_index: int,
        to_chapter_index: int,
        adopted_output_ref: str | None,
        accepted_outline_ref: str | None,
        chapter_goal_ref: str | None,
        source_refs: list[str] | None,
        covered_beat_ids: list[str] | None,
        summary_payload: ChapterBridgeSummaryPayload,
        metadata_json: dict[str, object],
    ) -> ChapterBridgeMaterial:
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
            covered_beat_ids=list(covered_beat_ids or []),
            continuity_refs=continuity_refs,
            continuity_notes=list(summary_payload.continuity_notes),
            open_threads=list(summary_payload.open_threads),
            summary_text=summary_payload.summary_text,
            source_refs=list(source_refs or []),
            metadata_json=dict(metadata_json),
        )


def _excerpt(value: str | None, *, limit: int = 400) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _normalize_text_list(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output
