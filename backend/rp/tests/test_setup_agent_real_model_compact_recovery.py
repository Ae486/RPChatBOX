"""Opt-in real-model behavior eval for compact draft-ref recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from models.model_registry import ModelCapabilityProfile, ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from rp.models.setup_agent import SetupAgentDialogueMessage, SetupAgentTurnRequest
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.runtime.rp_runtime_factory import RpRuntimeFactory
from rp.services.setup_workspace_service import SetupWorkspaceService
from services.model_registry import get_model_registry_service
from services.provider_registry import get_provider_registry_service


_EXACT_MAGIC_LAW_DETAIL = "Public spellcasting requires guild permits."
_OLD_RAW_HISTORY_MARKER = "OLD_RAW_HISTORY_OUTSIDE_SUMMARY_WINDOW"
_RUN_ENV = "CHATBOX_RUN_REAL_SETUP_AGENT_COMPACT_EVAL"


def _load_local_registry_model_config(
    *,
    model_id: str,
    provider_id: str,
) -> dict[str, str] | None:
    storage_dir = Path(
        os.environ.get(
            "CHATBOX_REAL_SETUP_EVAL_REGISTRY_DIR",
            Path(__file__).resolve().parents[2] / "storage",
        )
    )
    models_path = storage_dir / "models.json"
    providers_path = storage_dir / "providers.json"
    if not models_path.exists() or not providers_path.exists():
        return None
    models = json.loads(models_path.read_text(encoding="utf-8"))
    providers = json.loads(providers_path.read_text(encoding="utf-8"))
    if not isinstance(models, list) or not isinstance(providers, list):
        return None

    model_entry = next(
        (item for item in models if isinstance(item, dict) and item.get("id") == model_id),
        None,
    )
    if model_entry is None:
        return None
    resolved_provider_id = provider_id or str(model_entry.get("provider_id") or "")
    provider_entry = next(
        (
            item
            for item in providers
            if isinstance(item, dict) and item.get("id") == resolved_provider_id
        ),
        None,
    )
    if provider_entry is None or not provider_entry.get("is_enabled", True):
        return None
    api_key = str(provider_entry.get("api_key") or "")
    model_name = str(model_entry.get("model_name") or "")
    if not api_key or not model_name:
        return None
    return {
        "provider_id": resolved_provider_id,
        "model_id": model_id,
        "provider_type": str(provider_entry.get("type") or "openai"),
        "api_url": str(provider_entry.get("api_url") or ""),
        "api_key": api_key,
        "model_name": model_name,
        "seed_registry": "true",
    }


def _require_real_setup_model_config() -> dict[str, str]:
    if os.environ.get(_RUN_ENV, "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip(
            f"Set {_RUN_ENV}=1 plus CHATBOX_REAL_SETUP_EVAL_MODEL_NAME and "
            "CHATBOX_REAL_SETUP_EVAL_API_KEY, or set "
            "CHATBOX_REAL_SETUP_EVAL_MODEL_ID to use an existing local registry "
            "entry, to run the paid/network real-model eval."
        )

    model_id = os.environ.get("CHATBOX_REAL_SETUP_EVAL_MODEL_ID", "").strip()
    provider_id = os.environ.get("CHATBOX_REAL_SETUP_EVAL_PROVIDER_ID", "").strip()
    model_name = os.environ.get("CHATBOX_REAL_SETUP_EVAL_MODEL_NAME", "").strip()
    api_key = os.environ.get("CHATBOX_REAL_SETUP_EVAL_API_KEY", "").strip()
    if model_name and api_key:
        return {
            "provider_id": provider_id or "provider-real-setup-compact-eval",
            "model_id": model_id or "model-real-setup-compact-eval",
            "provider_type": os.environ.get(
                "CHATBOX_REAL_SETUP_EVAL_PROVIDER_TYPE",
                "openai",
            ).strip(),
            "api_url": os.environ.get(
                "CHATBOX_REAL_SETUP_EVAL_API_URL",
                "https://api.openai.com/v1",
            ).strip(),
            "api_key": api_key,
            "model_name": model_name,
            "seed_registry": "true",
        }

    if model_id:
        model_entry = get_model_registry_service().get_entry(model_id)
        if model_entry is None:
            seeded_config = _load_local_registry_model_config(
                model_id=model_id,
                provider_id=provider_id,
            )
            if seeded_config is not None:
                return seeded_config
            pytest.skip(f"Configured real setup model_id was not found: {model_id}")
        resolved_provider_id = provider_id or model_entry.provider_id
        provider_entry = get_provider_registry_service().get_entry(resolved_provider_id)
        if provider_entry is None or not provider_entry.is_enabled:
            pytest.skip(
                f"Configured real setup provider was not available: {resolved_provider_id}"
            )
        if not provider_entry.api_key or not model_entry.model_name:
            seeded_config = _load_local_registry_model_config(
                model_id=model_id,
                provider_id=resolved_provider_id,
            )
            if seeded_config is not None:
                return seeded_config
            pytest.skip(
                "Configured real setup provider/model exists but lacks api_key "
                f"or model_name: {model_id}"
            )
        return {
            "provider_id": resolved_provider_id,
            "model_id": model_id,
            "provider_type": provider_entry.type,
            "api_url": provider_entry.api_url or "",
            "api_key": provider_entry.api_key,
            "model_name": model_entry.model_name,
            "seed_registry": "true",
        }

    pytest.skip("No configured real setup model/provider env was provided.")
    raise AssertionError("unreachable after pytest.skip")


def _message_text(messages: list[Any]) -> str:
    return "\n".join(str(getattr(message, "content", "") or "") for message in messages)


def _response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return {}


def _assistant_content_from_response(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _tool_payload(tool: Any) -> dict[str, Any]:
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        return tool.model_dump(mode="json")
    return {}


def _draft_ref_tool_schema(tools: list[Any]) -> dict[str, Any]:
    for tool in tools:
        payload = _tool_payload(tool)
        function = payload.get("function") or {}
        if function.get("name") == "rp_setup__setup.read.draft_refs":
            return function.get("parameters") or {}
    return {}


def _truth_write_tool_schema(tools: list[Any]) -> dict[str, Any]:
    function = _truth_write_tool_function(tools)
    return function.get("parameters") or {}


def _truth_write_tool_function(tools: list[Any]) -> dict[str, Any]:
    for tool in tools:
        payload = _tool_payload(tool)
        function = payload.get("function") or {}
        if function.get("name") == "rp_setup__setup.truth.write":
            return function
    return {}


class _CapturingRealSetupLLMService:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.requests: list[Any] = []
        self.responses: list[dict[str, Any]] = []
        self.write_prompt_checked = False
        self.recovery_phase = False
        self.recovery_prompt_checked = False
        self.recovery_first_response: dict[str, Any] | None = None

    def start_recovery_phase(self) -> None:
        self.recovery_phase = True

    async def chat_completion_stream(self, request: Any):
        raise AssertionError("stream path is not used by this behavior eval")

    async def chat_completion(self, request: Any):
        self.requests.append(request)
        is_recovery_pre_tool_request = False
        visible_text = _message_text(list(request.messages or []))
        if not self.write_prompt_checked and _EXACT_MAGIC_LAW_DETAIL in visible_text:
            self._assert_write_round_prompt_visibility(request)
            self.write_prompt_checked = True
        if self.recovery_phase and not self.recovery_prompt_checked:
            self._assert_recovery_round_prompt_visibility(request)
            self.recovery_prompt_checked = True
            is_recovery_pre_tool_request = True
        response = await self._delegate.chat_completion(request)
        payload = _response_payload(response)
        self.responses.append(payload)
        if is_recovery_pre_tool_request:
            self.recovery_first_response = payload
        return response

    @staticmethod
    def _assert_write_round_prompt_visibility(request: Any) -> None:
        visible_text = _message_text(list(request.messages or []))
        assert _EXACT_MAGIC_LAW_DETAIL in visible_text
        truth_write_function = _truth_write_tool_function(list(request.tools or []))
        truth_write_schema = truth_write_function.get("parameters") or {}
        assert truth_write_schema, "setup.truth.write tool schema is not visible"
        assert "workspace_id" not in (truth_write_schema.get("properties") or {})
        assert "step_id" not in (truth_write_schema.get("properties") or {})
        truth_write_properties = (
            (truth_write_schema.get("properties") or {})
            .get("truth_write", {})
            .get("properties", {})
        )
        assert "payload_json" in truth_write_properties
        assert "block_type" not in truth_write_properties
        assert "current_step" not in truth_write_properties

    @staticmethod
    def _assert_recovery_round_prompt_visibility(request: Any) -> None:
        visible_text = _message_text(list(request.messages or []))

        assert _EXACT_MAGIC_LAW_DETAIL not in visible_text
        assert _OLD_RAW_HISTORY_MARKER not in visible_text
        assert "foundation:magic-law" in visible_text
        assert "recovery_hints" in visible_text
        assert "setup.read.draft_refs" in visible_text
        draft_ref_schema = _draft_ref_tool_schema(list(request.tools or []))
        assert draft_ref_schema, "setup.read.draft_refs tool schema is not visible"
        assert "refs" in (draft_ref_schema.get("required") or [])
        assert "detail" in (draft_ref_schema.get("properties") or {})


def _seed_real_model_registry(config: dict[str, str]) -> None:
    if config.get("seed_registry") == "false":
        return
    provider_service = get_provider_registry_service()
    model_service = get_model_registry_service()
    provider_service.upsert_entry(
        ProviderRegistryEntry(
            id=config["provider_id"],
            name="Real Setup Compact Eval Provider",
            type=config["provider_type"],
            api_key=config["api_key"],
            api_url=config["api_url"],
            custom_headers={},
            is_enabled=True,
            description="Opt-in real-model provider for compact recovery eval",
        )
    )
    model_service.upsert_entry(
        ModelRegistryEntry(
            id=config["model_id"],
            provider_id=config["provider_id"],
            model_name=config["model_name"],
            display_name="Real Setup Compact Eval Model",
            capabilities=["text", "tool"],
            capability_source="user_declared",
            capability_profile=ModelCapabilityProfile(
                known=True,
                provider_supported=True,
                capability_source="user_declared",
                transport_provider_type=config["provider_type"],
                mode="chat",
                supports_function_calling=True,
                supports_tool_choice=True,
                supported_openai_params=["tools", "tool_choice"],
                recommended_capabilities=["text", "tool"],
            ),
            is_enabled=True,
            description="Opt-in real-model setup eval model",
        )
    )


def _compact_recovery_history() -> list[SetupAgentDialogueMessage]:
    return [
        SetupAgentDialogueMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=(
                f"{_OLD_RAW_HISTORY_MARKER} compact candidate {index}"
                if index == 0
                else f"compact candidate history {index}"
            ),
        )
        for index in range(12)
    ]


def _tool_invocations_named(result: Any, suffix: str) -> list[Any]:
    return [
        item
        for item in result.tool_invocations
        if item.tool_name == suffix or item.tool_name.endswith(f"__{suffix}")
    ]


def _tool_results_named(result: Any, suffix: str) -> list[Any]:
    return [
        item
        for item in result.tool_results
        if item.tool_name == suffix or item.tool_name.endswith(f"__{suffix}")
    ]


def _foundation_magic_law_summary(workspace: Any) -> str | None:
    foundation = workspace.foundation_draft
    if foundation is None:
        return None
    for entry in foundation.entries:
        if entry.entry_id == "magic-law":
            content = entry.content
            if isinstance(content, dict):
                return str(content.get("summary") or "")
    return None


def _real_write_prompt(workspace_id: str) -> str:
    payload = {
        "entry_id": "magic-law",
        "domain": "rule",
        "path": "world.magic.law",
        "title": "Magic Law",
        "tags": ["law", "magic"],
        "content": {"summary": _EXACT_MAGIC_LAW_DETAIL},
    }
    return (
        "Call setup.truth.write exactly once to create the current foundation draft. "
        f"The workspace_id is {workspace_id}. The runtime already supplies step_id "
        "and block_type. Use this truth_write object: "
        + json.dumps(
            {
                "write_id": "write-magic-law",
                "target_ref": "foundation:magic-law",
                "operation": "create",
                "payload_json": json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "remaining_open_issues": [],
                "ready_for_review": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + ". Do not call setup.proposal.commit. "
        "After the tool result is successful, do not call any more tools; "
        "reply exactly: Draft write complete: foundation:magic-law."
    )


def _real_recovery_prompt() -> str:
    return (
        "For the current blueprint decision I need the exact current draft detail "
        "for foundation:magic-law. Do not infer it from memory or compact summary. "
        "If the exact detail is not visible in the current prompt, call "
        "setup.read.draft_refs with refs=['foundation:magic-law'] and detail='full'. "
        "After readback, answer with 'Recovered detail:' followed by the exact "
        "summary returned by the tool result."
    )


def _is_strict_enabled_model(model_name: str) -> bool:
    normalized = model_name.lower()
    return "gpt" in normalized or "codex" in normalized


@pytest.mark.asyncio
async def test_real_model_strict_truth_write_accepts_slim_schema(
    retrieval_session,
    monkeypatch,
):
    config = _require_real_setup_model_config()
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module
    from services.litellm_service import get_litellm_service as real_litellm_service

    model_registry_module._model_registry_service = None
    _seed_real_model_registry(config)

    llm = _CapturingRealSetupLLMService(real_litellm_service())
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: llm,
    )

    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-real-strict-truth-write",
        mode=StoryMode.LONGFORM,
    )
    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()

    await service.run_turn(
        SetupAgentTurnRequest(
            workspace_id=workspace.workspace_id,
            model_id=config["model_id"],
            provider_id=config["provider_id"],
            target_step=SetupStepId.FOUNDATION,
            user_prompt=_real_write_prompt(workspace.workspace_id),
        )
    )
    write_result = service.last_runtime_result

    assert write_result is not None
    assert write_result.status == "completed"
    assert llm.write_prompt_checked is True
    truth_write_function = _truth_write_tool_function(list(llm.requests[0].tools or []))
    if _is_strict_enabled_model(config["model_name"]):
        assert truth_write_function.get("strict") is True
    else:
        assert truth_write_function.get("strict") is None
    truth_write_invocations = _tool_invocations_named(
        write_result,
        "setup.truth.write",
    )
    assert truth_write_invocations, "setup.truth.write was not called"
    truth_write_args = truth_write_invocations[0].arguments
    assert truth_write_args["step_id"] == SetupStepId.FOUNDATION.value
    assert truth_write_args["truth_write"]["block_type"] == "foundation_entry"
    truth_write_results = _tool_results_named(write_result, "setup.truth.write")
    assert any(item.success for item in truth_write_results), (
        "setup.truth.write did not eventually succeed"
    )

    workspace_after_write = workspace_service.get_workspace(workspace.workspace_id)
    assert workspace_after_write is not None
    assert _foundation_magic_law_summary(workspace_after_write) == (
        _EXACT_MAGIC_LAW_DETAIL
    )


@pytest.mark.asyncio
async def test_real_model_truth_write_uses_slim_schema_for_non_strict_models(
    retrieval_session,
    monkeypatch,
):
    config = _require_real_setup_model_config()
    if any(
        marker in config["model_name"].lower()
        for marker in ("gpt", "codex")
    ):
        pytest.skip("This assertion targets non-strict model families.")
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module
    from services.litellm_service import get_litellm_service as real_litellm_service

    model_registry_module._model_registry_service = None
    _seed_real_model_registry(config)

    llm = _CapturingRealSetupLLMService(real_litellm_service())
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: llm,
    )

    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-real-slim-truth-write",
        mode=StoryMode.LONGFORM,
    )
    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()

    await service.run_turn(
        SetupAgentTurnRequest(
            workspace_id=workspace.workspace_id,
            model_id=config["model_id"],
            provider_id=config["provider_id"],
            target_step=SetupStepId.FOUNDATION,
            user_prompt=_real_write_prompt(workspace.workspace_id),
        )
    )
    write_result = service.last_runtime_result

    assert write_result is not None
    assert llm.write_prompt_checked is True
    truth_write_function = _truth_write_tool_function(list(llm.requests[0].tools or []))
    assert truth_write_function.get("strict") is None
    truth_write_schema = truth_write_function.get("parameters") or {}
    assert "workspace_id" not in (truth_write_schema.get("properties") or {})
    assert "step_id" not in (truth_write_schema.get("properties") or {})
    truth_write_properties = (
        (truth_write_schema.get("properties") or {})
        .get("truth_write", {})
        .get("properties", {})
    )
    assert "payload_json" in truth_write_properties
    assert "block_type" not in truth_write_properties
    assert "current_step" not in truth_write_properties


@pytest.mark.asyncio
async def test_real_model_compact_recovery_reads_draft_ref_before_using_detail(
    retrieval_session,
    monkeypatch,
):
    config = _require_real_setup_model_config()
    get_provider_registry_service.cache_clear()
    import services.model_registry as model_registry_module
    from services.litellm_service import get_litellm_service as real_litellm_service

    model_registry_module._model_registry_service = None
    _seed_real_model_registry(config)

    llm = _CapturingRealSetupLLMService(real_litellm_service())
    monkeypatch.setattr(
        "rp.services.setup_agent_execution_service.get_litellm_service",
        lambda: llm,
    )

    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-real-compact-recovery",
        mode=StoryMode.LONGFORM,
    )
    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()

    await service.run_turn(
        SetupAgentTurnRequest(
            workspace_id=workspace.workspace_id,
            model_id=config["model_id"],
            provider_id=config["provider_id"],
            target_step=SetupStepId.FOUNDATION,
            user_prompt=_real_write_prompt(workspace.workspace_id),
        )
    )
    write_result = service.last_runtime_result

    assert write_result is not None
    assert write_result.status == "completed"
    assert llm.write_prompt_checked is True
    truth_write_invocations = _tool_invocations_named(
        write_result,
        "setup.truth.write",
    )
    assert truth_write_invocations, "setup.truth.write was not called"
    assert truth_write_invocations[0].arguments["truth_write"]["target_ref"] == (
        "foundation:magic-law"
    )
    truth_write_results = _tool_results_named(write_result, "setup.truth.write")
    assert any(item.success for item in truth_write_results), (
        "setup.truth.write did not eventually succeed"
    )

    workspace_after_write = workspace_service.get_workspace(workspace.workspace_id)
    assert workspace_after_write is not None
    assert _foundation_magic_law_summary(workspace_after_write) == (
        _EXACT_MAGIC_LAW_DETAIL
    )

    llm.start_recovery_phase()
    await service.run_turn(
        SetupAgentTurnRequest(
            workspace_id=workspace.workspace_id,
            model_id=config["model_id"],
            provider_id=config["provider_id"],
            target_step=SetupStepId.LONGFORM_BLUEPRINT,
            user_prompt=_real_recovery_prompt(),
            history=_compact_recovery_history(),
            user_edit_delta_ids=["delta-1", "delta-2", "delta-3"],
        )
    )
    recovery_result = service.last_runtime_result

    assert recovery_result is not None
    assert llm.requests, "real model was not called"
    assert llm.responses, "real model response was not captured"
    assert llm.recovery_prompt_checked is True
    assert llm.recovery_first_response is not None
    assert _EXACT_MAGIC_LAW_DETAIL not in _assistant_content_from_response(
        llm.recovery_first_response
    )
    assert recovery_result.status == "completed"

    read_invocations = _tool_invocations_named(
        recovery_result,
        "setup.read.draft_refs",
    )
    assert read_invocations, "setup.read.draft_refs was not called"
    assert read_invocations[0].arguments["refs"] == ["foundation:magic-law"]
    assert read_invocations[0].arguments["detail"] == "full"

    read_results = _tool_results_named(recovery_result, "setup.read.draft_refs")
    assert read_results and read_results[0].success is True
    assert _EXACT_MAGIC_LAW_DETAIL in read_results[0].content_text
    assert _EXACT_MAGIC_LAW_DETAIL in recovery_result.assistant_text

    context_report = recovery_result.structured_payload["context_report"]
    compact_summary = recovery_result.structured_payload["compact_summary"]
    assert context_report["context_profile"] == "compact"
    assert context_report["compacted_history_count"] > 0
    assert _EXACT_MAGIC_LAW_DETAIL not in json.dumps(
        compact_summary,
        sort_keys=True,
    )
