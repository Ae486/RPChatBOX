"""Authoritative provenance read side over persisted proposal/apply receipts."""

from __future__ import annotations

from .core_state_store_repository import CoreStateStoreRepository
from rp.models.dsl import ObjectRef
from rp.models.memory_crud import ProvenanceResult

from .memory_object_mapper import normalize_authoritative_ref
from .proposal_repository import ProposalRepository
from .story_session_core_state_adapter import StorySessionCoreStateAdapter


class ProvenanceReadService:
    """Build authoritative provenance from proposal/apply persistence."""

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

    def read_provenance(
        self,
        target_ref: ObjectRef,
        *,
        session_id: str | None = None,
    ) -> ProvenanceResult:
        ref = normalize_authoritative_ref(target_ref)
        source_refs: list[str] = ["compatibility_mirror:story_session.current_state_json"]
        proposal_refs: list[str] = []
        session = self._adapter.get_story_session(session_id=session_id)
        if session is None:
            return ProvenanceResult(
                target_ref=ref,
                source_refs=source_refs,
                proposal_refs=proposal_refs,
                ingestion_refs=[],
            )
        if self._store_read_enabled and self._core_state_store_repository is not None:
            row = self._core_state_store_repository.get_authoritative_object(
                session_id=session.session_id,
                layer=ref.layer.value,
                scope=ref.scope or "story",
                object_id=ref.object_id,
            )
            if row is not None:
                link = self._proposal_repository.get_apply_target_link_for_target(
                    session_id=session.session_id,
                    object_id=ref.object_id,
                    revision=row.current_revision,
                )
                if link is not None:
                    proposal_refs.append(f"proposal:{link.proposal_id}")
                    proposal_record = self._proposal_repository.get_proposal_record(link.proposal_id)
                    if proposal_record is not None:
                        for base_ref in proposal_record.base_refs_json:
                            if base_ref.get("object_id"):
                                source_refs.append(f"base_ref:{base_ref['object_id']}")
                return ProvenanceResult(
                    target_ref=ref.model_copy(update={"revision": row.current_revision}),
                    source_refs=list(dict.fromkeys(["core_state_store:authoritative_revision", *source_refs[1:]])),
                    proposal_refs=proposal_refs,
                    ingestion_refs=[],
                )

        seen_proposals: set[str] = set()
        for record in self._proposal_repository.list_apply_receipts_for_target(
            story_id=session.story_id,
            target_ref=ref,
            session_id=session.session_id,
        ):
            if record.proposal_id not in seen_proposals:
                seen_proposals.add(record.proposal_id)
                proposal_refs.append(f"proposal:{record.proposal_id}")
            proposal_record = self._proposal_repository.get_proposal_record(record.proposal_id)
            if proposal_record is None:
                continue
            for base_ref in proposal_record.base_refs_json:
                if base_ref.get("object_id"):
                    source_refs.append(f"base_ref:{base_ref['object_id']}")

        return ProvenanceResult(
            target_ref=ref,
            source_refs=list(dict.fromkeys(source_refs)),
            proposal_refs=proposal_refs,
            ingestion_refs=[],
        )
