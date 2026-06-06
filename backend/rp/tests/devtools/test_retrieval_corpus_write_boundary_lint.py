"""Focused tests for the RetrievalCorpus write-boundary lint (T27 S4a)."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_retrieval_corpus_write_boundary import (
    ALLOWED_READ,
    ALLOWED_SCHEMA,
    AUTHORIZED,
    CORPUS_RECORD_NAMES,
    DEFAULT_BACKEND_ROOT,
    NONPROD_BYPASS_DEBT,
    PRODUCTION_BYPASS_DEBT,
    scan_retrieval_corpus_write_boundary,
)

_GRAPH_RECORD_NAMES = frozenset(
    {
        "MemoryGraphNodeRecord",
        "MemoryGraphEdgeRecord",
        "MemoryGraphEvidenceRecord",
        "MemoryGraphExtractionJobRecord",
    }
)


def _write_python(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _scan(backend_root: Path):
    return scan_retrieval_corpus_write_boundary(backend_root=backend_root)


def test_unexpected_importer_outside_allowlist_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "recall" / "rogue_service.py",
        "from models.rp_retrieval_store import KnowledgeChunkRecord\n"
        "VALUE = KnowledgeChunkRecord\n",
    )

    result = _scan(backend_root)

    assert len(result.unexpected_importers) >= 1
    assert result.unexpected_importers[0].code == "UNEXPECTED_IMPORTER"


def test_construction_outside_authorized_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "recall" / "rogue_service.py",
        "from models.rp_retrieval_store import SourceAssetRecord\n"
        "record = SourceAssetRecord()\n",
    )

    result = _scan(backend_root)

    assert len(result.construction_bypasses) >= 1
    assert result.construction_bypasses[0].code == "CONSTRUCTION_BYPASS"


def test_authorized_sink_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "retrieval" / "document_service.py",
        "from models.rp_retrieval_store import SourceAssetRecord\n"
        "record = SourceAssetRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_read_allowlisted_file_may_import_but_not_construct(tmp_path: Path) -> None:
    # A read-allowlisted file importing for reading is fine, but constructing a
    # record there is still a hard bypass: ALLOWED_READ is not construction-exempt.
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "retrieval" / "semantic_retriever.py",
        "from models.rp_retrieval_store import KnowledgeChunkRecord\n"
        "record = KnowledgeChunkRecord()\n",
    )

    result = _scan(backend_root)

    assert result.unexpected_importers == []
    assert len(result.allowed_read) >= 1
    assert len(result.construction_bypasses) >= 1


def test_archival_reads_and_nonprod_debt_stays_separate(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "archival_evolution_service.py",
        "from models.rp_retrieval_store import KnowledgeCollectionRecord\n"
        "VALUE = KnowledgeCollectionRecord\n",
    )
    _write_python(
        backend_root / "rp" / "eval" / "runner.py",
        "from models.rp_retrieval_store import EmbeddingRecordRecord\n"
        "VALUE = EmbeddingRecordRecord\n",
    )

    result = _scan(backend_root)

    assert {f.path for f in result.allowed_read} == {
        "rp/services/story/archival_evolution_service.py"
    }
    assert {f.path for f in result.nonprod_bypass_debt} == {"rp/eval/runner.py"}
    assert result.production_bypass_debt == []
    assert result.errors == []


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "retrieval" / "test_x.py",
        "from models.rp_retrieval_store import SourceAssetRecord\n"
        "record = SourceAssetRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_unexpected_importer_or_construction_bypass() -> None:
    result = scan_retrieval_corpus_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []


def test_real_tree_allowlists_are_exactly_classified() -> None:
    # Strict equality pins every declared allowlist entry to a real triggering
    # file: a new importer trips unexpected (above), a dead allowlist entry trips
    # these set comparisons. This is the import-closure source of truth for S4.
    result = scan_retrieval_corpus_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {f.path for f in result.allowed_authorized} == set(AUTHORIZED)
    assert {f.path for f in result.allowed_read} == set(ALLOWED_READ)
    assert {f.path for f in result.allowed_schema} == set(ALLOWED_SCHEMA)
    assert {f.path for f in result.production_bypass_debt} == set(PRODUCTION_BYPASS_DEBT)
    assert {f.path for f in result.nonprod_bypass_debt} == set(NONPROD_BYPASS_DEBT)


def test_real_tree_production_bypass_debt_is_resolved_empty() -> None:
    # T27 S4b: archival no longer penetrates the corpus write authority; it
    # delegates chunk/embedding lifecycle writes to the Indexer sink. The single
    # production write-authority penetration is resolved -> zero production debt.
    #
    # The production_bypass_debt bucket alone is a constant (the frozenset is now
    # empty), so it documents the DoD but cannot catch a regression on its own.
    # The teeth live in the archival classification below: archival is a pure
    # READER (allowed_read), and any re-introduced corpus-record construction
    # there would surface in construction_bypasses / unexpected_importers and trip
    # this test -- which is exactly the reclaimed boundary S4b must keep closed.
    result = scan_retrieval_corpus_write_boundary(DEFAULT_BACKEND_ROOT)
    archival = "rp/services/story/archival_evolution_service.py"

    assert result.production_bypass_debt == []
    assert set(PRODUCTION_BYPASS_DEBT) == set()
    assert archival in {finding.path for finding in result.allowed_read}
    assert archival not in {finding.path for finding in result.construction_bypasses}
    assert archival not in {finding.path for finding in result.unexpected_importers}


def test_graph_records_are_out_of_corpus_scope() -> None:
    # The four MemoryGraph* records are a separate memory-owned aggregate; they are
    # intentionally excluded from this corpus lint's record set.
    assert _GRAPH_RECORD_NAMES.isdisjoint(CORPUS_RECORD_NAMES)


def test_graph_projection_repository_does_not_appear_in_corpus_findings() -> None:
    # graph_projection_repository.py writes only the graph-4 records (not corpus),
    # so it must not surface anywhere in the corpus boundary scan. This anchors the
    # corpus/graph aggregate isolation.
    result = scan_retrieval_corpus_write_boundary(DEFAULT_BACKEND_ROOT)

    all_paths = {
        finding.path
        for bucket in (
            result.unexpected_importers,
            result.construction_bypasses,
            result.allowed_authorized,
            result.allowed_read,
            result.allowed_schema,
            result.production_bypass_debt,
            result.nonprod_bypass_debt,
        )
        for finding in bucket
    }
    assert "rp/services/memory/graph_projection_repository.py" not in all_paths
