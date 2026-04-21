"""Database-backed custom role store."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import desc
from sqlmodel import Session, select

from models.custom_role import CustomRolePayload, CustomRoleRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomRoleStoreService:
    """CRUD service for backend-owned custom roles."""

    def __init__(self, session: Session):
        self._session = session

    def list_roles(self) -> list[CustomRoleRecord]:
        statement = select(CustomRoleRecord).order_by(
            desc(CustomRoleRecord.updated_at),
            desc(CustomRoleRecord.created_at),
        )
        return list(self._session.exec(statement).all())

    def get_role(self, role_id: str) -> CustomRoleRecord | None:
        return self._session.get(CustomRoleRecord, role_id)

    def upsert_role(self, payload: CustomRolePayload) -> CustomRoleRecord:
        role_id = (payload.id or "").strip() or uuid4().hex
        record = self.get_role(role_id)
        now = _utcnow()
        if record is None:
            record = CustomRoleRecord(
                id=role_id,
                created_at=now,
            )

        record.name = payload.name
        record.description = payload.description
        record.system_prompt = payload.system_prompt
        record.icon = payload.icon
        record.updated_at = now

        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def delete_role(self, role_id: str) -> bool:
        record = self.get_role(role_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.commit()
        return True
