# Memory Graph Projection Decision Log

## Status

This document records the task-level working agreements for adding GraphRAG / knowledge-graph capability to the RP retrieval layer.

It is a design decision log, not an implementation diff. The current implementation direction is:

- keep existing retrieval-core and memory tool contracts stable;
- add a parallel `Memory Graph Projection` path;
- start with Archival Knowledge because setup fills it first;
- keep the design reusable for later Recall Memory ingestion.

## Design Axioms

- GraphRAG is not a new authoritative memory layer.
- GraphRAG is not a replacement for retrieval-core in the first implementation stage.
- Graph data is a projection over already-owned memory material, not the primary source of truth.
- Public tools express retrieval intent; retrieval internals decide whether to use text search, vector search, graph expansion, rerank, or fallback.
- Every graph fact used by generation must be able to return to source evidence.
- LLM-dependent work should be asynchronous and retryable whenever possible.

## Confirmed Decisions

| ID | Question | Decision | Implementation implication |
|---|---|---|---|
| G01 | Main product goal | Relation-aware creative retrieval, relationship-network reasoning, and multi-hop association. | Optimize for entity/relation/path recall, not just better chunk similarity. |
| G02 | Complement or replacement | Parallel at first, not replacement. | Existing archival / recall retrieval must keep working when graph projection is absent or failed. |
| G03 | First memory layer | Start with `Archival Knowledge`; design for later `Recall Memory`. | First producers read setup-source archival material; schema keeps `source_layer` and materialization fields. |
| G04 | Stable first-stage entity set | Use setup/Archival stable entities first: `character`, `place`, `faction_or_org`, `rule`, `object_or_artifact`, `term_or_concept`. | Do not make `scene`, `event`, or `foreshadow` first-stage required types; reserve them for Recall expansion. |
| G05 | Public tool surface | Do not add `memory.search_graph` in Phase 1. | Keep graph routing behind existing memory / retrieval surfaces. |
| G06 | Public query input | Public retrieval request may include high-level intent, not backend strategy. | Use fields like `intent`, `scope`, `need_evidence`, `need_relationship_view`; avoid `use_graph=true`. |
| G07 | Storage backend | First stage uses PostgreSQL lightweight graph projection. | Do not introduce Neo4j/Kuzu as MVP dependency; hide storage behind repository/service interfaces. |
| G08 | Future graph DB migration | Keep migration path open for Kuzu/Neo4j if graph becomes core. | Avoid business code depending directly on SQL graph traversal details. |
| G09 | Extraction timing | Run graph extraction as asynchronous maintenance after setup commit / archival ingestion. | Setup commit must not wait for LLM graph extraction. |
| G10 | Extraction granularity | Extract per section/chunk, then normalize entities and merge relations. | Reuse retrieval-core section/chunk metadata; keep asset-level graph summary as later extension. |
| G11 | Trust model | Extracted graph relations are candidate facts. | Relations can help retrieval expansion but cannot mutate Core State or become canon automatically. |
| G12 | Archival canon status | Archival graph relations are `source_reference`. | They mean "this source material says so", not "current story truth". |
| G13 | Query role | GraphRAG is candidate expansion / relation-aware context retrieval, not final source by itself. | Final result still goes through evidence chunks, unified rerank, context budget, and trace. |
| G14 | Evidence requirement | Any graph relation used in generation must have evidence pointers. | Relations without evidence are debug-only and must not enter writer context. |
| G15 | Query-time LLM use | Default query path avoids LLM; allow LLM fallback only for ambiguity, path explanation, or consistency analysis. | Normal relation lookup should use deterministic entity match, alias lookup, graph traversal, rerank, and fallback. |
| G16 | Failure policy | Graph failure must not break archival retrieval. | Graph failures go to maintenance status / trace and degrade to traditional retrieval. |
| G17 | Reliability target | User-facing failure probability should be extremely low; graph failures must be containable. | Treat graph extraction/query as optional enhancement until proven stable; preserve text retrieval as backbone. |
| G18 | Inspection surface | Phase 1 needs internal inspection API only; no product relationship graph UI yet. | Provide nodes, edges, evidence, extraction status, and trace for debugging/eval handoff. |
| G19 | Relation labels | Freeze a small relation taxonomy first; retain `raw_relation_text`. | Do not let LLM freely invent edge labels in persisted graph rows. |
| G20 | Eval ownership | Eval is handled by another session. | This task must emit enough trace/status/evidence for later eval, but does not implement eval metrics. |
| G21 | Relation taxonomy scope | Phase 1 relation types only cover stable setup/Archival relations, but the schema must explicitly reserve richer relation families for later. | MVP prompts reject complex narrative relations; models/tables keep extension points so later Recall/story relations do not require schema churn. |
| G22 | Graph extraction model config | Phase 1 must expose an independently configurable Graph Extraction provider/model slot. | Do not only inherit retrieval or agent config; reuse existing provider/model configuration patterns where possible. |
| G23 | Maintenance trigger | Phase 1 graph extraction should support both automatic trigger after archival ingestion and manual rebuild/retry controls. | Automatic keeps graph projection warm; manual controls support schema/model changes, failure recovery, and explicit rebuild. |
| G24 | API placement | Graph inspection / maintenance APIs live under existing `/api/rp/retrieval/...` routes. | Graph remains a retrieval projection, not setup/story ownership or a public memory layer. |
| G25 | Migration to primary path | Phase 1 graph path must not block existing retrieval, but should be switchable to primary later via retrieval policy. | Use policy/config flags and repository/service abstraction rather than hard-coded side paths. |
| G26 | MVP promotion rule | GraphRAG starts as an experimental enhancement and is promoted only if it proves better than traditional RAG for target scenarios. | Traditional retrieval remains default until observed quality/reliability/cost justify graph-first or hybrid-balanced policy. |
| G27 | Model config UI | Phase 1 includes a configurable Graph Extraction provider/model surface. | Reuse existing model configuration patterns, but persist graph extraction choices as a separate maintenance model slot. |
| G28 | Relationship network view | Relationship network visualization is a desired capability, but Phase 1 should start with local inspection subgraphs rather than a full product graph browser. | Backend must emit visualization-ready nodes/edges/evidence; frontend can render bounded neighborhoods later without changing backend schema. |
| G29 | Phase 1 frontend scope | Phase 1 includes graph extraction model configuration plus a minimal relationship-network inspection view. | The view is a debug/validation surface for non-engineer verification, not a polished product graph browser. |
| G30 | Implementation slicing | Implement in multiple Trellis spec slices rather than one large MVP drop. | Finish one coherent slice, run check, then continue; avoid mixing schema, LLM extraction, query policy, and frontend visualization in one risky change. |
| G31 | Early schema discipline | G1 must freeze foundational graph tables, DTOs, status values, taxonomy/version fields, and extension slots. | Later graph extraction, query, and frontend slices must reuse these fields instead of inventing incompatible state models. |
| G32 | Retrieval graph trace | Normal retrieval trace should include graph summary fields only. | Keep full nodes/edges/evidence in inspection API; normal retrieval payload should only show whether graph participated and what it contributed. |

## Phase 1 Data Model Template

These are conceptual records. Implementation may use SQLModel models or migrations following existing repository style.

### Graph Node

```text
node_id
story_id
workspace_id
session_id                 # nullable for Archival; reserved for Recall/story-session graph later
source_layer              # archival first; recall later
entity_type               # frozen taxonomy value
canonical_name
aliases_json
description
source_status             # source_reference for archival
confidence
first_seen_source_ref
entity_schema_version
normalization_key
metadata_json
created_at
updated_at
```

Required Phase 1 entity types:

```text
character
place
faction_or_org
rule
object_or_artifact
term_or_concept
```

Reserved later types:

```text
scene
event
foreshadow
chapter
timeline_marker
```

### Graph Edge

```text
edge_id
story_id
workspace_id
session_id                 # nullable for Archival; reserved for Recall/story-session graph later
source_node_id
target_node_id
source_entity_name         # denormalized debug aid for inspection
target_entity_name         # denormalized debug aid for inspection
relation_type             # frozen taxonomy value
relation_family            # stable_setup in MVP; richer families later
relation_schema_version
raw_relation_text
source_layer              # archival first; recall later
source_status             # source_reference for archival
confidence
direction
valid_from                 # nullable; reserved for temporal Recall / story evolution
valid_to                   # nullable; reserved for temporal Recall / story evolution
branch_id                  # nullable; reserved for branch-aware story memory
canon_status               # source_reference in Archival MVP; richer statuses later
metadata_json
created_at
updated_at
```

Initial relation taxonomy should stay small. Candidate first-stage values:

```text
alias_of
part_of
located_in
member_of
affiliated_with
has_role
owns_or_controls
governed_by_rule
requires
forbids
enables
related_to
```

Implementation rule:

- `related_to` is allowed as a fallback but should be discouraged in prompts and tracked in inspection output.
- `raw_relation_text` preserves the source wording so taxonomy can be improved later.
- Phase 1 relation taxonomy is an MVP restriction, not a long-term ontology.
- Persisted relation rows must allow a future `relation_family` / `relation_schema_version` / metadata extension without rewriting existing rows.
- Inspection output should expose unknown or collapsed relation evidence so future taxonomy expansion can be based on missed cases.

Reserved later relation families:

```text
social_relation        # knows, trusts, hates, protects, mentors
conflict_relation      # conflicts_with, threatens, opposes, competes_with
secret_relation        # hides_from, secretly_related_to, conceals
causal_relation        # causes, enables_event, prevents_event, motivates
foreshadow_relation    # foreshadows, resolves, pays_off
temporal_relation      # before, after, during, replaces
state_change_relation  # changes_state_of, reveals, invalidates
```

These are intentionally not required in the Archival MVP because they are more likely to express plans, hidden intentions, or future story possibilities rather than stable source-reference facts.

### Graph Evidence

```text
evidence_id
story_id
workspace_id
node_id | edge_id
source_layer
source_family
source_type
import_event
source_ref
source_asset_id
collection_id
parsed_document_id
chunk_id
section_id
domain
domain_path
commit_id
step_id
char_start
char_end
evidence_excerpt
metadata_json
```

Evidence rules:

- Store pointers to retrieval-core material; do not duplicate full source text.
- Evidence must preserve Archival metadata from setup-source intake.
- Graph relation without evidence cannot enter generation context.

### Graph Extraction Job

```text
graph_job_id
story_id
workspace_id
session_id                 # nullable for Archival; reserved for Recall/story-session graph later
commit_id
source_layer
source_asset_id
chunk_id | section_id
input_fingerprint
status                   # queued | running | completed | failed | skipped
attempt_count
model_config_ref
provider_id
model_id
extraction_schema_version
taxonomy_version
token_usage_json
warning_codes_json
error_code
error_message
queued_reason
retry_after
created_at
updated_at
completed_at
```

Job rules:

- Graph extraction is asynchronous maintenance.
- Fingerprint source text + extraction schema version + model config so unchanged chunks can be skipped.
- Failed graph jobs must be retryable and must not fail setup commit or archival search.
- Graph extraction jobs must record the configured provider/model and extraction schema version used for the run.
- Graph extraction jobs can be queued automatically after archival ingestion and manually through maintenance actions.
- Status values and warning/error codes should be centralized constants, not ad-hoc strings scattered across services.
- G1 should define future-ready nullable fields for Recall, branch, temporal validity, taxonomy versioning, and provider/model audit even if MVP does not actively use them yet.

## Phase 1 Structured Constants

G1 should define these as shared model constants / enums where the current code style allows it.

```text
source_layer:
  archival
  recall            # reserved

source_status:
  source_reference  # Archival MVP default
  canon_confirmed   # reserved
  candidate         # reserved
  invalidated       # reserved

canon_status:
  source_reference  # Archival MVP default
  canon_confirmed   # reserved
  non_canon         # reserved
  superseded        # reserved
  branch_only       # reserved

edge_direction:
  directed
  undirected

graph_job_status:
  queued
  running
  completed
  failed
  skipped
  cancelled         # reserved

graph_job_queued_reason:
  archival_ingested
  manual_rebuild
  manual_retry
  model_config_changed
  schema_version_changed

graph_warning_code:
  unsupported_entity_type
  unsupported_relation_type
  mapped_to_related_to
  low_confidence
  missing_optional_evidence_span
  duplicate_candidate_merged

graph_error_code:
  provider_unavailable
  model_config_missing
  structured_output_invalid
  extraction_timeout
  source_chunk_missing
  evidence_pointer_invalid
  persistence_failed
```

These constants are part of the contract. Later implementation slices should add to them intentionally instead of creating unrelated string variants.

## Graph Extraction Model Configuration

Phase 1 must provide a dedicated `graph_extraction_model` configuration surface.

Required behavior:

- allow selecting upstream provider and model for graph extraction;
- reuse existing provider/model configuration patterns rather than inventing a parallel settings system;
- do not couple graph extraction to retrieval embedding/rerank config;
- do not silently couple graph extraction to setup/writer agent model config;
- allow future replacement by specialized NER / relation extraction / triplet extraction models;
- persist enough model-config identity in extraction jobs for retry, cache invalidation, and audit.

Configuration fields should cover at least:

```text
provider_id
model_id
base_url / endpoint reference when required by existing provider config
structured_output_mode
temperature
max_output_tokens
timeout
retry_policy
fallback_model_ref
enabled
```

First-stage UI/UX can reuse an existing provider/model selector pattern, but the stored meaning must be separate: this slot is for asynchronous graph extraction maintenance, not chat generation, embedding, or reranking.

The first implementation should include configuration UX, not only backend placeholders. It may reuse the existing RP model configuration page patterns, but must expose graph extraction as its own provider/model selection instead of hiding it behind agent or retrieval defaults.

## Relationship Network Visualization Direction

Mature graph products usually avoid rendering the entire graph by default. They expose a graph scene or local exploration view around search results, selected entities, or bounded neighborhoods.

Project direction:

- Phase 1 backend returns visualization-ready graph data: nodes, edges, labels, relation types, confidence, source status, and evidence pointers.
- Phase 1 frontend should render a bounded inspection view so the user can visually verify that graph extraction, storage, evidence, and query traversal are connected end-to-end.
- The first useful view is a local neighborhood view, not the whole story graph.
- Default limits should keep the view small: `max_depth <= 2`, capped node/edge counts, and filters by `entity_type`, `relation_type`, `source_layer`, and `source_status`.
- Node click should show evidence and metadata; it should not trigger generation or mutate memory.
- Graph visualization must be read-only in Phase 1.

Implementation guidance:

- Prefer emitting a generic JSON graph shape compatible with common web graph renderers:

```json
{
  "nodes": [
    {
      "id": "...",
      "label": "...",
      "type": "character",
      "source_status": "source_reference",
      "confidence": 0.82,
      "metadata": {}
    }
  ],
  "edges": [
    {
      "id": "...",
      "source": "...",
      "target": "...",
      "label": "member_of",
      "raw_relation_text": "...",
      "confidence": 0.74,
      "evidence_count": 2,
      "metadata": {}
    }
  ]
}
```

- Do not make frontend graph rendering choices leak into backend storage.
- Phase 1 frontend rendering is required, but only as a bounded inspection surface rather than a full relationship-network product page.
- Existing Flutter WebView support makes a web graph renderer possible, but introducing a graph renderer should be a separate frontend slice after backend inspection data is stable.

## Extraction Pipeline Template

```text
setup commit
  -> canonical Archival Knowledge intake
  -> retrieval-core asset / section / chunk
  -> graph extraction maintenance candidate discovery
  -> section/chunk graph extraction
  -> candidate entities and relations
  -> entity normalization / alias merge
  -> relation taxonomy validation
  -> evidence pointer persistence
  -> graph node/edge/evidence upsert
  -> inspection / trace / retry state
```

Extraction constraints:

- Prompts must use a strict schema.
- Prompt output must reject unknown entity types unless explicitly mapped to `term_or_concept`.
- Prompt output must reject unknown relation types unless explicitly mapped to `related_to`.
- The extractor must not infer current canon status from archival material.
- The extractor must not write Core State or proposal records.

## Query Routing Template

Public retrieval intent may look like:

```json
{
  "query": "...",
  "scope": "archival | recall | both",
  "intent": "fact_lookup | relation_lookup | broad_context | consistency_check",
  "need_evidence": true,
  "need_relationship_view": false,
  "top_k": 8
}
```

These fields express user/workflow need. They do not expose implementation strategy.

Recommended internal routing:

```text
query
  -> parse high-level intent
  -> text / vector retrieval baseline
  -> optional entity linking
  -> optional graph expansion
  -> evidence chunk back-reference
  -> unified rerank
  -> context budget
  -> retrieval trace
```

Routing rules:

- `fact_lookup`: text/vector first, graph only if relation hints help.
- `relation_lookup`: entity linking + graph expansion + evidence chunks.
- `broad_context`: mixed retrieval with strict context budget.
- `consistency_check`: graph + evidence + Core State read, but GraphRAG must not mutate Core State.
- `need_relationship_view=true`: read graph projection / inspection path; do not call LLM by default.

Normal retrieval trace graph summary:

```text
graph_enabled
graph_backend
graph_policy_mode
graph_candidate_count
graph_expanded_hit_count
graph_warning_codes
graph_ms
```

Do not embed full graph nodes, edges, or evidence in normal retrieval results. Full graph payload belongs to inspection endpoints and the relationship-network inspection view.

## Internal Inspection API Template

Phase 1 inspection is internal/debug only. It is not an agent tool and not a product UI requirement.

Suggested capabilities:

```text
GET /api/rp/retrieval/stories/{story_id}/graph/maintenance
GET /api/rp/retrieval/stories/{story_id}/graph/nodes
GET /api/rp/retrieval/stories/{story_id}/graph/edges
GET /api/rp/retrieval/stories/{story_id}/graph/evidence
GET /api/rp/retrieval/stories/{story_id}/graph/neighborhood
POST /api/rp/retrieval/stories/{story_id}/graph/rebuild
POST /api/rp/retrieval/stories/{story_id}/graph/retry
```

Response must include:

- extraction status and warning/error codes;
- node/edge IDs and labels;
- source layer/status;
- confidence;
- evidence pointers;
- backend identifier such as `postgres_lightweight`;
- trace-friendly counts and timings.

## Non-Goals For First Implementation

- No `memory.search_graph` public agent tool.
- No Neo4j/Kuzu dependency.
- No product relationship graph UI.
- No automatic Core State mutation.
- No automatic canon promotion from Archival graph facts.
- No Recall graph extraction in the first slice, unless a later spec explicitly expands scope.
- No graph-only generation context.
- No eval metric implementation in this task.
- No behavior that blocks or slows the current archival retrieval path when graph extraction is unavailable.

## Implementation Slice Plan

Use these slices unless later implementation evidence proves a different order is cheaper.

### Slice G1: Graph Projection Storage And Inspection Skeleton

Goal:

- establish the graph projection backbone without LLM extraction or query behavior changes.

Scope:

- database records / SQLModel models for graph nodes, edges, evidence, and extraction jobs;
- repository/service abstractions such as `MemoryGraphProjectionService` and a PostgreSQL-backed repository;
- internal inspection endpoints under `/api/rp/retrieval/...`;
- deterministic seed/test helpers that can insert sample graph nodes/edges/evidence;
- maintenance snapshot fields for graph health if low-risk.

Acceptance:

- graph rows can be written and read for one story/workspace;
- evidence can point back to retrieval-core assets/chunks/sections;
- inspection API returns visualization-ready nodes/edges/evidence JSON;
- inspection API can be validated with deterministic seed/test graph data before real LLM extraction exists;
- frontend-facing graph data shape is frozen enough for later relationship-network inspection view work;
- existing archival retrieval still works without graph rows;
- no public `memory.search_graph` tool exists.

### Slice G2: Graph Extraction Model Config And Job Orchestration

Goal:

- let users configure graph extraction provider/model and queue/retry graph extraction jobs.

Scope:

- independent graph extraction model config slot;
- backend config read/write path using existing provider/model patterns;
- automatic queue after archival ingestion plus manual rebuild/retry;
- job fingerprinting with source text, extraction schema version, and model config identity;
- failure status, warning codes, token usage, and retry state.

Acceptance:

- graph extraction jobs can be queued without running extraction;
- model config changes can invalidate/rebuild graph jobs;
- setup commit and archival retrieval are not blocked by graph job failures.

### Slice G3: LLM Graph Extraction And Merge

Goal:

- generate candidate graph nodes/edges from archival chunks/sections.

Scope:

- strict extraction prompt/schema;
- entity normalization and alias merge;
- relation taxonomy validation and fallback to `related_to`;
- evidence pointer persistence;
- extraction warning/error handling.

Acceptance:

- setup archival material can produce candidate nodes/edges/evidence;
- unknown or unsupported relation/entity cases are visible in inspection;
- graph relations remain `source_reference` and cannot mutate Core State.

### Slice G4: Retrieval Graph Expansion

Goal:

- use graph projection as optional candidate expansion behind existing retrieval surfaces.

Scope:

- retrieval policy mode: `text_first` default;
- relation lookup / broad context intent handling;
- graph expansion candidate generation;
- evidence chunk back-reference;
- unified rerank and trace summary.

Acceptance:

- graph unavailable or failed degrades to normal archival retrieval;
- normal retrieval trace includes graph summary but not full graph payload;
- public memory tool surface remains stable.

### Slice G5: Frontend Model Config And Relationship Inspection View

Goal:

- expose graph extraction configuration and a bounded relationship-network inspection view.

Scope:

- graph extraction provider/model selector;
- retrieval maintenance panel integration;
- bounded local graph visualization using inspection API data;
- evidence/detail panel for selected node/edge.

Acceptance:

- user can configure graph extraction model;
- user can visually inspect a bounded graph neighborhood;
- graph view is read-only and debug/validation oriented.

## Parallel-First, Primary-Later Migration Rule

Phase 1 must be parallel-first:

```text
existing archival retrieval path
  -> still works without graph rows, graph jobs, graph model config, or graph endpoints

graph projection path
  -> can enrich retrieval and inspection when available
  -> degrades silently or with trace warnings when unavailable
```

However, the implementation must not paint the project into a sidecar-only corner. It should support a later policy switch:

```text
text_first        # current default: text/vector retrieval primary, graph expands candidates
hybrid_balanced   # later: graph and text both contribute to candidate/rerank weights
graph_first       # later: graph relation lookup primary, text/evidence retrieval verifies and fills context
```

The switch belongs in retrieval policy / broker configuration, not in public tools.

## Remaining Questions Before Implementation

No product/design blockers remain for Slice G1.

Implementation agents should start with the executable backend spec:

- `.trellis/spec/backend/rp-memory-graph-projection.md`

If implementation reveals a concrete schema/API/testability issue, return to this task document and update the spec before continuing to the next slice.
