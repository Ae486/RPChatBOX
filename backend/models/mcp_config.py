"""MCP server configuration models."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """Persistent MCP server configuration."""

    id: str
    name: str
    transport: Literal["stdio", "streamable_http"]
    enabled: bool = True

    # stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None

    # streamable_http transport
    url: str | None = None
    headers: dict[str, str] | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    def with_timestamps(
        self, *, existing: McpServerConfig | None = None
    ) -> McpServerConfig:
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={
                "created_at": self.created_at
                or (existing.created_at if existing else None)
                or now,
                "updated_at": now,
            }
        )


class McpServerStatus(BaseModel):
    """Runtime status of an MCP server (not persisted)."""

    id: str
    name: str
    transport: str
    enabled: bool
    connected: bool = False
    tool_count: int = 0
    error: str | None = None


class McpServerView(BaseModel):
    """Frontend-facing MCP server config merged with runtime status."""

    id: str
    name: str
    transport: Literal["stdio", "streamable_http"]
    enabled: bool = True
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    connected: bool = False
    tool_count: int = 0
    error: str | None = None

    @classmethod
    def from_config_and_status(
        cls,
        config: McpServerConfig,
        *,
        connected: bool = False,
        tool_count: int = 0,
        error: str | None = None,
    ) -> "McpServerView":
        return cls(
            id=config.id,
            name=config.name,
            transport=config.transport,
            enabled=config.enabled,
            command=config.command,
            args=list(config.args),
            env=dict(config.env) if config.env is not None else None,
            url=config.url,
            headers=dict(config.headers) if config.headers is not None else None,
            created_at=config.created_at,
            updated_at=config.updated_at,
            connected=connected,
            tool_count=tool_count,
            error=error,
        )


class McpToolInfo(BaseModel):
    """Tool discovered from a connected MCP server."""

    server_id: str
    server_name: str
    name: str
    description: str = ""
    input_schema: dict | None = None

    _SAFE_FUNCTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,63}$")
    _FUNCTION_NAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.:-]+")

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function-calling tool definition."""
        description = self.description or f"Tool: {self.name}"
        if self.server_name:
            description = f"[{self.server_name}] {description}"
        return {
            "type": "function",
            "function": {
                "name": self.qualified_name,
                "description": description,
                "parameters": self.sanitized_input_schema,
            },
        }

    @property
    def sanitized_input_schema(self) -> dict[str, Any]:
        """Provider-safe tool schema with refs/unions flattened for upstream LLMs."""
        return _sanitize_tool_schema(
            self.input_schema
            or {
                "type": "object",
                "properties": {},
            }
        )

    @property
    def raw_qualified_name(self) -> str:
        """Original namespaced tool name."""
        return f"{self.server_id}__{self.name}"

    @property
    def qualified_name(self) -> str:
        """LLM-safe tool name for providers with stricter function naming rules."""
        raw_name = self.raw_qualified_name
        if self._SAFE_FUNCTION_NAME_RE.fullmatch(raw_name):
            return raw_name

        normalized = self._FUNCTION_NAME_SANITIZE_RE.sub("_", raw_name)
        if not normalized or not re.match(r"^[A-Za-z_]", normalized):
            normalized = f"mcp_{normalized}"
        if self._SAFE_FUNCTION_NAME_RE.fullmatch(normalized):
            return normalized

        safe_tool_name = self._FUNCTION_NAME_SANITIZE_RE.sub("_", self.name).strip("_.:-")
        if not safe_tool_name:
            safe_tool_name = "tool"
        digest = hashlib.sha1(raw_name.encode("utf-8")).hexdigest()[:10]
        candidate = f"mcp_{digest}_{safe_tool_name}"[:64]
        if self._SAFE_FUNCTION_NAME_RE.fullmatch(candidate):
            return candidate
        return f"mcp_{digest}"

    @staticmethod
    def parse_qualified_name(qualified: str) -> tuple[str | None, str]:
        """Split 'serverId__toolName' → (serverId, toolName)."""
        parts = qualified.split("__", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, qualified


class McpToolCallRequest(BaseModel):
    """Execute one MCP tool by qualified name."""

    qualified_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpToolCallResponse(BaseModel):
    """Frontend-facing MCP tool execution result."""

    success: bool
    content: str
    error_code: str | None = None


_FORBIDDEN_SCHEMA_KEYS = {"$defs", "$ref", "$schema", "allOf", "anyOf", "oneOf"}
_SCHEMA_METADATA_KEYS = {
    "title",
    "default",
    "examples",
    "example",
    "deprecated",
    "readOnly",
    "writeOnly",
}


def _sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    root = deepcopy(schema)
    sanitized = _sanitize_schema_node(root, root_schema=root)
    if sanitized.get("type") != "object":
        return {
            "type": "object",
            "properties": {},
            "description": sanitized.get("description") or "Tool arguments",
        }
    sanitized.setdefault("properties", {})
    return sanitized


def _sanitize_schema_node(node: Any, *, root_schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {"type": "string"}

    if "$ref" in node:
        resolved = _resolve_local_ref(str(node["$ref"]), root_schema)
        merged = {
            **resolved,
            **{key: value for key, value in node.items() if key != "$ref"},
        }
        return _sanitize_schema_node(merged, root_schema=root_schema)

    union_key = next((key for key in ("anyOf", "oneOf", "allOf") if key in node), None)
    if union_key is not None:
        return _sanitize_union_schema(node, root_schema=root_schema, union_key=union_key)

    node_type = _normalize_schema_type(node)
    description = _normalize_description(node)

    if node_type == "object":
        properties: dict[str, Any] = {}
        raw_properties = node.get("properties")
        if isinstance(raw_properties, dict):
            for key, value in raw_properties.items():
                properties[key] = _sanitize_schema_node(value, root_schema=root_schema)
        sanitized: dict[str, Any] = {"type": "object"}
        if description:
            sanitized["description"] = description
        sanitized["properties"] = properties
        required = node.get("required")
        if isinstance(required, list):
            filtered_required = [
                item for item in required if isinstance(item, str) and item in properties
            ]
            if filtered_required:
                sanitized["required"] = filtered_required
        return sanitized

    if node_type == "array":
        items = _sanitize_schema_node(node.get("items", {}), root_schema=root_schema)
        sanitized = {"type": "array", "items": items}
        if description:
            sanitized["description"] = description
        return sanitized

    if node_type in {"string", "number", "integer", "boolean"}:
        sanitized = {"type": node_type}
        enum_values = node.get("enum")
        if isinstance(enum_values, list) and enum_values:
            sanitized["enum"] = list(enum_values)
        if description:
            sanitized["description"] = description
        return sanitized

    fallback = {"type": "string"}
    if description:
        fallback["description"] = description
    return fallback


def _sanitize_union_schema(
    node: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    union_key: str,
) -> dict[str, Any]:
    variants = node.get(union_key)
    if not isinstance(variants, list) or not variants:
        fallback = {"type": "string"}
        description = _normalize_description(node)
        if description:
            fallback["description"] = description
        return fallback

    non_null_variants = [
        variant for variant in variants if not _is_null_schema(variant)
    ]
    if len(non_null_variants) == 1:
        sanitized = _sanitize_schema_node(non_null_variants[0], root_schema=root_schema)
    else:
        sanitized_variants = [
            _sanitize_schema_node(variant, root_schema=root_schema)
            for variant in non_null_variants
        ]
        sanitized = _pick_union_fallback(sanitized_variants)

    description = _normalize_description(node)
    if description and "description" not in sanitized:
        sanitized["description"] = description
    return sanitized


def _pick_union_fallback(variants: list[dict[str, Any]]) -> dict[str, Any]:
    for candidate_type in ("object", "array", "string", "number", "integer", "boolean"):
        for variant in variants:
            if variant.get("type") == candidate_type:
                return dict(variant)
    return {"type": "string"}


def _resolve_local_ref(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {"type": "object", "properties": {}}

    current: Any = root_schema
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            return {"type": "object", "properties": {}}
        current = current[key]
    if isinstance(current, dict):
        return deepcopy(current)
    return {"type": "object", "properties": {}}


def _normalize_schema_type(node: dict[str, Any]) -> str:
    raw_type = node.get("type")
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw_type, list):
        candidates = [item for item in raw_type if isinstance(item, str) and item != "null"]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            return candidates[0]
    if isinstance(node.get("properties"), dict):
        return "object"
    if "items" in node:
        return "array"
    if "enum" in node:
        enum_values = node.get("enum")
        if isinstance(enum_values, list) and enum_values:
            first = enum_values[0]
            if isinstance(first, bool):
                return "boolean"
            if isinstance(first, int) and not isinstance(first, bool):
                return "integer"
            if isinstance(first, float):
                return "number"
        return "string"
    if "additionalProperties" in node:
        return "object"
    return "string"


def _normalize_description(node: dict[str, Any]) -> str | None:
    description = node.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _is_null_schema(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    raw_type = node.get("type")
    if raw_type == "null":
        return True
    if isinstance(raw_type, list) and "null" in raw_type and len(raw_type) == 1:
        return True
    return False
