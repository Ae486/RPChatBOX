# Recall Branch-Aware Lifecycle Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Goal: collect only the lightweight technical decisions that materially change how the full-foundation Recall spec should be written.

## 1. Current Repo Evidence

Current repo assets already worth reusing:

- `backend/rp/services/recall_detail_ingestion_service.py`
- `backend/rp/services/recall_summary_ingestion_service.py`
- `backend/rp/services/recall_scene_transcript_ingestion_service.py`
- `backend/rp/services/recall_continuity_note_ingestion_service.py`
- `backend/rp/services/recall_character_long_history_ingestion_service.py`
- `backend/rp/services/recall_retired_foreshadow_ingestion_service.py`
- `backend/rp/services/retrieval_broker.py`
- `backend/rp/models/memory_materialization.py`
- `.trellis/spec/backend/rp-memory-materialization-intake-contract.md`
- `.trellis/spec/backend/rp-memory-temporal-materialization.md`

What the code already proves:

1. Recall physical storage is already intentionally retrieval-core-based, not a separate truth table.
2. Existing Recall ingestion paths already cover multiple historical families, but they are still mainly story/session/chapter/workspace oriented.
3. Canonical Recall metadata builders already exist and are the right place to freeze memory-owned lifecycle metadata.
4. RetrievalBroker is already the stable read/search boundary; the missing piece is identity/visibility/governance, not a second search stack.

## 2. Reuse Decision

Keep and extend:

- retrieval-core physical storage (`SourceAsset`, parsed document, chunk, embedding, index job);
- existing Recall ingestion service family;
- memory-owned materialization metadata helpers;
- the boot-bar branch visibility and runtime identity contracts.

Do not add:

- a second Recall-specific truth database;
- direct worker/user writes that bypass retrieval-core ingestion/reindex;
- session-only Recall query semantics on runtime-owned paths.

Why:

- the storage/indexing wheel already exists in-project and is tested;
- the real gap is lifecycle governance: branch visibility, turn attribution, supersede/invalidate/recompute rules, and runtime identity on search/materialization.

## 3. Mature Wheel / Framework Decision

No external wheel is worth introducing here.

Reason:

- vector/document storage is already solved locally by retrieval-core;
- Letta-like historical memory behavior helps at the product-contract level, but does not justify importing a second memory persistence model;
- the needed work is application governance around the existing store, not a better embedding/index library.

## 4. Spec Consequences

The Recall full-foundation spec should therefore:

1. keep retrieval-core as the physical store;
2. require Recall material metadata to carry full branch/turn/source/lifecycle facts;
3. require active-identity visibility filtering on runtime Recall reads;
4. define explicit lifecycle transitions:
   - create/materialize
   - supersede
   - invalidate/hide
   - recompute
5. keep Recall historical-only and forbid it from becoming current fact truth.

## 5. Rejected Alternatives

Rejected: introduce a new Recall SQL truth table now.

- This duplicates retrieval-core storage responsibilities.
- It would create a second historical search/read path.
- It does not solve the real blocker, which is branch-aware lifecycle governance.

Rejected: solve branch semantics only in RetrievalBroker query filters.

- Search filtering alone cannot explain lifecycle transitions like supersede/recompute/invalidate.
- The material itself needs lifecycle metadata, not only the query.
