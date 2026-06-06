"""Inert marker protocol for the MemoryGraphProjection aggregate boundary.

This protocol names the existing repository-backed aggregate boundary for
memory graph projection rows. The four ``upsert_*`` methods are the command
entries; reads remain query methods on the repository/service side. The
repository owns validation and flush so callers cannot become hidden validators
or write owners.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryGraphProjectionAggregate(Protocol):
    """Command-side contract for repository-backed graph projection writes."""

    def upsert_node(self, *args: object, **kwargs: object) -> object: ...

    def upsert_edge(self, *args: object, **kwargs: object) -> object: ...

    def upsert_evidence(self, *args: object, **kwargs: object) -> object: ...

    def upsert_job(self, *args: object, **kwargs: object) -> object: ...
