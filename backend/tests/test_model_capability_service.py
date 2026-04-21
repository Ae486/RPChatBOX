"""Tests for model capability service."""
from services.model_capability_service import (
    get_litellm_model_name,
    query_model_capabilities,
    supports_function_calling,
)


def test_get_litellm_model_name_adds_prefix():
    assert get_litellm_model_name("openai", "gpt-4o") == "openai/gpt-4o"
    assert get_litellm_model_name("gemini", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"
    assert get_litellm_model_name("claude", "claude-sonnet-4-20250514") == "anthropic/claude-sonnet-4-20250514"


def test_get_litellm_model_name_preserves_existing_prefix():
    assert get_litellm_model_name("openai", "openai/gpt-4o") == "openai/gpt-4o"


def test_supports_function_calling_known_models():
    assert supports_function_calling("openai", "gpt-4o") is True
    assert supports_function_calling("gemini", "gemini-2.5-flash") is True
    assert supports_function_calling("claude", "claude-sonnet-4-20250514") is True


def test_query_capabilities_returns_known_for_valid_model():
    caps = query_model_capabilities("openai", "gpt-4o")
    assert caps["known"] is True
    assert caps["function_calling"] is True
    assert caps["vision"] is True
    assert isinstance(caps["max_input_tokens"], int)


def test_query_capabilities_returns_unknown_for_invalid_model():
    caps = query_model_capabilities("openai", "nonexistent-model-xyz-99")
    assert caps["known"] is False
