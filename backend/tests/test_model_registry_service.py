import json

from models.provider_registry import ProviderRegistryEntry
from services.model_registry import ModelRegistryService
from services.provider_registry import ProviderRegistryService


def test_model_registry_service_backfills_capability_profile_for_legacy_entries(
    tmp_path,
    monkeypatch,
):
    provider_service = ProviderRegistryService(storage_path=tmp_path / "providers.json")
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id="provider-1",
            name="OpenAI",
            type="openai",
            api_key="sk-test-12345678",
            api_url="https://api.openai.com/v1",
            is_enabled=True,
        )
    )
    monkeypatch.setattr(
        "services.model_registry.get_provider_registry_service",
        lambda: provider_service,
    )

    storage_path = tmp_path / "models.json"
    storage_path.write_text(
        json.dumps(
            [
                {
                    "id": "model-1",
                    "provider_id": "provider-1",
                    "model_name": "gpt-4o-mini",
                    "display_name": "GPT-4o Mini",
                    "capabilities": ["text"],
                    "is_enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    service = ModelRegistryService(storage_path=storage_path)
    entry = service.get_entry("model-1")

    assert entry is not None
    assert entry.capability_profile is not None
    assert entry.capability_source == "litellm_metadata"
    assert entry.capability_profile.supports_function_calling is True

    payload = json.loads(storage_path.read_text(encoding="utf-8"))
    assert payload[0]["capability_profile"]["supports_function_calling"] is True
    assert payload[0]["capability_source"] == "litellm_metadata"
