"""Contract tests for backend provider registry endpoints."""


def _provider_payload(
    *,
    provider_id: str = "provider-1",
    name: str = "OpenAI",
):
    return {
        "id": provider_id,
        "name": name,
        "type": "openai",
        "api_key": "sk-test-12345678",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {"X-Test": "1"},
        "is_enabled": True,
        "backend_mode": "auto",
        "fallback_enabled": False,
        "fallback_timeout_ms": 9000,
        "circuit_breaker": {
            "failure_threshold": 4,
            "window_ms": 120000,
            "open_ms": 45000,
            "half_open_max_calls": 3,
        },
    }


def test_put_provider_persists_registry_entry(client):
    response = client.put("/api/providers/provider-1", json=_provider_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "provider-1"
    assert data["name"] == "OpenAI"
    assert data["has_api_key"] is True
    assert data["masked_api_key"].startswith("sk-t")
    assert data["backend_mode"] == "auto"
    assert data["fallback_enabled"] is False
    assert data["circuit_breaker"]["failure_threshold"] == 4


def test_list_providers_masks_api_key(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    response = client.get("/api/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert data["data"][0]["id"] == "provider-1"
    assert data["data"][0]["masked_api_key"].startswith("sk-t")
    assert "api_key" not in data["data"][0]


def test_delete_provider_removes_registry_entry(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    delete_response = client.delete("/api/providers/provider-1")
    list_response = client.get("/api/providers")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == "provider-1"
    assert list_response.status_code == 200
    assert list_response.json()["data"] == []


def test_put_provider_preserves_existing_api_key_when_blank(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    response = client.put(
        "/api/providers/provider-1",
        json={
            **_provider_payload(name="Updated OpenAI"),
            "api_key": "",
        },
    )

    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert response.json()["name"] == "Updated OpenAI"

    from services.provider_registry import get_provider_registry_service

    entry = get_provider_registry_service().get_entry("provider-1")
    assert entry is not None
    assert entry.api_key == "sk-test-12345678"
    assert entry.name == "Updated OpenAI"


def test_registry_default_direct_bundle_preserves_explicit_direct(client):
    response = client.put(
        "/api/providers/provider-1",
        json={
            "id": "provider-1",
            "name": "OpenAI",
            "type": "openai",
            "api_key": "sk-test-12345678",
            "api_url": "https://api.openai.com/v1",
            "custom_headers": {},
            "is_enabled": True,
            "backend_mode": "direct",
            "fallback_enabled": True,
            "fallback_timeout_ms": 5000,
        },
    )

    assert response.status_code == 200

    from services.provider_registry import get_provider_registry_service

    entry = get_provider_registry_service().get_entry("provider-1")
    runtime_provider = entry.to_runtime_provider()

    assert runtime_provider.backend_mode == "direct"
    assert runtime_provider.fallback_enabled is None
    assert runtime_provider.fallback_timeout_ms is None
