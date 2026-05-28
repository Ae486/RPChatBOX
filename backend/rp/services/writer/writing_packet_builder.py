"""Deterministic WritingPacket builder for active-story runtime."""

from __future__ import annotations

from uuid import uuid4

from rp.models.longform_chapter_contracts import LONGFORM_OUTLINE_SCHEMA_VERSION
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.story_runtime import ChapterWorkspace, OrchestratorPlan, StorySession
from rp.models.writing_runtime import PacketSection, WritingPacket


class WritingPacketBuilder:
    """Build stable writer packets from digested slots, never raw runtime truth."""

    def build(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        runtime_identity: MemoryRuntimeIdentity | None,
        operation_mode: str,
        projection_context_sections: list[dict[str, object]],
        runtime_writer_hints: list[str],
        user_instruction: str,
        recent_raw_turn_sections: list[dict[str, object]] | None = None,
        mode_sidecar_sections: list[dict[str, object]] | None = None,
        runtime_retrieval_sections: list[dict[str, object]] | None = None,
        review_overlay_sections: list[dict[str, object]] | None = None,
        trace_refs: list[str] | None = None,
        packet_metadata: dict[str, object] | None = None,
    ) -> WritingPacket:
        writer_contract = dict(session.writer_contract or {})
        system_sections = [
            "You are the writing_worker for a longform story system.",
            "Write only the requested output. Do not expose internal planning, retrieval, or worker steps.",
        ]
        if plan.output_kind == "chapter_outline":
            system_sections.append(
                "When drafting a chapter outline, return structured JSON with "
                f"schema_version={LONGFORM_OUTLINE_SCHEMA_VERSION}, chapter_goal, "
                "and an ordered beats array. Markdown rendering can be derived later."
            )
        if writer_contract:
            contract_lines = [
                str(item)
                for item in (
                    *writer_contract.get("pov_rules", []),
                    *writer_contract.get("style_rules", []),
                    *writer_contract.get("writing_constraints", []),
                    *writer_contract.get("task_writing_rules", []),
                )
                if item
            ]
            if contract_lines:
                system_sections.append(
                    "Writer contract:\n" + "\n".join(contract_lines)
                )

        core_view_sections = self._build_packet_sections(
            projection_context_sections,
            family_prefix="core_view",
            default_source_kind="core_projection_view",
        )
        recent_raw_sections = self._build_packet_sections(
            recent_raw_turn_sections or [],
            family_prefix="recent_raw_turn",
            default_source_kind="story_discussion_entry_window",
        )
        sidecar_sections = self._build_packet_sections(
            mode_sidecar_sections or [],
            family_prefix="mode_sidecar",
            default_source_kind="mode_sidecar",
        )
        if runtime_writer_hints:
            sidecar_sections.append(
                PacketSection(
                    section_id="mode_sidecar.writer_hints",
                    label="writer_hints",
                    source_kind="worker_hint_digest",
                    items=list(runtime_writer_hints),
                )
            )
        retrieval_card_sections = self._build_packet_sections(
            runtime_retrieval_sections or [],
            family_prefix="retrieval_card",
            default_source_kind="runtime_retrieval_card_summary",
        )
        review_sections = self._build_packet_sections(
            review_overlay_sections or [],
            family_prefix="review_overlay",
            default_source_kind="review_overlay",
        )
        context_sections = [
            section.to_legacy_dict()
            for section in (
                *core_view_sections,
                *recent_raw_sections,
                *sidecar_sections,
                *retrieval_card_sections,
                *review_sections,
            )
        ]

        metadata = {
            "story_id": session.story_id,
            "chapter_index": chapter.chapter_index,
            "phase": chapter.phase.value,
            "output_kind": plan.output_kind.value,
            "plan_notes": list(plan.notes),
            "packet_builder_boundary": "thin_context_packet_builder",
            "legacy_orchestrator_plan_role": "adapter_input",
        }
        if packet_metadata:
            metadata.update(dict(packet_metadata))
        packet_summary_metadata = {
            "section_counts": {
                "core_view_sections": len(core_view_sections),
                "recent_raw_turn_sections": len(recent_raw_sections),
                "mode_sidecar_sections": len(sidecar_sections),
                "retrieval_card_sections": len(retrieval_card_sections),
                "review_overlay_sections": len(review_sections),
            },
            "flattened_section_labels": [
                str(section["label"])
                for section in context_sections
                if str(section.get("label") or "").strip()
            ],
        }
        return WritingPacket(
            packet_id=uuid4().hex,
            identity=runtime_identity,
            session_id=session.session_id,
            branch_head_id=(
                runtime_identity.branch_head_id if runtime_identity is not None else None
            ),
            turn_id=runtime_identity.turn_id if runtime_identity is not None else None,
            chapter_workspace_id=chapter.chapter_workspace_id,
            output_kind=plan.output_kind.value,
            phase=chapter.phase.value,
            operation_mode=operation_mode,
            system_sections=system_sections,
            writer_contract=writer_contract,
            core_view_sections=core_view_sections,
            recent_raw_turn_sections=recent_raw_sections,
            mode_sidecar_sections=sidecar_sections,
            retrieval_card_sections=retrieval_card_sections,
            review_overlay_sections=review_sections,
            context_sections=context_sections,
            user_instruction=user_instruction,
            packet_summary_metadata=packet_summary_metadata,
            trace_refs=list(trace_refs or []),
            metadata=metadata,
        )

    @staticmethod
    def _build_packet_sections(
        sections: list[dict[str, object]],
        *,
        family_prefix: str,
        default_source_kind: str,
    ) -> list[PacketSection]:
        packet_sections: list[PacketSection] = []
        for index, raw_section in enumerate(sections):
            label = str(raw_section.get("label") or "").strip()
            raw_items = raw_section.get("items")
            if not isinstance(raw_items, list):
                continue
            items = [
                normalized
                for item in raw_items
                if (normalized := str(item).strip())
            ]
            if not label or not items:
                continue
            raw_source_ref_ids = raw_section.get("source_ref_ids")
            source_ref_ids = [
                normalized
                for item in (
                    raw_source_ref_ids if isinstance(raw_source_ref_ids, list) else []
                )
                if (normalized := str(item).strip())
            ]
            metadata_json = raw_section.get("metadata_json")
            if not isinstance(metadata_json, dict):
                metadata_json = raw_section.get("metadata")
            packet_sections.append(
                PacketSection(
                    section_id=str(raw_section.get("section_id") or "").strip()
                    or f"{family_prefix}.{index}.{WritingPacketBuilder._section_key(label)}",
                    label=label,
                    source_kind=str(raw_section.get("source_kind") or "").strip()
                    or default_source_kind,
                    source_ref_ids=source_ref_ids,
                    items=items,
                    metadata_json=(
                        dict(metadata_json)
                        if isinstance(metadata_json, dict)
                        else {}
                    ),
                )
            )
        return packet_sections

    @staticmethod
    def _section_key(label: str) -> str:
        return "".join(
            character.lower() if character.isalnum() else "_"
            for character in label
        ).strip("_") or "section"
