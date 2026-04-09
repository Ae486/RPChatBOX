"""Chat completion models (OpenAI-compatible)."""
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class CircuitBreakerConfig(BaseModel):
    """Optional circuit breaker hints forwarded from Flutter."""

    failure_threshold: int | None = Field(default=None)
    window_ms: int | None = Field(default=None)
    open_ms: int | None = Field(default=None)
    half_open_max_calls: int | None = Field(default=None)


class ProviderConfig(BaseModel):
    """LLM provider configuration passed from Flutter."""

    type: str = Field(description="Provider type: openai, gemini, deepseek, claude")
    api_key: str = Field(description="API key for the provider")
    api_url: str = Field(description="Base API URL")
    custom_headers: dict[str, str] = Field(default_factory=dict)
    backend_mode: Literal["direct", "proxy", "auto"] | None = Field(default=None)
    fallback_enabled: bool | None = Field(default=None)
    fallback_timeout_ms: int | None = Field(default=None)
    circuit_breaker: CircuitBreakerConfig | None = Field(default=None)


class AttachedFile(BaseModel):
    """Attached file metadata passed from Flutter.

    Supports two input modes:
    - Remote: ``data`` contains base64-encoded file content (no local path needed)
    - Local:  ``path`` contains an absolute local file path (desktop co-located backend)

    At least one of ``data`` or ``path`` must be provided.
    """

    path: str | None = Field(default=None, description="Absolute local file path (optional for remote)")
    mime_type: str = Field(description="MIME type of the attached file")
    name: str = Field(description="Original file name")
    data: str | None = Field(default=None, description="Base64-encoded file content (remote upload)")

    @model_validator(mode="after")
    def _require_data_or_path(self) -> "AttachedFile":
        if not self.data and not self.path:
            raise ValueError("At least one of 'data' or 'path' must be provided")
        return self


class ChatMessage(BaseModel):
    """Chat message in OpenAI format."""

    role: Literal["system", "user", "assistant", "function", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    function_call: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    """Chat completion request (OpenAI-compatible with extensions)."""

    model: str
    model_id: str | None = None
    messages: list[ChatMessage]
    stream: bool = False

    # Standard parameters
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None

    # Extended parameters for specific providers
    include_reasoning: bool | None = None
    extra_body: dict[str, Any] | None = None
    files: list[AttachedFile] | None = None
    stream_event_mode: Literal["legacy", "typed"] | None = None

    # Provider routing (extension)
    provider_id: str | None = None
    provider: ProviderConfig | None = None


class Delta(BaseModel):
    """Streaming delta content."""

    role: str | None = None
    content: str | None = None
    reasoning: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class Choice(BaseModel):
    """Response choice."""

    index: int = 0
    message: ChatMessage | None = None
    delta: Delta | None = None
    finish_reason: str | None = None


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """Chat completion response (OpenAI-compatible)."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None
