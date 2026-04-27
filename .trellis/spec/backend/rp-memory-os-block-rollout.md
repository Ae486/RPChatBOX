# RP Memory OS Block Rollout

## Scenario: From Core State Block rollout to full Memory OS containerization

### 1. Scope / Trigger

- Trigger: the repo has moved beyond "should Block exist?" and now needs a real rollout plan that matches current code and frozen boundaries.
- Applies to RP backend Memory OS work across:
  - Core State Block integration
  - memory-layer chain bridging
  - future container registry work
  - final full Memory OS containerization
- This spec is a rollout/sequence contract. It is not a license to skip slice-level specs or quality gates.

### 2. Frozen Boundaries

- Keep the Memory OS hierarchy intact:
  - `Core State`
  - `Recall Memory`
  - `Archival Knowledge`
  - `Runtime Workspace`
- Start Block rollout from `Core State`, not from Recall / Archival physical storage.
- Keep `WritingPacketBuilder` independent from internal Block compile.
- Keep setup runtime-private cognition out of durable story Memory OS.
- Keep the external-facing memory tool family stable unless a later approved phase says otherwise.

### 3. Rollout Definition

Full Memory OS Block containerization in this project means:

- Core State becomes fully container-addressable;
- the memory/retrieval/tool/runtime chain can consume stable container-facing interfaces;
- Recall / Archival may join attach/compile/visibility through Block-compatible views or adapters;
- Recall / Archival do not have to be rebuilt as one new universal Block physical table.

### 4. Phase Order

#### Phase A: Core State complete Block integration and usability gate

Required outcomes:

- read-only Block envelope over Core State is real;
- active-story consumers can attach/read/compile current Blocks;
- authoritative mutation is still governed by proposal/apply;
- Block proposal detail/apply visibility is usable;
- `memory.get_state` / `memory.get_summary` are no longer placeholders for Core State gaps.

#### Phase B: Bridge the memory-layer chain

Required outcomes:

- `RetrievalBroker` remains the read boundary;
- `MemoryOsService` remains a facade;
- `MemoryCrudToolProvider` keeps the public tool contract stable;
- Block-backed Core State reads do not break provider routing, serialization, or agent-visible tool behavior;
- the public non-search tool chain remains stable across `memory.get_state`, `memory.get_summary`, `memory.list_versions`, `memory.read_provenance`, and `proposal.submit`;
- retrieval/tool compatibility failures are covered by focused tests.

#### Phase C: Introduce a new durable container layer only when needed

Required preconditions:

- Phase A and B are green;
- concrete gaps show that current Core State rows + `RpBlockView` adapters are insufficient.

Allowed goals:

- shared durable container registry
- richer attach/evolution semantics
- container identity beyond current Core State rows

Disallowed shortcuts:

- replacing retrieval-core physical storage for Recall / Archival
- bypassing current adapters and contracts
- widening public tool families by accident

Current decision for the repo state covered by this task:

- Phase A and B are green enough to evaluate the question;
- current `RpBlockView` plus formal Core State rows already cover the repo's present durable container needs;
- the remaining real gaps are Recall / Archival / Runtime Workspace Block-compatible views, not proof that a new durable registry is required;
- therefore a new durable container layer stays deferred until a later slice proves otherwise.

#### Phase D: Finish full Memory OS containerization

Required outcomes:

- Core State, retrieval-facing memory views, and runtime-facing compile/visibility flows align on a stable container model;
- end-to-end chain behavior is covered across retrieval, tools, runtime, and governance.

### 5. D4b Close-Out Result

`Phase D4b: Final chain verification and remaining-gap closure after non-Core-State Block views are proven read-only / non-attached` is now complete.

Completed close-out work:

- fixed the governance detail-route drift so non-authoritative Blocks exposed through `/memory/blocks` now reject proposal detail with `memory_block_mutation_unsupported` instead of leaking `memory_block_proposal_not_found`;
- re-verified the active-story compile boundary through Core State-only consumer/prompt tests;
- re-verified the public tool/provider chain through focused `RetrievalBroker` and `MemoryCrudToolProvider` coverage;
- re-verified API/controller governance semantics across authoritative, projection, and Runtime Workspace Block routes.

Conclusion:

- Core State, Recall, Archival, and Runtime Workspace now all have the intended Block-compatible read story for the current repo state;
- non-Core-State Block views remain read-only / non-attached and do not justify extra prompt/runtime wiring;
- the tool/runtime/governance chain is stable without introducing a universal durable container registry;
- therefore no additional real container wiring is currently justified in this rollout.

### 6. Wrong vs Correct

#### Wrong

```text
Core State has Block views now, so we should jump directly to one new rp_blocks table
for every memory layer.
```

#### Correct

```text
First finish Core State Block integration and chain compatibility. Only introduce a new
container registry layer when current adapters prove insufficient.
```
