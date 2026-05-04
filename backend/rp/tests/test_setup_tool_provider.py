"""Unit tests for setup tool provider error contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from rp.models.setup_drafts import (
    FoundationEntry,
    LongformBlueprintDraft,
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
    StoryConfigDraft,
    WritingContractDraft,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import (
    CommitProposalStatus,
    QuestionSeverity,
    QuestionStatus,
    SetupStepId,
    StoryMode,
)
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


class _DummyContextBuilder:
    def build(self, input_model):  # pragma: no cover - not used in these tests
        raise AssertionError("context builder should not be used in this test")


class _DummyRuntimeStateService:
    def get_snapshot(self, *, workspace_id: str, step_id):
        return None


class _FakeWorkspaceService:
    def __init__(self, workspace=None) -> None:
        self._workspace = workspace
        self.propose_commit_called = False
        self.propose_commit_kwargs: dict[str, Any] | None = None
        self.propose_stage_commit_called = False
        self.propose_stage_commit_kwargs: dict[str, Any] | None = None

    def get_workspace(self, workspace_id: str):
        return self._workspace

    def propose_commit(self, **kwargs):
        self.propose_commit_called = True
        self.propose_commit_kwargs = kwargs
        return SimpleNamespace(
            proposal_id="proposal-created",
            review_message="Review requested for story_config",
            unresolved_warnings=list(kwargs.get("unresolved_warnings") or []),
        )

    def propose_stage_commit(self, **kwargs):
        self.propose_stage_commit_called = True
        self.propose_stage_commit_kwargs = kwargs
        return SimpleNamespace(
            proposal_id="stage-proposal-created",
            review_message=f"Review requested for {kwargs['stage_id'].value}",
            unresolved_warnings=list(kwargs.get("unresolved_warnings") or []),
        )

    def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_setup_tool_provider_schema_validation_returns_machine_readable_details():
    provider = SetupToolProvider(
        workspace_service=cast(Any, _FakeWorkspaceService()),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name="setup.patch.story_config",
        arguments={"workspace_id": "workspace-1"},
    )

    payload = json.loads(result["content"])
    assert result["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["code"] == "schema_validation_failed"
    assert payload["details"]["tool_name"] == "setup.patch.story_config"
    assert payload["details"]["repair_strategy"] == "auto_repair"
    assert "patch" in payload["details"]["required_fields"]
    assert payload["details"]["provided_fields"] == ["workspace_id"]


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_still_requires_provider_contract_fields():
    provider = SetupToolProvider(
        workspace_service=cast(Any, _FakeWorkspaceService()),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name="setup.truth.write",
        arguments={
            "workspace_id": "workspace-1",
            "truth_write": {
                "write_id": "write-1",
                "current_step": SetupStepId.STORY_CONFIG.value,
                "operation": "merge",
                "payload": {"notes": "draft notes"},
            },
        },
    )

    payload = json.loads(result["content"])
    assert result["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["details"]["tool_name"] == "setup.truth.write"
    assert payload["details"]["repair_strategy"] == "auto_repair"
    assert set(payload["details"]["required_fields"]) == {
        "truth_write.block_type",
        "step_id",
    }


@pytest.mark.parametrize(
    ("tool_name", "arguments", "required_fields"),
    [
        (
            "setup.patch.foundation_entry",
            {"workspace_id": "workspace-1"},
            ["entry"],
        ),
        (
            "setup.patch.longform_blueprint",
            {"workspace_id": "workspace-1"},
            ["patch"],
        ),
        (
            "setup.question.raise",
            {
                "workspace_id": "workspace-1",
                "step_id": "foundation",
                "severity": "blocking",
            },
            ["text"],
        ),
        (
            "setup.asset.register",
            {
                "workspace_id": "workspace-1",
                "step_id": "foundation",
                "asset_kind": "reference",
            },
            ["source_ref"],
        ),
        (
            "setup.proposal.commit",
            {
                "workspace_id": "workspace-1",
                "step_id": "foundation",
            },
            ["target_draft_refs"],
        ),
    ],
)
@pytest.mark.asyncio
async def test_setup_tool_provider_key_tools_return_repairable_schema_errors(
    tool_name,
    arguments,
    required_fields,
):
    provider = SetupToolProvider(
        workspace_service=cast(Any, _FakeWorkspaceService()),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name=tool_name,
        arguments=arguments,
    )

    payload = json.loads(result["content"])
    assert result["success"] is False
    assert result["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["code"] == "schema_validation_failed"
    assert payload["details"]["tool_name"] == tool_name
    assert payload["details"]["failure_origin"] == "validation"
    assert payload["details"]["repair_strategy"] == "auto_repair"
    assert payload["details"]["required_fields"] == required_fields
    assert payload["details"]["errors"]
    assert payload["details"]["provided_fields"] == sorted(arguments.keys())


@pytest.mark.asyncio
async def test_setup_tool_provider_reads_stage_local_draft_refs(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-draft-refs-1",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            model_profile_ref="model:setup",
            notes="Use deliberate setup pacing.",
        ),
    )
    workspace_service.patch_writing_contract(
        workspace_id=workspace.workspace_id,
        patch=WritingContractDraft(style_rules=["plain, concrete prose"]),
    )
    workspace_service.patch_longform_blueprint(
        workspace_id=workspace.workspace_id,
        patch=LongformBlueprintDraft(premise="A guild regulates public magic."),
    )
    workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="magic-law",
            domain="rule",
            path="world.magic.law",
            title="Magic Law",
            content={"summary": "Public spellcasting requires guild permits."},
        ),
    )

    result = await provider.call_tool(
        tool_name="setup.read.draft_refs",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "refs": [
                "draft:story_config",
                "draft:writing_contract",
                "draft:longform_blueprint",
                "foundation:magic-law",
                "foundation:missing-law",
            ],
            "detail": "summary",
        },
    )

    payload = json.loads(result["content"])
    assert result["success"] is True
    assert payload["success"] is False
    assert payload["missing_refs"] == ["foundation:missing-law"]
    found = {item["ref"]: item for item in payload["items"] if item["found"]}
    assert found["draft:story_config"]["block_type"] == "story_config"
    assert "payload" not in found["draft:story_config"]
    assert "model:setup" in found["draft:story_config"]["summary"]
    assert found["draft:writing_contract"]["block_type"] == "writing_contract"
    assert found["draft:longform_blueprint"]["block_type"] == "longform_blueprint"
    assert found["foundation:magic-law"]["block_type"] == "foundation_entry"


@pytest.mark.asyncio
async def test_setup_tool_provider_reads_canonical_stage_draft_refs(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-draft-refs-stage-1",
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
                    sections=[
                        SetupDraftSection(
                            section_id="summary",
                            title="Summary",
                            kind="text",
                            content={"text": "Moonlit forest cities."},
                            retrieval_role="summary",
                        )
                    ],
                )
            ],
            notes="World background notes.",
        ),
    )

    result = await provider.call_tool(
        tool_name="setup.read.draft_refs",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "refs": [
                "draft:world_background",
                "stage:world_background:race_elf",
                "stage:world_background:race_elf:summary",
            ],
            "detail": "summary",
        },
    )

    payload = json.loads(result["content"])
    found = {item["ref"]: item for item in payload["items"] if item["found"]}
    assert result["success"] is True
    assert payload["success"] is True
    assert found["draft:world_background"]["block_type"] == "world_background"
    assert "World Background" in found["draft:world_background"]["title"]
    assert found["stage:world_background:race_elf"]["block_type"] == "world_background"
    assert found["stage:world_background:race_elf"]["title"] == "Elf"
    assert found["stage:world_background:race_elf:summary"]["title"] == "Summary"
    assert (
        "Moonlit forest cities."
        in found["stage:world_background:race_elf:summary"]["summary"]
    )


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_writes_stage_draft_entry(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-stage-truth-write-1",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.truth.write",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "truth_write": {
                "write_id": "write-race-elf",
                "current_step": "world_background",
                "block_type": "stage_draft",
                "stage_id": "world_background",
                "operation": "create",
                "payload": {
                    "entry_id": "race_elf",
                    "entry_type": "race",
                    "semantic_path": "world_background.race.elf",
                    "title": "Elf",
                    "summary": "Moonlit forest cities.",
                    "sections": [
                        {
                            "section_id": "summary",
                            "title": "Summary",
                            "kind": "text",
                            "content": {"text": "Moonlit forest cities."},
                            "retrieval_role": "summary",
                        }
                    ],
                },
                "ready_for_review": True,
            },
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert result["success"] is True
    assert payload["updated_refs"] == ["stage:world_background:race_elf"]
    assert refreshed is not None
    assert refreshed.foundation_draft is None
    assert refreshed.draft_blocks["world_background"].entries[0].entry_id == "race_elf"
    assert (
        payload["cognitive_state_snapshot"]["active_truth_write"]["block_type"]
        == "stage_draft"
    )
    assert (
        payload["cognitive_state_snapshot"]["active_truth_write"]["stage_id"]
        == "world_background"
    )


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_writes_full_stage_draft_block(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-stage-truth-write-block-1",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.truth.write",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "truth_write": {
                "write_id": "write-world-block",
                "current_step": "world_background",
                "block_type": "stage_draft",
                "stage_id": "world_background",
                "operation": "create",
                "target_ref": "draft:world_background",
                "payload": {
                    "stage_id": "world_background",
                    "entries": [
                        {
                            "entry_id": "location_moon_forest",
                            "entry_type": "location",
                            "semantic_path": "world_background.location.moon_forest",
                            "title": "Moon Forest",
                            "summary": "A luminous old forest.",
                            "sections": [
                                {
                                    "section_id": "summary",
                                    "title": "Summary",
                                    "kind": "text",
                                    "content": {"text": "A luminous old forest."},
                                }
                            ],
                        }
                    ],
                    "notes": "World background draft.",
                },
                "ready_for_review": True,
            },
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert result["success"] is True
    assert payload["updated_refs"] == ["draft:world_background"]
    assert refreshed is not None
    assert refreshed.foundation_draft is None
    assert refreshed.draft_blocks["world_background"].notes == "World background draft."
    assert (
        refreshed.draft_blocks["world_background"].entries[0].entry_id
        == "location_moon_forest"
    )


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_rejects_stage_payload_mismatch(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-stage-truth-write-2",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.truth.write",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "truth_write": {
                "write_id": "write-bad-block",
                "current_step": "world_background",
                "block_type": "stage_draft",
                "stage_id": "world_background",
                "operation": "create",
                "target_ref": "draft:world_background",
                "payload": {
                    "stage_id": "character_design",
                    "entries": [],
                },
                "ready_for_review": False,
            },
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert result["success"] is False
    assert result["error_code"] == "SETUP_TOOL_FAILED"
    assert payload["code"] == "setup_truth_write_stage_id_mismatch"
    assert refreshed is not None
    assert "world_background" not in refreshed.draft_blocks


@pytest.mark.parametrize(
    "target_ref",
    ["stage:world_background:race_elf", "draft:world_background"],
)
@pytest.mark.asyncio
async def test_setup_tool_provider_commit_proposal_routes_stage_refs_to_stage_commit(
    retrieval_session,
    target_ref,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-stage-commit-tool-1",
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
                    sections=[
                        SetupDraftSection(
                            section_id="summary",
                            title="Summary",
                            kind="text",
                            content={"text": "Moonlit forest cities."},
                        )
                    ],
                )
            ],
        ),
    )

    result = await provider.call_tool(
        tool_name="setup.proposal.commit",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "target_draft_refs": [target_ref],
            "reason": "World stage is ready.",
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    proposal = refreshed.commit_proposals[-1] if refreshed is not None else None

    assert result["success"] is True
    assert payload["updated_refs"][0].startswith("proposal:")
    assert proposal is not None
    assert proposal.step_id == SetupStageId.WORLD_BACKGROUND
    assert proposal.target_block_types == ["world_background"]
    assert proposal.target_draft_refs == [target_ref]


@pytest.mark.asyncio
async def test_setup_tool_provider_draft_ref_full_detail_honors_max_chars(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-draft-refs-2",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="long-entry",
            domain="world",
            path="world.long",
            content={"summary": "x" * 200},
        ),
    )

    result = await provider.call_tool(
        tool_name="setup.read.draft_refs",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "refs": ["foundation:long-entry"],
            "detail": "full",
            "max_chars": 80,
        },
    )

    payload = json.loads(result["content"])
    item = payload["items"][0]
    assert item["found"] is True
    assert item["payload"]["_truncated"] is True
    assert len(item["payload"]["preview"]) == 80


@pytest.mark.asyncio
async def test_setup_tool_provider_draft_refs_requires_refs(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-draft-refs-3",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.read.draft_refs",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "foundation",
            "refs": [],
        },
    )

    payload = json.loads(result["content"])
    assert result["error_code"] == "SETUP_DRAFT_REFS_REQUIRED"
    assert payload["code"] == "setup_draft_refs_required"
    assert payload["details"]["required_fields"] == ["refs"]


@pytest.mark.asyncio
async def test_setup_tool_provider_allows_commit_with_blocking_question_warning():
    workspace = SimpleNamespace(
        open_questions=[
            SimpleNamespace(
                question_id="q1",
                step_id=SetupStepId.STORY_CONFIG,
                status=QuestionStatus.OPEN,
                severity=QuestionSeverity.BLOCKING,
            )
        ],
        commit_proposals=[],
    )
    service = _FakeWorkspaceService(workspace=workspace)
    provider = SetupToolProvider(
        workspace_service=cast(Any, service),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name="setup.proposal.commit",
        arguments={
            "workspace_id": "workspace-1",
            "step_id": "story_config",
            "target_draft_refs": ["draft:story_config"],
        },
    )

    payload = json.loads(result["content"])
    assert result["success"] is True
    assert result["error_code"] is None
    assert payload["warnings"] == ["blocking_questions_present"]
    assert service.propose_commit_called is True
    assert service.propose_commit_kwargs is not None
    assert service.propose_commit_kwargs["unresolved_warnings"] == [
        "blocking_questions_present"
    ]


@pytest.mark.asyncio
async def test_setup_tool_provider_allows_reproposal_with_rejection_warning():
    now = datetime.now(timezone.utc)
    workspace = SimpleNamespace(
        open_questions=[],
        commit_proposals=[
            SimpleNamespace(
                proposal_id="proposal-1",
                step_id=SetupStepId.STORY_CONFIG,
                status=CommitProposalStatus.REJECTED,
                created_at=now,
                reviewed_at=now,
            )
        ],
    )
    service = _FakeWorkspaceService(workspace=workspace)
    provider = SetupToolProvider(
        workspace_service=cast(Any, service),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name="setup.proposal.commit",
        arguments={
            "workspace_id": "workspace-1",
            "step_id": "story_config",
            "target_draft_refs": ["draft:story_config"],
        },
    )

    payload = json.loads(result["content"])
    assert result["success"] is True
    assert result["error_code"] is None
    assert payload["warnings"] == ["previous_proposal_rejected"]
    assert service.propose_commit_called is True
    assert service.propose_commit_kwargs is not None
    assert service.propose_commit_kwargs["unresolved_warnings"] == [
        "previous_proposal_rejected"
    ]


@pytest.mark.asyncio
async def test_setup_tool_provider_persists_commit_readiness_warnings(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )
    workspace = workspace_service.create_workspace(
        story_id="story-commit-warnings-1",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.raise_question(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
        text="Need runtime preset choice.",
        severity=QuestionSeverity.BLOCKING,
    )

    result = await provider.call_tool(
        tool_name="setup.proposal.commit",
        arguments={
            "workspace_id": workspace.workspace_id,
            "step_id": "story_config",
            "target_draft_refs": ["draft:story_config"],
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    assert result["success"] is True
    assert payload["warnings"] == ["blocking_questions_present"]
    assert refreshed.commit_proposals[-1].unresolved_warnings == [
        "blocking_questions_present"
    ]
