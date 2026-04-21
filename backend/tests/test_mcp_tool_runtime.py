"""Tests for MCP manager and tool runtime service."""
from __future__ import annotations

import asyncio
import json
import pytest
from pydantic import BaseModel, ConfigDict, Field

from models.mcp_config import McpServerConfig, McpToolInfo
from services.mcp_manager import McpManager
from services.tool_runtime_service import ToolRuntimeService


# ---------------------------------------------------------------------------
# McpServerConfig tests
# ---------------------------------------------------------------------------

def test_mcp_server_config_roundtrip():
    config = McpServerConfig(
        id="test-server",
        name="Test Server",
        transport="stdio",
        command="python",
        args=["-m", "mcp_server"],
    )
    dumped = config.model_dump(mode="json")
    restored = McpServerConfig(**dumped)
    assert restored.id == "test-server"
    assert restored.transport == "stdio"
    assert restored.args == ["-m", "mcp_server"]


def test_mcp_server_config_with_timestamps():
    config = McpServerConfig(
        id="ts-test", name="TS", transport="streamable_http", url="http://localhost:8080"
    )
    stored = config.with_timestamps()
    assert stored.created_at is not None
    assert stored.updated_at is not None

    updated = stored.model_copy(update={"name": "Updated"})
    re_stored = updated.with_timestamps(existing=stored)
    assert re_stored.created_at == stored.created_at
    assert re_stored.updated_at >= stored.updated_at


# ---------------------------------------------------------------------------
# McpToolInfo tests
# ---------------------------------------------------------------------------

def test_tool_info_to_openai_format():
    tool = McpToolInfo(
        server_id="srv1",
        server_name="Server 1",
        name="web_search",
        description="Search the web",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
    )
    openai_def = tool.to_openai_tool()
    assert openai_def["type"] == "function"
    assert openai_def["function"]["name"] == "srv1__web_search"
    assert openai_def["function"]["description"] == "[Server 1] Search the web"
    assert openai_def["function"]["parameters"]["properties"]["q"]["type"] == "string"


def test_tool_info_qualified_name_prefixes_numeric_server_ids():
    tool = McpToolInfo(
        server_id="1770224826732",
        server_name="DeepWiki",
        name="ask_question",
        description="Ask DeepWiki about a repo",
        input_schema={"type": "object"},
    )

    assert tool.raw_qualified_name == "1770224826732__ask_question"
    assert tool.qualified_name == "mcp_1770224826732__ask_question"


class _NestedPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = None
    labels: list[str] = Field(default_factory=list)


class _ComplexToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    patch: _NestedPatch
    metadata: dict[str, object] = Field(default_factory=dict)
    items: list[_NestedPatch] = Field(default_factory=list)


def _contains_forbidden_schema_keys(node) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"$defs", "$ref", "anyOf", "oneOf", "allOf"}:
                return True
            if _contains_forbidden_schema_keys(value):
                return True
    elif isinstance(node, list):
        return any(_contains_forbidden_schema_keys(item) for item in node)
    return False


def test_tool_info_sanitizes_pydantic_schema_for_upstream_tool_calling():
    tool = McpToolInfo(
        server_id="rp_setup",
        server_name="RP Setup",
        name="setup.patch.story_config",
        description="Update story config",
        input_schema=_ComplexToolInput.model_json_schema(),
    )

    openai_def = tool.to_openai_tool()
    parameters = openai_def["function"]["parameters"]

    assert parameters["type"] == "object"
    assert "workspace_id" in parameters["properties"]
    assert parameters["properties"]["patch"]["type"] == "object"
    assert parameters["properties"]["items"]["type"] == "array"
    assert parameters["properties"]["items"]["items"]["type"] == "object"
    assert parameters["properties"]["metadata"]["type"] == "object"
    assert _contains_forbidden_schema_keys(parameters) is False


def test_qualified_name_parse():
    server_id, name = McpToolInfo.parse_qualified_name("srv1__web_search")
    assert server_id == "srv1"
    assert name == "web_search"

    server_id, name = McpToolInfo.parse_qualified_name("plain_tool")
    assert server_id is None
    assert name == "plain_tool"


# ---------------------------------------------------------------------------
# McpManager persistence tests
# ---------------------------------------------------------------------------

def test_mcp_manager_config_crud(tmp_path):
    manager = McpManager(storage_path=tmp_path / "mcp.json")

    assert manager.list_configs() == []

    config = McpServerConfig(
        id="test", name="Test", transport="stdio", command="echo"
    )
    stored = manager.upsert_config(config)
    assert stored.created_at is not None

    assert len(manager.list_configs()) == 1
    assert manager.get_config("test") is not None

    deleted = manager.delete_config("test")
    assert deleted is True
    assert manager.list_configs() == []


def test_mcp_manager_persistence_survives_reload(tmp_path):
    path = tmp_path / "mcp.json"

    m1 = McpManager(storage_path=path)
    m1.upsert_config(McpServerConfig(
        id="persist", name="Persist", transport="stdio", command="echo"
    ))

    m2 = McpManager(storage_path=path)
    assert len(m2.list_configs()) == 1
    assert m2.get_config("persist").name == "Persist"


@pytest.mark.asyncio
async def test_mcp_manager_preserves_error_after_timeout(tmp_path, monkeypatch):
    manager = McpManager(storage_path=tmp_path / "mcp.json")
    manager.upsert_config(
        McpServerConfig(
            id="srv-timeout",
            name="Timeout Server",
            transport="streamable_http",
            url="https://example.com/mcp",
        )
    )

    class DummyLifecycleStack:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    lifecycle_stack = DummyLifecycleStack()

    async def fake_create_session(config):
        return object(), lifecycle_stack

    async def fake_refresh_tools(server_id, config, session):
        raise TimeoutError("slow server")

    monkeypatch.setattr(manager, "_create_session", fake_create_session)
    monkeypatch.setattr(manager, "_refresh_tools", fake_refresh_tools)

    with pytest.raises(TimeoutError):
        await manager.connect("srv-timeout")

    view = manager.get_server_view("srv-timeout")
    assert view is not None
    assert view.connected is False
    assert view.error is not None
    assert "timed out" in view.error
    assert lifecycle_stack.closed is True


@pytest.mark.asyncio
async def test_mcp_manager_preserves_error_after_cancellation(tmp_path, monkeypatch):
    manager = McpManager(storage_path=tmp_path / "mcp.json")
    manager.upsert_config(
        McpServerConfig(
            id="srv-cancelled",
            name="Cancelled Server",
            transport="streamable_http",
            url="https://example.com/mcp",
        )
    )

    class DummyLifecycleStack:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    lifecycle_stack = DummyLifecycleStack()

    async def fake_create_session(config):
        return object(), lifecycle_stack

    async def fake_refresh_tools(server_id, config, session):
        raise asyncio.CancelledError("cancelled while initializing")

    monkeypatch.setattr(manager, "_create_session", fake_create_session)
    monkeypatch.setattr(manager, "_refresh_tools", fake_refresh_tools)

    with pytest.raises(asyncio.CancelledError):
        await manager.connect("srv-cancelled")

    view = manager.get_server_view("srv-cancelled")
    assert view is not None
    assert view.connected is False
    assert view.error == "Connection cancelled during MCP initialization"
    assert lifecycle_stack.closed is True


@pytest.mark.asyncio
async def test_mcp_manager_call_tool_by_safe_qualified_name_alias(tmp_path):
    manager = McpManager(storage_path=tmp_path / "mcp.json")
    manager._tools_cache = {
        "1770224826732": [
            McpToolInfo(
                server_id="1770224826732",
                server_name="DeepWiki",
                name="ask_question",
                description="Ask DeepWiki about a repo",
                input_schema={"type": "object"},
            )
        ]
    }

    async def mock_call_tool(*, server_id, tool_name, arguments):
        assert server_id == "1770224826732"
        assert tool_name == "ask_question"
        assert arguments == {"repoName": "owner/repo", "question": "summary"}
        return {"success": True, "content": "ok", "error_code": None}

    manager.call_tool = mock_call_tool

    result = await manager.call_tool_by_qualified_name(
        qualified_name="mcp_1770224826732__ask_question",
        arguments={"repoName": "owner/repo", "question": "summary"},
    )

    assert result == {"success": True, "content": "ok", "error_code": None}


# ---------------------------------------------------------------------------
# ToolRuntimeService unit tests
# ---------------------------------------------------------------------------

def test_tool_runtime_parse_sse_payload():
    assert ToolRuntimeService._parse_sse_payload("data: {\"type\":\"text_delta\",\"delta\":\"hi\"}\n\n") == {
        "type": "text_delta",
        "delta": "hi",
    }
    assert ToolRuntimeService._parse_sse_payload("data: [DONE]\n\n") is None
    assert ToolRuntimeService._parse_sse_payload("not-sse") is None
    assert ToolRuntimeService._parse_sse_payload("data: invalid-json\n\n") is None


def test_tool_runtime_emit_helpers():
    typed = ToolRuntimeService._emit_typed({"type": "tool_started", "call_id": "c1"})
    assert typed.startswith("data: ")
    payload = json.loads(typed[6:])
    assert payload["type"] == "tool_started"
    assert payload["call_id"] == "c1"

    done = ToolRuntimeService._emit_done()
    assert json.loads(done[6:]) == {"type": "done"}


@pytest.mark.asyncio
async def test_tool_runtime_passthrough_without_tools():
    """When LLM returns no tool_calls, events pass through and end with done."""
    from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig

    # Mock LLM service that returns text only (no tool_calls)
    class MockLLMService:
        async def chat_completion_stream(self, request):
            yield 'data: {"type":"text_delta","delta":"Hello"}\n\n'
            yield 'data: {"type":"done"}\n\n'

    manager = McpManager(storage_path=None)
    # Override _load_configs / _save_configs for in-memory
    manager._load_configs = lambda: {}
    manager._save_configs = lambda c: None

    service = ToolRuntimeService(mcp_manager=manager)

    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hi")],
        stream=True,
        stream_event_mode="typed",
        provider=ProviderConfig(
            type="openai",
            api_key="test",
            api_url="https://api.openai.com/v1",
        ),
    )

    chunks = []
    async for chunk in service.chat_completion_stream(request, llm_service=MockLLMService()):
        chunks.append(chunk)

    payloads = [json.loads(c[6:]) for c in chunks if c.startswith("data: ")]
    types = [p["type"] for p in payloads]

    assert types == ["text_delta", "done"]
    assert payloads[0]["delta"] == "Hello"


@pytest.mark.asyncio
async def test_tool_runtime_non_stream_passthrough_without_tools():
    """When LLM returns a final answer directly, tool runtime returns it unchanged."""
    from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig

    class MockLLMService:
        async def chat_completion(self, request):
            return {
                "id": "chatcmpl-final",
                "object": "chat.completion",
                "created": 123,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            }

    manager = McpManager(storage_path=None)
    manager._load_configs = lambda: {}
    manager._save_configs = lambda c: None

    service = ToolRuntimeService(mcp_manager=manager)
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hi")],
        stream=False,
        provider=ProviderConfig(
            type="openai",
            api_key="test",
            api_url="https://api.openai.com/v1",
        ),
    )

    result = await service.chat_completion(request, llm_service=MockLLMService())

    assert result["choices"][0]["message"]["content"] == "Hello"
    assert result["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


@pytest.mark.asyncio
async def test_tool_runtime_executes_tool_call_and_continues():
    """When LLM returns tool_calls, service executes them and does another round."""
    from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig

    call_count = 0

    class MockLLMService:
        async def chat_completion_stream(self, request):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First round: model requests a tool call
                yield 'data: {"type":"text_delta","delta":"Let me search"}\n\n'
                yield 'data: {"type":"tool_call","tool_calls":[{"id":"call_1","function":{"name":"search","arguments":"{\\"q\\":\\"test\\"}"}}]}\n\n'
                yield 'data: {"type":"done"}\n\n'
            else:
                # Second round: model gives final answer
                yield 'data: {"type":"text_delta","delta":"Found results"}\n\n'
                yield 'data: {"type":"done"}\n\n'

    manager = McpManager(storage_path=None)
    manager._load_configs = lambda: {}
    manager._save_configs = lambda c: None
    # Mock tool execution
    async def mock_call(*, qualified_name, arguments):
        return {"success": True, "content": "Search result: test data", "error_code": None}
    manager.call_tool_by_qualified_name = mock_call

    service = ToolRuntimeService(mcp_manager=manager)

    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Search for test")],
        stream=True,
        stream_event_mode="typed",
        provider=ProviderConfig(
            type="openai",
            api_key="test",
            api_url="https://api.openai.com/v1",
        ),
    )

    chunks = []
    async for chunk in service.chat_completion_stream(request, llm_service=MockLLMService()):
        chunks.append(chunk)

    payloads = [json.loads(c[6:]) for c in chunks if c.startswith("data: ")]
    types = [p["type"] for p in payloads]

    # Expected: text → tool_call → tool_started → tool_result → text → done
    assert "text_delta" in types
    assert "tool_call" in types
    assert "tool_started" in types
    assert "tool_result" in types
    assert types[-1] == "done"
    assert call_count == 2

    # Verify tool_result content
    result_payload = next(p for p in payloads if p["type"] == "tool_result")
    assert result_payload["call_id"] == "call_1"
    assert "Search result" in result_payload["result"]


@pytest.mark.asyncio
async def test_tool_runtime_stream_merges_fragmented_tool_call_deltas():
    """Streaming tool runtime should merge partial tool_call deltas before execution."""
    from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig

    call_count = 0

    class MockLLMService:
        async def chat_completion_stream(self, request):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                yield 'data: {"type":"tool_call","tool_calls":[{"index":0,"id":"call_1","type":"function","thought_signature":"sig-1","function":{"name":"search"}}]}\n\n'
                yield 'data: {"type":"tool_call","tool_calls":[{"index":0,"function":{"arguments":"{\\"q\\":\\"te"}}]}\n\n'
                yield 'data: {"type":"tool_call","tool_calls":[{"index":0,"function":{"arguments":"st\\"}"}}]}\n\n'
                yield 'data: {"type":"done"}\n\n'
            else:
                yield 'data: {"type":"text_delta","delta":"Found results"}\n\n'
                yield 'data: {"type":"done"}\n\n'

    manager = McpManager(storage_path=None)
    manager._load_configs = lambda: {}
    manager._save_configs = lambda c: None

    captured = {}

    async def mock_call(*, qualified_name, arguments):
        captured["qualified_name"] = qualified_name
        captured["arguments"] = arguments
        return {"success": True, "content": "Search result: test data", "error_code": None}

    manager.call_tool_by_qualified_name = mock_call

    service = ToolRuntimeService(mcp_manager=manager)
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Search for test")],
        stream=True,
        stream_event_mode="typed",
        provider=ProviderConfig(
            type="openai",
            api_key="test",
            api_url="https://api.openai.com/v1",
        ),
    )

    chunks = []
    async for chunk in service.chat_completion_stream(request, llm_service=MockLLMService()):
        chunks.append(chunk)

    payloads = [json.loads(c[6:]) for c in chunks if c.startswith("data: ")]
    result_payload = next(p for p in payloads if p["type"] == "tool_result")

    assert call_count == 2
    assert captured == {
        "qualified_name": "search",
        "arguments": {"q": "test"},
    }
    assert result_payload["call_id"] == "call_1"
    assert result_payload["tool_name"] == "search"


@pytest.mark.asyncio
async def test_tool_runtime_non_stream_executes_tool_call_and_continues():
    """Non-streaming tool runtime should execute tools and return the final answer."""
    from models.chat import ChatCompletionRequest, ChatMessage, ProviderConfig

    call_count = 0
    captured_requests = []

    class MockLLMService:
        async def chat_completion(self, request):
            nonlocal call_count
            call_count += 1
            captured_requests.append(request)

            if call_count == 1:
                return {
                    "id": "chatcmpl-tool-1",
                    "object": "chat.completion",
                    "created": 123,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "thought_signature": "sig-1",
                                        "function": {
                                            "name": "search",
                                            "arguments": "{\"q\":\"test\"}",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 4,
                        "total_tokens": 14,
                    },
                }

            return {
                "id": "chatcmpl-tool-2",
                "object": "chat.completion",
                "created": 124,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Found results",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 6,
                    "total_tokens": 18,
                },
            }

    manager = McpManager(storage_path=None)
    manager._load_configs = lambda: {}
    manager._save_configs = lambda c: None

    async def mock_call(*, qualified_name, arguments):
        assert qualified_name == "search"
        assert arguments == {"q": "test"}
        return {
            "success": True,
            "content": "Search result: test data",
            "error_code": None,
        }

    manager.call_tool_by_qualified_name = mock_call

    service = ToolRuntimeService(mcp_manager=manager)
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Search for test")],
        stream=False,
        provider=ProviderConfig(
            type="openai",
            api_key="test",
            api_url="https://api.openai.com/v1",
        ),
    )

    result = await service.chat_completion(request, llm_service=MockLLMService())

    assert call_count == 2
    assert result["choices"][0]["message"]["content"] == "Found results"
    assert result["usage"] == {
        "prompt_tokens": 22,
        "completion_tokens": 10,
        "total_tokens": 32,
    }
    assert captured_requests[1].messages[-2].role == "assistant"
    assert captured_requests[1].messages[-2].content == ""
    assert captured_requests[1].messages[-2].tool_calls is not None
    assert captured_requests[1].messages[-2].tool_calls[0]["thought_signature"] == "sig-1"
    assert captured_requests[1].messages[-1].role == "tool"
    assert captured_requests[1].messages[-1].name == "search"
    assert captured_requests[1].messages[-1].content == "Search result: test data"
