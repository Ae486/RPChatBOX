"""Provider-scoped model registry endpoints."""
from fastapi import APIRouter, HTTPException

from models.model_registry import ModelRegistryEntry, ModelRegistrySummary
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
    service = get_model_registry_service()
    stored = service.upsert_entry(
        entry.model_copy(update={"id": model_id, "provider_id": provider_id})
    )
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
