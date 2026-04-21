"""Active-story longform MVP runtime endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.models.story_runtime import LongformTurnRequest
from rp.services.story_runtime_controller import StoryRuntimeController
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from services.database import get_session

router = APIRouter()


def _story_controller(session: Session = Depends(get_session)) -> StoryRuntimeController:
    return RpRuntimeFactory(session).build_story_runtime_controller()


def _story_graph_runner(session: Session = Depends(get_session)) -> StoryGraphRunner:
    return RpRuntimeFactory(session).build_story_graph_runner()


@router.get("/api/rp/story-sessions")
async def list_story_sessions(
    controller: StoryRuntimeController = Depends(_story_controller),
):
    return {
        "object": "list",
        "data": [item.model_dump(mode="json") for item in controller.list_sessions()],
    }


@router.get("/api/rp/story-sessions/{session_id}")
async def get_story_session(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot = controller.read_session(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return snapshot.model_dump(mode="json")


@router.get("/api/rp/story-sessions/{session_id}/chapters/{chapter_index}")
async def get_story_chapter(
    session_id: str,
    chapter_index: int,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot = controller.read_chapter(
            session_id=session_id,
            chapter_index=chapter_index,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_chapter_not_found"}},
        ) from exc
    return snapshot.model_dump(mode="json")


@router.get("/api/rp/story-sessions/{session_id}/runtime/debug")
async def get_story_runtime_debug(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
    runner: StoryGraphRunner = Depends(_story_graph_runner),
):
    try:
        controller.read_session(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return runner.get_runtime_debug(session_id=session_id)


@router.post("/api/rp/story-sessions/{session_id}/turn")
async def run_story_turn(
    session_id: str,
    payload: LongformTurnRequest,
    runner: StoryGraphRunner = Depends(_story_graph_runner),
):
    if payload.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "session_id in body must match the route",
                    "code": "story_session_mismatch",
                }
            },
        )
    try:
        result = await runner.run_turn(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": str(exc), "code": "story_turn_failed"}},
        ) from exc
    return result.model_dump(mode="json", exclude_none=True)


@router.post("/api/rp/story-sessions/{session_id}/turn/stream")
async def run_story_turn_stream(
    session_id: str,
    payload: LongformTurnRequest,
    runner: StoryGraphRunner = Depends(_story_graph_runner),
):
    if payload.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "session_id in body must match the route",
                    "code": "story_session_mismatch",
                }
            },
        )

    async def _stream():
        try:
            async for chunk in runner.run_turn_stream(payload):
                if chunk:
                    yield chunk
        except ValueError as exc:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {
                            "message": str(exc),
                            "type": "story_turn_failed",
                        },
                    }
                )
                + "\n\n"
            )
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
