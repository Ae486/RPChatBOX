"""Core-completeness coverage for default RP memory tool write paths."""

from __future__ import annotations

import json

import pytest

from config import get_settings
from rp.models.dsl import Layer
from rp.models.story_runtime import LongformChapterPhase
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.proposal.repository import ProposalRepository
from rp.services.story.session_service import StorySessionService
from rp.tools.memory_crud_provider import MemoryCrudToolProvider


def _enable_core_shadow_write(monkeypatch) -> None:
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_WRITE_ENABLED", "true")
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_WRITE_SWITCH_ENABLED",
        "false",
    )
    get_settings.cache_clear()


def _seed_story_runtime(retrieval_session) -> str:
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-tool-core-write",
        source_workspace_id="workspace-tool-core-write",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return session.session_id


@pytest.mark.asyncio
async def test_default_memory_crud_provider_auto_apply_dual_writes_core_and_mirror(
    retrieval_session,
    monkeypatch,
):
    _enable_core_shadow_write(monkeypatch)
    session_id = _seed_story_runtime(retrieval_session)
    provider = MemoryCrudToolProvider()

    result = await provider.call_tool(
        tool_name="proposal.submit",
        arguments={
            "story_id": "story-tool-core-write",
            "mode": "longform",
            "domain": "timeline",
            "domain_path": "timeline.event_spine",
            "operations": [
                {
                    "kind": "append_event",
                    "target_ref": {
                        "object_id": "timeline.event_spine",
                        "layer": "core_state.authoritative",
                        "domain": "timeline",
                        "domain_path": "timeline.event_spine",
                    },
                    "event_data": {"event": "tool-auto-applied"},
                }
            ],
            "reason": "tool default core-completeness",
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["status"] == "applied"
    retrieval_session.expire_all()

    repository = ProposalRepository(retrieval_session)
    apply_receipts = repository.list_apply_receipts_for_proposal(payload["proposal_id"])
    assert len(apply_receipts) == 1
    assert apply_receipts[0].apply_backend == "dual_write"
    target_links = repository.list_apply_target_links_for_apply(apply_receipts[0].apply_id)
    assert len(target_links) == 1
    assert target_links[0].object_id == "timeline.event_spine"

    core_repo = CoreStateStoreRepository(retrieval_session)
    current_row = core_repo.get_authoritative_object(
        session_id=session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        scope="story",
        object_id="timeline.event_spine",
    )
    assert current_row is not None
    assert current_row.current_revision == 1
    assert current_row.data_json == [{"event": "tool-auto-applied"}]
    revisions = core_repo.list_authoritative_revisions(
        session_id=session_id,
        object_id="timeline.event_spine",
    )
    assert [revision.revision for revision in revisions] == [1]
    assert revisions[0].source_apply_id == apply_receipts[0].apply_id

    updated_session = StorySessionService(retrieval_session).get_session(session_id)
    assert updated_session is not None
    assert updated_session.current_state_json["timeline_spine"] == [
        {"event": "tool-auto-applied"}
    ]
