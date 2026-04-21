"""SSE replay tests for backend stream normalization."""
from __future__ import annotations

import json
from pathlib import Path

from models.stream_event import StreamEvent
from services.stream_normalization import StreamNormalizationService


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sse"


def _load_sse_fixture(name: str) -> list[dict]:
    items: list[dict] = []
    path = FIXTURE_DIR / name
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        items.append(json.loads(payload))
    return items


def _normalized_contents(
    fixture_name: str, *, model: str, provider_type: str
) -> tuple[list[str], list[dict]]:
    service = StreamNormalizationService(model=model, provider_type=provider_type)
    output: list[str] = []
    non_content_chunks: list[dict] = []

    for chunk in _load_sse_fixture(fixture_name):
        for normalized in service.normalize_chunk(chunk):
            delta = (
                normalized.get("choices", [{}])[0].get("delta", {})
                if normalized.get("choices")
                else {}
            )
            content = delta.get("content")
            if isinstance(content, str):
                output.append(content)
            else:
                non_content_chunks.append(normalized)

    for tail in service.flush():
        delta = tail["choices"][0]["delta"]
        output.append(delta["content"])

    return output, non_content_chunks


def _collect_compatible_chunks(
    chunk: dict, *, model: str, provider_type: str
) -> tuple[list[str], list[dict]]:
    service = StreamNormalizationService(model=model, provider_type=provider_type)
    output: list[str] = []
    non_content_chunks: list[dict] = []

    for normalized in service.normalize_chunk(chunk):
        delta = (
            normalized.get("choices", [{}])[0].get("delta", {})
            if normalized.get("choices")
            else {}
        )
        content = delta.get("content")
        if isinstance(content, str):
            output.append(content)
        else:
            non_content_chunks.append(normalized)

    for tail in service.flush():
        delta = tail["choices"][0]["delta"]
        output.append(delta["content"])

    return output, non_content_chunks


def _event_summary(events: list[StreamEvent]) -> list[tuple[str, str | None]]:
    return [(event.kind, event.text) for event in events]


# ---------------------------------------------------------------------------
# SSE fixture replay tests (OpenAI-compatible delta format, LiteLLM output)
# ---------------------------------------------------------------------------

def test_replay_openai_reasoning_fixture():
    output, non_content_chunks = _normalized_contents(
        "openai_reasoning.sse",
        model="deepseek-r1",
        provider_type="deepseek",
    )

    assert output == ["<think>", "先分析", "再推理", "</think>", "最终回答"]
    assert non_content_chunks == []


def test_replay_gemini_candidates_fixture():
    output, non_content_chunks = _normalized_contents(
        "gemini_candidates.sse",
        model="gemini-2.5-flash",
        provider_type="gemini",
    )

    assert output == ["<think>", "隐藏思考", "</think>", "第一段正文", "第二段正文"]
    assert non_content_chunks == []


def test_replay_midstream_error_closes_thinking_before_error():
    output, non_content_chunks = _normalized_contents(
        "midstream_error.sse",
        model="deepseek-r1",
        provider_type="deepseek",
    )

    assert output == ["<think>", "先思考", "</think>"]
    assert len(non_content_chunks) == 1
    assert non_content_chunks[0]["error"]["type"] == "api_error"


# ---------------------------------------------------------------------------
# Gemini native candidates extraction (google-genai SDK path)
# ---------------------------------------------------------------------------

def test_extract_events_from_gemini_native_parts_preserves_semantic_boundaries():
    service = StreamNormalizationService(model="gemini-2.5-pro", provider_type="gemini")
    chunk = {
        "id": "gemini-structured",
        "model": "gemini-2.5-pro",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": "先检索再组织答案"},
                        {"text": "这是正文第一段。"},
                        {
                            "function_call": {
                                "name": "google_search",
                                "args": {"q": "2026 Tokyo events"},
                            }
                        },
                        {"text": "这是正文第二段。"},
                    ]
                }
            }
        ],
    }

    events = service.extract_events(chunk)

    assert _event_summary(events) == [
        ("thinking", "先检索再组织答案"),
        ("text", "这是正文第一段。"),
        ("tool_call", None),
        ("text", "这是正文第二段。"),
    ]
    assert events[2].tool_calls is not None
    assert events[2].tool_calls[0]["function"]["name"] == "google_search"


def test_compatible_output_from_gemini_native_parts_matches_current_frontend_contract():
    chunk = {
        "id": "gemini-structured",
        "model": "gemini-2.5-pro",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": "先检索再组织答案"},
                        {"text": "这是正文第一段。"},
                        {
                            "function_call": {
                                "name": "google_search",
                                "args": {"q": "2026 Tokyo events"},
                            }
                        },
                        {"text": "这是正文第二段。"},
                    ]
                }
            }
        ],
    }

    output, non_content_chunks = _collect_compatible_chunks(
        chunk,
        model="gemini-2.5-pro",
        provider_type="gemini",
    )

    assert output == [
        "<think>",
        "先检索再组织答案",
        "</think>",
        "这是正文第一段。",
        "这是正文第二段。",
    ]
    assert len(non_content_chunks) == 1
    tool_calls = non_content_chunks[0]["choices"][0]["delta"]["tool_calls"]
    assert tool_calls[0]["function"]["name"] == "google_search"
    assert json.loads(tool_calls[0]["function"]["arguments"]) == {
        "q": "2026 Tokyo events"
    }


# ---------------------------------------------------------------------------
# OpenAI-compatible delta extraction (LiteLLM normalized output)
# ---------------------------------------------------------------------------

def test_delta_content_parts_use_explicit_reasoning_type_instead_of_position_guessing():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    chunk = {
        "id": "chatcmpl-structured",
        "model": "gpt-4o",
        "choices": [
            {
                "delta": {
                    "content": [
                        {"type": "thinking", "text": "先列步骤"},
                        {"type": "output_text", "text": "最终回答"},
                    ]
                }
            }
        ],
    }

    events = service.extract_events(chunk)
    assert _event_summary(events) == [
        ("thinking", "先列步骤"),
        ("text", "最终回答"),
    ]

    output, non_content_chunks = _collect_compatible_chunks(
        chunk,
        model="gpt-4o",
        provider_type="openai",
    )
    assert output == ["<think>", "先列步骤", "</think>", "最终回答"]
    assert non_content_chunks == []


def test_unknown_non_content_chunk_is_preserved_as_raw_passthrough():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    chunk = {
        "id": "chatcmpl-finish",
        "model": "gpt-4o",
        "choices": [
            {
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }

    events = service.extract_events(chunk)
    assert _event_summary(events) == [("raw", None)]

    compatible = service.normalize_chunk(chunk)
    assert compatible == [chunk]


def test_openai_compatible_delta_reasoning_and_tool_calls_preserve_both_semantics():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    chunk = {
        "id": "chatcmpl-mixed",
        "model": "gpt-4o",
        "choices": [
            {
                "delta": {
                    "reasoning_content": "先思考",
                    "tool_calls": [
                        {
                            "id": "call_789",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"q":"tokyo"}',
                            },
                        }
                    ],
                }
            }
        ],
    }

    events = service.extract_events(chunk)
    assert _event_summary(events) == [("thinking", "先思考"), ("tool_call", None)]

    output, non_content_chunks = _collect_compatible_chunks(
        chunk,
        model="gpt-4o",
        provider_type="openai",
    )
    assert output == ["<think>", "先思考", "</think>"]
    assert len(non_content_chunks) == 1
    assert (
        non_content_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"]
        == "web_search"
    )


# ---------------------------------------------------------------------------
# Typed payload emission
# ---------------------------------------------------------------------------

def test_emit_typed_payloads_from_mixed_events():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    chunk = {
        "id": "chatcmpl-mixed",
        "model": "gpt-4o",
        "choices": [
            {
                "delta": {
                    "reasoning_content": "先思考",
                    "content": "再回答",
                    "tool_calls": [
                        {
                            "id": "call_789",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"q":"tokyo"}',
                            },
                        }
                    ],
                }
            }
        ],
    }

    events = service.extract_events(chunk)
    payloads = service.emit_typed_payloads(events)

    assert payloads == [
        {"type": "thinking_delta", "delta": "先思考"},
        {"type": "text_delta", "delta": "再回答"},
        {
            "type": "tool_call",
            "tool_calls": [
                {
                    "id": "call_789",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"q":"tokyo"}',
                    },
                }
            ],
        },
    ]


def test_extract_usage_event_and_emit_typed_payload():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    chunk = {
        "id": "chatcmpl-usage",
        "model": "gpt-4o",
        "choices": [{"delta": {}}],
        "usage": {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
        },
    }

    events = service.extract_events(chunk)
    assert [event.kind for event in events] == ["usage"]

    payloads = service.emit_typed_payloads(events)
    assert payloads == [
        {
            "type": "usage",
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
        }
    ]


def test_emit_typed_payloads_from_error_event():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    payloads = service.emit_typed_payloads(
        [StreamEvent.error({"error": {"message": "boom", "type": "api_error"}})]
    )

    assert payloads == [
        {"type": "error", "error": {"message": "boom", "type": "api_error"}}
    ]


def test_emit_typed_payloads_from_tool_lifecycle_events():
    service = StreamNormalizationService(model="gpt-4o", provider_type="openai")
    payloads = service.emit_typed_payloads(
        [
            StreamEvent.tool_started(call_id="call_1", tool_name="web_search"),
            StreamEvent.tool_result(
                call_id="call_1",
                tool_name="web_search",
                result='{"items":[1,2,3]}',
            ),
            StreamEvent.tool_error(
                call_id="call_2",
                tool_name="read_file",
                error_message="permission denied",
            ),
        ]
    )

    assert payloads == [
        {"type": "tool_started", "call_id": "call_1", "tool_name": "web_search"},
        {
            "type": "tool_result",
            "call_id": "call_1",
            "tool_name": "web_search",
            "result": '{"items":[1,2,3]}',
        },
        {
            "type": "tool_error",
            "call_id": "call_2",
            "tool_name": "read_file",
            "error": "permission denied",
        },
    ]
