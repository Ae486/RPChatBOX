# Archival Evolution Reindex Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Goal: identify what should be reused and what should be tightened before writing the full-foundation Archival evolution spec.

## 1. Current Repo Evidence

Current code anchors:

- `backend/rp/services/retrieval_ingestion_service.py`
- `backend/rp/services/retrieval_maintenance_service.py`
- `backend/rp/services/retrieval_index_job_service.py`
- `backend/models/rp_retrieval_store.py`
- `.trellis/spec/backend/rp-archival-knowledge-intake-contract.md`
- `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md`

What the repo already has:

1. Story/collection/asset reindex and backfill are already solved in retrieval-core service form.
2. Archival ingestion already has a memory-owned metadata contract for setup/source imports.
3. Retrieval job persistence already exists and is good enough to stay the execution backbone for archival reindex.

What is still missing:

1. versioned Story Evolution edits over archival source material;
2. explicit visibility scope for runtime-authored archival changes;
3. a governed source-version to chunk-version to reindex-job trace chain;
4. source-version provenance flowing into later Core proposals.

## 2. Reuse Decision

Keep and extend:

- retrieval-core source asset / chunk / index job model;
- retrieval maintenance service for reindex execution;
- archival metadata contract as the canonical metadata baseline;
- boot-bar event foundation for traceability.

Do not add:

- a second archival search/index service;
- silent in-place metadata overwrite of active source assets;
- automatic story-global visibility for runtime-created archival edits.

Why:

- the physical ingestion and reindex execution wheel already exists;
- the missing capability is version governance and visibility policy, not ingest/index mechanics.

## 3. Mature Wheel / Framework Decision

No external framework should be added.

Reason:

- there is already a stable in-project retrieval pipeline;
- the product-specific problem is source governance, not document indexing capability;
- a new framework would force an unnecessary storage/maintenance migration without reducing the story-runtime risk.

## 4. Spec Consequences

The Archival full-foundation spec should:

1. keep retrieval-core as the archival physical store;
2. add version/supersession semantics around source assets and chunks;
3. define explicit visibility scopes:
   - `current_branch`
   - `selected_branches`
   - `all_existing_branches`
   - `story_global`
4. default setup seed/activation imports to `story_global`;
5. default active runtime evolution writes to current-branch visibility;
6. link every evolution edit to reindex jobs and memory events.

## 5. Rejected Alternatives

Rejected: mutate existing archival source/chunk rows in place and trust later reindex to clean up.

- This loses source-version provenance.
- It makes old writer evidence impossible to explain later.
- It risks stale chunks remaining searchable without a clean supersession story.

Rejected: treat all archival edits as story-global by default.

- The user explicitly confirmed branch-aware default behavior for active runtime evolution writes.
- Story-global by default would leak branch-local experimentation across timelines.
