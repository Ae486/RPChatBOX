"""In-process memory change event spine for trace and invalidation records."""

from __future__ import annotations

from dataclasses import dataclass, field

from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
)
from rp.services.memory_contract_registry import (
    MemoryContractRegistryError,
    MemoryContractRegistryService,
)


@dataclass
class MemoryChangeEventStore:
    """Process-local event store for the first lightweight spine slice."""

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

    Events remain trace and invalidation facts only. The service validates domain
    vocabulary through the declarative registry, isolates reads by full runtime
    identity, and deliberately does not expose replay or persistence semantics.
    """

    def __init__(
        self,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        store: MemoryChangeEventStore | None = None,
    ) -> None:
        self._registry_service = registry_service or MemoryContractRegistryService()
        self._store = store or MemoryChangeEventStore()

    @property
    def store(self) -> MemoryChangeEventStore:
        return self._store

    def record_event(self, event: MemoryChangeEvent) -> MemoryChangeEvent:
        if event.event_id in self._store.event_ids:
            raise MemoryChangeEventServiceError(
                "memory_change_event_id_conflict",
                event.event_id,
            )

        resolved_domain = self._require_registered_domain(event.domain)
        event = event.model_copy(update={"domain": resolved_domain})
        identity_key = _identity_key(event.identity)
        self._store.event_ids.add(event.event_id)
        self._store.events_by_identity.setdefault(identity_key, []).append(event)
        return event

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
        events = self._store.events_by_identity.get(_identity_key(identity), [])
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


def _identity_key(identity: MemoryRuntimeIdentity) -> tuple[str, str, str, str, str]:
    return (
        identity.story_id,
        identity.session_id,
        identity.branch_head_id,
        identity.turn_id,
        identity.runtime_profile_snapshot_id,
    )
