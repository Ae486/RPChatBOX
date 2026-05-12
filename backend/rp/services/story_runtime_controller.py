"""Active-story longform read/list/activate facade."""

from __future__ import annotations

from typing import Any, cast

from rp.models.block_view import BlockSource, RpBlockView
from rp.models.core_mutation import DirectCoreEditRequest
from rp.models.archival_evolution import ArchivalEvolutionRequest
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import (
    MemoryBlockProposalSubmitRequest,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProvenanceResult,
    VersionListResult,
)
from rp.models.runtime_config_contracts import (
    RuntimeConfigControlReceipt,
    RuntimeConfigPatchRequest,
)
from rp.models.runtime_identity import BranchControlReceipt
from rp.models.memory_inspection import RecallReviewCommand
from rp.models.revision_overlay_contracts import (
    DraftDocumentRecord,
    ReviewOverlayMode,
    ReviewOverlayRecord,
    RevisionAnchorRef,
)
from rp.models.story_runtime import (
    ChapterWorkspaceSnapshot,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StoryActivationResult,
    StorySession,
)
from rp.models.story_brainstorm import (
    BrainstormApplyReceipt,
    BrainstormApplyRequest,
    BrainstormItemUpdateRequest,
    BrainstormSession,
    BrainstormSessionStartRequest,
    BrainstormSummarizeRequest,
)
from .memory_inspection_read_service import MemoryInspectionReadService
from .memory_inspection_service import MemoryInspectionService
from .projection_read_service import ProjectionReadService
from .provenance_read_service import ProvenanceReadService
from .recall_scene_transcript_ingestion_service import (
    RecallSceneTranscriptIngestionService,
)
from .story_runtime_debug_query_service import StoryRuntimeDebugQueryService
from .story_runtime_identity_service import StoryRuntimeIdentityService
from .story_runtime_migration_service import StoryRuntimeMigrationService
from .runtime_config_control_service import RuntimeConfigControlService
from .runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from .draft_materialization_service import DraftMaterializationService
from .revision_overlay_service import RevisionOverlayService
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialServiceError
from .rp_block_read_service import RpBlockReadService
from .story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    MemoryBlockProposalNotFoundError,
    StoryBlockMutationService,
)
from .story_brainstorm_service import StoryBrainstormService
from .story_block_consumer_state_service import StoryBlockConsumerStateService
from .story_activation_service import StoryActivationService
from .story_session_service import StorySessionService
from .version_history_read_service import VersionHistoryReadService


class MemoryBlockHistoryUnsupportedError(RuntimeError):
    """Raised when a Block envelope has no read-only history/provenance backend."""


class StoryRuntimeController:
    """Thin facade for activation, read-model access, and governed Block mutation."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        story_activation_service: StoryActivationService,
        version_history_read_service: VersionHistoryReadService,
        provenance_read_service: ProvenanceReadService,
        projection_read_service: ProjectionReadService,
        memory_inspection_read_service: MemoryInspectionReadService,
        memory_inspection_service: MemoryInspectionService | None = None,
        rp_block_read_service: RpBlockReadService,
        story_block_mutation_service: StoryBlockMutationService | None = None,
        story_block_consumer_state_service: StoryBlockConsumerStateService
        | None = None,
        recall_scene_transcript_ingestion_service: (
            RecallSceneTranscriptIngestionService | None
        ) = None,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
        story_runtime_identity_service: StoryRuntimeIdentityService | None = None,
        story_runtime_debug_query_service: StoryRuntimeDebugQueryService | None = None,
        story_runtime_migration_service: StoryRuntimeMigrationService | None = None,
        runtime_config_control_service: RuntimeConfigControlService | None = None,
        draft_materialization_service: DraftMaterializationService | None = None,
        revision_overlay_service: RevisionOverlayService | None = None,
        story_brainstorm_service: StoryBrainstormService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._story_activation_service = story_activation_service
        self._version_history_read_service = version_history_read_service
        self._provenance_read_service = provenance_read_service
        self._projection_read_service = projection_read_service
        self._memory_inspection_read_service = memory_inspection_read_service
        self._memory_inspection_service = memory_inspection_service
        self._rp_block_read_service = rp_block_read_service
        self._story_block_mutation_service = story_block_mutation_service
        self._story_block_consumer_state_service = story_block_consumer_state_service
        self._recall_scene_transcript_ingestion_service = (
            recall_scene_transcript_ingestion_service
        )
        self._runtime_profile_snapshot_service = runtime_profile_snapshot_service
        self._story_runtime_identity_service = story_runtime_identity_service
        self._story_runtime_debug_query_service = story_runtime_debug_query_service
        self._story_runtime_migration_service = story_runtime_migration_service
        self._runtime_config_control_service = runtime_config_control_service
        self._draft_materialization_service = draft_materialization_service
        self._revision_overlay_service = revision_overlay_service
        self._story_brainstorm_service = story_brainstorm_service

    def activate_workspace(self, *, workspace_id: str) -> StoryActivationResult:
        return self._story_activation_service.activate_workspace(
            workspace_id=workspace_id
        )

    def list_sessions(self) -> list[StorySession]:
        return self._story_session_service.list_sessions()

    def read_session(self, *, session_id: str) -> ChapterWorkspaceSnapshot:
        session = self._require_session(session_id)
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=session.current_chapter_index,
        )

    def read_chapter(
        self, *, session_id: str, chapter_index: int
    ) -> ChapterWorkspaceSnapshot:
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=chapter_index,
        )

    def update_runtime_story_config(
        self,
        *,
        session_id: str,
        patch: dict[str, Any],
    ) -> ChapterWorkspaceSnapshot:
        if self._runtime_config_control_service is not None:
            snapshot, _receipt = self.publish_runtime_config_patch(
                RuntimeConfigPatchRequest(
                    session_id=session_id,
                    runtime_story_config=patch,
                )
            )
            return snapshot
        if self._runtime_profile_snapshot_service is None:
            raise RuntimeError("runtime_profile_snapshot_service_not_configured")
        updated_session = self._story_session_service.update_session(
            session_id=session_id,
            runtime_story_config_patch=patch,
        )
        compiled = self._runtime_profile_snapshot_service.compile_snapshot(
            story_id=updated_session.story_id,
            session_id=updated_session.session_id,
            mode=updated_session.mode,
            created_from="story_runtime.runtime_config_patch",
        )
        self._runtime_profile_snapshot_service.publish_snapshot(
            compiled.runtime_profile_snapshot_id
        )
        self._story_session_service.commit()
        return self._story_session_service.build_chapter_snapshot(
            session_id=updated_session.session_id,
            chapter_index=updated_session.current_chapter_index,
        )

    def publish_runtime_config_patch(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> tuple[ChapterWorkspaceSnapshot, RuntimeConfigControlReceipt]:
        if self._runtime_config_control_service is None:
            raise RuntimeError("runtime_config_control_service_not_configured")
        session_id = str(request.session_id or "").strip()
        if not session_id:
            raise ValueError("runtime_config_session_id_required")
        receipt = self._runtime_config_control_service.publish_patch(request)
        self._story_session_service.commit()
        session = self._require_session(session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=session.current_chapter_index,
        )
        return snapshot, receipt

    def list_runtime_config_control_history(
        self,
        *,
        session_id: str,
    ) -> list[RuntimeConfigControlReceipt]:
        if self._runtime_config_control_service is None:
            raise RuntimeError("runtime_config_control_service_not_configured")
        self._require_session(session_id)
        return self._runtime_config_control_service.list_control_history(
            session_id=session_id
        )

    def create_branch_from_turn(
        self,
        *,
        session_id: str,
        origin_turn_id: str,
        branch_name: str | None = None,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        receipt = self._require_story_runtime_identity_service().create_branch_from_turn(
            session_id=session_id,
            origin_turn_id=origin_turn_id,
            actor=actor,
            branch_name=branch_name,
            metadata=metadata,
        )
        self._story_session_service.commit()
        session = self._require_session(session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=session.current_chapter_index,
        )
        return snapshot, receipt

    def switch_branch(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        receipt = self._require_story_runtime_identity_service().switch_branch(
            session_id=session_id,
            target_branch_head_id=branch_head_id,
            actor=actor,
            metadata=metadata,
        )
        self._story_session_service.commit()
        session = self._require_session(session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=session.current_chapter_index,
        )
        return snapshot, receipt

    def delete_branch(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        receipt = self._require_story_runtime_identity_service().delete_branch(
            session_id=session_id,
            branch_head_id=branch_head_id,
            actor=actor,
            metadata=metadata,
        )
        self._story_session_service.commit()
        session = self._require_session(session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=session.current_chapter_index,
        )
        return snapshot, receipt

    def rollback_to_turn(
        self,
        *,
        session_id: str,
        target_turn_id: str,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        receipt = self._require_story_runtime_identity_service().rollback_to_turn(
            session_id=session_id,
            target_turn_id=target_turn_id,
            actor=actor,
            metadata=metadata,
        )
        self._story_session_service.commit()
        session = self._require_session(session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=session.current_chapter_index,
        )
        return snapshot, receipt

    def read_revision_review_surface(
        self,
        *,
        session_id: str,
        artifact_id: str,
        mode: str = "viewing",
    ) -> dict[str, Any]:
        """Return the R6 review surface for a draft artifact without making it truth."""

        session = self._require_session(session_id)
        artifact = self._require_draft_artifact(
            session_id=session_id,
            artifact_id=artifact_id,
        )
        identity = self._revision_identity_from_artifact(
            session=session,
            artifact=artifact,
        )
        draft_document, overlay = self._ensure_revision_overlay(
            identity=identity,
            artifact=artifact,
            mode=mode,
        )
        inspection = self._require_revision_overlay_service().inspect_overlay(
            identity=identity,
            overlay_id=overlay.overlay_id,
        )
        return {
            "session_id": session_id,
            "artifact_id": artifact.artifact_id,
            "draft_text": artifact.content_text,
            "identity": identity.model_dump(mode="json"),
            "draft_document": draft_document.model_dump(mode="json"),
            "overlay": inspection.overlay.model_dump(mode="json"),
            "comments": [item.model_dump(mode="json") for item in inspection.comments],
            "tracked_changes": [
                item.model_dump(mode="json") for item in inspection.tracked_changes
            ],
            "active_comment_refs": list(inspection.active_comment_refs),
            "active_tracked_change_refs": list(inspection.active_tracked_change_refs),
            "runtime_truth_owner": "rp_runtime",
            "superdoc_truth_owner": False,
            "canonical_truth": False,
        }

    def update_revision_draft_artifact(
        self,
        *,
        session_id: str,
        artifact_id: str,
        content_text: str,
    ) -> ChapterWorkspaceSnapshot:
        artifact = self._require_draft_artifact(
            session_id=session_id,
            artifact_id=artifact_id,
        )
        metadata = {
            **dict(artifact.metadata or {}),
            "manual_revision_edit": True,
            "manual_revision_edit_source": "longform_review_surface",
        }
        self._story_session_service.update_artifact(
            artifact_id=artifact.artifact_id,
            content_text=content_text,
            metadata=metadata,
        )
        self._story_session_service.commit()
        session = self._require_session(session_id)
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=session.current_chapter_index,
        )

    def add_revision_comment(
        self,
        *,
        session_id: str,
        artifact_id: str,
        block_id: str,
        instruction_text: str,
        selected_excerpt: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        superdoc_anchor_id: str | None = None,
    ) -> dict[str, Any]:
        surface = self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )
        identity = MemoryRuntimeIdentity.model_validate(surface["identity"])
        overlay = surface["overlay"]
        block = self._surface_block(surface=surface, block_id=block_id)
        anchor = RevisionAnchorRef(
            anchor_scope="single_block",
            block_ids=[block_id],
            start_offset=start_offset,
            end_offset=end_offset,
            selected_excerpt_hash=block.get("selected_excerpt_hash"),
            superdoc_anchor_id=superdoc_anchor_id,
            metadata_json={"adapter_surface": "flutter_native_r6"},
        )
        self._require_revision_overlay_service().add_comment(
            identity=identity,
            overlay_id=str(overlay["overlay_id"]),
            anchor_ref=anchor,
            instruction_text=instruction_text,
            selected_excerpt=selected_excerpt or str(block.get("selected_excerpt") or ""),
        )
        self._story_session_service.commit()
        return self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )

    def add_revision_tracked_change(
        self,
        *,
        session_id: str,
        artifact_id: str,
        block_id: str,
        original_text: str | None = None,
        suggested_text: str | None = None,
    ) -> dict[str, Any]:
        surface = self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )
        identity = MemoryRuntimeIdentity.model_validate(surface["identity"])
        overlay = surface["overlay"]
        block = self._surface_block(surface=surface, block_id=block_id)
        anchor = RevisionAnchorRef(
            anchor_scope="single_block",
            block_ids=[block_id],
            selected_excerpt_hash=block.get("selected_excerpt_hash"),
            metadata_json={"adapter_surface": "flutter_native_r6"},
        )
        self._require_revision_overlay_service().add_tracked_change(
            identity=identity,
            overlay_id=str(overlay["overlay_id"]),
            anchor_ref=anchor,
            change_kind="replace",
            original_text=original_text or str(block.get("text") or ""),
            suggested_text=suggested_text,
        )
        self._story_session_service.commit()
        return self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )

    def resolve_revision_comment(
        self,
        *,
        session_id: str,
        artifact_id: str,
        comment_id: str,
    ) -> dict[str, Any]:
        surface = self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )
        identity = MemoryRuntimeIdentity.model_validate(surface["identity"])
        self._require_revision_overlay_service().resolve_comment(
            identity=identity,
            comment_id=comment_id,
        )
        self._story_session_service.commit()
        return self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )

    def delete_revision_comment(
        self,
        *,
        session_id: str,
        artifact_id: str,
        comment_id: str,
    ) -> dict[str, Any]:
        surface = self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )
        identity = MemoryRuntimeIdentity.model_validate(surface["identity"])
        self._require_revision_overlay_service().delete_comment(
            identity=identity,
            comment_id=comment_id,
        )
        self._story_session_service.commit()
        return self.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode="suggesting",
        )

    def close_current_scene(self, *, session_id: str) -> ChapterWorkspaceSnapshot:
        chapter = self._story_session_service.close_current_scene(session_id=session_id)
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=chapter.chapter_index,
        )
        self._materialize_scene_transcript(snapshot=snapshot)
        self._story_session_service.commit()
        return snapshot

    def list_memory_authoritative(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_authoritative_objects(
            session_id=session_id
        )

    def list_memory_projection(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_projection_slots(
            session_id=session_id
        )

    def inspect_visible_memory(
        self,
        *,
        session_id: str,
        identity: MemoryRuntimeIdentity,
        layers: list[str] | None = None,
        domains: list[str] | None = None,
        include_hidden_audit: bool = False,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        if identity.session_id != session.session_id:
            raise ValueError("memory_inspection_identity_session_mismatch")
        if identity.story_id != session.story_id:
            raise ValueError("memory_inspection_identity_story_mismatch")
        if self._memory_inspection_service is None:
            raise RuntimeError("memory_inspection_service_not_configured")
        return self._memory_inspection_service.inspect_visible_memory(
            identity=identity,
            layers=layers,
            domains=domains,
            include_hidden_audit=include_hidden_audit,
        )

    def list_memory_blocks(
        self,
        *,
        session_id: str,
        layer: Layer | None = None,
        source: BlockSource | None = None,
    ) -> list[dict]:
        self._require_session(session_id)
        return [
            block.model_dump(mode="json")
            for block in self._rp_block_read_service.list_blocks(
                session_id=session_id,
                layer=layer,
                source=source,
            )
        ]

    def read_memory_overview(self, *, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        chapter = self._story_session_service.get_current_chapter(session_id)
        blocks = self._rp_block_read_service.list_blocks(session_id=session_id)
        proposals = self._memory_inspection_read_service.list_proposals(
            story_id=session.story_id,
            session_id=session_id,
        )
        consumers = self.list_memory_block_consumers(session_id=session_id)
        by_layer = self._count_values(block.layer.value for block in blocks)
        by_source = self._count_values(block.source for block in blocks)
        proposal_status_counts = self._count_values(
            str(item.get("status") or "unknown") for item in proposals
        )
        dirty_consumers = [item for item in consumers if bool(item.get("dirty"))]
        return {
            "session_id": session.session_id,
            "story_id": session.story_id,
            "current_chapter_index": session.current_chapter_index,
            "current_phase": session.current_phase.value,
            "chapter_workspace_id": (
                chapter.chapter_workspace_id if chapter is not None else None
            ),
            "blocks": {
                "total": len(blocks),
                "by_layer": by_layer,
                "by_source": by_source,
            },
            "layers": self._memory_overview_layers(by_layer),
            "proposals": {
                "total": len(proposals),
                "by_status": proposal_status_counts,
            },
            "consumers": {
                "total": len(consumers),
                "dirty": len(dirty_consumers),
                "dirty_consumer_keys": [
                    str(item.get("consumer_key"))
                    for item in dirty_consumers
                    if item.get("consumer_key") is not None
                ],
                "items": consumers,
            },
            "boundaries": [
                "authoritative_mutation_requires_proposal_apply",
                "projection_blocks_are_read_side_maintenance_views",
                "runtime_workspace_blocks_are_read_only_current_turn_scratch",
                "recall_and_archival_are_retrieval_backed_not_block_native",
                "overview_does_not_sync_or_compile_consumers",
            ],
        }

    def read_runtime_inspection(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        target_chapter_index: int | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        self._require_session(session_id)
        if self._story_runtime_debug_query_service is None:
            raise RuntimeError("story_runtime_debug_query_service_not_configured")
        return self._story_runtime_debug_query_service.read_runtime_inspection(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            target_chapter_index=target_chapter_index,
            limit=limit,
        )

    def read_story_evolution_history(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        self._require_session(session_id)
        if self._story_runtime_debug_query_service is None:
            raise RuntimeError("story_runtime_debug_query_service_not_configured")
        return self._story_runtime_debug_query_service.read_story_evolution_history(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            limit=limit,
        )

    def read_runtime_migration_summary(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        self._require_session(session_id)
        if self._story_runtime_migration_service is None:
            raise RuntimeError("story_runtime_migration_service_not_configured")
        return self._story_runtime_migration_service.read_runtime_migration_summary(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            limit=limit,
        )

    def get_memory_block(self, *, session_id: str, block_id: str) -> dict | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        return block.model_dump(mode="json")

    async def read_memory_block_versions(
        self,
        *,
        session_id: str,
        block_id: str,
    ) -> VersionListResult | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        block_ref = self._block_ref(block)
        if block.layer == Layer.CORE_STATE_AUTHORITATIVE:
            return self._version_history_read_service.list_versions(
                block_ref,
                session_id=session_id,
            )
        if block.layer == Layer.CORE_STATE_PROJECTION:
            return await self._projection_read_service.list_versions(
                MemoryListVersionsInput(target_ref=block_ref),
                session_id=session_id,
            )
        raise MemoryBlockHistoryUnsupportedError(
            f"Memory block history is unsupported for layer: {block.layer.value}"
        )

    async def read_memory_block_provenance(
        self,
        *,
        session_id: str,
        block_id: str,
    ) -> ProvenanceResult | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        block_ref = self._block_ref(block)
        if block.layer == Layer.CORE_STATE_AUTHORITATIVE:
            return self._provenance_read_service.read_provenance(
                block_ref,
                session_id=session_id,
            )
        if block.layer == Layer.CORE_STATE_PROJECTION:
            return await self._projection_read_service.read_provenance(
                MemoryReadProvenanceInput(target_ref=block_ref),
                session_id=session_id,
            )
        raise MemoryBlockHistoryUnsupportedError(
            f"Memory block provenance is unsupported for layer: {block.layer.value}"
        )

    def list_memory_proposals(
        self,
        *,
        session_id: str,
        status: str | None = None,
    ) -> list[dict]:
        session = self._require_session(session_id)
        return self._memory_inspection_read_service.list_proposals(
            story_id=session.story_id,
            session_id=session_id,
            status=status,
        )

    def list_memory_block_proposals(
        self,
        *,
        session_id: str,
        block_id: str,
        status: str | None = None,
    ) -> list[dict] | None:
        session = self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        if block.layer != Layer.CORE_STATE_AUTHORITATIVE:
            return []
        return (
            self._memory_inspection_read_service.list_proposals_for_authoritative_ref(
                story_id=session.story_id,
                session_id=session_id,
                target_ref=self._block_ref(block),
                status=status,
            )
        )

    def get_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None:
        session = self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        if block.layer != Layer.CORE_STATE_AUTHORITATIVE:
            raise MemoryBlockMutationUnsupportedError(
                "Memory block proposal detail only supports authoritative blocks"
            )
        detail = (
            self._memory_inspection_read_service.get_proposal_for_authoritative_ref(
                story_id=session.story_id,
                session_id=session_id,
                target_ref=self._block_ref(block),
                proposal_id=proposal_id,
            )
        )
        if detail is None:
            raise MemoryBlockProposalNotFoundError(
                f"Memory block proposal not found: {proposal_id}"
            )
        return detail

    async def submit_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: MemoryBlockProposalSubmitRequest,
    ) -> dict | None:
        if self._story_block_mutation_service is None:
            raise RuntimeError("story_block_mutation_service_not_configured")
        receipt = await self._story_block_mutation_service.submit_block_proposal(
            session_id=session_id,
            block_id=block_id,
            payload=payload,
        )
        if receipt is None:
            return None
        return receipt.model_dump(mode="json")

    async def direct_edit_memory_block(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: DirectCoreEditRequest,
    ) -> dict | None:
        if self._story_block_mutation_service is None:
            raise RuntimeError("story_block_mutation_service_not_configured")
        receipt = await self._story_block_mutation_service.direct_edit_block(
            session_id=session_id,
            block_id=block_id,
            payload=payload,
        )
        if receipt is None:
            return None
        return receipt.model_dump(mode="json")

    async def direct_edit_core_memory(
        self,
        *,
        session_id: str,
        payload: DirectCoreEditRequest,
    ) -> dict:
        session = self._require_session(session_id)
        if payload.identity.session_id != session.session_id:
            raise ValueError("memory_core_direct_edit_identity_session_mismatch")
        if payload.identity.story_id != session.story_id:
            raise ValueError("memory_core_direct_edit_identity_story_mismatch")
        if self._memory_inspection_service is None:
            raise RuntimeError("memory_inspection_service_not_configured")
        receipt = await self._memory_inspection_service.direct_core_edit(
            request=payload,
        )
        return receipt.model_dump(mode="json")

    def review_recall_memory(
        self,
        *,
        session_id: str,
        command: RecallReviewCommand,
    ) -> dict:
        session = self._require_session(session_id)
        if command.identity.session_id != session.session_id:
            raise ValueError("memory_recall_review_identity_session_mismatch")
        if command.identity.story_id != session.story_id:
            raise ValueError("memory_recall_review_identity_story_mismatch")
        if self._memory_inspection_service is None:
            raise RuntimeError("memory_inspection_service_not_configured")
        receipt = self._memory_inspection_service.review_recall(command=command)
        self._story_session_service.commit()
        return receipt.model_dump(mode="json")

    def evolve_archival_memory(
        self,
        *,
        session_id: str,
        request: ArchivalEvolutionRequest,
    ) -> dict:
        session = self._require_session(session_id)
        if request.identity.session_id != session.session_id:
            raise ValueError("memory_archival_evolution_identity_session_mismatch")
        if request.identity.story_id != session.story_id:
            raise ValueError("memory_archival_evolution_identity_story_mismatch")
        if self._memory_inspection_service is None:
            raise RuntimeError("memory_inspection_service_not_configured")
        receipt = self._memory_inspection_service.evolve_archival(request=request)
        self._story_session_service.commit()
        return receipt.model_dump(mode="json")

    def start_brainstorm_session(
        self,
        *,
        session_id: str,
        request: BrainstormSessionStartRequest,
    ) -> BrainstormSession:
        session = self._require_session(session_id)
        if request.identity.session_id != session.session_id:
            raise ValueError("brainstorm_identity_session_mismatch")
        if request.identity.story_id != session.story_id:
            raise ValueError("brainstorm_identity_story_mismatch")
        result = self._require_story_brainstorm_service().start_session(request)
        self._story_session_service.commit()
        return result

    def read_brainstorm_session(
        self,
        *,
        session_id: str,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormSession:
        session = self._require_session(session_id)
        if identity.session_id != session.session_id:
            raise ValueError("brainstorm_identity_session_mismatch")
        if identity.story_id != session.story_id:
            raise ValueError("brainstorm_identity_story_mismatch")
        return self._require_story_brainstorm_service().get_session(
            identity=identity,
            brainstorm_id=brainstorm_id,
        )

    async def summarize_brainstorm_session(
        self,
        *,
        session_id: str,
        brainstorm_id: str,
        request: BrainstormSummarizeRequest,
    ) -> BrainstormSession:
        session = self._require_session(session_id)
        if request.identity.session_id != session.session_id:
            raise ValueError("brainstorm_identity_session_mismatch")
        if request.identity.story_id != session.story_id:
            raise ValueError("brainstorm_identity_story_mismatch")
        result = await self._require_story_brainstorm_service().summarize_session(
            brainstorm_id=brainstorm_id,
            request=request,
        )
        self._story_session_service.commit()
        return result

    def update_brainstorm_item(
        self,
        *,
        session_id: str,
        brainstorm_id: str,
        item_id: str,
        request: BrainstormItemUpdateRequest,
    ) -> BrainstormSession:
        session = self._require_session(session_id)
        if request.identity.session_id != session.session_id:
            raise ValueError("brainstorm_identity_session_mismatch")
        if request.identity.story_id != session.story_id:
            raise ValueError("brainstorm_identity_story_mismatch")
        result = self._require_story_brainstorm_service().update_item(
            brainstorm_id=brainstorm_id,
            item_id=item_id,
            request=request,
        )
        self._story_session_service.commit()
        return result

    async def apply_brainstorm_session(
        self,
        *,
        session_id: str,
        brainstorm_id: str,
        request: BrainstormApplyRequest,
    ) -> BrainstormApplyReceipt:
        session = self._require_session(session_id)
        if request.identity.session_id != session.session_id:
            raise ValueError("brainstorm_identity_session_mismatch")
        if request.identity.story_id != session.story_id:
            raise ValueError("brainstorm_identity_story_mismatch")
        receipt = await self._require_story_brainstorm_service().apply_session(
            brainstorm_id=brainstorm_id,
            request=request,
        )
        self._story_session_service.commit()
        return receipt

    def apply_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None:
        if self._story_block_mutation_service is None:
            raise RuntimeError("story_block_mutation_service_not_configured")
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        self._story_block_mutation_service.apply_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )
        return self.get_memory_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )

    def list_memory_block_consumers(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        if self._story_block_consumer_state_service is None:
            return []
        return [
            item.model_dump(mode="json")
            for item in self._story_block_consumer_state_service.list_consumers(
                session_id=session_id
            )
        ]

    def get_memory_block_consumer(
        self,
        *,
        session_id: str,
        consumer_key: str,
    ) -> dict | None:
        self._require_session(session_id)
        if self._story_block_consumer_state_service is None:
            return None
        item = self._story_block_consumer_state_service.get_consumer(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        if item is None:
            return None
        return item.model_dump(mode="json")

    def read_memory_versions(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> VersionListResult:
        self._require_session(session_id)
        return self._version_history_read_service.list_versions(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def read_memory_provenance(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> ProvenanceResult:
        self._require_session(session_id)
        return self._provenance_read_service.read_provenance(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def _require_session(self, session_id: str) -> StorySession:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session

    def _require_draft_artifact(
        self,
        *,
        session_id: str,
        artifact_id: str,
    ) -> StoryArtifact:
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"StoryArtifact not found: {artifact_id}")
        if artifact.session_id != session_id:
            raise ValueError("revision_draft_session_mismatch")
        if artifact.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
            raise ValueError("revision_draft_kind_unsupported")
        if artifact.status != StoryArtifactStatus.DRAFT:
            raise ValueError("revision_draft_not_visible")
        return artifact

    def _revision_identity_from_artifact(
        self,
        *,
        session: StorySession,
        artifact: StoryArtifact,
    ) -> MemoryRuntimeIdentity:
        metadata = dict(artifact.metadata or {})
        story_id = self._metadata_text(metadata, "runtime_story_id")
        session_id = self._metadata_text(metadata, "runtime_session_id")
        branch_head_id = self._metadata_text(metadata, "runtime_branch_head_id")
        turn_id = self._metadata_text(metadata, "runtime_turn_id")
        runtime_profile_snapshot_id = self._metadata_text(
            metadata,
            "runtime_profile_snapshot_id",
        )
        missing = [
            name
            for name, value in (
                ("story_id", story_id),
                ("session_id", session_id),
                ("branch_head_id", branch_head_id),
                ("turn_id", turn_id),
                ("runtime_profile_snapshot_id", runtime_profile_snapshot_id),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "revision_runtime_identity_missing:" + ",".join(sorted(missing))
            )
        if story_id != session.story_id:
            raise ValueError("revision_story_id_mismatch")
        if session_id != session.session_id or artifact.session_id != session.session_id:
            raise ValueError("revision_session_id_mismatch")
        return MemoryRuntimeIdentity(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=runtime_profile_snapshot_id,
        )

    def _ensure_revision_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        artifact: StoryArtifact,
        mode: str,
    ) -> tuple[DraftDocumentRecord, ReviewOverlayRecord]:
        normalized_mode = self._revision_overlay_mode(mode)
        materialization_service = self._require_draft_materialization_service()
        overlay_service = self._require_revision_overlay_service()
        draft_ref = f"artifact:{artifact.artifact_id}"
        draft_document = materialization_service.materialize_draft(
            identity=identity,
            draft_ref=draft_ref,
            output_text=artifact.content_text,
            source_format="markdown",
            source_output_ref=artifact.artifact_id,
        )
        try:
            overlay_service.record_draft_document(
                identity=identity,
                draft_document=draft_document,
            )
        except RuntimeWorkspaceMaterialServiceError as exc:
            if exc.code != "runtime_workspace_material_id_conflict":
                raise
        overlay = overlay_service.create_or_update_overlay(
            identity=identity,
            draft_document_id=draft_document.draft_document_id,
            mode=normalized_mode,
        )
        return draft_document, overlay

    def _require_draft_materialization_service(self) -> DraftMaterializationService:
        if self._draft_materialization_service is None:
            raise RuntimeError("draft_materialization_service_not_configured")
        return self._draft_materialization_service

    def _require_revision_overlay_service(self) -> RevisionOverlayService:
        if self._revision_overlay_service is None:
            raise RuntimeError("revision_overlay_service_not_configured")
        return self._revision_overlay_service

    def _require_story_brainstorm_service(self) -> StoryBrainstormService:
        if self._story_brainstorm_service is None:
            raise RuntimeError("story_brainstorm_service_not_configured")
        return self._story_brainstorm_service

    def _require_story_runtime_identity_service(self) -> StoryRuntimeIdentityService:
        if self._story_runtime_identity_service is None:
            raise RuntimeError("story_runtime_identity_service_not_configured")
        return self._story_runtime_identity_service

    @staticmethod
    def _surface_block(
        *,
        surface: dict[str, Any],
        block_id: str,
    ) -> dict[str, Any]:
        document = surface.get("draft_document")
        blocks = []
        if isinstance(document, dict):
            blocks = list(document.get("blocks") or [])
        for block in blocks:
            if isinstance(block, dict) and block.get("block_id") == block_id:
                return block
        raise ValueError(f"revision_anchor_block_not_found:{block_id}")

    @staticmethod
    def _revision_overlay_mode(mode: str) -> ReviewOverlayMode:
        normalized = str(mode or "viewing").strip()
        if normalized not in {"viewing", "editing", "suggesting"}:
            raise ValueError(f"revision_overlay_mode_unsupported:{normalized}")
        return cast(ReviewOverlayMode, normalized)

    @staticmethod
    def _metadata_text(metadata: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = str(metadata.get(key) or "").strip()
            if value:
                return value
        return None

    def _materialize_scene_transcript(
        self,
        *,
        snapshot: ChapterWorkspaceSnapshot,
    ) -> None:
        if self._recall_scene_transcript_ingestion_service is None:
            return
        scene_ref = (snapshot.chapter.last_closed_scene_ref or "").strip()
        if not scene_ref:
            return
        input_model = (
            self._recall_scene_transcript_ingestion_service.build_promotion_input(
                session_id=snapshot.session.session_id,
                story_id=snapshot.session.story_id,
                chapter_index=snapshot.chapter.chapter_index,
                scene_ref=scene_ref,
                source_workspace_id=snapshot.session.source_workspace_id,
                discussion_entries=snapshot.discussion_entries,
                artifacts=snapshot.artifacts,
            )
        )
        self._recall_scene_transcript_ingestion_service.ingest_scene_transcript(
            input_model
        )

    @staticmethod
    def _build_authoritative_ref(
        *,
        object_id: str,
        domain: Domain,
        domain_path: str | None,
    ) -> ObjectRef:
        return ObjectRef(
            object_id=object_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=domain,
            domain_path=domain_path or object_id,
            scope="story",
            revision=1,
        )

    @staticmethod
    def _block_ref(block: RpBlockView) -> ObjectRef:
        return ObjectRef(
            object_id=block.label,
            layer=block.layer,
            domain=block.domain,
            domain_path=block.domain_path,
            scope=block.scope,
            revision=block.revision,
        )

    @staticmethod
    def _count_values(values) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _memory_overview_layers(block_counts: dict[str, int]) -> dict[str, dict]:
        return {
            Layer.CORE_STATE_AUTHORITATIVE.value: {
                "semantic_layer": "Core State.authoritative_state",
                "block_count": block_counts.get(
                    Layer.CORE_STATE_AUTHORITATIVE.value, 0
                ),
                "truth_status": "authoritative_truth",
                "storage_model": "formal_store_with_compatibility_mirror",
                "read_surface": "memory.get_state / memory.blocks",
                "mutation": "governed_proposal_apply",
                "history": "supported",
            },
            Layer.CORE_STATE_PROJECTION.value: {
                "semantic_layer": "Core State.derived_projection",
                "block_count": block_counts.get(Layer.CORE_STATE_PROJECTION.value, 0),
                "truth_status": "derived_projection",
                "storage_model": "formal_store_with_compatibility_mirror",
                "read_surface": "memory.get_summary / memory.blocks",
                "mutation": "maintenance_read_side_only",
                "history": "supported",
            },
            Layer.RECALL.value: {
                "semantic_layer": "Recall Memory",
                "block_count": block_counts.get(Layer.RECALL.value, 0),
                "truth_status": "historical_recall",
                "storage_model": "retrieval_core",
                "read_surface": "memory.search_recall",
                "mutation": "ingestion_only",
                "history": "retrieval_backed",
                "overview_count": "not_counted_in_this_surface",
                "known_source_families": [
                    "chapter_summary",
                    "accepted_story_segment",
                    "continuity_note",
                    "scene_transcript",
                    "character_long_history_summary",
                    "retired_foreshadow_summary",
                ],
            },
            Layer.ARCHIVAL.value: {
                "semantic_layer": "Archival Knowledge",
                "block_count": block_counts.get(Layer.ARCHIVAL.value, 0),
                "truth_status": "source_reference_material",
                "storage_model": "retrieval_core",
                "read_surface": "memory.search_archival",
                "mutation": "ingestion_only",
                "history": "retrieval_backed",
                "overview_count": "not_counted_in_this_surface",
            },
            Layer.RUNTIME_WORKSPACE.value: {
                "semantic_layer": "Runtime Workspace",
                "block_count": block_counts.get(Layer.RUNTIME_WORKSPACE.value, 0),
                "truth_status": "current_turn_scratch",
                "storage_model": "story_runtime_rows",
                "read_surface": "memory.blocks",
                "mutation": "unsupported_read_only",
                "history": "unsupported",
            },
        }
