"""Provider-scoped model registry endpoints."""
from fastapi import APIRouter, HTTPException

from models.model_registry import ModelRegistryEntry, ModelRegistrySummary
from rp.services.local_rerank_readiness_service import LocalRerankReadinessService
from services.model_capability_service import (
    hydrate_registry_model_entry,
    normalize_registry_capabilities,
    query_model_capabilities,
    resolve_model_capability_profile,
)
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


def _prepare_model_entry(
    *,
    entry: ModelRegistryEntry,
    existing: ModelRegistryEntry | None,
):
    provider = get_provider_registry_service().get_entry(entry.provider_id)
    return hydrate_registry_model_entry(
        entry=entry,
        provider_type=provider.type if provider is not None else None,
        existing=existing,
    )


@router.get("/api/providers/{provider_id}/models/_preview")
async def preview_provider_model(provider_id: str, model_name: str):
    _ensure_provider_exists(provider_id)
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
    profile = resolve_model_capability_profile(provider.type, model_name)
    return {
        "provider_id": provider_id,
        "model_name": model_name,
        "display_name": model_name,
        "capabilities": normalize_registry_capabilities(profile.recommended_capabilities),
        "capability_source": profile.capability_source,
        "capability_profile": profile.model_dump(mode="json", exclude_none=True),
    }


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

    existing = model_service.get_entry(model_id)
    prepared = _prepare_model_entry(entry=prepared, existing=existing)
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


@router.get("/api/retrieval/rerank/local-readiness")
async def get_local_rerank_readiness(
    model_id: str | None = None,
    provider_id: str | None = None,
    include_model_load: bool = False,
):
    readiness = LocalRerankReadinessService().get_readiness(
        model_id=model_id,
        provider_id=provider_id,
        include_model_load=include_model_load,
    )
    return readiness.model_dump(mode="json")
