"""Fail-closed guard for writer-side retrieval usage recording."""

from __future__ import annotations

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.runtime_retrieval_card_service import RuntimeRetrievalCardService


class WriterRetrievalUsageGuardServiceError(ValueError):
    """Stable writer-retrieval usage guard error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class WriterRetrievalUsageGuardService:
    """Ensure final writer output never bypasses required retrieval usage."""

    def __init__(
        self,
        *,
        runtime_retrieval_card_service: RuntimeRetrievalCardService,
    ) -> None:
        self._runtime_retrieval_card_service = runtime_retrieval_card_service

    def ensure_final_output_allowed(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        retrieval_generation: int,
        usage_generation: int,
        usage_material_id: str | None,
    ) -> None:
        if retrieval_generation <= 0:
            return
        if usage_generation < retrieval_generation or not usage_material_id:
            raise WriterRetrievalUsageGuardServiceError(
                "writer_retrieval_usage_required_before_final_output",
                identity.turn_id,
            )
        material = self._runtime_retrieval_card_service.require_material(
            identity=identity,
            material_id=usage_material_id,
        )
        if material.material_kind != RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD:
            raise WriterRetrievalUsageGuardServiceError(
                "writer_retrieval_usage_record_kind_mismatch",
                usage_material_id,
            )
