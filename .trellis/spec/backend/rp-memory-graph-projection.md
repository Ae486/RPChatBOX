# RP Memory Graph Projection

## Scenario: GraphRAG starts as a parallel relation-aware projection over RP memory material

### 1. Scope / Trigger

- Trigger: RP retrieval needs relation-aware creative recall, entity relationship inspection, and future GraphRAG query expansion without replacing the existing retrieval-core path.
- Applies to:
  - Archival Knowledge graph projection from setup-source material;
  - future Recall Memory graph projection from story materialization;
  - PostgreSQL-backed graph projection storage;
  - graph extraction jobs and maintenance controls;
  - graph inspection API and minimal relationship-network inspection view;
  - retrieval graph expansion behind existing memory search surfaces.
- First implementation stage starts with Archival Knowledge because setup fills it before Recall Memory exists.
- This spec does not authorize a second graph database dependency in the MVP.
- This spec does not create a public `memory.search_graph` tool.
- This spec does not replace retrieval-core as the physical source of source text, chunks, embeddings, or archival/recall search material.

### 2. Signatures

#### 2.1 Storage records

Conceptual SQLModel records. Names may follow existing repository naming style, but the fields and semantics are the contract.

```python
class MemoryGraphNodeRecord:
    node_id: str
    story_id: str
    workspace_id: str | None
    session_id: str | None
    source_layer: str
    entity_type: str
    canonical_name: str
    aliases_json: list[str]
    description: str | None
    source_status: str
    confidence: float | None
    first_seen_source_ref: str | None
    entity_schema_version: str
    normalization_key: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

class MemoryGraphEdgeRecord:
    edge_id: str
    story_id: str
    workspace_id: str | None
    session_id: str | None
    source_node_id: str
    target_node_id: str
    source_entity_name: str | None
    target_entity_name: str | None
    relation_type: str
    relation_family: str
    relation_schema_version: str
    raw_relation_text: str | None
    source_layer: str
    source_status: str
    confidence: float | None
    direction: str
    valid_from: str | None
    valid_to: str | None
    branch_id: str | None
    canon_status: str
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

class MemoryGraphEvidenceRecord:
    evidence_id: str
    story_id: str
    workspace_id: str | None
    node_id: str | None
    edge_id: str | None
    source_layer: str
    source_family: str | None
    source_type: str | None
    import_event: str | None
    source_ref: str | None
    source_asset_id: str | None
    collection_id: str | None
    parsed_document_id: str | None
    chunk_id: str | None
    section_id: str | None
    domain: str | None
    domain_path: str | None
    commit_id: str | None
    step_id: str | None
    char_start: int | None
    char_end: int | None
    evidence_excerpt: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

class MemoryGraphExtractionJobRecord:
    graph_job_id: str
    story_id: str
    workspace_id: str | None
    session_id: str | None
    commit_id: str | None
    source_layer: str
    source_asset_id: str | None
    chunk_id: str | None
    section_id: str | None
    input_fingerprint: str
    status: str
    attempt_count: int
    model_config_ref: str | None
    provider_id: str | None
    model_id: str | None
    extraction_schema_version: str
    taxonomy_version: str
    token_usage_json: dict
    warning_codes_json: list[str]
    error_code: str | None
    error_message: str | None
    queued_reason: str | None
    retry_after: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
```

#### 2.2 Constants

```python
GRAPH_SOURCE_LAYER_ARCHIVAL = "archival"
GRAPH_SOURCE_LAYER_RECALL = "recall"

GRAPH_SOURCE_STATUS_SOURCE_REFERENCE = "source_reference"
GRAPH_SOURCE_STATUS_CANON_CONFIRMED = "canon_confirmed"
GRAPH_SOURCE_STATUS_CANDIDATE = "candidate"
GRAPH_SOURCE_STATUS_INVALIDATED = "invalidated"

GRAPH_CANON_STATUS_SOURCE_REFERENCE = "source_reference"
GRAPH_CANON_STATUS_CANON_CONFIRMED = "canon_confirmed"
GRAPH_CANON_STATUS_NON_CANON = "non_canon"
GRAPH_CANON_STATUS_SUPERSEDED = "superseded"
GRAPH_CANON_STATUS_BRANCH_ONLY = "branch_only"

GRAPH_EDGE_DIRECTION_DIRECTED = "directed"
GRAPH_EDGE_DIRECTION_UNDIRECTED = "undirected"

GRAPH_JOB_STATUS_QUEUED = "queued"
GRAPH_JOB_STATUS_RUNNING = "running"
GRAPH_JOB_STATUS_COMPLETED = "completed"
GRAPH_JOB_STATUS_FAILED = "failed"
GRAPH_JOB_STATUS_SKIPPED = "skipped"
GRAPH_JOB_STATUS_CANCELLED = "cancelled"

GRAPH_JOB_REASON_ARCHIVAL_INGESTED = "archival_ingested"
GRAPH_JOB_REASON_MANUAL_REBUILD = "manual_rebuild"
GRAPH_JOB_REASON_MANUAL_RETRY = "manual_retry"
GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED = "model_config_changed"
GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED = "schema_version_changed"
```

#### 2.3 Phase 1 entity taxonomy

```python
GRAPH_ENTITY_CHARACTER = "character"
GRAPH_ENTITY_PLACE = "place"
GRAPH_ENTITY_FACTION_OR_ORG = "faction_or_org"
GRAPH_ENTITY_RULE = "rule"
GRAPH_ENTITY_OBJECT_OR_ARTIFACT = "object_or_artifact"
GRAPH_ENTITY_TERM_OR_CONCEPT = "term_or_concept"
```

Reserved for later Recall/story graph expansion:

```python
GRAPH_ENTITY_SCENE = "scene"
GRAPH_ENTITY_EVENT = "event"
GRAPH_ENTITY_FORESHADOW = "foreshadow"
GRAPH_ENTITY_CHAPTER = "chapter"
GRAPH_ENTITY_TIMELINE_MARKER = "timeline_marker"
```

#### 2.4 Phase 1 relation taxonomy

```python
GRAPH_REL_ALIAS_OF = "alias_of"
GRAPH_REL_PART_OF = "part_of"
GRAPH_REL_LOCATED_IN = "located_in"
GRAPH_REL_MEMBER_OF = "member_of"
GRAPH_REL_AFFILIATED_WITH = "affiliated_with"
GRAPH_REL_HAS_ROLE = "has_role"
GRAPH_REL_OWNS_OR_CONTROLS = "owns_or_controls"
GRAPH_REL_GOVERNED_BY_RULE = "governed_by_rule"
GRAPH_REL_REQUIRES = "requires"
GRAPH_REL_FORBIDS = "forbids"
GRAPH_REL_ENABLES = "enables"
GRAPH_REL_RELATED_TO = "related_to"
```

Reserved future relation families:

```python
GRAPH_RELATION_FAMILY_STABLE_SETUP = "stable_setup"
GRAPH_RELATION_FAMILY_SOCIAL = "social_relation"
GRAPH_RELATION_FAMILY_CONFLICT = "conflict_relation"
GRAPH_RELATION_FAMILY_SECRET = "secret_relation"
GRAPH_RELATION_FAMILY_CAUSAL = "causal_relation"
GRAPH_RELATION_FAMILY_FORESHADOW = "foreshadow_relation"
GRAPH_RELATION_FAMILY_TEMPORAL = "temporal_relation"
GRAPH_RELATION_FAMILY_STATE_CHANGE = "state_change_relation"
```

#### 2.5 Service boundaries

```python
class MemoryGraphProjectionService:
    def get_maintenance_snapshot(...): ...
    def list_nodes(...): ...
    def list_edges(...): ...
    def list_evidence(...): ...
    def get_neighborhood(...): ...
    def upsert_seed_graph(...): ...
    def queue_archival_extraction_jobs(...): ...
    def retry_failed_jobs(...): ...
    def rebuild_story_graph(...): ...

class MemoryGraphRepository:
    def upsert_node(...): ...
    def upsert_edge(...): ...
    def upsert_evidence(...): ...
    def upsert_job(...): ...
    def list_nodes(...): ...
    def list_edges(...): ...
    def list_evidence(...): ...
    def list_jobs(...): ...
```

The service name is intentionally storage-neutral. The first implementation is PostgreSQL-backed, but callers must not depend on SQL traversal details.

#### 2.6 Internal inspection / maintenance API

Routes live under existing RP retrieval APIs:

```text
GET  /api/rp/retrieval/stories/{story_id}/graph/maintenance
GET  /api/rp/retrieval/stories/{story_id}/graph/nodes
GET  /api/rp/retrieval/stories/{story_id}/graph/edges
GET  /api/rp/retrieval/stories/{story_id}/graph/evidence
GET  /api/rp/retrieval/stories/{story_id}/graph/neighborhood
POST /api/rp/retrieval/stories/{story_id}/graph/rebuild
POST /api/rp/retrieval/stories/{story_id}/graph/retry
```

These are internal retrieval maintenance / inspection endpoints. They are not agent tools and not public memory-layer mutation APIs.

#### 2.7 Visualization-ready graph response

```json
{
  "story_id": "story-1",
  "graph_backend": "postgres_lightweight",
  "source_layer": "archival",
  "nodes": [
    {
      "id": "node_1",
      "label": "Aileen",
      "type": "character",
      "source_status": "source_reference",
      "confidence": 0.82,
      "metadata": {}
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "node_1",
      "target": "node_2",
      "label": "affiliated_with",
      "raw_relation_text": "protected by the Order",
      "confidence": 0.74,
      "evidence_count": 2,
      "metadata": {}
    }
  ],
  "evidence": [
    {
      "id": "evidence_1",
      "edge_id": "edge_1",
      "source_ref": "setup_commit:commit-1:character-aileen",
      "source_asset_id": "asset-1",
      "chunk_id": "chunk-1",
      "section_id": "section-1",
      "excerpt": "Aileen is protected by the Order."
    }
  ]
}
```

#### 2.8 Query intent fields

Public retrieval requests may carry high-level intent fields. They do not expose graph/backend strategy.

```json
{
  "query": "...",
  "scope": "archival",
  "intent": "relation_lookup",
  "need_evidence": true,
  "need_relationship_view": false,
  "top_k": 8
}
```

Allowed intent values:

```text
fact_lookup
relation_lookup
broad_context
consistency_check
```

#### 2.9 Normal retrieval trace graph summary

Normal retrieval result trace may include graph summary fields:

```json
{
  "graph_enabled": true,
  "graph_backend": "postgres_lightweight",
  "graph_policy_mode": "text_first",
  "graph_candidate_count": 12,
  "graph_expanded_hit_count": 4,
  "graph_warning_codes": [],
  "graph_ms": 7.4
}
```

Normal retrieval result trace must not embed full graph nodes, edges, or evidence. Full graph payload belongs to inspection endpoints and the relationship-network inspection view.

#### 2.10 Graph extraction model config

Phase 1 must expose a separate graph extraction model slot:

```json
{
  "graph_extraction_provider_id": "provider-id",
  "graph_extraction_model_id": "model-id",
  "graph_extraction_structured_output_mode": "json_schema",
  "graph_extraction_temperature": 0.0,
  "graph_extraction_max_output_tokens": 2048,
  "graph_extraction_timeout_ms": 60000,
  "graph_extraction_retry_policy": {
    "max_attempts": 3
  },
  "graph_extraction_fallback_model_ref": null,
  "graph_extraction_enabled": true
}
```

This slot may reuse existing provider/model selector components and provider config storage patterns, but its stored meaning is separate from:

- setup/writer agent generation;
- retrieval embedding;
- retrieval rerank.

### 3. Contracts

#### 3.1 Layer ownership

- Graph projection is a read/query projection over memory material.
- Graph projection does not own source text.
- Graph projection does not mutate Core State.
- Graph projection does not submit proposal/apply records.
- Archival graph rows default to:
  - `source_layer = "archival"`;
  - `source_status = "source_reference"`;
  - `canon_status = "source_reference"`.
- `source_reference` means "this source material says so", not "this is current story truth".
- Recall graph rows may later carry session, branch, temporal, and canon fields; those fields are reserved in G1 but not active in Archival MVP.

#### 3.2 Parallel-first, primary-later

Phase 1 is parallel-first:

```text
existing archival retrieval path
  -> must work without graph rows, graph jobs, graph config, or graph endpoints

graph projection path
  -> may enrich retrieval and inspection when available
  -> degrades to trace warnings / maintenance failures when unavailable
```

The implementation must also be primary-later capable:

```text
text_first        # default: text/vector retrieval primary, graph expands candidates
hybrid_balanced   # later: graph and text both contribute to candidate/rerank weights
graph_first       # later: graph relation lookup primary, text/evidence verifies and fills context
```

The switch belongs in retrieval policy / broker configuration, not in public tools.

#### 3.3 Storage backend

- MVP backend is PostgreSQL lightweight graph projection.
- Do not introduce Neo4j, Kuzu, Apache AGE, or any second graph database as an MVP dependency.
- The repository/service boundary must avoid leaking PostgreSQL-specific traversal semantics into retrieval broker, extraction, or frontend services.
- Future graph database migration is allowed only behind the repository/service boundary.

#### 3.4 Evidence

- Every graph relation used in generation must have evidence.
- Evidence stores pointers and excerpts, not full duplicated source documents.
- Evidence must preserve canonical Archival metadata from setup-source intake:
  - `source_family`;
  - `source_type`;
  - `import_event`;
  - `source_ref`;
  - `source_asset_id`;
  - `collection_id`;
  - `chunk_id` / `section_id`;
  - `domain` / `domain_path`;
  - `commit_id` / `step_id`.
- Graph relations without evidence are debug-only and must not enter generation context.

#### 3.5 Extraction

Graph extraction is asynchronous maintenance:

```text
setup commit
  -> canonical Archival Knowledge intake
  -> retrieval-core asset / section / chunk
  -> graph extraction candidate discovery
  -> graph extraction job queued
  -> section/chunk LLM extraction
  -> candidate entities and relations
  -> entity normalization / alias merge
  -> relation taxonomy validation
  -> evidence pointer persistence
  -> graph node/edge/evidence upsert
  -> inspection / trace / retry state
```

Rules:

- Setup commit must not wait for graph extraction.
- Archival ingestion must not fail because graph extraction fails.
- Prompt output must use strict schema.
- Unsupported entity types are rejected or mapped to `term_or_concept` with warning.
- Unsupported relation types are rejected or mapped to `related_to` with warning.
- `related_to` is allowed as fallback but should be visible in inspection.
- Extraction jobs must fingerprint source text + schema version + taxonomy version + model config identity.
- Unchanged jobs can be skipped.
- Failed jobs must be retryable.

#### 3.6 Query routing

GraphRAG starts as candidate expansion, not final answer source:

```text
query
  -> high-level intent parsing
  -> text/vector retrieval baseline
  -> optional entity linking
  -> optional graph expansion
  -> evidence chunk back-reference
  -> unified rerank
  -> context budget
  -> retrieval trace
```

Intent rules:

- `fact_lookup`: text/vector first; graph may contribute relation hints.
- `relation_lookup`: entity linking + graph expansion + evidence chunks.
- `broad_context`: mixed retrieval with strict context budget.
- `consistency_check`: graph + evidence + Core State read, but no Core State mutation.
- `need_relationship_view=true`: read graph projection / inspection; do not call LLM by default.

#### 3.7 Query-time LLM

- Normal graph query should avoid LLM by default.
- Query-time LLM fallback is allowed only for:
  - ambiguous entity linking;
  - path explanation;
  - consistency analysis;
  - summarizing a complex relationship neighborhood for final generation.
- The deterministic path remains:

```text
entity / alias / embedding match
  -> bounded graph traversal
  -> evidence lookup
  -> unified rerank / trace
```

#### 3.8 Inspection API

- Inspection API is internal/debug/validation-oriented.
- Inspection API is read-only except rebuild/retry maintenance commands.
- Inspection API should support:
  - maintenance snapshot;
  - node list;
  - edge list;
  - evidence list;
  - bounded neighborhood.
- Bounded neighborhood defaults:
  - `max_depth <= 2`;
  - capped node/edge count;
  - filters by entity type, relation type, source layer, source status.
- Node/edge click in frontend should show evidence and metadata, not trigger generation or mutation.

#### 3.9 Frontend Phase 1

Phase 1 frontend scope:

- graph extraction provider/model selector;
- minimal relationship-network inspection view;
- bounded local subgraph, not full graph browser;
- evidence/details panel for selected node/edge;
- read-only validation surface.

The view exists so non-engineers can verify that graph extraction, storage, evidence, and traversal are connected end-to-end.

#### 3.10 Eval boundary

- Eval implementation is outside this task.
- This module must emit enough trace/status/evidence for later eval:
  - graph job status;
  - warnings/errors;
  - graph candidate count;
  - expanded hit count;
  - evidence coverage;
  - relation taxonomy fallback count.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| No graph tables/rows exist | Existing `memory.search_archival` still works through retrieval-core |
| Graph extraction config missing | Queue/rebuild reports `model_config_missing`; archival retrieval remains available |
| Graph extraction provider unavailable | Job moves to `failed` with `provider_unavailable`; retry is allowed |
| Graph extraction times out | Job moves to `failed` with `extraction_timeout`; retry policy controls next attempt |
| LLM returns invalid schema | Job moves to `failed` or warning path with `structured_output_invalid`; no partial unvalidated graph rows are persisted |
| LLM emits unknown entity type | Map to `term_or_concept` only when safe and warn `unsupported_entity_type`; otherwise reject candidate |
| LLM emits unknown relation type | Map to `related_to` and warn `unsupported_relation_type` / `mapped_to_related_to`, or reject candidate |
| Evidence pointer cannot resolve source chunk/section | Do not allow relation into generation context; record `evidence_pointer_invalid` |
| Graph relation has no evidence | Keep debug-only or reject from persisted generation-eligible edge set |
| Graph extraction fails after setup commit | Setup commit remains accepted; archival retrieval remains available |
| Manual rebuild requested | Queue jobs with `queued_reason="manual_rebuild"` and fingerprint current source/config/schema |
| Model config changes | Queue/rebuild can mark stale jobs with `queued_reason="model_config_changed"` |
| Schema/taxonomy version changes | Queue/rebuild can mark stale jobs with `queued_reason="schema_version_changed"` |
| `need_relationship_view=true` | Use inspection/graph projection path; do not expose public `memory.search_graph` |
| Graph unavailable during query | Emit graph warning summary and return normal text/vector retrieval result |
| Normal retrieval trace requested | Include graph summary fields only; no full nodes/edges/evidence payload |
| Inspection neighborhood too large | Enforce depth/count caps and return truncation warning |
| Archival graph relation appears canonical | Treat as bug; default must remain `source_reference` |
| Graph service attempts Core State mutation | Treat as contract violation |
| Frontend graph view attempts edit/mutation | Treat as contract violation; Phase 1 view is read-only |

### 5. Good / Base / Bad Cases

- Good: setup source material is ingested into Archival Knowledge, graph extraction later produces `character` and `faction_or_org` nodes with `source_reference` edges and evidence pointers to retrieval chunks.
- Good: `memory.search_archival` works exactly as before when graph extraction jobs are missing, failed, or disabled.
- Good: a relation lookup query uses graph expansion to find related entities, then returns evidence chunks through the existing retrieval result shape.
- Good: inspection API shows a bounded neighborhood and each edge's evidence.
- Good: graph extraction model can be configured separately from embedding and rerank models.
- Base: Phase 1 seed/test data can populate graph nodes/edges/evidence before real LLM extraction exists.
- Base: relation type maps to `related_to`; inspection shows fallback warnings so taxonomy can be improved later.
- Base: graph expansion contributes zero candidates; retrieval trace says graph participated but did not expand hits.
- Bad: adding `memory.search_graph` as a public agent tool in Phase 1.
- Bad: treating Archival graph facts as canon because setup commit was accepted.
- Bad: blocking setup commit until GraphRAG extraction succeeds.
- Bad: returning graph-only facts to writer context without evidence chunks.
- Bad: stuffing full nodes/edges/evidence into every normal retrieval response.
- Bad: making frontend graph visualization depend on backend storage table names.
- Bad: hard-coding PostgreSQL graph traversal directly in `RetrievalBroker` so a later Kuzu/Neo4j backend cannot be introduced.

### 6. Tests Required

#### Slice G1: Graph projection storage and inspection skeleton

- Unit tests for graph constants/taxonomy validation:
  - accepted entity/relation values pass;
  - unknown values reject or map only through explicit fallback.
- Repository tests:
  - upsert/list node;
  - upsert/list edge;
  - upsert/list evidence;
  - evidence can reference retrieval-core asset/chunk/section identifiers;
  - deterministic seed data can produce visualization-ready JSON.
- API tests:
  - maintenance endpoint returns graph backend, counts, and job summary;
  - node/edge/evidence endpoints filter by story/source/entity/relation;
  - neighborhood endpoint enforces depth/count caps.
- Regression tests:
  - existing archival retrieval still passes without graph rows.

#### Slice G2: Graph extraction model config and job orchestration

- Config tests:
  - graph extraction provider/model fields persist separately from embedding/rerank;
  - default/null config behavior is explicit.
- Job tests:
  - automatic queue after archival ingestion can create jobs;
  - manual rebuild queues jobs with `manual_rebuild`;
  - manual retry only retries retryable failed jobs;
  - fingerprint changes when source text, schema version, taxonomy version, or model config changes.
- Failure tests:
  - missing model config does not break archival retrieval;
  - job failure is visible in maintenance snapshot.

#### Slice G3: LLM graph extraction and merge

- Schema validation tests:
  - valid structured output creates candidate nodes/edges/evidence;
  - invalid structured output fails job safely;
  - unsupported entity/relation cases record warning codes.
- Merge tests:
  - aliases merge to stable node by normalization key;
  - duplicate relation evidence is merged, not duplicated blindly;
  - `raw_relation_text` is preserved.

#### Slice G4: Retrieval graph expansion

- Query tests:
  - `relation_lookup` can use graph expansion and evidence chunks;
  - graph unavailable degrades to text/vector retrieval;
  - graph summary trace fields are present;
  - full graph payload is absent from normal retrieval result.
- Policy tests:
  - `text_first` remains default;
  - public memory search tool names remain unchanged.

#### Slice G5: Frontend config and inspection view

- Model config UI tests:
  - graph extraction provider/model can be selected independently;
  - save failure rolls back local selection or shows error consistently with existing config page behavior.
- Service/model tests:
  - graph maintenance and neighborhood JSON parse into frontend models.
- UI tests:
  - bounded graph view renders nodes/edges;
  - selecting node/edge shows evidence;
  - view is read-only.

### 7. Wrong vs Correct

#### Wrong: public graph tool

```python
if tool_name == "memory.search_graph":
    return await graph_service.search_graph(input_model)
```

This exposes implementation strategy to agents and locks the product into a graph-specific public contract.

#### Correct: high-level intent through existing retrieval boundary

```python
result = await memory_os.search_archival(
    MemorySearchArchivalInput(
        query="How is Aileen related to the Order?",
        filters={
            "intent": "relation_lookup",
            "need_evidence": True,
        },
    )
)
```

`RetrievalBroker` / retrieval policy decides whether to use text search, vector search, graph expansion, rerank, or fallback.

#### Wrong: canonizing Archival extraction

```python
edge.canon_status = "canon_confirmed"
edge.source_status = "canon_confirmed"
```

This treats source/reference material as current story truth.

#### Correct: Archival source reference

```python
edge.canon_status = GRAPH_CANON_STATUS_SOURCE_REFERENCE
edge.source_status = GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
edge.source_layer = GRAPH_SOURCE_LAYER_ARCHIVAL
```

The graph fact means only "the source says this"; Core State remains authoritative truth.

#### Wrong: graph-only writer context

```python
writer_context.append(f"{edge.source_entity_name} {edge.relation_type} {edge.target_entity_name}")
```

This can leak hallucinated or unsupported extraction into generation.

#### Correct: graph relation must return to evidence

```python
if edge.evidence_count > 0:
    retrieval_candidates.extend(
        evidence_to_retrieval_candidates(edge.evidence)
    )
```

Writer context receives evidence-backed retrieval material, not graph-only claims.

#### Wrong: sync extraction during setup commit

```python
commit = accept_setup_commit(...)
graph_extractor.extract_all(commit)  # blocks user path and can fail commit
```

Graph extraction is LLM-dependent and cannot be on the critical setup commit path.

#### Correct: asynchronous graph maintenance

```python
commit = accept_setup_commit(...)
retrieval_ingestion.ingest_setup_sources(commit)
memory_graph.queue_archival_extraction_jobs(
    story_id=commit.story_id,
    commit_id=commit.commit_id,
    queued_reason=GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
)
```

Setup commit and archival retrieval remain stable while graph projection catches up.

### 8. Implementation Slice Plan

Use these slices unless implementation evidence proves a different order is safer.

#### G1: Graph projection storage and inspection skeleton

- Add graph node/edge/evidence/job records.
- Add repository/service abstractions.
- Add internal inspection endpoints under `/api/rp/retrieval/...`.
- Add deterministic seed/test helpers.
- Do not call LLM.
- Do not change normal retrieval ranking.
- Verify visualization-ready data shape.

#### G2: Graph extraction model config and job orchestration

- Add independent graph extraction provider/model config.
- Add queue/retry/rebuild job controls.
- Integrate automatic queue after archival ingestion.
- Record model/config/schema/taxonomy fingerprints.

#### G3: LLM graph extraction and merge

- Add strict schema extraction.
- Add entity normalization / alias merge.
- Add relation taxonomy validation.
- Persist evidence-backed graph nodes/edges.

#### G4: Retrieval graph expansion

- Add retrieval policy mode with `text_first` default.
- Add graph candidate expansion for high-level relation intent.
- Add graph summary trace fields.
- Preserve fallback to traditional retrieval.

#### G5: Frontend model config and relationship inspection view

- Add graph extraction provider/model selector.
- Add bounded relationship-network inspection view.
- Add node/edge evidence detail panel.
- Keep view read-only and validation-oriented.
