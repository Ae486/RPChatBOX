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
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.story_brainstorm import (
    BrainstormApplyRequest,
    BrainstormItemUpdateRequest,
    BrainstormSessionStartRequest,
    BrainstormSummarizeRequest,
)
from rp.models.story_runtime import ChapterWorkspaceSnapshot
from rp.models.story_runtime import LongformTurnRequest
from rp.services.runtime_config_control_service import (
    RuntimeConfigControlServiceError,
)
from rp.services.story_runtime_identity_service import (
    StoryRuntimeIdentityServiceError,
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
from rp.services.story_brainstorm_service import StoryBrainstormServiceError
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


class StoryBranchCreateRequest(BaseModel):
    origin_turn_id: str = Field(min_length=1)
    branch_name: str | None = None


class StoryRollbackRequest(BaseModel):
    target_turn_id: str = Field(min_length=1)


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


def _brainstorm_invalid(exc: Exception) -> HTTPException:
    error_code = getattr(exc, "code", None) or "story_brainstorm_invalid"
    status_code = 404 if error_code in {
        "story_session_not_found",
        "brainstorm_session_not_found",
        "brainstorm_item_not_found",
    } else 400
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": str(exc),
                "code": error_code,
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


def _story_stream_error_sse(*, message: str, code: str) -> str:
    return (
        "data: "
        + json.dumps(
            {
                "type": "error",
                "error": {
                    "message": message,
                    "type": code,
                    "code": code,
                },
            },
            ensure_ascii=False,
        )
        + "\n\n"
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


def _branch_control_payload(*, snapshot: ChapterWorkspaceSnapshot, receipt: dict) -> dict:
    return {
        "data": {
            "chapter_snapshot": _snapshot_payload(snapshot),
        },
        "receipt": receipt,
    }


def _story_branch_control_invalid(exc: Exception) -> HTTPException:
    message = str(exc)
    error_code = getattr(exc, "code", None) or "story_branch_control_invalid"
    status_code = 400
    if "story_session_not_found:" in message:
        error_code = "story_session_not_found"
        status_code = 404
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": message,
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


@router.post("/api/rp/story-sessions/{session_id}/branches")
async def create_story_branch(
    session_id: str,
    payload: StoryBranchCreateRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot, receipt = controller.create_branch_from_turn(
            session_id=session_id,
            origin_turn_id=payload.origin_turn_id,
            branch_name=payload.branch_name,
            actor="story_runtime_ui",
            metadata={
                "source": "story_runtime_product_route",
                "surface": "segment_action_menu",
            },
        )
    except StoryRuntimeIdentityServiceError as exc:
        raise _story_branch_control_invalid(exc) from exc
    return _branch_control_payload(
        snapshot=snapshot,
        receipt=receipt.model_dump(mode="json"),
    )


@router.post("/api/rp/story-sessions/{session_id}/branches/{branch_head_id}/switch")
async def switch_story_branch(
    session_id: str,
    branch_head_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot, receipt = controller.switch_branch(
            session_id=session_id,
            branch_head_id=branch_head_id,
            actor="story_runtime_ui",
            metadata={
                "source": "story_runtime_product_route",
                "surface": "branch_panel",
            },
        )
    except StoryRuntimeIdentityServiceError as exc:
        raise _story_branch_control_invalid(exc) from exc
    return _branch_control_payload(
        snapshot=snapshot,
        receipt=receipt.model_dump(mode="json"),
    )


@router.delete("/api/rp/story-sessions/{session_id}/branches/{branch_head_id}")
async def delete_story_branch(
    session_id: str,
    branch_head_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot, receipt = controller.delete_branch(
            session_id=session_id,
            branch_head_id=branch_head_id,
            actor="story_runtime_ui",
            metadata={
                "source": "story_runtime_product_route",
                "surface": "branch_panel",
            },
        )
    except StoryRuntimeIdentityServiceError as exc:
        raise _story_branch_control_invalid(exc) from exc
    return _branch_control_payload(
        snapshot=snapshot,
        receipt=receipt.model_dump(mode="json"),
    )


@router.post("/api/rp/story-sessions/{session_id}/rollback")
async def rollback_story_branch(
    session_id: str,
    payload: StoryRollbackRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        snapshot, receipt = controller.rollback_to_turn(
            session_id=session_id,
            target_turn_id=payload.target_turn_id,
            actor="story_runtime_ui",
            metadata={
                "source": "story_runtime_product_route",
                "surface": "segment_action_menu",
            },
        )
    except StoryRuntimeIdentityServiceError as exc:
        raise _story_branch_control_invalid(exc) from exc
    return _branch_control_payload(
        snapshot=snapshot,
        receipt=receipt.model_dump(mode="json"),
    )


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


@router.post("/api/rp/story-sessions/{session_id}/brainstorm/sessions")
async def start_story_brainstorm_session(
    session_id: str,
    payload: BrainstormSessionStartRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        session = controller.start_brainstorm_session(
            session_id=session_id,
            request=payload,
        )
        return _brainstorm_session_response(session_id=session_id, session=session)
    except (StoryBrainstormServiceError, RuntimeError, ValueError) as exc:
        raise _brainstorm_invalid(exc) from exc


@router.get(
    "/api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}"
)
async def get_story_brainstorm_session(
    session_id: str,
    brainstorm_id: str,
    story_id: str,
    branch_head_id: str,
    turn_id: str,
    runtime_profile_snapshot_id: str,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    identity = MemoryRuntimeIdentity(
        story_id=story_id,
        session_id=session_id,
        branch_head_id=branch_head_id,
        turn_id=turn_id,
        runtime_profile_snapshot_id=runtime_profile_snapshot_id,
    )
    try:
        session = controller.read_brainstorm_session(
            session_id=session_id,
            identity=identity,
            brainstorm_id=brainstorm_id,
        )
        return _brainstorm_session_response(session_id=session_id, session=session)
    except (StoryBrainstormServiceError, RuntimeError, ValueError) as exc:
        raise _brainstorm_invalid(exc) from exc


@router.post(
    "/api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/summarize"
)
async def summarize_story_brainstorm_session(
    session_id: str,
    brainstorm_id: str,
    payload: BrainstormSummarizeRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        session = await controller.summarize_brainstorm_session(
            session_id=session_id,
            brainstorm_id=brainstorm_id,
            request=payload,
        )
        return _brainstorm_session_response(session_id=session_id, session=session)
    except (StoryBrainstormServiceError, RuntimeError, ValueError) as exc:
        raise _brainstorm_invalid(exc) from exc


@router.patch(
    "/api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/items/{item_id}"
)
async def update_story_brainstorm_item(
    session_id: str,
    brainstorm_id: str,
    item_id: str,
    payload: BrainstormItemUpdateRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        session = controller.update_brainstorm_item(
            session_id=session_id,
            brainstorm_id=brainstorm_id,
            item_id=item_id,
            request=payload,
        )
        return _brainstorm_session_response(session_id=session_id, session=session)
    except (StoryBrainstormServiceError, RuntimeError, ValueError) as exc:
        raise _brainstorm_invalid(exc) from exc


@router.post(
    "/api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/apply"
)
async def apply_story_brainstorm_session(
    session_id: str,
    brainstorm_id: str,
    payload: BrainstormApplyRequest,
    controller: StoryRuntimeController = Depends(_story_controller),
):
    try:
        receipt = await controller.apply_brainstorm_session(
            session_id=session_id,
            brainstorm_id=brainstorm_id,
            request=payload,
        )
        return {
            "session_id": session_id,
            "receipt": receipt.model_dump(mode="json"),
            "action_metadata": {
                "schema_version": "rp.brainstorm.apply_receipt.v1",
                "action": "brainstorm_summary_apply",
                "origin_kind": "brainstorm_summary_apply",
                "identity": payload.identity.model_dump(mode="json"),
                "brainstorm_id": brainstorm_id,
                "source_item_ids": [
                    item.source_item_id for item in receipt.dispatch_receipts
                ],
                "affected_refs": _unique_memory_action_refs(
                    [
                        str(item.target_ref or "")
                        for item in receipt.dispatch_receipts
                    ]
                    + [
                        str(item.proposal_id or "")
                        for item in receipt.dispatch_receipts
                    ]
                ),
            },
            "refresh": receipt.refresh,
        }
    except (StoryBrainstormServiceError, RuntimeError, ValueError) as exc:
        raise _brainstorm_invalid(exc) from exc


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
        return _memory_action_response(
            session_id=session_id,
            item=item,
            identity=payload.identity,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            action="direct_core_edit",
            governed_by="StoryBlockMutationService.direct_edit_block",
            affected_refs=[
                f"core:{payload.domain.value}:{payload.domain_path or payload.domain.value}",
                str(item.get("proposal_id") or ""),
            ],
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
        return _memory_action_response(
            session_id=session_id,
            item=item,
            identity=payload.identity,
            layer=Layer.RECALL.value,
            action=f"review_recall:{payload.action.value}",
            governed_by="RecallLifecycleService",
            affected_refs=[
                *payload.material_refs,
                *list(item.get("touched_material_refs") or []),
                str(item.get("event_id") or ""),
            ],
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
        return _memory_action_response(
            session_id=session_id,
            item=item,
            identity=payload.identity,
            layer=Layer.ARCHIVAL.value,
            action="evolve_archival",
            governed_by="ArchivalEvolutionService.evolve_source",
            affected_refs=[
                str(item.get("source_asset_id") or ""),
                str(item.get("superseded_source_asset_id") or ""),
                str(item.get("root_source_asset_id") or ""),
                *list(item.get("replacement_chunk_ids") or []),
                *list(item.get("reindex_job_ids") or []),
                *list(item.get("event_ids") or []),
            ],
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
            code="memory_archival_evolution_invalid",
        ) from exc


def _memory_action_response(
    *,
    session_id: str,
    item: dict,
    identity: MemoryRuntimeIdentity,
    layer: str,
    action: str,
    governed_by: str,
    affected_refs: list[str],
) -> dict[str, object]:
    """Attach stable refresh entrypoints to governed memory action receipts."""

    return {
        "session_id": session_id,
        "item": item,
        "action_metadata": {
            "schema_version": "rp.memory.action_receipt.v1",
            "action": action,
            "layer": layer,
            "governed_by": governed_by,
            "identity": identity.model_dump(mode="json"),
            "affected_refs": _unique_memory_action_refs(affected_refs),
        },
        "refresh": {
            "memory_inspection": {
                "method": "GET",
                "path_template": (
                    "/api/rp/story-sessions/{session_id}/memory/inspection"
                ),
                "query_params": {
                    "branch_head_id": identity.branch_head_id,
                    "turn_id": identity.turn_id,
                    "runtime_profile_snapshot_id": (
                        identity.runtime_profile_snapshot_id
                    ),
                },
            },
            "runtime_inspect": {
                "method": "GET",
                "path_template": (
                    "/api/rp/story-sessions/{session_id}/runtime/inspect"
                ),
                "query_params": {
                    "branch_head_id": identity.branch_head_id,
                    "turn_id": identity.turn_id,
                },
            },
        },
    }


def _brainstorm_session_response(*, session_id: str, session) -> dict[str, object]:
    return {
        "session_id": session_id,
        "item": session.model_dump(mode="json"),
        "runtime_workspace_semantics": {
            "material_kind": RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION.value,
            "temporary": True,
            "source_of_truth": False,
            "core_state_truth": False,
            "recall_truth": False,
            "archival_truth": False,
        },
        "allowed_actions": [
            "summarize",
            "edit_item",
            "reject_item",
            "confirm_item",
            "apply_confirmed",
        ],
    }


def _unique_memory_action_refs(values: list[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = str(value or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


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
            yield _story_stream_error_sse(
                message=str(exc),
                code=getattr(exc, "code", None) or "story_turn_failed",
            )
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        except Exception as exc:
            yield _story_stream_error_sse(
                message=str(exc),
                code=getattr(exc, "code", None) or "story_turn_failed",
            )
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
