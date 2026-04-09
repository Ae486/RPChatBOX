"""Persistent backend provider registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock

from config import get_settings
from models.provider_registry import ProviderRegistryEntry


class ProviderRegistryService:
    """Persist provider configs so chat requests can reference them by id."""

    def __init__(self, *, storage_path: Path | None = None):
        settings = get_settings()
        self._storage_path = storage_path or (settings.storage_dir / "providers.json")
        self._lock = RLock()

    def list_entries(self) -> list[ProviderRegistryEntry]:
        """Return all stored providers."""
        with self._lock:
            return list(self._load_entries().values())

    def get_entry(self, provider_id: str) -> ProviderRegistryEntry | None:
        """Return a single provider entry by id."""
        with self._lock:
            return self._load_entries().get(provider_id)

    def upsert_entry(self, entry: ProviderRegistryEntry) -> ProviderRegistryEntry:
        """Create or update a provider entry."""
        with self._lock:
            entries = self._load_entries()
            existing = entries.get(entry.id)
            stored = entry.with_timestamps(existing=existing)
            entries[stored.id] = stored
            self._save_entries(entries)
            return stored

    def delete_entry(self, provider_id: str) -> bool:
        """Delete a provider entry if it exists."""
        with self._lock:
            entries = self._load_entries()
            if provider_id not in entries:
                return False
            del entries[provider_id]
            self._save_entries(entries)
            return True

    def _load_entries(self) -> dict[str, ProviderRegistryEntry]:
        if not self._storage_path.exists():
            return {}

        raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw_entries = raw.get("providers", [])
        else:
            raw_entries = raw

        entries = {}
        for item in raw_entries:
            entry = ProviderRegistryEntry(**item)
            entries[entry.id] = entry
        return entries

    def _save_entries(self, entries: dict[str, ProviderRegistryEntry]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@lru_cache
def get_provider_registry_service() -> ProviderRegistryService:
    """Return the singleton provider registry service."""
    return ProviderRegistryService()
