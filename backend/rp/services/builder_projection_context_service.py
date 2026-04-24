"""Build writer-facing settled projection context from the current chapter snapshot."""

from __future__ import annotations

from .projection_state_service import ProjectionStateService


class BuilderProjectionContextService:
    """Expose settled projection slots for WritingPacketBuilder consumption."""

    def __init__(self, projection_state_service: ProjectionStateService) -> None:
        self._projection_state_service = projection_state_service

    def build_context_sections(self, *, session_id: str) -> list[dict[str, object]]:
        return self._projection_state_service.build_context_sections(session_id=session_id)
