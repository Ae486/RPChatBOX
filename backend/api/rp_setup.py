"""SetupAgent MVP persistence and controller endpoints."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from rp.models.setup_agent import SetupAgentTurnRequest
from rp.models.setup_drafts import (
    FoundationEntry,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)
from rp.models.setup_workspace import (
    ImportedAssetParseStatus,
    QuestionSeverity,
    SetupStepId,
    StoryMode,
)
from rp.graphs.activation_graph_runner import ActivationGraphRunner
from rp.graphs.setup_graph_runner import SetupGraphRunner
from rp.observability.langfuse_scores import (
    emit_activation_trace_scores,
    emit_setup_trace_scores,
)
from rp.services.setup_runtime_controller import SetupRuntimeController
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from services.database import get_session
from services.langfuse_service import get_langfuse_service

router = APIRouter()


class SetupWorkspaceCreateRequest(BaseModel):
    story_id: str
    mode: StoryMode


class SetupQuestionRaiseRequest(BaseModel):
    step_id: SetupStepId
    text: str
    severity: QuestionSeverity = QuestionSeverity.NON_BLOCKING


class SetupAssetRegisterRequest(BaseModel):
    step_id: SetupStepId
    asset_kind: str
    source_ref: str
    title: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    local_path: str | None = None
    parse_status: ImportedAssetParseStatus = ImportedAssetParseStatus.STAGED
    parsed_payload: dict | None = None
    parse_warnings: list[str] = Field(default_factory=list)
    mapped_targets: list[str] = Field(default_factory=list)


class SetupCommitProposalRequest(BaseModel):
    step_id: SetupStepId
    target_draft_refs: list[str] = Field(default_factory=list)
    reason: str | None = None


class SetupStepContextRequest(BaseModel):
    current_step: SetupStepId
    user_prompt: str
    user_edit_delta_ids: list[str] = Field(default_factory=list)
    token_budget: int | None = None


def _workspace_not_found(workspace_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Setup workspace not found: {workspace_id}",
                "code": "setup_workspace_not_found",
            }
        },
    )


def _controller(session: Session = Depends(get_session)) -> SetupRuntimeController:
    return RpRuntimeFactory(session).build_setup_runtime_controller()


def _setup_graph_runner(session: Session = Depends(get_session)) -> SetupGraphRunner:
    return RpRuntimeFactory(session).build_setup_graph_runner()


def _activation_graph_runner(
    session: Session = Depends(get_session),
) -> ActivationGraphRunner:
    return RpRuntimeFactory(session).build_activation_graph_runner()


@router.get("/api/rp/setup/workspaces")
async def list_setup_workspaces(
    session: Session = Depends(get_session),
):
    service = SetupWorkspaceService(session)
    return {
        "object": "list",
        "data": [
            workspace.model_dump(mode="json")
            for workspace in service.list_workspaces()
        ],
    }


@router.post("/api/rp/setup/workspaces", status_code=201)
async def create_setup_workspace(
    payload: SetupWorkspaceCreateRequest,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        workspace = controller.create_workspace(story_id=payload.story_id, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": str(exc), "code": "setup_workspace_create_failed"}},
        ) from exc
    return workspace.model_dump(mode="json")


@router.get("/api/rp/setup/workspaces/{workspace_id}")
async def get_setup_workspace(
    workspace_id: str,
    controller: SetupRuntimeController = Depends(_controller),
):
    workspace = controller.read_workspace(workspace_id=workspace_id)
    if workspace is None:
        raise _workspace_not_found(workspace_id)
    return workspace.model_dump(mode="json")


@router.get("/api/rp/setup/workspaces/{workspace_id}/runtime/debug")
async def get_setup_runtime_debug(
    workspace_id: str,
    controller: SetupRuntimeController = Depends(_controller),
    runner: SetupGraphRunner = Depends(_setup_graph_runner),
):
    workspace = controller.read_workspace(workspace_id=workspace_id)
    if workspace is None:
        raise _workspace_not_found(workspace_id)
    return runner.get_runtime_debug(workspace_id=workspace_id)


@router.patch("/api/rp/setup/workspaces/{workspace_id}/story-config")
async def patch_story_config(
    workspace_id: str,
    payload: StoryConfigDraft,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.patch_story_config(workspace_id=workspace_id, patch=payload)
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.patch("/api/rp/setup/workspaces/{workspace_id}/writing-contract")
async def patch_writing_contract(
    workspace_id: str,
    payload: WritingContractDraft,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.patch_writing_contract(workspace_id=workspace_id, patch=payload)
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/foundation/entries")
async def patch_foundation_entry(
    workspace_id: str,
    payload: FoundationEntry,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.patch_foundation_entry(workspace_id=workspace_id, entry=payload)
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.patch("/api/rp/setup/workspaces/{workspace_id}/longform-blueprint")
async def patch_longform_blueprint(
    workspace_id: str,
    payload: LongformBlueprintDraft,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.patch_longform_blueprint(workspace_id=workspace_id, patch=payload)
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/questions")
async def raise_setup_question(
    workspace_id: str,
    payload: SetupQuestionRaiseRequest,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.raise_question(
            workspace_id=workspace_id,
            step_id=payload.step_id,
            text=payload.text,
            severity=payload.severity,
        )
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/assets")
async def register_setup_asset(
    workspace_id: str,
    payload: SetupAssetRegisterRequest,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.register_asset(
            workspace_id=workspace_id,
            step_id=payload.step_id,
            asset_kind=payload.asset_kind,
            source_ref=payload.source_ref,
            title=payload.title,
            mime_type=payload.mime_type,
            file_size_bytes=payload.file_size_bytes,
            local_path=payload.local_path,
            parse_status=payload.parse_status,
            parsed_payload=payload.parsed_payload,
            parse_warnings=payload.parse_warnings,
            mapped_targets=payload.mapped_targets,
        )
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/commit-proposals")
async def create_setup_commit_proposal(
    workspace_id: str,
    payload: SetupCommitProposalRequest,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.propose_commit(
            workspace_id=workspace_id,
            step_id=payload.step_id,
            target_draft_refs=payload.target_draft_refs,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/commit-proposals/{proposal_id}/accept")
async def accept_setup_commit(
    workspace_id: str,
    proposal_id: str,
    background_tasks: BackgroundTasks,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.accept_commit(
            workspace_id=workspace_id,
            proposal_id=proposal_id,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/commit-proposals/{proposal_id}/reject")
async def reject_setup_commit(
    workspace_id: str,
    proposal_id: str,
    controller: SetupRuntimeController = Depends(_controller),
):
    try:
        result = controller.reject_commit(workspace_id=workspace_id, proposal_id=proposal_id)
    except ValueError as exc:
        raise _workspace_not_found(workspace_id) from exc
    return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/step-context")
async def get_setup_step_context(
    workspace_id: str,
    payload: SetupStepContextRequest,
    controller: SetupRuntimeController = Depends(_controller),
):
    packet = controller.read_step_context(
        workspace_id=workspace_id,
        current_step=payload.current_step,
        user_prompt=payload.user_prompt,
        user_edit_delta_ids=payload.user_edit_delta_ids,
        token_budget=payload.token_budget,
    )
    if packet is None:
        raise _workspace_not_found(workspace_id)
    return packet.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/activation-check")
async def run_setup_activation_check(
    workspace_id: str,
    request: Request,
    controller: SetupRuntimeController = Depends(_controller),
):
    request_id = (request.headers.get("X-Request-Id") if request is not None else None) or uuid.uuid4().hex[:12]
    langfuse = get_langfuse_service()
    metadata = {
        "route": "rp_setup.activation_check",
        "request_id": request_id,
        "workspace_id": workspace_id,
    }
    with langfuse.propagate_attributes(
        session_id=workspace_id,
        tags=["rp", "activation", "api"],
        metadata=metadata,
        trace_name="rp.setup.activation_check",
    ):
        with langfuse.start_as_current_observation(
            name="rp.setup.activation_check",
            as_type="chain",
            input={"workspace_id": workspace_id},
        ) as observation:
            result = controller.run_activation_check(workspace_id=workspace_id)
            if result is None:
                emit_activation_trace_scores(
                    observation,
                    runtime_result={
                        "finish_reason": "activation_failed",
                        "activation_check": {},
                        "activation_result": {},
                        "error": {
                            "message": f"SetupWorkspace not found: {workspace_id}",
                            "type": "setup_workspace_not_found",
                        },
                    },
                    failure_layer="deterministic",
                    error_code="setup_workspace_not_found",
                )
                observation.update(
                    output={
                        "error": {
                            "message": f"SetupWorkspace not found: {workspace_id}",
                            "code": "setup_workspace_not_found",
                        }
                    }
                )
                raise _workspace_not_found(workspace_id)
            payload = result.model_dump(mode="json", exclude_none=True)
            observation.update(output=payload)
            emit_activation_trace_scores(
                observation,
                runtime_result={
                    "finish_reason": "activation_checked",
                    "activation_check": payload,
                    "activation_result": {},
                },
            )
            return payload


@router.post("/api/rp/setup/workspaces/{workspace_id}/activate")
async def activate_story_from_workspace(
    workspace_id: str,
    request: Request,
    runner: ActivationGraphRunner = Depends(_activation_graph_runner),
    controller: SetupRuntimeController = Depends(_controller),
):
    request_id = (request.headers.get("X-Request-Id") if request is not None else None) or uuid.uuid4().hex[:12]
    langfuse = get_langfuse_service()
    metadata = {
        "route": "rp_setup.activate",
        "request_id": request_id,
        "workspace_id": workspace_id,
    }
    with langfuse.propagate_attributes(
        session_id=workspace_id,
        tags=["rp", "activation", "api", "bootstrap"],
        metadata=metadata,
        trace_name="rp.setup.activate",
    ):
        with langfuse.start_as_current_observation(
            name="rp.setup.activate",
            as_type="chain",
            input={"workspace_id": workspace_id},
        ) as observation:
            activation_check = controller.run_activation_check(workspace_id=workspace_id)
            try:
                result = runner.activate_workspace(workspace_id=workspace_id)
            except ValueError as exc:
                runtime_payload = {
                    "finish_reason": "activation_failed",
                    "activation_check": (
                        activation_check.model_dump(mode="json", exclude_none=True)
                        if activation_check is not None
                        else {}
                    ),
                    "activation_result": {},
                    "error": {
                        "message": str(exc),
                        "type": "story_activation_failed",
                    },
                }
                emit_activation_trace_scores(
                    observation,
                    runtime_result=runtime_payload,
                    failure_layer="deterministic",
                    error_code="story_activation_failed",
                )
                observation.update(output=runtime_payload)
                raise HTTPException(
                    status_code=400,
                    detail={"error": {"message": str(exc), "code": "story_activation_failed"}},
                ) from exc
            payload = result.model_dump(mode="json")
            observation.update(
                output={
                    "activation_check": (
                        activation_check.model_dump(mode="json", exclude_none=True)
                        if activation_check is not None
                        else {}
                    ),
                    "activation_result": payload,
                }
            )
            emit_activation_trace_scores(
                observation,
                runtime_result={
                    "finish_reason": "activation_completed",
                    "activation_check": (
                        activation_check.model_dump(mode="json", exclude_none=True)
                        if activation_check is not None
                        else {}
                    ),
                    "activation_result": payload,
                },
            )
            return payload


@router.post("/api/rp/setup/workspaces/{workspace_id}/turn")
async def run_setup_agent_turn(
    workspace_id: str,
    payload: SetupAgentTurnRequest,
    request: Request,
    runner: SetupGraphRunner = Depends(_setup_graph_runner),
):
    if payload.workspace_id != workspace_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "workspace_id in body must match the route",
                    "code": "setup_workspace_mismatch",
                }
            },
        )
    request_id = (request.headers.get("X-Request-Id") if request is not None else None) or uuid.uuid4().hex[:12]
    langfuse = get_langfuse_service()
    metadata = {
        "route": "rp_setup.turn",
        "request_id": request_id,
        "workspace_id": workspace_id,
        "target_step": payload.target_step.value if payload.target_step is not None else None,
        "stream": False,
    }
    with langfuse.propagate_attributes(
        session_id=workspace_id,
        tags=["rp", "setup", "api"],
        metadata=metadata,
        trace_name="rp.setup.turn",
    ):
        with langfuse.start_as_current_observation(
            name="rp.setup.turn",
            as_type="agent",
            input=payload.model_dump(mode="json"),
        ) as observation:
            try:
                result = await runner.run_turn(payload)
            except ValueError as exc:
                emit_setup_trace_scores(
                    observation,
                    runtime_result={
                        "finish_reason": None,
                        "assistant_text": "",
                        "warnings": [],
                        "structured_payload": {},
                    },
                    failure_layer="infra",
                    error_code="setup_agent_turn_failed",
                )
                observation.update(
                    output={
                        "error": {
                            "message": str(exc),
                            "code": "setup_agent_turn_failed",
                        }
                    }
                )
                raise HTTPException(
                    status_code=400,
                    detail={"error": {"message": str(exc), "code": "setup_agent_turn_failed"}},
                ) from exc
            runtime_result = runner.last_runtime_result
            observation.update(
                output=(
                    runtime_result.model_dump(mode="json")
                    if runtime_result is not None
                    else result.model_dump(mode="json")
                )
            )
            if runtime_result is not None:
                emit_setup_trace_scores(
                    observation,
                    runtime_result=runtime_result.model_dump(mode="json"),
                )
            return result.model_dump(mode="json")


@router.post("/api/rp/setup/workspaces/{workspace_id}/turn/stream")
async def run_setup_agent_turn_stream(
    workspace_id: str,
    payload: SetupAgentTurnRequest,
    request: Request,
    runner: SetupGraphRunner = Depends(_setup_graph_runner),
):
    if payload.workspace_id != workspace_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "workspace_id in body must match the route",
                    "code": "setup_workspace_mismatch",
                }
            },
        )

    request_id = (request.headers.get("X-Request-Id") if request is not None else None) or uuid.uuid4().hex[:12]
    langfuse = get_langfuse_service()

    async def _stream():
        metadata = {
            "route": "rp_setup.turn.stream",
            "request_id": request_id,
            "workspace_id": workspace_id,
            "target_step": payload.target_step.value if payload.target_step is not None else None,
            "stream": True,
        }
        with langfuse.propagate_attributes(
            session_id=workspace_id,
            tags=["rp", "setup", "api", "stream"],
            metadata=metadata,
            trace_name="rp.setup.turn.stream",
        ):
            with langfuse.start_as_current_observation(
                name="rp.setup.turn.stream",
                as_type="agent",
                input=payload.model_dump(mode="json"),
            ) as observation:
                chunk_count = 0
                try:
                    async for chunk in runner.run_turn_stream(payload):
                        chunk_count += 1
                        yield chunk
                except ValueError as exc:
                    emit_setup_trace_scores(
                        observation,
                        runtime_result={
                            "finish_reason": None,
                            "assistant_text": "",
                            "warnings": [],
                            "structured_payload": {},
                        },
                        failure_layer="infra",
                        error_code="setup_agent_turn_failed",
                    )
                    observation.update(
                        output={
                            "error": {
                                "message": str(exc),
                                "code": "setup_agent_turn_failed",
                            },
                            "stream_chunk_count": chunk_count,
                        }
                    )
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "error",
                                "error": {
                                    "message": str(exc),
                                    "type": "setup_agent_turn_failed",
                                },
                            }
                        )
                        + "\n\n"
                    )
                    yield "data: " + json.dumps({"type": "done"}) + "\n\n"
                else:
                    runtime_result = runner.last_runtime_result
                    output_payload = (
                        runtime_result.model_dump(mode="json")
                        if runtime_result is not None
                        else {"status": "stream_completed"}
                    )
                    if isinstance(output_payload, dict):
                        output_payload = {
                            **output_payload,
                            "stream_chunk_count": chunk_count,
                        }
                    observation.update(output=output_payload)
                    if runtime_result is not None:
                        emit_setup_trace_scores(
                            observation,
                            runtime_result=runtime_result.model_dump(mode="json"),
                        )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
        },
    )
