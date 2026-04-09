"""Persistent backend registry for model metadata."""
from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from config import get_settings
from models.model_registry import ModelRegistryEntry


class ModelRegistryService:
    """Persist model configs so backend can become the runtime model source."""

    def __init__(self, *, storage_path: Path | None = None):
        settings = get_settings()
        self._storage_path = storage_path or (settings.storage_dir / "models.json")
        self._lock = RLock()

    def list_entries(self, *, provider_id: str | None = None) -> list[ModelRegistryEntry]:
        with self._lock:
            entries = list(self._load_entries().values())
            if provider_id is None:
                return entries
            return [entry for entry in entries if entry.provider_id == provider_id]

    def get_entry(self, model_id: str) -> ModelRegistryEntry | None:
        with self._lock:
            return self._load_entries().get(model_id)

    def upsert_entry(self, entry: ModelRegistryEntry) -> ModelRegistryEntry:
        with self._lock:
            entries = self._load_entries()
            existing = entries.get(entry.id)
            stored = entry.with_timestamps(existing=existing)
            entries[stored.id] = stored
            self._save_entries(entries)
            return stored

    def delete_entry(self, model_id: str) -> bool:
        with self._lock:
            entries = self._load_entries()
            if model_id not in entries:
                return False
            del entries[model_id]
            self._save_entries(entries)
            return True

    def delete_entries_for_provider(self, provider_id: str) -> int:
        with self._lock:
            entries = self._load_entries()
            to_delete = [
                model_id
                for model_id, entry in entries.items()
                if entry.provider_id == provider_id
            ]
            for model_id in to_delete:
                del entries[model_id]
            if to_delete:
                self._save_entries(entries)
            return len(to_delete)

    def _load_entries(self) -> dict[str, ModelRegistryEntry]:
        if not self._storage_path.exists():
            return {}

        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return {}

        entries: dict[str, ModelRegistryEntry] = {}
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            entry = ModelRegistryEntry.model_validate(raw)
            entries[entry.id] = entry
        return entries

    def _save_entries(self, entries: dict[str, ModelRegistryEntry]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            entry.model_dump(mode="json")
            for entry in sorted(entries.values(), key=lambda item: item.created_at or item.updated_at)
        ]
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


_model_registry_service: ModelRegistryService | None = None


def get_model_registry_service() -> ModelRegistryService:
    global _model_registry_service
    if _model_registry_service is None:
        _model_registry_service = ModelRegistryService()
    return _model_registry_service
