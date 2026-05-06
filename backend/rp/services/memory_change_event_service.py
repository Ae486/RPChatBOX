"""Persistent memory change event spine for trace and invalidation records."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from models.rp_memory_store import MemoryChangeEventRecord
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
)
from rp.services.memory_contract_registry import (
    MemoryContractRegistryError,
    MemoryContractRegistryService,
)
from rp.services.runtime_memory_persistence_repository import (
    MemoryChangeEventRepository,
    clone_json_value,
    utcnow,
)
from services.database import get_engine


@dataclass
class MemoryChangeEventStore:
    """Optional in-process fallback/test seam for memory events."""

    events_by_identity: dict[
        tuple[str, str, str, str, str], list[MemoryChangeEvent]
    ] = field(default_factory=dict)
    event_ids: set[str] = field(default_factory=set)


class MemoryChangeEventServiceError(ValueError):
    """Stable memory event spine error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class MemoryChangeEventService:
    """Shared lightweight event recording and dirty-target query surface.

    Persistent repository-backed storage is the default boot path. The injected
    in-process store remains available as a fallback/test seam when explicitly
    requested via `store=` without a session or repository.
    """

    def __init__(
        self,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        session: Session | None = None,
        repository: MemoryChangeEventRepository | None = None,
        store: MemoryChangeEventStore | None = None,
    ) -> None:
        self._registry_service = registry_service or MemoryContractRegistryService()
        self._session = session
        self._repository = repository
        self._store = store or MemoryChangeEventStore()
        self._persistent_enabled = (
            repository is not None or session is not None or store is None
        )

    @property
    def store(self) -> MemoryChangeEventStore:
        return self._store

    def record_event(self, event: MemoryChangeEvent) -> MemoryChangeEvent:
        resolved_domain = self._require_registered_domain(event.domain)
        normalized_event = event.model_copy(update={"domain": resolved_domain})
        if not self._persistent_enabled:
            return self._record_event_in_store(normalized_event)
        return self._record_event_persistently(normalized_event)

    def list_events(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        event_kind: str | None = None,
        operation_kind: str | None = None,
        source_type: str | None = None,
        dirty_target_kind: str | None = None,
        visibility_effect: str | None = None,
    ) -> list[MemoryChangeEvent]:
        resolved_domain = (
            self._require_registered_domain(domain) if domain is not None else None
        )
        if not self._persistent_enabled:
            events = self._store.events_by_identity.get(_identity_key(identity), [])
        else:
            with self._repository_scope() as (repository, _):
                events = [
                    _record_to_event(record)
                    for record in repository.list_events(
                        identity=identity,
                        domain=resolved_domain,
                        layer=layer,
                        event_kind=event_kind,
                        operation_kind=operation_kind,
                        visibility_effect=visibility_effect,
                    )
                ]
        return [
            event
            for event in events
            if (resolved_domain is None or event.domain == resolved_domain)
            and (layer is None or event.layer == layer)
            and (event_kind is None or event.event_kind == event_kind)
            and (operation_kind is None or event.operation_kind == operation_kind)
            and (
                source_type is None
                or any(ref.source_type == source_type for ref in event.source_refs)
            )
            and (
                dirty_target_kind is None
                or any(
                    target.target_kind == dirty_target_kind
                    for target in event.dirty_targets
                )
            )
            and (
                visibility_effect is None
                or event.visibility_effect == visibility_effect
            )
        ]

    def list_dirty_targets(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        target_kind: str | None = None,
    ) -> list[MemoryDirtyTarget]:
        events = self.list_events(identity=identity, domain=domain, layer=layer)
        dirty_targets: list[MemoryDirtyTarget] = []
        for event in events:
            for target in event.dirty_targets:
                if target_kind is None or target.target_kind == target_kind:
                    dirty_targets.append(target)
        return dirty_targets

    def _record_event_in_store(self, event: MemoryChangeEvent) -> MemoryChangeEvent:
        if event.event_id in self._store.event_ids:
            raise MemoryChangeEventServiceError(
                "memory_change_event_id_conflict",
                event.event_id,
            )
        identity_key = _identity_key(event.identity)
        self._store.event_ids.add(event.event_id)
        self._store.events_by_identity.setdefault(identity_key, []).append(event)
        return event

    def _record_event_persistently(self, event: MemoryChangeEvent) -> MemoryChangeEvent:
        with self._repository_scope() as (repository, managed_session):
            try:
                if repository.get_event(event.event_id) is not None:
                    raise MemoryChangeEventServiceError(
                        "memory_change_event_id_conflict",
                        event.event_id,
                    )
                repository.insert(_event_to_record(event))
                if managed_session is not None:
                    managed_session.commit()
                return event
            except MemoryChangeEventServiceError:
                _rollback_if_needed(managed_session)
                raise
            except IntegrityError as exc:
                _rollback_if_needed(managed_session)
                if repository.get_event(event.event_id) is not None:
                    raise MemoryChangeEventServiceError(
                        "memory_change_event_id_conflict",
                        event.event_id,
                    ) from exc
                raise
            except Exception:
                _rollback_if_needed(managed_session)
                raise

    @contextmanager
    def _repository_scope(
        self,
    ) -> Iterator[tuple[MemoryChangeEventRepository, Session | None]]:
        if not self._persistent_enabled:
            raise RuntimeError("persistent repository scope not available")
        if self._repository is not None:
            yield self._repository, None
            return
        if self._session is not None:
            yield MemoryChangeEventRepository(self._session), None
            return
        with Session(get_engine()) as session:
            yield MemoryChangeEventRepository(session), session

    def _require_registered_domain(self, domain: str) -> str:
        try:
            return self._registry_service.require_domain(domain).domain_id
        except MemoryContractRegistryError as exc:
            if exc.code != "memory_domain_not_registered":
                raise
            raise MemoryChangeEventServiceError(
                "memory_change_event_domain_not_registered",
                domain,
            ) from exc


def _event_to_record(event: MemoryChangeEvent) -> MemoryChangeEventRecord:
    return MemoryChangeEventRecord(
        event_id=event.event_id,
        story_id=event.identity.story_id,
        session_id=event.identity.session_id,
        branch_head_id=event.identity.branch_head_id,
        turn_id=event.identity.turn_id,
        runtime_profile_snapshot_id=event.identity.runtime_profile_snapshot_id,
        actor=event.actor,
        event_kind=event.event_kind,
        layer=event.layer,
        domain=event.domain,
        block_id=event.block_id,
        entry_id=event.entry_id,
        operation_kind=event.operation_kind,
        visibility_effect=event.visibility_effect,
        source_refs_json=[
            clone_json_value(ref.model_dump(mode="json")) for ref in event.source_refs
        ],
        dirty_targets_json=[
            clone_json_value(target.model_dump(mode="json"))
            for target in event.dirty_targets
        ],
        metadata_json=clone_json_value(event.metadata),
        created_at=utcnow(),
    )


def _record_to_event(record: MemoryChangeEventRecord) -> MemoryChangeEvent:
    return MemoryChangeEvent.model_validate(
        {
            "event_id": record.event_id,
            "identity": {
                "story_id": record.story_id,
                "session_id": record.session_id,
                "branch_head_id": record.branch_head_id,
                "turn_id": record.turn_id,
                "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
            },
            "actor": record.actor,
            "event_kind": record.event_kind,
            "layer": record.layer,
            "domain": record.domain,
            "block_id": record.block_id,
            "entry_id": record.entry_id,
            "operation_kind": record.operation_kind,
            "source_refs": clone_json_value(record.source_refs_json),
            "dirty_targets": clone_json_value(record.dirty_targets_json),
            "visibility_effect": record.visibility_effect,
            "metadata": clone_json_value(record.metadata_json),
        }
    )


def _identity_key(identity: MemoryRuntimeIdentity) -> tuple[str, str, str, str, str]:
    return (
        identity.story_id,
        identity.session_id,
        identity.branch_head_id,
        identity.turn_id,
        identity.runtime_profile_snapshot_id,
    )


def _rollback_if_needed(session: Session | None) -> None:
    if session is not None:
        session.rollback()
