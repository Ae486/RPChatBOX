"""Provider-scoped model registry endpoints."""
from fastapi import APIRouter, HTTPException

from models.model_registry import ModelRegistryEntry, ModelRegistrySummary
from services.model_capability_service import query_model_capabilities
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service

router = APIRouter()


def _ensure_provider_exists(provider_id: str) -> None:
    provider = get_provider_registry_service().get_entry(provider_id)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Provider not found: {provider_id}",
                    "code": "provider_not_found",
                }
            },
        )


@router.get("/api/providers/{provider_id}/models")
async def list_provider_models(provider_id: str):
    _ensure_provider_exists(provider_id)
    service = get_model_registry_service()
    return {
        "object": "list",
        "data": [
            ModelRegistrySummary.from_entry(entry).model_dump(mode="json")
            for entry in service.list_entries(provider_id=provider_id)
        ],
    }


@router.get("/api/providers/{provider_id}/models/{model_id}")
async def get_provider_model(provider_id: str, model_id: str):
    _ensure_provider_exists(provider_id)
    service = get_model_registry_service()
    entry = service.get_entry(model_id)
    if entry is None or entry.provider_id != provider_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Model not found: {model_id}",
                    "code": "model_not_found",
                }
            },
        )
    return ModelRegistrySummary.from_entry(entry).model_dump(mode="json")


@router.put("/api/providers/{provider_id}/models/{model_id}")
async def upsert_provider_model(
    provider_id: str,
    model_id: str,
    entry: ModelRegistryEntry,
):
    _ensure_provider_exists(provider_id)
    model_service = get_model_registry_service()
    prepared = entry.model_copy(update={"id": model_id, "provider_id": provider_id})

    # Auto-fill capabilities from LiteLLM on first registration
    existing = model_service.get_entry(model_id)
    if existing is None and prepared.capabilities == ["text"]:
        provider = get_provider_registry_service().get_entry(provider_id)
        if provider is not None:
            caps = query_model_capabilities(provider.type, prepared.model_name)
            if caps.get("known"):
                auto_caps = ["text"]
                if caps.get("function_calling"):
                    auto_caps.append("tool")
                if caps.get("vision"):
                    auto_caps.append("vision")
                if caps.get("web_search"):
                    auto_caps.append("network")
                if caps.get("audio_input") or caps.get("audio_output"):
                    auto_caps.append("audio")
                prepared = prepared.model_copy(update={"capabilities": auto_caps})

    stored = model_service.upsert_entry(prepared)
    return ModelRegistrySummary.from_entry(stored).model_dump(mode="json")


@router.delete("/api/providers/{provider_id}/models/{model_id}")
async def delete_provider_model(provider_id: str, model_id: str):
    _ensure_provider_exists(provider_id)
    service = get_model_registry_service()
    entry = service.get_entry(model_id)
    if entry is None or entry.provider_id != provider_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Model not found: {model_id}",
                    "code": "model_not_found",
                }
            },
        )
    service.delete_entry(model_id)
    return {"status": "ok", "deleted": model_id}


@router.get("/api/models/capabilities")
async def get_model_capabilities(provider_type: str, model: str):
    """Query model capabilities from LiteLLM metadata.

    Returns ``known: false`` for models not in LiteLLM's database,
    allowing clients to fall back to user-configured capabilities.
    """
    return query_model_capabilities(provider_type, model)
