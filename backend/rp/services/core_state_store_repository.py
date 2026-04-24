"""Repository for formal Core State store current/revision rows."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
    CoreStateProjectionSlotRecord,
    CoreStateProjectionSlotRevisionRecord,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CoreStateStoreRepository:
    """Persist formal authoritative/projection current rows and revision chains."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_authoritative_object(
        self,
        *,
        story_id: str,
        session_id: str,
        layer: str,
        domain: str,
        domain_path: str,
        object_id: str,
        scope: str,
        current_revision: int,
        data_json: dict | list,
        metadata_json: dict | None = None,
        latest_apply_id: str | None = None,
        payload_schema_ref: str | None = None,
    ) -> CoreStateAuthoritativeObjectRecord:
        record = self.get_authoritative_object(
            session_id=session_id,
            layer=layer,
            scope=scope,
            object_id=object_id,
        )
        if record is None:
            record = CoreStateAuthoritativeObjectRecord(
                authoritative_object_id=f"csa_obj_{uuid4().hex[:12]}",
                story_id=story_id,
                session_id=session_id,
                layer=layer,
                domain=domain,
                domain_path=domain_path,
                object_id=object_id,
                scope=scope,
                current_revision=current_revision,
                data_json=self._clone_json_value(data_json),
                metadata_json=dict(metadata_json or {}),
                latest_apply_id=latest_apply_id,
                payload_schema_ref=payload_schema_ref,
            )
            self._session.add(record)
            self._session.flush()
            return record

        record.story_id = story_id
        record.domain = domain
        record.domain_path = domain_path
        record.current_revision = current_revision
        record.data_json = self._clone_json_value(data_json)
        record.metadata_json = dict(metadata_json or {})
        record.latest_apply_id = latest_apply_id
        record.payload_schema_ref = payload_schema_ref
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return record

    def get_authoritative_object(
        self,
        *,
        session_id: str,
        layer: str,
        scope: str,
        object_id: str,
    ) -> CoreStateAuthoritativeObjectRecord | None:
        stmt = (
            select(CoreStateAuthoritativeObjectRecord)
            .where(CoreStateAuthoritativeObjectRecord.session_id == session_id)
            .where(CoreStateAuthoritativeObjectRecord.layer == layer)
            .where(CoreStateAuthoritativeObjectRecord.scope == scope)
            .where(CoreStateAuthoritativeObjectRecord.object_id == object_id)
        )
        return self._session.exec(stmt).first()

    def upsert_authoritative_revision(
        self,
        *,
        authoritative_object_id: str,
        story_id: str,
        session_id: str,
        layer: str,
        domain: str,
        domain_path: str,
        object_id: str,
        scope: str,
        revision: int,
        data_json: dict | list,
        revision_source_kind: str,
        source_apply_id: str | None = None,
        source_proposal_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> CoreStateAuthoritativeRevisionRecord:
        record = self.get_authoritative_revision(
            session_id=session_id,
            layer=layer,
            scope=scope,
            object_id=object_id,
            revision=revision,
        )
        if record is None:
            record = CoreStateAuthoritativeRevisionRecord(
                authoritative_revision_id=f"csa_rev_{uuid4().hex[:12]}",
                authoritative_object_id=authoritative_object_id,
                story_id=story_id,
                session_id=session_id,
                layer=layer,
                domain=domain,
                domain_path=domain_path,
                object_id=object_id,
                scope=scope,
                revision=revision,
                data_json=self._clone_json_value(data_json),
                revision_source_kind=revision_source_kind,
                source_apply_id=source_apply_id,
                source_proposal_id=source_proposal_id,
                metadata_json=dict(metadata_json or {}),
            )
            self._session.add(record)
            self._session.flush()
            return record

        record.authoritative_object_id = authoritative_object_id
        record.story_id = story_id
        record.domain = domain
        record.domain_path = domain_path
        record.data_json = self._clone_json_value(data_json)
        record.revision_source_kind = revision_source_kind
        record.source_apply_id = source_apply_id
        record.source_proposal_id = source_proposal_id
        record.metadata_json = dict(metadata_json or {})
        self._session.add(record)
        self._session.flush()
        return record

    def get_authoritative_revision(
        self,
        *,
        session_id: str,
        layer: str,
        scope: str,
        object_id: str,
        revision: int,
    ) -> CoreStateAuthoritativeRevisionRecord | None:
        stmt = (
            select(CoreStateAuthoritativeRevisionRecord)
            .where(CoreStateAuthoritativeRevisionRecord.session_id == session_id)
            .where(CoreStateAuthoritativeRevisionRecord.layer == layer)
            .where(CoreStateAuthoritativeRevisionRecord.scope == scope)
            .where(CoreStateAuthoritativeRevisionRecord.object_id == object_id)
            .where(CoreStateAuthoritativeRevisionRecord.revision == revision)
        )
        return self._session.exec(stmt).first()

    def list_authoritative_revisions(
        self,
        *,
        session_id: str,
        object_id: str,
    ) -> list[CoreStateAuthoritativeRevisionRecord]:
        stmt = (
            select(CoreStateAuthoritativeRevisionRecord)
            .where(CoreStateAuthoritativeRevisionRecord.session_id == session_id)
            .where(CoreStateAuthoritativeRevisionRecord.object_id == object_id)
            .order_by(CoreStateAuthoritativeRevisionRecord.revision.asc())
        )
        return list(self._session.exec(stmt).all())

    def list_authoritative_objects_for_session(
        self,
        *,
        session_id: str,
    ) -> list[CoreStateAuthoritativeObjectRecord]:
        stmt = (
            select(CoreStateAuthoritativeObjectRecord)
            .where(CoreStateAuthoritativeObjectRecord.session_id == session_id)
            .order_by(CoreStateAuthoritativeObjectRecord.object_id.asc())
        )
        return list(self._session.exec(stmt).all())

    def upsert_projection_slot(
        self,
        *,
        story_id: str,
        session_id: str,
        chapter_workspace_id: str,
        layer: str,
        domain: str,
        domain_path: str,
        summary_id: str,
        slot_name: str,
        scope: str,
        current_revision: int,
        items_json: list[str],
        metadata_json: dict | None = None,
        last_refresh_kind: str,
        payload_schema_ref: str | None = None,
    ) -> CoreStateProjectionSlotRecord:
        record = self.get_projection_slot(
            chapter_workspace_id=chapter_workspace_id,
            summary_id=summary_id,
        )
        if record is None:
            record = CoreStateProjectionSlotRecord(
                projection_slot_id=f"csp_slot_{uuid4().hex[:12]}",
                story_id=story_id,
                session_id=session_id,
                chapter_workspace_id=chapter_workspace_id,
                layer=layer,
                domain=domain,
                domain_path=domain_path,
                summary_id=summary_id,
                slot_name=slot_name,
                scope=scope,
                current_revision=current_revision,
                items_json=list(items_json),
                metadata_json=dict(metadata_json or {}),
                last_refresh_kind=last_refresh_kind,
                payload_schema_ref=payload_schema_ref,
            )
            self._session.add(record)
            self._session.flush()
            return record

        record.story_id = story_id
        record.session_id = session_id
        record.layer = layer
        record.domain = domain
        record.domain_path = domain_path
        record.slot_name = slot_name
        record.scope = scope
        record.current_revision = current_revision
        record.items_json = list(items_json)
        record.metadata_json = dict(metadata_json or {})
        record.last_refresh_kind = last_refresh_kind
        record.payload_schema_ref = payload_schema_ref
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return record

    def get_projection_slot(
        self,
        *,
        chapter_workspace_id: str,
        summary_id: str,
    ) -> CoreStateProjectionSlotRecord | None:
        stmt = (
            select(CoreStateProjectionSlotRecord)
            .where(CoreStateProjectionSlotRecord.chapter_workspace_id == chapter_workspace_id)
            .where(CoreStateProjectionSlotRecord.summary_id == summary_id)
        )
        return self._session.exec(stmt).first()

    def upsert_projection_slot_revision(
        self,
        *,
        projection_slot_id: str,
        story_id: str,
        session_id: str,
        chapter_workspace_id: str,
        layer: str,
        domain: str,
        domain_path: str,
        summary_id: str,
        slot_name: str,
        scope: str,
        revision: int,
        items_json: list[str],
        refresh_source_kind: str,
        refresh_source_ref: str | None = None,
        metadata_json: dict | None = None,
    ) -> CoreStateProjectionSlotRevisionRecord:
        record = self.get_projection_slot_revision(
            chapter_workspace_id=chapter_workspace_id,
            summary_id=summary_id,
            revision=revision,
        )
        if record is None:
            record = CoreStateProjectionSlotRevisionRecord(
                projection_slot_revision_id=f"csp_rev_{uuid4().hex[:12]}",
                projection_slot_id=projection_slot_id,
                story_id=story_id,
                session_id=session_id,
                chapter_workspace_id=chapter_workspace_id,
                layer=layer,
                domain=domain,
                domain_path=domain_path,
                summary_id=summary_id,
                slot_name=slot_name,
                scope=scope,
                revision=revision,
                items_json=list(items_json),
                refresh_source_kind=refresh_source_kind,
                refresh_source_ref=refresh_source_ref,
                metadata_json=dict(metadata_json or {}),
            )
            self._session.add(record)
            self._session.flush()
            return record

        record.projection_slot_id = projection_slot_id
        record.story_id = story_id
        record.session_id = session_id
        record.layer = layer
        record.domain = domain
        record.domain_path = domain_path
        record.slot_name = slot_name
        record.scope = scope
        record.items_json = list(items_json)
        record.refresh_source_kind = refresh_source_kind
        record.refresh_source_ref = refresh_source_ref
        record.metadata_json = dict(metadata_json or {})
        self._session.add(record)
        self._session.flush()
        return record

    def get_projection_slot_revision(
        self,
        *,
        chapter_workspace_id: str,
        summary_id: str,
        revision: int,
    ) -> CoreStateProjectionSlotRevisionRecord | None:
        stmt = (
            select(CoreStateProjectionSlotRevisionRecord)
            .where(CoreStateProjectionSlotRevisionRecord.chapter_workspace_id == chapter_workspace_id)
            .where(CoreStateProjectionSlotRevisionRecord.summary_id == summary_id)
            .where(CoreStateProjectionSlotRevisionRecord.revision == revision)
        )
        return self._session.exec(stmt).first()

    def list_projection_slot_revisions(
        self,
        *,
        chapter_workspace_id: str,
        summary_id: str,
    ) -> list[CoreStateProjectionSlotRevisionRecord]:
        stmt = (
            select(CoreStateProjectionSlotRevisionRecord)
            .where(CoreStateProjectionSlotRevisionRecord.chapter_workspace_id == chapter_workspace_id)
            .where(CoreStateProjectionSlotRevisionRecord.summary_id == summary_id)
            .order_by(CoreStateProjectionSlotRevisionRecord.revision.asc())
        )
        return list(self._session.exec(stmt).all())

    def list_projection_slots_for_chapter(
        self,
        *,
        chapter_workspace_id: str,
    ) -> list[CoreStateProjectionSlotRecord]:
        stmt = (
            select(CoreStateProjectionSlotRecord)
            .where(CoreStateProjectionSlotRecord.chapter_workspace_id == chapter_workspace_id)
            .order_by(CoreStateProjectionSlotRecord.slot_name.asc())
        )
        return list(self._session.exec(stmt).all())

    @staticmethod
    def _clone_json_value(value):
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return value
