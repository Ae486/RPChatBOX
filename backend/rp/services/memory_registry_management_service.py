"""Persistent management layer for RP memory registry descriptors and profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, select

from models.rp_registry_store import (
    MemoryBlockTemplateDescriptorRecord,
    MemoryDomainDescriptorRecord,
    MemoryModeProfileRecord,
    MemoryWorkerDescriptorRecord,
)
from rp.models.memory_contract_registry import (
    MemoryBlockTemplate,
    MemoryContractRegistry,
    MemoryDomainContract,
    MemoryLifecycleState,
    MemoryWorkerDescriptor,
)
from rp.services.memory_contract_registry import (
    MemoryContractRegistryService,
    build_bootstrap_memory_contract_registry,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_RecordT = TypeVar(
    "_RecordT",
    MemoryDomainDescriptorRecord,
    MemoryWorkerDescriptorRecord,
    MemoryBlockTemplateDescriptorRecord,
)


class MemoryRegistryManagementServiceError(ValueError):
    """Stable registry-management error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class MemoryRegistryManagementService:
    """Manage persistent descriptors/profiles layered above bootstrap defaults."""

    MODE_PROFILE_DRAFT = "draft"
    MODE_PROFILE_PUBLISHED = "published"
    MODE_PROFILE_ACTIVE = "active"
    MODE_PROFILE_SUPERSEDED = "superseded"
    MODE_PROFILE_RETIRED = "retired"

    def __init__(self, session: Session) -> None:
        self._session = session

    def registry_service(self) -> MemoryContractRegistryService:
        return MemoryContractRegistryService(registry=self.build_effective_registry())

    def build_effective_registry(self) -> MemoryContractRegistry:
        registry = build_bootstrap_memory_contract_registry()
        domain_records = self._latest_descriptor_records(
            self._session.exec(select(MemoryDomainDescriptorRecord)).all(),
            key_attr="domain_id",
        )
        block_records = self._latest_descriptor_records(
            self._session.exec(select(MemoryBlockTemplateDescriptorRecord)).all(),
            key_attr="block_template_id",
        )
        worker_records = self._latest_descriptor_records(
            self._session.exec(select(MemoryWorkerDescriptorRecord)).all(),
            key_attr="worker_id",
        )

        domains = {
            _normalize_key(registry_domain.domain_id): registry_domain
            for registry_domain in registry.domains
        }
        for record in domain_records:
            persistent_domain = self._domain_from_record(record)
            domains[_normalize_key(persistent_domain.domain_id)] = persistent_domain

        for record in block_records:
            template = self._block_template_from_record(record)
            domain_key = _normalize_key(template.domain_id)
            target_domain = domains.get(domain_key)
            if target_domain is None:
                continue
            templates = {
                _normalize_key(item.block_template_id): item
                for item in target_domain.block_templates
            }
            templates[_normalize_key(template.block_template_id)] = template
            allowed_layers = list(target_domain.allowed_layers)
            if template.layer not in allowed_layers:
                allowed_layers.append(template.layer)
            domains[domain_key] = target_domain.model_copy(
                update={
                    "allowed_layers": allowed_layers,
                    "block_templates": list(templates.values()),
                }
            )

        workers = {
            _normalize_key(worker.worker_id): worker for worker in registry.workers
        }
        for record in worker_records:
            worker = self._worker_from_record(record)
            workers[_normalize_key(worker.worker_id)] = worker

        return registry.model_copy(
            update={
                "version": self._registry_version(
                    registry=registry,
                    domain_records=domain_records,
                    block_records=block_records,
                    worker_records=worker_records,
                ),
                "domains": list(domains.values()),
                "workers": list(workers.values()),
            }
        )

    def upsert_domain_descriptor(
        self,
        descriptor: MemoryDomainContract | dict[str, Any],
        *,
        actor: str,
        version: int | None = None,
    ) -> MemoryDomainDescriptorRecord:
        domain = MemoryDomainContract.model_validate(descriptor)
        next_version = version or self._next_version(
            MemoryDomainDescriptorRecord,
            id_attr="domain_id",
            id_value=domain.domain_id,
        )
        now = _utcnow()
        record = MemoryDomainDescriptorRecord(
            descriptor_record_id=f"domain:{_normalize_key(domain.domain_id)}:v{next_version}",
            domain_id=domain.domain_id,
            version=next_version,
            lifecycle=domain.lifecycle.value,
            config_json=domain.model_dump(mode="json"),
            actor=_normalize_actor(actor),
            created_at=now,
            updated_at=now,
        )
        self._session.merge(record)
        self._session.flush()
        return record

    def upsert_worker_descriptor(
        self,
        descriptor: MemoryWorkerDescriptor | dict[str, Any],
        *,
        actor: str,
        version: int | None = None,
    ) -> MemoryWorkerDescriptorRecord:
        worker = MemoryWorkerDescriptor.model_validate(descriptor)
        next_version = version or self._next_version(
            MemoryWorkerDescriptorRecord,
            id_attr="worker_id",
            id_value=worker.worker_id,
        )
        now = _utcnow()
        record = MemoryWorkerDescriptorRecord(
            descriptor_record_id=f"worker:{_normalize_key(worker.worker_id)}:v{next_version}",
            worker_id=worker.worker_id,
            version=next_version,
            lifecycle=worker.lifecycle.value,
            config_json=worker.model_dump(mode="json"),
            actor=_normalize_actor(actor),
            created_at=now,
            updated_at=now,
        )
        self._session.merge(record)
        self._session.flush()
        return record

    def upsert_block_template_descriptor(
        self,
        descriptor: MemoryBlockTemplate | dict[str, Any],
        *,
        actor: str,
        version: int | None = None,
    ) -> MemoryBlockTemplateDescriptorRecord:
        template = MemoryBlockTemplate.model_validate(descriptor)
        self.registry_service().require_domain(template.domain_id)
        next_version = version or self._next_version(
            MemoryBlockTemplateDescriptorRecord,
            id_attr="block_template_id",
            id_value=template.block_template_id,
        )
        now = _utcnow()
        record = MemoryBlockTemplateDescriptorRecord(
            descriptor_record_id=(
                f"block_template:{_normalize_key(template.block_template_id)}:"
                f"v{next_version}"
            ),
            block_template_id=template.block_template_id,
            domain_id=template.domain_id,
            version=next_version,
            lifecycle=template.lifecycle.value,
            config_json=template.model_dump(mode="json"),
            actor=_normalize_actor(actor),
            created_at=now,
            updated_at=now,
        )
        self._session.merge(record)
        self._session.flush()
        return record

    def hide_domain_descriptor(
        self,
        *,
        domain_id: str,
        actor: str,
    ) -> MemoryDomainDescriptorRecord:
        domain = self.registry_service().require_domain(domain_id)
        return self.upsert_domain_descriptor(
            domain.model_copy(update={"lifecycle": MemoryLifecycleState.HIDDEN}),
            actor=actor,
        )

    def retire_domain_descriptor(
        self,
        *,
        domain_id: str,
        actor: str,
    ) -> MemoryDomainDescriptorRecord:
        domain = self.registry_service().require_domain(domain_id)
        return self.upsert_domain_descriptor(
            domain.model_copy(update={"lifecycle": MemoryLifecycleState.RETIRED}),
            actor=actor,
        )

    def migrate_domain_descriptor(
        self,
        *,
        domain_id: str,
        migrated_to: str,
        actor: str,
    ) -> MemoryDomainDescriptorRecord:
        domain = self.registry_service().require_domain(domain_id)
        return self.upsert_domain_descriptor(
            domain.model_copy(
                update={
                    "lifecycle": MemoryLifecycleState.MIGRATED,
                    "migrated_to": migrated_to,
                }
            ),
            actor=actor,
        )

    def hide_worker_descriptor(
        self,
        *,
        worker_id: str,
        actor: str,
    ) -> MemoryWorkerDescriptorRecord:
        worker = self.registry_service().require_worker(worker_id)
        return self.upsert_worker_descriptor(
            worker.model_copy(update={"lifecycle": MemoryLifecycleState.HIDDEN}),
            actor=actor,
        )

    def retire_worker_descriptor(
        self,
        *,
        worker_id: str,
        actor: str,
    ) -> MemoryWorkerDescriptorRecord:
        worker = self.registry_service().require_worker(worker_id)
        return self.upsert_worker_descriptor(
            worker.model_copy(update={"lifecycle": MemoryLifecycleState.RETIRED}),
            actor=actor,
        )

    def migrate_worker_descriptor(
        self,
        *,
        worker_id: str,
        migrated_to: str,
        actor: str,
    ) -> MemoryWorkerDescriptorRecord:
        worker = self.registry_service().require_worker(worker_id)
        return self.upsert_worker_descriptor(
            worker.model_copy(
                update={
                    "lifecycle": MemoryLifecycleState.MIGRATED,
                    "migrated_to": migrated_to,
                }
            ),
            actor=actor,
        )

    def hide_block_template_descriptor(
        self,
        *,
        block_template_id: str,
        actor: str,
    ) -> MemoryBlockTemplateDescriptorRecord:
        template = self.registry_service().require_block_template(block_template_id)
        return self.upsert_block_template_descriptor(
            template.model_copy(update={"lifecycle": MemoryLifecycleState.HIDDEN}),
            actor=actor,
        )

    def retire_block_template_descriptor(
        self,
        *,
        block_template_id: str,
        actor: str,
    ) -> MemoryBlockTemplateDescriptorRecord:
        template = self.registry_service().require_block_template(block_template_id)
        return self.upsert_block_template_descriptor(
            template.model_copy(update={"lifecycle": MemoryLifecycleState.RETIRED}),
            actor=actor,
        )

    def migrate_block_template_descriptor(
        self,
        *,
        block_template_id: str,
        migrated_to: str,
        actor: str,
    ) -> MemoryBlockTemplateDescriptorRecord:
        template = self.registry_service().require_block_template(block_template_id)
        return self.upsert_block_template_descriptor(
            template.model_copy(
                update={
                    "lifecycle": MemoryLifecycleState.MIGRATED,
                    "migrated_to": migrated_to,
                }
            ),
            actor=actor,
        )

    def list_domain_descriptors(
        self,
        *,
        mode: str | None = None,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.registry_service().list_domains(
                mode=mode,
                include_hidden=include_hidden,
            )
        ]

    def list_worker_descriptors(
        self,
        *,
        mode: str | None = None,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.registry_service().list_workers(
                mode=mode,
                include_hidden=include_hidden,
            )
        ]

    def list_block_template_descriptors(
        self,
        *,
        domain_id: str | None = None,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.registry_service().list_block_templates(
                domain_id=domain_id,
                include_hidden=include_hidden,
            )
        ]

    def create_mode_profile(
        self,
        *,
        profile_id: str,
        mode: str,
        config_json: dict[str, Any] | None = None,
        actor: str,
        version: int = 1,
    ) -> MemoryModeProfileRecord:
        normalized_profile_id = _require_key(profile_id, "profile_id")
        normalized_mode = _require_key(mode, "mode")
        now = _utcnow()
        existing = self._session.get(MemoryModeProfileRecord, normalized_profile_id)
        record = existing or MemoryModeProfileRecord(
            profile_id=normalized_profile_id,
            mode=normalized_mode,
            version=version,
            status=self.MODE_PROFILE_DRAFT,
            config_json={},
            actor=_normalize_actor(actor),
            created_at=now,
            updated_at=now,
        )
        record.mode = normalized_mode
        record.version = version
        record.status = self.MODE_PROFILE_DRAFT
        record.config_json = dict(config_json or {})
        record.actor = _normalize_actor(actor)
        record.published_at = None
        record.activated_at = None
        record.superseded_at = None
        record.updated_at = now
        self._session.add(record)
        self._session.flush()
        return record

    def publish_mode_profile(self, *, profile_id: str, actor: str) -> str:
        record = self._require_mode_profile(profile_id)
        if record.status == self.MODE_PROFILE_RETIRED:
            raise MemoryRegistryManagementServiceError(
                "memory_mode_profile_retired",
                profile_id,
            )
        record.status = self.MODE_PROFILE_PUBLISHED
        record.actor = _normalize_actor(actor)
        record.published_at = _utcnow()
        record.updated_at = record.published_at
        self._session.add(record)
        self._session.flush()
        return record.profile_id

    def activate_mode_profile(self, *, profile_id: str, actor: str) -> str:
        record = self._require_mode_profile(profile_id)
        if record.status == self.MODE_PROFILE_DRAFT:
            self.publish_mode_profile(profile_id=profile_id, actor=actor)
            record = self._require_mode_profile(profile_id)
        if record.status == self.MODE_PROFILE_RETIRED:
            raise MemoryRegistryManagementServiceError(
                "memory_mode_profile_retired",
                profile_id,
            )

        now = _utcnow()
        active_rows = self._session.exec(
            select(MemoryModeProfileRecord)
            .where(MemoryModeProfileRecord.mode == record.mode)
            .where(MemoryModeProfileRecord.status == self.MODE_PROFILE_ACTIVE)
        ).all()
        for active in active_rows:
            if active.profile_id == record.profile_id:
                continue
            active.status = self.MODE_PROFILE_SUPERSEDED
            active.superseded_at = now
            active.updated_at = now
            active.actor = _normalize_actor(actor)
            self._session.add(active)

        record.status = self.MODE_PROFILE_ACTIVE
        record.actor = _normalize_actor(actor)
        record.activated_at = now
        record.updated_at = now
        self._session.add(record)
        self._session.flush()
        return record.profile_id

    def get_active_mode_profile(
        self,
        *,
        mode: str,
    ) -> MemoryModeProfileRecord | None:
        normalized_mode = _require_key(mode, "mode")
        return self._session.exec(
            select(MemoryModeProfileRecord)
            .where(MemoryModeProfileRecord.mode == normalized_mode)
            .where(MemoryModeProfileRecord.status == self.MODE_PROFILE_ACTIVE)
        ).first()

    def get_active_mode_profile_config(self, *, mode: str) -> dict[str, Any] | None:
        record = self.get_active_mode_profile(mode=mode)
        if record is None:
            return None
        config = dict(record.config_json or {})
        config.setdefault("mode_profile_ref", record.profile_id)
        config.setdefault("mode_profile_version", record.version)
        config.setdefault("mode_profile_status", record.status)
        return config

    @staticmethod
    def _latest_descriptor_records(
        records: list[_RecordT],
        *,
        key_attr: str,
    ) -> list[_RecordT]:
        latest: dict[str, _RecordT] = {}
        for record in records:
            key = _normalize_key(str(getattr(record, key_attr)))
            previous = latest.get(key)
            if previous is None or record.version > previous.version:
                latest[key] = record
        return list(latest.values())

    @staticmethod
    def _domain_from_record(
        record: MemoryDomainDescriptorRecord,
    ) -> MemoryDomainContract:
        payload = dict(record.config_json or {})
        payload["domain_id"] = record.domain_id
        payload["lifecycle"] = record.lifecycle
        return MemoryDomainContract.model_validate(payload)

    @staticmethod
    def _worker_from_record(
        record: MemoryWorkerDescriptorRecord,
    ) -> MemoryWorkerDescriptor:
        payload = dict(record.config_json or {})
        payload["worker_id"] = record.worker_id
        payload["lifecycle"] = record.lifecycle
        return MemoryWorkerDescriptor.model_validate(payload)

    @staticmethod
    def _block_template_from_record(
        record: MemoryBlockTemplateDescriptorRecord,
    ) -> MemoryBlockTemplate:
        payload = dict(record.config_json or {})
        payload["block_template_id"] = record.block_template_id
        payload["domain_id"] = record.domain_id
        payload["lifecycle"] = record.lifecycle
        return MemoryBlockTemplate.model_validate(payload)

    @staticmethod
    def _registry_version(
        *,
        registry: MemoryContractRegistry,
        domain_records: list[MemoryDomainDescriptorRecord],
        block_records: list[MemoryBlockTemplateDescriptorRecord],
        worker_records: list[MemoryWorkerDescriptorRecord],
    ) -> str:
        if not domain_records and not block_records and not worker_records:
            return registry.version
        descriptor_refs = [
            f"domain:{item.domain_id}:v{item.version}:{item.lifecycle}"
            for item in domain_records
        ]
        descriptor_refs.extend(
            f"block:{item.block_template_id}:v{item.version}:{item.lifecycle}"
            for item in block_records
        )
        descriptor_refs.extend(
            f"worker:{item.worker_id}:v{item.version}:{item.lifecycle}"
            for item in worker_records
        )
        descriptor_key = ",".join(sorted(descriptor_refs))
        return f"{registry.version}+persistent:{descriptor_key}"

    def _next_version(
        self,
        record_type: type[_RecordT],
        *,
        id_attr: str,
        id_value: str,
    ) -> int:
        normalized = _normalize_key(id_value)
        records = self._session.exec(select(record_type)).all()
        current_versions = [
            record.version
            for record in records
            if _normalize_key(str(getattr(record, id_attr))) == normalized
        ]
        return max(current_versions, default=0) + 1

    def _require_mode_profile(self, profile_id: str) -> MemoryModeProfileRecord:
        record = self._session.get(
            MemoryModeProfileRecord,
            _require_key(profile_id, "profile_id"),
        )
        if record is None:
            raise MemoryRegistryManagementServiceError(
                "memory_mode_profile_not_found",
                profile_id,
            )
        return record


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower()


def _require_key(value: str, field_name: str) -> str:
    normalized = _normalize_key(value)
    if not normalized:
        raise MemoryRegistryManagementServiceError(
            "memory_registry_invalid_key",
            field_name,
        )
    return normalized


def _normalize_actor(actor: str) -> str:
    return str(actor or "").strip() or "system"
