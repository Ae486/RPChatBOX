"""Low-risk fixture helpers for eval runs."""

from __future__ import annotations

from typing import Any

from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.models.setup_workspace import StoryMode
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service


def ensure_registry_fixtures(request_payload: dict[str, Any]) -> dict[str, str]:
    """Ensure provider/model registry fixtures exist for an eval run."""

    provider_id = str(request_payload.get("provider_id") or "provider-eval")
    model_id = str(request_payload.get("model_id") or "model-eval")

    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()

    if provider_service.get_entry(provider_id) is None:
        provider_service.upsert_entry(
            ProviderRegistryEntry(
                id=provider_id,
                name="Eval Provider",
                type=str(request_payload.get("provider_type") or "openai"),
                api_key="sk-eval-placeholder",
                api_url="https://example.com/v1",
                custom_headers={},
                is_enabled=True,
                description="Auto-created provider for RP eval runs",
            )
        )
    if model_service.get_entry(model_id) is None:
        model_service.upsert_entry(
            ModelRegistryEntry(
                id=model_id,
                provider_id=provider_id,
                model_name=str(request_payload.get("model_name") or "gpt-4o-mini"),
                display_name=str(request_payload.get("display_name") or "Eval Model"),
                capabilities=["text", "tool"],
                is_enabled=True,
                description="Auto-created model for RP eval runs",
            )
        )

    return {
        "provider_id": provider_id,
        "model_id": model_id,
    }


def normalize_story_mode(raw_mode: str | None) -> StoryMode:
    return StoryMode(str(raw_mode or StoryMode.LONGFORM.value))
