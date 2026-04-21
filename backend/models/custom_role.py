"""Backend-owned custom role models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomRoleRecord(SQLModel, table=True):
    """Durable custom role / assistant identity record."""

    __tablename__ = "custom_roles"

    id: str = Field(primary_key=True, index=True)
    name: str
    description: str
    system_prompt: str
    icon: str = "✨"
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class CustomRolePayload(BaseModel):
    """Create/update payload for custom roles."""

    id: str | None = None
    name: str
    description: str
    system_prompt: str
    icon: str = "✨"


class CustomRoleSummary(BaseModel):
    """Frontend-facing custom role payload."""

    id: str
    name: str
    description: str
    system_prompt: str
    icon: str = "✨"
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: CustomRoleRecord) -> "CustomRoleSummary":
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            system_prompt=record.system_prompt,
            icon=record.icon,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
