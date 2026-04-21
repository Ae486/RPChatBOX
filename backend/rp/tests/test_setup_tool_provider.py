"""Unit tests for setup tool provider error contracts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rp.models.setup_workspace import CommitProposalStatus, QuestionSeverity, QuestionStatus, SetupStepId
from rp.tools.setup_tool_provider import SetupToolProvider


class _DummyContextBuilder:
    def build(self, input_model):  # pragma: no cover - not used in these tests
        raise AssertionError("context builder should not be used in this test")


class _FakeWorkspaceService:
    def __init__(self, workspace=None) -> None:
        self._workspace = workspace
        self.propose_commit_called = False

    def get_workspace(self, workspace_id: str):
        return self._workspace

    def propose_commit(self, **kwargs):
        self.propose_commit_called = True
        raise AssertionError("propose_commit should not be called when commit is blocked")

    def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_setup_tool_provider_schema_validation_returns_machine_readable_details():
    provider = SetupToolProvider(
        workspace_service=_FakeWorkspaceService(),
        context_builder=_DummyContextBuilder(),
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


@pytest.mark.asyncio
async def test_setup_tool_provider_blocks_commit_when_blocking_questions_exist():
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
    assert result["error_code"] == "SETUP_TOOL_FAILED"
    assert payload["code"] == "setup_commit_blocked"
    assert payload["details"]["repair_strategy"] == "block_commit"
    assert payload["details"]["block_commit"] is True
    assert service.propose_commit_called is False


@pytest.mark.asyncio
async def test_setup_tool_provider_blocks_reproposal_after_rejection():
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
    assert result["error_code"] == "SETUP_TOOL_FAILED"
    assert payload["code"] == "setup_commit_rejected_previously"
    assert payload["details"]["repair_strategy"] == "block_commit"
    assert payload["details"]["last_proposal_status"] == "rejected"
    assert service.propose_commit_called is False
