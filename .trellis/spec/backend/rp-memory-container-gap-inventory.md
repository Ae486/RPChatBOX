# RP Memory Container Gap Inventory

## Scenario: Decide Whether the Core State Block Rollout Now Needs a New Durable Container Layer

### 1. Scope / Trigger

- Trigger: Phase A and Phase B are green, and the repo needs an explicit decision on whether to introduce a new durable Block/container registry before extending Block coverage beyond Core State.
- Applies to:
  - rollout planning and PRD alignment
  - backend RP memory/container specs
  - follow-up runtime integration slices
- This spec is a decision gate. It does not itself create a new table, registry, or API family.

### 2. Decision Contract

- A new durable container layer is allowed only when current Core State rows plus `RpBlockView` adapters are proven insufficient for required runtime behavior.
- The decision must be based on current code truth and tests, not only proposal prose.
- Current repo decision: **do not introduce a new durable container layer yet**.

Current evidence:

- `RpBlockReadService` plus formal Core State rows already cover read-only Block identity for authoritative and projection state.
- Block-addressed versions, provenance, and proposal visibility already resolve through existing read/governance services.
- `StoryBlockConsumerStateService` plus `StoryBlockPromptContextService` / compile / render already provide attach, dirty tracking, and lazy rebuild for current Core State Blocks.
- The public memory tool chain compatibility gate is already green through `RetrievalBroker`, `MemoryOsService`, and `MemoryCrudToolProvider`.

Current remaining gaps:

- `Recall Memory` lacks Block-compatible read adapters.
- `Archival Knowledge` lacks Block-compatible read adapters.
- `Runtime Workspace` still lacks runtime-scoped Block-compatible views.

These are adapter/view gaps, not proof that one universal durable `rp_blocks` store is required.

### 3. Required Next Move

- The next slice after this decision is retrieval Block-compatible views for Recall / Archival.
- Reuse read-only `RpBlockView` envelopes as the container-facing view model.
- Keep retrieval-core as the physical source of truth.
- Keep public memory search tool contracts stable.
- Defer Runtime Workspace Block-view design until retrieval-backed views are proven.

### 4. Boundary Rules

- Do not create a new durable `rp_blocks` table or shared registry in this decision slice.
- Do not replace retrieval-core physical storage for Recall / Archival.
- Do not push retrieval-backed views into `StoryBlockConsumerStateService` or `block_context` in this slice.
- Do not widen the public memory tool family.
- Do not move setup/runtime-private cognition into durable Memory OS.

### 5. Evidence Checklist

- Phase A/B compatibility and usability checks are green.
- Current Core State Block rollout already covers read/history/provenance/governed mutation visibility.
- Remaining uncovered behavior is specifically in non-Core-State layers.
- The next slice is adapter-first, not storage-first.

### 6. Wrong vs Correct

#### Wrong

```text
Phase B passed, so now we should immediately build one durable rp_blocks registry
for every memory layer.
```

#### Correct

```text
Phase B passing only proves the Core State-first rollout is viable. The next move is
to add Block-compatible views where gaps actually exist, starting with retrieval-backed
Recall / Archival adapters.
```
