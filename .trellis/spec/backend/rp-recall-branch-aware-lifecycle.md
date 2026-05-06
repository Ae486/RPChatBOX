# RP Recall Branch-Aware Lifecycle

## Scenario: Recall becomes the branch-aware historical memory layer for longform, roleplay, and TRPG instead of remaining a longform/session/chapter-only retention path

### 1. Scope / Trigger

- Trigger: the repo already has multiple Recall ingestion services and retrieval-backed search, but full runtime foundation still lacks one lifecycle contract for branch-aware historical material. Runtime cannot treat Recall as a stable memory layer if search/materialization stay session/chapter oriented and rollback cannot hide later history.
- Applies to backend RP memory contract work for:
  - Recall material lifecycle metadata;
  - branch/turn-aware Recall materialization;
  - branch-visible Recall search/query rules;
  - supersede/invalidate/recompute behavior;
  - source-ref linkage from Runtime Workspace and accepted outputs into Recall history;
  - focused retrieval/lifecycle tests.
- This slice must not:
  - promote Recall into current-state truth;
  - replace retrieval-core as the physical store;
  - invent a second historical search service beside `RetrievalBroker`;
  - turn raw Runtime Workspace discussion/draft material into Recall by default.

### 2. Surfaces

Canonical lifecycle metadata carried on Recall source assets / sections / chunks:

```python
class RecallLifecycleMetadata(BaseModel):
    identity: MemoryRuntimeIdentity
    materialization_kind: str
    lifecycle_state: str
    visibility_scope: str
    source_refs: list[MemorySourceRef]
    supersedes_refs: list[str] = Field(default_factory=list)
    invalidated_by_event_ids: list[str] = Field(default_factory=list)
    hidden_after_turn_id: str | None = None
    scene_ref: str | None = None
```

Lifecycle states:

```text
active
superseded
invalidated
hidden_by_rollback
recomputed
```

Runtime Recall lifecycle service:

```python
class RecallLifecycleService:
    def materialize(self, *, metadata: RecallLifecycleMetadata, sections: list[dict[str, Any]]) -> list[str]: ...
    def supersede_material(self, *, material_refs: list[str], replacement_metadata: RecallLifecycleMetadata) -> list[str]: ...
    def invalidate_material(self, *, material_refs: list[str], event_id: str, reason: str) -> list[str]: ...
    def recompute_material(self, *, material_refs: list[str], identity: MemoryRuntimeIdentity, actor: str) -> list[str]: ...
```

Runtime read/search contract:

```python
class RetrievalQuery(BaseModel):
    identity: MemoryRuntimeIdentity | None = None
```

### 3. Contracts

#### Historical layer contract

- Recall is the layer for what already happened:
  - accepted prose;
  - closed-scene transcripts;
  - continuity notes;
  - character long-history summaries;
  - retired/resolved foreshadow history;
  - later all-mode historical materials such as roleplay turns, rules outcomes, and inventory history.
- Recall is not the authority for current facts.
- Current state remains in `Core State.authoritative_state`; hot current views remain in `Core State.derived_projection`.

#### Physical-store contract

- Recall continues to use retrieval-core physical storage:
  - `rp_source_assets`
  - `rp_parsed_documents`
  - `rp_knowledge_chunks`
  - `rp_embedding_records`
  - `rp_index_jobs`
- The full-foundation work strengthens metadata, lifecycle, and visibility semantics around that store; it does not replace it.

#### Identity and visibility contract

- Runtime-owned Recall materialization must carry full `MemoryRuntimeIdentity`.
- Runtime-owned Recall search through `RetrievalBroker` must resolve branch visibility from the active identity.
- Search by `session_id` alone is not enough on runtime-owned paths.
- Rollback and branch switches must hide later Recall material for runtime reads, even though audit history remains persisted.

#### Lifecycle contract

- Recall material must support explicit lifecycle transitions:
  - create/materialize
  - supersede
  - invalidate
  - recompute
  - hide by rollback visibility
- Superseding or recomputing Recall material must preserve auditability. Old material can become non-visible or superseded, but it is not silently deleted as if it never existed.
- Recompute is a governed maintenance path that may create replacement assets/chunks and mark older material superseded or invalidated.

#### Source-ref contract

- Recall material must preserve source refs to the actual settled source:
  - accepted artifact
  - closed-scene transcript source
  - chapter-close authoritative snapshot
  - turn/scene/workspace material selected for historical promotion
- Runtime Workspace can feed Recall promotion only through governed post-write / close / maintenance paths.
- Raw draft or unresolved scratch must not materialize to Recall by default.

#### Multi-mode contract

- The lifecycle model must not stay longform-specific.
- New Recall material kinds may be introduced for roleplay/TRPG, but they must still carry the same branch/turn/lifecycle rules.

#### Compatibility contract

- Existing longform Recall ingestion services remain valid producers.
- Their metadata and search behavior must be upgraded to the lifecycle contract instead of introducing mode-specific special cases.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Accepted settled material is promoted to Recall | Retrieval-core asset/section/chunk metadata carries full identity, materialization kind, lifecycle state, and source refs |
| Runtime Recall search runs under active identity | Only branch-visible historical material is returned |
| Branch rolls back before a later Recall materialization | Later Recall material becomes hidden for runtime reads on that branch |
| Recall material is corrected/recomputed | Replacement material is traceable and earlier material becomes superseded or invalidated rather than disappearing silently |
| Raw draft or discussion rows exist in Runtime Workspace | They stay scratch unless an explicit close/promotion path materializes them |
| Roleplay/TRPG adds a new historical material family | It reuses the same lifecycle/visibility contract rather than adding a second Recall system |

### 5. Good / Base / Bad Cases

- Good: a closed scene produces a Recall transcript asset with source refs to the scene transcript source material and the turn identity that closed it.
- Good: a rollback hides later Recall material for runtime reads while audit history remains queryable.
- Good: a corrected continuity note creates a recomputed/superseded historical chain rather than overwriting the old asset in place.
- Base: existing longform chapter summary/detail services continue to use retrieval-core, but now carry branch/turn/lifecycle metadata.
- Bad: `memory.search_recall(...)` on runtime-owned paths reads latest story data without active branch visibility.
- Bad: treating Recall as a fallback current-state truth store because it is searchable.
- Bad: promoting unresolved Runtime Workspace scratch directly to Recall without a governed close/maintenance path.

### 6. Tests Required

- Lifecycle tests cover:
  - materialization metadata carries identity/lifecycle/source refs;
  - supersede/invalidate/recompute transitions preserve auditability;
  - rollback visibility hides later Recall material for runtime reads.
- Retrieval integration tests cover:
  - Recall search is branch-aware under active identity;
  - legacy session/chapter-only behavior is not used on runtime-owned paths.
- Producer tests cover:
  - existing longform Recall producers emit lifecycle metadata compatible with the shared contract;
  - raw draft/discussion scratch is not materialized by default.
- Focused lint/type checks must include the Recall lifecycle contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
result = await broker.search_recall(
    MemorySearchRecallInput(query="what happened last night")
)
```

This does not guarantee branch/turn-aware visibility for runtime reads.

#### Correct

```python
query = RetrievalQuery(
    query_id="recall_q_1",
    query_kind="recall",
    story_id=identity.story_id,
    identity=identity,
)
```

Runtime-owned Recall search is anchored to the active memory identity, and the material itself carries lifecycle metadata that later rollback/recompute logic can govern.
