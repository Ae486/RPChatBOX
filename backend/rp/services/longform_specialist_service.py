"""Single-generalist specialist for longform MVP."""

from __future__ import annotations

import json

from models.chat import ChatMessage
from rp.models.memory_crud import MemorySearchArchivalInput, MemorySearchRecallInput
from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifact,
    StorySession,
)
from .memory_os_service import MemoryOsService
from .retrieval_broker import RetrievalBroker
from .story_llm_gateway import StoryLlmGateway


class LongformSpecialistService:
    """Digest retrieval and runtime state into builder-ready slots."""

    def __init__(
        self,
        *,
        llm_gateway: StoryLlmGateway | None = None,
        memory_os_factory=None,
    ) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()
        self._memory_os_factory = memory_os_factory or (
            lambda story_id: MemoryOsService(
                retrieval_broker=RetrievalBroker(default_story_id=story_id)
            )
        )

    async def analyze(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        accepted_segments: list[StoryArtifact],
        pending_artifact: StoryArtifact | None,
    ) -> SpecialistResultBundle:
        memory_os = self._memory_os_factory(session.story_id)
        archival_hits = []
        recall_hits = []
        for query in plan.archival_queries:
            if not query:
                continue
            result = await memory_os.search_archival(
                MemorySearchArchivalInput(query=query, top_k=3)
            )
            archival_hits.extend(result.hits)
        for query in plan.recall_queries:
            if not query:
                continue
            result = await memory_os.search_recall(
                MemorySearchRecallInput(query=query, top_k=3, scope="story")
            )
            recall_hits.extend(result.hits)

        fallback = self._fallback_bundle(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=command_kind,
            user_prompt=user_prompt,
            accepted_segments=accepted_segments,
            pending_artifact=pending_artifact,
            archival_hits=archival_hits,
            recall_hits=recall_hits,
        )
        if command_kind in {
            LongformTurnCommandKind.ACCEPT_OUTLINE,
            LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            LongformTurnCommandKind.COMPLETE_CHAPTER,
        }:
            return fallback

        system_prompt = (
            "You are the longform_specialist for an active-story MVP. "
            "Digest retrieval and runtime state into JSON only. "
            "Do not write user-visible prose. Return compact digests, writer hints, "
            "validation findings, and minimal state_patch_proposals."
        )
        user_payload = {
            "session": session.model_dump(mode="json"),
            "chapter": chapter.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "command_kind": command_kind.value,
            "user_prompt": user_prompt,
            "accepted_segments": [
                {
                    "artifact_id": item.artifact_id,
                    "content_text": item.content_text,
                    "metadata": item.metadata,
                }
                for item in accepted_segments[-3:]
            ],
            "pending_artifact": pending_artifact.model_dump(mode="json")
            if pending_artifact is not None
            else None,
            "archival_hits": [
                {
                    "excerpt_text": hit.excerpt_text,
                    "domain": hit.domain.value,
                    "domain_path": hit.domain_path,
                    "metadata": hit.metadata,
                }
                for hit in archival_hits[:4]
            ],
            "recall_hits": [
                {
                    "excerpt_text": hit.excerpt_text,
                    "domain": hit.domain.value,
                    "domain_path": hit.domain_path,
                    "metadata": hit.metadata,
                }
                for hit in recall_hits[:4]
            ],
            "response_schema": SpecialistResultBundle.model_json_schema(),
        }
        try:
            raw = await self._llm_gateway.complete_text(
                model_id=model_id,
                provider_id=provider_id,
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
                ],
                temperature=0.2,
                max_tokens=900,
            )
            return SpecialistResultBundle.model_validate(
                self._llm_gateway.extract_json_object(raw)
            )
        except Exception:
            return fallback

    @staticmethod
    def _fallback_bundle(
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        command_kind: LongformTurnCommandKind,
        user_prompt: str | None,
        accepted_segments: list[StoryArtifact],
        pending_artifact: StoryArtifact | None,
        archival_hits: list,
        recall_hits: list,
    ) -> SpecialistResultBundle:
        blueprint_digest = list(chapter.builder_snapshot_json.get("blueprint_digest", []))
        foundation_digest = list(chapter.builder_snapshot_json.get("foundation_digest", []))
        current_outline_digest = list(chapter.builder_snapshot_json.get("current_outline_digest", []))
        recent_segment_digest = [
            item.content_text[:240] for item in accepted_segments[-2:]
        ]
        current_state_digest = [
            f"phase={chapter.phase.value}",
            f"chapter={chapter.chapter_index}",
            f"accepted_segments={len(chapter.accepted_segment_ids)}",
        ]
        current_state_digest.extend(
            value
            for value in (
                session.current_state_json.get("narrative_progress", {}).get("chapter_summary"),
                session.current_state_json.get("chapter_digest", {}).get("title"),
            )
            if value
        )
        retrieval_digest = [hit.excerpt_text[:220] for hit in [*archival_hits[:2], *recall_hits[:2]]]
        if not current_outline_digest and chapter.accepted_outline_json is not None:
            current_outline_digest.append(
                str(chapter.accepted_outline_json.get("content_text") or chapter.accepted_outline_json)
            )
        if pending_artifact is not None and command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT:
            recent_segment_digest.append(pending_artifact.content_text[:240])
        writer_hints = list(plan.specialist_focus)
        writer_hints.extend(retrieval_digest[:2])
        if user_prompt:
            writer_hints.append(user_prompt)

        state_patch: dict[str, object] = {}
        if command_kind in {
            LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            LongformTurnCommandKind.COMPLETE_CHAPTER,
        }:
            segment_text = pending_artifact.content_text if pending_artifact is not None else ""
            summary = segment_text[:320] if segment_text else "Accepted segment updated runtime state."
            state_patch = {
                "chapter_digest": {
                    "current_chapter": chapter.chapter_index,
                    "last_accepted_excerpt": summary,
                },
                "narrative_progress": {
                    "last_command": command_kind.value,
                    "accepted_segments": len(chapter.accepted_segment_ids) + (
                        1 if command_kind == LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT else 0
                    ),
                    "chapter_summary": summary,
                },
                "timeline_spine": [
                    {
                        "chapter_index": chapter.chapter_index,
                        "summary": summary,
                    }
                ],
            }

        recall_summary = None
        if command_kind == LongformTurnCommandKind.COMPLETE_CHAPTER:
            recall_summary = " ".join(filter(None, recent_segment_digest))[:1200] or (
                chapter.chapter_goal or f"Chapter {chapter.chapter_index} completed."
            )

        return SpecialistResultBundle(
            foundation_digest=foundation_digest[:5],
            blueprint_digest=blueprint_digest[:6],
            current_outline_digest=current_outline_digest[:4],
            recent_segment_digest=recent_segment_digest[:4],
            current_state_digest=current_state_digest[:6],
            writer_hints=writer_hints[:8],
            validation_findings=[],
            state_patch_proposals=state_patch,
            summary_updates=retrieval_digest[:3],
            recall_summary_text=recall_summary,
        )
