"""Conversation/session metadata endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from models.conversation_store import (
    ConversationCreateRequest,
    ConversationSettingsPayload,
    ConversationSettingsSummary,
    ConversationSummary,
    ConversationUpdateRequest,
)
from services.conversation_store import ConversationStoreService
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


def _service(session: Session = Depends(get_session)) -> ConversationStoreService:
    return ConversationStoreService(session)


@router.get("/api/conversations")
async def list_conversations(
    include_archived: bool = Query(False),
    include_deleted: bool = Query(False),
    role_id: str | None = Query(None),
    service: ConversationStoreService = Depends(_service),
):
    records = service.list_conversations(
        include_archived=include_archived,
        include_deleted=include_deleted,
        role_id=role_id,
    )
    return {
        "object": "list",
        "data": [
            ConversationSummary.from_record(record).model_dump(mode="json")
            for record in records
        ],
    }


@router.post("/api/conversations", status_code=201)
async def create_conversation(
    payload: ConversationCreateRequest,
    service: ConversationStoreService = Depends(_service),
):
    record = service.create_conversation(payload)
    return ConversationSummary.from_record(record).model_dump(mode="json")


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
):
    record = service.get_conversation(conversation_id)
    if record is None:
        raise _conversation_not_found(conversation_id)
    return ConversationSummary.from_record(record).model_dump(mode="json")


@router.patch("/api/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    service: ConversationStoreService = Depends(_service),
):
    record = service.update_conversation(conversation_id, payload)
    if record is None:
        raise _conversation_not_found(conversation_id)
    return ConversationSummary.from_record(record).model_dump(mode="json")


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
):
    deleted = service.soft_delete_conversation(conversation_id)
    if not deleted:
        raise _conversation_not_found(conversation_id)
    return {"status": "ok", "deleted": str(conversation_id)}


@router.get("/api/conversations/{conversation_id}/settings")
async def get_conversation_settings(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
):
    settings = service.get_or_create_settings(conversation_id)
    if settings is None:
        raise _conversation_not_found(conversation_id)
    return ConversationSettingsSummary.from_record(settings).model_dump(mode="json")


@router.put("/api/conversations/{conversation_id}/settings")
async def upsert_conversation_settings(
    conversation_id: UUID,
    payload: ConversationSettingsPayload,
    service: ConversationStoreService = Depends(_service),
):
    settings = service.upsert_settings(conversation_id, payload)
    if settings is None:
        raise _conversation_not_found(conversation_id)
    return ConversationSettingsSummary.from_record(settings).model_dump(mode="json")
