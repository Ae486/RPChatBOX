"""Focused tests for the direct legal longform runtime seed helper."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
    CoreStateProjectionSlotRecord,
    CoreStateProjectionSlotRevisionRecord,
    CoreStateSnapshotManifestRecord,
)
from models.rp_memory_store import (
    MemoryApplyReceiptRecord,
    MemoryApplyTargetLinkRecord,
    MemoryChangeEventRecord,
    MemoryProposalRecord,
    RuntimeWorkspaceMaterialRecord,
)
from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    IndexJobRecord,
    KnowledgeChunkRecord,
    KnowledgeCollectionRecord,
    ParsedDocumentRecord,
    SourceAssetRecord,
)
from models.rp_story_store import StorySessionRecord
from rp.models.core_mutation import DirectCoreEditRequest
from rp.devtools.legal_longform_session_seed import (
    LegalLongformSessionSeedError,
    LegalLongformSessionSeeder,
    load_default_template,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.story_runtime import LongformChapterPhase
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.memory_inspection_service import MemoryInspectionService
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeService
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.runtime_read_manifest_service import BranchVisibilityResolver
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story_block_mutation_service import StoryBlockMutationService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chapter_ref() -> ObjectRef:
    return ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
    )


def _latest_identity(seed_result) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=seed_result.story_id,
        session_id=seed_result.session_id,
        branch_head_id=seed_result.active_branch_head_id,
        turn_id=seed_result.latest_turn_id,
        runtime_profile_snapshot_id=seed_result.active_runtime_profile_snapshot_id,
    )


def _insert_non_seed_story_scope_rows(
    retrieval_session, *, story_id: str
) -> dict[str, str]:
    now = _utcnow()
    marker = {
        "seed_tool": "legal_longform_session_seed",
        "seed_label": "other-label",
        "seed_marker": "legal_longform_session_seed:other-label",
    }
    collection_id = f"{story_id}:manual-collection"
    asset_id = f"{story_id}:manual-other-label-asset"
    parsed_document_id = f"manual-parsed-{story_id}"
    chunk_id = f"manual-chunk-{story_id}"
    embedding_id = f"manual-embedding-{story_id}"
    index_job_id = f"manual-index-job-{story_id}"
    session_id = f"manual-session-{story_id}"
    branch_head_id = f"manual-branch-{story_id}"
    turn_id = f"manual-turn-{story_id}"
    snapshot_id = f"manual-runtime-snapshot-{story_id}"
    chapter_workspace_id = f"manual-chapter-{story_id}"
    authoritative_object_id = f"manual-core-object-{story_id}"
    authoritative_revision_id = f"manual-core-revision-{story_id}"
    projection_slot_id = f"manual-projection-slot-{story_id}"
    projection_revision_id = f"manual-projection-revision-{story_id}"
    core_snapshot_id = f"manual-core-snapshot-{story_id}"
    proposal_id = f"manual-proposal-{story_id}"
    apply_id = f"manual-apply-{story_id}"
    apply_target_link_id = f"manual-apply-link-{story_id}"
    event_id = f"manual-memory-event-{story_id}"
    material_id = f"manual-runtime-material-{story_id}"

    retrieval_session.add(
        KnowledgeCollectionRecord(
            collection_id=collection_id,
            story_id=story_id,
            scope="story",
            collection_kind="archival",
            metadata_json={"created_by": "manual-test", **marker},
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        SourceAssetRecord(
            asset_id=asset_id,
            story_id=story_id,
            mode="longform",
            collection_id=collection_id,
            workspace_id="manual-workspace",
            step_id="manual-step",
            commit_id="legal_longform_session_seed:other-label",
            asset_kind="manual_note",
            source_ref=f"memory://{asset_id}",
            title="Manual non-seed material",
            parse_status="parsed",
            ingestion_status="completed",
            mapped_targets_json=["foundation"],
            metadata_json={
                **marker,
                "source_ref": f"seed:{story_id}:other-label:manual",
            },
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        ParsedDocumentRecord(
            parsed_document_id=parsed_document_id,
            asset_id=asset_id,
            story_id=story_id,
            parser_kind="manual",
            document_structure_json=[],
            parse_warnings_json=[],
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        KnowledgeChunkRecord(
            chunk_id=chunk_id,
            story_id=story_id,
            collection_id=collection_id,
            asset_id=asset_id,
            parsed_document_id=parsed_document_id,
            chunk_index=0,
            domain=Domain.WORLD_RULE.value,
            domain_path="manual.world.rule",
            title="Manual chunk",
            text="Ordinary same-story retrieval material must survive replace.",
            token_count=8,
            is_active=True,
            metadata_json={**marker, "domain": Domain.WORLD_RULE.value},
            provenance_refs_json=[f"asset:{asset_id}"],
            created_at=now,
        )
    )
    retrieval_session.add(
        EmbeddingRecordRecord(
            embedding_id=embedding_id,
            chunk_id=chunk_id,
            embedding_model="manual-test",
            provider_id=None,
            vector_dim=3,
            status="completed",
            is_active=True,
            embedding_vector=[0.1, 0.2, 0.3],
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        IndexJobRecord(
            job_id=index_job_id,
            story_id=story_id,
            asset_id=asset_id,
            collection_id=collection_id,
            job_kind="ingest",
            job_state="completed",
            target_refs_json=[],
            warnings_json=[],
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=now,
            completed_at=now,
        )
    )

    retrieval_session.add(
        CoreStateAuthoritativeObjectRecord(
            authoritative_object_id=authoritative_object_id,
            story_id=story_id,
            session_id=session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.current",
            object_id="manual.chapter.current",
            scope="story",
            payload_schema_ref=None,
            current_revision=1,
            data_json={"title": "Manual chapter"},
            metadata_json={**marker, "dual_write_source": "manual"},
            latest_apply_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        CoreStateAuthoritativeRevisionRecord(
            authoritative_revision_id=authoritative_revision_id,
            authoritative_object_id=authoritative_object_id,
            story_id=story_id,
            session_id=session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.current",
            object_id="manual.chapter.current",
            scope="story",
            revision=1,
            data_json={"title": "Manual chapter"},
            revision_source_kind="manual",
            source_apply_id=None,
            source_proposal_id=None,
            owning_branch_head_id=branch_head_id,
            origin_turn_id=turn_id,
            runtime_profile_snapshot_id=snapshot_id,
            visibility_scope="story_global",
            visibility_state="active",
            base_revision=None,
            source_event_id=None,
            metadata_json={**marker, "dual_write_source": "manual"},
            created_at=now,
        )
    )
    retrieval_session.add(
        CoreStateSnapshotManifestRecord(
            snapshot_id=core_snapshot_id,
            parent_snapshot_id=None,
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=snapshot_id,
            effective_revision_map_json={
                "manual.chapter.current": authoritative_revision_id
            },
            changed_ref_ids_json=["manual.chapter.current"],
            source_event_ids_json=[],
            manifest_kind="manual",
            metadata_json={**marker, "source": "manual"},
            created_at=now,
        )
    )
    retrieval_session.add(
        CoreStateProjectionSlotRecord(
            projection_slot_id=projection_slot_id,
            story_id=story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            layer=Layer.CORE_STATE_PROJECTION.value,
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.digest",
            summary_id="manual.summary",
            slot_name="manual_digest",
            scope="chapter",
            payload_schema_ref=None,
            current_revision=1,
            items_json=["manual"],
            metadata_json={**marker, "dual_write_source": "manual"},
            last_refresh_kind="manual",
            created_at=now,
            updated_at=now,
        )
    )
    retrieval_session.add(
        CoreStateProjectionSlotRevisionRecord(
            projection_slot_revision_id=projection_revision_id,
            projection_slot_id=projection_slot_id,
            story_id=story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            layer=Layer.CORE_STATE_PROJECTION.value,
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.digest",
            summary_id="manual.summary",
            slot_name="manual_digest",
            scope="chapter",
            revision=1,
            items_json=["manual"],
            refresh_source_kind="manual",
            refresh_source_ref=None,
            metadata_json={**marker, "dual_write_source": "manual"},
            created_at=now,
        )
    )

    retrieval_session.add(
        MemoryProposalRecord(
            proposal_id=proposal_id,
            story_id=story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            mode="longform",
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.current",
            status="applied",
            policy_decision="allow",
            submit_source="manual",
            operations_json=[],
            base_refs_json=[],
            reason="manual row must survive replace",
            trace_id=None,
            governance_metadata_json={**marker, "source": "manual"},
            created_at=now,
            updated_at=now,
            applied_at=now,
            error_message=None,
        )
    )
    retrieval_session.add(
        MemoryApplyReceiptRecord(
            apply_id=apply_id,
            proposal_id=proposal_id,
            story_id=story_id,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            target_refs_json=[],
            revision_after_json={"manual.chapter.current": 1},
            before_snapshot_json={},
            after_snapshot_json={"title": "Manual chapter"},
            warnings_json=[],
            apply_backend="manual",
            created_at=now,
        )
    )
    retrieval_session.add(
        MemoryApplyTargetLinkRecord(
            apply_target_link_id=apply_target_link_id,
            apply_id=apply_id,
            proposal_id=proposal_id,
            story_id=story_id,
            session_id=session_id,
            object_id="manual.chapter.current",
            domain=Domain.CHAPTER.value,
            domain_path="manual.chapter.current",
            scope="story",
            revision=1,
            authoritative_object_id=authoritative_object_id,
            authoritative_revision_id=authoritative_revision_id,
            created_at=now,
        )
    )
    retrieval_session.add(
        MemoryChangeEventRecord(
            event_id=event_id,
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=snapshot_id,
            actor="manual",
            event_kind="manual_event",
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            block_id="manual.chapter",
            entry_id="manual.chapter.current",
            operation_kind="manual.keep",
            visibility_effect="story_global",
            source_refs_json=[],
            dirty_targets_json=[],
            metadata_json={**marker, "source": "manual"},
            created_at=now,
        )
    )
    retrieval_session.add(
        RuntimeWorkspaceMaterialRecord(
            material_id=material_id,
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=snapshot_id,
            material_kind="post_write_trace",
            domain=Domain.CHAPTER.value,
            domain_path="manual.runtime.material",
            short_id="M1",
            short_id_key="m1",
            lifecycle="active",
            visibility="runtime_private",
            created_by="manual",
            expiration_ref=None,
            materialization_ref=None,
            payload_json={"manual": True},
            source_refs_json=[],
            metadata_json={**marker, "source": "manual"},
            created_at=now,
            updated_at=now,
            expired_at=None,
            invalidated_at=None,
        )
    )
    retrieval_session.commit()
    return {
        "collection_id": collection_id,
        "asset_id": asset_id,
        "parsed_document_id": parsed_document_id,
        "chunk_id": chunk_id,
        "embedding_id": embedding_id,
        "index_job_id": index_job_id,
        "authoritative_object_id": authoritative_object_id,
        "authoritative_revision_id": authoritative_revision_id,
        "core_snapshot_id": core_snapshot_id,
        "projection_slot_id": projection_slot_id,
        "projection_revision_id": projection_revision_id,
        "proposal_id": proposal_id,
        "apply_id": apply_id,
        "apply_target_link_id": apply_target_link_id,
        "event_id": event_id,
        "material_id": material_id,
    }


@pytest.mark.asyncio
async def test_legal_longform_session_seed_materializes_branchable_runtime(
    retrieval_session,
):
    template = load_default_template()
    seeded = LegalLongformSessionSeeder(retrieval_session).seed(
        template=template,
        story_id="story-legal-longform-seed-main",
        label="main-seed",
    )

    story_service = StorySessionService(retrieval_session)
    story_session = story_service.get_session(seeded.session_id)
    chapter = story_service.get_current_chapter(seeded.session_id)
    assert story_session is not None
    assert chapter is not None
    assert story_session.active_branch_head_id == seeded.active_branch_head_id
    assert (
        story_session.active_runtime_profile_snapshot_id
        == seeded.active_runtime_profile_snapshot_id
    )
    assert chapter.accepted_outline_json is not None
    assert (
        chapter.accepted_outline_json["structured_outline"]["schema_version"]
        == "longform_outline_v1"
    )

    accepted_segments = story_service.active_branch_accepted_story_segments(
        session_id=seeded.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert [
        item.artifact_id for item in accepted_segments
    ] == seeded.accepted_segment_ids

    latest_identity = _latest_identity(seeded)
    resolver = CoreStateAsOfResolver(
        session=retrieval_session,
        repository=CoreStateStoreRepository(retrieval_session),
    )
    manifest = resolver.ensure_manifest_for_identity(identity=latest_identity)
    revision = resolver.resolve_object_revision(
        manifest=manifest,
        object_ref=_chapter_ref(),
    )
    assert revision.data_json["title"] == template.chapter.chapter_title
    character_revision = resolver.resolve_object_revision(
        manifest=manifest,
        object_ref=ObjectRef(
            object_id="character.state_digest",
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=Domain.CHARACTER,
            domain_path="character.state_digest",
            scope="story",
        ),
    )
    assert character_revision.data_json["林鸢"]["mood"] == "警觉"

    progress_service = LongformChapterRuntimeService(
        story_session_service=story_service,
        session=retrieval_session,
    )
    progress_record = progress_service.get_latest_outline_progress_for_chapter(
        story_id=seeded.story_id,
        session_id=seeded.session_id,
        branch_head_id=seeded.active_branch_head_id,
        chapter_index=chapter.chapter_index,
        identity=latest_identity,
    )
    assert progress_record is not None
    _, progress = progress_record
    assert progress.covered_beat_ids == ["beat_001", "beat_002"]
    assert progress.current_beat_id == "beat_003"

    proposal_repository = ProposalRepository(retrieval_session)
    version_service = VersionHistoryReadService(
        adapter=StorySessionCoreStateAdapter(story_service),
        proposal_repository=proposal_repository,
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_service,
        builder_projection_context_service=BuilderProjectionContextService(
            ProjectionStateService(
                story_session_service=story_service,
                adapter=ChapterWorkspaceProjectionAdapter(story_service),
            )
        ),
        proposal_repository=proposal_repository,
        version_history_read_service=version_service,
        core_state_store_repository=CoreStateStoreRepository(retrieval_session),
        store_read_enabled=True,
    )
    authoritative_objects = inspection_service.list_authoritative_objects(
        session_id=seeded.session_id
    )
    projection_slots = inspection_service.list_projection_slots(
        session_id=seeded.session_id
    )
    assert any(
        item["object_ref"]["object_id"] == "chapter.current"
        for item in authoritative_objects
    )
    assert any(
        item["slot_name"] == "current_outline_digest" for item in projection_slots
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    block_read_service = RpBlockReadService(
        story_session_service=story_service,
        builder_projection_context_service=BuilderProjectionContextService(
            ProjectionStateService(
                story_session_service=story_service,
                adapter=ChapterWorkspaceProjectionAdapter(story_service),
            )
        ),
        core_state_store_repository=core_repo,
        memory_inspection_read_service=inspection_service,
        store_read_enabled=True,
    )
    proposal_apply_service = ProposalApplyService(
        story_session_service=story_service,
        proposal_repository=proposal_repository,
        story_state_apply_service=StoryStateApplyService(),
        core_state_dual_write_service=CoreStateDualWriteService(repository=core_repo),
        core_state_store_write_switch_enabled=True,
        memory_change_event_service=MemoryChangeEventService(session=retrieval_session),
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        core_state_as_of_resolver=resolver,
    )
    proposal_workflow_service = ProposalWorkflowService(
        proposal_repository=proposal_repository,
        proposal_apply_service=proposal_apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    story_block_mutation_service = StoryBlockMutationService(
        story_session_service=story_service,
        rp_block_read_service=block_read_service,
        memory_inspection_read_service=inspection_service,
        proposal_apply_service=proposal_apply_service,
        proposal_workflow_service=proposal_workflow_service,
    )
    memory_service = MemoryInspectionService(
        memory_inspection_read_service=inspection_service,
        rp_block_read_service=block_read_service,
        story_block_mutation_service=story_block_mutation_service,
        branch_visibility_resolver=BranchVisibilityResolver(retrieval_session),
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        retrieval_document_service=RetrievalDocumentService(retrieval_session),
    )
    character_ref = ObjectRef(
        object_id="character.state_digest",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHARACTER,
        domain_path="character.state_digest",
        scope="story",
        revision=int(character_revision.revision or 1),
    )
    direct_edit_receipt = await memory_service.direct_core_edit(
        request=DirectCoreEditRequest(
            identity=latest_identity,
            actor="test.memory_editor",
            domain=Domain.CHARACTER,
            domain_path="character.state_digest",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": character_ref.model_dump(mode="json"),
                    "field_patch": {"林鸢": {"mood": "警觉和怀疑"}},
                }
            ],
            base_refs=[character_ref],
            reason="test direct character mood edit",
        )
    )
    refreshed_after_edit = story_service.get_session(seeded.session_id)
    assert direct_edit_receipt.status == "applied"
    assert refreshed_after_edit is not None
    assert refreshed_after_edit.current_state_json["character_state_digest"]["林鸢"][
        "mood"
    ] == "警觉和怀疑"

    broker = RetrievalBroker(
        default_story_id=seeded.story_id,
        runtime_identity=latest_identity,
        session=retrieval_session,
    )
    recall_result = await broker.search_recall(
        MemorySearchRecallInput(query="林鸢撬开最底层的旧账册", scope="story")
    )
    assert recall_result.hits, recall_result.warnings
    archival_asset = retrieval_session.get(
        SourceAssetRecord,
        seeded.archival_asset_id,
    )
    assert archival_asset is not None
    assert archival_asset.title == template.archival_seed.title
    archival_chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.asset_id == seeded.archival_asset_id
        )
    ).all()
    assert archival_chunks
    assert any(template.archival_seed.text in chunk.text for chunk in archival_chunks)

    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )
    branch_receipt = identity_service.create_branch_from_turn(
        session_id=seeded.session_id,
        origin_turn_id=seeded.segment_turn_records[0].turn_id,
        actor="test.branch",
        branch_name="forked from first accepted segment",
    )
    assert branch_receipt.to_branch_head_id is not None
    branch_visible_segments = story_service.active_branch_accepted_story_segments(
        session_id=seeded.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert [item.artifact_id for item in branch_visible_segments] == [
        seeded.accepted_segment_ids[0]
    ]

    identity_service.switch_branch(
        session_id=seeded.session_id,
        target_branch_head_id=seeded.active_branch_head_id,
        actor="test.switch_back",
    )
    identity_service.rollback_to_turn(
        session_id=seeded.session_id,
        target_turn_id=seeded.segment_turn_records[0].turn_id,
        actor="test.rollback",
    )
    rollback_visible_segments = story_service.active_branch_accepted_story_segments(
        session_id=seeded.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert [item.artifact_id for item in rollback_visible_segments] == [
        seeded.accepted_segment_ids[0]
    ]


def test_legal_longform_session_seed_replace_recreates_matching_seed(retrieval_session):
    template = load_default_template()
    seeder = LegalLongformSessionSeeder(retrieval_session)
    first = seeder.seed(
        template=template,
        story_id="story-legal-longform-seed-replace",
        label="replaceable-seed",
    )
    second = LegalLongformSessionSeeder(retrieval_session).seed(
        template=template,
        story_id="story-legal-longform-seed-replace",
        label="replaceable-seed",
        replace=True,
    )

    story_service = StorySessionService(retrieval_session)
    assert story_service.get_session(first.session_id) is None
    assert story_service.get_session(second.session_id) is not None
    remaining = list(
        retrieval_session.exec(
            select(StorySessionRecord).where(
                StorySessionRecord.story_id == "story-legal-longform-seed-replace"
            )
        ).all()
    )
    assert len(remaining) == 1
    assert remaining[0].session_id == second.session_id


def test_legal_longform_session_seed_replace_preserves_non_seed_story_scope_rows(
    retrieval_session,
):
    template = load_default_template()
    story_id = "story-legal-longform-seed-replace-preserve-non-seed"
    first = LegalLongformSessionSeeder(retrieval_session).seed(
        template=template,
        story_id=story_id,
        label="replaceable-seed",
    )
    non_seed_ids = _insert_non_seed_story_scope_rows(
        retrieval_session,
        story_id=story_id,
    )

    second = LegalLongformSessionSeeder(retrieval_session).seed(
        template=template,
        story_id=story_id,
        label="replaceable-seed",
        replace=True,
    )

    story_service = StorySessionService(retrieval_session)
    assert story_service.get_session(first.session_id) is None
    assert story_service.get_session(second.session_id) is not None
    assert retrieval_session.get(SourceAssetRecord, first.recall_asset_ids[0]) is None
    assert (
        retrieval_session.get(SourceAssetRecord, non_seed_ids["asset_id"]) is not None
    )
    assert (
        retrieval_session.get(
            ParsedDocumentRecord,
            non_seed_ids["parsed_document_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(KnowledgeChunkRecord, non_seed_ids["chunk_id"])
        is not None
    )
    assert (
        retrieval_session.get(EmbeddingRecordRecord, non_seed_ids["embedding_id"])
        is not None
    )
    assert (
        retrieval_session.get(IndexJobRecord, non_seed_ids["index_job_id"]) is not None
    )
    assert (
        retrieval_session.get(
            KnowledgeCollectionRecord,
            non_seed_ids["collection_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(
            CoreStateAuthoritativeObjectRecord,
            non_seed_ids["authoritative_object_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(
            CoreStateAuthoritativeRevisionRecord,
            non_seed_ids["authoritative_revision_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(
            CoreStateSnapshotManifestRecord,
            non_seed_ids["core_snapshot_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(
            CoreStateProjectionSlotRecord,
            non_seed_ids["projection_slot_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(
            CoreStateProjectionSlotRevisionRecord,
            non_seed_ids["projection_revision_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(MemoryProposalRecord, non_seed_ids["proposal_id"])
        is not None
    )
    assert (
        retrieval_session.get(MemoryApplyReceiptRecord, non_seed_ids["apply_id"])
        is not None
    )
    assert (
        retrieval_session.get(
            MemoryApplyTargetLinkRecord,
            non_seed_ids["apply_target_link_id"],
        )
        is not None
    )
    assert (
        retrieval_session.get(MemoryChangeEventRecord, non_seed_ids["event_id"])
        is not None
    )
    assert (
        retrieval_session.get(
            RuntimeWorkspaceMaterialRecord, non_seed_ids["material_id"]
        )
        is not None
    )
    assert not list(
        retrieval_session.exec(
            select(CoreStateAuthoritativeObjectRecord).where(
                CoreStateAuthoritativeObjectRecord.session_id == first.session_id
            )
        ).all()
    )
    assert not list(
        retrieval_session.exec(
            select(RuntimeWorkspaceMaterialRecord).where(
                RuntimeWorkspaceMaterialRecord.session_id == first.session_id
            )
        ).all()
    )


def test_legal_longform_session_seed_replace_refuses_non_seed_story_scope(
    retrieval_session,
):
    story_service = StorySessionService(retrieval_session)
    story_session = story_service.create_session(
        story_id="story-legal-longform-seed-conflict",
        source_workspace_id="workspace-conflict",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    story_service.create_chapter_workspace(
        session_id=story_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={},
    )
    retrieval_session.commit()

    with pytest.raises(LegalLongformSessionSeedError) as exc_info:
        LegalLongformSessionSeeder(retrieval_session).seed(
            template=load_default_template(),
            story_id="story-legal-longform-seed-conflict",
            label="conflict-seed",
            replace=True,
        )

    assert exc_info.value.code == "legal_longform_seed_replace_conflict"
