"""State read broker for retrieval memory reads."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from rp.models.block.view import RpBlockView
from rp.models.shared.dsl import Layer, ObjectRef
from rp.models.memory.crud import (
    MemoryGetStateInput,
    StateReadResult,
    StateReadResultItem,
)

from .context import RetrievalBrokerContext
from .state_summary_base import StateSummaryReadBase


class _StateReadService(Protocol):
    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        ...


_StateReadServiceFactory = Callable[[Session], _StateReadService]


class StateBroker(StateSummaryReadBase):
    """Route state reads and block fallback through the core state read service."""

    def __init__(
        self,
        *,
        context: RetrievalBrokerContext,
        core_state_read_service_factory: _StateReadServiceFactory,
    ) -> None:
        super().__init__(context=context)
        self._core_state_read_service_factory = core_state_read_service_factory

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        try:
            with self._context.session_scope() as session:
                service = self._core_state_read_service_factory(session)
                result = await service.get_state(input_model)
                return self._merge_state_result_from_blocks(
                    session=session,
                    input_model=input_model,
                    result=result,
                )
        except SQLAlchemyError as exc:
            items: list[StateReadResultItem] = []
            refs = list(input_model.refs)
            if not refs:
                domain = input_model.domain
                if domain is None:
                    raise ValueError(
                        "MemoryGetStateInput must include refs or domain"
                    ) from exc
                refs = [
                    ObjectRef(
                        object_id=f"{domain.value}.current",
                        layer=Layer.CORE_STATE_AUTHORITATIVE,
                        domain=domain,
                        domain_path=f"{domain.value}.current",
                        scope=input_model.scope,
                        revision=1,
                    )
                ]
            for ref in refs:
                items.append(StateReadResultItem(object_ref=ref, data={}, warnings=[]))
            return StateReadResult(
                items=items,
                version_refs=[
                    f"{item.object_ref.object_id}@{item.object_ref.revision or 1}"
                    for item in items
                ],
                warnings=[f"story_store_unavailable:{type(exc).__name__}"],
            )

    def _merge_state_result_from_blocks(
        self,
        *,
        session: Session,
        input_model: MemoryGetStateInput,
        result: StateReadResult,
    ) -> StateReadResult:
        # Only explicit refs can safely resolve unmapped authoritative identities.
        if not input_model.refs:
            return result
        unresolved_indexes = [
            index
            for index, item in enumerate(result.items)
            if self._state_item_needs_block_resolution(item)
        ]
        if not unresolved_indexes:
            return result
        session_id = self._current_session_id(session)
        if session_id is None:
            return result

        block_service = self._build_rp_block_read_service(session)
        blocks = block_service.list_authoritative_blocks(session_id=session_id)
        blocks_by_identity = {
            self._authoritative_identity_from_block(block): block for block in blocks
        }
        items = list(result.items)
        version_refs = list(result.version_refs)

        for index in unresolved_indexes:
            current_item = items[index]
            block = blocks_by_identity.get(
                self._authoritative_identity_from_ref(current_item.object_ref)
            )
            if block is None:
                continue
            items[index] = self._state_item_from_block(
                block=block,
                warnings=current_item.warnings,
            )
            version_refs[index] = (
                f"{items[index].object_ref.object_id}@"
                f"{items[index].object_ref.revision or 1}"
            )

        return result.model_copy(update={"items": items, "version_refs": version_refs})

    @staticmethod
    def _state_item_needs_block_resolution(item: StateReadResultItem) -> bool:
        return any(
            warning.startswith("phase_e_authoritative_ref_not_materialized:")
            for warning in item.warnings
        )

    @staticmethod
    def _authoritative_identity_from_ref(ref: ObjectRef) -> tuple[str, str, str]:
        return (
            ref.object_id,
            ref.domain_path or ref.object_id,
            ref.scope or "story",
        )

    @staticmethod
    def _authoritative_identity_from_block(block: RpBlockView) -> tuple[str, str, str]:
        return (block.label, block.domain_path, block.scope or "story")

    @classmethod
    def _state_item_from_block(
        cls,
        *,
        block: RpBlockView,
        warnings: list[str],
    ) -> StateReadResultItem:
        payload = block.data_json if isinstance(block.data_json, dict) else {}
        return StateReadResultItem(
            object_ref=ObjectRef(
                object_id=block.label,
                layer=block.layer,
                domain=block.domain,
                domain_path=block.domain_path,
                scope=block.scope,
                revision=int(block.revision),
            ),
            data=deepcopy(payload),
            warnings=[
                warning
                for warning in warnings
                if not warning.startswith("phase_e_authoritative_ref_not_materialized:")
            ],
        )
