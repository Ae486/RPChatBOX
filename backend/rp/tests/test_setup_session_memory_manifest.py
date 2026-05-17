"""Tests for SetupAgent session memory manifest generation."""

from __future__ import annotations

from rp.agent_runtime.contracts import SetupDraftRefReadInput, SetupDraftRefReadResult
from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import StoryMode
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.setup_agent_memory.service import SetupSessionMemoryService


def _unused_draft_reader(
    input_model: SetupDraftRefReadInput,
) -> SetupDraftRefReadResult:
    return SetupDraftRefReadResult(
        success=False,
        items=[],
        missing_refs=list(input_model.refs),
    )


def _seed_world_workspace(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-setup-memory-manifest-1",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_stage_draft(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        draft=SetupStageDraftBlock(
            stage_id=SetupStageId.WORLD_BACKGROUND,
            entries=[
                SetupDraftEntry(
                    entry_id="race_elf",
                    entry_type="race",
                    semantic_path="world_background.race.elf",
                    title="Elf",
                    summary="Moonlit forest cities.",
                    aliases=["Eldar"],
                    tags=["forest"],
                    sections=[
                        SetupDraftSection(
                            section_id="summary",
                            title="Summary",
                            kind="text",
                            content={"text": "Moonlit forest cities."},
                            retrieval_role="summary",
                            tags=["overview"],
                        )
                    ],
                )
            ],
            notes="World background notes.",
        ),
    )
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    return refreshed


def test_setup_session_memory_manifest_builds_editable_draft_refs(
    retrieval_session,
):
    workspace = _seed_world_workspace(retrieval_session)
    service = SetupSessionMemoryService(draft_ref_reader=_unused_draft_reader)

    manifest = service.build_manifest(workspace=workspace)

    by_ref = {item.ref: item for item in manifest.items}
    assert manifest.workspace_id == workspace.workspace_id
    assert "draft:world_background" not in by_ref
    assert by_ref["stage:world_background:race_elf"].ref_kind == "setup_fact_entry"
    assert (
        by_ref["stage:world_background:race_elf:summary"].ref_kind
        == "setup_fact_section"
    )
    assert by_ref["stage:world_background:race_elf"].source_kind == "editable_draft"
    assert by_ref["stage:world_background:race_elf"].stage == "world_background"
    assert by_ref["stage:world_background:race_elf"].freshness.workspace_version == (
        workspace.version
    )
    assert by_ref["stage:world_background:race_elf"].freshness.fingerprint


def test_setup_session_memory_manifest_builds_accepted_truth_fact_refs(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-setup-memory-manifest-truth-1",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_stage_draft(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        draft=SetupStageDraftBlock(
            stage_id=SetupStageId.WORLD_BACKGROUND,
            entries=[
                SetupDraftEntry(
                    entry_id="race_elf",
                    entry_type="race",
                    semantic_path="world_background.race.elf",
                    title="Elf",
                    summary="Accepted moonlit forest cities.",
                    sections=[
                        SetupDraftSection(
                            section_id="summary",
                            title="Summary",
                            kind="text",
                            content={"text": "Accepted moonlit forest cities."},
                            retrieval_role="summary",
                        )
                    ],
                )
            ],
        ),
    )
    proposal = workspace_service.propose_stage_commit(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        target_draft_refs=["stage:world_background:race_elf"],
    )
    workspace_service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=proposal.proposal_id,
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)
    assert workspace is not None
    service = SetupSessionMemoryService(draft_ref_reader=_unused_draft_reader)

    manifest = service.build_manifest(workspace=workspace)

    by_ref = {item.ref: item for item in manifest.items}
    entry = by_ref["foundation:world_background:race_elf"]
    section = by_ref["foundation:world_background:race_elf:summary"]
    assert entry.source_kind == "accepted_truth"
    assert entry.ref_kind == "setup_fact_entry"
    assert section.ref_kind == "setup_fact_section"


def test_setup_session_memory_manifest_stays_setup_session_scoped(
    retrieval_session,
):
    workspace = _seed_world_workspace(retrieval_session)
    service = SetupSessionMemoryService(draft_ref_reader=_unused_draft_reader)

    manifest = service.build_manifest(workspace=workspace)

    assert {item.source_kind for item in manifest.items}.issubset(
        {"editable_draft", "accepted_truth"}
    )
    assert {item.ref_kind for item in manifest.items}.issubset(
        {"setup_fact_entry", "setup_fact_section"}
    )
    assert all("recall" not in item.source_kind for item in manifest.items)
    assert all("archival" not in item.source_kind for item in manifest.items)
