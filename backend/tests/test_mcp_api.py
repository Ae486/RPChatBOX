"""Contract tests for backend MCP control-plane endpoints."""
import asyncio

from models.mcp_config import McpToolInfo
from services.mcp_manager import get_mcp_manager


def test_mcp_server_crud_returns_full_server_view(client):
    payload = {
        "id": "srv-http",
        "name": "HTTP Tools",
        "transport": "streamable_http",
        "enabled": True,
        "url": "http://127.0.0.1:8787/mcp",
        "headers": {"Authorization": "Bearer demo"},
    }

    upsert_response = client.put("/api/mcp/servers/srv-http", json=payload)
    assert upsert_response.status_code == 200
    stored = upsert_response.json()
    assert stored["id"] == "srv-http"
    assert stored["transport"] == "streamable_http"
    assert stored["url"] == "http://127.0.0.1:8787/mcp"
    assert stored["headers"] == {"Authorization": "Bearer demo"}
    assert stored["connected"] is False
    assert stored["tool_count"] == 0

    list_response = client.get("/api/mcp/servers")
    assert list_response.status_code == 200
    servers = list_response.json()["data"]
    assert len(servers) == 1
    assert servers[0]["id"] == "srv-http"
    assert servers[0]["url"] == "http://127.0.0.1:8787/mcp"
    assert servers[0]["connected"] is False

    get_response = client.get("/api/mcp/servers/srv-http")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == "srv-http"
    assert fetched["url"] == "http://127.0.0.1:8787/mcp"
    assert fetched["headers"] == {"Authorization": "Bearer demo"}
    assert fetched["connected"] is False


def test_mcp_connect_and_tools_listing(client, monkeypatch):
    client.put(
        "/api/mcp/servers/srv-stdio",
        json={
            "id": "srv-stdio",
            "name": "Filesystem",
            "transport": "stdio",
            "enabled": True,
            "command": "python",
            "args": ["-m", "demo_server"],
        },
    )

    manager = get_mcp_manager()

    async def fake_connect(server_id: str) -> None:
        manager._sessions[server_id] = object()
        manager._tools_cache[server_id] = [
            McpToolInfo(
                server_id=server_id,
                server_name="Filesystem",
                name="read_file",
                description="Read one file",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            )
        ]

    monkeypatch.setattr(manager, "connect", fake_connect)

    connect_response = client.post("/api/mcp/servers/srv-stdio/connect")
    assert connect_response.status_code == 200

    server_response = client.get("/api/mcp/servers/srv-stdio")
    assert server_response.status_code == 200
    server = server_response.json()
    assert server["connected"] is True
    assert server["tool_count"] == 1

    tools_response = client.get("/api/mcp/servers/srv-stdio/tools")
    assert tools_response.status_code == 200
    tools = tools_response.json()["data"]
    assert len(tools) == 1
    assert tools[0]["name"] == "read_file"
    assert tools[0]["server_id"] == "srv-stdio"


def test_mcp_call_tool_endpoint(client, monkeypatch):
    manager = get_mcp_manager()

    async def fake_call(*, qualified_name: str, arguments: dict):
        assert qualified_name == "srv-http__web_search"
        assert arguments == {"q": "chatbox"}
        return {
            "success": True,
            "content": "Search result: chatbox",
            "error_code": None,
        }

    monkeypatch.setattr(manager, "call_tool_by_qualified_name", fake_call)

    response = client.post(
        "/api/mcp/tools/call",
        json={
            "qualified_name": "srv-http__web_search",
            "arguments": {"q": "chatbox"},
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result == {
        "success": True,
        "content": "Search result: chatbox",
        "error_code": None,
    }


def test_mcp_connect_timeout_returns_504(client, monkeypatch):
    client.put(
        "/api/mcp/servers/srv-timeout",
        json={
            "id": "srv-timeout",
            "name": "Slow Server",
            "transport": "streamable_http",
            "enabled": True,
            "url": "https://example.com/mcp",
        },
    )

    manager = get_mcp_manager()

    async def fake_connect(server_id: str) -> None:
        raise TimeoutError("Connection timed out after 90s")

    monkeypatch.setattr(manager, "connect", fake_connect)

    response = client.post("/api/mcp/servers/srv-timeout/connect")
    assert response.status_code == 504
    assert "Connection timed out" in response.json()["detail"]


def test_mcp_connect_cancelled_error_returns_504(client, monkeypatch):
    client.put(
        "/api/mcp/servers/srv-cancelled",
        json={
            "id": "srv-cancelled",
            "name": "Cancelled Server",
            "transport": "streamable_http",
            "enabled": True,
            "url": "https://example.com/mcp",
        },
    )

    manager = get_mcp_manager()

    async def fake_connect(server_id: str) -> None:
        raise asyncio.CancelledError("cancelled while initializing")

    monkeypatch.setattr(manager, "connect", fake_connect)

    response = client.post("/api/mcp/servers/srv-cancelled/connect")
    assert response.status_code == 504
    assert "Connection cancelled" in response.json()["detail"]
