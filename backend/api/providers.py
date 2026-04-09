"""Provider registry endpoints."""
from fastapi import APIRouter, HTTPException

from models.provider_registry import ProviderRegistryEntry, ProviderRegistrySummary
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service

router = APIRouter()


@router.get("/api/providers")
async def list_providers():
    """List registry-backed providers without exposing raw secrets."""
    service = get_provider_registry_service()
    return {
        "object": "list",
        "data": [
            ProviderRegistrySummary.from_entry(entry).model_dump(mode="json")
            for entry in service.list_entries()
        ],
    }


@router.get("/api/providers/{provider_id}")
async def get_provider(provider_id: str):
    """Fetch a single provider summary."""
    service = get_provider_registry_service()
    entry = service.get_entry(provider_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Provider not found: {provider_id}",
                    "code": "provider_not_found",
                }
            },
        )
    return ProviderRegistrySummary.from_entry(entry).model_dump(mode="json")


@router.put("/api/providers/{provider_id}")
async def upsert_provider(provider_id: str, entry: ProviderRegistryEntry):
    """Create or update a provider in the backend registry."""
    service = get_provider_registry_service()
    existing = service.get_entry(provider_id)
    if existing is not None and not entry.api_key:
        entry = entry.model_copy(update={"api_key": existing.api_key})
    stored = service.upsert_entry(entry.model_copy(update={"id": provider_id}))
    return ProviderRegistrySummary.from_entry(stored).model_dump(mode="json")


@router.delete("/api/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """Delete a provider from the backend registry."""
    service = get_provider_registry_service()
    deleted = service.delete_entry(provider_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Provider not found: {provider_id}",
                    "code": "provider_not_found",
                }
            },
        )
    get_model_registry_service().delete_entries_for_provider(provider_id)
    return {"status": "ok", "deleted": provider_id}
