# Runtime Identity + Profile Compiler Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: lightweight pre-spec technical research for:
> - `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
> - `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md`

## 1. Question

For the first memory boot-bar spec pair, what should be reused, and what should explicitly not be introduced?

The target is:

- persistent `BranchHead` / `StoryTurn`
- persistent immutable `RuntimeProfileSnapshot`
- deterministic runtime identity resolution
- deterministic profile compilation and turn-start pinning

without replacing the current stack or importing a heavyweight new branch/memory framework.

## 2. Existing Repo Wheels To Reuse

### SQLModel / SQLAlchemy persistence

Current repo already persists story/session/chapter/artifact/discussion state through SQLModel records and compatible schema helpers.

Decision:

- keep the same persistence pattern for `BranchHead`, `StoryTurn`, and `RuntimeProfileSnapshot`;
- do not introduce a second persistence stack, document database, or git-backed memory repo for this slice.

### Pydantic contract models

Current memory/runtime contracts already use Pydantic effectively:

- `MemoryRuntimeIdentity`
- `MemoryChangeEvent`
- `RuntimeWorkspaceMaterial`
- retrieval / proposal / projection DTOs

Decision:

- keep contract-first Pydantic DTOs around the new persistent records and compiler outputs;
- use typed compile output instead of ad hoc dict branching.

### Memory contract registry skeleton

Current `MemoryContractRegistryService` already provides:

- bootstrap domains
- mode defaults
- aliases / migration ids
- block templates
- permission defaults

Decision:

- reuse it as the input skeleton for `RuntimeProfileSnapshot` compilation;
- do not wait for full dynamic registry CRUD before freezing the minimal compiler spec.

## 3. Mature External References

### LangGraph

Useful reference:

- persistent checkpoint shell
- replay / fork primitives
- runtime workflow identity can remain external to graph state

Boundary:

- LangGraph does not make external memory stores branch-aware by itself.

Decision:

- keep LangGraph as workflow shell;
- do not use LangGraph checkpoints as the memory identity store of record.

### Letta

Useful reference:

- source-of-truth plus read-cache separation
- commit-style audit thinking
- block/tool-managed memory discipline

Boundary:

- Letta git memory versions one agent memory tree, not `StorySession + BranchHead + Turn + RuntimeProfileSnapshot`.
- Letta MemFS / git HTTP is too heavy and too file-tree-oriented for the first RP boot-bar slices.

Decision:

- copy architectural lessons only;
- do not transplant Letta git memory, memfs, or block repo as RP runtime identity storage.

### Dolt / lakeFS

Useful reference:

- metadata-first branching
- copy-on-write semantics
- branch lineage without full data cloning

Boundary:

- current RP product truth already lives in application tables, proposal/apply records, retrieval metadata, and Runtime Workspace material.
- replacing storage with Dolt or lakeFS would turn this task into a persistence migration rather than a memory contract strengthening task.

Decision:

- use them as branch semantics references only;
- keep RP branch identity in application storage and use lineage/visibility fields instead of full clone semantics.

## 4. Rejected Options

Rejected for this spec pair:

- Letta MemFS / git-backed primary memory store
- Dolt or lakeFS as the product truth backend
- a new agent runtime/framework for profile compilation or worker routing
- event-sourcing as the source of runtime identity truth

Reason:

- all of them introduce larger migrations than the current boot-bar memory problem requires;
- current repo already has the right persistence and contract layers to carry these slices with far less churn.

## 5. Spec Decisions Enabled By This Research

1. `BranchHead`, `StoryTurn`, and `RuntimeProfileSnapshot` should be first-class SQLModel records in RP application storage.
2. Runtime identity resolution should be a deterministic backend service, not an LLM decision and not an implicit graph-only concept.
3. `RuntimeProfileSnapshot` should compile from:
   - bootstrap registry defaults
   - persisted story/runtime config inputs
   - explicit overrides/publish actions
4. turn-start must pin one immutable snapshot id and carry it through memory/retrieval/proposal/workspace/event writes.
5. external API entry can still start at `session_id`, but internal boot-bar paths must resolve full runtime identity before touching stores.
6. branch semantics should be modeled through persistent lineage fields plus later visibility resolution, not through full branch repo clones.

## 6. Immediate Spec Consequence

The first two backend specs should be:

1. `rp-runtime-identity-persistence-propagation.md`
2. `rp-runtime-profile-snapshot-minimal-compiler.md`

They should be written as incremental extensions over:

- `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`
- current `backend/models/rp_story_store.py`
- current `backend/rp/services/memory_contract_registry.py`

They should not introduce:

- branch UI
- branch merge
- full registry CRUD UI
- a new agent framework
- file-tree or git-backed memory truth storage
