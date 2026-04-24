from services.model_capability_service import (
    get_litellm_model_name,
    normalize_registry_capabilities,
    query_model_capabilities,
    resolve_model_capability_profile,
)


def test_get_litellm_model_name_adds_known_prefixes():
    assert get_litellm_model_name("openai", "gpt-4o") == "openai/gpt-4o"
    assert get_litellm_model_name("gemini", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"
    assert get_litellm_model_name("claude", "claude-sonnet-4-20250514") == "anthropic/claude-sonnet-4-20250514"
    assert get_litellm_model_name("cohere", "rerank-v3.5") == "cohere/rerank-v3.5"
    assert get_litellm_model_name("voyage", "rerank-2.5") == "voyage/rerank-2.5"


def test_get_litellm_model_name_preserves_existing_prefix():
    assert get_litellm_model_name("openai", "openai/gpt-4o") == "openai/gpt-4o"


def test_query_capabilities_returns_known_for_valid_model():
    caps = query_model_capabilities("openai", "gpt-4o")

    assert caps["known"] is True
    assert caps["provider_supported"] is True
    assert "tool" in caps["recommended_capabilities"]
    assert caps["capability_source"] == "litellm_metadata"
    assert isinstance(caps["capability_profile"], dict)


def test_query_capabilities_returns_unknown_for_invalid_model():
    caps = query_model_capabilities("openai", "nonexistent-model-xyz-99")

    assert caps["known"] is False
    assert caps["provider_supported"] is True
    assert caps["recommended_capabilities"] == []
    assert caps["capability_source"] == "default_unmapped"


def test_query_capabilities_marks_known_rerank_model():
    caps = query_model_capabilities("cohere", "rerank-v3.5")

    assert caps["known"] is True
    assert caps["mode"] == "rerank"
    assert caps["rerank"] is True
    assert caps["recommended_capabilities"] == ["rerank"]


def test_resolve_profile_prefers_global_template_for_openai_transport_gemini_model():
    profile = resolve_model_capability_profile("openai", "gemini-2.5-flash")

    assert profile.known is True
    assert profile.capability_source == "litellm_metadata"
    assert profile.semantic_provider_type
    assert "tool" in profile.recommended_capabilities
    assert profile.supports_function_calling is True
    assert "tools" in profile.supported_openai_params


def test_query_capabilities_returns_default_for_unsupported_provider_type():
    caps = query_model_capabilities("local", "cross-encoder/ms-marco")

    assert caps["known"] is False
    assert caps["provider_supported"] is False
    assert caps["recommended_capabilities"] == []
    assert caps["capability_source"] == "default_unmapped"


def test_normalize_registry_capabilities_dedupes_and_lowercases():
    caps = normalize_registry_capabilities(
        ["Text", "rerank", "RERANK", "", "tool", "reasoning", "audio", "cross_encoder_rerank"]
    )

    assert caps == ["rerank", "tool", "reasoning"]
