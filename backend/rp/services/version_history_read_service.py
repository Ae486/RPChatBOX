"""Authoritative version history read side over persisted apply receipts."""

from __future__ import annotations

from .core_state_store_repository import CoreStateStoreRepository
from rp.models.dsl import ObjectRef
from rp.models.memory_crud import VersionListResult

from .memory_object_mapper import normalize_authoritative_ref
from .proposal_repository import ProposalRepository
from .story_session_core_state_adapter import StorySessionCoreStateAdapter


class VersionHistoryReadService:
    """Build authoritative version lists from apply receipts."""

    def __init__(
        self,
        *,
        adapter: StorySessionCoreStateAdapter,
        proposal_repository: ProposalRepository,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
    ) -> None:
        self._adapter = adapter
        self._proposal_repository = proposal_repository
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled

    def list_versions(
        self,
        target_ref: ObjectRef,
        *,
        session_id: str | None = None,
    ) -> VersionListResult:
        ref = normalize_authoritative_ref(target_ref)
        session = self._adapter.get_story_session(session_id=session_id)
        if session is None:
            current_ref = f"{ref.object_id}@{ref.revision or 1}"
            return VersionListResult(versions=[current_ref], current_ref=current_ref)
        if self._store_read_enabled and self._core_state_store_repository is not None:
            revisions = self._core_state_store_repository.list_authoritative_revisions(
                session_id=session.session_id,
                object_id=ref.object_id,
            )
            if revisions:
                versions = [
                    f"{ref.object_id}@{item.revision}"
                    for item in sorted(revisions, key=lambda item: item.revision, reverse=True)
                ]
                return VersionListResult(
                    versions=versions,
                    current_ref=versions[0],
                )

        revisions = {1}
        for record in self._proposal_repository.list_apply_receipts_for_target(
            story_id=session.story_id,
            target_ref=ref,
            session_id=session.session_id,
        ):
            revision = record.revision_after_json.get(ref.object_id)
            if revision is not None:
                revisions.add(int(revision))

        ordered = sorted(revisions, reverse=True)
        versions = [f"{ref.object_id}@{revision}" for revision in ordered]
        return VersionListResult(
            versions=versions,
            current_ref=versions[0] if versions else f"{ref.object_id}@1",
        )
