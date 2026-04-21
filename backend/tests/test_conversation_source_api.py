"""Contract tests for conversation source-thread endpoints."""


def _message_payload(
    *,
    message_id: str,
    role: str,
    content: str,
    created_at: str = "2026-04-09T00:00:00+00:00",
    edited_at: str | None = None,
    tool_call_records: list[dict] | None = None,
):
    payload = {
        "id": message_id,
        "role": role,
        "content": content,
        "created_at": created_at,
        "attached_files": [],
        "tool_call_records": tool_call_records or [],
    }
    if edited_at is not None:
        payload["edited_at"] = edited_at
    return payload


def test_conversation_source_starts_empty_and_supports_append_patch_fork_select(client):
    create_response = client.post(
        "/api/conversations", json={"title": "Threaded Story"}
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    empty_source = client.get(f"/api/conversations/{conversation_id}/source")
    assert empty_source.status_code == 200
    assert empty_source.json()["checkpoint_id"] is None
    assert empty_source.json()["messages"] == []

    append_user = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="Tell me a story about a cat.",
                )
            ]
        },
    )
    assert append_user.status_code == 200
    user_source = append_user.json()
    checkpoint_user = user_source["checkpoint_id"]
    assert checkpoint_user
    assert user_source["messages"][0]["id"] == "user-1"
    assert user_source["messages"][0]["role"] == "user"

    append_assistant = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="assistant-1",
                    role="assistant",
                    content="Once upon a time, there was a cat.",
                )
            ]
        },
    )
    assert append_assistant.status_code == 200
    assistant_source = append_assistant.json()
    checkpoint_assistant = assistant_source["checkpoint_id"]
    assert checkpoint_assistant != checkpoint_user
    assert [message["id"] for message in assistant_source["messages"]] == [
        "user-1",
        "assistant-1",
    ]

    patch_user = client.patch(
        f"/api/conversations/{conversation_id}/source/messages/user-1",
        json={
            "content": "Tell me a story about a dog.",
            "edited_at": "2026-04-09T00:10:00+00:00",
        },
    )
    assert patch_user.status_code == 200
    patched_source = patch_user.json()
    checkpoint_patched = patched_source["checkpoint_id"]
    assert checkpoint_patched not in {checkpoint_user, checkpoint_assistant}
    assert patched_source["messages"][0]["content"] == "Tell me a story about a dog."
    assert patched_source["messages"][0]["edited_at"] == "2026-04-09T00:10:00Z"
    assert (
        patched_source["messages"][1]["content"] == "Once upon a time, there was a cat."
    )

    fork_from_user = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "base_checkpoint_id": checkpoint_user,
            "messages": [
                _message_payload(
                    message_id="assistant-2",
                    role="assistant",
                    content="Once upon a time, there was a brave cat.",
                    created_at="2026-04-09T00:20:00+00:00",
                )
            ],
        },
    )
    assert fork_from_user.status_code == 200
    forked_source = fork_from_user.json()
    checkpoint_fork = forked_source["checkpoint_id"]
    assert checkpoint_fork not in {
        checkpoint_user,
        checkpoint_assistant,
        checkpoint_patched,
    }
    assert [message["id"] for message in forked_source["messages"]] == [
        "user-1",
        "assistant-2",
    ]
    assert forked_source["messages"][0]["content"] == "Tell me a story about a cat."

    history_response = client.get(
        f"/api/conversations/{conversation_id}/source/history"
    )
    assert history_response.status_code == 200
    history = history_response.json()["data"]
    assert history[0]["checkpoint_id"] == checkpoint_fork
    checkpoint_ids = {item["checkpoint_id"] for item in history}
    assert checkpoint_user in checkpoint_ids
    assert checkpoint_assistant in checkpoint_ids
    assert checkpoint_patched in checkpoint_ids
    fork_summary = next(
        item for item in history if item["checkpoint_id"] == checkpoint_fork
    )
    assert fork_summary["parent_checkpoint_id"] == checkpoint_user

    select_old_branch = client.put(
        f"/api/conversations/{conversation_id}/source/selection",
        json={"checkpoint_id": checkpoint_patched},
    )
    assert select_old_branch.status_code == 200
    selected_old = select_old_branch.json()
    assert selected_old["selected_checkpoint_id"] == checkpoint_patched
    assert [message["id"] for message in selected_old["messages"]] == [
        "user-1",
        "assistant-1",
    ]
    assert selected_old["messages"][0]["content"] == "Tell me a story about a dog."

    get_selected = client.get(f"/api/conversations/{conversation_id}/source")
    assert get_selected.status_code == 200
    assert get_selected.json()["selected_checkpoint_id"] == checkpoint_patched
    assert get_selected.json()["messages"][1]["id"] == "assistant-1"


def test_conversation_source_returns_not_found_for_missing_checkpoint_and_message(
    client,
):
    create_response = client.post("/api/conversations", json={"title": "Errors"})
    conversation_id = create_response.json()["id"]

    missing_checkpoint = client.put(
        f"/api/conversations/{conversation_id}/source/selection",
        json={"checkpoint_id": "missing-checkpoint"},
    )
    assert missing_checkpoint.status_code == 404
    assert (
        missing_checkpoint.json()["detail"]["error"]["code"] == "checkpoint_not_found"
    )

    append_user = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="hello",
                )
            ]
        },
    )
    assert append_user.status_code == 200

    missing_message = client.patch(
        f"/api/conversations/{conversation_id}/source/messages/missing-message",
        json={"content": "updated"},
    )
    assert missing_message.status_code == 404
    assert (
        missing_message.json()["detail"]["error"]["code"] == "source_message_not_found"
    )


def test_conversation_source_can_be_cleared_without_deleting_conversation(client):
    create_response = client.post("/api/conversations", json={"title": "Resettable"})
    conversation_id = create_response.json()["id"]

    append_user = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="hello",
                )
            ]
        },
    )
    assert append_user.status_code == 200
    assert append_user.json()["messages"][0]["id"] == "user-1"

    clear_response = client.delete(f"/api/conversations/{conversation_id}/source")
    assert clear_response.status_code == 200
    cleared = clear_response.json()
    assert cleared["checkpoint_id"] is None
    assert cleared["latest_checkpoint_id"] is None
    assert cleared["selected_checkpoint_id"] is None
    assert cleared["messages"] == []

    projection_response = client.get(
        f"/api/conversations/{conversation_id}/source/projection"
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert projection["current"]["messages"] == []
    assert projection["checkpoints"] == []

    get_conversation = client.get(f"/api/conversations/{conversation_id}")
    assert get_conversation.status_code == 200


def test_conversation_source_persists_tool_call_records(client):
    create_response = client.post("/api/conversations", json={"title": "Tool Records"})
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    tool_call_records = [
        {
            "callId": "call-1",
            "messageId": "assistant-1",
            "toolName": "search_docs",
            "serverName": "deepwiki",
            "status": "success",
            "durationMs": 842,
            "argumentsJson": "{\"query\":\"langgraph\"}",
            "result": "matched results",
            "errorMessage": None,
            "timestamp": "2026-04-09T00:00:10+00:00",
        }
    ]

    append_user = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="search langgraph docs",
                )
            ]
        },
    )
    assert append_user.status_code == 200

    append_assistant = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="assistant-1",
                    role="assistant",
                    content="done",
                    tool_call_records=tool_call_records,
                )
            ]
        },
    )
    assert append_assistant.status_code == 200
    source = append_assistant.json()
    assert source["messages"][-1]["tool_call_records"] == tool_call_records

    projection_response = client.get(
        f"/api/conversations/{conversation_id}/source/projection"
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert (
        projection["current"]["messages"][-1]["tool_call_records"] == tool_call_records
    )


def test_conversation_source_projection_includes_checkpoint_chains(client):
    create_response = client.post("/api/conversations", json={"title": "Projection"})
    conversation_id = create_response.json()["id"]

    first = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="hello",
                )
            ]
        },
    )
    checkpoint_user = first.json()["checkpoint_id"]

    second = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="assistant-1",
                    role="assistant",
                    content="hi there",
                )
            ]
        },
    )
    checkpoint_assistant = second.json()["checkpoint_id"]

    projection_response = client.get(
        f"/api/conversations/{conversation_id}/source/projection"
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert projection["current"]["checkpoint_id"] == checkpoint_assistant
    checkpoints = projection["checkpoints"]
    assert checkpoints[0]["checkpoint_id"] == checkpoint_assistant
    assert [message["id"] for message in checkpoints[0]["messages"]] == [
        "user-1",
        "assistant-1",
    ]
    user_checkpoint = next(
        item for item in checkpoints if item["checkpoint_id"] == checkpoint_user
    )
    assert [message["id"] for message in user_checkpoint["messages"]] == ["user-1"]


def test_conversation_source_delete_hides_removed_variant_and_selects_survivor(client):
    create_response = client.post(
        "/api/conversations", json={"title": "Delete Variant"}
    )
    conversation_id = create_response.json()["id"]

    user_response = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="user-1",
                    role="user",
                    content="hello",
                )
            ]
        },
    )
    checkpoint_user = user_response.json()["checkpoint_id"]

    assistant_old = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "messages": [
                _message_payload(
                    message_id="assistant-1",
                    role="assistant",
                    content="old branch",
                )
            ]
        },
    )
    checkpoint_old = assistant_old.json()["checkpoint_id"]

    assistant_new = client.post(
        f"/api/conversations/{conversation_id}/source/messages",
        json={
            "base_checkpoint_id": checkpoint_user,
            "messages": [
                _message_payload(
                    message_id="assistant-2",
                    role="assistant",
                    content="new branch",
                )
            ],
        },
    )
    checkpoint_new = assistant_new.json()["checkpoint_id"]

    select_old = client.put(
        f"/api/conversations/{conversation_id}/source/selection",
        json={"checkpoint_id": checkpoint_old},
    )
    assert select_old.status_code == 200

    delete_response = client.delete(
        f"/api/conversations/{conversation_id}/source/messages/assistant-1"
    )
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["selected_checkpoint_id"] == checkpoint_new
    assert [message["id"] for message in deleted["messages"]] == [
        "user-1",
        "assistant-2",
    ]

    projection_response = client.get(
        f"/api/conversations/{conversation_id}/source/projection"
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert [message["id"] for message in projection["current"]["messages"]] == [
        "user-1",
        "assistant-2",
    ]
    assert {
        message["id"]
        for checkpoint in projection["checkpoints"]
        for message in checkpoint["messages"]
    } == {"user-1", "assistant-2"}


def test_conversation_source_delete_promotes_descendants_in_visible_chain(client):
    create_response = client.post(
        "/api/conversations", json={"title": "Delete Promote"}
    )
    conversation_id = create_response.json()["id"]

    for message_id, role, content in (
        ("user-1", "user", "hello"),
        ("assistant-1", "assistant", "middle"),
        ("user-2", "user", "followup"),
        ("assistant-2", "assistant", "tail"),
    ):
        response = client.post(
            f"/api/conversations/{conversation_id}/source/messages",
            json={
                "messages": [
                    _message_payload(
                        message_id=message_id,
                        role=role,
                        content=content,
                    )
                ]
            },
        )
        assert response.status_code == 200

    delete_response = client.delete(
        f"/api/conversations/{conversation_id}/source/messages/assistant-1"
    )
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert [message["id"] for message in deleted["messages"]] == [
        "user-1",
        "user-2",
        "assistant-2",
    ]

    projection_response = client.get(
        f"/api/conversations/{conversation_id}/source/projection"
    )
    assert projection_response.status_code == 200
    projection = projection_response.json()
    assert [message["id"] for message in projection["current"]["messages"]] == [
        "user-1",
        "user-2",
        "assistant-2",
    ]
    assert {
        message["id"]
        for checkpoint in projection["checkpoints"]
        for message in checkpoint["messages"]
    } == {"user-1", "user-2", "assistant-2"}
