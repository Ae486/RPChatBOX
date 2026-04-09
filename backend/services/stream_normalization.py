"""Stream normalization for backend chat streaming."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from models.stream_event import StreamEvent


class StreamNormalizationService:
    """Extract structured events first, then emit frontend-compatible chunks.

    Input sources:
    - LiteLLM (primary): already-normalized OpenAI-compatible ``choices[].delta``
    - Gemini native SDK: ``candidates[].content.parts[]``
    - httpx fallback: raw OpenAI-compatible upstream SSE

    All three produce either ``choices`` or ``candidates`` dicts.
    Provider-specific native formats (Anthropic, OpenAI Responses) are handled
    by LiteLLM before reaching this layer.
    """

    def __init__(self, *, model: str | None = None, provider_type: str | None = None):
        self.model = model
        self.provider_type = provider_type
        self._compat_thinking_open = False
        self._legacy_gemini_body_started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize_chunk(self, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize one upstream chunk into frontend-compatible chunks."""
        return self.emit_compatible_chunks(self.extract_events(chunk), template=chunk)

    def extract_events(self, chunk: dict[str, Any]) -> list[StreamEvent]:
        """Extract structured stream events from one upstream chunk."""
        if chunk.get("error") is not None:
            return [StreamEvent.error(chunk)]

        events: list[StreamEvent] = []

        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            events.extend(self._extract_choice_events(choices))

        candidates = chunk.get("candidates")
        if isinstance(candidates, list) and candidates:
            events.extend(self._extract_candidate_events(candidates))

        return events or [StreamEvent.raw(chunk)]

    def emit_compatible_chunks(
        self,
        events: list[StreamEvent],
        *,
        template: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Emit current frontend-compatible OpenAI-style chunks from internal events."""
        emitted: list[dict[str, Any]] = []
        template = template or {}

        for event in events:
            if event.kind == "thinking":
                if not event.text:
                    continue
                if not self._compat_thinking_open:
                    emitted.append(self._build_content_chunk(template, "<think>"))
                    self._compat_thinking_open = True
                emitted.append(self._build_content_chunk(template, event.text))
                continue

            if event.kind == "text":
                if not event.text:
                    continue
                if self._compat_thinking_open:
                    emitted.append(self._build_content_chunk(template, "</think>"))
                    self._compat_thinking_open = False
                emitted.append(self._build_content_chunk(template, event.text))
                continue

            if event.kind == "tool_call":
                if self._compat_thinking_open:
                    emitted.append(self._build_content_chunk(template, "</think>"))
                    self._compat_thinking_open = False
                if event.tool_calls:
                    emitted.append(self._build_tool_call_chunk(template, event.tool_calls))
                continue

            if event.kind in {"tool_started", "tool_result", "tool_error"}:
                if self._compat_thinking_open:
                    emitted.append(self._build_content_chunk(template, "</think>"))
                    self._compat_thinking_open = False
                continue

            if event.kind == "error":
                if self._compat_thinking_open:
                    emitted.append(self._build_content_chunk(template, "</think>"))
                    self._compat_thinking_open = False
                if event.raw_chunk is not None:
                    emitted.append(event.raw_chunk)
                continue

            if event.raw_chunk is not None:
                emitted.append(event.raw_chunk)

        return emitted

    def emit_typed_payloads(self, events: list[StreamEvent]) -> list[dict[str, Any]]:
        """Emit external typed-event payloads from internal events."""
        payloads: list[dict[str, Any]] = []
        for event in events:
            if event.kind == "thinking":
                if event.text:
                    payloads.append({"type": "thinking_delta", "delta": event.text})
                continue

            if event.kind == "text":
                if event.text:
                    payloads.append({"type": "text_delta", "delta": event.text})
                continue

            if event.kind == "tool_call":
                if event.tool_calls:
                    payloads.append({"type": "tool_call", "tool_calls": event.tool_calls})
                continue

            if event.kind == "tool_started":
                if event.tool_call_id:
                    payloads.append(
                        {
                            "type": "tool_started",
                            "call_id": event.tool_call_id,
                            "tool_name": event.tool_name,
                        }
                    )
                continue

            if event.kind == "tool_result":
                if event.tool_call_id and event.tool_output is not None:
                    payloads.append(
                        {
                            "type": "tool_result",
                            "call_id": event.tool_call_id,
                            "tool_name": event.tool_name,
                            "result": event.tool_output,
                        }
                    )
                continue

            if event.kind == "tool_error":
                if event.tool_call_id and event.tool_error_message is not None:
                    payloads.append(
                        {
                            "type": "tool_error",
                            "call_id": event.tool_call_id,
                            "tool_name": event.tool_name,
                            "error": event.tool_error_message,
                        }
                    )
                continue

            if event.kind == "error":
                error_payload = (
                    event.raw_chunk.get("error")
                    if isinstance(event.raw_chunk, dict)
                    else None
                )
                payloads.append(
                    {
                        "type": "error",
                        "error": error_payload
                        if isinstance(error_payload, dict)
                        else {"message": "Unknown stream error", "type": "unknown"},
                    }
                )
                continue

            if event.raw_chunk is not None:
                payloads.append({"type": "raw", "chunk": event.raw_chunk})

        return payloads

    @staticmethod
    def build_done_payload() -> dict[str, str]:
        """Build the terminal payload for typed SSE mode."""
        return {"type": "done"}

    def flush(self, template: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Emit any trailing closing chunks at stream end."""
        if not self._compat_thinking_open:
            return []

        self._compat_thinking_open = False
        return [self._build_content_chunk(template or {}, "</think>")]

    # ------------------------------------------------------------------
    # OpenAI-compatible delta extraction (LiteLLM + httpx fallback)
    # ------------------------------------------------------------------

    def _extract_choice_events(self, choices: list[Any]) -> list[StreamEvent]:
        choice = choices[0] if choices else None
        if not isinstance(choice, dict):
            return []

        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return []

        return self._extract_events_from_delta(delta)

    def _extract_events_from_delta(self, delta: dict[str, Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        for key in ("reasoning", "reasoning_content", "internal_thoughts", "thinking"):
            value = delta.get(key)
            reasoning_text = self._extract_text(value)
            if reasoning_text:
                events.append(StreamEvent.thinking(reasoning_text))

        content_field = delta.get("content")
        if isinstance(content_field, str):
            if content_field:
                events.append(StreamEvent.text_delta(content_field))
        elif isinstance(content_field, list):
            for part in content_field:
                events.extend(self._extract_events_from_content_part(part))

        tool_calls = self._normalize_tool_calls(delta.get("tool_calls"))
        if tool_calls:
            events.append(StreamEvent.tool_call(tool_calls))

        function_call = delta.get("function_call")
        if isinstance(function_call, dict):
            events.append(StreamEvent.tool_call(self._wrap_function_call(function_call)))

        return events

    # ------------------------------------------------------------------
    # Gemini native candidates extraction (google-genai SDK)
    # ------------------------------------------------------------------

    def _extract_candidate_events(self, candidates: list[Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        if not candidates:
            return events

        candidate = candidates[0]
        if not isinstance(candidate, dict):
            return events

        content = candidate.get("content")
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                if self._should_use_legacy_gemini_first_part_fallback(parts):
                    events.extend(self._extract_legacy_gemini_candidate_events(parts))
                else:
                    for part in parts:
                        events.extend(self._extract_events_from_content_part(part))
            else:
                content_text = str(content.get("text") or "")
                if content_text:
                    events.append(StreamEvent.text_delta(content_text))
        else:
            candidate_text = str(candidate.get("text") or "")
            if candidate_text:
                events.append(StreamEvent.text_delta(candidate_text))

        return events

    def _extract_events_from_content_part(self, part: Any) -> list[StreamEvent]:
        if isinstance(part, str):
            return [StreamEvent.text_delta(part)] if part else []

        if not isinstance(part, dict):
            return []

        if isinstance(part.get("function_call"), dict):
            return [StreamEvent.tool_call(self._wrap_function_call(part["function_call"]))]

        tool_calls = self._normalize_tool_calls(part.get("tool_calls"))
        if tool_calls:
            return [StreamEvent.tool_call(tool_calls)]

        part_text = self._extract_part_text(part)
        if not part_text:
            return []

        if self._is_reasoning_part(part):
            return [StreamEvent.thinking(part_text)]
        return [StreamEvent.text_delta(part_text)]

    def _should_use_legacy_gemini_first_part_fallback(self, parts: list[Any]) -> bool:
        if not self._is_gemini_provider():
            return False
        return not any(
            isinstance(part, dict) and self._part_has_explicit_semantics(part)
            for part in parts
        )

    def _extract_legacy_gemini_candidate_events(self, parts: list[Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue

            text = self._extract_part_text(part)
            if not text:
                continue

            if not self._legacy_gemini_body_started and index == 0:
                events.append(StreamEvent.thinking(text))
            else:
                self._legacy_gemini_body_started = True
                events.append(StreamEvent.text_delta(text))

        return events

    # ------------------------------------------------------------------
    # Chunk builders (legacy compatible output)
    # ------------------------------------------------------------------

    def _build_content_chunk(
        self,
        template: dict[str, Any],
        content: str,
    ) -> dict[str, Any]:
        return {
            "id": template.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            "object": "chat.completion.chunk",
            "created": template.get("created", int(time.time())),
            "model": template.get("model", self.model or ""),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": content,
                    },
                    "finish_reason": None,
                }
            ],
        }

    def _build_tool_call_chunk(
        self,
        template: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "id": template.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            "object": "chat.completion.chunk",
            "created": template.get("created", int(time.time())),
            "model": template.get("model", self.model or ""),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": None,
                }
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_tool_calls(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _wrap_function_call(function_call: dict[str, Any]) -> list[dict[str, Any]]:
        name = str(function_call.get("name") or "").strip()
        if not name:
            return []

        args = function_call.get("args", {})
        arguments = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)

        return [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ]

    @staticmethod
    def _is_reasoning_type(value: str) -> bool:
        lower = value.lower()
        return "reason" in lower or "think" in lower or "thought" in lower

    def _is_gemini_provider(self) -> bool:
        model = str(self.model or "").lower()
        if "gemini" in model:
            return True
        return (self.provider_type or "").lower() == "gemini"

    def _is_reasoning_part(self, part: dict[str, Any]) -> bool:
        thought = part.get("thought")
        if isinstance(thought, str):
            return bool(thought.strip())
        if isinstance(thought, bool):
            return thought
        if part.get("thought_signature"):
            return True
        part_type = str(part.get("type") or part.get("role") or "")
        return self._is_reasoning_type(part_type)

    def _part_has_explicit_semantics(self, part: dict[str, Any]) -> bool:
        if isinstance(part.get("function_call"), dict):
            return True
        if self._normalize_tool_calls(part.get("tool_calls")):
            return True
        if "thought" in part or part.get("thought_signature"):
            return True
        part_type = str(part.get("type") or part.get("role") or "")
        return bool(part_type)

    @staticmethod
    def _extract_part_text(part: dict[str, Any]) -> str | None:
        thought = part.get("thought")
        if isinstance(thought, str) and thought.strip():
            return thought

        for key in ("thinking", "reasoning", "text", "content"):
            value = part.get(key)
            if isinstance(value, str) and value:
                return value

        return None

    @staticmethod
    def _extract_text(value: Any) -> str | None:
        if isinstance(value, str):
            return value or None
        if isinstance(value, dict):
            text = value.get("content") or value.get("text")
            return str(text) if text else None
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    if item:
                        parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("content") or item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts) or None
        return None
