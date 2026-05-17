"""Tests for deterministic SetupAgent session memory search/read."""

from __future__ import annotations

import json

from rp.models.setup_drafts import (
    SetupDraftEntry,
    SetupDraftSection,
    SetupStageDraftBlock,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import StoryMode
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.setup_agent_memory.contracts import SetupSessionMemorySearchFilters
from rp.setup_agent_memory.service import SetupSessionMemoryService
from rp.tools.setup_tools.read_draft_refs import ReadDraftRefsTool
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_truth_index_service import SetupTruthIndexService


def _seed_workspace(
    retrieval_session,
    *,
    long_text: str = "Moonlit forest cities.",
    entry_summary: str = "Moonlit forest cities.",
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-setup-memory-search-1",
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
                    summary=entry_summary,
                    tags=["forest"],
                    sections=[
                        SetupDraftSection(
                            section_id="summary",
                            title="Summary",
                            kind="text",
                            content={"text": long_text},
                            retrieval_role="summary",
                        )
                    ],
                )
            ],
        ),
    )
    workspace = workspace_service.get_workspace(workspace.workspace_id)
    assert workspace is not None
    return workspace_service, workspace


def _service(retrieval_session, workspace_service):
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    draft_tool = ReadDraftRefsTool(
        workspace_service=workspace_service,
        context_builder=SetupContextBuilder(workspace_service),
        runtime_state_service=runtime_state_service,
        truth_index_service=SetupTruthIndexService(),
    )
    return SetupSessionMemoryService(
        draft_ref_reader=lambda input_model: draft_tool._read_draft_refs(
            input_model=input_model
        )
    )


def test_setup_session_memory_search_returns_small_deterministic_hits(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(retrieval_session)
    service = _service(retrieval_session, workspace_service)

    result = service.search(
        workspace=workspace,
        query="Moonlit forest",
        filters=SetupSessionMemorySearchFilters(stages=["world_background"]),
        limit=3,
    )

    assert result.success is True
    assert result.items[0].ref == "stage:world_background:race_elf"
    assert result.items[0].scope == "entry"
    assert result.items[0].navigation_summary == "Moonlit forest cities."
    assert not hasattr(result.items[0], "payload")
    assert not hasattr(result.items[0], "source_kind")
    assert not hasattr(result.items[0], "score")


def test_setup_session_memory_search_bounds_returned_summary(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(
        retrieval_session,
        entry_summary="Moonlit " + ("forest " * 120),
    )
    service = _service(retrieval_session, workspace_service)

    result = service.search(
        workspace=workspace,
        query="Moonlit",
        filters=SetupSessionMemorySearchFilters(stages=["world_background"]),
        limit=1,
    )

    assert result.items[0].navigation_summary is not None
    assert len(result.items[0].navigation_summary) == 500
    assert not hasattr(result.items[0], "payload")


def test_setup_session_memory_open_entry_returns_section_directory(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(retrieval_session)
    service = _service(retrieval_session, workspace_service)

    result = service.open_ref(
        workspace=workspace,
        ref="stage:world_background:race_elf",
    )

    assert result.success is True
    assert result.result_type == "index"
    assert result.opened_ref == "stage:world_background:race_elf"
    assert result.sections is not None
    assert result.sections[0].ref == "stage:world_background:race_elf:summary"
    assert result.content is None
    assert "四级目录" in result.message


def test_setup_session_memory_open_entry_bounds_section_navigation_summaries(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(
        retrieval_session,
        long_text="Moonlit " + ("forest " * 120),
        entry_summary="Short entry summary.",
    )
    service = _service(retrieval_session, workspace_service)

    result = service.open_ref(
        workspace=workspace,
        ref="stage:world_background:race_elf",
    )

    assert result.success is True
    assert result.sections is not None
    assert result.sections[0].navigation_summary is not None
    assert len(result.sections[0].navigation_summary) == 500
    assert result.content is None


def test_setup_session_memory_open_section_returns_clean_content(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(retrieval_session)
    service = _service(retrieval_session, workspace_service)

    result = service.open_ref(
        workspace=workspace,
        ref="stage:world_background:race_elf:summary",
    )

    assert result.success is True
    assert result.result_type == "content"
    assert result.content is not None
    assert result.content.type == "text"
    assert result.content.title == "Summary"
    assert result.content.text == "Moonlit forest cities."
    assert result.sections is None
    assert "事实依据" in result.message


def test_setup_session_memory_open_section_bounds_clean_content_without_payload_leak(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(
        retrieval_session,
        long_text="x" * 500,
    )
    service = _service(retrieval_session, workspace_service)

    result = service.open_ref(
        workspace=workspace,
        ref="stage:world_background:race_elf:summary",
        max_chars=80,
    )

    assert result.success is True
    assert result.truncated is True
    assert result.content is not None
    assert result.content.type == "text"
    assert result.content.text == "x" * 80
    encoded = json.dumps(
        result.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "section_id" not in encoded
    assert "retrieval_role" not in encoded
    assert "source_kind" not in encoded
    assert "ref_kind" not in encoded
    assert "fingerprint" not in encoded


def test_setup_session_memory_open_accepted_truth_section_uses_same_shape(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(
        retrieval_session,
        long_text="Accepted moonlit forest cities.",
        entry_summary="Accepted moonlit forest cities.",
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
    service = _service(retrieval_session, workspace_service)

    entry = service.open_ref(
        workspace=workspace,
        ref="foundation:world_background:race_elf",
    )
    section = service.open_ref(
        workspace=workspace,
        ref="foundation:world_background:race_elf:summary",
    )

    assert entry.result_type == "index"
    assert entry.sections is not None
    assert entry.sections[0].ref == "foundation:world_background:race_elf:summary"
    assert section.result_type == "content"
    assert section.content is not None
    assert section.content.type == "text"
    assert section.content.text == "Accepted moonlit forest cities."


def test_setup_session_memory_read_refs_reports_missing_and_bounds_payload(
    retrieval_session,
):
    workspace_service, workspace = _seed_workspace(
        retrieval_session, long_text="x" * 500
    )
    service = _service(retrieval_session, workspace_service)

    result = service.read_refs(
        workspace=workspace,
        refs=[
            "stage:world_background:race_elf:summary",
            "stage:world_background:missing",
        ],
        detail="full",
        max_chars=80,
    )

    found = {item.ref: item for item in result.items if item.found}
    assert result.success is False
    assert result.missing_refs == ["stage:world_background:missing"]
    assert found["stage:world_background:race_elf:summary"].payload == {
        "_truncated": True,
        "preview": found["stage:world_background:race_elf:summary"].payload["preview"],
    }
    assert (
        len(found["stage:world_background:race_elf:summary"].payload["preview"]) == 80
    )
