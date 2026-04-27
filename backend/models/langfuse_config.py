"""Durable Langfuse runtime configuration contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LangfuseRuntimeConfig(BaseModel):
    """Effective Langfuse runtime configuration used by the backend."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    public_key: str | None = None
    secret_key: str | None = None
    base_url: str | None = None
    environment: str | None = None
    release: str | None = None
    sample_rate: float | None = None
    debug: bool = False


class LangfuseSettingsPayload(BaseModel):
    """Frontend-facing update payload for Langfuse runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    public_key: str | None = None
    secret_key: str | None = None
    clear_secret_key: bool = False
    base_url: str | None = None
    environment: str | None = None
    release: str | None = None
    sample_rate: float | None = None
    debug: bool = False


class LangfuseSettingsSummary(BaseModel):
    """Safe summary returned to the frontend without leaking the secret key."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    configured: bool = False
    service_enabled: bool = False
    sdk_available: bool = False
    status_reason: str = "disabled"
    source: str = "env"
    public_key: str | None = None
    has_secret_key: bool = False
    base_url: str | None = None
    dashboard_url: str | None = None
    environment: str | None = None
    release: str | None = None
    sample_rate: float | None = None
    debug: bool = False
    config_path: str | None = None

    @classmethod
    def from_runtime_config(
        cls,
        config: LangfuseRuntimeConfig,
        *,
        service_enabled: bool,
        sdk_available: bool,
        status_reason: str,
        source: str,
        config_path: str | None,
    ) -> "LangfuseSettingsSummary":
        dashboard_url = (config.base_url or "https://cloud.langfuse.com").rstrip("/")
        return cls(
            enabled=config.enabled,
            configured=bool(config.public_key and config.secret_key),
            service_enabled=service_enabled,
            sdk_available=sdk_available,
            status_reason=status_reason,
            source=source,
            public_key=config.public_key,
            has_secret_key=bool(config.secret_key),
            base_url=config.base_url,
            dashboard_url=dashboard_url,
            environment=config.environment,
            release=config.release,
            sample_rate=config.sample_rate,
            debug=config.debug,
            config_path=config_path,
        )
