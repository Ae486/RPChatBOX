"""Focused facade for Runtime Workspace main-chain material writes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.mode_extension_contracts import (
    RuleCardMaterial,
    RuleStateCardMaterial,
)
from rp.models.runtime_workspace_material import (
    RUNTIME_WORKSPACE_MATERIAL_LAYER,
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.story_runtime import StoryArtifact
from rp.models.worker_runtime_contracts import WorkerExecutionRequest, WorkerResult
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from rp.models.writing_runtime import WritingPacket

from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService


_RUNTIME_WORKSPACE_DOMAIN = "chapter"


@dataclass(frozen=True)
class WriterPacketSurfaceRefs:
    """Recorded Runtime Workspace refs produced while preparing the writer path."""

    writer_input_material_id: str | None = None
    packet_material_id: str | None = None


@dataclass(frozen=True)
class WorkerExecutionSurfaceRefs:
    """Recorded Runtime Workspace refs produced by one pre-write worker run."""

    evidence_material_id: str | None = None
    candidate_material_id: str | None = None


@dataclass(frozen=True)
class WriterOutputSurfaceRefs:
    """Recorded Runtime Workspace refs produced while finalizing writer output."""

    writer_output_material_id: str | None = None
    token_usage_material_id: str | None = None


class StoryRuntimeWorkspaceFacade:
    """Keep story-runtime material writes narrow and centralized."""

    def __init__(
        self,
        *,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService | None,
    ) -> None:
        self._runtime_workspace_material_service = runtime_workspace_material_service

    def record_writer_packet_surface(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        packet: WritingPacket,
    ) -> WriterPacketSurfaceRefs:
        if identity is None or self._runtime_workspace_material_service is None:
            return WriterPacketSurfaceRefs()

        recent_turn_ref_ids = _unique_non_blank(
            source_ref_id
            for section in packet.recent_raw_turn_sections
            for source_ref_id in section.source_ref_ids
        )
        retrieval_ref_ids = _unique_non_blank(
            source_ref_id
            for section in packet.retrieval_card_sections
            for source_ref_id in section.source_ref_ids
        )
        writer_input_material_id = self._record_material_id(
            RuntimeWorkspaceMaterial(
                material_id=f"writer-input-ref:{packet.packet_id}",
                material_kind=RuntimeWorkspaceMaterialKind.WRITER_INPUT_REF,
                identity=identity,
                domain=_RUNTIME_WORKSPACE_DOMAIN,
                domain_path=(
                    f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.writer_input"
                ),
                source_refs=[
                    *_discussion_entry_source_refs(recent_turn_ref_ids),
                    *_runtime_workspace_material_source_refs(retrieval_ref_ids),
                ],
                payload={
                    "packet_id": packet.packet_id,
                    "output_kind": packet.output_kind,
                    "phase": packet.phase,
                    "recent_turn_ref_ids": recent_turn_ref_ids,
                    "retrieval_ref_ids": retrieval_ref_ids,
                    "user_instruction_preview": _preview(packet.user_instruction),
                    "writer_contract_keys": sorted(packet.writer_contract.keys()),
                },
                visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                created_by="story_runtime.build_packet",
            )
        )
        packet_source_refs = _runtime_workspace_material_source_refs(
            [writer_input_material_id] if writer_input_material_id else []
        )
        packet_material_id = self._record_material_id(
            RuntimeWorkspaceMaterial(
                material_id=f"packet-ref:{packet.packet_id}",
                material_kind=RuntimeWorkspaceMaterialKind.PACKET_REF,
                identity=identity,
                domain=_RUNTIME_WORKSPACE_DOMAIN,
                domain_path=f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.packet",
                source_refs=packet_source_refs,
                payload={
                    "packet_id": packet.packet_id,
                    "output_kind": packet.output_kind,
                    "phase": packet.phase,
                    "runtime_read_manifest_id": str(
                        packet.metadata.get("runtime_read_manifest_id") or ""
                    ).strip()
                    or None,
                    "context_section_labels": [
                        str(section.get("label") or "").strip()
                        for section in packet.context_sections
                        if str(section.get("label") or "").strip()
                    ],
                    "section_counts": {
                        "core_view": len(packet.core_view_sections),
                        "recent_raw_turn": len(packet.recent_raw_turn_sections),
                        "mode_sidecar": len(packet.mode_sidecar_sections),
                        "retrieval_card": len(packet.retrieval_card_sections),
                        "review_overlay": len(packet.review_overlay_sections),
                    },
                    "packet_summary_metadata": deepcopy(packet.packet_summary_metadata),
                },
                visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                created_by="story_runtime.build_packet",
            )
        )
        return WriterPacketSurfaceRefs(
            writer_input_material_id=writer_input_material_id,
            packet_material_id=packet_material_id,
        )

    def record_prewrite_worker_surface(
        self,
        *,
        request: WorkerExecutionRequest,
        result: WorkerResult,
    ) -> WorkerExecutionSurfaceRefs:
        if self._runtime_workspace_material_service is None:
            return WorkerExecutionSurfaceRefs()

        source_refs = []
        if request.context_packet_ref:
            source_refs.append(
                MemorySourceRef(
                    source_type="worker_context_packet",
                    source_id=request.context_packet_ref,
                    layer="runtime_worker",
                    domain=_RUNTIME_WORKSPACE_DOMAIN,
                    entry_id=request.context_packet_ref,
                    metadata={
                        "worker_id": request.worker_id,
                        "phase": request.phase,
                    },
                )
            )
        source_refs.extend(_runtime_workspace_material_source_refs(result.evidence_refs))
        evidence_material_id = self._record_material_id(
            RuntimeWorkspaceMaterial(
                material_id=f"worker-evidence:{request.request_id}",
                material_kind=RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE,
                identity=request.identity,
                domain=_RUNTIME_WORKSPACE_DOMAIN,
                domain_path=(
                    f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.worker."
                    f"{request.worker_id}.evidence"
                ),
                source_refs=source_refs,
                payload={
                    "request_id": request.request_id,
                    "worker_id": request.worker_id,
                    "phase": request.phase,
                    "result_status": result.result_status.value,
                    "context_packet_ref": request.context_packet_ref,
                    "reason_codes": list(request.reason_codes),
                    "writer_hints": deepcopy(result.writer_hints),
                    "validation_findings": deepcopy(result.validation_findings),
                    "evidence_refs": list(result.evidence_refs),
                    "trace_summary": deepcopy(result.trace_summary),
                },
                visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                created_by="story_runtime.worker_execution",
            )
        )
        candidate_payload = {
            "request_id": request.request_id,
            "worker_id": request.worker_id,
            "phase": request.phase,
            "projection_refresh_requests": deepcopy(
                result.projection_refresh_requests
            ),
            "proposal_candidates": deepcopy(result.proposal_candidates),
            "recall_candidates": deepcopy(result.recall_candidates),
            "archival_candidates": deepcopy(result.archival_candidates),
        }
        has_candidate_payload = any(
            candidate_payload[key]
            for key in (
                "projection_refresh_requests",
                "proposal_candidates",
                "recall_candidates",
                "archival_candidates",
            )
        )
        candidate_material_id: str | None = None
        if has_candidate_payload:
            candidate_material_id = self._record_material_id(
                RuntimeWorkspaceMaterial(
                    material_id=f"worker-candidate:{request.request_id}",
                    material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
                    identity=request.identity,
                    domain=_RUNTIME_WORKSPACE_DOMAIN,
                    domain_path=(
                        f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.worker."
                        f"{request.worker_id}.candidate"
                    ),
                    source_refs=_runtime_workspace_material_source_refs(
                        [evidence_material_id] if evidence_material_id else []
                    )
                    or source_refs,
                    payload=candidate_payload,
                    visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                    created_by="story_runtime.worker_execution",
                )
            )
        return WorkerExecutionSurfaceRefs(
            evidence_material_id=evidence_material_id,
            candidate_material_id=candidate_material_id,
        )

    def record_writer_output_surface(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        packet: WritingPacket,
        artifact: StoryArtifact,
        result: WritingWorkerExecutionResult,
        linked_discussion_entry_id: str | None = None,
    ) -> WriterOutputSurfaceRefs:
        if identity is None or self._runtime_workspace_material_service is None:
            return WriterOutputSurfaceRefs()
        packet_material_id = _optional_text(
            packet.metadata.get("runtime_workspace_packet_material_id")
        )
        writer_input_material_id = _optional_text(
            packet.metadata.get("runtime_workspace_writer_input_material_id")
        )
        source_material_ids = [
            material_id
            for material_id in (
                packet_material_id,
                writer_input_material_id,
            )
            if material_id
        ]
        writer_output_material_id = self._record_material_id(
            RuntimeWorkspaceMaterial(
                material_id=f"writer-output-ref:{artifact.artifact_id}",
                material_kind=RuntimeWorkspaceMaterialKind.WRITER_OUTPUT_REF,
                identity=identity,
                domain=_RUNTIME_WORKSPACE_DOMAIN,
                domain_path=f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.writer_output",
                source_refs=_runtime_workspace_material_source_refs(source_material_ids),
                payload={
                    "packet_id": packet.packet_id,
                    "operation_mode": packet.operation_mode,
                    "artifact_id": artifact.artifact_id,
                    "artifact_kind": artifact.artifact_kind.value,
                    "artifact_status": artifact.status.value,
                    "artifact_revision": artifact.revision,
                    "linked_discussion_entry_id": linked_discussion_entry_id,
                    "runtime_read_manifest_id": _optional_text(
                        packet.metadata.get("runtime_read_manifest_id")
                    ),
                },
                visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                created_by="story_runtime.persist_generated_artifact",
            )
        )
        token_usage_material_id: str | None = None
        if result.usage_metadata:
            token_usage_material_id = self._record_material_id(
                RuntimeWorkspaceMaterial(
                    material_id=f"writer-usage:{identity.turn_id}:{packet.packet_id}",
                    material_kind=RuntimeWorkspaceMaterialKind.TOKEN_USAGE_METADATA,
                    identity=identity,
                    domain=_RUNTIME_WORKSPACE_DOMAIN,
                    domain_path=(
                        f"{_RUNTIME_WORKSPACE_DOMAIN}.runtime_workspace.writer_usage"
                    ),
                    source_refs=_runtime_workspace_material_source_refs(
                        [
                            material_id
                            for material_id in (
                                *source_material_ids,
                                writer_output_material_id,
                            )
                            if material_id
                        ]
                    ),
                    payload={
                        "packet_id": packet.packet_id,
                        "artifact_id": artifact.artifact_id,
                        "operation_mode": result.operation_mode,
                        "usage_metadata": deepcopy(result.usage_metadata),
                    },
                    visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
                    created_by="story_runtime.persist_generated_artifact",
                )
            )
        return WriterOutputSurfaceRefs(
            writer_output_material_id=writer_output_material_id,
            token_usage_material_id=token_usage_material_id,
        )

    def record_rule_card_material(
        self,
        *,
        material: RuleCardMaterial,
        domain: str = "rule_state",
        visibility: str = RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        created_by: str = "story_runtime.mode_extension",
    ) -> str | None:
        return self._record_mode_sidecar_material(
            identity=material.identity,
            material_id=material.material_id,
            material_kind=RuntimeWorkspaceMaterialKind.RULE_CARD,
            domain=domain,
            source_refs=_mode_extension_source_refs(
                source_ref_ids=material.source_refs,
                domain=domain,
                material_kind=RuntimeWorkspaceMaterialKind.RULE_CARD,
            ),
            payload={
                "rule_refs": list(material.rule_refs),
                "adjudication_summary": material.adjudication_summary,
                "source_refs": list(material.source_refs),
                "metadata_json": deepcopy(material.metadata_json),
            },
            visibility=visibility,
            created_by=created_by,
        )

    def record_rule_state_card_material(
        self,
        *,
        material: RuleStateCardMaterial,
        domain: str = "rule_state",
        visibility: str = RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        created_by: str = "story_runtime.mode_extension",
    ) -> str | None:
        return self._record_mode_sidecar_material(
            identity=material.identity,
            material_id=material.material_id,
            material_kind=RuntimeWorkspaceMaterialKind.RULE_STATE_CARD,
            domain=domain,
            source_refs=_mode_extension_source_refs(
                source_ref_ids=material.source_refs,
                domain=domain,
                material_kind=RuntimeWorkspaceMaterialKind.RULE_STATE_CARD,
            ),
            payload={
                "mechanics_state_patch": deepcopy(material.mechanics_state_patch),
                "status_effects": deepcopy(material.status_effects),
                "source_refs": list(material.source_refs),
                "metadata_json": deepcopy(material.metadata_json),
            },
            visibility=visibility,
            created_by=created_by,
        )

    def _record_material_id(self, material: RuntimeWorkspaceMaterial) -> str | None:
        if self._runtime_workspace_material_service is None:
            return None
        existing = self._runtime_workspace_material_service.get_material(
            identity=material.identity,
            material_id=material.material_id,
        )
        if existing is not None:
            return existing.material_id
        receipt = self._runtime_workspace_material_service.record_material(material)
        return receipt.material.material_id

    def _record_mode_sidecar_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        material_kind: RuntimeWorkspaceMaterialKind,
        domain: str,
        source_refs: list[MemorySourceRef],
        payload: dict[str, Any],
        visibility: str,
        created_by: str,
    ) -> str | None:
        return self._record_material_id(
            RuntimeWorkspaceMaterial(
                material_id=material_id,
                material_kind=material_kind,
                identity=identity,
                domain=domain,
                domain_path=f"{domain}.runtime_workspace.{material_kind.value}",
                source_refs=source_refs,
                payload=payload,
                visibility=visibility,
                created_by=created_by,
            )
        )


def _discussion_entry_source_refs(entry_ids: list[str]) -> list[MemorySourceRef]:
    return [
        MemorySourceRef(
            source_type="story_discussion_entry",
            source_id=entry_id,
            layer="runtime_workspace",
            domain=_RUNTIME_WORKSPACE_DOMAIN,
            entry_id=entry_id,
        )
        for entry_id in entry_ids
    ]


def _runtime_workspace_material_source_refs(
    material_ids: list[str],
) -> list[MemorySourceRef]:
    return [
        MemorySourceRef(
            source_type="runtime_workspace_material",
            source_id=material_id,
            layer="runtime_workspace",
            domain=_RUNTIME_WORKSPACE_DOMAIN,
            entry_id=material_id,
        )
        for material_id in material_ids
    ]


def _mode_extension_source_refs(
    *,
    source_ref_ids: list[str],
    domain: str,
    material_kind: RuntimeWorkspaceMaterialKind,
) -> list[MemorySourceRef]:
    return [
        MemorySourceRef(
            source_type="mode_extension_source_ref",
            source_id=source_ref_id,
            layer=RUNTIME_WORKSPACE_MATERIAL_LAYER,
            domain=domain,
            block_id=f"{domain}.runtime_workspace",
            metadata={
                "mode_extension_sidecar_kind": material_kind.value,
                "raw_source_ref": source_ref_id,
            },
        )
        for source_ref_id in _unique_non_blank(source_ref_ids)
    ]


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _preview(value: str, *, limit: int = 240) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _unique_non_blank(values: Any) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values
