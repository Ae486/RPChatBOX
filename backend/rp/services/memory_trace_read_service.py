"""Read-only debug/eval traces over persisted memory evidence."""

from __future__ import annotations

from typing import Any, Iterable

from sqlmodel import Session, select

from models.rp_memory_store import (
    MemoryApplyReceiptRecord,
    MemoryChangeEventRecord,
    MemoryProposalRecord,
    RuntimeWorkspaceMaterialRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_trace import MemoryTraceBundle
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.proposal_repository import ProposalRepository
from rp.services.runtime_memory_persistence_repository import (
    MemoryChangeEventRepository,
    RuntimeWorkspaceMaterialRepository,
    clone_json_value,
)
from rp.services.runtime_read_manifest_service import (
    RuntimeReadManifestService,
    RuntimeReadManifestServiceError,
)
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)


class MemoryTraceReadService:
    """Join persisted memory evidence without replaying it into business truth."""

    def __init__(
        self,
        *,
        session: Session,
        event_repository: MemoryChangeEventRepository | None = None,
        material_repository: RuntimeWorkspaceMaterialRepository | None = None,
        proposal_repository: ProposalRepository | None = None,
        runtime_read_manifest_service: RuntimeReadManifestService | None = None,
    ) -> None:
        self._session = session
        self._event_repository = event_repository or MemoryChangeEventRepository(
            session
        )
        self._material_repository = (
            material_repository or RuntimeWorkspaceMaterialRepository(session)
        )
        self._proposal_repository = proposal_repository or ProposalRepository(session)
        self._runtime_read_manifest_service = (
            runtime_read_manifest_service
            or RuntimeReadManifestService(
                session=session,
                runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
                    session=session
                ),
            )
        )

    def get_turn_trace(self, *, identity: MemoryRuntimeIdentity) -> dict[str, Any]:
        """Return exact-identity turn evidence from durable memory stores."""

        events = self._event_repository.list_events(identity=identity)
        materials = self._material_repository.list(identity=identity)
        proposal_records = self._proposal_records_for_identity(
            story_id=identity.story_id,
            identity=identity,
            related_proposal_ids=self._proposal_ids_from_records(
                events=events,
                materials=materials,
            ),
        )
        bundle = self._bundle(
            trace_kind="turn",
            trace_scope={"query": "exact_identity"},
            identity=identity,
            events=events,
            materials=materials,
            proposal_records=proposal_records,
            manifest_identities=[identity],
        )
        return bundle.model_dump(mode="json")

    def get_branch_trace(
        self,
        *,
        story_id: str,
        branch_head_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return branch-scoped trace evidence across persisted turns."""

        normalized_limit = max(1, int(limit))
        events = self._event_records_for_branch(
            story_id=story_id,
            branch_head_id=branch_head_id,
            limit=normalized_limit,
        )
        materials = self._material_records_for_branch(
            story_id=story_id,
            branch_head_id=branch_head_id,
            limit=normalized_limit,
        )
        proposal_records = self._proposal_records_for_branch(
            story_id=story_id,
            branch_head_id=branch_head_id,
            related_proposal_ids=self._proposal_ids_from_records(
                events=events,
                materials=materials,
            ),
            limit=normalized_limit,
        )
        identities = self._identities_from_evidence(
            events=events,
            materials=materials,
            proposal_records=proposal_records,
        )
        bundle = self._bundle(
            trace_kind="branch",
            trace_scope={
                "story_id": story_id,
                "branch_head_id": branch_head_id,
                "limit": normalized_limit,
            },
            identity=None,
            events=events,
            materials=materials,
            proposal_records=proposal_records,
            manifest_identities=identities,
        )
        return bundle.model_dump(mode="json")

    def get_source_ref_trace(
        self,
        *,
        source_ref: str,
        story_id: str,
    ) -> dict[str, Any]:
        """Return evidence connected to a source ref id or `type:id` token."""

        source_ref = _require_text(source_ref, field_name="source_ref")
        events = [
            record
            for record in self._event_records_for_story(story_id)
            if self._record_has_source_ref(record, source_ref)
        ]
        materials = [
            record
            for record in self._material_records_for_story(story_id)
            if self._material_matches_ref(record, source_ref)
        ]
        proposal_records = self._proposal_records_for_source_ref(
            story_id=story_id,
            source_ref=source_ref,
            related_proposal_ids=self._proposal_ids_from_records(
                events=events,
                materials=materials,
            ),
        )
        identities = self._identities_from_evidence(
            events=events,
            materials=materials,
            proposal_records=proposal_records,
        )
        bundle = self._bundle(
            trace_kind="source_ref",
            trace_scope={"story_id": story_id, "source_ref": source_ref},
            identity=None,
            events=events,
            materials=materials,
            proposal_records=proposal_records,
            manifest_identities=identities,
        )
        return bundle.model_dump(mode="json")

    def get_proposal_trace(
        self,
        *,
        proposal_id: str,
        story_id: str,
    ) -> dict[str, Any]:
        """Return proposal/apply receipts plus related events and materials."""

        proposal_id = _require_text(proposal_id, field_name="proposal_id")
        proposal_record = self._proposal_repository.get_proposal_record(proposal_id)
        proposal_records = (
            [proposal_record]
            if proposal_record is not None and proposal_record.story_id == story_id
            else []
        )
        events = [
            record
            for record in self._event_records_for_story(story_id)
            if self._event_matches_proposal(record, proposal_id)
        ]
        material_refs = self._material_refs_from_events(events)
        material_refs.update(self._material_refs_from_proposals(proposal_records))
        materials = [
            record
            for record in self._material_records_for_story(story_id)
            if record.material_id in material_refs
            or self._material_matches_ref(record, proposal_id)
            or any(
                self._material_matches_ref(record, material_ref)
                for material_ref in material_refs
            )
        ]
        identities = self._identities_from_evidence(
            events=events,
            materials=materials,
            proposal_records=proposal_records,
        )
        bundle = self._bundle(
            trace_kind="proposal",
            trace_scope={"story_id": story_id, "proposal_id": proposal_id},
            identity=identities[0] if len(identities) == 1 else None,
            events=events,
            materials=materials,
            proposal_records=proposal_records,
            manifest_identities=identities,
        )
        return bundle.model_dump(mode="json")

    def get_material_trace(
        self,
        *,
        material_ref: str,
        story_id: str,
    ) -> dict[str, Any]:
        """Return trace evidence related to a Runtime Workspace material ref."""

        material_ref = _require_text(material_ref, field_name="material_ref")
        materials = [
            record
            for record in self._material_records_for_story(story_id)
            if self._material_matches_ref(record, material_ref)
        ]
        material_ids = {record.material_id for record in materials}
        events = [
            record
            for record in self._event_records_for_story(story_id)
            if record.entry_id in material_ids
            or self._record_has_source_ref(record, material_ref)
            or any(
                self._record_has_source_ref(record, material_id)
                for material_id in material_ids
            )
        ]
        proposal_records = self._proposal_records_for_source_ref(
            story_id=story_id,
            source_ref=material_ref,
            related_proposal_ids=self._proposal_ids_from_records(
                events=events,
                materials=materials,
            ),
        )
        identities = self._identities_from_evidence(
            events=events,
            materials=materials,
            proposal_records=proposal_records,
        )
        bundle = self._bundle(
            trace_kind="material",
            trace_scope={"story_id": story_id, "material_ref": material_ref},
            identity=identities[0] if len(identities) == 1 else None,
            events=events,
            materials=materials,
            proposal_records=proposal_records,
            manifest_identities=identities,
        )
        return bundle.model_dump(mode="json")

    def _bundle(
        self,
        *,
        trace_kind,
        trace_scope: dict[str, Any],
        identity: MemoryRuntimeIdentity | None,
        events: list[MemoryChangeEventRecord],
        materials: list[RuntimeWorkspaceMaterialRecord],
        proposal_records: list[MemoryProposalRecord],
        manifest_identities: list[MemoryRuntimeIdentity],
    ) -> MemoryTraceBundle:
        warnings: list[str] = []
        manifests = self._build_read_manifests(
            manifest_identities,
            warnings=warnings,
        )
        material_items = [self._material_item(record) for record in materials]
        return MemoryTraceBundle(
            trace_kind=trace_kind,
            trace_scope=clone_json_value(trace_scope),
            identity=identity,
            events=[self._event_item(record) for record in events],
            runtime_workspace_materials=material_items,
            read_manifests=manifests,
            proposal_receipts=[
                self._proposal_receipt_item(record) for record in proposal_records
            ],
            retrieval_usage_refs=self._retrieval_usage_refs(material_items),
            dirty_targets=self._dirty_targets_from_events(events),
            warnings=warnings,
        )

    def _build_read_manifests(
        self,
        identities: list[MemoryRuntimeIdentity],
        *,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for identity in self._dedupe_identities(identities):
            try:
                manifest = self._runtime_read_manifest_service.build_writer_manifest(
                    identity=identity,
                    packet_kind="writer",
                )
            except RuntimeReadManifestServiceError as exc:
                warnings.append(
                    f"read_manifest_unavailable:{exc.code}:{identity.turn_id}"
                )
                continue
            manifests.append(
                {
                    **manifest.model_dump(mode="json"),
                    "readback_route": "deterministic_rebuild",
                    "source_of_truth": False,
                }
            )
        return manifests

    def _proposal_records_for_identity(
        self,
        *,
        story_id: str,
        identity: MemoryRuntimeIdentity,
        related_proposal_ids: set[str],
    ) -> list[MemoryProposalRecord]:
        return [
            record
            for record in self._proposal_repository.list_proposals_for_story(story_id)
            if record.proposal_id in related_proposal_ids
            or self._proposal_identity(record) == identity
        ]

    def _proposal_records_for_branch(
        self,
        *,
        story_id: str,
        branch_head_id: str,
        related_proposal_ids: set[str],
        limit: int,
    ) -> list[MemoryProposalRecord]:
        records: list[MemoryProposalRecord] = []
        for record in self._proposal_repository.list_proposals_for_story(story_id):
            identity = self._proposal_identity(record)
            if record.proposal_id in related_proposal_ids or (
                identity is not None and identity.branch_head_id == branch_head_id
            ):
                records.append(record)
        return records[:limit]

    def _proposal_records_for_source_ref(
        self,
        *,
        story_id: str,
        source_ref: str,
        related_proposal_ids: set[str],
    ) -> list[MemoryProposalRecord]:
        return [
            record
            for record in self._proposal_repository.list_proposals_for_story(story_id)
            if record.proposal_id in related_proposal_ids
            or self._proposal_matches_source_ref(record, source_ref)
        ]

    def _proposal_ids_from_records(
        self,
        *,
        events: list[MemoryChangeEventRecord],
        materials: list[RuntimeWorkspaceMaterialRecord],
    ) -> set[str]:
        proposal_ids: set[str] = set()
        for event in events:
            metadata = _dict(event.metadata_json)
            proposal_id = _text(metadata.get("proposal_id"))
            if proposal_id is not None:
                proposal_ids.add(proposal_id)
            for ref in _list_of_dicts(event.source_refs_json):
                if _text(ref.get("source_type")) in {
                    "memory_proposal",
                    "proposal",
                    "proposal_receipt",
                }:
                    source_id = _text(ref.get("source_id"))
                    if source_id is not None:
                        proposal_ids.add(source_id)
                ref_proposal_id = _text(_dict(ref.get("metadata")).get("proposal_id"))
                if ref_proposal_id is not None:
                    proposal_ids.add(ref_proposal_id)
        for material in materials:
            for ref in _list_of_dicts(material.source_refs_json):
                proposal_id = _text(_dict(ref.get("metadata")).get("proposal_id"))
                if proposal_id is not None:
                    proposal_ids.add(proposal_id)
        return proposal_ids

    def _proposal_identity(
        self,
        record: MemoryProposalRecord,
    ) -> MemoryRuntimeIdentity | None:
        metadata = _dict(record.governance_metadata_json)
        for raw_identity in (
            metadata.get("identity"),
            _dict(metadata.get("core_mutation")).get("identity"),
        ):
            identity = self._identity_from_payload(raw_identity)
            if identity is not None:
                return identity
        return None

    def _proposal_matches_source_ref(
        self,
        record: MemoryProposalRecord,
        source_ref: str,
    ) -> bool:
        metadata = _dict(record.governance_metadata_json)
        if _ref_token_matches(record.trace_id, source_ref):
            return True
        source_ref_payloads = [
            *_list_of_dicts(metadata.get("source_refs")),
            *_list_of_dicts(_dict(metadata.get("core_mutation")).get("source_refs")),
        ]
        return any(_source_ref_matches(ref, source_ref) for ref in source_ref_payloads)

    def _event_matches_proposal(
        self,
        record: MemoryChangeEventRecord,
        proposal_id: str,
    ) -> bool:
        metadata = _dict(record.metadata_json)
        if metadata.get("proposal_id") == proposal_id:
            return True
        return any(
            _source_ref_matches(ref, proposal_id)
            for ref in _list_of_dicts(record.source_refs_json)
        )

    def _record_has_source_ref(
        self,
        record: MemoryChangeEventRecord,
        source_ref: str,
    ) -> bool:
        if record.entry_id == source_ref or record.event_id == source_ref:
            return True
        metadata = _dict(record.metadata_json)
        if any(
            _ref_token_matches(metadata.get(key), source_ref)
            for key in ("proposal_id", "apply_id", "material_id")
        ):
            return True
        return any(
            _source_ref_matches(ref, source_ref)
            for ref in _list_of_dicts(record.source_refs_json)
        )

    def _material_matches_ref(
        self,
        record: RuntimeWorkspaceMaterialRecord,
        material_ref: str,
    ) -> bool:
        if record.material_id == material_ref or record.short_id == material_ref:
            return True
        if (
            record.materialization_ref == material_ref
            or record.expiration_ref == material_ref
        ):
            return True
        metadata = _dict(record.metadata_json)
        payload = _dict(record.payload_json)
        if any(
            _ref_token_matches(metadata.get(key), material_ref)
            for key in (
                "proposal_id",
                "apply_id",
                "material_id",
                "expanded_from_card_material_id",
            )
        ):
            return True
        if any(
            _ref_token_matches(payload.get(key), material_ref)
            for key in ("card_material_id", "hit_id", "query_id")
        ):
            return True
        if any(
            _ref_token_matches(item, material_ref)
            for key in (
                "used_card_material_ids",
                "used_expanded_chunk_material_ids",
                "missed_query_material_ids",
            )
            for item in _list_of_text(payload.get(key))
        ):
            return True
        return any(
            _source_ref_matches(ref, material_ref)
            for ref in _list_of_dicts(record.source_refs_json)
        )

    def _material_refs_from_events(
        self,
        events: list[MemoryChangeEventRecord],
    ) -> set[str]:
        material_ids: set[str] = set()
        for event in events:
            if event.entry_id:
                material_ids.add(event.entry_id)
            metadata = _dict(event.metadata_json)
            material_id = _text(metadata.get("material_id"))
            if material_id is not None:
                material_ids.add(material_id)
            for ref in _list_of_dicts(event.source_refs_json):
                entry_id = _text(ref.get("entry_id"))
                if entry_id is not None:
                    material_ids.add(entry_id)
        return material_ids

    def _material_refs_from_proposals(
        self,
        proposal_records: list[MemoryProposalRecord],
    ) -> set[str]:
        material_ids: set[str] = set()
        for record in proposal_records:
            metadata = _dict(record.governance_metadata_json)
            source_ref_payloads = [
                *_list_of_dicts(metadata.get("source_refs")),
                *_list_of_dicts(
                    _dict(metadata.get("core_mutation")).get("source_refs")
                ),
            ]
            for ref in source_ref_payloads:
                if _text(ref.get("source_type")) in {
                    RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD.value,
                    RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK.value,
                    RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS.value,
                    RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD.value,
                    "runtime_workspace_material",
                    "runtime_workspace",
                }:
                    source_id = _text(ref.get("source_id"))
                    if source_id is not None:
                        material_ids.add(source_id)
                entry_id = _text(ref.get("entry_id"))
                if entry_id is not None:
                    material_ids.add(entry_id)
                ref_metadata = _dict(ref.get("metadata"))
                for key in ("material_id", "source_ref"):
                    material_id = _text(ref_metadata.get(key))
                    if material_id is not None:
                        material_ids.add(material_id)
        return material_ids

    def _identities_from_evidence(
        self,
        *,
        events: list[MemoryChangeEventRecord],
        materials: list[RuntimeWorkspaceMaterialRecord],
        proposal_records: list[MemoryProposalRecord],
    ) -> list[MemoryRuntimeIdentity]:
        identities: list[MemoryRuntimeIdentity] = []
        for record in events:
            identities.append(
                MemoryRuntimeIdentity(
                    story_id=record.story_id,
                    session_id=record.session_id,
                    branch_head_id=record.branch_head_id,
                    turn_id=record.turn_id,
                    runtime_profile_snapshot_id=record.runtime_profile_snapshot_id,
                )
            )
        for record in materials:
            identities.append(
                MemoryRuntimeIdentity(
                    story_id=record.story_id,
                    session_id=record.session_id,
                    branch_head_id=record.branch_head_id,
                    turn_id=record.turn_id,
                    runtime_profile_snapshot_id=record.runtime_profile_snapshot_id,
                )
            )
        for record in proposal_records:
            identity = self._proposal_identity(record)
            if identity is not None:
                identities.append(identity)
        return self._dedupe_identities(identities)

    @staticmethod
    def _dedupe_identities(
        identities: Iterable[MemoryRuntimeIdentity],
    ) -> list[MemoryRuntimeIdentity]:
        result: list[MemoryRuntimeIdentity] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for identity in identities:
            key = (
                identity.story_id,
                identity.session_id,
                identity.branch_head_id,
                identity.turn_id,
                identity.runtime_profile_snapshot_id,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(identity)
        return result

    @staticmethod
    def _identity_from_payload(payload: Any) -> MemoryRuntimeIdentity | None:
        if not isinstance(payload, dict):
            return None
        try:
            return MemoryRuntimeIdentity.model_validate(payload)
        except ValueError:
            return None

    def _event_records_for_story(self, story_id: str) -> list[MemoryChangeEventRecord]:
        stmt = (
            select(MemoryChangeEventRecord)
            .where(MemoryChangeEventRecord.story_id == story_id)
            .order_by(MemoryChangeEventRecord.created_at.asc())
            .order_by(MemoryChangeEventRecord.event_id.asc())
        )
        return list(self._session.exec(stmt).all())

    def _event_records_for_branch(
        self,
        *,
        story_id: str,
        branch_head_id: str,
        limit: int,
    ) -> list[MemoryChangeEventRecord]:
        stmt = (
            select(MemoryChangeEventRecord)
            .where(MemoryChangeEventRecord.story_id == story_id)
            .where(MemoryChangeEventRecord.branch_head_id == branch_head_id)
            .order_by(MemoryChangeEventRecord.created_at.asc())
            .order_by(MemoryChangeEventRecord.event_id.asc())
            .limit(limit)
        )
        return list(self._session.exec(stmt).all())

    def _material_records_for_story(
        self,
        story_id: str,
    ) -> list[RuntimeWorkspaceMaterialRecord]:
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(RuntimeWorkspaceMaterialRecord.story_id == story_id)
            .order_by(RuntimeWorkspaceMaterialRecord.created_at.asc())
            .order_by(RuntimeWorkspaceMaterialRecord.material_id.asc())
        )
        return list(self._session.exec(stmt).all())

    def _material_records_for_branch(
        self,
        *,
        story_id: str,
        branch_head_id: str,
        limit: int,
    ) -> list[RuntimeWorkspaceMaterialRecord]:
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(RuntimeWorkspaceMaterialRecord.story_id == story_id)
            .where(RuntimeWorkspaceMaterialRecord.branch_head_id == branch_head_id)
            .order_by(RuntimeWorkspaceMaterialRecord.created_at.asc())
            .order_by(RuntimeWorkspaceMaterialRecord.material_id.asc())
            .limit(limit)
        )
        return list(self._session.exec(stmt).all())

    def _event_item(self, record: MemoryChangeEventRecord) -> dict[str, Any]:
        return {
            "event_id": record.event_id,
            "identity": self._identity_record_payload(record),
            "actor": record.actor,
            "event_kind": record.event_kind,
            "layer": record.layer,
            "domain": record.domain,
            "block_id": record.block_id,
            "entry_id": record.entry_id,
            "operation_kind": record.operation_kind,
            "source_refs": clone_json_value(record.source_refs_json),
            "dirty_targets": clone_json_value(record.dirty_targets_json),
            "visibility_effect": record.visibility_effect,
            "metadata": clone_json_value(record.metadata_json),
            "created_at": _datetime_to_json(record.created_at),
        }

    @staticmethod
    def _material_item(record: RuntimeWorkspaceMaterialRecord) -> dict[str, Any]:
        return {
            "material_id": record.material_id,
            "identity": {
                "story_id": record.story_id,
                "session_id": record.session_id,
                "branch_head_id": record.branch_head_id,
                "turn_id": record.turn_id,
                "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
            },
            "material_kind": record.material_kind,
            "domain": record.domain,
            "domain_path": record.domain_path,
            "short_id": record.short_id,
            "lifecycle": record.lifecycle,
            "visibility": record.visibility,
            "created_by": record.created_by,
            "expiration_ref": record.expiration_ref,
            "materialization_ref": record.materialization_ref,
            "payload": clone_json_value(record.payload_json),
            "source_refs": clone_json_value(record.source_refs_json),
            "metadata": clone_json_value(record.metadata_json),
            "created_at": _datetime_to_json(record.created_at),
            "updated_at": _datetime_to_json(record.updated_at),
            "expired_at": _datetime_to_json(record.expired_at),
            "invalidated_at": _datetime_to_json(record.invalidated_at),
        }

    def _proposal_receipt_item(self, record: MemoryProposalRecord) -> dict[str, Any]:
        return {
            "proposal": {
                "proposal_id": record.proposal_id,
                "story_id": record.story_id,
                "session_id": record.session_id,
                "chapter_workspace_id": record.chapter_workspace_id,
                "mode": record.mode,
                "domain": record.domain,
                "domain_path": record.domain_path,
                "status": record.status,
                "policy_decision": record.policy_decision,
                "submit_source": record.submit_source,
                "operations": clone_json_value(record.operations_json),
                "base_refs": clone_json_value(record.base_refs_json),
                "reason": record.reason,
                "trace_id": record.trace_id,
                "governance_metadata": clone_json_value(
                    record.governance_metadata_json
                ),
                "created_at": _datetime_to_json(record.created_at),
                "updated_at": _datetime_to_json(record.updated_at),
                "applied_at": _datetime_to_json(record.applied_at),
                "error_message": record.error_message,
            },
            "apply_receipts": [
                self._apply_receipt_item(item)
                for item in self._proposal_repository.list_apply_receipts_for_proposal(
                    record.proposal_id
                )
            ],
        }

    @staticmethod
    def _apply_receipt_item(record: MemoryApplyReceiptRecord) -> dict[str, Any]:
        return {
            "apply_id": record.apply_id,
            "proposal_id": record.proposal_id,
            "story_id": record.story_id,
            "session_id": record.session_id,
            "chapter_workspace_id": record.chapter_workspace_id,
            "target_refs": clone_json_value(record.target_refs_json),
            "revision_after": clone_json_value(record.revision_after_json),
            "before_snapshot": clone_json_value(record.before_snapshot_json),
            "after_snapshot": clone_json_value(record.after_snapshot_json),
            "warnings": list(record.warnings_json),
            "apply_backend": record.apply_backend,
            "created_at": _datetime_to_json(record.created_at),
        }

    @staticmethod
    def _retrieval_usage_refs(
        material_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for material in material_items:
            if (
                material["material_kind"]
                != RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD.value
            ):
                continue
            payload = _dict(material.get("payload"))
            refs.append(
                {
                    "material_id": material["material_id"],
                    "short_id": material.get("short_id"),
                    "used_card_material_ids": _list_of_text(
                        payload.get("used_card_material_ids")
                    ),
                    "used_expanded_chunk_material_ids": _list_of_text(
                        payload.get("used_expanded_chunk_material_ids")
                    ),
                    "missed_query_material_ids": _list_of_text(
                        payload.get("missed_query_material_ids")
                    ),
                    "source_refs": clone_json_value(material.get("source_refs", [])),
                }
            )
        return refs

    @staticmethod
    def _dirty_targets_from_events(
        events: list[MemoryChangeEventRecord],
    ) -> list[dict[str, Any]]:
        dirty_targets: list[dict[str, Any]] = []
        for event in events:
            for target in _list_of_dicts(event.dirty_targets_json):
                dirty_targets.append(
                    {
                        **clone_json_value(target),
                        "event_id": event.event_id,
                    }
                )
        return dirty_targets

    @staticmethod
    def _identity_record_payload(record: MemoryChangeEventRecord) -> dict[str, str]:
        return {
            "story_id": record.story_id,
            "session_id": record.session_id,
            "branch_head_id": record.branch_head_id,
            "turn_id": record.turn_id,
            "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
        }


def _source_ref_matches(ref: dict[str, Any], needle: str) -> bool:
    source_type = _text(ref.get("source_type"))
    source_id = _text(ref.get("source_id"))
    entry_id = _text(ref.get("entry_id"))
    if source_id == needle or entry_id == needle:
        return True
    if source_type is not None and source_id is not None:
        if f"{source_type}:{source_id}" == needle:
            return True
    metadata = _dict(ref.get("metadata"))
    return any(
        _ref_token_matches(metadata.get(key), needle)
        for key in ("proposal_id", "apply_id", "material_id", "source_ref")
    )


def _ref_token_matches(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle or needle in value.split(",")
    if isinstance(value, list):
        return any(_ref_token_matches(item, needle) for item in value)
    return False


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _require_text(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _datetime_to_json(value: Any) -> str | None:
    return None if value is None else value.isoformat()
