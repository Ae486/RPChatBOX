"""S-Y4 oracle: RET-012 / ACC-10 retrieval observability normal/debug split.

ACC-10 (``_extractions/11-retrieval.md:182``): "The normal stream for a
retrieval turn shows only a concise summary; card ids/queries/usage-records/
attempts appear only in detail/debug, and debug renders source titles/snippets/
refs (not only ids)."

The debug view already existed (``_retrieval_summary``). These oracles cover the
newly-added concise ``normal`` render level and the two-level inspect payload,
derived from the *same* turn-trace workspace materials the debug view reads.

Falsifiable, deterministic, L1 (no network / no keys). The static builders are
exactly the production code path: ``read_runtime_inspection`` places
``_retrieval_summary_with_levels`` under ``bundle["retrieval"]``.
"""

from __future__ import annotations

import json

from rp.services.story.runtime_debug_query_service import (
    StoryRuntimeDebugQueryService,
)

# Distinctive tokens that MUST NOT leak into the normal stream.
_CARD_SHORT_ID = "R1"
_USAGE_SHORT_ID = "U1"
_MISS_SHORT_ID = "M1"
_QUERY_TEXT = "TAKI_NIGHT_SHIFT_WORKPLACE_QUERY"
_CARD_TITLE = "Night shift convenience store"
_CARD_SUMMARY = "Taki works a late-night shift near the station."
_CARD_EXCERPT = "He clocks in after dark and closes the register at dawn."


def _card_material() -> dict:
    """A writer-visible retrieval card, shaped like ``_material_item`` output."""
    return {
        "material_id": "retrieval_card_abc",
        "material_kind": "retrieval_card",
        "short_id": _CARD_SHORT_ID,
        "visibility": "writer_visible",
        "lifecycle": "active",
        "payload": {
            "hit_id": "hit-xyz",
            "query_id": "q-1",
            "query_text": _QUERY_TEXT,
            "search_kind": "archival",
            "excerpt": _CARD_EXCERPT,
            "text": _CARD_EXCERPT,
            "summary": _CARD_SUMMARY,
            "title": _CARD_TITLE,
            "rank": 1,
            "score": 0.91,
        },
        "metadata": {"search_kind": "archival", "attempt_index": 0},
    }


def _usage_material(*, used: list[str], gaps: list[dict]) -> dict:
    return {
        "material_id": "retrieval_usage_abc",
        "material_kind": "retrieval_usage_record",
        "short_id": _USAGE_SHORT_ID,
        "visibility": "runtime_private",
        "lifecycle": "used",
        "payload": {
            "used_card_short_ids": list(used),
            "expanded_card_short_ids": [],
            "unused_card_short_ids": [],
            "knowledge_gaps": list(gaps),
        },
        "metadata": {"usage_kind": "writer_explicit"},
    }


def _miss_material() -> dict:
    return {
        "material_id": "retrieval_miss_abc",
        "material_kind": "retrieval_miss",
        "short_id": _MISS_SHORT_ID,
        "visibility": "runtime_private",
        "lifecycle": "active",
        "payload": {
            "query": _QUERY_TEXT,
            "query_text": _QUERY_TEXT,
            "search_kind": "archival",
            "attempt_index": 2,
            "miss_reason": "search_no_hit",
        },
        "metadata": {"miss_kind": "search_no_hit", "attempt_index": 2},
    }


def _turn_trace(materials: list[dict], *, usage_refs: list[dict] | None = None) -> dict:
    return {
        "runtime_workspace_materials": list(materials),
        "retrieval_usage_refs": list(usage_refs or []),
    }


def _build():
    return StoryRuntimeDebugQueryService


# ---------------------------------------------------------------------------
# ACC-10 capstone: two-level snapshot over the same materials.
# ---------------------------------------------------------------------------


def test_acc10_normal_and_debug_render_levels_split_over_same_materials():
    trace = _turn_trace(
        [
            _card_material(),
            _usage_material(used=[_CARD_SHORT_ID], gaps=[{"query": _QUERY_TEXT, "status": "missed"}]),
            _miss_material(),
        ],
        usage_refs=[{"material_id": "retrieval_usage_abc", "short_id": _USAGE_SHORT_ID}],
    )

    composed = _build()._retrieval_summary_with_levels(turn_trace=trace)

    # Two render levels are exposed so a caller can request either.
    assert set(composed["render_levels"].keys()) == {"normal", "debug"}
    normal = composed["render_levels"]["normal"]
    debug = composed["render_levels"]["debug"]
    # ``normal`` is also surfaced as a direct shortcut.
    assert composed["normal"] == normal

    # --- NORMAL level: concise readable status only. ---
    assert normal["render_level"] == "normal"
    assert normal["retrieval_occurred"] is True
    assert normal["reference_material_used"] is True
    assert normal["gaps_remained"] is True
    assert isinstance(normal["message"], str) and normal["message"].strip()
    assert normal["message"] == (
        "Reference material was used; some information gaps remained."
    )

    # The normal payload must carry NONE of {card ids, query text, usage records,
    # attempt counts}. Snapshot the serialized form and assert the forbidden
    # tokens / detail keys are absent.
    normal_blob = json.dumps(normal)
    assert _CARD_SHORT_ID not in normal_blob
    assert _USAGE_SHORT_ID not in normal_blob
    assert _MISS_SHORT_ID not in normal_blob
    assert _QUERY_TEXT not in normal_blob
    assert "attempt" not in normal_blob
    for forbidden_key in ("cards", "usage_records", "misses", "expanded_chunks", "usage_refs"):
        assert forbidden_key not in normal

    # --- DEBUG level: full cards with readable titles/snippets/refs (not only ids). ---
    assert debug["cards"], "debug must surface full retrieval cards"
    debug_card = debug["cards"][0]["payload"]
    assert debug_card["title"] == _CARD_TITLE
    assert debug_card["summary"] == _CARD_SUMMARY
    assert debug_card["excerpt"] == _CARD_EXCERPT
    assert debug["usage_records"], "debug must surface usage records"
    assert debug["misses"], "debug must surface misses"
    # Debug detail must not be polluted by the normal-level keys.
    assert "render_level" not in debug
    assert "render_levels" not in debug

    # Back-compat: existing consumers read the flat debug-detail keys directly
    # off ``bundle["retrieval"]`` (e.g. runtime_migration_service usage_refs).
    assert composed["usage_refs"] == [
        {"material_id": "retrieval_usage_abc", "short_id": _USAGE_SHORT_ID}
    ]
    assert composed["cards"] == debug["cards"]
    assert composed["render_levels"]["debug"] == _build()._retrieval_summary(
        turn_trace=trace
    )


# ---------------------------------------------------------------------------
# Normal-level derivation matrix (booleans never leak detail).
# ---------------------------------------------------------------------------


def test_normal_no_retrieval_activity_reports_nothing_retrieved():
    normal = _build()._retrieval_normal_summary(turn_trace=_turn_trace([]))
    assert normal["retrieval_occurred"] is False
    assert normal["reference_material_used"] is False
    assert normal["gaps_remained"] is False
    assert normal["message"] == "No reference material was retrieved this turn."


def test_normal_none_turn_trace_is_empty_summary():
    normal = _build()._retrieval_normal_summary(turn_trace=None)
    assert normal["retrieval_occurred"] is False
    assert normal["reference_material_used"] is False
    assert normal["gaps_remained"] is False
    assert normal["message"] == "No reference material was retrieved this turn."


def test_normal_used_via_usage_record_short_ids():
    trace = _turn_trace([_usage_material(used=[_CARD_SHORT_ID], gaps=[])])
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    assert normal["reference_material_used"] is True
    assert normal["gaps_remained"] is False
    assert normal["message"] == "Reference material was used."


def test_normal_writer_visible_card_counts_as_reference_used_without_usage_record():
    trace = _turn_trace([_card_material()])
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    assert normal["reference_material_used"] is True
    assert normal["gaps_remained"] is False
    # No card ids/queries leak even on the fallback path.
    assert _CARD_SHORT_ID not in json.dumps(normal)
    assert _QUERY_TEXT not in json.dumps(normal)


def test_normal_runtime_private_card_is_not_reference_used_fallback():
    card = _card_material()
    card["visibility"] = "runtime_private"
    trace = _turn_trace([card])
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    # The fallback signal is WRITER_VISIBLE only; a private card with no usage
    # record does not count as reference material used.
    assert normal["reference_material_used"] is False
    assert normal["retrieval_occurred"] is True
    assert normal["message"] == "Reference material was retrieved but not used."


def test_normal_miss_only_reports_gaps_without_use():
    trace = _turn_trace([_miss_material()])
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    assert normal["reference_material_used"] is False
    assert normal["gaps_remained"] is True
    assert normal["message"] == (
        "No reference material was used; information gaps remained."
    )


def test_normal_knowledge_gaps_in_usage_record_count_as_gaps():
    trace = _turn_trace(
        [_usage_material(used=[_CARD_SHORT_ID], gaps=[{"query": _QUERY_TEXT, "status": "missed"}])]
    )
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    assert normal["gaps_remained"] is True
    assert normal["reference_material_used"] is True
    # Knowledge-gap query text must not surface in the concise message.
    assert _QUERY_TEXT not in json.dumps(normal)


def test_normal_empty_knowledge_gaps_list_is_not_a_gap():
    trace = _turn_trace([_usage_material(used=[_CARD_SHORT_ID], gaps=[])])
    normal = _build()._retrieval_normal_summary(turn_trace=trace)
    assert normal["gaps_remained"] is False
