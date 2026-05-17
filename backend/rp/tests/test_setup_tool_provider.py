"""Unit tests for setup tool provider error contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import (
    CommitProposalStatus,
    QuestionSeverity,
    QuestionStatus,
    SetupStepId,
    StoryMode,
)
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider
from rp.tools.setup_tool_registry import SETUP_TOOL_REGISTRY


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


def test_setup_tool_provider_registry_schema_handler_and_list_order_stay_aligned():
    provider = SetupToolProvider(
        workspace_service=cast(Any, _FakeWorkspaceService()),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    registry_names = [entry.name for entry in SETUP_TOOL_REGISTRY]
    listed_tools = provider.list_tools()

    assert len(set(registry_names)) == len(registry_names)
    assert list(provider._schemas.keys()) == registry_names
    assert list(provider._dispatch_handlers.keys()) == registry_names
    assert [tool.name for tool in listed_tools] == registry_names
    for entry, tool in zip(SETUP_TOOL_REGISTRY, listed_tools):
        assert provider._schemas[entry.name] is entry.input_model
        assert callable(provider._dispatch_handlers[entry.name])
        assert tool.server_id == provider.provider_id
        assert tool.server_name == provider.server_name
        assert tool.description == entry.description
        assert tool.input_schema == entry.input_model.model_json_schema()


@pytest.mark.parametrize(
    ("tool_name", "arguments", "required_fields"),
    [
        (
            "setup.asset.register",
            {
                "workspace_id": "workspace-1",
                "step_id": "foundation",
                "asset_kind": "reference",
            },
            ["source_ref"],
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


@pytest.mark.parametrize(
    "tool_name",
    [
        "setup.proposal.commit",
        "setup.question.raise",
        "setup.discussion.update_state",
        "setup.chunk.upsert",
        "setup.truth.write",
        "setup.patch.story_config",
        "setup.patch.writing_contract",
        "setup.patch.foundation_entry",
        "setup.patch.longform_blueprint",
        "setup.read.workspace",
        "setup.read.step_context",
        "setup.read.draft_refs",
        "setup.truth_index.search",
        "setup.truth_index.read_refs",
    ],
)
@pytest.mark.asyncio
async def test_confirmed_deleted_setup_tools_are_not_provider_callable(tool_name):
    provider = SetupToolProvider(
        workspace_service=cast(Any, _FakeWorkspaceService()),
        context_builder=_DummyContextBuilder(),
        runtime_state_service=_DummyRuntimeStateService(),
    )

    result = await provider.call_tool(
        tool_name=tool_name,
        arguments={"workspace_id": "workspace-1"},
    )

    payload = json.loads(result["content"])
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_TOOL"
    assert payload["code"] == "unknown_tool"


@pytest.mark.parametrize(
    "target_ref",
    ["stage:world_background:race_elf", "draft:world_background"],
)
@pytest.mark.asyncio
async def test_workspace_service_commit_proposal_routes_stage_refs_to_stage_commit(
    retrieval_session,
    target_ref,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-stage-commit-service-1",
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

    proposal = workspace_service.propose_stage_commit(
        workspace_id=workspace.workspace_id,
        stage_id=SetupStageId.WORLD_BACKGROUND,
        target_draft_refs=[target_ref],
        reason="World stage is ready.",
    )

    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert refreshed is not None
    assert refreshed.commit_proposals[-1].proposal_id == proposal.proposal_id
    assert proposal.step_id == SetupStageId.WORLD_BACKGROUND
    assert proposal.target_block_types == ["world_background"]
    assert proposal.target_draft_refs == [target_ref]


@pytest.mark.asyncio
async def test_workspace_service_keeps_raise_question_backend_capability(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-question-service-1",
        mode=StoryMode.LONGFORM,
    )

    question = workspace_service.raise_question(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
        text="Need runtime preset choice.",
        severity=QuestionSeverity.BLOCKING,
    )
    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert refreshed is not None
    assert question.text == "Need runtime preset choice."
    assert refreshed.open_questions[-1].question_id == question.question_id


def test_workspace_service_can_propose_commit_with_blocking_question_warning():
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

    proposal = service.propose_commit(
        workspace_id="workspace-1",
        step_id=SetupStepId.STORY_CONFIG,
        target_draft_refs=["draft:story_config"],
        unresolved_warnings=["blocking_questions_present"],
    )

    assert proposal.unresolved_warnings == ["blocking_questions_present"]
    assert service.propose_commit_called is True
    assert service.propose_commit_kwargs is not None
    assert service.propose_commit_kwargs["unresolved_warnings"] == [
        "blocking_questions_present"
    ]


def test_workspace_service_can_propose_commit_with_rejection_warning():
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

    proposal = service.propose_commit(
        workspace_id="workspace-1",
        step_id=SetupStepId.STORY_CONFIG,
        target_draft_refs=["draft:story_config"],
        unresolved_warnings=["previous_proposal_rejected"],
    )

    assert proposal.unresolved_warnings == ["previous_proposal_rejected"]
    assert service.propose_commit_called is True
    assert service.propose_commit_kwargs is not None
    assert service.propose_commit_kwargs["unresolved_warnings"] == [
        "previous_proposal_rejected"
    ]


@pytest.mark.asyncio
async def test_workspace_service_persists_commit_readiness_warnings(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
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

    proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
        target_draft_refs=["draft:story_config"],
        unresolved_warnings=["blocking_questions_present"],
    )

    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    assert proposal.unresolved_warnings == ["blocking_questions_present"]
    assert refreshed.commit_proposals[-1].unresolved_warnings == [
        "blocking_questions_present"
    ]
