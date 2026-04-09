"""Contract tests for backend conversation/session endpoints."""
from unittest.mock import MagicMock, patch

from config import get_settings
from services.langgraph_checkpoint_store import ensure_langgraph_checkpoint_schema


def test_conversation_crud_and_settings_flow(client):
    create_response = client.post(
        "/api/conversations",
        json={
            "title": "Story A",
            "system_prompt": "You are a narrator.",
            "role_id": "role-1",
            "role_type": "preset",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    conversation_id = created["id"]
    assert created["title"] == "Story A"
    assert created["role_id"] == "role-1"
    assert created["is_pinned"] is False
    assert created["is_archived"] is False

    get_response = client.get(f"/api/conversations/{conversation_id}")
    assert get_response.status_code == 200
    assert get_response.json()["system_prompt"] == "You are a narrator."

    settings_response = client.get(f"/api/conversations/{conversation_id}/settings")
    assert settings_response.status_code == 200
    settings = settings_response.json()
    assert settings["selected_model_id"] is None
    assert settings["parameters"]["maxTokens"] == 2048

    updated_settings_response = client.put(
        f"/api/conversations/{conversation_id}/settings",
        json={
            "selected_provider_id": "provider-1",
            "selected_model_id": "model-1",
            "parameters": {
                "temperature": 0.4,
                "maxTokens": 4096,
                "topP": 0.9,
                "frequencyPenalty": 0.1,
                "presencePenalty": 0.2,
                "streamOutput": True,
            },
            "enable_vision": True,
            "enable_tools": True,
            "enable_network": True,
            "enable_experimental_streaming_markdown": True,
            "context_length": 16,
        },
    )
    assert updated_settings_response.status_code == 200
    updated_settings = updated_settings_response.json()
    assert updated_settings["selected_provider_id"] == "provider-1"
    assert updated_settings["selected_model_id"] == "model-1"
    assert updated_settings["enable_tools"] is True
    assert updated_settings["context_length"] == 16
    assert updated_settings["parameters"]["maxTokens"] == 4096

    patch_response = client.patch(
        f"/api/conversations/{conversation_id}",
        json={
            "title": "Story A (Renamed)",
            "latest_checkpoint_id": "cp-latest",
            "selected_checkpoint_id": "cp-selected",
            "is_pinned": True,
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["title"] == "Story A (Renamed)"
    assert patched["latest_checkpoint_id"] == "cp-latest"
    assert patched["selected_checkpoint_id"] == "cp-selected"
    assert patched["is_pinned"] is True

    delete_response = client.delete(f"/api/conversations/{conversation_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == conversation_id

    missing_response = client.get(f"/api/conversations/{conversation_id}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["error"]["code"] == "conversation_not_found"

    include_deleted_response = client.get("/api/conversations?include_deleted=true")
    assert include_deleted_response.status_code == 200
    assert include_deleted_response.json()["data"][0]["id"] == conversation_id


def test_conversation_list_sorts_by_last_activity_and_pin(client):
    first = client.post("/api/conversations", json={"title": "First"}).json()
    second = client.post("/api/conversations", json={"title": "Second"}).json()

    initial_list = client.get("/api/conversations")
    assert initial_list.status_code == 200
    initial_ids = [item["id"] for item in initial_list.json()["data"]]
    assert initial_ids[0] == second["id"]
    assert initial_ids[1] == first["id"]

    settings_touch = client.put(
        f"/api/conversations/{first['id']}/settings",
        json={
            "selected_provider_id": "provider-1",
            "selected_model_id": "model-1",
            "parameters": {
                "temperature": 0.7,
                "maxTokens": 2048,
                "topP": 1.0,
                "frequencyPenalty": 0.0,
                "presencePenalty": 0.0,
                "streamOutput": True,
            },
            "enable_vision": False,
            "enable_tools": False,
            "enable_network": False,
            "enable_experimental_streaming_markdown": False,
            "context_length": 10,
        },
    )
    assert settings_touch.status_code == 200

    touched_list = client.get("/api/conversations")
    touched_ids = [item["id"] for item in touched_list.json()["data"]]
    assert touched_ids[0] == first["id"]

    pin_second = client.patch(
        f"/api/conversations/{second['id']}",
        json={"is_pinned": True},
    )
    assert pin_second.status_code == 200

    pinned_list = client.get("/api/conversations")
    pinned_ids = [item["id"] for item in pinned_list.json()["data"]]
    assert pinned_ids[0] == second["id"]


def test_langgraph_checkpoint_setup_uses_postgres_when_configured(monkeypatch):
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        "postgresql://postgres:postgres@127.0.0.1:5432/chatboxapp",
    )
    get_settings.cache_clear()

    mock_saver = MagicMock()
    mock_manager = MagicMock()
    mock_manager.__enter__.return_value = mock_saver
    mock_manager.__exit__.return_value = None

    with patch(
        "langgraph.checkpoint.postgres.PostgresSaver.from_conn_string",
        return_value=mock_manager,
    ) as factory:
        ensure_langgraph_checkpoint_schema()

    factory.assert_called_once_with(
        "postgresql://postgres:postgres@127.0.0.1:5432/chatboxapp"
    )
    mock_saver.setup.assert_called_once_with()
    get_settings.cache_clear()
