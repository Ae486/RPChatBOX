# Runtime Branch Visibility + Read Manifest Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: lightweight pre-spec technical research for:
> - `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`
> - `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`

## 1. Question

For the next boot-bar memory pair, what external and local patterns are actually worth absorbing for:

- branch-aware visibility across Core / Projection / Runtime Workspace / Recall / Retrieval;
- deterministic read manifest and strict fact/view boundaries for writer and scheduler packets?

The standard is practical absorption only. If a framework or doc does not change the contract, it should not be carried forward just to decorate the proposal.

## 2. Absorbable External Signals

### LangGraph persistence / time-travel

Useful reference:

- checkpoints are graph-state snapshots organized by thread;
- replay and fork exist at the workflow-shell level.

Absorbed conclusion:

- keep LangGraph as the lower-layer checkpoint/fork substrate;
- do not mistake checkpoint replay for memory-layer branch visibility;
- branch-aware memory reads must stay application-owned.

Official references:

- `https://docs.langchain.com/oss/python/langgraph/persistence`
- `https://docs.langchain.com/oss/python/langgraph/use-time-travel`

### Dolt / lakeFS branch semantics

Useful reference:

- branch creation can be metadata-first / zero-copy;
- changed data diverges through copy-on-write rather than full duplication.

Absorbed conclusion:

- RP branch creation should not copy all memory rows or all retrieval artifacts;
- visibility should be computed from active branch lineage plus later-turn hide rules;
- branch-aware reads need lineage and cutoff metadata, not whole-store clones.

Official references:

- `https://docs.dolthub.com/sql-reference/version-control/branches`
- `https://docs.lakefs.io/v1.61/quickstart/branch/`

### Letta core vs archival memory split

Useful reference:

- core memory is always visible;
- archival memory is out-of-context and tool-searched;
- archival storage should not silently become in-context truth.

Absorbed conclusion:

- RP should keep strict current fact/view vs searchable history/source separation;
- deterministic read manifest must explicitly record what became visible vs what was merely searchable;
- retrieval hits must not automatically become Core truth.

Official references:

- `https://docs.letta.com/guides/agents/memory-blocks/`
- `https://docs.letta.com/guides/ade/archival-memory`

## 3. Rejected External Patterns

Rejected for this pair:

- using LangGraph checkpoint state as the branch visibility source of truth
- cloning full memory stores per branch like a repo/worktree copy
- using Letta-style direct block overwrite semantics as the Core truth update model
- treating retrieval/index infrastructure as branch truth instead of derived visibility infrastructure

Reason:

- each one would either collapse layers, over-copy storage, or bypass the project's governed mutation model.

## 4. Existing Repo Wheels To Reuse

### Existing Memory OS layer boundaries

Already frozen locally:

- `Core State.authoritative_state`
- `Core State.derived_projection`
- `Recall Memory`
- `Archival Knowledge`
- `Runtime Workspace`

Absorbed conclusion:

- `C` should extend this with branch visibility defaults, not redefine the layer model;
- `D` should extend this with read-manifest and projection-hardening rules, not introduce a replacement compile system.

### Current projection and mutation hardening specs

Already frozen locally:

- base revision conflict checks
- projection refresh freshness metadata
- Runtime Workspace typed materials
- event skeleton / event spine

Absorbed conclusion:

- `D` should build on those specs rather than restating them from scratch;
- runtime-owned refresh paths should become identity-required while legacy compatibility remains explicit and bounded.

## 5. Spec Decisions Enabled By This Research

1. `C` should define a branch visibility resolver over lineage/cutoff metadata, not over full cloned memory stores.
2. branch visibility must be a shared read contract reused by:
   - Core reads
   - Projection reads
   - Runtime Workspace reads
   - Recall search
   - RetrievalBroker runtime calls
3. retrieval/index rows are derived infrastructure and must inherit source visibility instead of inventing independent branch truth.
4. `D` should freeze a deterministic read manifest that answers:
   - what was visible
   - what was selected
   - why something was omitted
   - which revisions/hashes/refs were used
5. `D` must not replace `WritingPacketBuilder`; it must provide a contract that packet builders can consume.
6. runtime-owned projection refresh should require identity and strict fact/view separation, while legacy no-identity bundle refresh remains an explicit compatibility path only.

## 6. Immediate Spec Consequence

The next two backend specs should be:

1. `rp-branch-visibility-resolver-lineage.md`
2. `rp-core-projection-read-manifest-hardening.md`

They should be written as incremental extensions over:

- `.trellis/spec/backend/rp-memory-temporal-materialization.md`
- `.trellis/spec/backend/rp-memory-os-block-rollout.md`
- `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
- `.trellis/spec/backend/rp-projection-refresh-write-contract.md`
- `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
- `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md`

They should not introduce:

- branch merge
- runtime scheduler implementation
- a replacement for `WritingPacketBuilder`
- direct retrieval-to-Core promotion
- full debug UI
