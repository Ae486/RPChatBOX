"""Tests for committed setup truth direct index/search/read behavior."""

from __future__ import annotations

from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_truth_index import SetupTruthIndexFilters
from rp.models.setup_workspace import StoryMode
from rp.services.setup_truth_index_service import SetupTruthIndexService
from rp.services.setup_workspace_service import SetupWorkspaceService


def _text_section(section_id: str, title: str, text: str) -> SetupDraftSection:
    return SetupDraftSection(
        section_id=section_id,
        title=title,
        kind="text",
        content={"text": text},
        retrieval_role="summary" if section_id == "summary" else "detail",
        tags=[section_id],
    )


def _world_block(*, title: str, summary: str, alias: str) -> SetupStageDraftBlock:
    return SetupStageDraftBlock(
        stage_id=SetupStageId.WORLD_BACKGROUND,
        entries=[
            SetupDraftEntry(
                entry_id="race_elf",
                entry_type="race",
                semantic_path="world_background.race.elf",
                title=title,
                display_label="Race",
                summary=summary,
                aliases=[alias],
                tags=["world", "race", "forest"],
                sections=[
                    _text_section("summary", "Summary", summary),
                    _text_section(
                        "culture", "Culture", "Forest cities under moonlight."
                    ),
                ],
            )
        ],
        notes="World background stage.",
    )


def _commit_world_block(
    service: SetupWorkspaceService,
    *,
    workspace_id: str,
    block: SetupStageDraftBlock,
):
    service.patch_stage_draft(
        workspace_id=workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        draft=block,
    )
    proposal = service.propose_stage_commit(
        workspace_id=workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        target_draft_refs=["stage:world_background:race_elf"],
    )
    accepted, _ = service.accept_commit(
        workspace_id=workspace_id,
        proposal_id=proposal.proposal_id,
    )
    return accepted


def test_setup_truth_index_rebuilds_stage_entry_and_section_rows(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-truth-index-1",
        mode=StoryMode.LONGFORM,
    )
    accepted = _commit_world_block(
        workspace_service,
        workspace_id=workspace.workspace_id,
        block=_world_block(
            title="Elf",
            summary="Moonlit forest cities.",
            alias="Eldar",
        ),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)

    index = SetupTruthIndexService().rebuild(workspace=workspace)

    refs = {row.ref for row in index.rows}
    assert accepted.commit_id in {row.commit_id for row in index.rows}
    assert "foundation:world_background" in refs
    assert "foundation:world_background:race_elf" in refs
    assert "foundation:world_background:race_elf:summary" in refs
    assert "foundation:world_background:race_elf:culture" in refs
    section = next(
        row
        for row in index.rows
        if row.ref == "foundation:world_background:race_elf:culture"
    )
    assert section.parent_path == "world_background.race.elf"
    assert section.preview_text == "Forest cities under moonlight."
    assert section.content_hash


def test_setup_truth_index_search_matches_title_alias_tag_and_path(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-truth-index-search-1",
        mode=StoryMode.LONGFORM,
    )
    _commit_world_block(
        workspace_service,
        workspace_id=workspace.workspace_id,
        block=_world_block(
            title="Elf", summary="Moonlit forest cities.", alias="Eldar"
        ),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)
    service = SetupTruthIndexService()

    by_alias = service.search(workspace=workspace, query="Eldar")
    by_tag = service.search(
        workspace=workspace,
        filters=SetupTruthIndexFilters(tags=["forest"]),
    )
    by_path = service.search(
        workspace=workspace,
        query="race elf",
        filters=SetupTruthIndexFilters(semantic_path_prefix="world_background.race"),
    )

    assert by_alias.items[0].ref == "foundation:world_background:race_elf"
    assert "foundation:world_background:race_elf" in {item.ref for item in by_tag.items}
    assert by_path.items[0].semantic_path.startswith("world_background.race")


def test_setup_truth_index_reads_exact_refs_and_stage_aliases(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-truth-index-read-1",
        mode=StoryMode.LONGFORM,
    )
    accepted = _commit_world_block(
        workspace_service,
        workspace_id=workspace.workspace_id,
        block=_world_block(
            title="Elf", summary="Moonlit forest cities.", alias="Eldar"
        ),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)

    result = SetupTruthIndexService().read_refs(
        workspace=workspace,
        refs=[
            "foundation:world_background:race_elf:summary",
            "stage:world_background:race_elf",
            "foundation:world_background:missing",
        ],
        detail="full",
        max_chars=1200,
    )

    found = {item.ref: item for item in result.items if item.found}
    assert result.success is False
    assert result.missing_refs == ["foundation:world_background:missing"]
    assert found["foundation:world_background:race_elf:summary"].source == (
        "committed_snapshot"
    )
    assert found["foundation:world_background:race_elf:summary"].commit_id == (
        accepted.commit_id
    )
    summary_payload = found["foundation:world_background:race_elf:summary"].payload
    assert summary_payload is not None
    assert summary_payload["content"]["text"] == "Moonlit forest cities."
    assert found["stage:world_background:race_elf"].semantic_path == (
        "world_background.race.elf"
    )


def test_setup_truth_index_defaults_to_latest_commit_per_stage(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-truth-index-latest-1",
        mode=StoryMode.LONGFORM,
    )
    old_commit = _commit_world_block(
        workspace_service,
        workspace_id=workspace.workspace_id,
        block=_world_block(title="Elf", summary="Old forest cities.", alias="Oldfolk"),
    )
    new_commit = _commit_world_block(
        workspace_service,
        workspace_id=workspace.workspace_id,
        block=_world_block(title="Elf", summary="New forest cities.", alias="Newfolk"),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)
    service = SetupTruthIndexService()

    latest = service.read_refs(
        workspace=workspace,
        refs=["foundation:world_background:race_elf:summary"],
        detail="full",
    )
    old = service.read_refs(
        workspace=workspace,
        refs=["foundation:world_background:race_elf:summary"],
        detail="full",
        commit_id=old_commit.commit_id,
    )

    assert latest.items[0].commit_id == new_commit.commit_id
    latest_payload = latest.items[0].payload
    assert latest_payload is not None
    assert latest_payload["content"]["text"] == "New forest cities."
    assert old.items[0].commit_id == old_commit.commit_id
    old_payload = old.items[0].payload
    assert old_payload is not None
    assert old_payload["content"]["text"] == "Old forest cities."
