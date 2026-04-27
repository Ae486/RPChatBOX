"""Langfuse runtime configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from models.langfuse_config import (
    LangfuseRuntimeConfig,
    LangfuseSettingsPayload,
    LangfuseSettingsSummary,
)
from services.langfuse_config_service import get_langfuse_config_service
from services.langfuse_service import (
    get_langfuse_service,
    is_langfuse_sdk_available,
    is_langfuse_sdk_compatible,
    reset_langfuse_service,
)

router = APIRouter()


@router.get("/api/observability/langfuse")
async def get_langfuse_settings() -> dict:
    return _build_langfuse_summary().model_dump(mode="json")


@router.put("/api/observability/langfuse")
async def upsert_langfuse_settings(payload: LangfuseSettingsPayload) -> dict:
    service = get_langfuse_config_service()
    service.upsert_config(payload)
    reset_langfuse_service()
    _ = get_langfuse_service()
    return _build_langfuse_summary().model_dump(mode="json")


def _build_langfuse_summary() -> LangfuseSettingsSummary:
    config_service = get_langfuse_config_service()
    config, source = config_service.get_effective_config_with_source()
    langfuse_service = get_langfuse_service()
    status_reason = _status_reason(
        config=config,
        service_enabled=langfuse_service.enabled,
    )
    return LangfuseSettingsSummary.from_runtime_config(
        config,
        service_enabled=langfuse_service.enabled,
        sdk_available=is_langfuse_sdk_available(),
        status_reason=status_reason,
        source=source,
        config_path=(
            str(config_service.storage_path)
            if source == "storage"
            else None
        ),
    )


def _status_reason(*, config: LangfuseRuntimeConfig, service_enabled: bool) -> str:
    if not config.enabled:
        return "disabled"
    if not config.public_key or not config.secret_key:
        return "missing_api_keys"
    if not is_langfuse_sdk_available():
        return "sdk_unavailable"
    if not is_langfuse_sdk_compatible():
        return "sdk_incompatible"
    if service_enabled:
        return "active"
    return "client_init_failed"
