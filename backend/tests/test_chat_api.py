"""Contract tests for chat API endpoints."""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat import _stream_with_disconnect_guard


def _provider_payload():
    return {
        "type": "openai",
        "api_key": "sk-test",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
    }


def _chat_payload(stream: bool):
    return {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": stream,
        "provider": _provider_payload(),
    }


class StubLLMService:
    async def chat_completion(self, chat_request):
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 123,
            "model": chat_request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi from backend"},
                    "finish_reason": "stop",
                }
            ],
        }

    async def chat_completion_stream(self, chat_request):
        if chat_request.stream_event_mode == "typed":
            yield 'data: {"type":"thinking_delta","delta":"draft"}\n\n'
            yield 'data: {"type":"text_delta","delta":"answer"}\n\n'
            yield 'data: {"type":"done"}\n\n'
            return
        yield 'data: {"id":"chatcmpl-test","choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield "data: [DONE]\n\n"


class CapturingStubLLMService(StubLLMService):
    def __init__(self):
        self.last_request = None

    async def chat_completion(self, chat_request):
        self.last_request = chat_request
        return await super().chat_completion(chat_request)

    async def chat_completion_stream(self, chat_request):
        self.last_request = chat_request
        async for chunk in super().chat_completion_stream(chat_request):
            yield chunk


def test_chat_completions_requires_provider(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "missing_provider"


def test_chat_completions_resolves_provider_id_from_registry(client):
    registry_payload = {
        "id": "provider-1",
        "name": "Registry Provider",
        "type": "openai",
        "api_key": "sk-registry",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }
    upsert = client.put("/api/providers/provider-1", json=registry_payload)
    assert upsert.status_code == 200

    with patch("api.chat._get_llm_service", return_value=StubLLMService()):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "provider_id": "provider-1",
            },
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hi from backend"


def test_chat_completions_provider_id_not_found(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
            "provider_id": "missing-provider",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "provider_not_found"


def test_chat_completions_resolves_model_id_from_registry(client):
    provider_payload = {
        "id": "provider-1",
        "name": "Registry Provider",
        "type": "openai",
        "api_key": "sk-registry",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }
    model_payload = {
        "id": "model-1",
        "provider_id": "provider-1",
        "model_name": "gpt-4.1-mini",
        "display_name": "GPT-4.1 Mini",
        "capabilities": ["text"],
        "is_enabled": True,
    }
    assert client.put("/api/providers/provider-1", json=provider_payload).status_code == 200
    assert (
        client.put("/api/providers/provider-1/models/model-1", json=model_payload).status_code
        == 200
    )

    service = CapturingStubLLMService()
    with patch("api.chat._get_llm_service", return_value=service):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "stale-local-model",
                "model_id": "model-1",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
        )

    assert response.status_code == 200
    assert service.last_request is not None
    assert service.last_request.model == "gpt-4.1-mini"
    assert service.last_request.provider is not None
    assert service.last_request.provider.type == "openai"


def test_chat_completions_model_id_not_found(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "model_id": "missing-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "model_not_found"


def test_chat_completions_model_id_provider_mismatch(client):
    provider_payload = {
        "id": "provider-1",
        "name": "Registry Provider",
        "type": "openai",
        "api_key": "sk-registry",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }
    other_provider_payload = {
        "id": "provider-2",
        "name": "Other Provider",
        "type": "openai",
        "api_key": "sk-other",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }
    model_payload = {
        "id": "model-1",
        "provider_id": "provider-1",
        "model_name": "gpt-4.1-mini",
        "display_name": "GPT-4.1 Mini",
        "capabilities": ["text"],
        "is_enabled": True,
    }
    assert client.put("/api/providers/provider-1", json=provider_payload).status_code == 200
    assert client.put("/api/providers/provider-2", json=other_provider_payload).status_code == 200
    assert (
        client.put("/api/providers/provider-1/models/model-1", json=model_payload).status_code
        == 200
    )

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "model_id": "model-1",
            "provider_id": "provider-2",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "model_provider_mismatch"


def test_chat_completions_non_stream_contract(client):
    with patch("api.chat._get_llm_service", return_value=StubLLMService()):
        response = client.post("/v1/chat/completions", json=_chat_payload(stream=False))

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "chatcmpl-test"
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hi from backend"


def test_chat_completions_stream_contract(client):
    with patch("api.chat._get_llm_service", return_value=StubLLMService()):
        with client.stream("POST", "/v1/chat/completions", json=_chat_payload(stream=True)) as response:
            body = "".join(chunk.decode("utf-8") for chunk in response.iter_raw())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"]
    assert 'data: {"id":"chatcmpl-test"' in body
    assert "data: [DONE]" in body


def test_chat_completions_typed_stream_contract(client):
    payload = _chat_payload(stream=True)
    payload["stream_event_mode"] = "typed"

    with patch("api.chat._get_llm_service", return_value=StubLLMService()):
        with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            body = "".join(chunk.decode("utf-8") for chunk in response.iter_raw())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type":"thinking_delta","delta":"draft"}' in body
    assert 'data: {"type":"text_delta","delta":"answer"}' in body
    assert 'data: {"type":"done"}' in body
    assert "data: [DONE]" not in body


class _DisconnectingRequest:
    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


@pytest.mark.asyncio
async def test_stream_disconnect_guard_closes_upstream_generator(caplog):
    caplog.set_level(logging.INFO, logger="api.chat")
    request = _DisconnectingRequest()
    state = {"closed": False}

    async def upstream_stream():
        try:
            yield 'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            await asyncio.sleep(0.05)
            yield 'data: {"choices":[{"delta":{"content":"second"}}]}\n\n'
        finally:
            state["closed"] = True

    async def trigger_disconnect():
        await asyncio.sleep(0.01)
        request.disconnected = True

    chunks: list[str] = []
    disconnect_task = asyncio.create_task(trigger_disconnect())
    async for chunk in _stream_with_disconnect_guard(
        request,
        upstream_stream(),
        request_id="req-test-stop",
        provider_type="openai",
        model="gpt-4o-mini",
        service_name="StubLLMService",
        poll_interval=0.001,
    ):
        chunks.append(chunk)
    await disconnect_task

    assert chunks == ['data: {"choices":[{"delta":{"content":"first"}}]}\n\n']
    assert state["closed"] is True
    assert "stream_cancelled request_id=req-test-stop" in caplog.text


@pytest.mark.asyncio
async def test_stream_disconnect_guard_closes_upstream_before_first_chunk(caplog):
    caplog.set_level(logging.INFO, logger="api.chat")
    request = _DisconnectingRequest()
    state = {"closed": False}

    async def upstream_stream():
        try:
            await asyncio.sleep(0.05)
            yield 'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'
        finally:
            state["closed"] = True

    async def trigger_disconnect():
        await asyncio.sleep(0.01)
        request.disconnected = True

    chunks: list[str] = []
    disconnect_task = asyncio.create_task(trigger_disconnect())
    async for chunk in _stream_with_disconnect_guard(
        request,
        upstream_stream(),
        request_id="req-test-pre-first-chunk-stop",
        provider_type="openai",
        model="gpt-4o-mini",
        service_name="StubLLMService",
        poll_interval=0.001,
    ):
        chunks.append(chunk)
    await disconnect_task

    assert chunks == []
    assert state["closed"] is True
    assert (
        "stream_cancelled request_id=req-test-pre-first-chunk-stop" in caplog.text
    )


def test_post_models_without_provider_returns_health_sentinel(client):
    response = client.post("/models", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert data["data"][0]["id"] == "proxy-health-check"


def test_post_models_with_provider_proxies_upstream(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "object": "list",
        "data": [{"id": "gpt-4o-mini", "object": "model"}],
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("api.chat.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.post("/models", json={"provider": _provider_payload()})

    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["id"] == "gpt-4o-mini"
    mock_client.get.assert_awaited_once()
    called_url = mock_client.get.await_args.args[0]
    assert called_url == "https://api.openai.com/v1/models"


def test_post_models_with_provider_id_uses_registry(client):
    registry_payload = {
        "id": "provider-1",
        "name": "Registry Provider",
        "type": "openai",
        "api_key": "sk-registry",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }
    upsert = client.put("/api/providers/provider-1", json=registry_payload)
    assert upsert.status_code == 200

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "object": "list",
        "data": [{"id": "gpt-4o", "object": "model"}],
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("api.chat.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.post("/models", json={"provider_id": "provider-1"})

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "gpt-4o"


def test_post_models_strips_chat_completion_suffix_from_upstream_url(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "object": "list",
        "data": [{"id": "gpt-4o-mini", "object": "model"}],
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("api.chat.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.post(
            "/models",
            json={
                "provider": {
                    "type": "openai",
                    "api_key": "sk-test",
                    "api_url": "https://x666.me/v1/chat/completions",
                    "custom_headers": {},
                }
            },
        )

    assert response.status_code == 200
    called_url = mock_client.get.await_args.args[0]
    assert called_url == "https://x666.me/v1/models"
