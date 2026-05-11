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

Add the product path that turns writer brainstorm discussion into governed
memory changes.

Minimum flow:

1. user starts brainstorm from the story runtime discussion area;
2. writer/brainstorm worker returns structured summary items, not raw memory
   mutations;
3. user can edit, reject, or confirm each item;
4. confirmed items are planned into memory operations;
5. Core-affecting items use `brainstorm_summary_apply` through the shared Core
   mutation kernel;
6. Recall/Archival-affecting items route through lifecycle/evolution services;
7. result receipts are visible in Memory inspection and runtime inspect.

Brainstorm remains separate from revision comments. Revision comments guide
rewrite of prose; brainstorm can change story memory/foundation only after
user confirmation and governed apply.

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

## 5. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Branch created from turn N | New branch reads pre-fork memory and excludes source-branch post-N memory |
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
`BrainstormItem` should start with a small closed enum taxonomy or an
extensible label/action taxonomy. This does not block V0/V1/V2, but it affects
the stability of the brainstorm apply DTO.

If implementation finds that task/spec docs do not decide a product semantic,
the escalation order is:

1. check task requirements and backend specs;
2. check local mature project references under `docs/research`;
3. check Python framework/ecosystem options;
4. search the web for current references;
5. only then add a grill question for the user.
