"""Conversation source-thread endpoints backed by LangGraph checkpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from models.conversation_source import (
    ConversationSourcePatchRequest,
    ConversationSourceSelectionRequest,
    ConversationSourceWriteRequest,
)
from services.conversation_source import (
    ConversationSourceCheckpointNotFoundError,
    ConversationSourceMessageNotFoundError,
    ConversationSourceService,
)
from services.database import get_session

router = APIRouter()


def _conversation_not_found(conversation_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Conversation not found: {conversation_id}",
                "code": "conversation_not_found",
            }
        },
    )


def _checkpoint_not_found(checkpoint_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Checkpoint not found: {checkpoint_id}",
                "code": "checkpoint_not_found",
            }
        },
    )


def _message_not_found(message_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Message not found in source checkpoint: {message_id}",
                "code": "source_message_not_found",
            }
        },
    )


def _service(session: Session = Depends(get_session)) -> ConversationSourceService:
    return ConversationSourceService(session)


@router.get("/api/conversations/{conversation_id}/source")
async def get_conversation_source(
    conversation_id: UUID,
    service: ConversationSourceService = Depends(_service),
):
    source = service.get_source(conversation_id)
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")


@router.get("/api/conversations/{conversation_id}/source/projection")
async def get_conversation_source_projection(
    conversation_id: UUID,
    service: ConversationSourceService = Depends(_service),
):
    projection = service.get_projection(conversation_id)
    if projection is None:
        raise _conversation_not_found(conversation_id)
    return projection.model_dump(mode="json")


@router.get("/api/conversations/{conversation_id}/source/history")
async def list_conversation_source_history(
    conversation_id: UUID,
    service: ConversationSourceService = Depends(_service),
):
    history = service.list_history(conversation_id)
    if history is None:
        raise _conversation_not_found(conversation_id)
    return {
        "object": "list",
        "data": [item.model_dump(mode="json") for item in history],
    }


@router.post("/api/conversations/{conversation_id}/source/messages")
async def append_conversation_source_messages(
    conversation_id: UUID,
    payload: ConversationSourceWriteRequest,
    service: ConversationSourceService = Depends(_service),
):
    try:
        source = service.append_messages(conversation_id, payload)
    except ConversationSourceCheckpointNotFoundError:
        raise _checkpoint_not_found(payload.base_checkpoint_id or "")
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")


@router.patch("/api/conversations/{conversation_id}/source/messages/{message_id}")
async def patch_conversation_source_message(
    conversation_id: UUID,
    message_id: str,
    payload: ConversationSourcePatchRequest,
    service: ConversationSourceService = Depends(_service),
):
    try:
        source = service.patch_message(conversation_id, message_id, payload)
    except ConversationSourceCheckpointNotFoundError:
        raise _checkpoint_not_found(payload.base_checkpoint_id or "")
    except ConversationSourceMessageNotFoundError:
        raise _message_not_found(message_id)
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")


@router.delete("/api/conversations/{conversation_id}/source/messages/{message_id}")
async def delete_conversation_source_message(
    conversation_id: UUID,
    message_id: str,
    service: ConversationSourceService = Depends(_service),
):
    try:
        source = service.delete_message(conversation_id, message_id)
    except ConversationSourceMessageNotFoundError:
        raise _message_not_found(message_id)
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")


@router.put("/api/conversations/{conversation_id}/source/selection")
async def select_conversation_source_checkpoint(
    conversation_id: UUID,
    payload: ConversationSourceSelectionRequest,
    service: ConversationSourceService = Depends(_service),
):
    try:
        source = service.select_checkpoint(conversation_id, payload)
    except ConversationSourceCheckpointNotFoundError:
        raise _checkpoint_not_found(payload.checkpoint_id or "")
    except ConversationSourceMessageNotFoundError:
        raise _message_not_found(payload.message_id or "")
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")


@router.delete("/api/conversations/{conversation_id}/source")
async def clear_conversation_source(
    conversation_id: UUID,
    service: ConversationSourceService = Depends(_service),
):
    source = service.clear_source(conversation_id)
    if source is None:
        raise _conversation_not_found(conversation_id)
    return source.model_dump(mode="json")
