"""Conversation/session metadata endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from models.conversation_store import (
    ConversationAttachmentSummary,
    ConversationAttachmentUploadRequest,
    ConversationCompactSummary,
    ConversationCompactSummaryPayload,
    ConversationCreateRequest,
    ConversationSettingsPayload,
    ConversationSettingsSummary,
    ConversationSummary,
    ConversationUpdateRequest,
)
from services.conversation_attachment_service import (
    ConversationAttachmentPersistError,
    ConversationAttachmentService,
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


def _attachment_service(
    session: Session = Depends(get_session),
) -> ConversationAttachmentService:
    return ConversationAttachmentService(session)


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


@router.get("/api/conversations/{conversation_id}/compact-summary")
async def get_conversation_compact_summary(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
):
    conversation = service.get_conversation(conversation_id)
    if conversation is None:
        raise _conversation_not_found(conversation_id)
    summary = service.get_compact_summary(conversation_id)
    if summary is None:
        return ConversationCompactSummary.empty(conversation_id).model_dump(mode="json")
    return ConversationCompactSummary.from_record(summary).model_dump(mode="json")


@router.put("/api/conversations/{conversation_id}/compact-summary")
async def upsert_conversation_compact_summary(
    conversation_id: UUID,
    payload: ConversationCompactSummaryPayload,
    service: ConversationStoreService = Depends(_service),
):
    summary = service.upsert_compact_summary(conversation_id, payload)
    if summary is None:
        raise _conversation_not_found(conversation_id)
    return ConversationCompactSummary.from_record(summary).model_dump(mode="json")


@router.delete("/api/conversations/{conversation_id}/compact-summary")
async def clear_conversation_compact_summary(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
):
    cleared = service.clear_compact_summary(conversation_id)
    if not cleared:
        raise _conversation_not_found(conversation_id)
    return ConversationCompactSummary.empty(conversation_id).model_dump(mode="json")


@router.get("/api/conversations/{conversation_id}/attachments")
async def list_conversation_attachments(
    conversation_id: UUID,
    service: ConversationStoreService = Depends(_service),
    attachment_service: ConversationAttachmentService = Depends(_attachment_service),
):
    conversation = service.get_conversation(conversation_id)
    if conversation is None:
        raise _conversation_not_found(conversation_id)
    return {
        "object": "list",
        "data": [
            item.model_dump(mode="json")
            for item in attachment_service.list_attachments(conversation_id)
        ],
    }


@router.post("/api/conversations/{conversation_id}/attachments", status_code=201)
async def upload_conversation_attachments(
    conversation_id: UUID,
    payload: ConversationAttachmentUploadRequest,
    attachment_service: ConversationAttachmentService = Depends(_attachment_service),
):
    try:
        attachments = attachment_service.persist_attachments(conversation_id, payload)
    except ConversationAttachmentPersistError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": str(exc),
                    "code": "attachment_persist_error",
                }
            },
        ) from exc

    if attachments is None:
        raise _conversation_not_found(conversation_id)
    return {
        "object": "list",
        "data": [item.model_dump(mode="json") for item in attachments],
    }
