"""Protocol for backend-local tool providers."""
from __future__ import annotations

from typing import Any, Protocol

from models.mcp_config import McpToolInfo


class LocalToolProvider(Protocol):
    provider_id: str

    def list_tools(self) -> list[McpToolInfo]:
        """Return tools exposed by this provider."""

    async def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute one tool and return the McpManager-compatible payload."""

