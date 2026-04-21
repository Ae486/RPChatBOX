"""Chat completion endpoints (OpenAI-compatible)."""
import asyncio
from contextlib import suppress
import json
import logging
import time
from typing import Any, AsyncIterator
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
import httpx

from config import get_settings
from models.chat import ChatCompletionRequest, ProviderConfig
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)
_MODEL_DISCOVERY_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/messages",
    "/embeddings",
)


def _provider_not_found(provider_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Provider not found: {provider_id}",
                "code": "provider_not_found",
            }
        },
    )


def _provider_disabled(provider_id: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": f"Provider is disabled: {provider_id}",
                "code": "provider_disabled",
            }
        },
    )


def _model_not_found(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"Model not found: {model_id}",
                "code": "model_not_found",
            }
        },
    )


def _model_disabled(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": f"Model is disabled: {model_id}",
                "code": "model_disabled",
            }
        },
    )


def _model_provider_mismatch(model_id: str, provider_id: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": (
                    f"Model {model_id} does not belong to provider {provider_id}"
                ),
                "code": "model_provider_mismatch",
            }
        },
    )


def _resolve_runtime_model(
    *,
    model_id: str | None,
    request_model: str,
    provider_id: str | None,
) -> tuple[str, str | None]:
    """Resolve model_id into runtime model name and provider reference."""
    if not model_id:
        return request_model, provider_id

    entry = get_model_registry_service().get_entry(model_id)
    if entry is None:
        raise _model_not_found(model_id)
    if not entry.is_enabled:
        raise _model_disabled(model_id)
    if provider_id and provider_id != entry.provider_id:
        raise _model_provider_mismatch(model_id, provider_id)
    return entry.model_name, entry.provider_id


def _resolve_runtime_provider(
    *,
    provider_id: str | None,
    inline_provider: ProviderConfig | None,
) -> ProviderConfig | None:
    """Resolve a provider reference to a runtime provider config."""
    if provider_id:
        entry = get_provider_registry_service().get_entry(provider_id)
        if entry is not None:
            if not entry.is_enabled:
                raise _provider_disabled(provider_id)
            return entry.to_runtime_provider()
        if inline_provider is None:
            raise _provider_not_found(provider_id)
    return inline_provider


def _get_models_url(provider: ProviderConfig) -> str:
    """Build upstream model-list URL, matching the original Flutter direct path."""
    base_url = provider.api_url.rstrip("/")
    if base_url.endswith("#"):
        base_url = base_url[:-1]

    for suffix in _MODEL_DISCOVERY_ENDPOINT_SUFFIXES:
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break

    if "/v1" not in base_url and provider.type in ("openai", "deepseek"):
        base_url = f"{base_url}/v1"

    return f"{base_url.rstrip('/')}/models"


def _get_llm_service():
    """Get appropriate LLM service based on config and availability."""
    if settings.use_litellm:
        try:
            from services.runtime_routing_service import get_runtime_routing_service

            return get_runtime_routing_service()
        except ImportError:
            # litellm not available (e.g., Android), fallback to httpx proxy
            pass
    from services.llm_proxy import get_llm_proxy_service
    return get_llm_proxy_service()


async def _wait_for_client_disconnect(
    request: Request,
    *,
    poll_interval: float = 0.1,
) -> None:
    """Poll FastAPI/Starlette request state until the client disconnects."""
    while True:
        if await request.is_disconnected():
            return
        await asyncio.sleep(poll_interval)


async def _stream_with_disconnect_guard(
    request: Request,
    stream: AsyncIterator[str],
    *,
    request_id: str,
    provider_type: str,
    model: str,
    service_name: str,
    poll_interval: float = 0.1,
    idle_timeout: float | None = None,
) -> AsyncIterator[str]:
    """Close the upstream stream promptly when the downstream client disconnects."""
    iterator = stream.__aiter__()
    disconnect_task = asyncio.create_task(
        _wait_for_client_disconnect(request, poll_interval=poll_interval)
    )
    started_at = time.perf_counter()
    chunk_count = 0
    first_chunk_logged = False
    next_chunk_task: asyncio.Task[str] | None = None
    idle_timeout_task: asyncio.Task[None] | None = None
    effective_idle_timeout = (
        idle_timeout if idle_timeout is not None else settings.llm_stream_idle_timeout
    )

    try:
        while True:
            next_chunk_task = asyncio.create_task(anext(iterator))
            wait_tasks: set[asyncio.Task[Any]] = {next_chunk_task, disconnect_task}
            if first_chunk_logged and effective_idle_timeout > 0:
                idle_timeout_task = asyncio.create_task(
                    asyncio.sleep(effective_idle_timeout)
                )
                wait_tasks.add(idle_timeout_task)
            done, _ = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if disconnect_task in done:
                if not next_chunk_task.done():
                    next_chunk_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_chunk_task
                logger.info(
                    "[OBS] stream_cancelled request_id=%s provider=%s model=%s service=%s chunk_count=%s duration_ms=%.1f",
                    request_id,
                    provider_type,
                    model,
                    service_name,
                    chunk_count,
                    (time.perf_counter() - started_at) * 1000,
                )
                next_chunk_task = None
                break

            if idle_timeout_task is not None and idle_timeout_task in done:
                if not next_chunk_task.done():
                    next_chunk_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_chunk_task
                logger.error(
                    "[OBS] stream_idle_timeout request_id=%s provider=%s model=%s service=%s chunk_count=%s idle_timeout_s=%.1f duration_ms=%.1f",
                    request_id,
                    provider_type,
                    model,
                    service_name,
                    chunk_count,
                    effective_idle_timeout,
                    (time.perf_counter() - started_at) * 1000,
                )
                yield _build_stream_error_sse(
                    code="stream_idle_timeout",
                    message=(
                        "Upstream stream stalled after first chunk for "
                        f"{effective_idle_timeout:.1f}s"
                    ),
                )
                next_chunk_task = None
                idle_timeout_task = None
                break

            try:
                chunk = next_chunk_task.result()
            except StopAsyncIteration:
                logger.info(
                    "[OBS] stream_completed request_id=%s provider=%s model=%s service=%s chunk_count=%s duration_ms=%.1f",
                    request_id,
                    provider_type,
                    model,
                    service_name,
                    chunk_count,
                    (time.perf_counter() - started_at) * 1000,
                )
                next_chunk_task = None
                break
            except Exception:
                logger.exception(
                    "[OBS] stream_iteration_error request_id=%s provider=%s model=%s service=%s chunk_count=%s",
                    request_id,
                    provider_type,
                    model,
                    service_name,
                    chunk_count,
                )
                raise

            next_chunk_task = None
            if idle_timeout_task is not None:
                idle_timeout_task.cancel()
                with suppress(asyncio.CancelledError):
                    await idle_timeout_task
                idle_timeout_task = None
            chunk_count += 1
            if not first_chunk_logged:
                first_chunk_logged = True
                logger.info(
                    "[OBS] stream_first_chunk request_id=%s provider=%s model=%s service=%s first_chunk_ms=%.1f",
                    request_id,
                    provider_type,
                    model,
                    service_name,
                    (time.perf_counter() - started_at) * 1000,
                )
            yield chunk
    except asyncio.CancelledError:
        logger.info(
            "[OBS] stream_task_cancelled request_id=%s provider=%s model=%s service=%s chunk_count=%s duration_ms=%.1f",
            request_id,
            provider_type,
            model,
            service_name,
            chunk_count,
            (time.perf_counter() - started_at) * 1000,
        )
        raise
    finally:
        if next_chunk_task is not None and not next_chunk_task.done():
            next_chunk_task.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_chunk_task

        if idle_timeout_task is not None and not idle_timeout_task.done():
            idle_timeout_task.cancel()
            with suppress(asyncio.CancelledError):
                await idle_timeout_task

        disconnect_task.cancel()
        with suppress(asyncio.CancelledError):
            await disconnect_task

        aclose = getattr(iterator, "aclose", None)
        if callable(aclose):
            with suppress(asyncio.CancelledError, RuntimeError):
                await aclose()


def _build_stream_error_sse(*, code: str, message: str) -> str:
    payload = {
        "error": {
            "message": message,
            "type": code,
            "code": code,
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


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

    chat_request.model, chat_request.provider_id = _resolve_runtime_model(
        model_id=chat_request.model_id,
        request_model=chat_request.model,
        provider_id=chat_request.provider_id,
    )

    chat_request.provider = _resolve_runtime_provider(
        provider_id=chat_request.provider_id,
        inline_provider=chat_request.provider,
    )

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
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    provider_type = chat_request.provider.type
    service_name = service.__class__.__name__

    try:
        if chat_request.stream:
            logger.info(
                "[OBS] stream_request_started request_id=%s provider=%s model=%s service=%s",
                request_id,
                provider_type,
                chat_request.model,
                service_name,
            )
            return StreamingResponse(
                _stream_with_disconnect_guard(
                    request,
                    service.chat_completion_stream(chat_request),
                    request_id=request_id,
                    provider_type=provider_type,
                    model=chat_request.model,
                    service_name=service_name,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Request-Id": request_id,
                },
            )
        else:
            started_at = time.perf_counter()
            logger.info(
                "[OBS] request_started request_id=%s provider=%s model=%s service=%s stream=false",
                request_id,
                provider_type,
                chat_request.model,
                service_name,
            )
            response = await service.chat_completion(chat_request)
            logger.info(
                "[OBS] request_completed request_id=%s provider=%s model=%s service=%s duration_ms=%.1f",
                request_id,
                provider_type,
                chat_request.model,
                service_name,
                (time.perf_counter() - started_at) * 1000,
            )
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
        logger.exception(
            "[OBS] request_failed request_id=%s provider=%s model=%s service=%s stream=%s",
            request_id,
            provider_type,
            chat_request.model,
            service_name,
            chat_request.stream,
        )
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

    provider_id = body.get("provider_id")
    provider_data = body.get("provider")
    if not provider_data and not provider_id:
        return {
            "object": "list",
            "data": [{"id": "proxy-health-check", "object": "model", "owned_by": "chatbox"}],
        }

    provider: ProviderConfig | None = None
    if provider_data:
        try:
            provider = ProviderConfig(**provider_data)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    provider = _resolve_runtime_provider(
        provider_id=provider_id,
        inline_provider=provider,
    )
    if provider is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Provider configuration is required",
                    "code": "missing_provider",
                }
            },
        )

    models_url = _get_models_url(provider)
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
