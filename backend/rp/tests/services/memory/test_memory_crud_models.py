"""Tests for RP memory CRUD models."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import (
    MemoryGetStateInput,
    ProposalReceipt,
    ProposalSubmitInput,
    RetrievalHit,
    RetrievalQuery,
    RetrievalTrace,
    StatePatchOperation,
)


def test_get_state_requires_refs_or_domain():
    with pytest.raises(ValidationError):
        MemoryGetStateInput()


def test_invalid_domain_is_rejected():
    with pytest.raises(ValidationError):
        MemoryGetStateInput(domain="invalid-domain")


def test_operation_union_discriminates_by_kind():
    operation = StatePatchOperation.__metadata__[0].discriminator
    assert operation == "kind"


def test_proposal_submit_requires_matching_domains():
    with pytest.raises(ValidationError):
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.SCENE,
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "character.1",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHARACTER,
                    },
                    "field_patch": {"hp": 1},
                }
            ],
        )


def test_receipt_and_hit_dump_stably():
    receipt = ProposalReceipt(
        proposal_id="proposal_1",
        mode="longform",
        domain=Domain.SCENE,
        operation_kinds=["patch_fields"],
        created_at=datetime(2026, 4, 19, 10, 0, 0),
    )
    hit = RetrievalHit(
        hit_id="hit-1",
        query_id="rq_1",
        layer="recall",
        domain=Domain.SCENE,
        excerpt_text="hello",
        score=0.9,
        rank=1,
    )
    trace = RetrievalTrace(trace_id="trace_1", query_id="rq_1", route="fake_recall")

    assert receipt.model_dump(mode="json")["domain"] == "scene"
    assert hit.model_dump(mode="json")["domain"] == "scene"
    assert trace.model_dump(mode="json")["route"] == "fake_recall"
    assert trace.model_dump(mode="json")["retriever_routes"] == []
    assert trace.model_dump(mode="json")["pipeline_stages"] == []
    assert trace.model_dump(mode="json")["details"] == {}


def test_retrieval_query_uses_phase_a_shared_shape():
    query = RetrievalQuery(
        query_id="rq_1",
        query_kind="recall",
        story_id="story_1",
        domains=[Domain.SCENE],
        text_query="market square",
    )

    dumped = query.model_dump(mode="json")

    assert dumped["query_kind"] == "recall"
    assert dumped["domains"] == ["scene"]
