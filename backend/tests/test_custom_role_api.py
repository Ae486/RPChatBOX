"""Contract tests for backend custom role endpoints."""


def test_custom_role_crud_flow(client):
    create_response = client.post(
        "/api/custom-roles",
        json={
            "id": "role-custom-1",
            "name": "Writer",
            "description": "Creative fiction writer",
            "system_prompt": "You are a creative fiction writer.",
            "icon": "✍️",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["id"] == "role-custom-1"
    assert created["name"] == "Writer"

    list_response = client.get("/api/custom-roles")
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert listed[0]["id"] == "role-custom-1"

    get_response = client.get("/api/custom-roles/role-custom-1")
    assert get_response.status_code == 200
    assert get_response.json()["system_prompt"] == "You are a creative fiction writer."

    update_response = client.put(
        "/api/custom-roles/role-custom-1",
        json={
            "name": "Writer Updated",
            "description": "Creative fiction writer",
            "system_prompt": "You are an updated fiction writer.",
            "icon": "🖋️",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Writer Updated"
    assert updated["icon"] == "🖋️"

    delete_response = client.delete("/api/custom-roles/role-custom-1")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == "role-custom-1"

    missing_response = client.get("/api/custom-roles/role-custom-1")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["error"]["code"] == "custom_role_not_found"
