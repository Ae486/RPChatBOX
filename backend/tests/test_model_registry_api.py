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
        "capabilities": ["tool"],
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
    assert data["capabilities"] == ["tool"]
    assert data["capability_source"] == "user_declared"
    assert data["capability_profile"]["resolution_strategy"] == "manual_override"


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


def test_put_rerank_model_auto_fills_rerank_capability_when_known(client):
    client.put(
        "/api/providers/provider-rerank",
        json={
            "id": "provider-rerank",
            "name": "Cohere",
            "type": "cohere",
            "api_key": "sk-test-12345678",
            "api_url": "https://api.cohere.com/v2/rerank",
            "custom_headers": {},
            "is_enabled": True,
        },
    )

    response = client.put(
        "/api/providers/provider-rerank/models/model-rerank",
        json={
            **_model_payload("model-rerank"),
            "provider_id": "provider-rerank",
            "model_name": "rerank-v3.5",
            "display_name": "Rerank V3.5",
            "capabilities": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["capabilities"] == ["rerank"]
    assert response.json()["capability_source"] == "litellm_metadata"
    assert response.json()["capability_profile"]["mode"] == "rerank"


def test_put_unknown_model_defaults_capability_source_to_default_unmapped(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    response = client.put(
        "/api/providers/provider-1/models/model-unknown",
        json={
            **_model_payload("model-unknown"),
            "model_name": "nonexistent-model-xyz-99",
            "display_name": "Unknown Model",
            "capabilities": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["capabilities"] == []
    assert response.json()["capability_source"] == "default_unmapped"
    assert response.json()["capability_profile"]["resolution_strategy"] == "unmapped"


def test_put_local_cross_encoder_model_preserves_user_declared_capability(client):
    client.put(
        "/api/providers/provider-local",
        json={
            "id": "provider-local",
            "name": "Local CrossEncoder",
            "type": "local",
            "api_key": "unused",
            "api_url": "local://cross-encoder",
            "custom_headers": {},
            "is_enabled": True,
        },
    )

    response = client.put(
        "/api/providers/provider-local/models/model-local-rerank",
        json={
            **_model_payload("model-local-rerank"),
            "provider_id": "provider-local",
            "model_name": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "display_name": "MS MARCO Cross Encoder",
            "capabilities": ["cross_encoder_rerank"],
        },
    )

    assert response.status_code == 200
    assert response.json()["capabilities"] == ["rerank"]
    assert response.json()["capability_source"] == "user_declared"
    assert response.json()["capability_profile"]["mode"] == "rerank"


def test_preview_model_returns_structured_capability_profile(client):
    client.put("/api/providers/provider-1", json=_provider_payload())

    response = client.get(
        "/api/providers/provider-1/models/_preview",
        params={"model_name": "gpt-4o-mini"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider_id"] == "provider-1"
    assert data["model_name"] == "gpt-4o-mini"
    assert data["capability_source"] == "litellm_metadata"
    assert "tool" in data["capabilities"]
    assert data["capability_profile"]["supports_function_calling"] is True


def test_local_rerank_readiness_endpoint_returns_unconfigured_when_no_model(client):
    response = client.get("/api/retrieval/rerank/local-readiness")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unconfigured"
    assert data["configured"] is False
    assert data["dependencies"]


def test_local_rerank_readiness_endpoint_returns_configured_local_model(client):
    client.put(
        "/api/providers/provider-local",
        json={
            "id": "provider-local",
            "name": "Local CrossEncoder",
            "type": "local",
            "api_key": "unused",
            "api_url": "local://cross-encoder",
            "custom_headers": {},
            "is_enabled": True,
        },
    )
    client.put(
        "/api/providers/provider-local/models/model-local-rerank",
        json={
            **_model_payload("model-local-rerank"),
            "provider_id": "provider-local",
            "model_name": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "display_name": "MS MARCO Cross Encoder",
            "capabilities": ["cross_encoder_rerank"],
        },
    )

    response = client.get(
        "/api/retrieval/rerank/local-readiness",
        params={"model_id": "model-local-rerank", "provider_id": "provider-local"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["model_id"] == "model-local-rerank"
    assert data["provider_id"] == "provider-local"
    assert data["requirements_path"].endswith("requirements-rerank-local.txt")
