"""Durable attachment persistence for backend-owned conversations."""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from uuid import UUID, uuid4

from sqlmodel import Session

from config import get_settings
from models.conversation_store import (
    ConversationAttachmentSummary,
    ConversationAttachmentUploadItem,
    ConversationAttachmentUploadRequest,
)
from services.conversation_store import ConversationStoreService

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ConversationAttachmentPersistError(Exception):
    """Raised when attachment bytes cannot be persisted."""


class ConversationAttachmentService:
    """Persist durable attachment metadata and file bytes."""

    def __init__(self, session: Session):
        self._session = session
        self._conversation_store = ConversationStoreService(session)

    def list_attachments(self, conversation_id: UUID) -> list[ConversationAttachmentSummary]:
        return [
            ConversationAttachmentSummary.from_record(record)
            for record in self._conversation_store.list_attachments(conversation_id)
        ]

    def persist_attachments(
        self,
        conversation_id: UUID,
        payload: ConversationAttachmentUploadRequest,
    ) -> list[ConversationAttachmentSummary] | None:
        conversation = self._conversation_store.get_conversation(conversation_id)
        if conversation is None:
            return None

        persisted: list[ConversationAttachmentSummary] = []
        for item in payload.files:
            attachment_id = item.client_id or uuid4().hex
            raw = self._read_bytes(item)
            safe_name = self._safe_filename(item.name)
            storage_key = f"attachments/{conversation_id}/{attachment_id}_{safe_name}"
            local_path = (get_settings().storage_dir / storage_key).resolve()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(raw)

            record = self._conversation_store.upsert_attachment(
                attachment_id=attachment_id,
                conversation_id=conversation_id,
                storage_key=storage_key,
                local_path=str(local_path),
                original_name=item.name,
                mime_type=item.mime_type,
                size_bytes=len(raw),
                kind=item.kind or self._infer_kind(item.mime_type, item.name),
                metadata_payload=item.metadata,
            )
            if record is None:
                return None
            persisted.append(ConversationAttachmentSummary.from_record(record))

        return persisted

    def _read_bytes(self, item: ConversationAttachmentUploadItem) -> bytes:
        if item.data:
            try:
                return base64.b64decode(item.data)
            except (binascii.Error, ValueError) as exc:
                raise ConversationAttachmentPersistError(
                    f"Invalid base64 attachment payload for {item.name}"
                ) from exc

        if item.path:
            path = Path(item.path)
            if not path.exists():
                raise ConversationAttachmentPersistError(
                    f"Attachment path does not exist: {item.path}"
                )
            return path.read_bytes()

        raise ConversationAttachmentPersistError(
            f"Attachment has no readable data: {item.name}"
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        sanitized = _SAFE_FILENAME_RE.sub("_", name).strip("._")
        return sanitized or "attachment"

    @staticmethod
    def _infer_kind(mime_type: str, name: str) -> str:
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("text/"):
            return "code" if ConversationAttachmentService._looks_like_code(name) else "document"
        if any(
            token in mime_type
            for token in (
                "json",
                "xml",
                "yaml",
                "javascript",
                "python",
                "dart",
            )
        ):
            return "code"
        if any(
            token in mime_type
            for token in ("pdf", "word", "excel", "powerpoint", "markdown")
        ):
            return "document"
        return "other"

    @staticmethod
    def _looks_like_code(name: str) -> bool:
        ext = Path(name).suffix.lower()
        return ext in {
            ".js",
            ".ts",
            ".py",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".cs",
            ".go",
            ".rs",
            ".swift",
            ".kt",
            ".dart",
            ".html",
            ".css",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
        }
