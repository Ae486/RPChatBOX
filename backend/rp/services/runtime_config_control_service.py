"""Runtime config control-plane publish service."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
from uuid import uuid4

from sqlalchemy import asc
from sqlmodel import Session, select

from models.rp_story_store import (
    RuntimeConfigControlReceiptRecord,
    RuntimeProfileSnapshotRecord,
    StorySessionRecord,
)
from rp.models.runtime_config_contracts import (
    RuntimeConfigControlReceipt,
    RuntimeConfigPatchRequest,
    RuntimeConfigPreview,
)
from rp.services.memory_contract_registry import MemoryContractRegistryError
from rp.services.memory_registry_management_service import (
    MemoryRegistryManagementService,
)
from rp.services.runtime_profile_snapshot_service import (
    RuntimeProfileSnapshotService,
    RuntimeProfileSnapshotServiceError,
)
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service


_PERMISSION_LEVELS: set[str] = {
    "observe",
    "suggest",
    "propose",
    "maintain_projection",
    "trusted_maintainer",
}

_STRUCTURED_PATCH_FIELDS: tuple[str, ...] = (
    "worker_overrides",
    "permission_overrides",
    "retrieval_policy_patch",
    "context_policy_patch",
    "packet_policy_patch",
    "model_profile_patch",
    "scheduling_policy_patch",
    "budget_latency_policy_patch",
)

_RETRIEVAL_MODEL_PROVIDER_PAIRS: tuple[tuple[str, str], ...] = (
    ("retrieval_embedding_model_id", "retrieval_embedding_provider_id"),
    ("retrieval_rerank_model_id", "retrieval_rerank_provider_id"),
    ("graph_extraction_model_id", "graph_extraction_provider_id"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeConfigControlServiceError(ValueError):
    """Stable runtime-config error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RuntimeConfigControlService:
    """Validate, publish, and audit runtime control-plane config changes."""

    def __init__(
        self,
        session: Session,
        *,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
        registry_management_service: MemoryRegistryManagementService | None = None,
        model_registry_service: Any | None = None,
        provider_registry_service: Any | None = None,
    ) -> None:
        self._session = session
        self._runtime_profile_snapshot_service = (
            runtime_profile_snapshot_service
            if runtime_profile_snapshot_service is not None
            else RuntimeProfileSnapshotService(session)
        )
        self._registry_management_service = (
            registry_management_service
            if registry_management_service is not None
            else MemoryRegistryManagementService(session)
        )
        self._model_registry_service = (
            model_registry_service
            if model_registry_service is not None
            else get_model_registry_service()
        )
        self._provider_registry_service = (
            provider_registry_service
            if provider_registry_service is not None
            else get_provider_registry_service()
        )

    def preview_patch(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> RuntimeConfigPreview:
        session_record = self._require_session_record(request.session_id)
        active_snapshot = self._active_snapshot(session_id=session_record.session_id)
        next_config, changed_fields = self._validated_next_config(
            session_record=session_record,
            request=request,
        )
        return RuntimeConfigPreview(
            session_id=session_record.session_id,
            previous_snapshot_id=active_snapshot.runtime_profile_snapshot_id,
            changed_fields=changed_fields,
            next_runtime_story_config=next_config,
        )

    def publish_patch(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> RuntimeConfigControlReceipt:
        session_record = self._require_session_record(request.session_id)
        next_config, changed_fields = self._validated_next_config(
            session_record=session_record,
            request=request,
        )
        if not changed_fields:
            raise RuntimeConfigControlServiceError(
                "runtime_config_patch_empty",
                session_record.session_id,
            )
        active_snapshot = self._active_snapshot(session_id=session_record.session_id)
        expected_snapshot_id = _optional_text(request.expected_active_snapshot_id)
        if (
            expected_snapshot_id is not None
            and expected_snapshot_id != active_snapshot.runtime_profile_snapshot_id
        ):
            raise RuntimeConfigControlServiceError(
                "runtime_config_snapshot_conflict",
                expected_snapshot_id,
            )

        previous_config = dict(session_record.runtime_story_config_json or {})
        try:
            now = _utcnow()
            session_record.runtime_story_config_json = next_config
            session_record.updated_at = now
            self._session.add(session_record)
            self._session.flush()

            compiled = self._runtime_profile_snapshot_service.compile_snapshot_from_runtime_config_patch(
                story_id=session_record.story_id,
                session_id=session_record.session_id,
                mode=session_record.mode,
                base_snapshot_id=active_snapshot.runtime_profile_snapshot_id,
                runtime_story_config=next_config,
                created_from="story_runtime.runtime_config_control.publish",
            )
            published = self._runtime_profile_snapshot_service.publish_snapshot(
                compiled.runtime_profile_snapshot_id
            )
            receipt = self._write_receipt(
                session_record=session_record,
                previous_snapshot=active_snapshot,
                published_snapshot=published,
                changed_fields=changed_fields,
                request=request,
                previous_config=previous_config,
                created_at=now,
            )
            self._session.flush()
            return receipt
        except RuntimeConfigControlServiceError:
            self._session.rollback()
            raise
        except (RuntimeProfileSnapshotServiceError, ValueError) as exc:
            self._session.rollback()
            raise RuntimeConfigControlServiceError(
                "runtime_config_compile_failed",
                str(exc),
            ) from exc

    def list_control_history(
        self,
        *,
        session_id: str,
    ) -> list[RuntimeConfigControlReceipt]:
        self._require_session_record(session_id)
        rows = self._session.exec(
            select(RuntimeConfigControlReceiptRecord)
            .where(RuntimeConfigControlReceiptRecord.session_id == session_id)
            .order_by(asc(RuntimeConfigControlReceiptRecord.created_at))
            .order_by(asc(RuntimeConfigControlReceiptRecord.receipt_id))
        ).all()
        return [self._record_to_receipt(row) for row in rows]

    def _validated_next_config(
        self,
        *,
        session_record: StorySessionRecord,
        request: RuntimeConfigPatchRequest,
    ) -> tuple[dict[str, Any], list[str]]:
        patch = self._normalized_patch_payload(request)
        if not patch:
            raise RuntimeConfigControlServiceError(
                "runtime_config_patch_empty",
                session_record.session_id,
            )
        self._validate_patch(patch)
        current = dict(session_record.runtime_story_config_json or {})
        next_config = _deep_merge(current, patch)
        changed_fields = _changed_fields(current=current, patch=patch)
        return next_config, changed_fields

    def _normalized_patch_payload(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if request.runtime_story_config:
            patch = _deep_merge(patch, dict(request.runtime_story_config))
        for field_name in _STRUCTURED_PATCH_FIELDS:
            value = getattr(request, field_name)
            if isinstance(value, dict) and value:
                patch[field_name] = dict(value)
        return patch

    def _validate_patch(self, patch: dict[str, Any]) -> None:
        registry_service = self._registry_management_service.registry_service()
        self._validate_worker_overrides(
            patch.get("worker_overrides"),
            registry_service=registry_service,
        )
        self._validate_permission_overrides(
            patch.get("permission_overrides"),
            registry_service=registry_service,
        )
        self._validate_model_profile_patch(patch.get("model_profile_patch"))
        self._validate_retrieval_model_refs(patch)
        self._validate_budget_sections(patch)

    def _validate_worker_overrides(
        self,
        payload: object,
        *,
        registry_service: Any,
    ) -> None:
        if payload is None:
            return
        if not isinstance(payload, dict):
            raise RuntimeConfigControlServiceError(
                "runtime_config_unknown_worker",
                "worker_overrides_not_object",
            )
        for worker_id, value in payload.items():
            self._require_worker(worker_id, registry_service=registry_service)
            if value is not None and not isinstance(value, dict):
                raise RuntimeConfigControlServiceError(
                    "runtime_config_unknown_worker",
                    str(worker_id),
                )

    def _validate_permission_overrides(
        self,
        payload: object,
        *,
        registry_service: Any,
    ) -> None:
        if payload is None:
            return
        if not isinstance(payload, dict):
            raise RuntimeConfigControlServiceError(
                "runtime_config_invalid_permission_level",
                "permission_overrides_not_object",
            )
        for key, value in payload.items():
            normalized_key = _normalize_key(str(key))
            if normalized_key in {"workers", "worker_overrides"}:
                self._validate_permission_workers(value, registry_service)
                continue
            if normalized_key in {"domains", "domain_overrides"}:
                self._validate_permission_domains(value, registry_service)
                continue
            if self._has_worker(str(key), registry_service=registry_service):
                self._validate_permission_worker_payload(value, registry_service)
                continue
            self._require_domain(str(key), registry_service=registry_service)
            self._validate_permission_levels(value)
        self._validate_permission_levels(payload)

    def _validate_permission_workers(
        self,
        payload: object,
        registry_service: Any,
    ) -> None:
        if not isinstance(payload, dict):
            raise RuntimeConfigControlServiceError(
                "runtime_config_unknown_worker",
                "workers_not_object",
            )
        for worker_id, value in payload.items():
            self._require_worker(worker_id, registry_service=registry_service)
            self._validate_permission_worker_payload(value, registry_service)

    def _validate_permission_worker_payload(
        self,
        payload: object,
        registry_service: Any,
    ) -> None:
        if not isinstance(payload, dict):
            self._validate_permission_levels(payload)
            return
        domains = payload.get("domains") or payload.get("domain_overrides")
        if domains is not None:
            self._validate_permission_domains(domains, registry_service)
        self._validate_permission_levels(payload)

    def _validate_permission_domains(
        self,
        payload: object,
        registry_service: Any,
    ) -> None:
        if not isinstance(payload, dict):
            raise RuntimeConfigControlServiceError(
                "runtime_config_unknown_domain",
                "domains_not_object",
            )
        for domain_id, value in payload.items():
            self._require_domain(domain_id, registry_service=registry_service)
            self._validate_permission_levels(value)

    def _validate_permission_levels(self, payload: object) -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized_key = _normalize_key(str(key))
                if normalized_key in {"level", "permission_level"} or (
                    normalized_key.endswith("_level")
                ):
                    self._require_permission_level(value)
                else:
                    self._validate_permission_levels(value)
        elif isinstance(payload, list):
            for item in payload:
                self._validate_permission_levels(item)

    def _require_permission_level(self, value: object) -> None:
        normalized = _normalize_key(str(value or ""))
        if normalized not in _PERMISSION_LEVELS:
            raise RuntimeConfigControlServiceError(
                "runtime_config_invalid_permission_level",
                str(value),
            )

    def _validate_model_profile_patch(self, payload: object) -> None:
        if payload is None:
            return
        if not isinstance(payload, dict):
            raise RuntimeConfigControlServiceError(
                "runtime_config_invalid_model_profile",
                "model_profile_patch_not_object",
            )
        self._validate_model_refs_recursive(payload)

    def _validate_retrieval_model_refs(self, patch: dict[str, Any]) -> None:
        for model_key, provider_key in _RETRIEVAL_MODEL_PROVIDER_PAIRS:
            self._validate_model_provider_pair(
                model_id=_optional_text(patch.get(model_key)),
                provider_id=_optional_text(patch.get(provider_key)),
            )
        retrieval_patch = patch.get("retrieval_policy_patch")
        if isinstance(retrieval_patch, dict):
            self._validate_model_provider_pair(
                model_id=_optional_text(retrieval_patch.get("embedding_model_id")),
                provider_id=_optional_text(
                    retrieval_patch.get("embedding_provider_id")
                ),
            )
            self._validate_model_provider_pair(
                model_id=_optional_text(retrieval_patch.get("rerank_model_id")),
                provider_id=_optional_text(retrieval_patch.get("rerank_provider_id")),
            )
            self._validate_model_provider_pair(
                model_id=_optional_text(
                    retrieval_patch.get("graph_extraction_model_id")
                ),
                provider_id=_optional_text(
                    retrieval_patch.get("graph_extraction_provider_id")
                ),
            )

    def _validate_model_refs_recursive(self, payload: object) -> None:
        if isinstance(payload, dict):
            model_id = _optional_text(payload.get("model_id"))
            provider_id = _optional_text(payload.get("provider_id"))
            if model_id is not None or provider_id is not None:
                self._validate_model_provider_pair(
                    model_id=model_id,
                    provider_id=provider_id,
                )
            for key, value in payload.items():
                key_text = str(key)
                if key_text.endswith("_model_id"):
                    prefix = key_text[: -len("_model_id")]
                    self._validate_model_provider_pair(
                        model_id=_optional_text(value),
                        provider_id=_optional_text(payload.get(f"{prefix}_provider_id")),
                    )
                    continue
                if isinstance(value, (dict, list)):
                    self._validate_model_refs_recursive(value)
        elif isinstance(payload, list):
            for item in payload:
                self._validate_model_refs_recursive(item)

    def _validate_model_provider_pair(
        self,
        *,
        model_id: str | None,
        provider_id: str | None,
    ) -> None:
        provider = None
        if provider_id is not None:
            provider = self._provider_registry_service.get_entry(provider_id)
            if provider is None or not bool(getattr(provider, "is_enabled", True)):
                raise RuntimeConfigControlServiceError(
                    "runtime_config_invalid_model_profile",
                    f"provider:{provider_id}",
                )
        if model_id is None:
            return
        model = self._model_registry_service.get_entry(model_id)
        if model is None or not bool(getattr(model, "is_enabled", True)):
            raise RuntimeConfigControlServiceError(
                "runtime_config_invalid_model_profile",
                f"model:{model_id}",
            )
        model_provider_id = _optional_text(getattr(model, "provider_id", None))
        if provider_id is not None and model_provider_id != provider_id:
            raise RuntimeConfigControlServiceError(
                "runtime_config_invalid_model_profile",
                f"model_provider_mismatch:{model_id}",
            )
        if provider is None and model_provider_id is not None:
            provider = self._provider_registry_service.get_entry(model_provider_id)
            if provider is None or not bool(getattr(provider, "is_enabled", True)):
                raise RuntimeConfigControlServiceError(
                    "runtime_config_invalid_model_profile",
                    f"provider:{model_provider_id}",
                )

    def _validate_budget_sections(self, patch: dict[str, Any]) -> None:
        for key in (
            "context_policy_patch",
            "packet_policy_patch",
            "scheduling_policy_patch",
            "budget_latency_policy_patch",
        ):
            self._validate_budget_payload(patch.get(key))

    def _validate_budget_payload(self, payload: object) -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                key_text = _normalize_key(str(key))
                if any(
                    marker in key_text
                    for marker in (
                        "budget",
                        "token",
                        "window",
                        "limit",
                        "max_",
                        "timeout",
                        "_ms",
                        "frequency",
                        "interval",
                    )
                ):
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise RuntimeConfigControlServiceError(
                            "runtime_config_invalid_budget",
                            str(key),
                        )
                    if key_text.startswith("max_") and value == 0:
                        raise RuntimeConfigControlServiceError(
                            "runtime_config_invalid_budget",
                            str(key),
                        )
                else:
                    self._validate_budget_payload(value)
        elif isinstance(payload, list):
            for item in payload:
                self._validate_budget_payload(item)

    def _require_worker(self, worker_id: object, *, registry_service: Any) -> None:
        try:
            registry_service.require_worker(str(worker_id))
        except MemoryContractRegistryError as exc:
            raise RuntimeConfigControlServiceError(
                "runtime_config_unknown_worker",
                str(worker_id),
            ) from exc

    def _has_worker(self, worker_id: str, *, registry_service: Any) -> bool:
        return registry_service.get_worker(worker_id) is not None

    def _require_domain(self, domain_id: object, *, registry_service: Any) -> None:
        try:
            registry_service.require_domain(str(domain_id))
        except MemoryContractRegistryError as exc:
            raise RuntimeConfigControlServiceError(
                "runtime_config_unknown_domain",
                str(domain_id),
            ) from exc

    def _require_session_record(self, session_id: str | None) -> StorySessionRecord:
        normalized_session_id = _optional_text(session_id)
        if normalized_session_id is None:
            raise RuntimeConfigControlServiceError(
                "runtime_config_patch_empty",
                "session_id",
            )
        record = self._session.get(StorySessionRecord, normalized_session_id)
        if record is None:
            raise RuntimeConfigControlServiceError(
                "story_session_not_found",
                normalized_session_id,
            )
        return record

    def _active_snapshot(
        self,
        *,
        session_id: str,
    ) -> RuntimeProfileSnapshotRecord:
        try:
            return self._runtime_profile_snapshot_service.require_active_snapshot(
                session_id=session_id
            )
        except RuntimeProfileSnapshotServiceError as exc:
            if exc.code == "runtime_profile_snapshot_no_active_snapshot":
                return self._runtime_profile_snapshot_service.ensure_active_snapshot(
                    session_id=session_id,
                    created_from="runtime_config_control.ensure_previous_active",
                )
            raise RuntimeConfigControlServiceError(exc.code, str(exc)) from exc

    def _write_receipt(
        self,
        *,
        session_record: StorySessionRecord,
        previous_snapshot: RuntimeProfileSnapshotRecord,
        published_snapshot: RuntimeProfileSnapshotRecord,
        changed_fields: list[str],
        request: RuntimeConfigPatchRequest,
        previous_config: dict[str, Any],
        created_at: datetime,
    ) -> RuntimeConfigControlReceipt:
        metadata = {
            **dict(request.metadata_json or {}),
            "previous_runtime_story_config": previous_config,
            "runtime_config_contract": "control_plane_snapshot_publish",
        }
        record = RuntimeConfigControlReceiptRecord(
            receipt_id=f"runtime-config:{uuid4().hex}",
            story_id=session_record.story_id,
            session_id=session_record.session_id,
            previous_snapshot_id=previous_snapshot.runtime_profile_snapshot_id,
            published_snapshot_id=published_snapshot.runtime_profile_snapshot_id,
            changed_fields_json=list(changed_fields),
            actor_id=_optional_text(request.actor_id),
            source=request.source,
            reason=_optional_text(request.reason),
            metadata_json=metadata,
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._record_to_receipt(record)

    @staticmethod
    def _record_to_receipt(
        record: RuntimeConfigControlReceiptRecord,
    ) -> RuntimeConfigControlReceipt:
        return RuntimeConfigControlReceipt(
            receipt_id=record.receipt_id,
            story_id=record.story_id,
            session_id=record.session_id,
            previous_snapshot_id=record.previous_snapshot_id,
            published_snapshot_id=record.published_snapshot_id,
            changed_fields=list(record.changed_fields_json or []),
            actor_id=record.actor_id,
            source=record.source,  # type: ignore[arg-type]
            reason=record.reason,
            metadata_json=dict(record.metadata_json or {}),
            created_at=record.created_at,
        )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _changed_fields(
    *,
    current: dict[str, Any],
    patch: dict[str, Any],
    prefix: str = "",
) -> list[str]:
    changed: list[str] = []
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        current_value = current.get(key)
        if isinstance(value, dict) and isinstance(current_value, dict):
            changed.extend(
                _changed_fields(
                    current=dict(current_value),
                    patch=value,
                    prefix=path,
                )
            )
            continue
        if current_value != value:
            changed.append(path)
    return changed


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower()
