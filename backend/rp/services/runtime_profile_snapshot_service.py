"""Persistent runtime profile snapshot compilation and activation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import desc
from sqlmodel import Session, select

from models.rp_story_store import RuntimeProfileSnapshotRecord, StorySessionRecord
from rp.models.memory_contract_registry import MemoryLifecycleState
from rp.models.mode_extension_contracts import (
    build_mode_extension_profile,
    packet_sidecar_slot_ids_for_profile,
    worker_slot_ids_for_profile,
    workspace_material_slot_ids_for_profile,
)
from rp.models.post_write_policy import (
    PostWriteMaintenancePolicy,
    build_balanced_policy,
    build_conservative_policy,
)
from rp.models.runtime_identity import (
    RuntimeProfileBudgetLatencyPolicy,
    RuntimeProfileModeProfile,
    RuntimeProfileSnapshotCompiledProfile,
    RuntimeProfileSnapshotStatus,
    RuntimeProfileWriterPolicy,
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

        effective_profile_config = profile_config or self._profile_config_for_session(
            session_record
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

    def compile_snapshot_from_runtime_config_patch(
        self,
        *,
        story_id: str,
        session_id: str,
        mode: str,
        base_snapshot_id: str,
        runtime_story_config: dict[str, Any],
        created_from: str,
    ) -> RuntimeProfileSnapshotRecord:
        """Create a future-turn snapshot from the currently active snapshot.

        Runtime config publishes are control-plane hot updates. They must not
        silently rebase an existing story onto a newer active ModeProfile or
        registry default while applying a small panel patch.
        """

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
        base_snapshot = self.require_snapshot(base_snapshot_id)
        if (
            base_snapshot.story_id != story_id
            or base_snapshot.session_id != session_id
            or base_snapshot.mode != mode
        ):
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_compile_failed",
                f"base_snapshot_mismatch:{base_snapshot_id}",
            )

        base_compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
            base_snapshot.compiled_profile_json or {}
        )
        compiled = self._apply_runtime_config_patch_to_compiled_profile(
            base_compiled,
            runtime_story_config=dict(runtime_story_config or {}),
        )
        return self._create_snapshot_record(
            session_record=session_record,
            compiled=compiled,
            created_from=str(created_from or "runtime_profile_snapshot.compile"),
            profile_config={
                "base_runtime_profile_snapshot_id": base_snapshot_id,
                "runtime_story_config": dict(runtime_story_config or {}),
            },
        )

    def publish_snapshot(self, snapshot_id: str) -> RuntimeProfileSnapshotRecord:
        record = self.require_snapshot(snapshot_id)
        if record.status == RuntimeProfileSnapshotStatus.ACTIVE.value:
            self._pin_session_active_snapshot(
                session_id=record.session_id,
                snapshot_id=record.runtime_profile_snapshot_id,
            )
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
        self._pin_session_active_snapshot(
            session_id=record.session_id,
            snapshot_id=record.runtime_profile_snapshot_id,
            updated_at=now,
        )
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
        session_record = self._require_session_record(session_id)
        try:
            pinned_record = self._require_session_pinned_active_snapshot(
                session_record=session_record
            )
        except RuntimeProfileSnapshotServiceError as exc:
            active_record = self._latest_active_snapshot(session_id=session_id)
            if active_record is None:
                raise RuntimeProfileSnapshotServiceError(
                    "runtime_profile_snapshot_no_active_snapshot",
                    session_id,
                ) from exc
            self._pin_session_active_snapshot(
                session_id=session_id,
                snapshot_id=active_record.runtime_profile_snapshot_id,
            )
            return active_record
        if pinned_record is not None:
            return pinned_record

        active_record = self._latest_active_snapshot(session_id=session_id)
        if active_record is None:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_no_active_snapshot",
                session_id,
            )
        self._pin_session_active_snapshot(
            session_id=session_id,
            snapshot_id=active_record.runtime_profile_snapshot_id,
        )
        return active_record

    def ensure_active_snapshot(
        self,
        *,
        session_id: str,
        created_from: str,
    ) -> RuntimeProfileSnapshotRecord:
        session_record = self._require_session_record(session_id)
        profile_config = self._profile_config_for_session(session_record)
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
            active = self._require_session_pinned_active_snapshot(
                session_record=session_record
            )
        except RuntimeProfileSnapshotServiceError:
            active = None
        else:
            if (
                active is not None
                and active.source_config_revision == source_config_revision
            ):
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
        writer_contract = dict(session_record.writer_contract_json or {})
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
            worker_defaults = worker.mode_defaults.get(normalized_mode)
            is_active = bool(
                worker.lifecycle.value == "active"
                and worker_defaults
                and worker_defaults.active
            )
            metadata = _merge_dict(
                dict(worker.metadata or {}),
                dict(worker_defaults.metadata if worker_defaults else {}),
            )
            is_active = self._apply_worker_activation_policy(
                is_active=is_active,
                metadata=metadata,
                retrieval_policy=retrieval_policy,
            )
            worker_payload: dict[str, Any] = {
                "active": is_active,
                "profile_ref": (
                    worker_defaults.profile_ref if worker_defaults else None
                ),
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
                dict(
                    worker_defaults.permission_defaults if worker_defaults else {}
                ),
            )
        extension_profile = build_mode_extension_profile(normalized_mode)
        if extension_profile is not None:
            for runtime_worker_id in worker_slot_ids_for_profile(extension_profile):
                worker_activation[runtime_worker_id] = RuntimeWorkerActivation(
                    active=True,
                    profile_ref=_optional_text(
                        runtime_story_config.get("worker_profile_ref")
                    ),
                    metadata={
                        "extension_mode": normalized_mode,
                        "runtime_extension_worker": True,
                    },
                )
                worker_permission_defaults.setdefault(
                    runtime_worker_id,
                    {
                        "read": True,
                        "propose": True,
                        "refresh_projection": True,
                    },
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
                    "mode_sidecar_slots": packet_sidecar_slot_ids_for_profile(
                        extension_profile
                    ),
                },
                _dict_section(profile_config, "packet_policy"),
            ),
            writer_policy=self._writer_policy(
                normalized_mode=normalized_mode,
                writer_contract=writer_contract,
                profile_config=profile_config,
            ),
            post_write_policy=self._post_write_policy(
                runtime_story_config=runtime_story_config,
                profile_config=profile_config,
            ),
            budget_latency_policy=self._budget_latency_policy(
                profile_config=profile_config
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
                    "mode_extension_profile": (
                        extension_profile.model_dump(mode="json")
                        if extension_profile is not None
                        else None
                    ),
                    "workspace_material_slots": workspace_material_slot_ids_for_profile(
                        extension_profile
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
            "writer_contract": session_record.writer_contract_json or {},
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

    def _require_session_pinned_active_snapshot(
        self,
        *,
        session_record: StorySessionRecord,
    ) -> RuntimeProfileSnapshotRecord | None:
        pinned_snapshot_id = str(
            session_record.active_runtime_profile_snapshot_id or ""
        ).strip()
        if not pinned_snapshot_id:
            return None
        record = self.require_snapshot(pinned_snapshot_id)
        if record.session_id != session_record.session_id:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_activation_conflict",
                f"session_snapshot_mismatch:{session_record.session_id}",
            )
        if record.status != RuntimeProfileSnapshotStatus.ACTIVE.value:
            raise RuntimeProfileSnapshotServiceError(
                "runtime_profile_snapshot_activation_conflict",
                f"session_snapshot_not_active:{pinned_snapshot_id}",
            )
        return record

    def _latest_active_snapshot(
        self,
        *,
        session_id: str,
    ) -> RuntimeProfileSnapshotRecord | None:
        return self._session.exec(
            select(RuntimeProfileSnapshotRecord)
            .where(RuntimeProfileSnapshotRecord.session_id == session_id)
            .where(
                RuntimeProfileSnapshotRecord.status
                == RuntimeProfileSnapshotStatus.ACTIVE.value
            )
            .order_by(desc(cast(Any, RuntimeProfileSnapshotRecord.activated_at)))
            .order_by(desc(cast(Any, RuntimeProfileSnapshotRecord.created_at)))
        ).first()

    def _pin_session_active_snapshot(
        self,
        *,
        session_id: str,
        snapshot_id: str,
        updated_at: datetime | None = None,
    ) -> None:
        session_record = self._require_session_record(session_id)
        if session_record.active_runtime_profile_snapshot_id == snapshot_id:
            return
        session_record.active_runtime_profile_snapshot_id = snapshot_id
        session_record.updated_at = updated_at or _utcnow()
        self._session.add(session_record)
        self._session.flush()

    def _effective_registry_service(self) -> MemoryContractRegistryService:
        if self._registry_service is not None:
            return self._registry_service
        return self._registry_management_service.registry_service()

    def _profile_config_for_session(
        self,
        session_record: StorySessionRecord,
    ) -> dict[str, Any] | None:
        profile_config: dict[str, Any] = {}
        if self._registry_service is None:
            active_profile = (
                self._registry_management_service.get_active_mode_profile_config(
                    mode=session_record.mode
                )
            )
            if active_profile is not None:
                profile_config = dict(active_profile)

        runtime_config = dict(session_record.runtime_story_config_json or {})
        runtime_profile_config = _runtime_config_profile_sections(runtime_config)
        if runtime_profile_config:
            profile_config = _merge_dict(profile_config, runtime_profile_config)
        return profile_config or None

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
    def _apply_runtime_config_patch_to_compiled_profile(
        base_compiled: RuntimeProfileSnapshotCompiledProfile,
        *,
        runtime_story_config: dict[str, Any],
    ) -> RuntimeProfileSnapshotCompiledProfile:
        payload = base_compiled.model_dump(mode="json")
        profile_config = _runtime_config_profile_sections(runtime_story_config)

        _merge_payload_section(
            payload,
            target_key="worker_activation",
            override=_dict_section(profile_config, "worker_overrides"),
        )
        _merge_payload_section(
            payload,
            target_key="permission_profile",
            override=_dict_section(profile_config, "permission_profile"),
        )
        _merge_payload_section(
            payload,
            target_key="context_policy",
            override=_dict_section(profile_config, "context_policy"),
        )
        _merge_payload_section(
            payload,
            target_key="packet_policy",
            override=_dict_section(profile_config, "packet_policy"),
        )
        _merge_payload_section(
            payload,
            target_key="writer_model_profile",
            override=_dict_section(profile_config, "writer_model_profile"),
        )
        _merge_payload_section(
            payload,
            target_key="worker_model_profiles",
            override=_dict_section(profile_config, "worker_model_profiles"),
        )
        _merge_payload_section(
            payload,
            target_key="mode_specific_settings",
            override=_dict_section(profile_config, "mode_specific_settings"),
        )
        _merge_payload_section(
            payload,
            target_key="budget_latency_policy",
            override=_dict_section(profile_config, "budget_latency_policy"),
        )

        retrieval_override = _runtime_config_retrieval_policy(runtime_story_config)
        if retrieval_override is not None:
            base_retrieval = RetrievalRuntimeConfig.model_validate(
                payload.get("retrieval_policy") or {}
            )
            payload["retrieval_policy"] = base_retrieval.overlay(
                override=retrieval_override
            ).model_dump(mode="json")

        preset = _optional_text(runtime_story_config.get("post_write_policy_preset"))
        if preset is not None:
            policy = (
                build_conservative_policy()
                if preset == "conservative"
                else build_balanced_policy()
            )
            payload["post_write_policy"] = policy.model_dump(mode="json")
            mode_settings = dict(payload.get("mode_specific_settings") or {})
            mode_settings["post_write_policy_preset"] = preset
            payload["mode_specific_settings"] = mode_settings

        return RuntimeProfileSnapshotCompiledProfile.model_validate(payload)

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
        extension_workers = {
            worker_id
            for worker_id, activation in worker_activation.items()
            if bool(activation.metadata.get("runtime_extension_worker"))
        }
        for worker_id, activation in worker_activation.items():
            profile_ref = activation.profile_ref or session_worker_profile_ref
            if (
                profile_ref is not None
                or worker_id in {"orchestrator", "specialist"}
                or worker_id in extension_workers
            ):
                profiles[worker_id] = {"worker_profile_ref": profile_ref}
        return profiles

    @staticmethod
    def _writer_policy(
        *,
        normalized_mode: str,
        writer_contract: dict[str, Any],
        profile_config: dict[str, Any],
    ) -> RuntimeProfileWriterPolicy:
        base = RuntimeProfileWriterPolicy(
            supported_operation_modes=["writing", "rewrite", "discussion"],
            retrieval_mode="bounded_tool_loop",
            rewrite_requires_explicit_selection=(normalized_mode == "longform"),
            discussion_summary_enabled=True,
            pov_rules=_string_list(writer_contract.get("pov_rules")),
            style_rules=_string_list(writer_contract.get("style_rules")),
            writing_constraints=_string_list(
                writer_contract.get("writing_constraints")
            ),
            task_writing_rules=_string_list(
                writer_contract.get("task_writing_rules")
            ),
        )
        override = _dict_section(profile_config, "writer_policy")
        if not override:
            return base
        payload = _merge_dict(base.model_dump(mode="json"), override)
        return RuntimeProfileWriterPolicy.model_validate(payload)

    @staticmethod
    def _post_write_policy(
        *,
        runtime_story_config: dict[str, Any],
        profile_config: dict[str, Any],
    ) -> PostWriteMaintenancePolicy:
        preset = _optional_text(profile_config.get("post_write_policy_preset"))
        if preset is None:
            preset = _optional_text(runtime_story_config.get("post_write_policy_preset"))
        if preset == "conservative":
            base = build_conservative_policy()
        else:
            base = build_balanced_policy()
        override = _dict_section(profile_config, "post_write_policy")
        if not override:
            return base
        payload = _merge_dict(base.model_dump(mode="json"), override)
        return PostWriteMaintenancePolicy.model_validate(payload)

    @staticmethod
    def _budget_latency_policy(
        *,
        profile_config: dict[str, Any],
    ) -> RuntimeProfileBudgetLatencyPolicy:
        base = RuntimeProfileBudgetLatencyPolicy(
            max_blocking_analysis_workers=1,
            max_writer_workers=1,
            token_usage_source="provider_usage_metadata",
            prewrite_estimation_enabled=True,
        )
        override = _dict_section(profile_config, "budget_latency_policy")
        if not override:
            return base
        payload = _merge_dict(base.model_dump(mode="json"), override)
        return RuntimeProfileBudgetLatencyPolicy.model_validate(payload)


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


def _runtime_config_profile_sections(
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    profile_config: dict[str, Any] = {}
    for source_key, target_key in (
        ("worker_overrides", "worker_overrides"),
        ("retrieval_policy_patch", "retrieval_policy"),
        ("context_policy_patch", "context_policy"),
        ("packet_policy_patch", "packet_policy"),
        ("budget_latency_policy_patch", "budget_latency_policy"),
    ):
        section = _dict_section(runtime_config, source_key)
        if section:
            profile_config[target_key] = section

    permission_overrides = _dict_section(runtime_config, "permission_overrides")
    if permission_overrides:
        profile_config["permission_profile"] = {
            "runtime_config_overrides": permission_overrides
        }

    model_profile_patch = _dict_section(runtime_config, "model_profile_patch")
    if model_profile_patch:
        writer_profile = _dict_section(model_profile_patch, "writer_model_profile")
        if not writer_profile:
            writer_profile = _dict_section(model_profile_patch, "writer")
        if writer_profile:
            profile_config["writer_model_profile"] = writer_profile

        worker_profiles = _dict_section(model_profile_patch, "worker_model_profiles")
        if not worker_profiles:
            worker_profiles = _dict_section(model_profile_patch, "workers")
        if worker_profiles:
            profile_config["worker_model_profiles"] = worker_profiles

        remaining_model_patch = {
            key: value
            for key, value in model_profile_patch.items()
            if key
            not in {
                "writer",
                "writer_model_profile",
                "workers",
                "worker_model_profiles",
            }
        }
        if remaining_model_patch:
            profile_config["mode_specific_settings"] = _merge_dict(
                _dict_section(profile_config, "mode_specific_settings"),
                {"runtime_config_model_profile_patch": remaining_model_patch},
            )

    scheduling_policy = _dict_section(runtime_config, "scheduling_policy_patch")
    if scheduling_policy:
        profile_config["mode_specific_settings"] = _merge_dict(
            _dict_section(profile_config, "mode_specific_settings"),
            {"scheduling_policy": scheduling_policy},
        )
    return profile_config


def _runtime_config_retrieval_policy(
    runtime_config: dict[str, Any],
) -> RetrievalRuntimeConfig | None:
    values: dict[str, Any] = {}
    for target_key, source_key in (
        ("embedding_model_id", "retrieval_embedding_model_id"),
        ("embedding_provider_id", "retrieval_embedding_provider_id"),
        ("rerank_model_id", "retrieval_rerank_model_id"),
        ("rerank_provider_id", "retrieval_rerank_provider_id"),
        ("graph_extraction_provider_id", "graph_extraction_provider_id"),
        ("graph_extraction_model_id", "graph_extraction_model_id"),
        (
            "graph_extraction_structured_output_mode",
            "graph_extraction_structured_output_mode",
        ),
        ("graph_extraction_temperature", "graph_extraction_temperature"),
        (
            "graph_extraction_max_output_tokens",
            "graph_extraction_max_output_tokens",
        ),
        ("graph_extraction_timeout_ms", "graph_extraction_timeout_ms"),
        (
            "graph_extraction_fallback_model_ref",
            "graph_extraction_fallback_model_ref",
        ),
        ("graph_extraction_enabled", "graph_extraction_enabled"),
    ):
        if source_key in runtime_config and runtime_config[source_key] is not None:
            values[target_key] = runtime_config[source_key]
    if "graph_extraction_retry_policy" in runtime_config:
        raw_retry_policy = runtime_config["graph_extraction_retry_policy"]
        if raw_retry_policy is not None:
            values["graph_extraction_retry_policy"] = raw_retry_policy

    retrieval_policy_patch = _dict_section(runtime_config, "retrieval_policy_patch")
    if retrieval_policy_patch:
        values = _merge_dict(values, retrieval_policy_patch)
    if not values:
        return None
    return RetrievalRuntimeConfig.model_validate(values)


def _merge_payload_section(
    payload: dict[str, Any],
    *,
    target_key: str,
    override: dict[str, Any],
) -> None:
    if not override:
        return
    payload[target_key] = _merge_dict(dict(payload.get(target_key) or {}), override)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text is not None:
            normalized.append(text)
    return normalized


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
