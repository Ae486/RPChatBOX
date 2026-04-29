# Retrieval Dev Task

## Goal

Bring the session-scoped retrieval development task back under Trellis control by documenting the real code baseline first. This task is not a rewrite of retrieval-core. The working goal is to continue from the current implementation and make future retrieval slices explicit, checkable, and aligned with the actual backend/frontend surfaces already present in the repo.

The current code shows retrieval as a mature RP subsystem with store, ingestion, query pipeline, rerank, observability, maintenance, setup ingestion, story runtime recall, and frontend maintenance/model-configuration entry points. Future work should refine and verify this system rather than re-create the Phase B skeleton.

## Current Code Baseline

### Retrieval storage

Retrieval storage is backed by SQLModel records in `backend/models/rp_retrieval_store.py`:

- `KnowledgeCollectionRecord`
- `SourceAssetRecord`
- `ParsedDocumentRecord`
- `KnowledgeChunkRecord`
- `EmbeddingRecordRecord`
- `IndexJobRecord`

The storage helper also includes compatibility schema patching and PostgreSQL pgvector/HNSW support. The physical reality is still retrieval-core tables, not a separate universal durable Block container store for Recall or Archival.

### Ingestion pipeline

The main ingestion path is `RetrievalIngestionService`:

```text
SourceAsset
  -> Parser
  -> Chunker
  -> Embedder
  -> Indexer
  -> active chunks and embeddings
```

The job state machine currently includes:

- `queued`
- `parsing`
- `chunking`
- `embedding`
- `indexing`
- `completed`
- `failed`
- `cancelled` in the public model shape

Implemented maintenance behavior includes reindex, stub-embedding backfill candidate discovery, retry of failed ingest/reindex jobs, nested transaction protection for per-asset processing, stable warning taxonomy, and asset failure marking.

### Parser and chunking

The parser is structure-first:

1. `SourceAsset.metadata.seed_sections`
2. `parsed_payload.sections`
3. raw file fallback from `storage_path`
4. `raw_excerpt / title / source_ref` fallback

The chunker is no longer simple fixed-window chunking. It preserves section-aligned primary chunks, adds deterministic secondary small-window chunks for long primary chunks, and enriches metadata with:

- baseline identity fields: `title`, `domain`, `domain_path`, `section_id`, `section_part`, `asset_id`, `collection_id`, `source_ref`, `commit_id`
- multi-view fields: `chunk_view`, `chunk_size`, `chunk_pass`, `parent_section_part`, `view_part`, `chunk_family_id`, `char_start`, `char_end`
- context fields: `document_title`, `document_summary`, `context_header`, `contextual_text`, `contextual_text_version`
- page/image fields: `page_no`, `page_label`, `page_ref`, `image_caption`

### Query pipeline

`RetrievalService` already exposes an explicit slot-based query pipeline:

```text
QueryPreprocessor
  -> KeywordRetriever + SemanticRetriever
  -> RrfFusionStrategy
  -> Reranker
  -> ResultBuilder
```

Current retrieval behavior:

- sparse route: PostgreSQL FTS when available, lexical fallback otherwise
- dense route: pgvector when available, Python cosine fallback otherwise
- fusion: reciprocal-rank fusion
- result views: chunk result, document result, and internal RAG context
- trace: route, retriever routes, pipeline stages, reranker name, candidate counts, returned counts, timings, warnings, details

### Rerank

Rerank is implemented as an enhancement layer, not as a dependency for base retrieval:

- `NoOpReranker`
- `SimpleMetadataReranker`
- `CrossEncoderReranker`
- `HostedRerankerBackend`
- `LocalCrossEncoderBackend`
- `LLMReranker`

The current failure policy is correct in principle: reranker failure or unavailable backend must degrade to metadata rerank or preserve base retrieval behavior rather than failing the whole search path.

### Memory facade and Block-compatible views

`RetrievalBroker` is the memory-facing facade:

- `memory.search_recall` maps to retrieval-core recall search.
- `memory.search_archival` maps to retrieval-core archival search.
- `memory.get_state` and `memory.get_summary` use Core State / projection read services with Block read fallback; they are not implemented by converting retrieval into an all-purpose authoritative memory store.
- Langfuse retrieval observations and retrieval scores are emitted from the broker/search path.

Retrieval hits can be projected into additive read-only Block-compatible views through `RetrievalBlockAdapterService`. These views are for runtime payloads and observability; they do not replace retrieval storage, public search result shape, proposal state, or Block consumer sync.

### Observability and maintenance

`RetrievalObservabilityService` builds a structured query view with:

- query metadata
- route and pipeline stages
- reranker identity
- filters, timings, warnings, warning buckets, details
- top hit previews
- additive `block_view` for top hits
- optional maintenance snapshot

`RetrievalMaintenanceService` and `backend/api/rp_retrieval.py` expose:

- story maintenance snapshot
- collection maintenance snapshot
- story/collection reindex
- story/collection backfill
- story/collection failed-job retry
- single job retry

Flutter already has a backend service/model pair for these endpoints and `PrestorySetupPage` contains a retrieval maintenance panel with story/collection reindex, backfill, retry, and single-job retry actions.

### Setup and Archival Knowledge ingestion

Setup commit ingestion enters retrieval through `MinimalRetrievalIngestionService`. The current active work in the dirty tree is moving setup source material into canonical Archival Knowledge metadata before delegating to retrieval-core.

Expected source families and source types:

- source family: `setup_source`
- source types: `foundation_entry`, `longform_blueprint`, `imported_asset`
- import event: `setup.commit_ingest`

This path must keep setup/source metadata as Archival Knowledge, not Recall history, Runtime Workspace scratch, or direct Core State mutation.

### Story runtime and Recall materialization

Recall materialization already has multiple producer services:

- chapter summary
- accepted story segment detail
- continuity note
- scene transcript
- character long-history summary
- retired foreshadow summary

These use the shared `build_recall_materialization_metadata` and `build_recall_seed_section` contract. Runtime producers provide source payloads and family-specific facts, while the memory layer owns canonical Recall fields such as `layer`, `source_family`, `materialized_to_recall`, `materialization_kind`, `materialization_event`, `session_id`, `chapter_index`, and `domain_path`.

### Model configuration

Retrieval model choice is story scoped:

- Setup default config comes from the `story_config` draft block.
- Active story override comes from `runtime_story_config`.
- `RetrievalRuntimeConfigService` overlays story runtime config on top of setup defaults.
- Flutter setup/story pages share a model config page for agent and retrieval model selection.

## Requirements

- Preserve retrieval-core as the physical source of truth for Recall and Archival search material unless a later task proves a different physical model is required.
- Keep public memory tool contracts stable:
  - `memory.search_recall`
  - `memory.search_archival`
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.list_versions`
  - `memory.read_provenance`
- Treat retrieval Block-compatible views as additive/read-only projections, not persisted Blocks or replacement public outputs.
- Keep setup source imports in Archival Knowledge with canonical `setup_source` metadata.
- Keep runtime/story settled material in Recall Memory only through explicit materialization services.
- Keep query pipeline slot boundaries explicit and avoid folding rerank, result building, and observability back into retriever implementations.
- Keep rerank optional and degradation-safe.
- Keep setup default retrieval config and active story runtime override semantics distinct.
- Use current code behavior as the baseline when resolving conflicts with older implementation specs.

## Current Active Work Surface

The dirty tree shows retrieval-adjacent work already in progress:

- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/rp-archival-knowledge-intake-contract.md`
- `backend/rp/models/memory_materialization.py`
- `backend/rp/services/minimal_retrieval_ingestion_service.py`
- `backend/rp/services/setup_workspace_service.py`
- `backend/rp/tests/test_memory_materialization_contract.py`
- `backend/rp/tests/test_minimal_retrieval_ingestion_service.py`

This likely represents the current first implementation slice: canonical Archival Knowledge intake metadata for setup ingestion. Do not overwrite or revert these changes unless explicitly asked.

## Proposed Next Slices

### Slice 1: Task documentation and context setup

Status: current slice.

Scope:

- Create this task PRD from actual code state.
- Replace seed rows in `implement.jsonl` and `check.jsonl` with relevant spec/research entries.
- Do not modify retrieval business code.

Acceptance:

- `prd.md` exists and describes the current implementation accurately enough for a follow-up implement/check agent.
- `implement.jsonl` and `check.jsonl` contain real context entries, not only the `_example` seed row.
- `python .\.trellis\scripts\task.py current` still resolves this session to `04-29-retrieval-dev-task`.

### Slice 2: Archival Knowledge intake verification

Scope:

- Review and finish the current Archival metadata changes if they are not already complete.
- Ensure setup foundation entries, longform blueprint material, and imported assets all write canonical Archival metadata to parent assets, seed sections, chunks, and search hit metadata.
- Ensure conflicting upstream metadata cannot redefine layer/source ownership.

Acceptance:

- Focused metadata helper tests pass.
- Focused setup ingestion tests pass.
- `memory.search_archival` preserves canonical Archival source metadata in returned hits.
- No public memory tool contract is widened.

### Slice 3: Narrative retrieval policy implementation

Scope:

- Implement the newly captured `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md` in coherent sub-slices.
- Start with broker rerank strategy and Archival source filters before adding broader narrative scoring/budget behavior.
- Keep public memory tools stable and use structured `filters` policy rather than adding narrow `memory.search_*` variants.

Acceptance:

- `memory.search_recall` / `memory.search_archival` can resolve rerank through explicit search policy and/or runtime config without hard-coded `rerank=False`.
- Archival search supports source metadata filters such as `source_types`, `source_origins`, `workspace_ids`, and `commit_ids`.
- New narrative filters/scoring/budget behavior is traceable and covered by retrieval eval gold cases before being consumed by story runtime.

### Slice 4: Retrieval maintenance UI/API reconciliation

Scope:

- Compare the current retrieval-layer spec statement that "maintenance UI is pending" against actual Flutter implementation.
- Decide whether the remaining work is documentation update, UX polish, missing endpoint coverage, or no-op.
- If implementation is needed, keep it additive and scoped to existing API/model/service surfaces.

Acceptance:

- The task records whether maintenance UI/API is already sufficient or what concrete gap remains.
- Any future UI/API changes preserve the existing backend endpoint shapes.

### Slice 5: Final retrieval consistency check

Scope:

- Run relevant backend tests for retrieval ingestion, broker, runtime config, observability, maintenance, materialization, and API.
- Run relevant Flutter analyzer targets if frontend surfaces are changed.
- Update `.trellis/spec/` only if this task discovers durable conventions not already captured.

Acceptance:

- Focused tests pass or failures are documented with root cause and next step.
- No retrieval contract drift is left undocumented.

## Acceptance Criteria

- [ ] Task PRD reflects actual code implementation rather than stale Phase B/C assumptions.
- [ ] Task context files reference retrieval-specific specs/research for future implement/check agents.
- [ ] Current dirty retrieval-adjacent work is documented as active work surface, not treated as disposable.
- [ ] The next implementable slice is explicit enough to dispatch a Trellis implement agent without re-discovering the whole retrieval stack.
- [ ] No business code is changed in the documentation-only slice.

## Definition of Done

- `prd.md` exists in `.trellis/tasks/04-29-retrieval-dev-task/`.
- `implement.jsonl` has real spec/research entries.
- `check.jsonl` has real spec/research entries.
- The session still resolves to `.trellis/tasks/04-29-retrieval-dev-task`.
- Any skipped verification is stated explicitly at handoff.

## Out of Scope

- Rewriting retrieval-core.
- Replacing PostgreSQL/pgvector/FTS with an external retrieval runtime.
- Introducing new public memory tools.
- Promoting Runtime Workspace discussion/drafts into Recall without explicit materialization.
- Converting Recall/Archival retrieval hits into durable Block rows.
- Changing setup/story model configuration semantics in this documentation slice.
- Running broad test suites for unrelated dirty work.

## Technical Notes

Primary implementation anchors:

- `backend/models/rp_retrieval_store.py`
- `backend/rp/models/memory_crud.py`
- `backend/rp/models/retrieval_records.py`
- `backend/rp/models/memory_materialization.py`
- `backend/rp/retrieval/`
- `backend/rp/services/retrieval_service.py`
- `backend/rp/services/retrieval_broker.py`
- `backend/rp/services/retrieval_ingestion_service.py`
- `backend/rp/services/minimal_retrieval_ingestion_service.py`
- `backend/rp/services/retrieval_maintenance_service.py`
- `backend/api/rp_retrieval.py`
- `lib/services/backend_rp_retrieval_service.dart`
- `lib/models/rp_retrieval.dart`
- `lib/pages/prestory_setup_page.dart`
- `lib/pages/longform_story_page.dart`
- `lib/pages/rp_model_config_page.dart`

Primary spec/context anchors:

- `docs/research/rp-redesign/agent/implementation-spec/retrieval-layer-development-spec-2026-04-21.md`
- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/rp-archival-knowledge-intake-contract.md`
- `.trellis/spec/backend/rp-memory-materialization-intake-contract.md`
- `.trellis/spec/backend/rp-recall-source-family-retrieval-contract.md`
- `.trellis/spec/backend/rp-recall-source-family-search-filters.md`
- `.trellis/spec/backend/rp-retrieval-block-compatible-views.md`
- `.trellis/spec/backend/rp-retrieval-block-observability.md`
- `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md`
- `.trellis/spec/frontend/index.md`
