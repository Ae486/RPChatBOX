# RP Shared Core Mutation Kernel And Direct Edit

## Scenario: user direct edit, worker proposal/apply, and brainstorm summary apply must share one governed Core mutation kernel before boot runtime exposes editable current truth

### 1. Scope / Trigger

- Trigger: boot-bar identity, snapshot pinning, persistent events, branch visibility direction, retrieval source refs, and worker permission contracts are now frozen enough that direct Core edits can no longer stay unspecified. The backend must prevent a second hidden write path from emerging when boot runtime or review tools expose “direct edit”.
- Applies to backend RP authoritative Core mutation contract work for:
  - one shared Core mutation envelope/kernel;
  - direct user Core edit routing;
  - worker proposal/apply and brainstorm summary apply alignment;
  - base revision/conflict validation reuse;
  - shared dirty-target / projection refresh / event emission outcomes;
  - focused mutation-governance tests.
- This slice must not:
  - replace proposal/apply persistence;
  - turn projection refresh into a truth write path;
  - widen Recall/Archival user review/edit flows beyond Core direct edit for boot;
  - add a raw user-only write endpoint.

### 2. Surfaces

Shared authoritative mutation envelope:

```python
class CoreMutationEnvelope(BaseModel):
    identity: MemoryRuntimeIdentity
    origin_kind: str
    actor: str
    worker_id: str | None = None
    phase: str | None = None
    domain: str
    domain_path: str | None = None
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef]
    source_refs: list[MemorySourceRef]
    trace_refs: list[str]
    permission_decision: str | None = None
    permission_reason_codes: list[str] = Field(default_factory=list)
    reason: str | None = None
```

Origin kinds:

```text
user_direct_edit
worker_proposal_apply
brainstorm_summary_apply
deterministic_system_refresh
```

Boot direct-edit surface:

```python
class DirectCoreEditRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    domain: str
    domain_path: str | None = None
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef]
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None
```

Kernel service surface:

```python
class CoreMutationKernelService:
    async def submit(self, envelope: CoreMutationEnvelope) -> ProposalReceipt: ...
```

### 3. Contracts

#### Shared kernel contract

- All authoritative Core truth mutations must pass through one shared governed mutation kernel.
- The kernel may adapt into existing proposal/apply services, but must remain the single backend contract for:
  - user direct edit
  - worker proposal/apply
  - brainstorm summary apply
- `StoryStateApplyService` stays an internal apply helper only; it is not an external mutation entrypoint.

#### Direct-edit contract

- Product may label the action `direct edit`.
- Backend implementation must not create a raw user-only write path.
- Direct edit is an immediate governed apply through the shared mutation kernel, with:
  - full runtime identity
  - actor/origin metadata
  - base refs when editing existing facts
  - source refs when available
  - event + dirty-target + projection refresh/invalidation outcomes

#### Conflict contract

- Existing base revision conflict enforcement remains the authoritative conflict guard.
- Any path that edits existing Core facts must provide `base_refs` or follow the explicit legacy compatibility rule if still allowed.
- The kernel must not silently overwrite newer user or worker changes.

#### Outcome contract

- Shared mutation outcomes must include:
  - proposal/apply receipt or immediate apply receipt semantics
  - persistent event record(s)
  - dirty targets for affected projection slots and related downstream consumers
  - pending Runtime Workspace candidate invalidation when targeting the same refs
  - projection refresh or stale marking for affected derived views

#### Worker/brainstorm alignment contract

- Worker authoritative writes stay governed through proposal/apply and may auto-apply only through policy.
- Brainstorm summary apply must not bypass the shared kernel just because it comes from discussion flow.
- Origin metadata must clearly distinguish user, worker, and brainstorm-triggered mutations even when the kernel path is shared.

#### Compatibility contract

- Existing proposal/apply infrastructure remains the backbone.
- This slice does not force full user-visible Recall/Archival edit flows yet.
- Boot-bar scope only requires the shared kernel plus Core direct edit routing if direct edit is exposed.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| User direct edit request enters with identity/base refs | Routed through shared mutation kernel, not raw write |
| Worker authoritative mutation enters | Routed through same kernel with worker/phase/permission metadata |
| Brainstorm summary apply enters | Routed through same kernel with `brainstorm_summary_apply` origin |
| Edit targets stale base revision | Fail closed through existing conflict enforcement |
| Edit succeeds | Event + dirty targets + projection refresh/invalidation outcomes are recorded |
| Matching pending Workspace candidates exist | Candidates are invalidated or marked stale through shared outcome handling |
| Direct edit path tries to skip proposal/apply backbone | Not allowed by contract |

### 5. Good / Base / Bad Cases

- Good: a user fixes a Core fact through `direct edit`, and the backend records actor/origin, applies conflict checks, emits events, and marks affected projection slots dirty.
- Good: a worker proposal and a brainstorm summary apply produce the same type of governed mutation envelope with different origins.
- Base: boot runtime only needs Core direct edit alignment here; wider Recall/Archival edit contracts can follow later.
- Bad: `direct edit` mutates `current_state_json` or Core store directly with no kernel/provenance/event path.
- Bad: worker trusted-path mutation bypasses proposal/apply because it is “internal”.
- Bad: brainstorm summary writes truth through a separate shortcut because it originates from discussion.

### 6. Tests Required

- Contract tests cover:
  - direct edit request adapts into shared mutation envelope;
  - origin kinds are preserved distinctly.
- Conflict tests cover:
  - stale base revision fails closed for direct edit just like worker proposal paths.
- Outcome tests cover:
  - successful direct edit produces event + dirty targets;
  - pending candidate invalidation/stale marking is triggered for matching refs;
  - projection refresh or stale marking is invoked according to the shared path.
- Focused lint/type checks must include the shared kernel contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
story_session.current_state_json["chapter_digest"] = patch
session.commit()
```

This creates a raw user-only write path outside revision/provenance/event/conflict handling.

#### Correct

```python
receipt = await core_mutation_kernel.submit(
    CoreMutationEnvelope(
        identity=identity,
        origin_kind="user_direct_edit",
        actor=user_id,
        domain="chapter",
        operations=operations,
        base_refs=base_refs,
        source_refs=source_refs,
    )
)
```

The same governed mutation kernel handles user direct edit, worker apply, and brainstorm summary apply without creating parallel truth-write semantics.
