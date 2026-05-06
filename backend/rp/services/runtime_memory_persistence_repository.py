"""Persistent repositories for Runtime Workspace materials and memory events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from sqlmodel import Session, select

from models.rp_memory_store import (
    MemoryChangeEventRecord,
    RuntimeWorkspaceMaterialRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_optional_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def clone_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clone_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clone_json_value(item) for item in value]
    return value


def identity_filters(
    model: type[Any], identity: MemoryRuntimeIdentity
) -> tuple[Any, ...]:
    return (
        model.story_id == identity.story_id,
        model.session_id == identity.session_id,
        model.branch_head_id == identity.branch_head_id,
        model.turn_id == identity.turn_id,
        model.runtime_profile_snapshot_id == identity.runtime_profile_snapshot_id,
    )


class RuntimeWorkspaceMaterialRepository:
    """Repository for persistent Runtime Workspace turn materials."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def insert(
        self,
        record: RuntimeWorkspaceMaterialRecord,
    ) -> RuntimeWorkspaceMaterialRecord:
        self._session.add(record)
        self._session.flush()
        return record

    def get_by_material_id(
        self,
        material_id: str,
    ) -> RuntimeWorkspaceMaterialRecord | None:
        return self._session.get(RuntimeWorkspaceMaterialRecord, material_id)

    def get(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
    ) -> RuntimeWorkspaceMaterialRecord | None:
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(*identity_filters(RuntimeWorkspaceMaterialRecord, identity))
            .where(RuntimeWorkspaceMaterialRecord.material_id == material_id)
        )
        return self._session.exec(stmt).first()

    def get_by_short_id(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        short_id: str,
    ) -> RuntimeWorkspaceMaterialRecord | None:
        normalized_short_id = normalize_optional_key(short_id)
        if normalized_short_id is None:
            return None
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(*identity_filters(RuntimeWorkspaceMaterialRecord, identity))
            .where(RuntimeWorkspaceMaterialRecord.short_id_key == normalized_short_id)
        )
        return self._session.exec(stmt).first()

    def list(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_kind: str | None = None,
        domain: str | None = None,
        lifecycle: str | None = None,
    ) -> list[RuntimeWorkspaceMaterialRecord]:
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(*identity_filters(RuntimeWorkspaceMaterialRecord, identity))
            .order_by(cast(Any, RuntimeWorkspaceMaterialRecord.created_at).asc())
            .order_by(cast(Any, RuntimeWorkspaceMaterialRecord.material_id).asc())
        )
        if material_kind is not None:
            stmt = stmt.where(
                RuntimeWorkspaceMaterialRecord.material_kind == material_kind
            )
        if domain is not None:
            stmt = stmt.where(RuntimeWorkspaceMaterialRecord.domain == domain)
        if lifecycle is not None:
            stmt = stmt.where(RuntimeWorkspaceMaterialRecord.lifecycle == lifecycle)
        return list(self._session.exec(stmt).all())

    def update_lifecycle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: str,
        updated_at: datetime,
        expired_at: datetime | None = None,
        invalidated_at: datetime | None = None,
    ) -> RuntimeWorkspaceMaterialRecord | None:
        record = self.get(identity=identity, material_id=material_id)
        if record is None:
            return None
        record.lifecycle = lifecycle
        record.updated_at = updated_at
        if expired_at is not None:
            record.expired_at = expired_at
        if invalidated_at is not None:
            record.invalidated_at = invalidated_at
        self._session.add(record)
        self._session.flush()
        return record


class MemoryChangeEventRepository:
    """Repository for persistent lightweight memory trace/invalidation events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get_event(
        self,
        event_id: str,
    ) -> MemoryChangeEventRecord | None:
        return self._session.get(MemoryChangeEventRecord, event_id)

    def insert(self, record: MemoryChangeEventRecord) -> MemoryChangeEventRecord:
        self._session.add(record)
        self._session.flush()
        return record

    def list_events(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        event_kind: str | None = None,
        operation_kind: str | None = None,
        visibility_effect: str | None = None,
    ) -> list[MemoryChangeEventRecord]:
        stmt = (
            select(MemoryChangeEventRecord)
            .where(*identity_filters(MemoryChangeEventRecord, identity))
            .order_by(cast(Any, MemoryChangeEventRecord.created_at).asc())
            .order_by(cast(Any, MemoryChangeEventRecord.event_id).asc())
        )
        if domain is not None:
            stmt = stmt.where(MemoryChangeEventRecord.domain == domain)
        if layer is not None:
            stmt = stmt.where(MemoryChangeEventRecord.layer == layer)
        if event_kind is not None:
            stmt = stmt.where(MemoryChangeEventRecord.event_kind == event_kind)
        if operation_kind is not None:
            stmt = stmt.where(MemoryChangeEventRecord.operation_kind == operation_kind)
        if visibility_effect is not None:
            stmt = stmt.where(
                MemoryChangeEventRecord.visibility_effect == visibility_effect
            )
        return list(self._session.exec(stmt).all())
