"""Model capability detection via LiteLLM metadata."""
from __future__ import annotations

import logging
from typing import Any

from models.model_registry import ModelCapabilityProfile, ModelRegistryEntry

logger = logging.getLogger(__name__)

# LiteLLM provider prefix mapping (same as LiteLLMService.PROVIDER_PREFIX)
_PROVIDER_PREFIX: dict[str, str] = {
    "openai": "openai",
    "deepseek": "deepseek",
    "gemini": "gemini",
    "claude": "anthropic",
    "cohere": "cohere",
    "voyage": "voyage",
}

_CANONICAL_CAPABILITIES = {
    "reasoning",
    "vision",
    "network",
    "tool",
    "rerank",
    "embedding",
}
_LEGACY_CAPABILITY_ALIASES = {
    "cross_encoder_rerank": "rerank",
    "text": None,
    "audio": None,
    "video": None,
}


def normalize_registry_capabilities(capabilities: list[str] | None) -> list[str]:
    """Normalize registry capability values into a stable, deduplicated list."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in capabilities or []:
        raw_capability = str(raw or "").strip().lower()
        capability: str | None = _LEGACY_CAPABILITY_ALIASES.get(
            raw_capability,
            raw_capability,
        )
        if (
            not capability
            or capability not in _CANONICAL_CAPABILITIES
            or capability in seen
        ):
            continue
        seen.add(capability)
        normalized.append(capability)
    return normalized


def get_litellm_model_name(provider_type: str, model: str) -> str:
    """Convert to LiteLLM format: provider/model."""
    if "/" in model:
        return model
    prefix = _PROVIDER_PREFIX.get(provider_type, "openai")
    return f"{prefix}/{model}"


def _resolve_lookup_model(provider_type: str, model: str) -> str | None:
    if "/" in model:
        existing_prefix = model.split("/", 1)[0].strip().lower()
        if existing_prefix in set(_PROVIDER_PREFIX.values()):
            return model
        return None
    provider_prefix = _PROVIDER_PREFIX.get(provider_type)
    if provider_prefix is None:
        return None
    return f"{provider_prefix}/{model}"


def _recommended_capabilities_from_info(info: dict[str, Any]) -> list[str]:
    mode = str(info.get("mode") or "").strip().lower()
    if mode == "rerank" or info.get("rerank"):
        return ["rerank"]
    if mode == "embedding" or info.get("output_vector_size"):
        return ["embedding"]

    capabilities: list[str] = []
    if info.get("reasoning"):
        capabilities.append("reasoning")
    if info.get("function_calling"):
        capabilities.append("tool")
    if info.get("vision"):
        capabilities.append("vision")
    if info.get("web_search"):
        capabilities.append("network")
    return normalize_registry_capabilities(capabilities)


def _infer_function_calling_from_supported_params(
    supported_openai_params: list[str],
) -> bool | None:
    """Infer tool-call support when LiteLLM omits the boolean flag.

    Some OpenAI-compatible transports expose `tools` / `tool_choice` in the
    supported param list while returning `supports_function_calling=None` from
    `get_model_info(...)`. Treat that as tool-capable instead of degrading to an
    empty capability profile.
    """

    supported = {
        str(item or "").strip().lower()
        for item in supported_openai_params
        if str(item or "").strip()
    }
    if {"tools", "tool_choice"}.issubset(supported):
        return True
    if {"functions", "function_call"}.issubset(supported):
        return True
    return None


def _infer_tool_choice_from_supported_params(
    supported_openai_params: list[str],
) -> bool | None:
    """Infer tool-choice support from transport params when metadata is sparse."""

    supported = {
        str(item or "").strip().lower()
        for item in supported_openai_params
        if str(item or "").strip()
    }
    if "tool_choice" in supported or "function_call" in supported:
        return True
    return None


def _try_get_model_info(
    *,
    model: str,
    custom_llm_provider: str | None = None,
) -> dict[str, Any] | None:
    try:
        import litellm

        info = litellm.get_model_info(
            model=model,
            custom_llm_provider=custom_llm_provider,
        )
    except Exception:
        return None

    model_dump = getattr(info, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=False)
        return dumped if isinstance(dumped, dict) else None
    if isinstance(info, dict):
        return info
    try:
        return {str(key): value for key, value in dict(info).items()}
    except Exception:
        return None


def _get_supported_openai_params(
    *,
    provider_type: str,
    model: str,
) -> list[str]:
    try:
        import litellm

        params = litellm.get_supported_openai_params(
            model=model,
            custom_llm_provider=provider_type,
        )
    except Exception:
        return []

    if not isinstance(params, list):
        return []
    return [str(item).strip() for item in params if str(item).strip()]


def _supports_parallel_function_calling(
    *,
    model: str,
    custom_llm_provider: str | None = None,
) -> bool | None:
    try:
        import litellm

        supports_parallel = getattr(litellm, "supports_parallel_function_calling", None)
        if not callable(supports_parallel):
            return None
        return bool(
            supports_parallel(
                model=model,
                custom_llm_provider=custom_llm_provider,
            )
        )
    except Exception:
        return None


def resolve_model_capability_profile(
    provider_type: str,
    model: str,
) -> ModelCapabilityProfile:
    """Resolve the capability profile for a model using LiteLLM metadata first.

    For OpenAI-compatible transports, semantic model lookup and transport-level
    supported params are treated separately:
    - semantic capability lookup prefers real LiteLLM model templates
    - transport parameter support uses the current provider type
    """

    transport_provider = str(provider_type or "").strip().lower()
    transport_supported = transport_provider in _PROVIDER_PREFIX
    supported_openai_params = (
        _get_supported_openai_params(
            provider_type=transport_provider,
            model=model,
        )
        if transport_supported
        else []
    )

    info: dict[str, Any] | None = None
    resolution_strategy: str | None = None
    semantic_lookup_model: str | None = None

    if transport_supported:
        provider_info = _try_get_model_info(
            model=model,
            custom_llm_provider=transport_provider,
        )
        if provider_info is not None:
            info = provider_info
            resolution_strategy = "provider_model_info"
            semantic_lookup_model = str(provider_info.get("key") or model)

    if info is None:
        global_info = _try_get_model_info(model=model)
        if global_info is not None:
            info = global_info
            resolution_strategy = "global_model_info"
            semantic_lookup_model = str(global_info.get("key") or model)

    if info is None and transport_supported:
        provider_lookup_model = _resolve_lookup_model(transport_provider, model)
        if provider_lookup_model:
            prefixed_info = _try_get_model_info(
                model=provider_lookup_model,
                custom_llm_provider=transport_provider,
            )
            if prefixed_info is not None:
                info = prefixed_info
                resolution_strategy = "prefixed_provider_model_info"
                semantic_lookup_model = str(prefixed_info.get("key") or provider_lookup_model)

    if info is None:
        return ModelCapabilityProfile(
            known=False,
            provider_supported=transport_supported,
            capability_source="default_unmapped",
            resolution_strategy="unmapped",
            transport_provider_type=transport_provider or None,
            supported_openai_params=supported_openai_params,
            recommended_capabilities=[],
        )

    mode = info.get("mode")
    payload = {
        "known": True,
        "provider_supported": True,
        "capability_source": "litellm_metadata",
        "resolution_strategy": resolution_strategy,
        "transport_provider_type": transport_provider or None,
        "semantic_provider_type": info.get("litellm_provider"),
        "semantic_lookup_model": semantic_lookup_model,
        "mode": mode,
        "max_input_tokens": info.get("max_input_tokens"),
        "max_output_tokens": info.get("max_output_tokens"),
        "output_vector_size": info.get("output_vector_size"),
        "supports_function_calling": None,
        "supports_parallel_function_calling": _supports_parallel_function_calling(
            model=model,
            custom_llm_provider=transport_provider or None,
        ),
        "supports_vision": (
            bool(info.get("supports_vision"))
            if info.get("supports_vision") is not None
            else None
        ),
        "supports_response_schema": (
            bool(info.get("supports_response_schema"))
            if info.get("supports_response_schema") is not None
            else None
        ),
        "supports_tool_choice": None,
        "supports_reasoning": (
            bool(info.get("supports_reasoning"))
            if info.get("supports_reasoning") is not None
            else None
        ),
        "supports_pdf_input": (
            bool(info.get("supports_pdf_input"))
            if info.get("supports_pdf_input") is not None
            else None
        ),
        "supports_web_search": (
            bool(info.get("supports_web_search"))
            if info.get("supports_web_search") is not None
            else None
        ),
        "supports_audio_input": (
            bool(info.get("supports_audio_input"))
            if info.get("supports_audio_input") is not None
            else None
        ),
        "supports_audio_output": (
            bool(info.get("supports_audio_output"))
            if info.get("supports_audio_output") is not None
            else None
        ),
        "supports_system_messages": (
            bool(info.get("supports_system_messages"))
            if info.get("supports_system_messages") is not None
            else None
        ),
        "supported_openai_params": supported_openai_params,
    }
    payload["supports_function_calling"] = (
        bool(info.get("supports_function_calling"))
        if info.get("supports_function_calling") is not None
        else _infer_function_calling_from_supported_params(supported_openai_params)
    )
    payload["supports_tool_choice"] = (
        bool(info.get("supports_tool_choice"))
        if info.get("supports_tool_choice") is not None
        else _infer_tool_choice_from_supported_params(supported_openai_params)
    )
    payload["recommended_capabilities"] = _recommended_capabilities_from_info(
        {
            "mode": mode,
            "rerank": mode == "rerank",
            "reasoning": payload.get("supports_reasoning"),
            "function_calling": payload.get("supports_function_calling"),
            "vision": payload.get("supports_vision"),
            "web_search": payload.get("supports_web_search"),
            "output_vector_size": payload.get("output_vector_size"),
        }
    )
    return ModelCapabilityProfile.model_validate(payload)


def build_manual_capability_profile(
    *,
    provider_type: str,
    model: str,
    capabilities: list[str],
    capability_source: str = "user_declared",
) -> ModelCapabilityProfile:
    """Build a compatibility profile from explicit project-side capability overrides."""

    normalized_capabilities = normalize_registry_capabilities(capabilities)
    mode: str | None = "chat"
    if "rerank" in normalized_capabilities:
        mode = "rerank"
    elif "embedding" in normalized_capabilities:
        mode = "embedding"

    return ModelCapabilityProfile(
        known=False,
        provider_supported=str(provider_type or "").strip().lower() in _PROVIDER_PREFIX,
        capability_source=capability_source,
        resolution_strategy="manual_override",
        transport_provider_type=str(provider_type or "").strip().lower() or None,
        semantic_lookup_model=model,
        mode=mode,
        supports_reasoning="reasoning" in normalized_capabilities,
        supports_function_calling="tool" in normalized_capabilities,
        supports_vision="vision" in normalized_capabilities,
        supports_web_search="network" in normalized_capabilities,
        recommended_capabilities=normalized_capabilities,
    )


def hydrate_registry_model_entry(
    *,
    entry: ModelRegistryEntry,
    provider_type: str | None,
    existing: ModelRegistryEntry | None = None,
) -> ModelRegistryEntry:
    """Populate capability source/profile for stored model entries.

    This is used both on write-time and for lazy backfill of older registry data.
    """

    normalized_capabilities = normalize_registry_capabilities(entry.capabilities)
    normalized_provider_type = str(provider_type or "").strip().lower()
    provider_supported = normalized_provider_type in _PROVIDER_PREFIX
    explicit_user_override = entry.capability_source == "user_declared"

    if not normalized_provider_type:
        capability_source = entry.capability_source or "user_declared"
        return entry.model_copy(
            update={
                "capabilities": normalized_capabilities,
                "capability_source": capability_source,
                "capability_profile": build_manual_capability_profile(
                    provider_type="",
                    model=entry.model_name,
                    capabilities=normalized_capabilities,
                    capability_source=capability_source,
                ),
            }
        )

    if explicit_user_override:
        manual_profile = build_manual_capability_profile(
            provider_type=normalized_provider_type,
            model=entry.model_name,
            capabilities=normalized_capabilities,
            capability_source="user_declared",
        )
        return entry.model_copy(
            update={
                "capabilities": normalized_capabilities,
                "capability_source": "user_declared",
                "capability_profile": manual_profile,
            }
        )

    if provider_supported and (
        not normalized_capabilities
        or entry.capability_source in {"litellm_metadata", "default_text", "default_unmapped"}
        or entry.capability_profile is not None
    ):
        profile = resolve_model_capability_profile(normalized_provider_type, entry.model_name)
        return entry.model_copy(
            update={
                "capabilities": normalize_registry_capabilities(profile.recommended_capabilities),
                "capability_source": profile.capability_source,
                "capability_profile": profile,
            }
        )

    existing_capabilities = (
        normalize_registry_capabilities(existing.capabilities) if existing else []
    )
    if (
        existing is not None
        and normalized_capabilities == existing_capabilities
        and existing.capability_source
        and existing.capability_profile is not None
        and not explicit_user_override
    ):
        return entry.model_copy(
            update={
                "capabilities": normalized_capabilities,
                "capability_source": existing.capability_source,
                "capability_profile": existing.capability_profile,
            }
        )

    manual_profile = build_manual_capability_profile(
        provider_type=normalized_provider_type,
        model=entry.model_name,
        capabilities=normalized_capabilities,
        capability_source="user_declared",
    )
    return entry.model_copy(
        update={
            "capabilities": normalized_capabilities,
            "capability_source": "user_declared",
            "capability_profile": manual_profile,
        }
    )


def query_model_capabilities(
    provider_type: str,
    model: str,
) -> dict[str, Any]:
    """Query model capabilities from LiteLLM's built-in metadata.

    Returns a dict of capability flags. Unknown models return conservative
    defaults (all False) so callers can fall back to user-configured caps.
    """
    profile = resolve_model_capability_profile(provider_type, model)
    return {
        "known": profile.known,
        "provider_supported": profile.provider_supported,
        "capability_source": profile.capability_source,
        "resolution_strategy": profile.resolution_strategy,
        "semantic_provider_type": profile.semantic_provider_type,
        "semantic_lookup_model": profile.semantic_lookup_model,
        "mode": profile.mode,
        "rerank": profile.mode == "rerank",
        "function_calling": bool(profile.supports_function_calling),
        "vision": bool(profile.supports_vision),
        "system_messages": bool(profile.supports_system_messages),
        "response_schema": bool(profile.supports_response_schema),
        "tool_choice": bool(profile.supports_tool_choice),
        "reasoning": bool(profile.supports_reasoning),
        "pdf_input": bool(profile.supports_pdf_input),
        "web_search": bool(profile.supports_web_search),
        "audio_input": bool(profile.supports_audio_input),
        "audio_output": bool(profile.supports_audio_output),
        "max_input_tokens": profile.max_input_tokens,
        "max_output_tokens": profile.max_output_tokens,
        "output_vector_size": profile.output_vector_size,
        "supported_openai_params": profile.supported_openai_params,
        "recommended_capabilities": profile.recommended_capabilities,
        "capability_profile": profile.model_dump(mode="json", exclude_none=True),
    }


def supports_function_calling(provider_type: str, model: str) -> bool:
    """Check if a model supports function calling / tool use."""
    profile = resolve_model_capability_profile(provider_type, model)
    return bool(profile.supports_function_calling)
