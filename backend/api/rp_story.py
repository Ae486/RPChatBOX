"""Active-story longform MVP runtime endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from config import get_settings
from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.models.block_view import BlockSource
from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import MemoryBlockProposalSubmitRequest
from rp.models.story_runtime import ChapterWorkspaceSnapshot
from rp.models.story_runtime import LongformTurnRequest, StoryRuntimeConfigPatchRequest
from rp.services.story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    MemoryBlockProposalNotFoundError,
    MemoryBlockTargetMismatchError,
)
from rp.services.story_runtime_controller import (
    MemoryBlockHistoryUnsupportedError,
    StoryRuntimeController,
)
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from services.database import get_session

router = APIRouter()


def _story_controller(
    session: Session = Depends(get_session),
) -> StoryRuntimeController:
    return RpRuntimeFactory(session).build_story_runtime_controller()


def _story_graph_runner(session: Session = Depends(get_session)) -> StoryGraphRunner:
    return RpRuntimeFactory(session).build_story_graph_runner()


def _memory_backend_metadata() -> dict[str, object]:
    settings = get_settings()
    store_write_enabled = bool(settings.rp_memory_core_state_store_write_enabled)
    store_read_enabled = bool(settings.rp_memory_core_state_store_read_enabled)
    write_switch_enabled = bool(
        store_write_enabled and settings.rp_memory_core_state_store_write_switch_enabled
    )
    truth_source = (
        "core_state_store" if write_switch_enabled else "compatibility_mirror"
    )
    return {
        "phase": "phase_g4c_cleanup_prep",
        "authoritative_truth_source": truth_source,
        "projection_truth_source": truth_source,
        "read_surface": "core_state_store"
        if store_read_enabled
        else "compatibility_mirror",
        "legacy_fields": {
            "session.current_state_json": "compatibility_mirror",
            "chapter.builder_snapshot_json": "compatibility_mirror",
        },
        "mirror_sync_enabled": True,
        "hard_cleanup_enabled": False,
        "flags": {
            "core_state_store_write_enabled": store_write_enabled,
            "core_state_store_read_enabled": store_read_enabled,
            "core_state_store_write_switch_enabled": write_switch_enabled,
        },
    }


def _snapshot_payload(snapshot: ChapterWorkspaceSnapshot) -> dict:
    payload = snapshot.model_dump(mode="json")
    payload["memory_backend"] = _memory_backend_metadata()
    return payload


def _memory_block_not_found(block_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Memory block not found: {block_id}",
                "code": "memory_block_not_found",
            }
        },
    )


def _memory_block_history_unsupported(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_block_history_unsupported",
            }
        },
    )


def _memory_block_mutation_unsupported(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_block_mutation_unsupported",
            }
        },
    )


def _memory_block_target_mismatch(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_block_target_mismatch",
            }
        },
    )


def _memory_block_proposal_invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_block_proposal_invalid",
            }
        },
    )


def _memory_block_proposal_not_found(proposal_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Memory block proposal not found: {proposal_id}",
                "code": "memory_block_proposal_not_found",
            }
        },
    )


def _memory_block_proposal_apply_failed(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": "memory_block_proposal_apply_failed",
            }
        },
    )


def _memory_block_consumer_not_found(consumer_key: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Memory block consumer not found: {consumer_key}",
                "code": "memory_block_consumer_not_found",
            }
        },
    )


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
    return _snapshot_payload(snapshot)


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
    return _snapshot_payload(snapshot)


@router.patch("/api/rp/story-sessions/{session_id}/runtime-config")
async def patch_story_runtime_config(
    session_id: str,
    payload: StoryRuntimeConfigPatchRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot = controller.update_runtime_story_config(
            session_id=session_id,
            patch=payload.runtime_story_config,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return _snapshot_payload(snapshot)


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


@router.get("/api/rp/story-sessions/{session_id}/memory/authoritative")
async def get_story_memory_authoritative(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_authoritative(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, "items": items}


@router.get("/api/rp/story-sessions/{session_id}/memory/projection")
async def get_story_memory_projection(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_projection(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, "items": items}


@router.get("/api/rp/story-sessions/{session_id}/memory/blocks")
async def get_story_memory_blocks(
    session_id: str,
    layer: Layer | None = None,
    source: BlockSource | None = None,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_blocks(
            session_id=session_id,
            layer=layer,
            source=source,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, "items": items}


@router.get("/api/rp/story-sessions/{session_id}/memory/block-consumers")
async def get_story_memory_block_consumers(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_block_consumers(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, "items": items}


@router.get("/api/rp/story-sessions/{session_id}/memory/block-consumers/{consumer_key}")
async def get_story_memory_block_consumer(
    session_id: str,
    consumer_key: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.get_memory_block_consumer(
            session_id=session_id,
            consumer_key=consumer_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    if item is None:
        raise _memory_block_consumer_not_found(consumer_key)
    return {"session_id": session_id, "item": item}


@router.get("/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}")
async def get_story_memory_block(
    session_id: str,
    block_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.get_memory_block(session_id=session_id, block_id=block_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    if item is None:
        raise _memory_block_not_found(block_id)
    return {"session_id": session_id, "item": item}


@router.get("/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/versions")
async def get_story_memory_block_versions(
    session_id: str,
    block_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        result = await controller.read_memory_block_versions(
            session_id=session_id,
            block_id=block_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    except MemoryBlockHistoryUnsupportedError as exc:
        raise _memory_block_history_unsupported(exc) from exc
    if result is None:
        raise _memory_block_not_found(block_id)
    return {
        "session_id": session_id,
        "block_id": block_id,
        **result.model_dump(mode="json"),
    }


@router.get("/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/provenance")
async def get_story_memory_block_provenance(
    session_id: str,
    block_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        result = await controller.read_memory_block_provenance(
            session_id=session_id,
            block_id=block_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    except MemoryBlockHistoryUnsupportedError as exc:
        raise _memory_block_history_unsupported(exc) from exc
    if result is None:
        raise _memory_block_not_found(block_id)
    return {
        "session_id": session_id,
        "block_id": block_id,
        **result.model_dump(mode="json"),
    }


@router.get("/api/rp/story-sessions/{session_id}/memory/proposals")
async def get_story_memory_proposals(
    session_id: str,
    status: str | None = None,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_proposals(session_id=session_id, status=status)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, "items": items}


@router.get("/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals")
async def get_story_memory_block_proposals(
    session_id: str,
    block_id: str,
    status: str | None = None,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        items = controller.list_memory_block_proposals(
            session_id=session_id,
            block_id=block_id,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    if items is None:
        raise _memory_block_not_found(block_id)
    return {"session_id": session_id, "block_id": block_id, "items": items}


@router.get(
    "/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals/{proposal_id}"
)
async def get_story_memory_block_proposal(
    session_id: str,
    block_id: str,
    proposal_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.get_memory_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )
    except MemoryBlockMutationUnsupportedError as exc:
        raise _memory_block_mutation_unsupported(exc) from exc
    except MemoryBlockProposalNotFoundError as exc:
        raise _memory_block_proposal_not_found(proposal_id) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    if item is None:
        raise _memory_block_not_found(block_id)
    return {
        "session_id": session_id,
        "block_id": block_id,
        "proposal_id": proposal_id,
        "item": item,
    }


@router.post("/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals")
async def create_story_memory_block_proposal(
    session_id: str,
    block_id: str,
    payload: MemoryBlockProposalSubmitRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = await controller.submit_memory_block_proposal(
            session_id=session_id,
            block_id=block_id,
            payload=payload,
        )
    except MemoryBlockMutationUnsupportedError as exc:
        raise _memory_block_mutation_unsupported(exc) from exc
    except MemoryBlockTargetMismatchError as exc:
        raise _memory_block_target_mismatch(exc) from exc
    except ValueError as exc:
        if str(exc).startswith("StorySession not found:"):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "message": str(exc),
                        "code": "story_session_not_found",
                    }
                },
            ) from exc
        raise _memory_block_proposal_invalid(exc) from exc
    if item is None:
        raise _memory_block_not_found(block_id)
    return {"session_id": session_id, "block_id": block_id, "item": item}


@router.post(
    "/api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals/{proposal_id}/apply"
)
async def apply_story_memory_block_proposal(
    session_id: str,
    block_id: str,
    proposal_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.apply_memory_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )
    except MemoryBlockProposalNotFoundError as exc:
        raise _memory_block_proposal_not_found(proposal_id) from exc
    except MemoryBlockMutationUnsupportedError as exc:
        raise _memory_block_mutation_unsupported(exc) from exc
    except ValueError as exc:
        if str(exc).startswith("StorySession not found:"):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "message": str(exc),
                        "code": "story_session_not_found",
                    }
                },
            ) from exc
        raise _memory_block_proposal_apply_failed(exc) from exc
    if item is None:
        raise _memory_block_not_found(block_id)
    return {
        "session_id": session_id,
        "block_id": block_id,
        "proposal_id": proposal_id,
        "item": item,
    }


@router.get("/api/rp/story-sessions/{session_id}/memory/versions")
async def get_story_memory_versions(
    session_id: str,
    object_id: str,
    domain: Domain,
    domain_path: str | None = None,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        result = controller.read_memory_versions(
            session_id=session_id,
            object_id=object_id,
            domain=domain,
            domain_path=domain_path,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, **result.model_dump(mode="json")}


@router.get("/api/rp/story-sessions/{session_id}/memory/provenance")
async def get_story_memory_provenance(
    session_id: str,
    object_id: str,
    domain: Domain,
    domain_path: str | None = None,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        result = controller.read_memory_provenance(
            session_id=session_id,
            object_id=object_id,
            domain=domain,
            domain_path=domain_path,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {"session_id": session_id, **result.model_dump(mode="json")}


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
