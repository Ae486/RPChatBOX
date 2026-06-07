"""Summary read broker for retrieval memory reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from rp.models.block.view import RpBlockView
from rp.models.memory.crud import (
    MemoryGetSummaryInput,
    SummaryEntry,
    SummaryReadResult,
)
from rp.services.memory.object_mapper import normalize_projection_summary_id

from .context import RetrievalBrokerContext
from .state_summary_base import StateSummaryReadBase


class _SummaryReadService(Protocol):
    async def get_summary(
        self,
        input_model: MemoryGetSummaryInput,
    ) -> SummaryReadResult:
        ...


_SummaryReadServiceFactory = Callable[[Session], _SummaryReadService]


class SummaryBroker(StateSummaryReadBase):
    """Route summary reads and block fallback through the projection read service."""

    def __init__(
        self,
        *,
        context: RetrievalBrokerContext,
        projection_read_service_factory: _SummaryReadServiceFactory,
    ) -> None:
        super().__init__(context=context)
        self._projection_read_service_factory = projection_read_service_factory

    async def get_summary(
        self, input_model: MemoryGetSummaryInput
    ) -> SummaryReadResult:
        try:
            with self._context.session_scope() as session:
                service = self._projection_read_service_factory(session)
                result = await service.get_summary(input_model)
                return self._merge_summary_result_from_blocks(
                    session=session,
                    input_model=input_model,
                    result=result,
                )
        except SQLAlchemyError as exc:
            return SummaryReadResult(
                items=[],
                warnings=[f"story_store_unavailable:{type(exc).__name__}"],
            )

    def _merge_summary_result_from_blocks(
        self,
        *,
        session: Session,
        input_model: MemoryGetSummaryInput,
        result: SummaryReadResult,
    ) -> SummaryReadResult:
        session_id = self._current_session_id(session)
        if session_id is None:
            return result

        block_service = self._build_rp_block_read_service(session)
        blocks = block_service.list_projection_blocks(session_id=session_id)
        if not blocks:
            return result
        blocks_by_summary_id = {
            normalize_projection_summary_id(block.label): block for block in blocks
        }
        item_by_summary_id = {
            normalize_projection_summary_id(
                item.summary_id
            ): self._summary_entry_with_block_metadata(
                item=item,
                block=blocks_by_summary_id.get(
                    normalize_projection_summary_id(item.summary_id)
                ),
                requested_scope=input_model.scope,
            )
            for item in result.items
        }

        if input_model.summary_ids:
            items = []
            resolved_from_blocks: set[str] = set()
            for raw_summary_id in input_model.summary_ids:
                summary_id = normalize_projection_summary_id(raw_summary_id)
                item = item_by_summary_id.get(summary_id)
                if item is not None:
                    items.append(item)
                    continue
                block = blocks_by_summary_id.get(summary_id)
                if block is None:
                    continue
                items.append(
                    self._summary_entry_from_block(
                        block=block,
                        requested_scope=input_model.scope,
                    )
                )
                resolved_from_blocks.add(summary_id)
            warnings = self._strip_summary_resolution_warnings(
                warnings=result.warnings,
                resolved_summary_ids=resolved_from_blocks,
            )
            return result.model_copy(update={"items": items, "warnings": warnings})

        ordered_items = [
            item_by_summary_id[normalize_projection_summary_id(item.summary_id)]
            for item in result.items
        ]
        return result.model_copy(update={"items": ordered_items})

    @classmethod
    def _summary_entry_with_block_metadata(
        cls,
        *,
        item: SummaryEntry,
        block: RpBlockView | None,
        requested_scope: str | None,
    ) -> SummaryEntry:
        if block is None:
            return item
        return item.model_copy(
            update={
                "summary_id": block.label,
                "domain": block.domain,
                "domain_path": block.domain_path,
                "metadata": cls._summary_metadata(
                    existing=item.metadata,
                    block=block,
                    requested_scope=requested_scope,
                ),
            }
        )

    @classmethod
    def _summary_entry_from_block(
        cls,
        *,
        block: RpBlockView,
        requested_scope: str | None,
    ) -> SummaryEntry:
        raw_value: Any = block.items_json
        if raw_value is None:
            raw_value = block.data_json
        return SummaryEntry(
            summary_id=block.label,
            domain=block.domain,
            domain_path=block.domain_path,
            summary_text=cls._stringify_summary_value(raw_value),
            metadata=cls._summary_metadata(
                existing=None,
                block=block,
                requested_scope=requested_scope,
            ),
        )

    @staticmethod
    def _summary_metadata(
        *,
        existing: dict[str, Any] | None,
        block: RpBlockView,
        requested_scope: str | None,
    ) -> dict[str, Any]:
        metadata = dict(existing or {})
        metadata["block_id"] = block.block_id
        metadata["source"] = block.source
        metadata["source_row_id"] = block.metadata.get("source_row_id")
        metadata["revision"] = int(block.revision)
        metadata["payload_schema_ref"] = block.payload_schema_ref
        metadata["block_route"] = block.metadata.get("route")
        metadata["scope"] = metadata.get("scope") or requested_scope or block.scope
        metadata["session_id"] = metadata.get("session_id") or block.metadata.get(
            "session_id"
        )
        chapter_workspace_id = metadata.get(
            "chapter_workspace_id"
        ) or block.metadata.get("chapter_workspace_id")
        if chapter_workspace_id is not None:
            metadata["chapter_workspace_id"] = chapter_workspace_id
        slot_name = metadata.get("slot_name") or block.metadata.get("source_field")
        if slot_name is not None:
            metadata["slot_name"] = slot_name
        return metadata

    @staticmethod
    def _stringify_summary_value(raw_value: Any) -> str:
        if raw_value is None:
            return ""
        if isinstance(raw_value, list):
            return "\n".join(str(item) for item in raw_value if item is not None)
        return str(raw_value)

    @staticmethod
    def _strip_summary_resolution_warnings(
        *,
        warnings: list[str],
        resolved_summary_ids: set[str],
    ) -> list[str]:
        if not resolved_summary_ids:
            return list(warnings)
        stripped: list[str] = []
        for warning in warnings:
            if not warning.startswith("phase_e_projection_summary_not_materialized:"):
                stripped.append(warning)
                continue
            summary_id = warning.split(":", 1)[1]
            if summary_id not in resolved_summary_ids:
                stripped.append(warning)
        return stripped
