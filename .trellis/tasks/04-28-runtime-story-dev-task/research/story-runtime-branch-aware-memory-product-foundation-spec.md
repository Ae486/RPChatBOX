# Story Runtime Branch-aware Memory Product Foundation Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Stage: V
>
> Status: draft-v1

## 1. Scope

This stage turns Memory OS from a mostly backend-visible foundation into a
branch-aware, user-readable, user-editable product surface.

This is not a single "memory panel" UI task. Product-level readable + editable
memory requires all of the following to be true:

- active branch reads resolve the correct memory state for the selected branch
  and cutoff turn;
- writer context uses that same branch-aware memory/read scope;
- users can inspect Core, Projection, Runtime Workspace, Recall, and Archival
  layers through one canonical envelope;
- users can edit Core through governed direct edit;
- users can review Recall through lifecycle actions;
- users can edit Archival through Story Evolution / version / reindex
  governance;
- writer brainstorm can produce user-confirmed summary items and apply them
  through the same governed memory paths;
- post-write maintenance can materialize the minimum memory outputs needed by
  the next writer turn.

## 2. Source Documents

This stage is grounded in existing task/spec documents, not old MVP runtime
code.

- `story-runtime-memory-domain-preliminary-design.md`
  - all Memory OS layers should be visible to users;
  - Core State can be directly edited by users;
  - Recall is mostly review / invalidation / recomputation;
  - Archival can be modified only through Evolution / ingestion / reindex.
- `rp-branch-visibility-resolver-lineage.md`
  - Core, Projection, Runtime Workspace, Recall, and RetrievalBroker runtime
    calls must enforce active branch lineage;
  - branch creation is metadata-first / copy-on-write, not full-store cloning;
  - rollback hides later memory/materialization for runtime reads.
- `rp-user-visible-memory-inspection-edit-backend-contracts.md`
  - one branch-aware inspection surface must cover Core / Projection /
    Workspace / Recall / Archival;
  - Core direct edit, Recall review, and Archival evolution must route through
    governed backend services.
- `rp-user-visible-memory-canonical-json-governance.md`
  - UI, worker trace, debug, and eval must share one canonical block/entry
    envelope with stable ids, revisions, editable fields, allowed actions, and
    entrypoints.
- `rp-shared-core-mutation-kernel-direct-edit.md`
  - user direct edit, worker proposal apply, and brainstorm summary apply must
    share one governed Core mutation kernel.
- `rp-recall-branch-aware-lifecycle.md`
  - Recall is historical memory, not current truth;
  - Recall materialization/search/recompute/supersede/invalidate must be
    branch-aware.
- `rp-archival-evolution-reindex-governance.md`
  - Archival edits create versioned source/chunk/index chains and reindex jobs;
  - active runtime Evolution writes default to current-branch visibility.
- `story-runtime-story-evolution-development-spec.md`
  - Story Evolution reuses Memory Inspection, governed mutation, Archival
    ingestion/retrieval maintenance, memory events, and branch visibility.
- `story-runtime-technical-research-and-pseudocode.md`
  - brainstorm does not directly modify blocks; it produces summary items,
    waits for user edit/reject/apply, then hands confirmed items to scheduler /
    workers / governed memory dispatch.
- `runtime-tech-research-memory-versioning.md` and
  `branching-memory-framework-research.md`
  - use Dolt/lakeFS-style metadata-first branch semantics and Letta-inspired
    memory block/version lessons inside RP storage;
  - do not replace RP branch-aware database governance with Letta MemFS or
    LangGraph checkpoints.

## 3. Stage Slices

### V0. Product Evidence Lock

Run a short no-new-feature revalidation before implementing memory product
work:

- clean longform session;
- structured outline accepted;
- first two accepted story segments;
- branch from the earlier segment;
- continue on the new branch;
- inspect writer packet/read manifest/current branch evidence.

The goal is not broad manual QA. The goal is to capture the current baseline
and route failures:

- branch body truth bug;
- branch-aware memory/read-scope missing;
- old session / old outline artifact;
- model-following weakness;
- frontend/backend reachability gap.

### V1. Branch-aware Memory Resolver Closure

Implement or complete the read resolver used by memory inspection, writer
context, Recall search, RetrievalBroker runtime calls, and debug/eval reads.

Minimum contract:

```python
class RuntimeBranchMemoryReadScope(BaseModel):
    story_id: str
    session_id: str
    active_branch_head_id: str
    selected_turn_id: str | None = None
    turn_cutoff_by_branch: dict[str, str | None]
    visible_branch_head_ids: list[str]
    include_story_global: bool = True


class BranchAwareMemoryReadResolver:
    def build_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> RuntimeBranchMemoryReadScope: ...

    def filter_visible_memory_refs(
        self,
        *,
        scope: RuntimeBranchMemoryReadScope,
        refs: list[MemorySourceRef],
    ) -> list[MemorySourceRef]: ...
```

Rules:

- writer context, Memory inspection, Recall search, RetrievalBroker runtime
  calls, and debug/eval reads must share the same read scope contract;
- creating a branch from turn `N` must not copy all memory;
- pre-fork memory remains visible through lineage;
- post-fork writes/materializations belong to the producing branch;
- current writer context must not read hidden future memory from the source
  branch after fork or rollback;
- old `latest session` projection/digest reads must not feed writer context on
  runtime-owned paths.
- runtime product read paths must not use `accepted_segment_ids_json`, legacy
  `turn_id` / `branch_head_id` artifact metadata, or output-ref reverse lookup
  as truth fallback. Exact `runtime_turn_id` / `runtime_branch_head_id` remains
  the ownership boundary for runtime-produced story artifacts.

V1 also owns Core State as-of closure. Branch filtering over materials is not
enough because the same Core object may have different values at different
turns. Runtime Core reads must resolve the selected branch/turn's Core State
manifest and object revisions before reading payloads.

Minimum contract:

```python
class CoreStateSnapshotManifest(BaseModel):
    snapshot_id: str
    parent_snapshot_id: str | None = None
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
    effective_revision_map: dict[str, str]
    changed_ref_ids: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)


class CoreStateAsOfResolver:
    def resolve_manifest(
        self,
        *,
        scope: RuntimeBranchMemoryReadScope,
        selected_turn_id: str | None = None,
    ) -> CoreStateSnapshotManifest: ...

    def resolve_object_revision(
        self,
        *,
        manifest: CoreStateSnapshotManifest,
        object_ref: ObjectRef,
    ) -> CoreStateAuthoritativeRevisionRecord: ...
```

Rules:

- turn `0` / activation creates the initial Core State manifest;
- turns with no Core mutation reuse the previous visible manifest;
- a Core-mutating turn creates complete object revisions for changed objects and
  a new manifest that inherits unchanged object revision pointers;
- branch creation from turn `N` inherits the manifest visible at turn `N`;
- first Core mutation on a branch creates branch-scoped object revisions and a
  new branch-local manifest;
- current/latest Core object rows are cache/compatibility views only for
  runtime-owned reads and must not feed writer context as truth;
- old sessions without turn-bound Core history may receive a compatibility
  snapshot, but historical as-of reads before the migration anchor must be
  marked unavailable instead of fabricated.

### V2. Memory Inspection/Edit Backend Product Contract

Harden the backend product surface so the frontend can call one coherent
memory API family:

```text
GET  /api/rp/story-sessions/{session_id}/memory/inspection
POST /api/rp/story-sessions/{session_id}/memory/core/direct-edit
POST /api/rp/story-sessions/{session_id}/memory/recall/actions
POST /api/rp/story-sessions/{session_id}/memory/archival/evolution
```

Rules:

- Core edits route through shared governed mutation;
- Recall actions are lifecycle review actions, not raw text writes;
- Archival edits route through Evolution/version/reindex;
- every response that can be rendered by the product surface returns the
  canonical block/entry envelope;
- all actions carry full `MemoryRuntimeIdentity`, branch/cutoff scope, base
  revision when applicable, source refs, and actor/origin metadata.

### V3. Memory Product UI Surface

Expose the Memory OS as a product surface inside story runtime.

Minimum UI capabilities:

- read Core / Projection / Runtime Workspace / Recall / Archival blocks;
- show domain, layer, visibility, revision, lifecycle, source refs, validation,
  allowed actions, and entrypoints from the canonical envelope;
- edit Core entries when `direct_core_edit` is allowed;
- trigger Recall recompute / invalidate / supersede actions when allowed;
- trigger Archival evolution for editable Archival entries;
- show branch identity and selected/cutoff turn used by the memory view;
- refresh writer context evidence after memory changes.

The UI must not invent a second memory shape. It consumes backend canonical
envelopes and action entrypoints.

### V4. Writer Brainstorm Apply

Add the product path that turns writer brainstorm discussion into governed Core
State change candidates.

Writer brainstorm is not a memory worker and not a memory editor. It is the
writer's discussion persona / mode: it sees the writer-visible context plus the
user's brainstorm prompt, discusses with the user, and later summarizes the
discussion into user-editable intent items. It must not know Memory OS layer
details or Core field paths.

Minimum flow:

1. user starts brainstorm from the story runtime discussion area;
2. backend creates a branch/turn-scoped `BrainstormSession` with Runtime
   Workspace semantics;
3. writer brainstorm mode uses the writer packet plus the user's brainstorm
   prompt and discussion transcript;
4. ordinary discussion does not create memory items or write memory;
5. if the user decides nothing should change, the session closes as no-op and
   the user returns to writing;
6. if the user explicitly clicks/runs "summarize as change items" or equivalent,
   a dedicated `brainstorm_summarize` prompt reads this brainstorm session and
   outputs structured `BrainstormItem[]`;
7. user can edit, reject, or confirm each item;
8. confirmed items are sent to the scheduler / dispatcher;
9. the scheduler classifies Core domain / worker ownership for each confirmed
   item;
10. the corresponding Core worker reads branch-aware as-of Core State and base
    revision, then produces minimal field-level executable changes;
11. backend fills deterministic old values, performs base revision / conflict
    checks, and applies worker permission policy;
12. Core-affecting worker outputs use `brainstorm_summary_apply` through the
    shared Core mutation kernel;
13. result receipts are visible in Memory inspection and runtime inspect.

Brainstorm remains separate from revision comments and Story Evolution.
Revision comments guide rewrite of prose. Writer brainstorm is a Core State
discussion-to-intent path. Recall is historical memory and is not normally
edited by brainstorm. Archival changes go through Story Evolution / version /
reindex governance, not through V4 brainstorm.

Brainstorm summary items must stay memory-layer agnostic. They may preserve
user intent, low-cost evidence handles, and uncertainty, but they must not claim
`target_layer`, `target_domain`, `operation_kind`, `intent_labels`, or a
governed operation. Those fields are owned by the scheduler/dispatcher and
memory workers.

Brainstorm summary creation is a context-engineering operation, not ordinary
writer chat and not memory mutation. It should use the shared Context
Engineering / Compact-Summary contract described in
`context-engineering-compact-summary-module-spec.md`: brainstorm sees the
writer-visible context plus the user's brainstorm prompt, produces typed
summary items, then waits for user edit/reject/confirm before scheduler
dispatch.

The first version uses explicit summarization only. Brainstorm must not decide
by itself when to summarize, must not incrementally write temporary items after
each chat turn, and must not silently dispatch changes. This avoids extra LLM
judgment calls, premature summaries, and hidden token/latency cost.

Minimum persistence semantics:

- `BrainstormSession` represents one discussion/summarization task and has
  Runtime Workspace material semantics: branch/turn scoped, temporary,
  traceable, cleanable, and not truth.
- `BrainstormItem` is the per-item unit users can edit / reject / confirm /
  dispatch.
- `source_item_id` in downstream worker output points to the confirmed
  `BrainstormItem`, not directly to an arbitrary discussion message.
- full conversation `source_refs` are optional and may be added after
  discussion message ids / transcript anchors are stable.

Minimum context scope:

- default brainstorm input uses writer-visible context, branch-aware Core
  projection, current discussion thread, user brainstorm prompt, and a small
  recent prose / turn summary if needed;
- it does not proactively pull Recall, Archival, or retrieval results;
- retrieval/search is only allowed when the user explicitly asks to check prior
  text/material before discussing the change.

Resource principle:

- brainstorm summarizes intent only;
- scheduler classifies only confirmed items;
- V4 workers process only confirmed Core-oriented items;
- non-Core wishes are returned as review/redirect material, such as Story
  Evolution for Archival changes, instead of being dispatched as Recall or
  Archival brainstorm edits;
- worker result fields stay minimal and executable;
- deterministic backend code fills fields that do not require LLM judgment.

### V5. Post-write Memory Maintenance Minimum Closure

Close the minimum gap between accepted prose and next-turn memory quality.

Required work:

- projection refresh requests execute as derived view maintenance, not truth
  writes;
- Recall materialization records accepted settled prose / closed scene /
  continuity material with branch-aware lifecycle metadata;
- Archival materialization or Evolution outputs remain versioned and scoped;
- deferred materialization jobs are either completed, explicitly deferred with
  user-visible reason, or excluded from next-turn packet by contract;
- writer packet/read manifest can explain which memory refs were selected,
  omitted, stale, or hidden by branch/rollback.

### V6. Product Acceptance

Acceptance must follow implemented scope only. It must not test future full
RP/TRPG runtime, branch merge, physical purge, or legacy-session migration.

The minimum product path:

1. create clean longform session;
2. write and accept two segments;
3. inspect memory view on main branch;
4. branch from segment one;
5. verify memory view and writer packet do not include post-fork future memory;
6. direct-edit a Core item and verify event / dirty / projection effect;
7. run one Recall action;
8. run one Archival Evolution edit and verify version/reindex receipt;
9. brainstorm a story-memory change, confirm it, and verify governed apply;
10. continue writing and verify writer context uses the updated branch-aware
    memory state.

## 4. Design Decisions

### Branch-aware memory before Memory UI

Memory UI cannot come first. If the product shows or edits memory while reads
still use latest-session state, a user can edit the wrong branch's truth. V1
therefore precedes V2/V3.

### Copy-on-write, not memory snapshots per branch

New branches do not clone full Core / Recall / Archival / Workspace state. RP
uses `BranchHead + Turn + MemoryChangeEvent + revision/provenance` as the
application-level commit model, with branch-scoped writes after divergence and
lineage reads for shared ancestors.

For Core State, the copy-on-write unit is a turn-bound snapshot manifest plus
complete object revisions for changed objects. The manifest is the branch/turn
read anchor; object revisions are payload truth; MemoryChangeEvent/apply receipt
records are audit, diff, dirty-target, and projection-refresh evidence.

### Layer-specific edit semantics

Readable + editable does not mean one generic CRUD API:

- Core: direct governed edit;
- Projection: inspect / refresh, not direct truth write;
- Runtime Workspace: inspect scratch/candidates, promotion only through
  governed paths;
- Recall: lifecycle review / recompute / invalidate / supersede;
- Archival: Evolution / version / reindex.

### Brainstorm is not direct memory mutation

Brainstorm output is structured discussion summary. It becomes memory change
only after user confirmation and governed apply. This prevents a discussion
feature from becoming a hidden truth-write shortcut.

### Brainstorm does not classify Memory layers

The discussion worker is not a Memory OS router. It should not know or decide
whether an item belongs to Core, Recall, or Archival. Its job is to summarize
what the user wants to change in plain structured items. The scheduler /
dispatcher and memory-domain workers own classification, routing, and governed
operation planning.

## 5. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Branch created from turn N | New branch reads pre-fork memory and excludes source-branch post-N memory |
| Core changes at turn 3 while turn 1/2 had no Core change | Turn 1/2 reuse the previous Core manifest; turn 3 creates a new manifest |
| Branch created from turn 2 after Core changed at turn 3 | New branch reads the turn 2 Core manifest, not the latest current Core row |
| Writer continues on new branch | Writer packet/read manifest uses active branch memory scope, not latest session projection |
| Rollback hides later turn | Workspace, Recall, retrieval hits, and derived projections after cutoff are hidden from default runtime reads |
| User inspects Memory OS | Canonical blocks/entries include layer, domain, revision, visibility, allowed actions, and entrypoints |
| User edits Core | Shared mutation kernel records actor/origin/base refs/event/dirty/projection effect |
| User reviews Recall | Recall lifecycle action records traceable recompute/invalidate/supersede result |
| User edits Archival | Evolution creates version/reindex receipt and active runtime search excludes superseded hidden chunks |
| User applies brainstorm item | Confirmed item routes through scheduler/governed memory dispatch with `brainstorm_summary_apply` origin where applicable |
| Post-write maintenance is incomplete | Next writer turn either sees completed memory materialization or an explicit omitted/deferred reason |

## 6. Wrong vs Correct

### Wrong

```python
data = core_state_store.get_authoritative_object(
    session_id=identity.session_id,
    layer=ref.layer.value,
    scope=ref.scope,
    object_id=ref.object_id,
).data_json
```

This reads latest session cache and leaks future Core values into branches
created from earlier turns.

### Correct

```python
scope = branch_memory_read_resolver.build_scope(
    identity=identity,
    selected_turn_id=identity.turn_id,
)
manifest = core_state_as_of_resolver.resolve_manifest(scope=scope)
revision = core_state_as_of_resolver.resolve_object_revision(
    manifest=manifest,
    object_ref=ref,
)
data = revision.data_json
```

Runtime-owned Core reads use selected branch/turn manifest resolution. Latest
current rows remain cache or explicit compatibility views.

### Wrong

```python
projection = latest_session_projection(session_id)
packet.current_state_digest = projection.current_state_digest
```

This reads latest-session state and can leak source-branch future memory into a
new branch.

### Correct

```python
scope = branch_memory_read_resolver.build_scope(
    identity=identity,
    selected_turn_id=identity.turn_id,
)
packet.memory_sections = context_orchestrator.build_memory_sections(
    identity=identity,
    read_scope=scope,
)
```

Writer context is built from the same branch-aware scope used by memory
inspection and retrieval filtering.

### Wrong

```python
memory_row.value = user_payload["value"]
session.commit()
```

This creates a raw user-only write path and bypasses provenance, conflict
checks, events, and downstream invalidation.

### Correct

```python
receipt = await core_mutation_kernel.submit(
    CoreMutationEnvelope(
        identity=identity,
        origin_kind="user_direct_edit",
        actor=actor,
        domain=domain,
        operations=operations,
        base_refs=base_refs,
        source_refs=source_refs,
        trace_refs=trace_refs,
    )
)
```

User edits, worker applies, and brainstorm applies share the same governed Core
truth mutation path.

## 7. Out Of Scope

- full branch merge / compare;
- physical purge of branch-only memory;
- legacy session migration / old outline compatibility;
- full RP/TRPG runtime;
- replacing retrieval-core, LangGraph, or RP memory storage with Letta MemFS;
- SuperDoc/WebView integration for Memory OS. SuperDoc remains a revision UI
  reference, not the Memory truth model.

## 8. Grill Status

No blocker grill is known for draft-v1.

The only known deferred grill is before V4 implementation: whether
the scheduler/dispatcher output taxonomy should start with a small closed enum
or an extensible label/action taxonomy. `BrainstormItem` itself is confirmed to
remain memory-layer agnostic and does not need this grill.

If implementation finds that task/spec docs do not decide a product semantic,
the escalation order is:

1. check task requirements and backend specs;
2. check local mature project references under `docs/research`;
3. check Python framework/ecosystem options;
4. search the web for current references;
5. only then add a grill question for the user.
