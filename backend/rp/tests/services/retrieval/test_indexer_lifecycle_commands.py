"""Focused tests for Indexer lifecycle commands."""

from __future__ import annotations

from sqlmodel import select

from models.rp_retrieval_store import EmbeddingRecordRecord, KnowledgeChunkRecord
from rp.retrieval.indexer import Indexer
from rp.tests.services.story.test_archival_evolution_service import (
    _seed_archival_asset,
    _seed_runtime_identities,
)


class _CommitCountingSession:
    def __init__(self, inner):
        self._inner = inner
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1
        return self._inner.commit()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_supersede_asset_chunks_is_non_committing_and_cascades_embeddings(
    retrieval_session,
) -> None:
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-indexer-supersede",
        text="supersede chunk anchor.",
    )

    active_chunks = list(
        retrieval_session.exec(
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.asset_id == "asset-indexer-supersede")
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        ).all()
    )
    active_chunk_ids = [chunk.chunk_id for chunk in active_chunks]
    active_embeddings = list(
        retrieval_session.exec(
            select(EmbeddingRecordRecord).where(
                EmbeddingRecordRecord.chunk_id.in_(active_chunk_ids)
            )
        ).all()
    )

    assert active_chunks
    assert active_embeddings

    spy = _CommitCountingSession(retrieval_session)
    Indexer(spy).supersede_asset_chunks(
        asset_id="asset-indexer-supersede",
        metadata_merge={"lifecycle_state": "superseded"},
    )

    assert spy.commit_count == 0

    retrieval_session.flush()
    all_chunks = list(
        retrieval_session.exec(
            select(KnowledgeChunkRecord).where(
                KnowledgeChunkRecord.asset_id == "asset-indexer-supersede"
            )
        ).all()
    )
    all_chunk_ids = [chunk.chunk_id for chunk in all_chunks]
    all_embeddings = list(
        retrieval_session.exec(
            select(EmbeddingRecordRecord).where(
                EmbeddingRecordRecord.chunk_id.in_(all_chunk_ids)
            )
        ).all()
    )

    assert all_chunks
    for chunk in all_chunks:
        assert chunk.is_active is False
        assert chunk.metadata_json["lifecycle_state"] == "superseded"
    assert all_embeddings
    for embedding in all_embeddings:
        assert embedding.is_active is False
        assert embedding.updated_at is not None


def test_annotate_active_chunks_is_non_committing_and_dedupes_provenance(
    retrieval_session,
) -> None:
    main_identity, _ = _seed_runtime_identities(retrieval_session)
    _seed_archival_asset(
        retrieval_session,
        identity=main_identity,
        asset_id="asset-indexer-annotate",
        text="annotate chunk anchor.",
    )

    ordered_chunks = list(
        retrieval_session.exec(
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.asset_id == "asset-indexer-annotate")
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
            .order_by(KnowledgeChunkRecord.chunk_index.asc())
        ).all()
    )

    assert ordered_chunks

    spy = _CommitCountingSession(retrieval_session)
    chunk_ids = Indexer(spy).annotate_active_chunks(
        asset_id="asset-indexer-annotate",
        metadata_merge={"k": "v"},
        provenance_appends=["p:1", "P:1", "p:2"],
    )

    assert spy.commit_count == 0
    assert chunk_ids == [chunk.chunk_id for chunk in ordered_chunks]

    retrieval_session.flush()
    chunk = retrieval_session.get(KnowledgeChunkRecord, ordered_chunks[0].chunk_id)

    assert chunk is not None
    assert chunk.metadata_json["k"] == "v"
    # casefold dedup must drop the "P:1" duplicate of "p:1" (this is the only
    # casefold-but-not-exact collision under test; without dedup "P:1" survives).
    assert "P:1" not in chunk.provenance_refs_json
    assert chunk.provenance_refs_json.count("p:1") == 1
    assert chunk.provenance_refs_json.count("p:2") == 1
