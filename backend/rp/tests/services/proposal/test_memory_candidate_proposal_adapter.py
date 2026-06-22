from __future__ import annotations

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.shared.dsl import Domain, Layer
from rp.services.proposal.memory_candidate_proposal_adapter import (
    MemoryCandidateProposalAdapter,
    MemoryCandidateProposalAdapterError,
    S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
)
from rp.services.writer.memory_maintenance_worker_adapter import (
    S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
)
from rp.services.writer.worker_registry_service import LONGFORM_MEMORY_WORKER_ID


def test_adapter_emits_canonical_proposal_input_and_preserves_s3_boundary():
    handoffs = MemoryCandidateProposalAdapter().build_handoffs(
        identity=_identity(),
        story_id="story-s3c",
        mode="longform",
        candidate=_worker_candidate(),
    )

    assert len(handoffs) == 1
    handoff = handoffs[0]
    proposal_input = handoff.proposal_input
    assert proposal_input.story_id == "story-s3c"
    assert proposal_input.mode == "longform"
    assert proposal_input.domain == Domain.PLOT_THREAD
    assert proposal_input.domain_path == "plot_thread.active"
    assert proposal_input.operations[0].kind == "append_event"
    assert proposal_input.operations[0].target_ref.object_id == "plot_thread.active"
    assert proposal_input.operations[0].target_ref.layer == (
        Layer.CORE_STATE_AUTHORITATIVE
    )
    assert proposal_input.operations[0].event_data["content"] == (
        "The bridge cutoff becomes the active thread."
    )
    assert proposal_input.operations[0].event_data["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert proposal_input.base_refs[0].object_id == "plot_thread.active"
    assert proposal_input.base_refs[0].revision == 1
    assert handoff.metadata["original_candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert handoff.metadata["s3_target_domain"] == "plot_threads"
    assert handoff.metadata["s3_target_block_id"] == "plot.active_threads"
    assert handoff.metadata["source_of_truth"] is False
    assert handoff.metadata["authoritative_mutation"] is False
    assert handoff.metadata["base_revision_bridge"] == {
        "source_field": "base_block_revision_id",
        "source_value": "block-revision-1",
        "base_ref_revision": 1,
    }
    assert any(
        ref.source_type == "accepted_prose" and ref.source_id == "segment-s3c-1"
        for ref in handoff.source_refs
    )
    assert "s3_candidate_kind:s3_memory_maintenance_candidate" in handoff.trace_refs


def test_adapter_accepts_plain_numeric_base_revision():
    payload = _worker_candidate()
    payload["payload"]["candidates"][0]["base_block_revision_id"] = "1"

    handoff = MemoryCandidateProposalAdapter().build_handoffs(
        identity=_identity(),
        story_id="story-s3c",
        mode="longform",
        candidate=payload,
    )[0]

    assert handoff.proposal_input.base_refs[0].revision == 1


@pytest.mark.parametrize(
    ("mutate_payload", "expected_code"),
    [
        (
            lambda payload: payload["payload"]["candidates"][0].update(
                {"base_block_revision_id": None}
            ),
            "memory_candidate_missing_base_block_revision",
        ),
        (
            lambda payload: payload["payload"]["candidates"][0].update(
                {"base_block_revision_id": "revision-one"}
            ),
            "memory_candidate_base_revision_unparseable",
        ),
        (
            lambda payload: payload["payload"]["candidates"][0].update(
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                }
            ),
            "memory_candidate_target_unsupported_for_s3c",
        ),
        (
            lambda payload: payload["payload"]["candidates"][0]["operations"][
                0
            ].update(
                {
                    "kind": "update_item",
                    "target_fact_id": "fact-plot-1",
                }
            ),
            "memory_candidate_operation_unsupported_for_s3c",
        ),
    ],
)
def test_adapter_fails_closed_before_proposal_submit(mutate_payload, expected_code):
    payload = _worker_candidate()
    mutate_payload(payload)

    with pytest.raises(MemoryCandidateProposalAdapterError) as exc_info:
        MemoryCandidateProposalAdapter().build_handoffs(
            identity=_identity(),
            story_id="story-s3c",
            mode="longform",
            candidate=payload,
        )

    assert exc_info.value.code == expected_code


def _identity() -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-s3c",
        session_id="session-s3c",
        branch_head_id="branch-s3c-main",
        turn_id="turn-s3c-1",
        runtime_profile_snapshot_id="snapshot-s3c-1",
    )


def _worker_candidate() -> dict:
    return {
        "candidate_kind": S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
        "payload": {
            "schema_version": S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": "post_write_maintenance",
            "candidates": [
                {
                    "target_domain": "plot_threads",
                    "target_block_id": "plot.active_threads",
                    "base_block_revision_id": "block-revision-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "field_id": "facts",
                            "content": (
                                "The bridge cutoff becomes the active thread."
                            ),
                        }
                    ],
                    "source_refs": [
                        {
                            "source_type": "accepted_prose",
                            "source_id": "segment-s3c-1",
                            "layer": "runtime_workspace",
                        }
                    ],
                    "change_summary": "Track the bridge cutoff as a plot thread.",
                }
            ],
        },
        "source_of_truth": False,
        "authoritative_mutation": False,
        "metadata": {"adapter": "s3_memory_maintenance_worker_adapter"},
    }
