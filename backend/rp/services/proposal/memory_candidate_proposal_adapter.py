"""Adapter from S3 memory-maintenance candidates to proposal inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, cast

from rp.models.memory.contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory.crud import AppendEventOp, ProposalSubmitInput, StatePatchOperation
from rp.models.memory.maintenance_candidate import (
    MemoryMaintenanceCandidate,
    MemoryMaintenanceCandidateBatch,
    MemoryMaintenanceOperation,
)
from rp.models.proposal.post_write_policy import (
    PolicyDecision,
    PostWriteMaintenancePolicy,
)
from rp.models.shared.dsl import Domain, Layer, ObjectRef
from rp.services.memory.memory_candidate_validation_service import (
    MemoryCandidateValidationService,
)


S3_MEMORY_MAINTENANCE_CANDIDATE_KIND = "s3_memory_maintenance_candidate"

_S3_TARGET_TO_AUTHORITATIVE_REF: dict[tuple[str, str], ObjectRef] = {
    (
        "plot_threads",
        "plot.active_threads",
    ): ObjectRef(
        object_id="plot_thread.active",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.PLOT_THREAD,
        domain_path="plot_thread.active",
        scope="story",
    ),
}
_BASE_REVISION_PATTERN = re.compile(r"^(?:block-revision-)?(?P<revision>\d+)$")


class MemoryCandidateProposalAdapterError(ValueError):
    """Stable S3 candidate handoff error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class CandidateProposalHandoff:
    """One proposal input plus S3 handoff evidence and policy mapping."""

    proposal_input: ProposalSubmitInput
    policy: PostWriteMaintenancePolicy | None = None
    source_refs: list[MemorySourceRef] = field(default_factory=list)
    trace_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryCandidateProposalAdapter:
    """Build canonical proposal inputs from named S3 memory candidates.

    S3 worker output is candidate material, not truth. This adapter is the
    explicit boundary where the candidate contract is translated into the
    existing proposal/apply contract while preserving the original S3 identity
    and fail-closing unsupported targets before proposal persistence.
    """

    def __init__(
        self,
        *,
        validation_service: MemoryCandidateValidationService | None = None,
    ) -> None:
        self._validation_service = validation_service or MemoryCandidateValidationService()

    def build_handoffs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        story_id: str,
        mode: str,
        candidate: dict[str, Any],
    ) -> list[CandidateProposalHandoff]:
        candidate_kind = _non_blank_text(candidate.get("candidate_kind"))
        if candidate_kind != S3_MEMORY_MAINTENANCE_CANDIDATE_KIND:
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_kind_unsupported",
                candidate_kind or "<blank>",
            )
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_payload_invalid",
                candidate_kind,
            )
        try:
            batch = MemoryMaintenanceCandidateBatch.model_validate(payload)
        except Exception as exc:
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_payload_invalid",
                str(exc),
            ) from exc

        validation = self._validation_service.validate_batch(batch)
        if not validation.accepted:
            first_error = validation.errors[0]
            raise MemoryCandidateProposalAdapterError(
                first_error.code,
                first_error.message,
            )

        outer_metadata = dict(candidate.get("metadata") or {})
        handoffs: list[CandidateProposalHandoff] = []
        for index, s3_candidate in enumerate(batch.candidates):
            handoffs.append(
                self._build_candidate_handoff(
                    identity=identity,
                    story_id=story_id,
                    mode=mode,
                    batch=batch,
                    candidate_kind=candidate_kind,
                    outer_metadata=outer_metadata,
                    candidate_index=index,
                    s3_candidate=s3_candidate,
                )
            )
        return handoffs

    def _build_candidate_handoff(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        story_id: str,
        mode: str,
        batch: MemoryMaintenanceCandidateBatch,
        candidate_kind: str,
        outer_metadata: dict[str, Any],
        candidate_index: int,
        s3_candidate: MemoryMaintenanceCandidate,
    ) -> CandidateProposalHandoff:
        target_ref = self._map_target(s3_candidate)
        base_revision = _parse_base_revision(s3_candidate.base_block_revision_id)
        base_ref = target_ref.model_copy(update={"revision": base_revision})
        operations = cast(
            list[StatePatchOperation],
            [
                self._map_operation(
                    target_ref=target_ref,
                    base_revision=base_revision,
                    candidate_kind=candidate_kind,
                    candidate_index=candidate_index,
                    s3_candidate=s3_candidate,
                    operation_index=operation_index,
                    operation=operation,
                )
                for operation_index, operation in enumerate(s3_candidate.operations)
            ],
        )
        source_refs = list(s3_candidate.source_refs)
        trace_refs = _unique_non_blank(
            [
                f"s3_candidate_kind:{candidate_kind}",
                f"s3_target_domain:{s3_candidate.target_domain}",
                f"s3_target_block:{s3_candidate.target_block_id}",
                f"s3_worker:{batch.worker_id}",
                f"s3_phase:{batch.phase}",
                f"s3_base_revision:{s3_candidate.base_block_revision_id}",
                f"runtime_turn:{identity.turn_id}",
            ]
        )
        metadata = {
            "original_candidate_kind": candidate_kind,
            "s3_target_domain": s3_candidate.target_domain,
            "s3_target_block_id": s3_candidate.target_block_id,
            "worker_id": batch.worker_id,
            "phase": batch.phase,
            "source_of_truth": False,
            "authoritative_mutation": False,
            "base_revision_bridge": {
                "source_field": "base_block_revision_id",
                "source_value": s3_candidate.base_block_revision_id,
                "base_ref_revision": base_revision,
            },
            "source_ref_count": len(source_refs),
            "trace_refs": trace_refs,
        }
        return CandidateProposalHandoff(
            proposal_input=ProposalSubmitInput(
                story_id=story_id,
                mode=mode,
                domain=target_ref.domain,
                domain_path=target_ref.domain_path,
                operations=operations,
                base_refs=[base_ref],
                reason=(
                    "s3_memory_maintenance_candidate:"
                    f"{s3_candidate.target_domain}/{s3_candidate.target_block_id}:"
                    f"{s3_candidate.change_summary}"
                ),
                trace_id="|".join(trace_refs),
            ),
            policy=_policy_for_route(
                _governance_route(
                    outer_metadata=outer_metadata,
                    batch_metadata=batch.metadata,
                    candidate_metadata=s3_candidate.metadata,
                )
            ),
            source_refs=source_refs,
            trace_refs=trace_refs,
            metadata=metadata,
        )

    @staticmethod
    def _map_target(s3_candidate: MemoryMaintenanceCandidate) -> ObjectRef:
        target = _S3_TARGET_TO_AUTHORITATIVE_REF.get(
            (s3_candidate.target_domain, s3_candidate.target_block_id)
        )
        if target is None:
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_target_unsupported_for_s3c",
                f"{s3_candidate.target_domain}:{s3_candidate.target_block_id}",
            )
        return target

    @staticmethod
    def _map_operation(
        *,
        target_ref: ObjectRef,
        base_revision: int,
        candidate_kind: str,
        candidate_index: int,
        s3_candidate: MemoryMaintenanceCandidate,
        operation_index: int,
        operation: MemoryMaintenanceOperation,
    ) -> AppendEventOp:
        if operation.kind != "append_item":
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_operation_unsupported_for_s3c",
                operation.kind,
            )
        if operation.content is None:
            raise MemoryCandidateProposalAdapterError(
                "memory_candidate_missing_fact_content",
                f"candidate={candidate_index}:operation={operation_index}",
            )
        return AppendEventOp(
            target_ref=target_ref,
            event_data={
                "content": operation.content,
                "candidate_kind": candidate_kind,
                "s3_target_domain": s3_candidate.target_domain,
                "s3_target_block_id": s3_candidate.target_block_id,
                "field_id": operation.field_id,
                "group_key": operation.group_key,
                "subject_label": operation.subject_label,
                "change_summary": s3_candidate.change_summary,
                "base_revision": base_revision,
                "source_refs": [
                    ref.model_dump(mode="json") for ref in s3_candidate.source_refs
                ],
                "operation_metadata": dict(operation.metadata),
            },
        )


def _parse_base_revision(value: str | None) -> int:
    normalized = _non_blank_text(value)
    if normalized is None:
        raise MemoryCandidateProposalAdapterError(
            "memory_candidate_base_revision_missing",
            "base_block_revision_id",
        )
    match = _BASE_REVISION_PATTERN.match(normalized)
    if match is None:
        raise MemoryCandidateProposalAdapterError(
            "memory_candidate_base_revision_unparseable",
            normalized,
        )
    return int(match.group("revision"))


def _governance_route(
    *,
    outer_metadata: dict[str, Any],
    batch_metadata: dict[str, Any],
    candidate_metadata: dict[str, Any],
) -> str:
    for payload in (candidate_metadata, batch_metadata, outer_metadata):
        route = _non_blank_text(
            payload.get("governance_route")
            or payload.get("s3_governance_route")
            or payload.get("governance_decision")
        )
        if route is not None:
            return route
    return "review_required"


def _policy_for_route(route: str) -> PostWriteMaintenancePolicy:
    if route == "review_required":
        decision = PolicyDecision.REVIEW_REQUIRED
    elif route == "direct_apply_allowed":
        decision = PolicyDecision.NOTIFY_APPLY
    else:
        raise MemoryCandidateProposalAdapterError(
            "memory_candidate_governance_route_unsupported",
            route,
        )
    return PostWriteMaintenancePolicy(
        preset_id=f"s3c_memory_candidate_{route}",
        fallback_decision=decision,
    )


def _non_blank_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _unique_non_blank(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized
