"""Tests for canonical setup stage modules and data-driven draft blocks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.rp_setup_store import SetupDraftBlockRecord
from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId, get_stage_module
from rp.models.setup_workspace import SetupStepLifecycleState, StoryMode
from rp.services.setup_workspace_service import SetupWorkspaceService


def _text_section(section_id: str, title: str, text: str) -> SetupDraftSection:
    return SetupDraftSection(
        section_id=section_id,
        title=title,
        kind="text",
        content={"text": text},
    )


def _stage_block(
    stage_id: SetupStageId, entry_id: str, semantic_path: str
) -> SetupStageDraftBlock:
    return SetupStageDraftBlock(
        stage_id=stage_id,
        entries=[
            SetupDraftEntry(
                entry_id=entry_id,
                entry_type="world_rule"
                if stage_id == SetupStageId.WORLD_BACKGROUND
                else "character",
                semantic_path=semantic_path,
                title=semantic_path.rsplit(".", 1)[-1],
                sections=[
                    _text_section(
                        "summary",
                        "Summary",
                        f"{semantic_path} summary",
                    )
                ],
            )
        ],
    )


def test_longform_workspace_initializes_canonical_stage_plan(retrieval_session):
    service = SetupWorkspaceService(retrieval_session)

    workspace = service.create_workspace(
        story_id="story-stage-plan-1",
        mode=StoryMode.LONGFORM,
    )

    assert workspace.current_step.value == "foundation"
    assert workspace.current_stage == SetupStageId.WORLD_BACKGROUND
    assert [stage.value for stage in workspace.stage_plan] == [
        "world_background",
        "character_design",
        "plot_blueprint",
        "writer_config",
        "worker_config",
        "overview",
        "activate",
    ]
    assert [state.stage_id for state in workspace.stage_states] == workspace.stage_plan
    assert {state.step_id.value for state in workspace.step_states} == {
        "foundation",
        "longform_blueprint",
        "writing_contract",
        "story_config",
    }
    assert (
        get_stage_module(SetupStageId.WRITER_CONFIG).draft_block_type == "writer_config"
    )


def test_stage_draft_blocks_are_separate_from_legacy_foundation(retrieval_session):
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(
        story_id="story-stage-blocks-1",
        mode=StoryMode.LONGFORM,
    )

    workspace = service.patch_stage_draft(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        draft=_stage_block(
            SetupStageId.WORLD_BACKGROUND,
            "race_elf",
            "world_background.race.elf",
        ),
    )
    workspace = service.patch_stage_draft(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.CHARACTER_DESIGN,
        draft=_stage_block(
            SetupStageId.CHARACTER_DESIGN,
            "hero_lin",
            "character_design.protagonist.lin",
        ),
    )

    assert set(workspace.draft_blocks) == {"world_background", "character_design"}
    assert workspace.draft_blocks["world_background"].entries[0].entry_id == "race_elf"
    assert workspace.draft_blocks["character_design"].entries[0].entry_id == "hero_lin"
    assert workspace.foundation_draft is None
    assert (
        workspace.readiness_status.step_readiness["world_background"].value
        == "ready_for_commit"
    )
    assert (
        workspace.readiness_status.step_readiness["character_design"].value
        == "ready_for_commit"
    )


def test_patch_stage_draft_rejects_stage_outside_mode_plan(retrieval_session):
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(
        story_id="story-stage-plan-reject-1",
        mode=StoryMode.LONGFORM,
    )

    with pytest.raises(ValueError, match="not in mode plan"):
        service.patch_stage_draft(
            workspace_id=workspace.workspace_id,
            stage_id=SetupStageId.TRPG_RULES,
            draft=SetupStageDraftBlock(stage_id=SetupStageId.TRPG_RULES),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "stage_id": "world_background",
            "entries": [
                {
                    "entry_id": "",
                    "entry_type": "race",
                    "semantic_path": "world_background.race.elf",
                    "title": "Elf",
                    "sections": [],
                }
            ],
        },
        {
            "stage_id": "world_background",
            "entries": [
                {
                    "entry_id": "race_elf",
                    "entry_type": "race",
                    "semantic_path": "",
                    "title": "Elf",
                    "sections": [],
                }
            ],
        },
        {
            "stage_id": "world_background",
            "entries": [
                {
                    "entry_id": "race_elf",
                    "entry_type": "race",
                    "semantic_path": "world_background.race.elf",
                    "title": "Elf",
                    "sections": [
                        {
                            "section_id": "summary",
                            "title": "Summary",
                            "kind": "unknown",
                            "content": {"text": "Elves live long."},
                        }
                    ],
                }
            ],
        },
        {
            "stage_id": "world_background",
            "entries": [
                {
                    "entry_id": "race_elf",
                    "entry_type": "race",
                    "semantic_path": "world_background.race.elf",
                    "title": "Elf",
                    "sections": [
                        {
                            "section_id": "summary",
                            "title": "Summary",
                            "kind": "text",
                            "content": {},
                        }
                    ],
                }
            ],
        },
    ],
)
def test_stage_draft_block_validates_entry_and_section_shape(payload):
    with pytest.raises(ValidationError):
        SetupStageDraftBlock.model_validate(payload)


def test_stage_commit_freezes_only_current_stage_and_advances_stage_lifecycle(
    retrieval_session,
):
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(
        story_id="story-stage-commit-1",
        mode=StoryMode.LONGFORM,
    )
    workspace = service.patch_stage_draft(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        draft=_stage_block(
            SetupStageId.WORLD_BACKGROUND,
            "race_elf",
            "world_background.race.elf",
        ),
    )

    proposal = service.propose_stage_commit(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        target_draft_refs=["stage:world_background:race_elf"],
    )
    accepted, jobs = service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=proposal.proposal_id,
    )
    workspace = service.get_workspace(workspace.workspace_id)

    assert accepted.step_id == SetupStageId.WORLD_BACKGROUND
    assert accepted.snapshots[0].block_type == "world_background"
    assert accepted.snapshots[0].payload["stage_id"] == "world_background"
    assert accepted.committed_refs == ["stage:world_background:race_elf"]
    assert [job.step_id for job in jobs] == [SetupStageId.WORLD_BACKGROUND]
    assert workspace.current_stage == SetupStageId.CHARACTER_DESIGN
    state_by_stage = {state.stage_id: state for state in workspace.stage_states}
    assert (
        state_by_stage[SetupStageId.WORLD_BACKGROUND].state
        == SetupStepLifecycleState.FROZEN
    )
    assert (
        state_by_stage[SetupStageId.CHARACTER_DESIGN].state
        == SetupStepLifecycleState.DISCUSSING
    )
    assert workspace.current_step.value == "foundation"


def test_stage_commit_rejects_structurally_invalid_stored_stage_payload(
    retrieval_session,
):
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(
        story_id="story-stage-invalid-commit-1",
        mode=StoryMode.LONGFORM,
    )
    retrieval_session.add(
        SetupDraftBlockRecord(
            draft_block_id="invalid-stage-block",
            workspace_id=workspace.workspace_id,
            step_id=SetupStageId.WORLD_BACKGROUND.value,
            block_type=SetupStageId.WORLD_BACKGROUND.value,
            payload_json={
                "stage_id": "world_background",
                "entries": [
                    {
                        "entry_id": "race_elf",
                        "entry_type": "race",
                        "semantic_path": "",
                        "title": "Elf",
                        "sections": [],
                    }
                ],
            },
        )
    )
    retrieval_session.commit()

    with pytest.raises(ValidationError):
        service.propose_stage_commit(
            workspace_id=workspace.workspace_id,
            stage_id=SetupStageId.WORLD_BACKGROUND,
            target_draft_refs=["stage:world_background:race_elf"],
        )


def test_stage_commit_rejects_stored_stage_payload_mismatch(retrieval_session):
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(
        story_id="story-stage-mismatch-commit-1",
        mode=StoryMode.LONGFORM,
    )
    retrieval_session.add(
        SetupDraftBlockRecord(
            draft_block_id="mismatched-stage-block",
            workspace_id=workspace.workspace_id,
            step_id=SetupStageId.WORLD_BACKGROUND.value,
            block_type=SetupStageId.WORLD_BACKGROUND.value,
            payload_json={
                "stage_id": "character_design",
                "entries": [
                    {
                        "entry_id": "hero_lin",
                        "entry_type": "character",
                        "semantic_path": "character_design.protagonist.lin",
                        "title": "Lin",
                        "sections": [
                            {
                                "section_id": "summary",
                                "title": "Summary",
                                "kind": "text",
                                "content": {"text": "Lin summary"},
                            }
                        ],
                    }
                ],
            },
        )
    )
    retrieval_session.commit()

    with pytest.raises(ValueError, match="Stored stage draft block mismatch"):
        service.propose_stage_commit(
            workspace_id=workspace.workspace_id,
            stage_id=SetupStageId.WORLD_BACKGROUND,
            target_draft_refs=["stage:world_background:hero_lin"],
        )
