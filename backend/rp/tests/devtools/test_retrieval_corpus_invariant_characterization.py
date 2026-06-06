"""Invariant characterization baseline for the RetrievalCorpus (T27 S4a).

ADR-0015 S4 mandates compensating the invariant BEFORE abstracting any interface.
There is no single corpus command entry today: four retrieval sinks construct the
records and there is no corpus-wide optimistic-concurrency (OCC) guard. The only
version guard in the entire corpus write surface lives on the story archival
request. These tests pin that current reality so a future consolidation slice is
forced to consciously update the baseline when it introduces a corpus command
boundary or OCC -- making that irreversible change visible in the diff.

These are characterization assertions (record current behavior), not curve-fit:
each one encodes an architectural fact the ADR explicitly wants locked.
"""

from __future__ import annotations

import inspect

from rp.models.story.archival_evolution import ArchivalEvolutionRequest
from rp.services.retrieval.collection_service import RetrievalCollectionService
from rp.services.retrieval.document_service import RetrievalDocumentService
from rp.services.retrieval.index_job_service import RetrievalIndexJobService
from rp.services.retrieval.ingestion_service import RetrievalIngestionService

# OCC vocabulary grounded in this codebase (core_state uses base_ref; archival
# uses expected_source_version). A consolidation slice adding corpus-wide OCC
# would introduce a parameter matching one of these hints.
_OCC_PARAM_HINTS = ("version", "expected", "base_ref")


def _occ_params(func) -> list[str]:
    return [
        name
        for name in inspect.signature(func).parameters
        if any(hint in name.lower() for hint in _OCC_PARAM_HINTS)
    ]


def test_only_corpus_occ_is_archival_request_expected_version() -> None:
    # The single optimistic-concurrency guard across the whole corpus write surface
    # is carried on the story archival request (checked in evolve_source).
    assert "expected_source_version" in ArchivalEvolutionRequest.model_fields


def test_generic_corpus_write_entries_have_no_version_guard() -> None:
    # The generic retrieval write entries take no version/OCC parameter: corpus-wide
    # optimistic concurrency is ABSENT today. This is the baseline a consolidation
    # slice must change deliberately.
    assert _occ_params(RetrievalCollectionService.ensure_story_collection) == []
    assert _occ_params(RetrievalDocumentService.upsert_source_asset) == []
    assert _occ_params(RetrievalDocumentService.save_parsed_document) == []
    assert _occ_params(RetrievalIndexJobService.submit_ingest_job) == []
    assert _occ_params(RetrievalIndexJobService.submit_reindex_job) == []


def test_per_asset_consistency_unit_is_begin_nested() -> None:
    # The de-facto consistency boundary for corpus ingestion is a per-asset nested
    # transaction, not a corpus-wide unit (ADR contract item 10, commit/flush
    # ownership). Pinning it documents the current transaction shape.
    source = inspect.getsource(RetrievalIngestionService.process_job)
    assert "begin_nested" in source
