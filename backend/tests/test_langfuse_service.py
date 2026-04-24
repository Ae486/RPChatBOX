from __future__ import annotations

from config import Settings
from services.langfuse_service import LangfuseService


def test_langfuse_service_is_noop_when_disabled():
    service = LangfuseService(Settings())

    assert service.enabled is False
    with service.propagate_attributes(session_id="session-1"):
        with service.start_as_current_observation(name="noop") as observation:
            observation.update(output={"ok": True})
            child = observation.start_as_current_observation(name="child")
            child.update(output={"child": True})

    service.flush()
    service.shutdown()
