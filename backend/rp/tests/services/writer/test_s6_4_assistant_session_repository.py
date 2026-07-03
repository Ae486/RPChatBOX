"""S6-4 O-foundation oracle: assistant session store CRUD (REV-028).

Offline/deterministic. The assistant session is a story-scoped agent
conversation record, not story truth: list/load/save/delete must behave as
plain conversation storage and never touch runtime truth surfaces.
"""

from __future__ import annotations

import pytest

from rp.services.writer.assistant_session_repository import (
    AssistantSessionRepository,
    AssistantSessionRepositoryError,
)


def test_save_session_creates_then_updates_idempotently(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)

    created = repo.save_session(
        story_id="story-a",
        title="Plot talk",
        messages=[_turn("user", "hello")],
    )
    assert created.assistant_session_id
    assert created.title == "Plot talk"
    assert created.messages_json == [_turn("user", "hello")]

    updated = repo.save_session(
        assistant_session_id=created.assistant_session_id,
        story_id="story-a",
        messages=[_turn("user", "hello"), _turn("assistant", "hi")],
    )
    assert updated.assistant_session_id == created.assistant_session_id
    assert updated.title == "Plot talk"
    assert len(updated.messages_json) == 2

    # Upsert on the same id keeps exactly one row.
    rows = repo.list_sessions("story-a")
    assert [row.assistant_session_id for row in rows] == [
        created.assistant_session_id
    ]


def test_load_session_restores_conversation(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)
    saved = repo.save_session(
        story_id="story-a",
        title="Image chat",
        messages=[_turn("user", "draw the harbor"), _turn("assistant", "done")],
    )
    retrieval_session.commit()

    loaded = repo.load_session(saved.assistant_session_id)
    assert loaded is not None
    assert loaded.story_id == "story-a"
    assert [item["text"] for item in loaded.messages_json] == [
        "draw the harbor",
        "done",
    ]
    assert repo.load_session("assistant_session_missing") is None


def test_list_sessions_orders_by_updated_at_desc(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)
    first = repo.save_session(
        story_id="story-a", title="first", messages=[_turn("user", "1")]
    )
    second = repo.save_session(
        story_id="story-a", title="second", messages=[_turn("user", "2")]
    )
    assert [row.title for row in repo.list_sessions("story-a")] == [
        "second",
        "first",
    ]

    # Touching the first session bumps it back to the top (resume ordering).
    repo.save_session(
        assistant_session_id=first.assistant_session_id,
        story_id="story-a",
        messages=[_turn("user", "1"), _turn("assistant", "resumed")],
    )
    assert [row.title for row in repo.list_sessions("story-a")] == [
        "first",
        "second",
    ]
    assert second.assistant_session_id in {
        row.assistant_session_id for row in repo.list_sessions("story-a")
    }


def test_story_scoping_isolates_sessions(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)
    repo.save_session(story_id="story-a", title="a", messages=[])
    repo.save_session(story_id="story-b", title="b", messages=[])

    assert [row.story_id for row in repo.list_sessions("story-a")] == ["story-a"]
    assert [row.story_id for row in repo.list_sessions("story-b")] == ["story-b"]
    assert repo.list_sessions("story-unknown") == []


def test_save_session_rejects_cross_story_reuse(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)
    saved = repo.save_session(story_id="story-a", title="a", messages=[])

    with pytest.raises(AssistantSessionRepositoryError) as exc:
        repo.save_session(
            assistant_session_id=saved.assistant_session_id,
            story_id="story-b",
            messages=[],
        )
    assert exc.value.code == "assistant_session_story_mismatch"


def test_delete_session_removes_only_the_conversation(retrieval_session):
    repo = AssistantSessionRepository(retrieval_session)
    saved = repo.save_session(story_id="story-a", title="a", messages=[])
    keep = repo.save_session(story_id="story-a", title="keep", messages=[])

    assert repo.delete_session(saved.assistant_session_id) is True
    assert repo.load_session(saved.assistant_session_id) is None
    assert repo.delete_session(saved.assistant_session_id) is False
    assert [row.assistant_session_id for row in repo.list_sessions("story-a")] == [
        keep.assistant_session_id
    ]


def _turn(role: str, text: str) -> dict[str, str]:
    return {"role": role, "text": text, "created_at": "2026-07-02T00:00:00+00:00"}
