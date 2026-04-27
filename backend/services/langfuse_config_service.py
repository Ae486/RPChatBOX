"""Persistent runtime configuration for Langfuse observability."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

from config import Settings, get_settings
from models.langfuse_config import LangfuseRuntimeConfig, LangfuseSettingsPayload


class LangfuseConfigService:
    """Load and persist backend-owned Langfuse runtime settings."""

    def __init__(
        self,
        *,
        storage_path: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage_path = storage_path or (
            self._settings.storage_dir / "langfuse_settings.json"
        )
        self._lock = RLock()

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    def get_effective_config(self) -> LangfuseRuntimeConfig:
        config, _ = self.get_effective_config_with_source()
        return config

    def get_effective_config_with_source(self) -> tuple[LangfuseRuntimeConfig, str]:
        with self._lock:
            stored = self._load_stored_config()
            if stored is not None:
                return stored, "storage"
            return self._env_config(), "env"

    def upsert_config(self, payload: LangfuseSettingsPayload) -> LangfuseRuntimeConfig:
        with self._lock:
            existing = self._load_stored_config() or self._env_config()
            public_key = _normalize_optional_text(payload.public_key)
            secret_key = _normalize_optional_text(payload.secret_key)
            if payload.clear_secret_key:
                secret_key = None
            elif secret_key is None:
                secret_key = existing.secret_key
            config = LangfuseRuntimeConfig(
                enabled=bool(payload.enabled),
                public_key=public_key,
                secret_key=secret_key,
                base_url=_normalize_optional_text(payload.base_url),
                environment=_normalize_optional_text(payload.environment),
                release=_normalize_optional_text(payload.release),
                sample_rate=payload.sample_rate,
                debug=bool(payload.debug),
            )
            self._save_config(config)
            return config

    def _env_config(self) -> LangfuseRuntimeConfig:
        return LangfuseRuntimeConfig(
            enabled=bool(self._settings.langfuse_enabled),
            public_key=_normalize_optional_text(self._settings.langfuse_public_key),
            secret_key=_normalize_optional_text(self._settings.langfuse_secret_key),
            base_url=_normalize_optional_text(self._settings.langfuse_base_url),
            environment=_normalize_optional_text(self._settings.langfuse_environment),
            release=_normalize_optional_text(self._settings.langfuse_release),
            sample_rate=self._settings.langfuse_sample_rate,
            debug=bool(self._settings.langfuse_debug),
        )

    def _load_stored_config(self) -> LangfuseRuntimeConfig | None:
        if not self._storage_path.exists():
            return None
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return LangfuseRuntimeConfig.model_validate(payload)

    def _save_config(self, config: LangfuseRuntimeConfig) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@lru_cache
def get_langfuse_config_service() -> LangfuseConfigService:
    return LangfuseConfigService()


def reset_langfuse_config_service() -> None:
    get_langfuse_config_service.cache_clear()

