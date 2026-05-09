"""Active-story longform MVP runtime endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from config import get_settings
from rp.graphs.story_graph_runner import StoryGraphRunner
from rp.models.archival_evolution import ArchivalEvolutionRequest
from rp.models.block_view import BlockSource
from rp.models.core_mutation import DirectCoreEditRequest
from rp.models.dsl import Domain, Layer
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import MemoryBlockProposalSubmitRequest
from rp.models.memory_inspection import RecallReviewCommand
from rp.models.runtime_config_contracts import RuntimeConfigPatchRequest
from rp.models.story_runtime import ChapterWorkspaceSnapshot
from rp.models.story_runtime import LongformTurnRequest
from rp.services.runtime_config_control_service import (
    RuntimeConfigControlServiceError,
)
from rp.services.story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    MemoryBlockProposalNotFoundError,
    MemoryBlockTargetMismatchError,
)
from rp.services.story_runtime_controller import (
    MemoryBlockHistoryUnsupportedError,
    StoryRuntimeController,
)
from rp.services.story_runtime_debug_query_service import (
    StoryRuntimeDebugQueryServiceError,
)
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from services.database import get_session

router = APIRouter()


class RevisionDraftUpdateRequest(BaseModel):
    content_text: str = Field(min_length=1)


class RevisionCommentCreateRequest(BaseModel):
    block_id: str = Field(min_length=1)
    instruction_text: str = Field(min_length=1)
    selected_excerpt: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    superdoc_anchor_id: str | None = None


class RevisionTrackedChangeCreateRequest(BaseModel):
    block_id: str = Field(min_length=1)
    original_text: str | None = None
    suggested_text: str | None = None


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


def _memory_inspection_invalid(exc: Exception, *, code: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": str(exc),
                "code": code,
            }
        },
    )


def _story_runtime_read_invalid(
    exc: Exception,
    *,
    code: str,
) -> HTTPException:
    error_code = getattr(exc, "code", None) or code
    status_code = (
        404
        if error_code == "story_runtime_debug_session_not_found"
        else 400
    )
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": str(exc),
                "code": error_code,
            }
        },
    )


def _runtime_config_invalid(exc: Exception) -> HTTPException:
    error_code = getattr(exc, "code", None) or "runtime_config_invalid"
    status_code = 409 if error_code == "runtime_config_snapshot_conflict" else 400
    if error_code == "story_session_not_found":
        status_code = 404
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": str(exc),
                "code": error_code,
            }
        },
    )


def _revision_review_invalid(exc: Exception) -> HTTPException:
    message = str(exc)
    code = message.split(":", 1)[0] if ":" in message else message
    status_code = (
        404
        if message.startswith("StorySession not found:")
        or message.startswith("StoryArtifact not found:")
        else 400
    )
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": message,
                "code": code or "revision_review_surface_invalid",
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
    payload: RuntimeConfigPatchRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        request = payload.model_copy(update={"session_id": session_id})
        snapshot, receipt = controller.publish_runtime_config_patch(
            request,
        )
    except RuntimeConfigControlServiceError as exc:
        raise _runtime_config_invalid(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    response = _snapshot_payload(snapshot)
    response["runtime_config_receipt"] = receipt.model_dump(mode="json")
    return response


@router.get("/api/rp/story-sessions/{session_id}/runtime-config/history")
async def list_story_runtime_config_history(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        history = controller.list_runtime_config_control_history(
            session_id=session_id
        )
    except RuntimeConfigControlServiceError as exc:
        raise _runtime_config_invalid(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc
    return {
        "object": "list",
        "session_id": session_id,
        "data": [item.model_dump(mode="json") for item in history],
    }


@router.get("/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}")
async def get_revision_review_surface(
    session_id: str,
    artifact_id: str,
    mode: str = Query(default="viewing"),
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.read_revision_review_surface(
            session_id=session_id,
            artifact_id=artifact_id,
            mode=mode,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc


@router.patch(
    "/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}/draft"
)
async def update_revision_review_draft(
    session_id: str,
    artifact_id: str,
    payload: RevisionDraftUpdateRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot = controller.update_revision_draft_artifact(
            session_id=session_id,
            artifact_id=artifact_id,
            content_text=payload.content_text,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc
    return _snapshot_payload(snapshot)


@router.post(
    "/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}/comments"
)
async def create_revision_review_comment(
    session_id: str,
    artifact_id: str,
    payload: RevisionCommentCreateRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.add_revision_comment(
            session_id=session_id,
            artifact_id=artifact_id,
            block_id=payload.block_id,
            instruction_text=payload.instruction_text,
            selected_excerpt=payload.selected_excerpt,
            start_offset=payload.start_offset,
            end_offset=payload.end_offset,
            superdoc_anchor_id=payload.superdoc_anchor_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc


@router.post(
    "/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}/tracked-changes"
)
async def create_revision_review_tracked_change(
    session_id: str,
    artifact_id: str,
    payload: RevisionTrackedChangeCreateRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.add_revision_tracked_change(
            session_id=session_id,
            artifact_id=artifact_id,
            block_id=payload.block_id,
            original_text=payload.original_text,
            suggested_text=payload.suggested_text,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc


@router.post(
    "/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}/comments/{comment_id}/resolve"
)
async def resolve_revision_review_comment(
    session_id: str,
    artifact_id: str,
    comment_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.resolve_revision_comment(
            session_id=session_id,
            artifact_id=artifact_id,
            comment_id=comment_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc


@router.delete(
    "/api/rp/story-sessions/{session_id}/revision-review/{artifact_id}/comments/{comment_id}"
)
async def delete_revision_review_comment(
    session_id: str,
    artifact_id: str,
    comment_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.delete_revision_comment(
            session_id=session_id,
            artifact_id=artifact_id,
            comment_id=comment_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise _revision_review_invalid(exc) from exc


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


@router.get("/api/rp/story-sessions/{session_id}/runtime/inspect")
async def get_story_runtime_inspection(
    session_id: str,
    branch_head_id: str | None = None,
    turn_id: str | None = None,
    target_chapter_index: int | None = Query(default=None, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.read_runtime_inspection(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            target_chapter_index=target_chapter_index,
            limit=limit,
        )
    except StoryRuntimeDebugQueryServiceError as exc:
        raise _story_runtime_read_invalid(
            exc,
            code="story_runtime_inspection_invalid",
        ) from exc
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
        raise _story_runtime_read_invalid(
            exc,
            code="story_runtime_inspection_invalid",
        ) from exc


@router.get("/api/rp/story-sessions/{session_id}/memory/archival/evolution/history")
async def get_story_archival_evolution_history(
    session_id: str,
    branch_head_id: str | None = None,
    turn_id: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.read_story_evolution_history(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            limit=limit,
        )
    except StoryRuntimeDebugQueryServiceError as exc:
        raise _story_runtime_read_invalid(
            exc,
            code="story_evolution_history_invalid",
        ) from exc
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
        raise _story_runtime_read_invalid(
            exc,
            code="story_evolution_history_invalid",
        ) from exc


@router.get("/api/rp/story-sessions/{session_id}/runtime/migration")
async def get_story_runtime_migration_summary(
    session_id: str,
    branch_head_id: str | None = None,
    turn_id: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.read_runtime_migration_summary(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            limit=limit,
        )
    except StoryRuntimeDebugQueryServiceError as exc:
        raise _story_runtime_read_invalid(
            exc,
            code="story_runtime_migration_invalid",
        ) from exc
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
        raise _story_runtime_read_invalid(
            exc,
            code="story_runtime_migration_invalid",
        ) from exc


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


@router.get("/api/rp/story-sessions/{session_id}/memory/overview")
async def get_story_memory_overview(
    session_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        return controller.read_memory_overview(session_id=session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": str(exc), "code": "story_session_not_found"}},
        ) from exc


@router.get("/api/rp/story-sessions/{session_id}/memory/inspection")
async def get_story_memory_inspection(
    session_id: str,
    branch_head_id: str,
    turn_id: str,
    runtime_profile_snapshot_id: str,
    layers: list[Layer] | None = Query(default=None),
    domains: list[Domain] | None = Query(default=None),
    include_hidden_audit: bool = False,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        session = controller.read_session(session_id=session_id).session
        identity = MemoryRuntimeIdentity(
            story_id=session.story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=runtime_profile_snapshot_id,
        )
        return controller.inspect_visible_memory(
            session_id=session_id,
            identity=identity,
            layers=None if layers is None else [item.value for item in layers],
            domains=None if domains is None else [item.value for item in domains],
            include_hidden_audit=include_hidden_audit,
        )
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
        raise _memory_inspection_invalid(
            exc,
            code="memory_inspection_invalid",
        ) from exc


@router.post("/api/rp/story-sessions/{session_id}/memory/core/direct-edit")
async def direct_edit_story_core_memory(
    session_id: str,
    payload: DirectCoreEditRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = await controller.direct_edit_core_memory(
            session_id=session_id,
            payload=payload,
        )
        return {"session_id": session_id, "item": item}
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
        raise _memory_inspection_invalid(
            exc,
            code="memory_core_direct_edit_invalid",
        ) from exc


@router.post("/api/rp/story-sessions/{session_id}/memory/recall/actions")
async def review_story_recall_memory(
    session_id: str,
    payload: RecallReviewCommand,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.review_recall_memory(
            session_id=session_id,
            command=payload,
        )
        return {"session_id": session_id, "item": item}
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
        raise _memory_inspection_invalid(
            exc,
            code="memory_recall_action_invalid",
        ) from exc


@router.post("/api/rp/story-sessions/{session_id}/memory/archival/evolution")
async def evolve_story_archival_memory(
    session_id: str,
    payload: ArchivalEvolutionRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        item = controller.evolve_archival_memory(
            session_id=session_id,
            request=payload,
        )
        return {"session_id": session_id, "item": item}
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
        raise _memory_inspection_invalid(
            exc,
            code="memory_archival_evolution_invalid",
        ) from exc


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
