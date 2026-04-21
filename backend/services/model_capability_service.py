"""Model capability detection via LiteLLM metadata."""
from __future__ import annotations

import logging
from typing import Any

from models.chat import ProviderConfig

logger = logging.getLogger(__name__)

# LiteLLM provider prefix mapping (same as LiteLLMService.PROVIDER_PREFIX)
_PROVIDER_PREFIX: dict[str, str] = {
    "openai": "openai",
    "deepseek": "deepseek",
    "gemini": "gemini",
    "claude": "anthropic",
}


def get_litellm_model_name(provider_type: str, model: str) -> str:
    """Convert to LiteLLM format: provider/model."""
    if "/" in model:
        return model
    prefix = _PROVIDER_PREFIX.get(provider_type, "openai")
    return f"{prefix}/{model}"


def query_model_capabilities(
    provider_type: str,
    model: str,
) -> dict[str, Any]:
    """Query model capabilities from LiteLLM's built-in metadata.

    Returns a dict of capability flags. Unknown models return conservative
    defaults (all False) so callers can fall back to user-configured caps.
    """
    litellm_model = get_litellm_model_name(provider_type, model)

    try:
        import litellm

        info = litellm.get_model_info(model=litellm_model)
    except Exception:
        logger.debug("litellm.get_model_info unavailable for %s", litellm_model)
        return {"known": False}

    return {
        "known": True,
        "function_calling": bool(info.get("supports_function_calling")),
        "vision": bool(info.get("supports_vision")),
        "system_messages": bool(info.get("supports_system_messages")),
        "response_schema": bool(info.get("supports_response_schema")),
        "tool_choice": bool(info.get("supports_tool_choice")),
        "reasoning": bool(info.get("supports_reasoning")),
        "pdf_input": bool(info.get("supports_pdf_input")),
        "web_search": bool(info.get("supports_web_search")),
        "audio_input": bool(info.get("supports_audio_input")),
        "audio_output": bool(info.get("supports_audio_output")),
        "max_input_tokens": info.get("max_input_tokens"),
        "max_output_tokens": info.get("max_output_tokens"),
    }


def supports_function_calling(provider_type: str, model: str) -> bool:
    """Check if a model supports function calling / tool use."""
    litellm_model = get_litellm_model_name(provider_type, model)
    try:
        import litellm
        return litellm.supports_function_calling(model=litellm_model)
    except Exception:
        return False
