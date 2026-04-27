# RP Memory Temporal Materialization

## Scenario: RP owns memory-layer semantics while borrowing Letta-style layering mechanics

### 1. Scope / Trigger

- Trigger: Core State Block rollout is usable enough that the next work must define what each memory layer owns over time, not keep adding container wiring blindly.
- Applies to RP backend Memory OS planning and later implementation across:
  - Core State current truth
  - Core State current projection
  - Recall Memory historical material
  - Archival Knowledge source/reference material
  - Runtime Workspace current-turn scratch
  - retrieval/tool/runtime reads over those layers
- This spec freezes the semantic ownership and materialization timing rules. It is not itself a storage migration and does not authorize a universal durable `rp_blocks` table.
- Letta is reference material for layered memory mechanics, Block objects, prompt compilation, attachment/fan-out, and background maintenance. Letta is not the semantic blueprint for RP narrative memory.

### 2. Signatures / Surfaces

Layer ownership vocabulary:

```text
Core State.authoritative_state
  -> current structured story truth.

Core State.derived_projection
  -> current hot summary / writer-facing / orchestrator-facing projection.

Recall Memory
  -> closed or historical story material that should remain retrievable after it is no longer current.

Archival Knowledge
  -> imported or authored source/reference material that is not produced by the current runtime turn.

Runtime Workspace
  -> current-turn scratch, raw hits, drafts, discussion traces, tool outputs, and worker intermediate state.
```

Primary read surfaces:

```python
class MemoryOsService:
    async def get_state(...)
    async def get_summary(...)
    async def search_recall(...)
    async def search_archival(...)
    async def list_versions(...)
    async def read_provenance(...)

class RetrievalBroker:
    async def get_state(...)
    async def get_summary(...)
    async def search_recall(...)
    async def search_archival(...)
    async def list_versions(...)
    async def read_provenance(...)
```

Primary materialization families:

```text
per-turn projection refresh
heavy regression / chapter close
future scene close
setup/story-evolution import
future background maintenance
```

Recall source families:

```text
chapter_summary
accepted_story_segment
future scene_transcript
future continuity_note
future character_long_history_summary
future retired_foreshadow_summary
```

### 3. Contracts

#### Layer ownership contract

- `Core State.authoritative_state` owns current structured truth.
  - It is exact, governed, revisioned, and proposal/apply protected.
  - It should answer "what is currently true in the active story state?"
  - Mutation must not bypass proposal/apply.
- `Core State.derived_projection` owns current hot projections.
  - It is derived from authoritative truth plus accepted maintenance policies.
  - It should answer "what compact current view should runtime, writer-facing packet assembly, UI, debug, or export consume?"
  - Refreshing projection is maintenance, not authoritative truth mutation.
- `Recall Memory` owns historical story material.
  - It is retrieval-oriented and may include summaries, accepted prose, future closed-scene transcripts, continuity notes, and long-history summaries.
  - It should answer "what previously happened or was settled, but is no longer the current compact state?"
  - Recall physical storage remains retrieval-core unless a later executable spec proves current retrieval-core cannot support a required behavior.
- `Archival Knowledge` owns source/reference material.
  - It is retrieval-oriented and covers world book, character files, rules, imported documents, and other authored/external knowledge.
  - It should answer "what source material may inform the story?"
  - It must not be confused with runtime-generated story history.
- `Runtime Workspace` owns current-turn scratch.
  - It may expose read-only Block-compatible views for visibility/debug/runtime payloads.
  - It is not durable story truth and is not historical recall by default.
  - Drafts, tool outputs, raw retrieval hits, discussion entries, and worker intermediate state stay here unless a specific promotion/materialization path moves selected content elsewhere.

#### Letta borrowing boundary

- Borrow from Letta:
  - layered memory ownership;
  - first-class current in-context memory objects;
  - prompt compilation as deterministic infrastructure;
  - shared/isolated attachment and lazy dirty refresh;
  - background maintenance as separate from foreground generation.
- Do not borrow blindly:
  - Letta's message-history-first Recall semantics do not define RP Recall.
  - Letta's string Block value does not replace RP typed domain payloads.
  - Letta-style agent self-edit does not bypass RP proposal/apply governance.
  - Letta's core memory compiler does not replace `WritingPacketBuilder`.

#### Temporal materialization contract

- Per-turn projection refresh:
  - updates `Core State.derived_projection`;
  - should keep current hot summaries fresh for runtime use;
  - must not create Recall history merely because a draft or raw hit exists.
  - formal projection slot current/revision metadata must mark:
    - `semantic_layer = "Core State.derived_projection"`
    - `layer_family = "core_state.derived_projection"`
    - `projection_role = "current_projection"`
    - `materialization_event = "projection_refresh"`
    - `authoritative_mutation = False`
- Heavy regression / chapter close:
  - may materialize chapter-level summary into Recall Memory;
  - may materialize accepted story prose into Recall Memory;
  - must not ingest drafts, superseded artifacts, or current-turn discussion traces as settled history.
  - Recall summary/detail source asset metadata and seed section metadata must mark:
    - `layer = "recall"`
    - `source_family = "longform_story_runtime"`
    - `materialization_event = "heavy_regression.chapter_close"`
    - `materialized_to_recall = True`
    - `materialization_kind = "chapter_summary"` or `"accepted_story_segment"`
- Future scene close:
  - may materialize a selected closed-scene transcript into Recall Memory;
  - must define transcript construction rules before treating `StoryDiscussionEntry` as a transcript source.
- Setup/story-evolution import:
  - may materialize authored/imported source material into Archival Knowledge;
  - may propose authoritative Core State mutations through proposal/apply;
  - must not treat setup runtime-private cognition as durable story Memory OS.
- Future background maintenance:
  - may refresh projections, create summaries, or propose low-risk promotions;
  - must operate as maintenance over already-owned layers, not as an uncontrolled alternate truth writer.

#### Discussion entry contract

- `StoryDiscussionEntry` is not automatically a scene transcript.
- Discussion entries are interaction traces / Runtime Workspace material unless a later spec explicitly defines:
  - which entries are selectable;
  - how they are ordered and normalized;
  - how private tool/runtime chatter is filtered;
  - what source metadata and provenance are persisted;
  - when the resulting transcript becomes closed historical Recall.
- Runtime Workspace Block metadata for draft artifacts and discussion entries must mark:
  - `layer = "runtime_workspace"`
  - `source_family = "runtime_workspace"`
  - `workspace_role = "current_turn_scratch"`
  - `materialized_to_recall = False`
  - `recall_materialization_state = "not_recall_materialized"`
  - `not_scene_transcript = True`
  - `scene_transcript = False`

#### Retrieval and tool boundary

- All memory reads exposed to tools flow through `MemoryOsService` / `RetrievalBroker`.
- Workers decide intent; broker executes the read against the correct layer.
- Tools must not bypass the broker to talk directly to Block services, retrieval storage, or Core State repositories.
- Search surfaces stay retrieval-oriented:
  - `memory.search_recall` reads Recall Memory;
  - `memory.search_archival` reads Archival Knowledge.
- Exact current-state surfaces stay Core-State-oriented:
  - `memory.get_state` reads current authoritative state;
  - `memory.get_summary` reads current derived projection.

#### Governance contract

- Authoritative truth mutation uses proposal/apply.
- Projection refresh, recall ingestion, and archival ingestion are maintenance/ingestion paths, not proposal/apply mutation paths.
- Maintenance paths must still preserve provenance and failure visibility.
- Read-only Block-compatible views for Recall, Archival, or Runtime Workspace do not imply those layers are writable through Core State proposal APIs.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Current truth needs exact read | Use `memory.get_state` through `MemoryOsService` / `RetrievalBroker` and resolve `Core State.authoritative_state` |
| Current hot summary needs read | Use `memory.get_summary` through `MemoryOsService` / `RetrievalBroker` and resolve `Core State.derived_projection` |
| Accepted prose is closed during heavy regression | Materialize into Recall Memory as `accepted_story_segment` through retrieval-core |
| Chapter summary is produced during chapter close | Materialize into Recall Memory as `chapter_summary` |
| Draft artifact exists in current workspace | Keep it in Runtime Workspace; do not ingest into Recall |
| Discussion entry exists | Keep as Runtime Workspace / interaction trace unless a transcript promotion spec selects it |
| Imported world book or source document arrives | Ingest into Archival Knowledge, preserving source metadata |
| Worker wants historical detail | Use Recall search; do not inflate Core State with all history |
| Worker wants source/reference knowledge | Use Archival search; do not treat source material as settled story history |
| Authoritative change is requested | Submit proposal/apply; do not patch Core State directly |
| Projection refresh fails | Surface maintenance failure and keep authoritative truth unchanged |
| Recall summary ingestion fails | Raise `recall_summary_ingestion_failed:{asset_id}:{detail}`; do not report false success |
| Recall detail ingestion fails | Raise `recall_detail_ingestion_failed:{asset_id}:{detail}`; do not report false success |
| A later feature needs durable shared container identity beyond current adapters | Write a new executable spec proving the gap before adding a durable registry |

### 5. Good / Base / Bad Cases

- Good: active scene truth is exact-read from `Core State.authoritative_state`, while the current writer-facing outline is read from `Core State.derived_projection`.
- Good: chapter close stores both a compact `chapter_summary` and accepted prose details into Recall Memory, so later retrieval can recover summary and detail.
- Good: imported setting documents enter Archival Knowledge and remain searchable without becoming canon until a governed Core State proposal applies selected facts.
- Good: current-turn draft text appears in Runtime Workspace Block views for visibility, but it is not Recall until accepted and materialized by a close/regression path.
- Base: `StoryDiscussionEntry` remains an interaction trace; a future scene transcript feature must define promotion rules before using it as historical material.
- Bad: stuffing every historical fact into `Core State.authoritative_state` until current truth becomes an unbounded archive.
- Bad: treating Archival source documents as Recall history just because they are retrievable.
- Bad: letting a worker write Core State directly because Letta supports memory edit tools.
- Bad: replacing `WritingPacketBuilder` with a generic memory compiler and exposing raw retrieval/Core State JSON to the writer.
- Bad: adding universal durable `rp_blocks` before proving current Core State rows, retrieval-core storage, and read-only Block-compatible views are insufficient.

### 6. Tests Required

For this total-spec itself:

- Documentation consistency checks:
  - backend spec index includes this spec;
  - task `implement.jsonl` and `check.jsonl` include this spec for future sub-agents;
  - task PRD records the post-D4b temporal materialization planning step.

For later executable slices:

- Projection refresh:
  - proves current hot summary updates without mutating authoritative truth;
  - proves writer-facing packets still receive deterministic projection sections through `WritingPacketBuilder`.
  - proves projection current rows and revision rows carry `Core State.derived_projection` / maintenance / non-authoritative metadata.
- Recall materialization:
  - proves `chapter_summary` and `accepted_story_segment` are retrievable from Recall;
  - proves draft/superseded/current-turn scratch is not ingested.
  - proves summary/detail metadata identifies Recall layer, source family, materialization event, and materialization kind.
  - proves summary/detail ingestion failures surface explicitly from the returned retrieval-core `IndexJob`.
- Future transcript promotion:
  - proves discussion entries are filtered/normalized before transcript materialization;
  - proves private runtime/tool chatter is excluded.
- Archival ingestion:
  - proves imported source material is searchable through `memory.search_archival`;
  - proves source material does not silently mutate Core State.
- Governance:
  - proves authoritative changes still require proposal/apply;
  - proves maintenance failures are visible and do not create false-success state.

### 7. Wrong vs Correct

#### Wrong

```text
Letta has blocks and recall, so RP should use one generic block table for
current truth, history, source docs, drafts, and tool traces.
```

#### Correct

```text
Use Letta to validate the need for layered memory mechanics, then let RP
requirements decide ownership: current truth in Core State, history in Recall,
source/reference material in Archival, and current-turn scratch in Runtime
Workspace.
```

#### Wrong

```text
StoryDiscussionEntry exists, therefore it is already a scene transcript and
should be indexed into Recall.
```

#### Correct

```text
StoryDiscussionEntry is Runtime Workspace / interaction trace by default. A
future scene transcript spec must explicitly define selection, filtering,
normalization, provenance, and close timing before Recall ingestion.
```
