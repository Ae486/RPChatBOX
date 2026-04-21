"""Factory wiring tests for the setup runtime default and fallback paths."""
from __future__ import annotations

from config import get_settings
from rp.runtime.rp_runtime_factory import RpRuntimeFactory


def test_setup_runtime_v2_default_uses_new_runtime(retrieval_session, monkeypatch):
    monkeypatch.delenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", raising=False)
    monkeypatch.delenv(
        "CHATBOX_BACKEND_RP_SETUP_AGENT_RUNTIME_V2_ENABLED",
        raising=False,
    )
    get_settings.cache_clear()

    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()
    runner = RpRuntimeFactory(retrieval_session).build_setup_graph_runner()

    assert service._runtime_executor is not None
    assert service._adapter is not None
    assert runner._execution_service._runtime_executor is not None
    assert runner._execution_service._adapter is not None

    get_settings.cache_clear()


def test_setup_runtime_v2_flag_disabled_uses_legacy_service(retrieval_session, monkeypatch):
    monkeypatch.setenv("RP_SETUP_AGENT_RUNTIME_V2_ENABLED", "false")
    get_settings.cache_clear()

    service = RpRuntimeFactory(retrieval_session).build_setup_agent_execution_service()
    runner = RpRuntimeFactory(retrieval_session).build_setup_graph_runner()

    assert service._runtime_executor is None
    assert service._adapter is None
    assert runner._execution_service._runtime_executor is None
    assert runner._execution_service._adapter is None

    get_settings.cache_clear()
