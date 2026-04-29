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
