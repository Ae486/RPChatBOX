"""Deterministic context orchestration for writer and worker packets."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.mode_extension_contracts import (
    packet_sidecar_material_kinds_for_slot,
)
from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifact,
    StorySession,
)
from rp.models.longform_chapter_contracts import LongformStructuredOutline
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
)
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.models.worker_runtime_contracts import WorkerContextPacket
from rp.models.writing_runtime import WritingPacket

from .builder_projection_context_service import BuilderProjectionContextService
from .longform_chapter_runtime_service import LongformChapterRuntimeService
from .runtime_read_manifest_service import RuntimeReadManifestService
from .runtime_retrieval_card_service import RuntimeRetrievalCardService
from .runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .story_session_service import StorySessionService
from .writing_packet_builder import WritingPacketBuilder


class ContextOrchestrationService:
    """Assemble deterministic writer and worker packets from stable read surfaces."""

    _BRANCH_SENSITIVE_PROJECTION_LABELS = {
        "current_state_digest",
        "recent_segment_digest",
    }
    _DEFAULT_FORBIDDEN_CONTEXT = (
        "raw_authoritative_state_json",
        "tool_call_trace",
        "worker_chain_of_thought",
    )
    _MANDATORY_CONTINUITY_INSTRUCTION = (
        "Continue after the latest accepted segment; do not restart the scene; "
        "do not rewrite already completed outline material."
    )
    _MANDATORY_REWRITE_INSTRUCTION = (
        "Apply every listed review constraint exactly. Treat active comments and "
        "tracked changes as mandatory rewrite requirements."
    )

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        builder_projection_context_service: BuilderProjectionContextService,
        writing_packet_builder: WritingPacketBuilder,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService
        | None = None,
        runtime_read_manifest_service: RuntimeReadManifestService | None = None,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
        longform_chapter_runtime_service: LongformChapterRuntimeService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._builder_projection_context_service = builder_projection_context_service
        self._writing_packet_builder = writing_packet_builder
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._runtime_read_manifest_service = runtime_read_manifest_service
        self._runtime_profile_snapshot_service = runtime_profile_snapshot_service
        self._longform_chapter_runtime_service = longform_chapter_runtime_service

    def build_writing_packet(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        specialist_bundle: SpecialistResultBundle,
        operation_mode: str = "writing",
        command_kind: LongformTurnCommandKind | None = None,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        target_artifact_id: str | None = None,
        review_overlay_sections: list[dict[str, object]] | None = None,
    ) -> WritingPacket:
        packet_metadata: dict[str, object] = {}
        projection_context_sections = (
            self._builder_projection_context_service.build_context_sections(
                session_id=session.session_id,
            )
        )
        projection_context_sections = (
            self._branch_scoped_projection_context_sections(
                sections=projection_context_sections,
                runtime_identity=runtime_identity,
                packet_metadata=packet_metadata,
            )
        )
        recent_raw_turn_sections = self._build_recent_raw_turn_sections(
            chapter=chapter,
        )
        runtime_retrieval_sections: list[dict[str, object]] = []
        if runtime_identity is not None:
            packet_metadata["runtime_identity"] = runtime_identity.model_dump(
                mode="json"
            )
            (
                runtime_retrieval_sections,
                source_ref_bundle,
            ) = self._build_runtime_retrieval_packet_context(
                identity=runtime_identity,
            )
            if not source_ref_bundle.is_empty():
                packet_metadata["worker_source_ref_bundle"] = (
                    source_ref_bundle.model_dump(mode="json")
                )
            mode_sidecar_sections = self._build_mode_sidecar_sections(
                identity=runtime_identity,
                session_mode=str(session.mode or "").strip().lower(),
                packet_metadata=packet_metadata,
            )
            mode_sidecar_sections.extend(
                self._build_longform_chapter_progress_sections(
                    session=session,
                    chapter=chapter,
                    identity=runtime_identity,
                    command_kind=command_kind,
                )
            )
            mode_sidecar_sections.extend(
                self._build_longform_chapter_bridge_sections(
                    session=session,
                    chapter=chapter,
                    identity=runtime_identity,
                    packet_metadata=packet_metadata,
                )
            )
        else:
            mode_sidecar_sections = []
        if command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT:
            resolved_target_artifact_id = str(
                target_artifact_id or chapter.pending_segment_artifact_id or ""
            ).strip()
            review_scope = "full"
            if review_overlay_sections:
                first_metadata = review_overlay_sections[0].get("metadata_json")
                if isinstance(first_metadata, dict):
                    review_scope = (
                        str(first_metadata.get("rewrite_scope") or "").strip()
                        or review_scope
                    )
            packet_metadata.update(
                {
                    "rewrite_scope": review_scope,
                    "target_artifact_id": resolved_target_artifact_id or None,
                    "revision_constraint_source": (
                        "active_review_overlay"
                        if review_overlay_sections
                        else "no_active_review_constraints"
                    ),
                    "review_overlay_section_count": len(review_overlay_sections or []),
                    "mandatory_rewrite_instruction": (
                        self._MANDATORY_REWRITE_INSTRUCTION
                        if review_overlay_sections
                        else None
                    ),
                }
            )
        packet = self._writing_packet_builder.build(
            session=session,
            chapter=chapter,
            plan=plan,
            runtime_identity=runtime_identity,
            operation_mode=operation_mode,
            projection_context_sections=projection_context_sections,
            recent_raw_turn_sections=recent_raw_turn_sections,
            mode_sidecar_sections=mode_sidecar_sections,
            runtime_retrieval_sections=runtime_retrieval_sections,
            runtime_writer_hints=list(specialist_bundle.writer_hints),
            review_overlay_sections=review_overlay_sections,
            user_instruction=plan.writer_instruction,
            packet_metadata=packet_metadata,
        )
        if (
            runtime_identity is None
            or self._runtime_read_manifest_service is None
        ):
            return packet
        manifest = self._runtime_read_manifest_service.build_writer_manifest(
            identity=runtime_identity,
            packet_kind="writer",
            packet_sections=packet.context_sections,
            selected_section_labels=[
                str(section.get("label") or "").strip()
                for section in packet.context_sections
                if str(section.get("label") or "").strip()
            ],
            policy_versions={"packet_kind": "writer"},
        )
        return packet.model_copy(
            update={
                "trace_refs": [
                    *list(packet.trace_refs),
                    f"runtime_read_manifest:{manifest.manifest_id}",
                ],
                "metadata": {
                    **dict(packet.metadata),
                    "runtime_read_manifest_id": manifest.manifest_id,
                    "runtime_read_manifest": manifest.model_dump(mode="json"),
                }
            }
        )

    def _branch_scoped_projection_context_sections(
        self,
        *,
        sections: list[dict[str, object]],
        runtime_identity: MemoryRuntimeIdentity | None,
        packet_metadata: dict[str, object],
    ) -> list[dict[str, object]]:
        if runtime_identity is None or self._runtime_read_manifest_service is None:
            return [dict(section) for section in sections]
        scope = self._runtime_read_manifest_service.build_branch_scope(
            identity=runtime_identity
        )
        if not self._scope_requires_projection_omission(scope):
            return [dict(section) for section in sections]
        filtered_sections: list[dict[str, object]] = []
        omitted: list[dict[str, object]] = []
        for section in sections:
            label = str(section.get("label") or "").strip()
            if label not in self._BRANCH_SENSITIVE_PROJECTION_LABELS:
                filtered_sections.append(dict(section))
                continue
            omitted.append(
                {
                    "label": label,
                    "reason": (
                        "branch_sensitive_projection_omitted_until_"
                        "branch_scoped_projection_refresh"
                    ),
                    "active_branch_head_id": scope.active_branch_head_id,
                    "selected_turn_id": scope.selected_turn_id,
                    "active_branch_lineage": list(scope.visible_branch_head_ids),
                    "turn_cutoff_by_branch": dict(scope.turn_cutoff_by_branch),
                }
            )
        if omitted:
            packet_metadata["branch_visibility_omitted_projection_sections"] = omitted
        return filtered_sections

    @staticmethod
    def _scope_requires_projection_omission(scope) -> bool:
        if len(scope.visible_branch_head_ids) > 1:
            return True
        return any(
            bool(turn_ids)
            for turn_ids in dict(scope.hidden_turn_ids_by_branch).values()
        )

    def build_worker_context_packet(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity,
        worker_id: str,
        phase: str,
        mode: str,
        context_requirements: dict[str, object] | None = None,
        reason_codes: list[str] | None = None,
        budget_class: str | None = None,
    ) -> WorkerContextPacket:
        projection_context_sections = (
            self._builder_projection_context_service.build_context_sections(
                session_id=session.session_id,
            )
        )
        recent_raw_turn_sections = self._build_recent_raw_turn_sections(
            chapter=chapter,
        )
        source_ref_bundle = self._build_worker_source_ref_bundle(identity=identity)
        workspace_refs = self._list_workspace_refs(identity=identity)
        mode_sidecar_refs = self._list_mode_sidecar_ref_ids(
            identity=identity,
            slot_ids=self._requested_sidecar_slot_ids(context_requirements),
        )
        recent_turn_ref_count = sum(
            len(self._section_source_ref_ids(section))
            for section in recent_raw_turn_sections
        )
        packet_metadata = {
            "context_requirements": dict(context_requirements or {}),
            "reason_codes": list(reason_codes or []),
            "budget_class": budget_class,
            "worker_source_ref_bundle": source_ref_bundle.model_dump(mode="json"),
            "section_counts": {
                "core_projection_refs": len(projection_context_sections),
                "recent_raw_turn_refs": recent_turn_ref_count,
                "retrieval_refs": len(
                    [
                        *source_ref_bundle.retrieval_card_material_ids,
                        *source_ref_bundle.retrieval_expanded_chunk_material_ids,
                        *source_ref_bundle.retrieval_usage_material_ids,
                    ]
                ),
                "sidecar_refs": len(mode_sidecar_refs),
                "workspace_refs": len(workspace_refs),
            },
        }
        return WorkerContextPacket(
            packet_id=f"worker-packet-{uuid4().hex}",
            identity=identity,
            worker_id=worker_id,
            phase=phase,
            mode=mode,
            session_refs=[
                f"story_session:{session.session_id}",
                f"chapter_workspace:{chapter.chapter_workspace_id}",
            ],
            recent_turn_refs=[
                source_ref
                for section in recent_raw_turn_sections
                for source_ref in self._section_source_ref_ids(section)
            ],
            core_projection_refs=[
                self._projection_ref_id(section=section, index=index)
                for index, section in enumerate(projection_context_sections)
            ],
            retrieval_refs=[
                *source_ref_bundle.retrieval_card_material_ids,
                *source_ref_bundle.retrieval_expanded_chunk_material_ids,
                *source_ref_bundle.retrieval_usage_material_ids,
            ],
            sidecar_refs=mode_sidecar_refs,
            workspace_refs=workspace_refs,
            forbidden_context=list(self._DEFAULT_FORBIDDEN_CONTEXT),
            token_budget={
                "budget_class": budget_class or "default",
                "policy": "deterministic_bootstrap",
            },
            packet_metadata=packet_metadata,
        )

    def _build_recent_raw_turn_sections(
        self,
        *,
        chapter: ChapterWorkspace,
        window_size: int = 4,
    ) -> list[dict[str, object]]:
        entries = [
            entry
            for entry in self._story_session_service.list_discussion_entries(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if entry.role in {"user", "assistant"}
            and str(entry.content_text or "").strip()
        ]
        if not entries:
            return []
        window_entries = entries[-window_size:]
        return [
            {
                "section_id": "recent_raw_turn.raw_window",
                "label": "recent_raw_turns",
                "source_kind": "story_discussion_entry_window",
                "source_ref_ids": [entry.entry_id for entry in window_entries],
                "items": [
                    f"{entry.role}: {entry.content_text.strip()}"
                    for entry in window_entries
                ],
                "metadata_json": {
                    "window_size": len(window_entries),
                    "entry_roles": [entry.role for entry in window_entries],
                },
            }
        ]

    def _build_runtime_retrieval_packet_context(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> tuple[list[dict[str, object]], WorkerSourceRefBundle]:
        if self._runtime_workspace_material_service is None:
            return [], WorkerSourceRefBundle()
        retrieval_service = self._runtime_retrieval_cards()
        writer_visible_materials = retrieval_service.list_writer_visible_materials(
            identity=identity
        )
        card_ids = [
            material.material_id
            for material in writer_visible_materials
            if material.material_kind.value == "retrieval_card"
        ]
        expanded_ids = [
            material.material_id
            for material in writer_visible_materials
            if material.material_kind.value == "retrieval_expanded_chunk"
        ]
        if not card_ids and not expanded_ids:
            return [], WorkerSourceRefBundle()
        items = []
        for item in retrieval_service.list_writer_visible_context(identity=identity):
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            short_id = str(item.get("short_id") or "").strip()
            kind = str(item.get("kind") or "").strip()
            title = str(item.get("title") or "").strip()
            prefix = f"{short_id} " if short_id else ""
            title_prefix = f"{title}: " if title else ""
            items.append(f"{prefix}[{kind}] {title_prefix}{summary}".strip())
        return (
            [
                {
                    "section_id": "retrieval_card.writer_visible",
                    "label": "retrieval_cards",
                    "source_kind": "runtime_retrieval_card_summary",
                    "source_ref_ids": [*card_ids, *expanded_ids],
                    "items": items,
                    "metadata_json": {
                        "retrieval_card_count": len(card_ids),
                        "retrieval_expanded_count": len(expanded_ids),
                    },
                }
            ]
            if items
            else [],
            WorkerSourceRefBundle(
                retrieval_card_material_ids=card_ids,
                retrieval_expanded_chunk_material_ids=expanded_ids,
            ),
        )

    def _build_worker_source_ref_bundle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> WorkerSourceRefBundle:
        if self._runtime_workspace_material_service is None:
            return WorkerSourceRefBundle()
        return self._runtime_retrieval_cards().build_source_ref_bundle(
            identity=identity,
        )

    def _list_workspace_refs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> list[str]:
        if self._runtime_workspace_material_service is None:
            return []
        return [
            material.material_id
            for material in self._runtime_workspace_material_service.list_materials(
                identity=identity,
            )
            if material.material_kind
            not in {
                RuntimeWorkspaceMaterialKind.RULE_CARD,
                RuntimeWorkspaceMaterialKind.RULE_STATE_CARD,
            }
        ]

    def _build_longform_chapter_progress_sections(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity | None,
        command_kind: LongformTurnCommandKind | None,
    ) -> list[dict[str, object]]:
        if command_kind != LongformTurnCommandKind.WRITE_NEXT_SEGMENT:
            return []
        if self._longform_chapter_runtime_service is None:
            return []
        branch_head_id = (
            identity.branch_head_id
            if identity is not None
            else str(session.active_branch_head_id or "").strip()
        )
        if not branch_head_id:
            return []
        outline_progress = self._longform_chapter_runtime_service.effective_outline_progress(
            chapter=chapter,
            identity=identity,
        )
        if outline_progress is None:
            return []
        accepted_segments = self._accepted_story_segments(
            session=session,
            chapter=chapter,
        )
        latest_segment = accepted_segments[-1] if accepted_segments else None
        accepted_outline_ref = self._accepted_outline_ref(chapter=chapter)
        structured_outline = self._accepted_structured_outline(chapter=chapter)
        current_beat = (
            None
            if structured_outline is None
            else structured_outline.beat_by_id(outline_progress.current_beat_id)
        )
        source_ref_ids: list[str] = []
        if latest_segment is not None:
            source_ref_ids.append(latest_segment.artifact_id)
        if accepted_outline_ref is not None:
            source_ref_ids.append(accepted_outline_ref)
        source_ref_ids.extend(
            artifact_id
            for artifact_id in outline_progress.segment_by_beat_id.values()
            if str(artifact_id or "").strip()
        )
        items = [
            f"chapter_index: {chapter.chapter_index}",
            f"chapter_goal: {self._chapter_goal_text(chapter=chapter)}",
            f"accepted_segment_count: {len(accepted_segments)}",
            (
                "covered_beat_ids: "
                + (
                    ", ".join(outline_progress.covered_beat_ids)
                    if outline_progress.covered_beat_ids
                    else "(none)"
                )
            ),
        ]
        if current_beat is not None:
            items.extend(
                [
                    f"current_beat_id: {current_beat.beat_id}",
                    f"current_beat_order: {current_beat.order}",
                    f"current_beat_title: {current_beat.title}",
                    f"current_beat_goal: {current_beat.goal}",
                    (
                        "current_beat_must_include: "
                        + (
                            "; ".join(current_beat.must_include)
                            if current_beat.must_include
                            else "(none)"
                        )
                    ),
                    (
                        "current_beat_avoid: "
                        + (
                            "; ".join(current_beat.avoid)
                            if current_beat.avoid
                            else "(none)"
                        )
                    ),
                    (
                        "current_beat_continuity_notes: "
                        + (
                            "; ".join(current_beat.continuity_notes)
                            if current_beat.continuity_notes
                            else "(none)"
                        )
                    ),
                ]
            )
        if accepted_outline_ref is not None:
            items.append(f"accepted_outline_ref: {accepted_outline_ref}")
        if latest_segment is not None:
            items.append(
                "latest_accepted_segment_excerpt: "
                f"{self._excerpt(latest_segment.content_text)}"
            )
        items.append(
            "next_required_continuity_instruction: "
            "Write one segment for the current beat only; continue after the latest "
            "accepted segment; stop before later beats."
        )
        return [
            {
                "section_id": "mode_sidecar.longform.chapter_progress",
                "label": "chapter_progress",
                "source_kind": "longform_chapter_progress",
                "source_ref_ids": source_ref_ids,
                "items": items,
                "metadata_json": {
                    "section_family": "mode_sidecar",
                    "accepted_segment_count": len(accepted_segments),
                    "latest_accepted_segment_id": (
                        None if latest_segment is None else latest_segment.artifact_id
                    ),
                    "accepted_outline_ref": accepted_outline_ref,
                    "current_beat_id": outline_progress.current_beat_id,
                    "covered_beat_ids": list(outline_progress.covered_beat_ids),
                    "chapter_goal_present": bool(
                        str(chapter.chapter_goal or "").strip()
                    ),
                },
            }
        ]

    def _build_mode_sidecar_sections(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session_mode: str,
        packet_metadata: dict[str, object],
    ) -> list[dict[str, object]]:
        if self._runtime_workspace_material_service is None:
            return []
        mode_extension_profile = self._mode_extension_profile_from_identity(identity)
        if not mode_extension_profile:
            return []
        raw_slots = mode_extension_profile.get("slots")
        if not isinstance(raw_slots, list):
            return []
        sections: list[dict[str, object]] = []
        section_slot_ids: list[str] = []
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                continue
            if str(raw_slot.get("slot_kind") or "").strip() != "packet_sidecar":
                continue
            if not bool(raw_slot.get("enabled_by_default", False)):
                continue
            slot_id = str(raw_slot.get("slot_id") or "").strip()
            if not slot_id:
                continue
            materials = self._list_materials_for_sidecar_slot(
                identity=identity,
                slot_id=slot_id,
            )
            if not materials:
                continue
            section_slot_ids.append(slot_id)
            sections.append(
                {
                    "section_id": f"mode_sidecar.{session_mode}.{slot_id}",
                    "label": slot_id,
                    "source_kind": "runtime_mode_sidecar",
                    "source_ref_ids": [
                        material.material_id for material in materials
                    ],
                    "items": [
                        self._mode_sidecar_item_text(material.payload)
                        for material in materials
                    ],
                    "metadata_json": {
                        "section_family": "mode_sidecar",
                        "slot_id": slot_id,
                        "material_kinds": [
                            material.material_kind.value for material in materials
                        ],
                    },
                }
            )
        if section_slot_ids:
            packet_metadata["mode_sidecar_slot_ids"] = section_slot_ids
        return sections

    def _list_materials_for_sidecar_slot(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        slot_id: str,
    ) -> list[RuntimeWorkspaceMaterial]:
        if self._runtime_workspace_material_service is None:
            return []
        materials: list[RuntimeWorkspaceMaterial] = []
        for material_kind in packet_sidecar_material_kinds_for_slot(slot_id):
            materials.extend(
                self._runtime_workspace_material_service.list_materials(
                    identity=identity,
                    material_kind=material_kind,
                )
            )
        return materials

    def _list_mode_sidecar_ref_ids(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        slot_ids: list[str] | None = None,
    ) -> list[str]:
        if not slot_ids:
            return []
        mode_extension_profile = self._mode_extension_profile_from_identity(identity)
        if not mode_extension_profile:
            return []
        normalized_slot_ids = {
            normalized
            for slot_id in (slot_ids or [])
            if (normalized := str(slot_id or "").strip())
        }
        raw_slots = mode_extension_profile.get("slots")
        if not isinstance(raw_slots, list):
            return []
        ref_ids: list[str] = []
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                continue
            if str(raw_slot.get("slot_kind") or "").strip() != "packet_sidecar":
                continue
            if not bool(raw_slot.get("enabled_by_default", False)):
                continue
            slot_id = str(raw_slot.get("slot_id") or "").strip()
            if not slot_id:
                continue
            if slot_id not in normalized_slot_ids:
                continue
            ref_ids.extend(
                material.material_id
                for material in self._list_materials_for_sidecar_slot(
                    identity=identity,
                    slot_id=slot_id,
                )
            )
        return ref_ids

    @staticmethod
    def _requested_sidecar_slot_ids(
        context_requirements: dict[str, object] | None,
    ) -> list[str] | None:
        if not isinstance(context_requirements, dict):
            return None
        raw_slot_ids = context_requirements.get("sidecar_slot_ids")
        if not isinstance(raw_slot_ids, list):
            return None
        normalized_slot_ids = [
            normalized
            for slot_id in raw_slot_ids
            if (normalized := str(slot_id or "").strip())
        ]
        return normalized_slot_ids or None

    def _mode_extension_profile_from_identity(
        self,
        identity: MemoryRuntimeIdentity,
    ) -> dict[str, object] | None:
        if self._runtime_profile_snapshot_service is None:
            return None
        snapshot = self._runtime_profile_snapshot_service.require_snapshot(
            identity.runtime_profile_snapshot_id
        )
        compiled_profile = dict(snapshot.compiled_profile_json or {})
        mode_specific_settings = compiled_profile.get("mode_specific_settings")
        if not isinstance(mode_specific_settings, dict):
            return None
        payload = mode_specific_settings.get("mode_extension_profile")
        return dict(payload) if isinstance(payload, dict) else None

    def _build_longform_chapter_bridge_sections(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        identity: MemoryRuntimeIdentity,
        packet_metadata: dict[str, object],
    ) -> list[dict[str, object]]:
        if self._longform_chapter_runtime_service is None:
            return []
        if str(session.mode or "").strip().lower() != "longform":
            return []
        resolved = (
            self._longform_chapter_runtime_service.get_latest_bridge_material_for_target_chapter(
                story_id=identity.story_id,
                session_id=identity.session_id,
                branch_head_id=identity.branch_head_id,
                target_chapter_index=chapter.chapter_index,
                identity=identity,
            )
        )
        if resolved is None:
            return []
        material_id, bridge = resolved
        items = [
            normalized
            for normalized in (
                self._chapter_bridge_summary_text(bridge),
                self._chapter_bridge_goal_text(bridge),
                self._chapter_bridge_outline_text(bridge),
            )
            if normalized is not None
        ]
        if not items:
            return []
        packet_metadata["chapter_bridge_material_ref"] = material_id
        return [
            {
                "section_id": "mode_sidecar.longform.chapter_bridge_material",
                "label": "chapter_bridge_material",
                "source_kind": "mode_sidecar",
                "source_ref_ids": [
                    material_id,
                    *list(bridge.source_refs),
                    *list(bridge.continuity_refs),
                ],
                "items": items,
                "metadata_json": {
                    "section_family": "mode_sidecar",
                    "bridge_id": bridge.bridge_id,
                    "source_chapter_index": bridge.source_chapter_index,
                    "target_chapter_index": bridge.target_chapter_index,
                    "runtime_truth_owner": "rp_runtime",
                    "canonical_truth": False,
                },
            }
        ]

    @staticmethod
    def _chapter_bridge_summary_text(bridge: object) -> str | None:
        summary_text = str(getattr(bridge, "summary_text", "") or "").strip()
        if not summary_text:
            return None
        return f"Prior chapter bridge summary: {summary_text}"

    @staticmethod
    def _chapter_bridge_goal_text(bridge: object) -> str | None:
        goal_ref = str(getattr(bridge, "chapter_goal_ref", "") or "").strip()
        if not goal_ref:
            return None
        metadata_json = getattr(bridge, "metadata_json", {}) or {}
        if not isinstance(metadata_json, dict):
            metadata_json = {}
        chapter_goal = str(metadata_json.get("chapter_goal") or "").strip()
        if chapter_goal:
            return f"Current chapter goal: {chapter_goal}"
        return f"Current chapter goal ref: {goal_ref}"

    @staticmethod
    def _chapter_bridge_outline_text(bridge: object) -> str | None:
        outline_ref = str(getattr(bridge, "accepted_outline_ref", "") or "").strip()
        if not outline_ref:
            return None
        return f"Accepted outline ref: {outline_ref}"

    def _accepted_story_segments(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
    ) -> list[StoryArtifact]:
        return self._story_session_service.active_branch_accepted_segment_artifacts(
            session_id=session.session_id,
            chapter_index=chapter.chapter_index,
            chapter=chapter,
        )

    @staticmethod
    def _accepted_outline_ref(chapter: ChapterWorkspace) -> str | None:
        accepted_outline = chapter.accepted_outline_json or {}
        outline_ref = str(accepted_outline.get("artifact_id") or "").strip()
        return outline_ref or None

    @staticmethod
    def _accepted_structured_outline(
        chapter: ChapterWorkspace,
    ) -> LongformStructuredOutline | None:
        accepted_outline = chapter.accepted_outline_json or {}
        payload = accepted_outline.get("structured_outline")
        if isinstance(payload, dict):
            try:
                return LongformStructuredOutline.model_validate(payload)
            except ValueError:
                return None
        metadata = accepted_outline.get("metadata")
        if isinstance(metadata, dict):
            structured = metadata.get("structured_outline")
            if isinstance(structured, dict):
                try:
                    return LongformStructuredOutline.model_validate(structured)
                except ValueError:
                    return None
        return None

    @staticmethod
    def _accepted_outline_digest(chapter: ChapterWorkspace) -> str | None:
        accepted_outline = chapter.accepted_outline_json or {}
        structured_outline = ContextOrchestrationService._accepted_structured_outline(
            chapter=chapter
        )
        if structured_outline is not None:
            beat_summaries = [
                f"{beat.order}. {beat.title}: {beat.goal}"
                for beat in structured_outline.beats[:4]
            ]
            if beat_summaries:
                return " | ".join(beat_summaries)
        outline_text = str(accepted_outline.get("content_text") or "").strip()
        if outline_text:
            return ContextOrchestrationService._excerpt(outline_text)
        snapshot = chapter.builder_snapshot_json or {}
        outline_digest = snapshot.get("current_outline_digest")
        if isinstance(outline_digest, list):
            items = [str(item).strip() for item in outline_digest if str(item).strip()]
            if items:
                return " | ".join(items)
        return None

    @staticmethod
    def _chapter_goal_text(*, chapter: ChapterWorkspace) -> str:
        goal = str(chapter.chapter_goal or "").strip()
        return goal or "(not set)"

    @staticmethod
    def _excerpt(value: str | None, *, limit: int = 280) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return "(empty)"
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    @staticmethod
    def _mode_sidecar_item_text(payload: Mapping[str, object]) -> str:
        adjudication_summary = str(payload.get("adjudication_summary") or "").strip()
        if adjudication_summary:
            return adjudication_summary
        if "mechanics_state_patch" in payload:
            return (
                "mechanics_state_patch: "
                + str(payload.get("mechanics_state_patch") or {})
            )
        if "rule_refs" in payload:
            rule_refs = payload.get("rule_refs")
            if isinstance(rule_refs, list) and rule_refs:
                return "rule_refs: " + ", ".join(str(item).strip() for item in rule_refs)
        return str(payload).strip()

    @staticmethod
    def _projection_ref_id(*, section: dict[str, object], index: int) -> str:
        section_id = str(section.get("section_id") or "").strip()
        if section_id:
            return section_id
        label = str(section.get("label") or "").strip()
        if label:
            return f"projection_slot:{label}"
        return f"projection_slot:{index}"

    @staticmethod
    def _section_source_ref_ids(section: Mapping[str, object]) -> list[str]:
        raw_source_ref_ids = section.get("source_ref_ids")
        if not isinstance(raw_source_ref_ids, list):
            return []
        return [
            normalized
            for item in raw_source_ref_ids
            if (normalized := str(item).strip())
        ]

    def _runtime_retrieval_cards(self) -> RuntimeRetrievalCardService:
        return RuntimeRetrievalCardService(
            runtime_workspace_material_service=self._runtime_workspace_material_service
        )
