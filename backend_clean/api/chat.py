"""Chat completion endpoints (OpenAI-compatible)."""
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
import httpx

from config import get_settings
from models.chat import ChatCompletionRequest, ProviderConfig

router = APIRouter()
settings = get_settings()


def _get_llm_service():
    """Get appropriate LLM service based on config and availability."""
    if settings.use_litellm:
        try:
            from services.litellm_service import get_litellm_service
            return get_litellm_service()
        except ImportError:
            # litellm not available (e.g., Android), fallback to httpx proxy
            pass
    from services.llm_proxy import get_llm_proxy_service
    return get_llm_proxy_service()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.

    Accepts standard OpenAI format plus extension fields:
    - provider: { type, api_key, api_url, custom_headers }

    Supports both streaming and non-streaming responses.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    try:
        chat_request = ChatCompletionRequest(**body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    if not chat_request.provider:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Provider configuration is required",
                    "code": "missing_provider",
                }
            },
        )

    service = _get_llm_service()

    try:
        if chat_request.stream:
            return StreamingResponse(
                service.chat_completion_stream(chat_request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            response = await service.chat_completion(chat_request)
            if hasattr(response, "model_dump"):
                return response.model_dump()
            return response

    except httpx.HTTPStatusError as e:
        try:
            error_body = e.response.json()
        except json.JSONDecodeError:
            error_body = {"error": {"message": e.response.text}}
        raise HTTPException(status_code=e.response.status_code, detail=error_body)

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": {"message": "Upstream API timeout", "code": "timeout"}},
        )

    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"message": f"Failed to connect: {e}", "code": "connection_error"}},
        )

    except Exception as e:
        # LiteLLM exceptions
        if settings.use_litellm:
            from services.litellm_service import get_http_status_for_exception
            status_code, error_code = get_http_status_for_exception(e)
            raise HTTPException(
                status_code=status_code,
                detail={"error": {"message": str(e), "code": error_code}},
            )
        raise HTTPException(
            status_code=500,
            detail={"error": {"message": f"Internal error: {e}", "code": "internal_error"}},
        )


@router.get("/models")
@router.get("/v1/models")
async def list_models(request: Request):
    """List available models (health check)."""
    return {
        "object": "list",
        "data": [{"id": "proxy-health-check", "object": "model", "owned_by": "chatbox"}],
    }


@router.post("/models")
@router.post("/v1/models")
async def list_models_with_provider(request: Request):
    """List models from upstream provider (with provider config in body)."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}

    provider_data = body.get("provider")
    if not provider_data:
        return {
            "object": "list",
            "data": [{"id": "proxy-health-check", "object": "model", "owned_by": "chatbox"}],
        }

    try:
        provider = ProviderConfig(**provider_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    base_url = provider.api_url.rstrip("/")
    if base_url.endswith("#"):
        base_url = base_url[:-1]
    elif "/v1" not in base_url and provider.type in ("openai", "deepseek"):
        base_url = f"{base_url}/v1"

    models_url = f"{base_url}/models"
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    headers.update(provider.custom_headers)

    try:
        async with httpx.AsyncClient(timeout=30.0, proxy=None) as client:
            response = await client.get(models_url, headers=headers)
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        try:
            error_body = e.response.json()
        except json.JSONDecodeError:
            error_body = {"error": {"message": e.response.text}}
        raise HTTPException(status_code=e.response.status_code, detail=error_body)

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"message": f"Failed to fetch models: {e}"}},
        )
