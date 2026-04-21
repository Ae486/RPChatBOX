"""MCP server management endpoints."""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from models.mcp_config import (
    McpServerConfig,
    McpToolCallRequest,
    McpToolCallResponse,
)
from services.mcp_manager import get_mcp_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/mcp/servers")
async def list_servers():
    """List all MCP server configs with runtime status."""
    manager = get_mcp_manager()
    return {
        "object": "list",
        "data": [s.model_dump(mode="json") for s in manager.list_server_views()],
    }


@router.get("/api/mcp/servers/{server_id}")
async def get_server(server_id: str):
    manager = get_mcp_manager()
    server = manager.get_server_view(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")
    return server.model_dump(mode="json")


@router.put("/api/mcp/servers/{server_id}")
async def upsert_server(server_id: str, config: McpServerConfig):
    manager = get_mcp_manager()
    manager.upsert_config(config.model_copy(update={"id": server_id}))
    stored = manager.get_server_view(server_id)
    if stored is None:
        raise HTTPException(status_code=500, detail="Failed to load stored MCP server")
    return stored.model_dump(mode="json")


@router.delete("/api/mcp/servers/{server_id}")
async def delete_server(server_id: str):
    manager = get_mcp_manager()
    if manager.is_connected(server_id):
        await manager.disconnect(server_id)
    deleted = manager.delete_config(server_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")
    return {"status": "ok", "deleted": server_id}


@router.post("/api/mcp/servers/{server_id}/connect")
async def connect_server(server_id: str):
    manager = get_mcp_manager()
    try:
        await manager.connect(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Connection timed out: {exc}")
    except asyncio.CancelledError as exc:
        raise HTTPException(status_code=504, detail=f"Connection cancelled: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Connection failed: {exc}")
    return {"status": "connected", "server_id": server_id}


@router.post("/api/mcp/servers/{server_id}/disconnect")
async def disconnect_server(server_id: str):
    manager = get_mcp_manager()
    await manager.disconnect(server_id)
    return {"status": "disconnected", "server_id": server_id}


@router.get("/api/mcp/servers/{server_id}/tools")
async def list_server_tools(server_id: str):
    manager = get_mcp_manager()
    if not manager.is_connected(server_id):
        raise HTTPException(status_code=400, detail=f"Server not connected: {server_id}")
    tools = manager.get_server_tools(server_id)
    return {
        "object": "list",
        "data": [t.model_dump(mode="json") for t in tools],
    }


@router.get("/api/mcp/tools")
async def list_all_tools():
    """List all tools from all connected MCP servers."""
    manager = get_mcp_manager()
    tools = manager.get_all_tools()
    return {
        "object": "list",
        "data": [t.model_dump(mode="json") for t in tools],
    }


@router.post("/api/mcp/tools/call")
async def call_tool(payload: McpToolCallRequest):
    manager = get_mcp_manager()
    result = await manager.call_tool_by_qualified_name(
        qualified_name=payload.qualified_name,
        arguments=payload.arguments,
    )
    return McpToolCallResponse(**result).model_dump(mode="json")
