"""Post-write regression for longform active-story MVP."""

from __future__ import annotations

from typing import Any

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    SpecialistResultBundle,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySession,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from .legacy_state_patch_proposal_builder import LegacyStatePatchProposalBuilder
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_specialist_service import LongformSpecialistService
from .projection_refresh_service import ProjectionRefreshService
from .proposal_workflow_service import ProposalWorkflowService
from .recall_character_long_history_ingestion_service import (
    RecallCharacterLongHistoryIngestionService,
)
from .recall_continuity_note_ingestion_service import (
    RecallContinuityNoteIngestionService,
)
from .recall_detail_ingestion_service import RecallDetailIngestionService
from .recall_retired_foreshadow_ingestion_service import (
    RecallRetiredForeshadowIngestionService,
)
from .recall_summary_ingestion_service import RecallSummaryIngestionService
from .story_session_service import StorySessionService


class LongformRegressionService:
    """Digest accepted artifacts back into session/chapter runtime state."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        orchestrator_service: LongformOrchestratorService,
        specialist_service: LongformSpecialistService,
        proposal_workflow_service: ProposalWorkflowService,
        legacy_state_patch_proposal_builder: LegacyStatePatchProposalBuilder
        | None = None,
        projection_refresh_service: ProjectionRefreshService | None = None,
        recall_summary_ingestion_service: RecallSummaryIngestionService | None = None,
        recall_detail_ingestion_service: RecallDetailIngestionService | None = None,
        recall_continuity_note_ingestion_service: RecallContinuityNoteIngestionService
        | None = None,
        recall_character_long_history_ingestion_service: RecallCharacterLongHistoryIngestionService
        | None = None,
        recall_retired_foreshadow_ingestion_service: RecallRetiredForeshadowIngestionService
        | None = None,
        regression_policy: PostWriteMaintenancePolicy | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._orchestrator_service = orchestrator_service
        self._specialist_service = specialist_service
        self._proposal_workflow_service = proposal_workflow_service
        self._legacy_state_patch_proposal_builder = (
            legacy_state_patch_proposal_builder or LegacyStatePatchProposalBuilder()
        )
        self._projection_refresh_service = (
            projection_refresh_service
            or ProjectionRefreshService(story_session_service)
        )
        self._recall_summary_ingestion_service = recall_summary_ingestion_service
        self._recall_detail_ingestion_service = recall_detail_ingestion_service
        self._recall_continuity_note_ingestion_service = (
            recall_continuity_note_ingestion_service
        )
        self._recall_character_long_history_ingestion_service = (
            recall_character_long_history_ingestion_service
        )
        self._recall_retired_foreshadow_ingestion_service = (
            recall_retired_foreshadow_ingestion_service
        )
        self._regression_policy = regression_policy or PostWriteMaintenancePolicy(
            preset_id="phase_e_internal_regression",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        )

    async def run_light_regression(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        accepted_artifact: StoryArtifact,
        model_id: str,
        provider_id: str | None,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> tuple[StorySession, ChapterWorkspace]:
        plan = await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            target_artifact_id=accepted_artifact.artifact_id,
        )
        bundle = await self._specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            accepted_segments=self._collect_light_regression_segments(
                chapter=chapter,
                accepted_artifact=accepted_artifact,
            ),
            pending_artifact=accepted_artifact,
        )
        return await self._apply_bundle(session=session, chapter=chapter, bundle=bundle)

    async def run_heavy_regression(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        model_id: str,
        provider_id: str | None,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> tuple[StorySession, ChapterWorkspace]:
        accepted_segments = self._list_accepted_story_segments(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        recall_source_refs = self._build_recall_source_refs(
            session=session,
            chapter=chapter,
            accepted_segments=accepted_segments,
        )
        plan = await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            target_artifact_id=None,
        )
        bundle = await self._specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            accepted_segments=accepted_segments,
            pending_artifact=accepted_segments[-1] if accepted_segments else None,
        )
        updated_session, updated_chapter = await self._apply_bundle(
            session=session,
            chapter=chapter,
            bundle=bundle,
        )
        if (
            self._recall_summary_ingestion_service is not None
            and bundle.recall_summary_text
        ):
            self._recall_summary_ingestion_service.ingest_chapter_summary(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                source_workspace_id=session.source_workspace_id,
                summary_text=bundle.recall_summary_text,
                runtime_identity=runtime_identity,
                source_refs=recall_source_refs,
            )
        if self._recall_detail_ingestion_service is not None and accepted_segments:
            self._recall_detail_ingestion_service.ingest_accepted_story_segments(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                source_workspace_id=session.source_workspace_id,
                accepted_segments=accepted_segments,
                runtime_identity=runtime_identity,
                source_refs=recall_source_refs,
            )
        if (
            self._recall_continuity_note_ingestion_service is not None
            and bundle.summary_updates
        ):
            self._recall_continuity_note_ingestion_service.ingest_continuity_notes(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                source_workspace_id=session.source_workspace_id,
                summary_updates=bundle.summary_updates,
                runtime_identity=runtime_identity,
                source_refs=recall_source_refs,
            )
        if (
            self._recall_character_long_history_ingestion_service is not None
            and isinstance(updated_session.current_state_json, dict)
        ):
            character_state_digest = updated_session.current_state_json.get(
                "character_state_digest"
            )
            if isinstance(character_state_digest, dict):
                self._recall_character_long_history_ingestion_service.ingest_character_summaries(
                    session_id=updated_session.session_id,
                    story_id=updated_session.story_id,
                    chapter_index=updated_chapter.chapter_index,
                    source_workspace_id=updated_session.source_workspace_id,
                    character_state_digest=character_state_digest,
                    chapter_summary_text=bundle.recall_summary_text,
                    continuity_notes=bundle.summary_updates,
                    accepted_segments=accepted_segments,
                    runtime_identity=runtime_identity,
                    source_refs=recall_source_refs,
                )
        if self._recall_retired_foreshadow_ingestion_service is not None and isinstance(
            updated_session.current_state_json, dict
        ):
            foreshadow_registry = updated_session.current_state_json.get(
                "foreshadow_registry"
            )
            if isinstance(foreshadow_registry, list):
                self._recall_retired_foreshadow_ingestion_service.ingest_retired_foreshadow_summaries(
                    session_id=updated_session.session_id,
                    story_id=updated_session.story_id,
                    chapter_index=updated_chapter.chapter_index,
                    source_workspace_id=updated_session.source_workspace_id,
                    foreshadow_registry=foreshadow_registry,
                    chapter_summary_text=bundle.recall_summary_text,
                    continuity_notes=bundle.summary_updates,
                    accepted_segments=accepted_segments,
                    runtime_identity=runtime_identity,
                    source_refs=recall_source_refs,
                )
        return updated_session, updated_chapter

    async def _apply_bundle(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        bundle: SpecialistResultBundle,
    ) -> tuple[StorySession, ChapterWorkspace]:
        if bundle.state_patch_proposals:
            proposal_inputs = self._legacy_state_patch_proposal_builder.build_inputs(
                story_id=session.story_id,
                mode=session.mode,
                patch=bundle.state_patch_proposals,
            )
            for proposal_input in proposal_inputs:
                await self._proposal_workflow_service.submit_and_route(
                    proposal_input,
                    session_id=session.session_id,
                    chapter_workspace_id=chapter.chapter_workspace_id,
                    submit_source="post_write_regression",
                    policy=self._regression_policy,
                )
        updated_session = (
            self._story_session_service.get_session(session.session_id) or session
        )
        updated_chapter = self._projection_refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=bundle,
        )
        return updated_session, updated_chapter

    def _collect_light_regression_segments(
        self,
        *,
        chapter: ChapterWorkspace,
        accepted_artifact: StoryArtifact,
    ) -> list[StoryArtifact]:
        accepted_segments = self._list_accepted_story_segments(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        if all(
            item.artifact_id != accepted_artifact.artifact_id
            for item in accepted_segments
        ):
            accepted_segments.append(accepted_artifact)
        return accepted_segments

    def _list_accepted_story_segments(
        self,
        *,
        chapter_workspace_id: str,
    ) -> list[StoryArtifact]:
        return [
            item
            for item in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter_workspace_id
            )
            if (
                item.status == StoryArtifactStatus.ACCEPTED
                and item.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            )
        ]

    @staticmethod
    def _build_recall_source_refs(
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        accepted_segments: list[StoryArtifact],
    ) -> list[MemorySourceRef]:
        refs: list[MemorySourceRef] = [
            MemorySourceRef(
                source_type="story_session_chapter",
                source_id=f"{session.session_id}:chapter:{chapter.chapter_index}",
                layer="core_state.derived_projection",
                domain="chapter",
                metadata={"chapter_index": chapter.chapter_index},
            )
        ]
        seen_artifact_ids: set[str] = set()
        for artifact in accepted_segments:
            if artifact.artifact_id in seen_artifact_ids:
                continue
            seen_artifact_ids.add(artifact.artifact_id)
            refs.append(
                MemorySourceRef(
                    source_type="story_artifact",
                    source_id=artifact.artifact_id,
                    layer="runtime_workspace",
                    domain="chapter",
                    entry_id=artifact.artifact_id,
                    revision=artifact.revision,
                    metadata={
                        "artifact_kind": artifact.artifact_kind.value,
                        "scene_ref": artifact.scene_ref,
                    },
                )
            )
            refs.extend(
                LongformRegressionService._worker_source_refs_from_metadata(
                    artifact.metadata
                )
            )
        return LongformRegressionService._dedupe_source_refs(refs)

    @staticmethod
    def _worker_source_refs_from_metadata(
        metadata: dict[str, Any] | None,
    ) -> list[MemorySourceRef]:
        if not isinstance(metadata, dict):
            return []
        bundle_payload = metadata.get("worker_source_ref_bundle")
        if not isinstance(bundle_payload, dict):
            return []
        card_ids = list(bundle_payload.get("retrieval_card_material_ids") or [])
        expanded_ids = list(
            bundle_payload.get("retrieval_expanded_chunk_material_ids") or []
        )
        usage_ids = list(bundle_payload.get("retrieval_usage_material_ids") or [])
        refs: list[MemorySourceRef] = []
        for source_type, material_ids in (
            ("retrieval_card_material", card_ids),
            ("retrieval_expanded_chunk_material", expanded_ids),
            ("retrieval_usage_material", usage_ids),
        ):
            for material_id in material_ids:
                normalized = str(material_id or "").strip()
                if not normalized:
                    continue
                refs.append(
                    MemorySourceRef(
                        source_type=source_type,
                        source_id=normalized,
                        layer="runtime_workspace",
                        metadata={"source_of_truth": False},
                    )
                )
        return refs

    @staticmethod
    def _dedupe_source_refs(
        source_refs: list[MemorySourceRef],
    ) -> list[MemorySourceRef]:
        deduped: list[MemorySourceRef] = []
        seen: set[tuple[str, str]] = set()
        for ref in source_refs:
            key = (ref.source_type.casefold(), ref.source_id.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ref)
        return deduped
