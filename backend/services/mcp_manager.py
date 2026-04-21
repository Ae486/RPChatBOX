"""MCP server connection manager and tool discovery."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from threading import RLock
from typing import Any

from config import get_settings
from models.mcp_config import (
    McpServerConfig,
    McpServerStatus,
    McpServerView,
    McpToolInfo,
)
from rp.services.local_tool_provider_registry import LocalToolProviderRegistry
from rp.tools.memory_crud_provider import MemoryCrudToolProvider

logger = logging.getLogger(__name__)
_MCP_CONNECT_TIMEOUT_SECONDS = 90


class McpManager:
    """Manage MCP server configurations, connections, and tool discovery.

    Persistence follows the same JSON-file pattern as ProviderRegistryService.
    Connections use the official Python MCP SDK (``mcp`` package).
    """

    def __init__(
        self,
        *,
        storage_path: Path | None = None,
        local_tool_provider_registry: LocalToolProviderRegistry | None = None,
        register_default_local_providers: bool = True,
    ):
        settings = get_settings()
        self._storage_path = storage_path or (settings.storage_dir / "mcp_servers.json")
        self._lock = RLock()

        # Runtime state (not persisted)
        self._sessions: dict[str, Any] = {}  # server_id → ClientSession
        self._transports: dict[str, AsyncExitStack] = {}  # server_id → lifecycle stack
        self._connection_locks: dict[str, asyncio.Lock] = {}
        self._tools_cache: dict[str, list[McpToolInfo]] = {}
        self._errors: dict[str, str] = {}
        self._local_tool_provider_registry = (
            local_tool_provider_registry or LocalToolProviderRegistry()
        )
        if register_default_local_providers:
            self._local_tool_provider_registry.register(MemoryCrudToolProvider())

    # ------------------------------------------------------------------
    # Config CRUD (persisted)
    # ------------------------------------------------------------------

    def list_configs(self) -> list[McpServerConfig]:
        with self._lock:
            return list(self._load_configs().values())

    def get_config(self, server_id: str) -> McpServerConfig | None:
        with self._lock:
            return self._load_configs().get(server_id)

    def upsert_config(self, config: McpServerConfig) -> McpServerConfig:
        with self._lock:
            configs = self._load_configs()
            existing = configs.get(config.id)
            stored = config.with_timestamps(existing=existing)
            configs[stored.id] = stored
            self._save_configs(configs)
            return stored

    def delete_config(self, server_id: str) -> bool:
        with self._lock:
            configs = self._load_configs()
            if server_id not in configs:
                return False
            del configs[server_id]
            self._save_configs(configs)
        # Clean up runtime state
        self._cleanup_runtime(server_id)
        return True

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, server_id: str) -> None:
        async with self._get_connection_lock(server_id):
            config = self.get_config(server_id)
            if config is None:
                raise ValueError(f"MCP server not found: {server_id}")

            if server_id in self._sessions:
                await self._disconnect_unlocked(server_id)

            self._errors.pop(server_id, None)
            session = None
            lifecycle_stack: AsyncExitStack | None = None

            try:
                async with asyncio.timeout(_MCP_CONNECT_TIMEOUT_SECONDS):
                    session, lifecycle_stack = await self._create_session(config)
                    await self._refresh_tools(server_id, config, session)
                self._sessions[server_id] = session
                self._transports[server_id] = lifecycle_stack
                logger.info(
                    "[MCP] connected server=%s tools=%d",
                    server_id,
                    len(self._tools_cache.get(server_id, [])),
                )
            except TimeoutError as exc:
                self._errors[server_id] = (
                    f"Connection timed out after {_MCP_CONNECT_TIMEOUT_SECONDS}s"
                )
                if lifecycle_stack is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await lifecycle_stack.aclose()
                self._cleanup_runtime(server_id, preserve_error=True)
                logger.warning("[MCP] connect timed out server=%s", server_id)
                raise TimeoutError(self._errors[server_id]) from exc
            except asyncio.CancelledError:
                self._errors[server_id] = "Connection cancelled during MCP initialization"
                if lifecycle_stack is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await lifecycle_stack.aclose()
                self._cleanup_runtime(server_id, preserve_error=True)
                logger.warning("[MCP] connect cancelled server=%s", server_id)
                raise
            except Exception as exc:
                self._errors[server_id] = self._format_runtime_error(exc)
                if lifecycle_stack is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await lifecycle_stack.aclose()
                self._cleanup_runtime(server_id, preserve_error=True)
                logger.warning("[MCP] connect failed server=%s: %s", server_id, exc)
                raise

    async def disconnect(self, server_id: str) -> None:
        async with self._get_connection_lock(server_id):
            await self._disconnect_unlocked(server_id)

    async def _disconnect_unlocked(self, server_id: str) -> None:
        session = self._sessions.pop(server_id, None)
        if session is not None:
            with suppress(Exception, asyncio.CancelledError):
                pass
        lifecycle_stack = self._transports.pop(server_id, None)
        if lifecycle_stack is not None:
            with suppress(Exception, asyncio.CancelledError):
                await lifecycle_stack.aclose()
        self._tools_cache.pop(server_id, None)
        self._errors.pop(server_id, None)
        logger.info("[MCP] disconnected server=%s", server_id)

    def is_connected(self, server_id: str) -> bool:
        return server_id in self._sessions

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def get_all_tools(self) -> list[McpToolInfo]:
        tools: list[McpToolInfo] = []
        for server_tools in self._tools_cache.values():
            tools.extend(server_tools)
        tools.extend(self._local_tool_provider_registry.list_all_tools())
        return tools

    def get_server_tools(self, server_id: str) -> list[McpToolInfo]:
        return list(self._tools_cache.get(server_id, []))

    def get_openai_tool_definitions(self) -> list[dict]:
        return [t.to_openai_tool() for t in self.get_all_tools()]

    def has_tools(self) -> bool:
        return bool(self.get_all_tools())

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        *,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool on a connected MCP server.

        Returns {"success": bool, "content": str, "error_code": str | None}.
        """
        session = self._sessions.get(server_id)
        if session is None:
            return {
                "success": False,
                "content": f"Server not connected: {server_id}",
                "error_code": "NOT_CONNECTED",
            }

        try:
            from mcp import types as mcp_types

            result = await session.call_tool(tool_name, arguments)

            content_parts: list[str] = []
            for block in result.content:
                if isinstance(block, mcp_types.TextContent):
                    content_parts.append(block.text)
                elif isinstance(block, mcp_types.ImageContent):
                    content_parts.append(f"[Image: {block.mimeType}]")
                else:
                    content_parts.append(str(block))

            return {
                "success": not result.isError,
                "content": "\n".join(content_parts),
                "error_code": "TOOL_ERROR" if result.isError else None,
            }
        except Exception as exc:
            return {
                "success": False,
                "content": f"Tool execution failed: {exc}",
                "error_code": "EXECUTION_ERROR",
            }

    async def call_tool_by_qualified_name(
        self,
        *,
        qualified_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        remote_tools: list[McpToolInfo] = []
        for server_tools in self._tools_cache.values():
            remote_tools.extend(server_tools)

        for tool in remote_tools:
            if qualified_name in (tool.qualified_name, tool.raw_qualified_name):
                return await self.call_tool(
                    server_id=tool.server_id,
                    tool_name=tool.name,
                    arguments=arguments,
                )

        local_result = await self._local_tool_provider_registry.call_tool_by_qualified_name(
            qualified_name=qualified_name,
            arguments=arguments,
        )
        if local_result is not None:
            return local_result

        server_id, tool_name = McpToolInfo.parse_qualified_name(qualified_name)
        if server_id is None:
            # Single-server mode: pick first connected
            for sid in self._sessions:
                server_id = sid
                break
        if server_id is None:
            return {
                "success": False,
                "content": "No MCP server connected",
                "error_code": "NO_SERVER",
            }
        return await self.call_tool(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_statuses(self) -> list[McpServerStatus]:
        configs = self.list_configs()
        statuses: list[McpServerStatus] = []
        for config in configs:
            statuses.append(
                McpServerStatus(
                    id=config.id,
                    name=config.name,
                    transport=config.transport,
                    enabled=config.enabled,
                    connected=self.is_connected(config.id),
                    tool_count=len(self._tools_cache.get(config.id, [])),
                    error=self._errors.get(config.id),
                )
            )
        return statuses

    def get_server_view(self, server_id: str) -> McpServerView | None:
        config = self.get_config(server_id)
        if config is None:
            return None
        return McpServerView.from_config_and_status(
            config,
            connected=self.is_connected(server_id),
            tool_count=len(self._tools_cache.get(server_id, [])),
            error=self._errors.get(server_id),
        )

    def list_server_views(self) -> list[McpServerView]:
        return [
            McpServerView.from_config_and_status(
                config,
                connected=self.is_connected(config.id),
                tool_count=len(self._tools_cache.get(config.id, [])),
                error=self._errors.get(config.id),
            )
            for config in self.list_configs()
        ]

    async def connect_enabled_servers(self) -> None:
        for config in self.list_configs():
            if not config.enabled:
                continue
            try:
                await self.connect(config.id)
            except Exception as exc:
                logger.warning(
                    "[MCP] startup connect failed server=%s: %s",
                    config.id,
                    exc,
                )

    async def disconnect_all(self) -> None:
        for server_id in list(self._sessions.keys()):
            await self.disconnect(server_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _create_session(self, config: McpServerConfig) -> tuple[Any, AsyncExitStack]:
        """Create an MCP ClientSession using the appropriate transport."""
        from mcp import ClientSession

        lifecycle_stack = AsyncExitStack()
        try:
            if config.transport == "stdio":
                if not config.command:
                    raise ValueError("Command is required for stdio transport")
                from mcp.client.stdio import stdio_client, StdioServerParameters

                params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=config.env,
                )
                read_stream, write_stream = await lifecycle_stack.enter_async_context(
                    stdio_client(params)
                )

                session = await lifecycle_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                return session, lifecycle_stack

            if config.transport == "streamable_http":
                if not config.url:
                    raise ValueError("URL is required for streamable_http transport")
                import httpx
                from mcp.client.streamable_http import streamable_http_client

                http_client = await lifecycle_stack.enter_async_context(
                    httpx.AsyncClient(
                        follow_redirects=True,
                        headers=config.headers or None,
                        timeout=httpx.Timeout(30.0, read=300.0),
                    )
                )

                read_stream, write_stream, _ = await lifecycle_stack.enter_async_context(
                    streamable_http_client(
                        config.url,
                        http_client=http_client,
                    )
                )

                session = await lifecycle_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                return session, lifecycle_stack

            raise ValueError(f"Unsupported transport: {config.transport}")
        except BaseException:
            with suppress(Exception, asyncio.CancelledError):
                await lifecycle_stack.aclose()
            raise

    async def _refresh_tools(
        self,
        server_id: str,
        config: McpServerConfig,
        session: Any,
    ) -> None:
        result = await session.list_tools()
        self._tools_cache[server_id] = [
            McpToolInfo(
                server_id=server_id,
                server_name=config.name,
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else None,
            )
            for tool in result.tools
        ]

    def _cleanup_runtime(self, server_id: str, *, preserve_error: bool = False) -> None:
        self._sessions.pop(server_id, None)
        self._transports.pop(server_id, None)
        self._tools_cache.pop(server_id, None)
        if not preserve_error:
            self._errors.pop(server_id, None)

    def _get_connection_lock(self, server_id: str) -> asyncio.Lock:
        lock = self._connection_locks.get(server_id)
        if lock is None:
            lock = asyncio.Lock()
            self._connection_locks[server_id] = lock
        return lock

    @staticmethod
    def _format_runtime_error(exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return exc.__class__.__name__

    def _load_configs(self) -> dict[str, McpServerConfig]:
        if not self._storage_path.exists():
            return {}
        raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        entries = raw if isinstance(raw, list) else raw.get("servers", [])
        configs: dict[str, McpServerConfig] = {}
        for item in entries:
            config = McpServerConfig(**item)
            configs[config.id] = config
        return configs

    def _save_configs(self, configs: dict[str, McpServerConfig]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [c.model_dump(mode="json") for c in configs.values()]
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


_mcp_manager: McpManager | None = None


def get_mcp_manager() -> McpManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = McpManager()
    return _mcp_manager


def reset_mcp_manager() -> None:
    global _mcp_manager
    _mcp_manager = None
