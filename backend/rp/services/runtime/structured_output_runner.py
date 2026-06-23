"""Generic structured-output runner port for runtime-owned consumers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.chat import ChatMessage
from rp.services.story.llm_gateway import StoryLlmGateway

STRUCTURED_OUTPUT_RUNNER_REASON_SCRIPTED_QUEUE_EMPTY = (
    "structured_output_scripted_queue_empty"
)
STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED = (
    "structured_output_tool_calls_disabled"
)
STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR = (
    "structured_output_provider_error"
)
STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT = "structured_output_timeout"
STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED = "structured_output_cancelled"
STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT = (
    "structured_output_invalid_output"
)


class StructuredOutputToolPolicy(BaseModel):
    """Structured-output tool policy for the generic runtime runner port."""

    model_config = ConfigDict(extra="forbid")

    tool_calls_enabled: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    tool_results_enabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_tools")
    @classmethod
    def _normalize_allowed_tools(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="allowed_tools")

    @model_validator(mode="after")
    def _validate_policy_shape(self) -> "StructuredOutputToolPolicy":
        if not self.tool_calls_enabled and self.allowed_tools:
            raise ValueError("allowed_tools requires tool_calls_enabled")
        return self


class StructuredOutputRunRequest(BaseModel):
    """Runtime-owned structured-output request contract."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    role: str
    worker_id: str | None = None
    phase: str | None = None
    provider_id: str | None = None
    model_id: str
    schema_name: str
    schema_version: str
    messages: list[ChatMessage]
    response_schema: dict[str, Any]
    tool_policy: StructuredOutputToolPolicy = Field(
        default_factory=StructuredOutputToolPolicy
    )
    timeout_s: float | None = None
    repair_budget: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    gateway_request_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "run_id",
        "role",
        "model_id",
        "schema_name",
        "schema_version",
    )
    @classmethod
    def _require_text(cls, value: str, info) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("worker_id", "phase", "provider_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("messages")
    @classmethod
    def _require_messages(cls, values: list[ChatMessage]) -> list[ChatMessage]:
        if not values:
            raise ValueError("messages must not be empty")
        return values

    @field_validator("response_schema")
    @classmethod
    def _require_response_schema(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError("response_schema must not be empty")
        return value

    @field_validator("timeout_s")
    @classmethod
    def _normalize_timeout(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("timeout_s must be positive when provided")
        return float(value)

    @field_validator("repair_budget")
    @classmethod
    def _normalize_repair_budget(cls, value: int) -> int:
        if value < 0:
            raise ValueError("repair_budget must be non-negative")
        return value


class StructuredOutputRunResult(BaseModel):
    """Runtime-owned structured-output result contract."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed", "cancelled", "timeout"]
    structured_output: dict[str, Any] | None = None
    raw_text: str | None = None
    stop_reason: str | None = None
    reason_code: str | None = None
    message: str | None = None
    retryable: bool = False
    repair_attempts: int = 0
    raw_output_visibility: Literal["private_trace", "redacted", "none"] = (
        "private_trace"
    )
    trace: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_result_shape(self) -> "StructuredOutputRunResult":
        if self.status == "completed" and self.structured_output is None:
            raise ValueError("completed result requires structured_output")
        if self.status != "completed" and self.structured_output is not None:
            raise ValueError("non-completed result must not carry structured_output")
        if self.repair_attempts < 0:
            raise ValueError("repair_attempts must be non-negative")
        return self


@runtime_checkable
class StructuredOutputRunner(Protocol):
    """Generic runtime runner port for structured-output execution."""

    async def run(
        self,
        *,
        request: StructuredOutputRunRequest,
    ) -> StructuredOutputRunResult:
        """Execute one structured-output request."""


class StoryStructuredOutputRunner:
    """Model-backed structured-output runner built on the existing Story gateway."""

    def __init__(self, *, llm_gateway: StoryLlmGateway | None = None) -> None:
        self._llm_gateway = llm_gateway or StoryLlmGateway()

    async def run(
        self,
        *,
        request: StructuredOutputRunRequest,
    ) -> StructuredOutputRunResult:
        if request.tool_policy.tool_calls_enabled or request.tool_policy.allowed_tools:
            return self._failure_result(
                request=request,
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED,
                message="Tool calls are disabled for this structured-output runner.",
                retryable=False,
                raw_output_visibility="none",
            )
        try:
            text, usage = await self._complete_text_with_usage(request=request)
        except asyncio.CancelledError as exc:
            return self._failure_result(
                request=request,
                status="cancelled",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_CANCELLED,
                message=str(exc) or "Structured-output runner was cancelled.",
                retryable=True,
                raw_output_visibility="none",
            )
        except TimeoutError as exc:
            return self._failure_result(
                request=request,
                status="timeout",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_TIMEOUT,
                message=str(exc) or "Structured-output runner timed out.",
                retryable=True,
                raw_output_visibility="none",
            )
        except Exception as exc:  # pragma: no cover - provider boundaries are runner-owned
            return self._failure_result(
                request=request,
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_PROVIDER_ERROR,
                message=str(exc),
                retryable=True,
                raw_output_visibility="none",
            )
        return self._completed_or_invalid_output_result(
            request=request,
            text=text,
            usage=usage,
        )

    async def _complete_text_with_usage(
        self,
        *,
        request: StructuredOutputRunRequest,
    ) -> tuple[str, dict[str, Any]]:
        return await self._llm_gateway.complete_text_with_usage(
            model_id=request.model_id,
            provider_id=request.provider_id,
            messages=list(request.messages),
            temperature=float(request.gateway_request_metadata.get("temperature") or 0.0),
            max_tokens=(
                int(request.gateway_request_metadata["max_tokens"])
                if request.gateway_request_metadata.get("max_tokens") is not None
                else None
            ),
            include_reasoning=(
                bool(request.gateway_request_metadata["include_reasoning"])
                if request.gateway_request_metadata.get("include_reasoning") is not None
                else None
            ),
        )

    def _completed_or_invalid_output_result(
        self,
        *,
        request: StructuredOutputRunRequest,
        text: str,
        usage: dict[str, Any],
    ) -> StructuredOutputRunResult:
        try:
            output = StoryLlmGateway.extract_json_object(text)
        except Exception as exc:
            return self._failure_result(
                request=request,
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT,
                message=str(exc) or "Model output was not valid structured JSON.",
                retryable=False,
                raw_output_visibility="private_trace",
                usage=usage,
            )
        if not isinstance(output, dict) or not output:
            return self._failure_result(
                request=request,
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_INVALID_OUTPUT,
                message="Model output was not valid structured JSON.",
                retryable=False,
                raw_output_visibility="private_trace",
                usage=usage,
            )
        return StructuredOutputRunResult(
            status="completed",
            structured_output=output,
            raw_text=text,
            stop_reason="stop",
            retryable=False,
            raw_output_visibility="private_trace",
            trace=self._trace(
                request=request,
                runner_mode="production",
                usage=usage,
            ),
        )

    def _failure_result(
        self,
        *,
        request: StructuredOutputRunRequest,
        status: Literal["failed", "cancelled", "timeout"],
        reason_code: str,
        message: str,
        retryable: bool,
        raw_output_visibility: Literal["private_trace", "redacted", "none"],
        usage: dict[str, Any] | None = None,
    ) -> StructuredOutputRunResult:
        return StructuredOutputRunResult(
            status=status,
            reason_code=reason_code,
            message=message,
            retryable=retryable,
            raw_output_visibility=raw_output_visibility,
            trace=self._trace(
                request=request,
                runner_mode="production",
                reason_code=reason_code,
                usage=usage,
            ),
        )

    @staticmethod
    def _trace(
        *,
        request: StructuredOutputRunRequest,
        runner_mode: str,
        reason_code: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace: dict[str, Any] = {
            "runner_mode": runner_mode,
            "run_id": request.run_id,
            "role": request.role,
            "worker_id": request.worker_id,
            "phase": request.phase,
            "provider_id": request.provider_id,
            "model_id": request.model_id,
            "schema_name": request.schema_name,
            "schema_version": request.schema_version,
            "tool_calls_enabled": request.tool_policy.tool_calls_enabled,
            "allowed_tools": list(request.tool_policy.allowed_tools),
            "repair_budget": request.repair_budget,
        }
        if reason_code is not None:
            trace["reason_code"] = reason_code
        if usage is not None:
            trace["usage"] = dict(usage)
        return trace


class ScriptedStructuredOutputRunner:
    """Deterministic fake runner for contract tests and future harness seams."""

    def __init__(
        self,
        outputs: Sequence[StructuredOutputRunResult],
    ) -> None:
        self._outputs = list(outputs)
        self.requests: list[StructuredOutputRunRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    async def run(
        self,
        *,
        request: StructuredOutputRunRequest,
    ) -> StructuredOutputRunResult:
        self.requests.append(request)
        if request.tool_policy.tool_calls_enabled or request.tool_policy.allowed_tools:
            return StructuredOutputRunResult(
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_TOOL_CALLS_DISABLED,
                message="Tool calls are disabled for this structured-output runner.",
                retryable=False,
                raw_output_visibility="none",
                trace={
                    "runner_mode": "scripted",
                    "run_id": request.run_id,
                    "worker_id": request.worker_id,
                    "phase": request.phase,
                    "schema_name": request.schema_name,
                    "schema_version": request.schema_version,
                    "tool_calls_enabled": request.tool_policy.tool_calls_enabled,
                    "allowed_tools": list(request.tool_policy.allowed_tools),
                },
            )
        if not self._outputs:
            return StructuredOutputRunResult(
                status="failed",
                reason_code=STRUCTURED_OUTPUT_RUNNER_REASON_SCRIPTED_QUEUE_EMPTY,
                message="Scripted structured-output queue is empty.",
                retryable=False,
                raw_output_visibility="none",
                trace={
                    "runner_mode": "scripted",
                    "run_id": request.run_id,
                    "worker_id": request.worker_id,
                    "phase": request.phase,
                    "schema_name": request.schema_name,
                    "schema_version": request.schema_version,
                },
            )
        return self._outputs.pop(0)


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalize_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values
