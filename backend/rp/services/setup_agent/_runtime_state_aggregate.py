"""Inert marker protocol for the SetupAgentRuntimeState aggregate (T27 S3a, ADR-0015).

This protocol NAMES the existing runtime-private cognitive-state write boundary;
it is NOT a framework. It is intentionally INERT: no production module imports it.
SetupAgentRuntimeStateService satisfies it structurally; only tests assert that.

Single persistence entry: ``save_snapshot``. The five governance methods
(``replace_discussion_state``, ``upsert_chunk``, ``record_truth_write``,
``reconcile_snapshot``, ``persist_turn_governance``) are command adapters that ALL
funnel into ``save_snapshot``; no durable write to ``SetupAgentRuntimeStateRecord``
occurs outside it. The entry enforces fail-closed durable-field validation
(``validate_durable_snapshot_payload``). No ledger: this is transient cross-turn
cognitive state, not an audit receipt or externally-visible command log.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SetupAgentRuntimeStateAggregate(Protocol):
    """Command-side contract for the SetupAgentRuntimeState aggregate.

    ``save_snapshot`` is the single durable persistence entry. See ADR-0015.
    """

    def save_snapshot(self, *args: object, **kwargs: object) -> object: ...
