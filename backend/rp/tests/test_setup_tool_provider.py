"""Unit tests for setup tool provider error contracts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rp.models.setup_drafts import (
    FoundationEntry,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)
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
        self.propose_commit_kwargs = None

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

    def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_setup_tool_provider_schema_validation_returns_machine_readable_details():
    provider = SetupToolProvider(
        workspace_service=_FakeWorkspaceService(),
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
async def test_setup_tool_provider_draft_ref_full_detail_honors_max_chars(retrieval_session):
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
        workspace_service=service,
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
        workspace_service=service,
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
    assert service.propose_commit_kwargs["unresolved_warnings"] == [
        "previous_proposal_rejected"
    ]


@pytest.mark.asyncio
async def test_setup_tool_provider_persists_commit_readiness_warnings(retrieval_session):
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
