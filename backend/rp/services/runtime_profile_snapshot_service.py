"""Persistent runtime profile snapshot compilation and activation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import desc
from sqlmodel import Session, select

from models.rp_story_store import RuntimeProfileSnapshotRecord, StorySessionRecord
from rp.models.memory_contract_registry import MemoryLifecycleState
from rp.models.runtime_identity import (
    RuntimeProfileModeProfile,
    RuntimeProfileSnapshotCompiledProfile,
    RuntimeProfileSnapshotStatus,
    RuntimeWorkerActivation,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig
from rp.services.memory_contract_registry import MemoryContractRegistryService
from rp.services.memory_registry_management_service import (
    MemoryRegistryManagementService,
)
from rp.services.retrieval_runtime_config_service import RetrievalRuntimeConfigService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeProfileSnapshotServiceError(ValueError):
    """Stable runtime-profile error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RuntimeProfileSnapshotService:
    """Compile, publish, and resolve immutable runtime profile snapshots."""

    def __init__(
        self,
        session: Session,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        registry_management_service: MemoryRegistryManagementService | None = None,
        retrieval_runtime_config_service: RetrievalRuntimeConfigService | None = None,
    ) -> None:
        self._session = session
        self._registry_service = registry_service
        self._registry_management_service = (
            registry_management_service
            if registry_management_service is not None
            else MemoryRegistryManagementService(session)
        )
        self._retrieval_runtime_config_service = (
            retrieval_runtime_config_service or RetrievalRuntimeConfigService(session)
        )

    def compile_snapshot(
        self,
        *,
        story_id: str,
        session_id: str,
        mode: str,
        created_from: str,
        profile_config: dict[str, Any] | None = None,
    ) -> RuntimeProfileSnapshotRecord:
        session_record = self._require_session_record(session_id)
        if session_record.story_id != story_id:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_compile_failed",
                f"story_id_mismatch:{story_id}",
            )
        if session_record.mode != mode:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_compile_failed",
                f"mode_mismatch:{mode}",
            )

        effective_profile_config = profile_config or self._profile_config_for_mode(
            session_record.mode
        )
        compiled = self._compile_profile(
            session_record,
            profile_config=effective_profile_config,
        )
        record = self._create_snapshot_record(
            session_record=session_record,
            compiled=compiled,
            created_from=str(created_from or "runtime_profile_snapshot.compile"),
            profile_config=effective_profile_config,
        )
        return record

    def publish_snapshot(self, snapshot_id: str) -> RuntimeProfileSnapshotRecord:
        record = self.require_snapshot(snapshot_id)
        if record.status == RuntimeProfileSnapshotStatus.ACTIVE.value:
            return record

        now = _utcnow()
        active_rows = self._session.exec(
            select(RuntimeProfileSnapshotRecord)
            .where(RuntimeProfileSnapshotRecord.session_id == record.session_id)
            .where(
                RuntimeProfileSnapshotRecord.status
                == RuntimeProfileSnapshotStatus.ACTIVE.value
            )
        ).all()
        for active in active_rows:
            if active.runtime_profile_snapshot_id == record.runtime_profile_snapshot_id:
                continue
            active.status = RuntimeProfileSnapshotStatus.SUPERSEDED.value
            active.superseded_at = now
            self._session.add(active)

        record.status = RuntimeProfileSnapshotStatus.ACTIVE.value
        record.activated_at = now
        record.superseded_at = None
        self._session.add(record)
        self._session.flush()
        return record

    def require_snapshot(self, snapshot_id: str) -> RuntimeProfileSnapshotRecord:
        record = self._session.get(RuntimeProfileSnapshotRecord, snapshot_id)
        if record is None:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_not_found",
                snapshot_id,
            )
        return record

    def require_active_snapshot(
        self,
        *,
        session_id: str,
    ) -> RuntimeProfileSnapshotRecord:
        record = self._session.exec(
            select(RuntimeProfileSnapshotRecord)
            .where(RuntimeProfileSnapshotRecord.session_id == session_id)
            .where(
                RuntimeProfileSnapshotRecord.status
                == RuntimeProfileSnapshotStatus.ACTIVE.value
            )
            .order_by(desc(RuntimeProfileSnapshotRecord.activated_at))
            .order_by(desc(RuntimeProfileSnapshotRecord.created_at))
        ).first()
        if record is None:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_no_active_snapshot",
                session_id,
            )
        return record

    def ensure_active_snapshot(
        self,
        *,
        session_id: str,
        created_from: str,
    ) -> RuntimeProfileSnapshotRecord:
        session_record = self._require_session_record(session_id)
        profile_config = self._profile_config_for_mode(session_record.mode)
        compiled = self._compile_profile(
            session_record,
            profile_config=profile_config,
        )
        source_config_revision = self._source_config_revision(
            session_record=session_record,
            compiled=compiled,
            profile_config=profile_config,
        )
        try:
            active = self.require_active_snapshot(session_id=session_id)
        except RuntimeProfileSnapshotServiceError as exc:
            if exc.code != "runtime_profile_snapshot_no_active_snapshot":
                raise
        else:
            if active.source_config_revision == source_config_revision:
                return active

        record = self._create_snapshot_record(
            session_record=session_record,
            compiled=compiled,
            created_from=created_from,
            profile_config=profile_config,
            source_config_revision=source_config_revision,
        )
        return self.publish_snapshot(record.runtime_profile_snapshot_id)

    def _compile_profile(
        self,
        session_record: StorySessionRecord,
        *,
        profile_config: dict[str, Any] | None = None,
    ) -> RuntimeProfileSnapshotCompiledProfile:
        normalized_mode = str(session_record.mode or "").strip().lower()
        runtime_story_config = dict(session_record.runtime_story_config_json or {})
        retrieval_policy = (
            self._retrieval_runtime_config_service.resolve_session_config(
                session_id=session_record.session_id
            )
        )
        profile_config = dict(profile_config or {})
        retrieval_policy = self._profile_retrieval_policy(
            retrieval_policy=retrieval_policy,
            profile_config=profile_config,
        )
        registry_service = self._effective_registry_service()
        registry_version = registry_service.registry_version()

        all_domains = registry_service.list_domains(include_hidden=True)
        domain_activation: dict[str, dict[str, object]] = {}
        block_activation: dict[str, dict[str, object]] = {}
        permission_profile_domains: dict[str, dict[str, object]] = {}
        domain_overrides = _dict_section(profile_config, "domain_overrides")
        block_overrides = _dict_section(profile_config, "block_overrides")

        for domain in all_domains:
            defaults = domain.mode_defaults.get(normalized_mode)
            is_active = bool(
                domain.lifecycle.value == "active" and defaults and defaults.active
            )
            domain_payload: dict[str, object] = {
                "active": is_active,
                "ui_visible": bool(defaults and defaults.ui_visible),
                "allowed_layers": list(domain.allowed_layers),
                "lifecycle": domain.lifecycle.value,
            }
            domain_payload = _merge_dict(
                domain_payload,
                _dict_section(domain_overrides, domain.domain_id),
            )
            if domain.lifecycle != MemoryLifecycleState.ACTIVE:
                domain_payload["active"] = False
                domain_payload["ui_visible"] = False
            domain_activation[domain.domain_id] = domain_payload
            permission_profile_domains[domain.domain_id] = _merge_dict(
                domain.permission_defaults.model_dump(mode="json"),
                dict(defaults.permission_overrides if defaults else {}),
            )
            for template in registry_service.list_block_templates(
                domain_id=domain.domain_id
            ):
                template_payload: dict[str, object] = {
                    "active": bool(domain_payload.get("active", False)),
                    "domain_id": domain.domain_id,
                    "layer": template.layer,
                    "ui_visible": template.ui_visible,
                    "allowed_operations": list(template.allowed_operations),
                    "permission_defaults": template.permission_defaults.model_dump(
                        mode="json"
                    ),
                }
                block_activation[template.block_template_id] = _merge_dict(
                    template_payload,
                    _dict_section(block_overrides, template.block_template_id),
                )
                if (
                    domain.lifecycle != MemoryLifecycleState.ACTIVE
                    or template.lifecycle != MemoryLifecycleState.ACTIVE
                    or not bool(domain_payload.get("active", False))
                ):
                    block_activation[template.block_template_id]["active"] = False

        worker_activation: dict[str, RuntimeWorkerActivation] = {}
        worker_permission_defaults: dict[str, dict[str, Any]] = {}
        worker_overrides = _dict_section(profile_config, "worker_overrides")
        for worker in registry_service.list_workers(include_hidden=True):
            defaults = worker.mode_defaults.get(normalized_mode)
            is_active = bool(
                worker.lifecycle.value == "active" and defaults and defaults.active
            )
            metadata = _merge_dict(
                dict(worker.metadata or {}),
                dict(defaults.metadata if defaults else {}),
            )
            is_active = self._apply_worker_activation_policy(
                is_active=is_active,
                metadata=metadata,
                retrieval_policy=retrieval_policy,
            )
            worker_payload: dict[str, Any] = {
                "active": is_active,
                "profile_ref": defaults.profile_ref if defaults else None,
                "metadata": metadata,
            }
            worker_payload = _merge_dict(
                worker_payload,
                _dict_section(worker_overrides, worker.worker_id),
            )
            if worker.lifecycle != MemoryLifecycleState.ACTIVE:
                worker_payload["active"] = False
            worker_activation[worker.worker_id] = (
                RuntimeWorkerActivation.model_validate(worker_payload)
            )
            worker_permission_defaults[worker.worker_id] = _merge_dict(
                dict(worker.permission_defaults or {}),
                dict(defaults.permission_defaults if defaults else {}),
            )

        return RuntimeProfileSnapshotCompiledProfile(
            mode_profile=RuntimeProfileModeProfile(
                mode=normalized_mode,
                registry_version=registry_version,
                mode_profile_ref=_optional_text(profile_config.get("mode_profile_ref")),
                mode_profile_version=_optional_int(
                    profile_config.get("mode_profile_version")
                ),
                model_profile_ref=_optional_text(
                    runtime_story_config.get("model_profile_ref")
                ),
                worker_profile_ref=_optional_text(
                    runtime_story_config.get("worker_profile_ref")
                ),
            ),
            domain_activation=domain_activation,
            block_activation=block_activation,
            worker_activation=worker_activation,
            permission_profile=_merge_dict(
                {
                    "registry_version": registry_version,
                    "domain_defaults": permission_profile_domains,
                    "worker_defaults": worker_permission_defaults,
                },
                _dict_section(profile_config, "permission_profile"),
            ),
            retrieval_policy=retrieval_policy,
            context_policy=_merge_dict(
                {
                    "pin_scope": "turn",
                    "block_prompt_overlay": True,
                    "consumer_keys": [
                        "story.orchestrator",
                        "story.specialist",
                        "story.writer_packet",
                    ],
                },
                _dict_section(profile_config, "context_policy"),
            ),
            packet_policy=_merge_dict(
                {
                    "builder": "WritingPacketBuilder",
                    "stable_boundary": True,
                    "identity_metadata_fields": [
                        "branch_head_id",
                        "turn_id",
                        "runtime_profile_snapshot_id",
                    ],
                },
                _dict_section(profile_config, "packet_policy"),
            ),
            writer_model_profile=_merge_dict(
                {
                    "model_profile_ref": _optional_text(
                        runtime_story_config.get("model_profile_ref")
                    ),
                    "resolution_mode": "request_supplied_model",
                },
                _dict_section(profile_config, "writer_model_profile"),
            ),
            worker_model_profiles=_merge_dict(
                self._worker_model_profiles(
                    worker_activation=worker_activation,
                    runtime_story_config=runtime_story_config,
                ),
                _dict_section(profile_config, "worker_model_profiles"),
            ),
            mode_specific_settings=_merge_dict(
                {
                    "story_id": session_record.story_id,
                    "post_write_policy_preset": _optional_text(
                        runtime_story_config.get("post_write_policy_preset")
                    ),
                    "mode_profile_ref": _optional_text(
                        profile_config.get("mode_profile_ref")
                    ),
                    "mode_profile_version": _optional_int(
                        profile_config.get("mode_profile_version")
                    ),
                },
                _dict_section(profile_config, "mode_specific_settings"),
            ),
        )

    def _create_snapshot_record(
        self,
        *,
        session_record: StorySessionRecord,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        created_from: str,
        profile_config: dict[str, Any] | None = None,
        source_config_revision: str | None = None,
    ) -> RuntimeProfileSnapshotRecord:
        now = _utcnow()
        record = RuntimeProfileSnapshotRecord(
            runtime_profile_snapshot_id=uuid4().hex,
            story_id=session_record.story_id,
            session_id=session_record.session_id,
            mode=session_record.mode,
            source_config_revision=source_config_revision
            or self._source_config_revision(
                session_record=session_record,
                compiled=compiled,
                profile_config=profile_config,
            ),
            compiled_profile_json=compiled.model_dump(mode="json"),
            created_from=created_from,
            status=RuntimeProfileSnapshotStatus.DRAFT.value,
            created_at=now,
            activated_at=None,
            superseded_at=None,
        )
        self._session.add(record)
        self._session.flush()
        return record

    @staticmethod
    def _source_config_revision(
        *,
        session_record: StorySessionRecord,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        profile_config: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "story_id": session_record.story_id,
            "mode": session_record.mode,
            "runtime_story_config": session_record.runtime_story_config_json or {},
            "profile_config": profile_config or {},
            "compiled_profile": compiled.model_dump(mode="json"),
        }
        digest = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"sha1:{digest[:16]}"

    def _require_session_record(self, session_id: str) -> StorySessionRecord:
        record = self._session.get(StorySessionRecord, session_id)
        if record is None:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_compile_failed",
                f"story_session_not_found:{session_id}",
            )
        return record

    def _effective_registry_service(self) -> MemoryContractRegistryService:
        if self._registry_service is not None:
            return self._registry_service
        return self._registry_management_service.registry_service()

    def _profile_config_for_mode(self, mode: str) -> dict[str, Any] | None:
        if self._registry_service is not None:
            return None
        return self._registry_management_service.get_active_mode_profile_config(
            mode=mode
        )

    @staticmethod
    def _profile_retrieval_policy(
        *,
        retrieval_policy: RetrievalRuntimeConfig,
        profile_config: dict[str, Any],
    ) -> RetrievalRuntimeConfig:
        payload = _dict_section(profile_config, "retrieval_policy")
        if not payload:
            return retrieval_policy
        override = RetrievalRuntimeConfig.model_validate(payload)
        return retrieval_policy.overlay(override=override)

    @staticmethod
    def _apply_worker_activation_policy(
        *,
        is_active: bool,
        metadata: dict[str, Any],
        retrieval_policy: RetrievalRuntimeConfig,
    ) -> bool:
        activation_policy = metadata.get("activation_policy")
        if not isinstance(activation_policy, dict):
            return is_active
        retrieval_field = _optional_text(
            activation_policy.get("retrieval_policy_field")
        )
        if retrieval_field is None:
            return is_active
        return is_active and bool(getattr(retrieval_policy, retrieval_field, False))

    @staticmethod
    def _worker_model_profiles(
        *,
        worker_activation: dict[str, RuntimeWorkerActivation],
        runtime_story_config: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        session_worker_profile_ref = _optional_text(
            runtime_story_config.get("worker_profile_ref")
        )
        profiles: dict[str, dict[str, Any]] = {}
        for worker_id, activation in worker_activation.items():
            profile_ref = activation.profile_ref or session_worker_profile_ref
            if profile_ref is not None or worker_id in {"orchestrator", "specialist"}:
                profiles[worker_id] = {"worker_profile_ref": profile_ref}
        return profiles


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return int(normalized)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _dict_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _merge_dict(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged
