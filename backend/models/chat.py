"""Chat completion models (OpenAI-compatible)."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """LLM provider configuration passed from Flutter."""

    type: str = Field(description="Provider type: openai, gemini, deepseek, claude")
    api_key: str = Field(description="API key for the provider")
    api_url: str = Field(description="Base API URL")
    custom_headers: dict[str, str] = Field(default_factory=dict)


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

    # Provider routing (extension)
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
