"""Shared context primitives for retrieval broker decomposition."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlmodel import Session

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from services.database import get_engine


class RetrievalBrokerContext:
    """Own the cross-family primitives shared by future retrieval sub-brokers."""

    def __init__(
        self,
        *,
        default_story_id: str | None = None,
        runtime_identity: MemoryRuntimeIdentity | dict[str, Any] | None = None,
        session: Session | None = None,
    ) -> None:
        self.default_story_id = default_story_id
        self.runtime_identity = self.normalize_runtime_identity(runtime_identity)
        self.session = session

    @staticmethod
    def normalize_runtime_identity(
        runtime_identity: object | None,
    ) -> MemoryRuntimeIdentity | None:
        if runtime_identity is None:
            return None
        if isinstance(runtime_identity, MemoryRuntimeIdentity):
            return runtime_identity
        if not isinstance(runtime_identity, dict):
            return None
        try:
            return MemoryRuntimeIdentity.model_validate(runtime_identity)
        except ValueError:
            return None

    def effective_runtime_identity(
        self,
        filters: dict[str, object],
    ) -> MemoryRuntimeIdentity | None:
        if self.runtime_identity is not None:
            return self.runtime_identity
        return self.normalize_runtime_identity(filters.get("runtime_identity"))

    @contextmanager
    def session_scope(self):
        if self.session is not None:
            yield self.session
            return
        with Session(get_engine()) as session:
            yield session
