# RP Worker Memory Tool And Permission Boot Contract

## Scenario: boot workers need governed memory reads/searches/proposals/refresh requests before runtime can expand beyond one longform specialist path

### 1. Scope / Trigger

- Trigger: boot-bar identity, profile snapshot pinning, persistent Runtime Workspace, persistent events, and retrieval card loops are now in place or planned, but worker-facing memory interaction is still too implicit. Runtime cannot safely expand if workers call arbitrary services without shared identity/phase/permission contracts.
- Applies to backend RP runtime/memory contract work for:
  - shared internal worker-facing memory service contracts;
  - identity/worker/phase/permission-aware guards;
  - proposal/apply permission decision metadata for boot workers;
  - minimal projection refresh request governance for workers;
  - focused permission/governance tests.
- This slice must not:
  - widen the public memory tool family for general external consumers;
  - replace the existing public `MemoryCrudToolProvider`;
  - invent a second mutation kernel separate from proposal/apply;
  - hardcode longform-only worker branches as the contract baseline.

### 2. Surfaces

Internal worker memory context:

```python
class WorkerMemoryContext(BaseModel):
    identity: MemoryRuntimeIdentity
    worker_id: str
    phase: str
    domain: str | None = None
    block_id: str | None = None
    runtime_profile_snapshot_id: str
    permission_profile: dict[str, Any]
    source_refs: list[MemorySourceRef]
    trace_refs: list[str]
```

Internal worker-facing service surface:

```python
class WorkerMemoryService:
    async def get_state(self, *, ctx: WorkerMemoryContext, input_model: MemoryGetStateInput) -> StateReadResult: ...
    async def get_summary(self, *, ctx: WorkerMemoryContext, input_model: MemoryGetSummaryInput) -> SummaryReadResult: ...
    async def search_recall(self, *, ctx: WorkerMemoryContext, input_model: MemorySearchRecallInput) -> RetrievalSearchResult: ...
    async def search_archival(self, *, ctx: WorkerMemoryContext, input_model: MemorySearchArchivalInput) -> RetrievalSearchResult: ...
    async def submit_proposal(self, *, ctx: WorkerMemoryContext, input_model: ProposalSubmitInput) -> ProposalReceipt: ...
    def refresh_projection(self, *, ctx: WorkerMemoryContext, request: ProjectionRefreshRequest) -> None: ...
```

Permission decision record minimum fields:

```text
worker_id
phase
runtime_profile_snapshot_id
permission_decision
permission_reason_codes
```

### 3. Contracts

#### Shared internal contract

- Boot-bar workers should first use shared internal service contracts, not ad hoc direct service calls.
- External DTO exposure may remain minimal, but it must adapt to the same internal shapes rather than inventing a second path.
- The public memory tool family stays stable unless a later spec explicitly widens it.

#### Identity/phase/worker contract

- Every worker-facing memory read/search/proposal/refresh request must carry:
  - `MemoryRuntimeIdentity`
  - `worker_id`
  - `phase`
  - snapshot-derived permission context
- A worker path without this context is invalid for boot-bar runtime behavior.

#### Permission contract

- Permission checks must run before storage mutation or protected read paths.
- Permission resolution must come from the pinned `RuntimeProfileSnapshot`, not scattered defaults or latest mutable config.
- Boot-bar minimum must be able to reject:
  - disabled worker
  - disabled domain/layer
  - forbidden operation kind
  - forbidden phase

#### Proposal/apply governance contract

- Worker authoritative writes still route through existing proposal/apply.
- Proposal records/receipts for worker paths must gain metadata for:
  - identity
  - worker id
  - phase
  - permission decision
  - permission reason codes
- Auto-apply/silent/notify/manual behavior must remain governed by policy, not worker direct writes.

#### Projection refresh contract

- Worker-originated projection refresh requests must still remain derived-view maintenance only.
- Worker refresh path must not mutate authoritative truth directly.
- Refresh permission and identity context must be explicit for runtime-owned worker refreshes.

#### Compatibility contract

- Existing public memory tools remain stable for non-worker callers.
- Boot-bar worker paths may initially be internal-only service contracts while public tool exposure stays unchanged.
- Longform bootstrap workers may adapt through these contracts first, but the contract must stay mode-extensible.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Worker path lacks identity/worker/phase context | Reject before read/search/write |
| Worker is disabled in pinned snapshot | Reject before operation |
| Worker requests forbidden domain/layer/op | Reject before operation |
| Worker submits proposal through internal worker service | Proposal receipt carries worker/phase/permission metadata |
| Worker tries to bypass proposal/apply for Core mutation | Not allowed by contract |
| Worker refreshes projection | Allowed only as derived-view maintenance with identity/permission context |

### 5. Good / Base / Bad Cases

- Good: a longform memory worker reads Core summary, searches Recall, and submits a proposal through one shared internal worker memory service with snapshot-derived permission checks.
- Good: the same contract can later serve roleplay/TRPG workers without rewriting the mutation kernel.
- Base: public MCP/provider tool names remain unchanged while boot worker contracts stay internal/shared.
- Bad: calling `ProposalWorkflowService` directly from each worker with hand-rolled metadata and no shared permission guard.
- Bad: adding a worker-only raw Core mutation shortcut because the worker is “trusted”.
- Bad: forking longform/roleplay/TRPG worker memory contracts into separate service families.

### 6. Tests Required

- Permission tests cover:
  - disabled worker rejection;
  - forbidden domain/layer/op rejection;
  - phase-based rejection;
  - snapshot-derived permission acceptance.
- Proposal/apply tests cover:
  - worker/phase/permission metadata persisted on worker proposal path;
  - no direct authoritative write bypass.
- Integration tests cover:
  - one boot worker path can read/search/propose/refresh through the shared internal contract.
- Focused lint/type checks must include the worker memory contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
receipt = await proposal_service.submit(input_model)
```

This gives no shared worker identity/phase/permission contract and makes governance metadata inconsistent.

#### Correct

```python
receipt = await worker_memory_service.submit_proposal(
    ctx=worker_ctx,
    input_model=proposal_input,
)
```

The worker path carries full runtime identity, worker id, phase, and snapshot-derived permission context into the governed mutation flow.
