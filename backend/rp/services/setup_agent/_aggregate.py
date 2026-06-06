"""Inert marker protocol for the SetupWorkspace aggregate (T27 S2a, ADR-0015).

This protocol NAMES the existing setup workspace governed-mutation boundary; it
is NOT a framework. It is intentionally INERT: no production module imports it.
SetupWorkspaceService satisfies it structurally; only tests assert that.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SetupWorkspaceAggregate(Protocol):
    """Command-side contract for the SetupWorkspace aggregate.

    The existing command families are:
    1. workspace lifecycle (`create_workspace`)
    2. step/draft/asset/question mutation (`register_asset` as representative)
    3. commit proposal and accepted commit ledger (`commit_proposal` /
       `accepted_commit` surface, represented here by `accept_commit`)
    4. retrieval ingestion job update (`update_ingestion_job`)
    5. pending user edit delta writes (S2b gap; not declared yet)
    6. activation session link (`mark_activated_story_session`)
    """

    def create_workspace(self, *args: object, **kwargs: object) -> object: ...

    def register_asset(self, *args: object, **kwargs: object) -> object: ...

    def accept_commit(self, *args: object, **kwargs: object) -> object: ...

    def update_ingestion_job(self, *args: object, **kwargs: object) -> object: ...

    def mark_activated_story_session(
        self, *args: object, **kwargs: object
    ) -> object: ...
