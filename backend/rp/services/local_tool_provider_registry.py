"""Registry for backend-local tool providers."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from models.mcp_config import McpToolInfo
from rp.tools.local_tool_provider import LocalToolProvider


class LocalToolProviderRegistry:
    """Keep local providers opaque to the shared tool runtime."""

    def __init__(self) -> None:
        self._providers: OrderedDict[str, LocalToolProvider] = OrderedDict()

    def register(self, provider: LocalToolProvider) -> None:
        self._providers[provider.provider_id] = provider

    def list_all_tools(self) -> list[McpToolInfo]:
        tools: list[McpToolInfo] = []
        for provider in self._providers.values():
            tools.extend(provider.list_tools())
        return tools

    def has_tools(self) -> bool:
        return any(provider.list_tools() for provider in self._providers.values())

    async def call_tool_by_qualified_name(
        self,
        *,
        qualified_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        for tool in self.list_all_tools():
            if qualified_name in (tool.qualified_name, tool.raw_qualified_name):
                provider = self._providers.get(tool.server_id)
                if provider is None:
                    return None
                return await provider.call_tool(
                    tool_name=tool.name,
                    arguments=arguments,
                )
        return None

