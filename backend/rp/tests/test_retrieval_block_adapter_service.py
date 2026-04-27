"""Tests for retrieval-backed Block-compatible views."""

from __future__ import annotations

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import RetrievalHit
from rp.services.retrieval_block_adapter_service import RetrievalBlockAdapterService


def test_build_block_views_maps_retrieval_hits_without_mutating_metadata():
    archival_hit = RetrievalHit(
        hit_id="chunk-archive-1",
        query_id="rq-archive-1",
        layer=Layer.ARCHIVAL.value,
        domain=Domain.WORLD_RULE,
        domain_path="foundation.world.rules.archive_policy",
        knowledge_ref=ObjectRef(
            object_id="world_rule.archive_policy",
            layer=Layer.ARCHIVAL,
            domain=Domain.WORLD_RULE,
            domain_path="foundation.world.rules.archive_policy",
            scope="story",
            revision=2,
        ),
        excerpt_text="Archive policy says all relics must be sealed at dusk.",
        score=0.91,
        rank=1,
        metadata={"title": "Archive Policy", "document_title": "Worldbook"},
        provenance_refs=["prov:archive-policy"],
    )
    recall_hit = RetrievalHit(
        hit_id="recall-note-1",
        query_id="rq-recall-1",
        layer=Layer.RECALL.value,
        domain=Domain.CHAPTER,
        domain_path=None,
        knowledge_ref=None,
        excerpt_text="Earlier in chapter one, the seal broke during the storm.",
        score=0.77,
        rank=2,
        metadata={"title": "Storm Callback"},
        provenance_refs=["prov:storm-callback"],
    )
    archival_metadata_before = dict(archival_hit.metadata)
    recall_metadata_before = dict(recall_hit.metadata)

    service = RetrievalBlockAdapterService()

    blocks = service.build_block_views(hits=[archival_hit, recall_hit])

    assert [block.block_id for block in blocks] == [
        "retrieval.archival.rq-archive-1.chunk-archive-1",
        "retrieval.recall.rq-recall-1.recall-note-1",
    ]
    assert blocks[0].label == "world_rule.archive_policy"
    assert blocks[0].layer == Layer.ARCHIVAL
    assert blocks[0].source == "retrieval_store"
    assert blocks[0].scope == "story"
    assert blocks[0].revision == 2
    assert (
        blocks[0].data_json["knowledge_ref"]["object_id"] == "world_rule.archive_policy"
    )
    assert blocks[0].metadata["query_id"] == "rq-archive-1"
    assert blocks[0].metadata["source"] == "retrieval_store"
    assert blocks[1].label == "recall-note-1"
    assert blocks[1].layer == Layer.RECALL
    assert blocks[1].domain_path == ""
    assert blocks[1].scope == "retrieval"
    assert blocks[1].revision == 1
    assert blocks[1].metadata["raw_domain_path"] is None
    assert blocks[1].metadata["raw_scope"] is None
    assert archival_hit.metadata == archival_metadata_before
    assert recall_hit.metadata == recall_metadata_before


def test_build_block_views_rejects_unsupported_retrieval_layer():
    service = RetrievalBlockAdapterService()

    hit = RetrievalHit(
        hit_id="bad-hit",
        query_id="rq-bad",
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        knowledge_ref=None,
        excerpt_text="unexpected layer",
        score=0.1,
        rank=1,
        metadata={},
    )

    with pytest.raises(ValueError, match="Unsupported retrieval Block layer"):
        service.build_block_views(hits=[hit])
