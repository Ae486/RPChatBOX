"""Deterministic WritingPacket builder for active-story runtime."""

from __future__ import annotations

from uuid import uuid4

from rp.models.story_runtime import ChapterWorkspace, OrchestratorPlan, StorySession
from rp.models.writing_runtime import WritingPacket


class WritingPacketBuilder:
    """Build stable writer packets from digested runtime slots."""

    def build(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        projection_context_sections: list[dict[str, object]],
        runtime_writer_hints: list[str],
        user_instruction: str,
    ) -> WritingPacket:
        writer_contract = session.writer_contract
        system_sections = [
            "You are the writing_worker for a longform story system.",
            "Write only the requested output. Do not expose internal planning, retrieval, or worker steps.",
        ]
        if writer_contract:
            system_sections.append(
                "Writer contract:\n"
                + "\n".join(
                    str(item)
                    for item in (
                        *writer_contract.get("pov_rules", []),
                        *writer_contract.get("style_rules", []),
                        *writer_contract.get("writing_constraints", []),
                        *writer_contract.get("task_writing_rules", []),
                    )
                    if item
                )
            )

        context_sections = list(projection_context_sections)
        if runtime_writer_hints:
            context_sections.append({"label": "writer_hints", "items": list(runtime_writer_hints)})

        metadata = {
            "story_id": session.story_id,
            "chapter_index": chapter.chapter_index,
            "phase": chapter.phase.value,
            "output_kind": plan.output_kind.value,
            "plan_notes": list(plan.notes),
        }
        return WritingPacket(
            packet_id=uuid4().hex,
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            output_kind=plan.output_kind.value,
            phase=chapter.phase.value,
            system_sections=system_sections,
            context_sections=context_sections,
            user_instruction=user_instruction,
            metadata=metadata,
        )
