"""Deterministic context orchestration for writer and worker packets."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.story_runtime import (
    ChapterWorkspace,
    OrchestratorPlan,
    SpecialistResultBundle,
    StorySession,
)
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.models.worker_runtime_contracts import WorkerContextPacket
from rp.models.writing_runtime import WritingPacket

from .builder_projection_context_service import BuilderProjectionContextService
from .runtime_read_manifest_service import RuntimeReadManifestService
from .runtime_retrieval_card_service import RuntimeRetrievalCardService
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .story_session_service import StorySessionService
from .writing_packet_builder import WritingPacketBuilder


class ContextOrchestrationService:
    """Assemble deterministic writer and worker packets from stable read surfaces."""

    _DEFAULT_FORBIDDEN_CONTEXT = (
        "raw_authoritative_state_json",
        "tool_call_trace",
        "worker_chain_of_thought",
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
    ) -> None:
        self._story_session_service = story_session_service
        self._builder_projection_context_service = builder_projection_context_service
        self._writing_packet_builder = writing_packet_builder
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._runtime_read_manifest_service = runtime_read_manifest_service

    def build_writing_packet(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: OrchestratorPlan,
        specialist_bundle: SpecialistResultBundle,
        operation_mode: str = "writing",
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> WritingPacket:
        projection_context_sections = (
            self._builder_projection_context_service.build_context_sections(
                session_id=session.session_id,
            )
        )
        recent_raw_turn_sections = self._build_recent_raw_turn_sections(
            chapter=chapter,
        )
        runtime_retrieval_sections: list[dict[str, object]] = []
        packet_metadata: dict[str, object] = {}
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
        packet = self._writing_packet_builder.build(
            session=session,
            chapter=chapter,
            plan=plan,
            runtime_identity=runtime_identity,
            operation_mode=operation_mode,
            projection_context_sections=projection_context_sections,
            recent_raw_turn_sections=recent_raw_turn_sections,
            runtime_retrieval_sections=runtime_retrieval_sections,
            runtime_writer_hints=list(specialist_bundle.writer_hints),
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
        ]

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
