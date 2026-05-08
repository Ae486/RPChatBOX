"""Focused tests for user-visible memory inspection/edit backend contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from models.rp_story_store import BranchHeadRecord
from rp.models.archival_evolution import (
    ArchivalEvolutionReceipt,
    ArchivalEvolutionRequest,
)
from rp.models.block_view import RpBlockView
from rp.models.core_mutation import DirectCoreEditRequest
from rp.models.dsl import Domain, Layer
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import ProposalReceipt
from rp.models.memory_inspection import RecallReviewCommand
from rp.models.retrieval_records import SourceAsset
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.memory_inspection_service import (
    MemoryInspectionError,
    MemoryInspectionService,
)
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_read_manifest_service import BranchVisibilityResolver
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _FakeReadService:
    def list_authoritative_objects(self, *, session_id: str) -> list[dict[str, Any]]:
        return [
            {
                "object_ref": {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE.value,
                    "domain": Domain.CHAPTER.value,
                    "domain_path": "chapter.current",
                },
                "data": {"title": "Visible Core"},
            }
        ]

    def list_projection_slots(self, *, session_id: str) -> list[dict[str, Any]]:
        return [{"summary_id": "projection.current_outline", "items": ["Outline"]}]


class _FakeBlockReadService:
    def __init__(self) -> None:
        self.block = RpBlockView(
            block_id="block.chapter.current",
            label="chapter.current",
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            scope="story",
            revision=3,
            source="core_state_store",
            data_json={"title": "Visible Core"},
        )

    def list_blocks(
        self,
        *,
        session_id: str,
        layer: Layer | None = None,
    ) -> list[RpBlockView]:
        if layer is not None and layer != self.block.layer:
            return []
        return [self.block]


class _FakeBlockMutationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def direct_edit_block(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: DirectCoreEditRequest,
    ) -> ProposalReceipt:
        self.calls.append(
            {
                "session_id": session_id,
                "block_id": block_id,
                "payload": payload,
            }
        )
        return ProposalReceipt(
            proposal_id="proposal.direct.1",
            status="applied",
            mode="longform",
            domain=payload.domain,
            domain_path=payload.domain_path,
            operation_kinds=[operation.kind for operation in payload.operations],
            created_at=_utcnow(),
        )


class _FakeRecallLifecycleService:
    def __init__(self) -> None:
        self.invalidated: dict[str, Any] | None = None

    def invalidate_material(
        self,
        *,
        material_refs,
        event_id: str,
        reason: str,
    ) -> list[str]:
        self.invalidated = {
            "material_refs": list(material_refs),
            "event_id": event_id,
            "reason": reason,
        }
        return list(material_refs)

    def supersede_material(self, *, material_refs, replacement_metadata):
        return list(material_refs)

    def recompute_material(self, *, material_refs, replacement_metadata):
        return list(material_refs)


class _FakeArchivalEvolutionService:
    def __init__(self) -> None:
        self.request: ArchivalEvolutionRequest | None = None

    def evolve_source(
        self,
        request: ArchivalEvolutionRequest,
    ) -> ArchivalEvolutionReceipt:
        self.request = request
        return ArchivalEvolutionReceipt(
            evolution_id="evolution.visible.1",
            source_asset_id="asset.archival.visible.v2",
            superseded_source_asset_id=request.source_asset_id,
            root_source_asset_id=request.source_asset_id,
            new_source_version=2,
            superseded_source_version=request.expected_source_version,
            visibility_scope=request.visibility_scope,
            selected_branch_head_ids=[request.identity.branch_head_id],
            replacement_chunk_ids=["chunk.archival.visible.v2"],
            reindex_job_ids=["job.reindex.visible.1"],
            event_ids=["event.archival.visible.1"],
        )


def _seed_identities(
    retrieval_session,
) -> tuple[MemoryRuntimeIdentity, MemoryRuntimeIdentity]:
    story_service = StorySessionService(retrieval_session)
    story_session = story_service.create_session(
        story_id="story-memory-inspection",
        source_workspace_id="workspace-memory-inspection",
        mode=StoryMode.LONGFORM.value,
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
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.memory_inspection",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    main_branch = identity_service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    main_turn = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    sibling_branch = BranchHeadRecord(
        branch_head_id=f"branch:{story_session.session_id}:sibling",
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        branch_name="sibling",
        parent_branch_head_id=None,
        forked_from_turn_id=None,
        head_turn_id=None,
        status="active",
        visibility_scope="active_lineage",
    )
    retrieval_session.add(sibling_branch)
    retrieval_session.flush()
    sibling_turn = identity_service.create_turn(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=sibling_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    return (
        MemoryRuntimeIdentity(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            branch_head_id=main_branch.branch_head_id,
            turn_id=main_turn.turn_id,
            runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        ),
        MemoryRuntimeIdentity(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            branch_head_id=sibling_branch.branch_head_id,
            turn_id=sibling_turn.turn_id,
            runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        ),
    )


def _inspection_service(
    retrieval_session,
    *,
    block_mutation_service: Any | None = None,
    recall_lifecycle_service: Any | None = None,
    archival_evolution_service: Any | None = None,
) -> MemoryInspectionService:
    return MemoryInspectionService(
        memory_inspection_read_service=_FakeReadService(),  # type: ignore[arg-type]
        rp_block_read_service=_FakeBlockReadService(),  # type: ignore[arg-type]
        story_block_mutation_service=block_mutation_service,
        branch_visibility_resolver=BranchVisibilityResolver(retrieval_session),
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        retrieval_document_service=RetrievalDocumentService(retrieval_session),
        recall_lifecycle_service=recall_lifecycle_service,
        archival_evolution_service=archival_evolution_service,
    )


def _seed_asset(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    asset_id: str,
    layer: str,
    domain: str,
    visibility_scope: str,
    owning_branch_head_id: str | None,
    origin_turn_id: str | None,
    visibility_state: str = "active",
    story_id: str | None = None,
) -> SourceAsset:
    metadata = {
        "layer": layer,
        "domain": domain,
        "domain_path": f"{layer}.{domain}.{asset_id}",
        "visibility_scope": visibility_scope,
        "visibility_state": visibility_state,
        "lifecycle_state": visibility_state,
        "source_version": 1,
        "source_refs": [
            {
                "source_type": "story_turn" if origin_turn_id else "seed_asset",
                "source_id": origin_turn_id or asset_id,
                "layer": layer,
                "domain": domain,
                "entry_id": asset_id,
            }
        ],
    }
    if owning_branch_head_id is not None:
        metadata["owning_branch_head_id"] = owning_branch_head_id
    if origin_turn_id is not None:
        metadata["origin_turn_id"] = origin_turn_id
    asset = SourceAsset(
        asset_id=asset_id,
        story_id=story_id or identity.story_id,
        mode=StoryMode.LONGFORM,
        collection_id=None,
        workspace_id="workspace-memory-inspection",
        step_id="memory-inspection",
        commit_id="commit-memory-inspection",
        asset_kind=f"{layer}_material",
        source_ref=f"memory://{asset_id}",
        title=asset_id,
        parse_status="completed",
        ingestion_status="completed",
        mapped_targets=[domain],
        metadata=metadata,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(asset)
    retrieval_session.flush()
    return asset


def test_inspection_filters_visible_layers_and_keeps_hidden_audit_explicit(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_identities(retrieval_session)
    RuntimeWorkspaceMaterialService(session=retrieval_session).record_material(
        RuntimeWorkspaceMaterial(
            material_id="workspace.main.visible",
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            identity=main_identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.current",
            payload={"title": "Visible workspace overlay"},
            visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
            created_by="reviewer",
        )
    )
    RuntimeWorkspaceMaterialService(session=retrieval_session).record_material(
        RuntimeWorkspaceMaterial(
            material_id="workspace.sibling.hidden",
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            identity=sibling_identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.current",
            payload={"title": "Sibling workspace overlay"},
            visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
            created_by="reviewer",
        )
    )
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="recall.main.visible",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER.value,
        visibility_scope="branch_scoped",
        owning_branch_head_id=main_identity.branch_head_id,
        origin_turn_id=main_identity.turn_id,
    )
    _seed_asset(
        retrieval_session,
        identity=sibling_identity,
        asset_id="recall.sibling.hidden",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER.value,
        visibility_scope="branch_scoped",
        owning_branch_head_id=sibling_identity.branch_head_id,
        origin_turn_id=sibling_identity.turn_id,
    )
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="archival.global.visible",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE.value,
        visibility_scope="story_global",
        owning_branch_head_id=None,
        origin_turn_id=None,
    )
    _seed_asset(
        retrieval_session,
        identity=sibling_identity,
        asset_id="archival.sibling.hidden",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE.value,
        visibility_scope="branch_scoped",
        owning_branch_head_id=sibling_identity.branch_head_id,
        origin_turn_id=sibling_identity.turn_id,
    )

    service = _inspection_service(retrieval_session)
    visible = service.inspect_visible_memory(identity=main_identity)
    audit = service.inspect_visible_memory(
        identity=main_identity,
        include_hidden_audit=True,
    )

    assert (
        visible["layers"][Layer.RUNTIME_WORKSPACE.value]["items"][0]["material_id"]
        == "workspace.main.visible"
    )
    assert {
        item["asset_id"] for item in visible["layers"][Layer.RECALL.value]["items"]
    } == {"recall.main.visible"}
    assert {
        item["asset_id"] for item in visible["layers"][Layer.ARCHIVAL.value]["items"]
    } == {"archival.global.visible"}
    assert "hidden_audit_items" not in visible["layers"][Layer.RECALL.value]
    assert {
        item["asset_id"]
        for item in audit["layers"][Layer.RECALL.value]["hidden_audit_items"]
    } == {"recall.sibling.hidden"}
    assert {
        item["asset_id"]
        for item in audit["layers"][Layer.ARCHIVAL.value]["hidden_audit_items"]
    } == {"archival.sibling.hidden"}

    assert visible["canonical_envelope"] == {
        "schema_version": "rp.memory.display.v1",
        "producer": "MemoryInspectionService",
        "governance_bound": True,
        "shared_by": [
            "inspection_ui",
            "governed_user_edit_ui",
            "worker_proposal_trace",
            "debug_eval_tools",
        ],
    }
    blocks_by_layer = {block["layer"]: block for block in visible["blocks"]}
    core_block = blocks_by_layer[Layer.CORE_STATE_AUTHORITATIVE.value]
    assert core_block["block_id"] == "block.chapter.current"
    assert core_block["permission_level"]["governance"] == (
        "shared_core_mutation_kernel"
    )
    assert core_block["editable_fields"] == ["title"]
    assert core_block["allowed_actions"] == ["inspect", "direct_core_edit"]
    assert core_block["entrypoints"]["direct_core_edit"]["path_template"].endswith(
        "/memory/core/direct-edit"
    )
    assert core_block["entries"][0]["entry_id"] == "block.chapter.current:current"
    assert core_block["entries"][0]["base_revision"] == 3
    assert core_block["entries"][0]["conflict_state"] == "none"

    workspace_block = blocks_by_layer[Layer.RUNTIME_WORKSPACE.value]
    assert workspace_block["block_id"] == (
        "runtime_workspace:material:workspace.main.visible"
    )
    assert workspace_block["permission_level"]["durable_edit"] is False
    assert workspace_block["allowed_actions"] == ["inspect"]
    assert workspace_block["entries"][0]["entry_id"] == "workspace.main.visible"

    recall_block = blocks_by_layer[Layer.RECALL.value]
    assert recall_block["block_id"] == "recall:asset:recall.main.visible"
    assert "review_recall:invalidate" in recall_block["allowed_actions"]
    assert "direct_core_edit" not in recall_block["allowed_actions"]
    assert recall_block["entrypoints"]["review_recall"]["governed_by"] == (
        "RecallLifecycleService"
    )
    assert recall_block["entries"][0]["entry_id"] == "recall.main.visible"
    assert {
        source_ref["source_type"] for source_ref in recall_block["source_refs"]
    } >= {"story_turn", "retrieval_asset"}

    archival_block = blocks_by_layer[Layer.ARCHIVAL.value]
    assert archival_block["block_id"] == ("archival:asset:archival.global.visible")
    assert archival_block["editable_fields"] == ["replacement_sections"]
    assert archival_block["permission_level"]["raw_source_overwrite"] is False
    assert archival_block["entrypoints"]["evolve_archival"]["governed_by"] == (
        "ArchivalEvolutionService.evolve_source"
    )
    assert archival_block["entries"][0]["base_revision"] == 1

    hidden_block_ids = {block["block_id"] for block in audit["hidden_audit_blocks"]}
    assert hidden_block_ids == {
        "recall:asset:recall.sibling.hidden",
        "archival:asset:archival.sibling.hidden",
    }


@pytest.mark.asyncio
async def test_core_direct_edit_routes_product_surface_to_block_mutation_kernel(
    retrieval_session,
):
    main_identity, _ = _seed_identities(retrieval_session)
    mutation_service = _FakeBlockMutationService()
    service = _inspection_service(
        retrieval_session,
        block_mutation_service=mutation_service,
    )

    receipt = await service.direct_core_edit(
        request=DirectCoreEditRequest(
            identity=main_identity,
            actor="user.memory_editor",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                        "revision": 3,
                    },
                    "field_patch": {"title": "Corrected"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 3,
                }
            ],
            reason="user-visible direct edit",
        )
    )

    assert receipt.status == "applied"
    assert mutation_service.calls == [
        {
            "session_id": main_identity.session_id,
            "block_id": "block.chapter.current",
            "payload": mutation_service.calls[0]["payload"],
        }
    ]
    assert mutation_service.calls[0]["payload"].actor == "user.memory_editor"


def test_recall_review_routes_through_lifecycle_and_rejects_hidden_refs(
    retrieval_session,
):
    main_identity, sibling_identity = _seed_identities(retrieval_session)
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="recall.review.visible",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER.value,
        visibility_scope="branch_scoped",
        owning_branch_head_id=main_identity.branch_head_id,
        origin_turn_id=main_identity.turn_id,
    )
    _seed_asset(
        retrieval_session,
        identity=sibling_identity,
        asset_id="recall.review.hidden",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER.value,
        visibility_scope="branch_scoped",
        owning_branch_head_id=sibling_identity.branch_head_id,
        origin_turn_id=sibling_identity.turn_id,
    )
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        story_id="foreign-story",
        asset_id="recall.review.foreign_story",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER.value,
        visibility_scope="story_global",
        owning_branch_head_id=None,
        origin_turn_id=None,
    )
    lifecycle_service = _FakeRecallLifecycleService()
    service = _inspection_service(
        retrieval_session,
        recall_lifecycle_service=lifecycle_service,
    )

    receipt = service.review_recall(
        command=RecallReviewCommand(
            identity=main_identity,
            actor="user.memory_editor",
            action="invalidate",
            material_refs=["recall.review.visible"],
            reason="stale recall",
            event_id="event.recall.review.1",
        )
    )

    assert receipt.routed_through == "RecallLifecycleService"
    assert receipt.touched_material_refs == ["recall.review.visible"]
    assert lifecycle_service.invalidated == {
        "material_refs": ["recall.review.visible"],
        "event_id": "event.recall.review.1",
        "reason": "stale recall",
    }
    with pytest.raises(
        MemoryInspectionError, match="memory_inspection_material_not_visible"
    ):
        service.review_recall(
            command=RecallReviewCommand(
                identity=main_identity,
                actor="user.memory_editor",
                action="invalidate",
                material_refs=["recall.review.hidden"],
                reason="hidden sibling recall",
            )
        )
    with pytest.raises(
        MemoryInspectionError, match="memory_inspection_material_story_mismatch"
    ):
        service.review_recall(
            command=RecallReviewCommand(
                identity=main_identity,
                actor="user.memory_editor",
                action="invalidate",
                material_refs=["recall.review.foreign_story"],
                reason="foreign story recall",
            )
        )


def test_archival_evolution_routes_through_governed_service(
    retrieval_session,
):
    main_identity, _ = _seed_identities(retrieval_session)
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="archival.review.visible",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE.value,
        visibility_scope="story_global",
        owning_branch_head_id=None,
        origin_turn_id=None,
    )
    _seed_asset(
        retrieval_session,
        identity=main_identity,
        story_id="foreign-story",
        asset_id="archival.review.foreign_story",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE.value,
        visibility_scope="story_global",
        owning_branch_head_id=None,
        origin_turn_id=None,
    )
    evolution_service = _FakeArchivalEvolutionService()
    service = _inspection_service(
        retrieval_session,
        archival_evolution_service=evolution_service,
    )

    receipt = service.evolve_archival(
        request=ArchivalEvolutionRequest(
            identity=main_identity,
            actor="user.memory_editor",
            source_asset_id="archival.review.visible",
            expected_source_version=1,
            replacement_sections=[
                {
                    "text": "Corrected archival source.",
                    "metadata": {"domain": Domain.WORLD_RULE.value},
                }
            ],
            reason="user-visible archival correction",
        )
    )

    assert evolution_service.request is not None
    assert evolution_service.request.actor == "user.memory_editor"
    assert receipt.evolution_id == "evolution.visible.1"
    assert receipt.reindex_job_ids == ["job.reindex.visible.1"]

    with pytest.raises(
        MemoryInspectionError, match="memory_inspection_material_story_mismatch"
    ):
        service.evolve_archival(
            request=ArchivalEvolutionRequest(
                identity=main_identity,
                actor="user.memory_editor",
                source_asset_id="archival.review.foreign_story",
                expected_source_version=1,
                replacement_sections=[
                    {
                        "text": "Cross-story archival source.",
                        "metadata": {"domain": Domain.WORLD_RULE.value},
                    }
                ],
                reason="foreign story archival correction",
            )
        )
    assert evolution_service.request.source_asset_id == "archival.review.visible"
