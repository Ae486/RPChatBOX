"""Focused Stage W writer brainstorm service tests."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.models.story_brainstorm import (
    BrainstormBatchSubmitRequest,
    BrainstormContinueWritingRequest,
    BrainstormDiscussionRequest,
    BrainstormItemCreateRequest,
    BrainstormItemStatus,
    BrainstormItemUpdateRequest,
    BrainstormSessionStartRequest,
    BrainstormSummarizeRequest,
)
from rp.models.story_runtime import LongformChapterPhase
from rp.models.story_runtime import StoryArtifactKind, StoryArtifactStatus
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story_brainstorm_service import (
    StoryBrainstormService,
    StoryBrainstormServiceError,
)
from rp.services.story_session_service import StorySessionService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService


class _StubStoryLlmGateway:
    def __init__(self, *, discussion_reply: str = "先把想保留的伏笔说清楚。", summary_payload=None):
        self.discussion_reply = discussion_reply
        self.summary_payload = summary_payload or {"items": ["保留钟楼债务伏笔", "强化使者与账册的关联"]}
        self.calls: list[dict[str, object]] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        system_prompt = str(kwargs["messages"][0].content)
        if "brainstorm_summarize" in system_prompt:
            return (
                str(self.summary_payload),
                {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            )
        return (
            self.discussion_reply,
            {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
        )

    @staticmethod
    def extract_json_object(text: str):
        import ast

        return ast.literal_eval(text)


@pytest.mark.asyncio
async def test_discuss_and_summarize_creates_batch_and_flushes_active_window(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session, story_id="brainstorm-stage-w-lifecycle"
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    llm = _StubStoryLlmGateway()
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        llm_gateway=llm,
    )

    started = service.start_session(
        BrainstormSessionStartRequest(
            identity=identity,
            actor="writer",
            metadata={"frontend_entry": "discussion_pane"},
        )
    )
    discussed = await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="我想保留钟楼债务这条暗线，但别太早揭露。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )
    summarized = await service.summarize_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormSummarizeRequest(
            identity=identity,
            actor="writer",
            dry_run_items=["保留钟楼债务伏笔", "强化使者与账册的关联"],
        ),
    )
    materials = RuntimeWorkspaceMaterialService(session=retrieval_session).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
    )

    assert len(discussed.windows) == 1
    assert [message.role for message in discussed.windows[0].messages] == [
        "user",
        "assistant",
    ]
    assert discussed.windows[0].status == "active"
    assert len(summarized.batches) == 1
    assert summarized.batches[0].status == "draft"
    assert [item.text for item in summarized.batches[0].items] == [
        "保留钟楼债务伏笔",
        "强化使者与账册的关联",
    ]
    assert summarized.windows[0].status == "flushed"
    assert summarized.windows[0].flush_reason == "summarize"
    assert [material.lifecycle.value for material in materials] == [
        "invalidated",
        "invalidated",
        "active",
    ]


@pytest.mark.asyncio
async def test_continue_writing_flushes_without_creating_batch_and_new_discussion_uses_new_window(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session, story_id="brainstorm-stage-w-continue"
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    llm = _StubStoryLlmGateway(discussion_reply="先告诉我你希望哪一段先埋线。")
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        llm_gateway=llm,
    )

    started = service.start_session(
        BrainstormSessionStartRequest(identity=identity, actor="writer")
    )
    discussed = await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="先聊埋线位置。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )
    flushed = service.continue_writing(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormContinueWritingRequest(identity=identity, actor="writer"),
    )
    rediscussed = await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="第二轮只聊人物动机。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )

    assert discussed.windows[0].status == "active"
    assert flushed.windows[0].status == "flushed"
    assert flushed.windows[0].flush_reason == "continue_writing"
    assert not flushed.batches
    assert len(rediscussed.windows) == 2
    assert rediscussed.windows[0].status == "flushed"
    assert rediscussed.windows[1].status == "active"
    assert [message.content_text for message in rediscussed.windows[1].messages] == [
        "第二轮只聊人物动机。",
        "先告诉我你希望哪一段先埋线。",
    ]


@pytest.mark.asyncio
async def test_user_added_deleted_restored_and_submit_filters_deleted_items(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session, story_id="brainstorm-stage-w-submit"
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)

    started = service.start_session(
        BrainstormSessionStartRequest(identity=identity, actor="writer")
    )
    await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="梳理本章要保留的两个伏笔。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )
    summarized = await service.summarize_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormSummarizeRequest(
            identity=identity,
            actor="writer",
            dry_run_items=["保留钟楼债务伏笔"],
        ),
    )
    batch = summarized.batches[0]
    added = service.create_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        request=BrainstormItemCreateRequest(
            identity=identity,
            actor="writer",
            text="补一条使者与旧账册的因果线索",
        ),
    )
    deleted = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="deleted",
        ),
    )
    restored = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="active",
        ),
    )
    edited = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            text="保留钟楼债务伏笔，但延后揭露",
        ),
    )
    deleted_again = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=added.batches[0].items[1].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="deleted",
        ),
    )
    submitted_session, receipt = service.submit_batch(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        request=BrainstormBatchSubmitRequest(identity=identity, actor="writer"),
    )

    final_batch = submitted_session.batches[0]
    assert len(added.batches[0].items) == 2
    assert deleted.batches[0].items[0].status == BrainstormItemStatus.DELETED
    assert edited.batches[0].items[0].text == "保留钟楼债务伏笔，但延后揭露"
    assert restored.batches[0].items[0].status == BrainstormItemStatus.ACTIVE
    assert deleted_again.batches[0].items[1].status == BrainstormItemStatus.DELETED
    assert receipt.status == "pending_processing"
    assert receipt.submitted_item_ids == [final_batch.items[0].item_id]
    assert receipt.deleted_item_ids == [final_batch.items[1].item_id]
    assert final_batch.status == "pending_processing"
    assert final_batch.frozen is True
    assert final_batch.items[0].status == BrainstormItemStatus.PENDING_PROCESSING
    assert final_batch.items[1].status == BrainstormItemStatus.DELETED
    assert retrieval_session.exec(select(RuntimeWorkflowJobRecord)).all() == []


@pytest.mark.asyncio
async def test_empty_batch_submit_is_rejected_and_frozen_batch_cannot_edit(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session, story_id="brainstorm-stage-w-empty"
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)

    started = service.start_session(
        BrainstormSessionStartRequest(identity=identity, actor="writer")
    )
    await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="只留一个可删的意图。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )
    summarized = await service.summarize_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormSummarizeRequest(
            identity=identity,
            actor="writer",
            dry_run_items=["这条之后会删掉"],
        ),
    )
    batch = summarized.batches[0]
    deleted = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="deleted",
        ),
    )
    with pytest.raises(StoryBrainstormServiceError) as empty_exc:
        service.submit_batch(
            brainstorm_id=started.brainstorm_id,
            batch_id=batch.batch_id,
            request=BrainstormBatchSubmitRequest(identity=identity, actor="writer"),
        )

    restored = service.update_item(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="active",
        ),
    )
    submitted_session, _receipt = service.submit_batch(
        brainstorm_id=started.brainstorm_id,
        batch_id=batch.batch_id,
        request=BrainstormBatchSubmitRequest(identity=identity, actor="writer"),
    )
    with pytest.raises(StoryBrainstormServiceError) as frozen_exc:
        service.update_item(
            brainstorm_id=started.brainstorm_id,
            batch_id=batch.batch_id,
            item_id=batch.items[0].item_id,
            request=BrainstormItemUpdateRequest(
                identity=identity,
                actor="writer",
                text="提交后不应允许再编辑",
            ),
        )

    assert deleted.batches[0].items[0].status == BrainstormItemStatus.DELETED
    assert empty_exc.value.code == "brainstorm_batch_submit_empty"
    assert restored.batches[0].items[0].status == BrainstormItemStatus.ACTIVE
    assert submitted_session.batches[0].frozen is True
    assert frozen_exc.value.code == "brainstorm_batch_frozen"


@pytest.mark.asyncio
async def test_summarize_rejects_non_string_structured_output(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session, story_id="brainstorm-stage-w-schema"
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    llm = _StubStoryLlmGateway(summary_payload={"items": [{"target_layer": "core"}]})
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        llm_gateway=llm,
    )

    started = service.start_session(
        BrainstormSessionStartRequest(identity=identity, actor="writer")
    )
    await service.discuss_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormDiscussionRequest(
            identity=identity,
            actor="writer",
            prompt="试图让模型输出非法 routing 字段。",
            model_id="test-model",
            provider_id="test-provider",
        ),
    )

    with pytest.raises(StoryBrainstormServiceError) as exc_info:
        await service.summarize_session(
            brainstorm_id=started.brainstorm_id,
            request=BrainstormSummarizeRequest(
                identity=identity,
                actor="writer",
                model_id="test-model",
                provider_id="test-provider",
            ),
        )

    assert exc_info.value.code == "brainstorm_summarize_invalid_output"


def _build_service(
    retrieval_session,
    *,
    story_service: StorySessionService,
    llm_gateway: _StubStoryLlmGateway | None = None,
) -> StoryBrainstormService:
    return StoryBrainstormService(
        story_session_service=story_service,
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        llm_gateway=llm_gateway or _StubStoryLlmGateway(),
    )


def _runtime_identity(retrieval_session, session_id: str):
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from="test.story_brainstorm",
    )
    return StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind="brainstorm",
        actor="writer",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


def _seed_story_runtime(retrieval_session, *, story_id: str):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id=story_id,
        source_workspace_id=f"workspace-{story_id}",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 1,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Foundation"],
            "blueprint_digest": ["Blueprint"],
            "current_outline_digest": ["Outline"],
            "recent_segment_digest": ["Segment"],
            "current_state_digest": ["State"],
        },
    )
    service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_outline_json={
            "content_text": "Accepted outline: the envoy arrives with an old debt.",
        },
    )
    service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted segment: the envoy reaches the city gate.",
        metadata={},
    )
    service.commit()
    refreshed_session = service.get_session(session.session_id)
    refreshed_chapter = service.get_chapter_workspace(chapter.chapter_workspace_id)
    assert refreshed_session is not None
    assert refreshed_chapter is not None
    return refreshed_session, refreshed_chapter, service
