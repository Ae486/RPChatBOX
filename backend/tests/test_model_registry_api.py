"""Contract tests for backend provider-scoped model registry endpoints."""


def _provider_payload(provider_id: str = "provider-1"):
    return {
        "id": provider_id,
        "name": "OpenAI",
        "type": "openai",
        "api_key": "sk-test-12345678",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }


def _model_payload(model_id: str = "model-1"):
    return {
        "id": model_id,
        "provider_id": "provider-1",
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "capabilities": ["text", "tool"],
        "default_params": {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "stream_output": True,
        },
        "is_enabled": True,
        "description": "test model",
    }


def test_put_model_persists_registry_entry(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    response = client.put(
        "/api/providers/provider-1/models/model-1",
        json=_model_payload(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "model-1"
    assert data["provider_id"] == "provider-1"
    assert data["model_name"] == "gpt-4o-mini"
    assert data["display_name"] == "GPT-4o Mini"
    assert data["capabilities"] == ["text", "tool"]


def test_list_models_returns_provider_scoped_models(client):
    client.put("/api/providers/provider-1", json=_provider_payload())
    client.put("/api/providers/provider-2", json=_provider_payload("provider-2"))

    client.put(
        "/api/providers/provider-1/models/model-1",
        json=_model_payload("model-1"),
    )
    client.put(
        "/api/providers/provider-2/models/model-2",
        json={**_model_payload("model-2"), "provider_id": "provider-2"},
    )

    response = client.get("/api/providers/provider-1/models")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "model-1"


def test_delete_provider_cascades_model_registry_entries(client):
    client.put("/api/providers/provider-1", json=_provider_payload())
    client.put(
        "/api/providers/provider-1/models/model-1",
        json=_model_payload(),
    )

    delete_response = client.delete("/api/providers/provider-1")
    list_response = client.get("/api/providers/provider-1/models")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == "provider-1"
    assert list_response.status_code == 404
