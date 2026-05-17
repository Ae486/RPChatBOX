# RP Narrative Retrieval Policy Contract

## Scenario: Narrative-aware retrieval policy closes the gap between generic RAG and longform/RP memory use

### 1. Scope / Trigger

- Trigger: retrieval-core already has a working DB-backed query pipeline, but memory/retrieval review found that the public `memory.search_*` path, filter grammar, ranking policy, context composition, and eval gates are still generic RAG surfaces rather than longform/RP narrative retrieval contracts.
- Applies to:
  - `MemorySearchRecallInput.filters` and `MemorySearchArchivalInput.filters`
  - `RetrievalBroker.search_recall` / `RetrievalBroker.search_archival`
  - `RetrievalBroker._build_query`
  - `DefaultQueryPreprocessor`
  - `row_matches_common_filters`
  - deterministic reranking / metadata scoring
  - `RagContextBuilder` or the specialist-side retrieval result composition layer
  - retrieval eval cases under `backend/rp/eval/cases/retrieval`
- This spec summarizes the current confirmed gaps and freezes the target implementation contract. It does not say retrieval-core is missing; the existing keyword/semantic/fusion/rerank/trace/store path must be preserved.
- This spec is not permission to add narrow public tools. Keep the public memory search tool family stable unless a later product spec explicitly widens it.

Confirmed implementation gaps as of this spec:

| Gap | Current implementation fact | Required direction |
|---|---|---|
| Broker rerank strategy | `RetrievalQuery.rerank` exists, but `RetrievalBroker._build_query()` sets `rerank=False` for `memory.search_recall` and `memory.search_archival` | Broker must derive rerank from explicit search policy and/or runtime config |
| Recall filters | Recall supports `materialization_kinds`, `source_families`, and `chapter_indices` | Keep these stable and extend narrative filters without fabricating metadata |
| Archival filters | Archival canonical metadata exists, but search filtering is mostly collection/domain/path based | Add Archival-specific source filters |
| Narrative filters | runtime/ingestion can produce fields such as `scene_ref`, but retrieval search does not treat them as first-class filters/ranking inputs | Retrieval consumes upstream metadata through frozen filter grammar |
| Ranking | deterministic metadata rerank mainly boosts title/path/tags/prefix | Add explainable narrative boosts/penalties before relying on LLM rerank |
| Context budget | RAG context builder dedupes and renders compact excerpts, but does not budget by source family/domain/scene/character/chapter | Add selected/excluded result composition trace |
| Eval | retrieval eval covers ingestion/query/provenance/maintenance and optional RAGAS wiring | Add narrative policy gold cases and budget/ranking assertions |

### Implemented Sparse Baseline: Chinese field-aware BM25 fallback

- `KeywordRetriever` Python fallback must remain Chinese-capable. The fallback tokenizer emits:
  - ASCII/number tokens;
  - CJK single characters;
  - CJK bi-grams;
  - CJK tri-grams.
- The fallback must not flatten every field into one equal-weight body string. Sparse scoring treats structured setup/worldbook fields as first-class ranking signals:
  - `entry_title` / `aliases` are highest-weight entity signals;
  - `title` / `asset_title` are strong document identity signals;
  - `tags`, `section_title`, and `retrieval_role` are medium-weight routing signals;
  - semantic/domain paths are weak structured hints;
  - body text remains baseline evidence.
- This is intentionally a Python/SQLite/local fallback contract. PostgreSQL FTS still uses `to_tsvector('simple', title || text)` for plain ASCII/simple queries, but structured or CJK queries must bypass that PG FTS path and use the same field-aware BM25 sparse path as the fallback until an indexed normalized sparse-text/analyzer slice exists.
- Regression anchor: Chinese relationship queries such as `林鸢和夜紫林的关系` must be able to rank the matching relationship section above a shared-keyword noise section using metadata/title/tag/role signals, without requiring dense retrieval.

### Implemented Query Analysis and Structured Sparse Boosts

- `DefaultQueryPreprocessor` attaches deterministic `filters["query_analysis"]` for non-empty text queries. This is an internal retrieval hint, not a public memory search API field that callers must provide.
- Current retrieval quality evaluation is retrieval-only: benchmark queries are hand-authored inputs used to test the retrieval chain after a query is already provided. Do not count LLM tool-query construction or prompt/query-contract quality as part of these retrieval metrics.
- The retrieval tool boundary should not require model callers to know memory internals. Do not expose memory-layer filters such as entity type, source family, materialization kind, or section metadata as required LLM-authored inputs unless a later product spec explicitly opens that contract. Retrieval internals may still use normalized filters, stored metadata, and deterministic `query_analysis`.
- Test queries should be stratified by input difficulty:
  - `good`: retrieval-friendly manual query with explicit names and target terms;
  - `base`: ordinary natural-language query;
  - `bad`: underspecified, vague, or context-dependent query used to map retrieval-only limits, not as the primary success gate.
- `query_analysis` shape:

```python
{
    "version": "structured_query_analysis_v1",
    "intent": "relationship | appearance | speech | history | weakness | motivation | rule | None",
    "entity_terms": list[str],
    "intent_terms": list[str],
    "intent_expansion_terms": list[str],
    "sparse_terms": list[str],
}
```

- Query analysis must remain model-free and general. It may identify common structured RP/setup query signals such as entity names joined by Chinese connector words and explicit section/intent terms, but it must not special-case fixture names, dataset ids, or benchmark gold labels.
- Sparse retrieval must not blindly append every intent synonym into the BM25 query. That failure mode turns queries such as `丰川祥子 的外貌` into broad "any appearance section" lookup and can outrank the target entity. The implemented fallback keeps BM25 query terms grounded in the original query text, then applies bounded metadata multipliers:
  - entity metadata match: additive multiplier up to `+0.6`;
  - explicit intent term metadata match: additive multiplier up to `+0.2`;
  - structured entity query with no entity metadata match: mild penalty.
- RRF supports per-route weights through transient `_rrf_weight` ranking hints. The helper must strip `_rrf_weight` before returning public hit payloads. For structured queries with entity/intent terms, keyword routes default to higher weight than semantic routes unless `filters.search_policy.hybrid.route_weights` overrides it.

### Target Runtime LLM-Facing Retrieval Tool Contract

This section captures the 2026-05-17 runtime-tool decision. It is a target
contract for writer/worker/orchestrator-facing retrieval, not a statement that
the current writer loop already implements the full shape.

#### 1. Scope / Trigger

- Trigger: runtime writer/worker/orchestrator need a shared LLM-facing retrieval
  tool that is cleaner than legacy `memory.search_recall` /
  `memory.search_archival` and simpler than the current card/expand-heavy
  writer loop.
- `SetupAgent` is out of scope. It keeps its independent
  `setup.memory.search` / `setup.memory.read_refs` tools.
- The LLM-facing retrieval contract should follow standard RAG: caller provides
  the query intent, retrieval returns Top-K clean results, and the LLM reads the
  returned results without reranking.

#### 2. Signatures

Target LLM-facing search input:

```python
class RuntimeRetrievalSearchInput(BaseModel):
    query: str
    mode: Literal["entity", "entity_relation", "semantic", "mixed", "vague"] | None = None
    lexical_anchors: list[str] = Field(default_factory=list)
    semantic_predicates: list[str] = Field(default_factory=list)
```

Target LLM-facing result item:

```python
class RuntimeRetrievalResultItem(BaseModel):
    result_id: str
    title: str | None = None
    summary: str | None = None
    excerpt: str | None = None
    text: str
    section: str | None = None
```

Target LLM-facing search response:

```python
class RuntimeRetrievalSearchOutput(BaseModel):
    query: str
    results: list[RuntimeRetrievalResultItem]
    warnings: list[str] = Field(default_factory=list)
```

#### 3. Contracts

- `query` is required and non-blank.
- `mode`, `lexical_anchors`, and `semantic_predicates` are lightweight query
  expression hints. They are not retrieval algorithm controls.
- The LLM must not provide source routing, sparse/dense weights, K values,
  rerank policy, source family, materialization kind, entity type, or memory
  filters.
- `search_kind` must not be present in the LLM-facing input. Recall vs archival
  routing belongs to backend retrieval policy.
- Writer main-path source policy may search both recall and archival/setup/worldbook material, then return one unified Top-K result list. The model must not see or select those sources.
- `summary` means a stored setup/archival summary written before retrieval. It
  must not be generated or invented by retrieval at query time.
- If no stored summary exists, bounded preview text should be exposed as
  `excerpt`, not `summary`.
- `text` is the matched evidence body/section content, possibly length-bounded.
- Do not expose raw `score`, `rank`, `hit_id`, `chunk_id`, `asset_id`,
  `collection_id`, `domain_path`, raw `metadata`, `provenance_refs`, or raw
  retrieval trace in the normal LLM-facing response. Keep those for backend
  trace/eval/debug surfaces.
- `results` replaces LLM-facing `cards` terminology. Internal runtime workspace
  materials may still keep short ids or card-like storage records for
  traceability, but the tool contract should look like standard RAG.
- Do not add complex cross-source semantic deduplication in the first runtime
  tool slice. Recall represents landed prose, story progress, outlines, and
  runtime summaries; archival represents setting facts, worldbook material,
  character foundations, and rules. Treat them as complementary unless the same
  source/hit/chunk is already deduped by existing retrieval behavior.

#### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `query` is blank | Reject with schema/validation error |
| `mode` is unknown | Reject or normalize to missing-mode fallback; do not silently treat it as a retrieval weight |
| `lexical_anchors` / `semantic_predicates` contain blanks or duplicates | Trim and dedupe |
| caller includes `search_kind` | Reject once the target strict schema is active |
| caller attempts to pass `top_k`, route weights, filters, or rerank settings | Reject once the target strict schema is active |
| no stored summary exists | Return `excerpt` or omit `summary`; do not fabricate `summary` |
| retrieval returns no hits | Return empty `results` plus warning/miss metadata appropriate for backend trace |
| recall and archival both produce useful hits | Return a unified Top-K list; do not ask the LLM to choose source family |
| recall and archival appear semantically similar | Keep both in the first slice unless they are the same source/hit/chunk under existing dedup behavior |

#### 5. Good/Base/Bad Cases

- Good: `{"query": "林鸢和夜紫林的关系怎么样", "mode": "entity_relation", "lexical_anchors": ["林鸢", "夜紫林"], "semantic_predicates": ["关系"]}` returns relationship-focused Top-K results.
- Base: `{"query": "林鸢和夜紫林的关系怎么样"}` still works through deterministic query analysis.
- Bad: `{"query": "林鸢和夜紫林的关系怎么样", "search_kind": "archival", "top_k": 50, "filters": {"source_families": ["..."]}}` exposes backend retrieval concerns to the model and should not be accepted by the LLM-facing runtime tool.
- Base: writer search may internally query both story recall and archival/worldbook facts, then return a unified `results` list without exposing source routing.

#### 6. Tests Required

- Schema tests: accept `query` plus optional lightweight hints; reject legacy
  `search_kind`, filters, K, and route weights under strict mode.
- Serialization tests: LLM-facing response includes only `result_id`, `title`,
  stored `summary` when available, `excerpt` fallback when needed, `text`,
  `section`, and `warnings`.
- Regression tests: existing retrieval ranking remains backend-owned; the LLM
  does not receive fields that imply manual reranking.
- E2E runtime test: writer/worker/orchestrator can call `retrieval.search` and
  receive clean Top-K RAG results while backend trace still preserves full
  retrieval diagnostics.
- Source policy test: writer main path does not require `search_kind` and can
  compose recall plus archival results behind the tool boundary.
- Dedup boundary test: do not add new cross-source semantic folding in this
  slice; only same-source/same-hit behavior already present in retrieval may
  apply.

#### 7. Wrong vs Correct

Wrong:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "search_kind": "archival",
  "top_k": 50,
  "filters": {"source_families": ["recall_detail"]},
  "rerank_top_n": 20
}
```

Correct:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "mode": "entity_relation",
  "lexical_anchors": ["林鸢", "夜紫林"],
  "semantic_predicates": ["关系"]
}
```
- Deterministic dense fallback must not be used as the tuning anchor for final hybrid conclusions. If dense retrieval is local deterministic fallback, structured sparse metrics are the primary quality signal and RRF results are diagnostic only.
- Real hosted embeddings must be evaluated before final RRF weighting. On the raw worldbook good/base/bad retrieval-only benchmark, SiliconFlow `Qwen/Qwen3-Embedding-8B` materially outperformed deterministic dense fallback and current structured sparse on early-ranking metrics; equal sparse+dense RRF improved Recall@10 but did not beat dense-only nDCG/MRR. Treat this as evidence that dense retrieval is required and that final fusion should be query-aware plus reranked, not a fixed sparse-heavy default.
- Hybrid/rerank must use a deeper internal candidate pool than the caller's final `top_k`. The external `top_k` remains the response limit, while retrieval and RRF may use `filters.search_policy.hybrid.candidate_top_k` or a bounded default candidate pool. Candidate-pool expansion is an internal retrieval concern and must be visible in trace details, not exposed as a required LLM-authored filter.
- Cross-Encoder rerank should operate on the fused candidate pool, not only the already-truncated response top-k. Hosted rerank latency/failure is expected to be managed through bounded `candidate_top_k`, trace warnings, and fallback to fused/metadata order.
- PostgreSQL parity rule:
  - plain ASCII/simple keyword queries may continue to use PG FTS;
  - CJK queries or queries with structured `query_analysis.entity_terms` / `intent_terms` must bypass PG `simple` FTS because it does not tokenize Chinese or structured metadata fields correctly;
  - the bypass route is `retrieval.keyword.bm25` with warning `fts_bypassed:structured_sparse_parity`;
  - this is a correctness-first bridge, not the final performance architecture. The final PG implementation should index backend-generated normalized sparse text or use a Chinese-capable analyzer while preserving the same ranking semantics.

### 2. Signatures

Public memory search input shape remains stable:

```python
class MemorySearchRecallInput(BaseModel):
    query: str
    scope: str | None = None
    domains: list[Domain] = Field(default_factory=list)
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class MemorySearchArchivalInput(BaseModel):
    query: str
    knowledge_collections: list[str] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)
```

`RetrievalQuery` remains the internal normalized query object:

```python
class RetrievalQuery(BaseModel):
    query_id: str
    query_kind: Literal["structured", "recall", "archival", "hybrid"]
    story_id: str
    scope: str | None = None
    domains: list[Domain] = Field(default_factory=list)
    text_query: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = 5
    rerank: bool = False
    required_refs: list[ObjectRef] = Field(default_factory=list)
    optional_refs: list[ObjectRef] = Field(default_factory=list)
```

Search policy extension stays inside `filters` to avoid new public tool contracts:

```python
filters = {
    "search_policy": {
        "profile": "default | longform | roleplay | trpg",
        "rerank": "auto | on | off",
        "context": {
            "current_chapter_index": int | None,
            "target_chapter_index": int | None,
        },
        "context_budget": {
            "max_tokens": int | None,
            "per_source_family": dict[str, int],
            "per_domain": dict[str, int],
        },
    },
}
```

Narrative Recall filter keys:

```python
filters = {
    "materialization_kinds": list[str],
    "source_families": list[str],
    "chapter_indices": list[int],
    "scene_refs": list[str],
    "character_refs": list[str],
    "pov_character_refs": list[str],
    "foreshadow_refs": list[str],
    "foreshadow_statuses": list[str],
    "branch_ids": list[str],
    "canon_statuses": list[str],
}
```

Archival filter keys:

```python
filters = {
    "source_types": list[str],
    "source_families": list[str],
    "source_origins": list[str],
    "workspace_ids": list[str],
    "commit_ids": list[str],
    "domain_path_prefix": str,
}
```

Narrative scoring trace details:

```python
trace.details["narrative_scoring"] = {
    "profile": "longform",
    "rules": [
        {
            "hit_id": str,
            "boosts": dict[str, float],
            "penalties": dict[str, float],
            "final_adjustment": float,
        }
    ],
}
```

Context composition trace details:

```python
trace.details["context_budget"] = {
    "max_tokens": int | None,
    "selected": [
        {
            "hit_id": str,
            "source_family": str | None,
            "domain": str | None,
            "estimated_tokens": int,
            "reason": str,
        }
    ],
    "excluded": [
        {
            "hit_id": str,
            "reason": "duplicate_asset | source_family_budget | domain_budget | token_budget | lower_priority",
        }
    ],
}
```

### 3. Contracts

- `RetrievalBroker._build_query()` must not hard-code `rerank=False` after this contract is implemented.
- Rerank resolution order:
  - explicit `filters.search_policy.rerank == "on"` enables rerank;
  - explicit `filters.search_policy.rerank == "off"` disables rerank;
  - `"auto"` or missing value resolves from story retrieval runtime config and profile defaults;
  - profile default enables deterministic/model-backed rerank for `longform`, `roleplay`, and `trpg` when no explicit rerank config is present;
  - reranker failure must degrade to deterministic metadata rerank or preserve fused order with warnings; it must not fail the whole search.
- Query preprocessing must normalize supported list filters deterministically:
  - string lists: trim, drop blanks, dedupe preserving order;
  - int lists: coerce valid integer strings, drop invalid values, dedupe preserving order;
  - unknown keys may pass through, but only documented keys affect retrieval behavior.
- Filter matching must use chunk metadata first and asset metadata/columns as fallback.
- Recall filters:
  - existing `materialization_kinds`, `source_families`, and `chapter_indices` semantics remain unchanged;
  - narrative fields only match if upstream memory/runtime ingestion produced the corresponding metadata;
  - retrieval must never infer `scene_ref`, `character_refs`, `foreshadow_status`, `branch_id`, or `canon_status` from plain text.
- Archival filters:
  - `source_types` matches metadata field `source_type`;
  - `source_families` matches metadata field `source_family`;
  - `source_origins` matches metadata field `source_origin`;
  - `workspace_ids` matches chunk/asset metadata first, then `SourceAssetRecord.workspace_id`;
  - `commit_ids` matches chunk/asset metadata first, then `SourceAssetRecord.commit_id`;
  - `domain_path_prefix` keeps the current prefix semantics.
- Multiple supported filter keys combine with AND semantics.
- Multiple values within the same filter key combine with OR semantics.
- Narrative ranking must be deterministic and traceable before any LLM rerank is introduced:
  - boost current/closed scene matches when `scene_refs` or profile context supplies them;
  - boost POV/current-character matches when character metadata exists;
  - boost active foreshadow for forward-writing context, but do not treat retired/resolved foreshadow as active constraints unless explicitly requested;
  - penalize `canon_status in {"superseded", "rejected", "draft"}` by default unless filters explicitly include them;
  - penalize branch mismatches by default once `branch_ids` are available;
  - apply chapter-distance boosts only from structured `chapter_index` metadata and `filters.search_policy.context.current_chapter_index` / `target_chapter_index`, not from text heuristics.
- Context composition must not let `WritingPacketBuilder` consume raw retrieval hits directly.
- Retrieval-backed Block-compatible views remain additive/read-only. Do not attach retrieval hits to the active-story Block consumer registry as if they were current Core State.
- Retrieval policy owns search/filter/ranking/budget/explanation. Runtime/story owns the actual retrieval intent and upstream metadata production. Memory owns canonical materialization/source metadata.
- Story-runtime specialist retrieval must honor `OrchestratorPlan.needs_retrieval`:
  - when `needs_retrieval=False`, specialist-side retrieval composition must not call `memory.search_archival` or `memory.search_recall`, even if query lists are non-empty;
  - deterministic post-write commands such as `ACCEPT_OUTLINE`, `ACCEPT_PENDING_SEGMENT`, and `COMPLETE_CHAPTER` should not use fallback retrieval unless a later spec explicitly introduces a retrieval-backed maintenance policy;
  - tests must not reach provider embedding / HTTP clients for deterministic accept or metadata-promotion paths.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `filters.search_policy.rerank="on"` | Broker builds `RetrievalQuery(rerank=True)` |
| `filters.search_policy.rerank="off"` | Broker builds `RetrievalQuery(rerank=False)` even if config has a rerank model |
| `filters.search_policy.rerank="auto"` | Broker resolves from runtime config/profile defaults |
| `filters.search_policy.profile="longform"` and rerank is `"auto"` | Broker enables rerank even without an explicit rerank model, allowing metadata fallback ranking |
| Reranker backend unavailable | Search returns fused/metadata-ranked results with warnings and trace details |
| Recall filter includes `scene_refs=["chapter:1:scene:1"]` | Only hits whose metadata resolves to that scene ref match |
| Recall hit lacks `scene_ref` | It remains searchable without `scene_refs`, but does not match when `scene_refs` is present |
| Recall filter includes `foreshadow_statuses=["open"]` | Only metadata-marked open foreshadow hits match |
| Archival filter includes `source_types=["foundation_entry"]` | Only Archival hits with that source type match |
| Archival filter includes `workspace_ids=[workspace_id]` | Match canonical metadata first, then source asset column fallback |
| Branch/canon filters are absent and metadata exists | Default policy excludes or penalizes superseded/rejected/foreign-branch material |
| Branch/canon metadata is absent | Do not fabricate it; preserve existing search behavior and omit canon scoring trace for that hit |
| Context budget excludes a hit | Trace records the exclusion reason |
| Unknown filter key is provided | It may pass through unchanged, but must not silently alter ranking or matching |

### 5. Good / Base / Bad Cases

- Good: longform runtime calls `memory.search_recall` with a profile and `scene_refs`, and retrieval returns closed-scene transcript plus continuity notes before generic semantically similar prose.
- Good: `memory.search_archival` can target `source_types=["longform_blueprint"]` without the caller manually filtering generic hits.
- Good: active foreshadow material is boosted when writing forward, while retired foreshadow is still retrievable only when explicitly requested.
- Good: trace explains why a continuity note was selected over raw accepted prose because source-family budget favored compact continuity constraints.
- Base: ordinary recall/archival search without narrative filters keeps current behavior.
- Base: missing upstream narrative metadata means the filter cannot match; retrieval does not infer it from prose.
- Bad: adding `memory.search_scene`, `memory.search_foreshadow`, or `memory.search_archival_by_source_type` instead of extending the existing `filters` contract.
- Bad: treating retrieval hits as authoritative Core State or attaching them to active-story Block consumers.
- Bad: passing raw retrieval hits directly into `WritingPacketBuilder` and letting the writer decide continuity budget.
- Bad: using LLM rerank as the first fix before deterministic scoring and traceable penalties exist.

### 6. Tests Required

- Broker rerank strategy:
  - `memory.search_recall` with `filters.search_policy.rerank="on"` builds/runs a `RetrievalQuery` with `rerank=True`;
  - `"off"` forces `rerank=False`;
  - reranker exception produces warnings/fallback rather than failed search.
- Query preprocessing:
  - normalizes every documented list filter;
  - preserves unknown keys without applying behavior;
  - rejects no request solely because optional narrative filters are absent.
- Recall narrative filters:
  - scene transcript hits can be filtered by `scene_refs`;
  - character/foreshadow/canon filters exclude hits missing those fields when filters are present;
  - existing source-family/materialization/chapter-index tests remain green.
- Archival filters:
  - foundation entry, longform blueprint, and imported asset can be separated by `source_types`;
  - `source_origins`, `workspace_ids`, and `commit_ids` match canonical metadata and asset fallback;
  - collection and domain filters continue to compose with source filters.
- Narrative scoring:
  - current-scene/current-character hits outrank generic semantic hits when base scores are close;
  - superseded/rejected/foreign-branch hits are penalized or excluded by default when metadata exists;
  - same/near-chapter hits receive only structured chapter-distance boosts from `chapter_index` plus search policy context;
  - `trace.details["narrative_scoring"]` records boosts and penalties.
- Context budget:
  - selected/excluded trace is emitted;
  - duplicate assets and source-family/domain/token budget exclusions are visible;
  - `WritingPacketBuilder` tests prove it consumes composed specialist context, not raw retrieval hits.
- Story-runtime retrieval gating:
  - fallback plans for deterministic accept / complete commands set `needs_retrieval=False`;
  - specialist analysis skips Memory OS calls when `needs_retrieval=False`.
- Eval:
  - add retrieval eval gold cases for scene recall, archival source filtering, active vs retired foreshadow, branch/canon isolation, and context budget composition;
  - optional RAGAS metrics may remain additive but cannot be the only quality gate for narrative retrieval.

Eval-only Recall fixtures may be seeded through retrieval eval request payloads as `recall_seed_assets` so narrative search policies can be validated without depending on story-runtime producer completion. This is not a public memory API and must not be surfaced as a runtime mutation tool.

### 7. Wrong vs Correct

#### Wrong

```python
query = RetrievalQuery(
    query_kind="recall",
    text_query=input_model.query,
    filters=input_model.filters,
    top_k=input_model.top_k,
    rerank=False,
)
```

This ignores story/runtime rerank configuration and makes configured rerank unavailable from the public memory search path.

#### Correct

```python
policy = resolve_search_policy(
    story_id=story_id,
    query_kind="recall",
    filters=input_model.filters,
)
query = RetrievalQuery(
    query_kind="recall",
    text_query=input_model.query,
    filters=policy.normalized_filters,
    top_k=input_model.top_k,
    rerank=policy.rerank_enabled,
)
```

The broker keeps the public tool shape stable, resolves strategy explicitly, and lets reranker failure degrade inside the retrieval pipeline.

#### Wrong

```python
# Wrong: post-filter archival hits in the runtime worker.
hits = await memory.search_archival(query="blueprint magic law")
hits = [hit for hit in hits if hit.metadata.get("source_type") == "longform_blueprint"]
```

This hides source filtering from retrieval trace/eval and makes ranking depend on caller-specific ad hoc code.

#### Correct

```python
hits = await memory.search_archival(
    query="magic law",
    filters={"source_types": ["longform_blueprint"]},
)
```

The filter is visible to query preprocessing, matching, observability, and eval.

#### Wrong

```python
# Wrong: writer packet consumes raw retrieval hits and decides budget implicitly.
packet.retrieval_hits = result.hits
```

#### Correct

```python
# Correct: specialist/context composition turns retrieval candidates into a traced context package first.
context = compose_retrieval_context(
    hits=result.hits,
    policy=policy,
)
packet.continuity_context = context.selected_sections
```

The writer receives deterministic context, while retrieval/specialist trace explains selection and exclusion.
