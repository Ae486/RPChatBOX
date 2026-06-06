"""Inert marker protocol for the CoreState authoritative aggregate (T27 S1, ADR-0015).

This protocol NAMES the existing core_state governed-mutation boundary; it is
NOT a framework. It is intentionally INERT: no production module imports it.
ProposalApplyService satisfies it structurally; only tests assert that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from rp.models.memory_crud import ProposalReceipt


@runtime_checkable
class CoreStateAggregate(Protocol):
    """Command-side contract for the CoreState authoritative aggregate.

    The sole governed entry for authoritative core_state mutation is
    `apply_proposal` (ProposalApplyService); the executor is
    CoreStateDualWriteService. See ADR-0015.
    """

    def apply_proposal(self, proposal_id: str) -> "ProposalReceipt": ...
