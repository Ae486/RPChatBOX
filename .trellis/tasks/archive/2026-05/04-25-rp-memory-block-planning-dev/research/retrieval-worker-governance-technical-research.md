# Retrieval Card Loop + Worker Governance Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: lightweight pre-spec technical research for:
> - `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md`
> - `.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md`

## 1. Question

For the next boot-bar memory pair, what should be reused for:

- retrieval card / expansion / usage / post-write source-ref loop
- worker-facing governed memory reads/proposals/refresh requests

without widening the public memory tool family or inventing separate hidden service paths?

## 2. Existing Repo Wheels To Reuse

### RetrievalBroker and retrieval-core

Current repo already has:

- `RetrievalBroker`
- retrieval-core store/query/rerank/trace path
- `RetrievalRuntimeConfigService`
- retrieval observability

Decision:

- keep the existing retrieval core and `RetrievalBroker` as the read boundary;
- do not introduce a second retrieval framework or separate “writer retrieval stack”;
- extend the runtime path so broker results can be materialized as Runtime Workspace cards.

### Runtime Workspace typed material model

Current repo already froze the right material families:

- `retrieval_card`
- `retrieval_expanded_chunk`
- `retrieval_miss`
- `retrieval_usage_record`
- `worker_candidate`
- `worker_evidence_bundle`

Decision:

- reuse Runtime Workspace as the only boot-bar place where retrieval cards/usages live;
- do not allow retrieval hits to bypass Workspace and jump directly into Core truth.

### Proposal/apply governance

Current repo already has:

- proposal validation
- proposal persistence
- policy decision
- apply path with base revision conflict enforcement

Decision:

- worker-facing memory write contract must adapt into existing proposal/apply, not replace it;
- new worker governance metadata should be recorded around the existing mutation kernel.

### Existing public memory provider boundary

Current repo already froze the public memory tool family:

- `memory.get_state`
- `memory.get_summary`
- `memory.search_recall`
- `memory.search_archival`
- `proposal.submit`
- `memory.list_versions`
- `memory.read_provenance`

Decision:

- boot-bar worker contracts should first be internal/shared service contracts;
- if worker-facing tool DTOs are exposed, they must adapt to those same internal contracts and must not invent a parallel mutation/read path.

## 3. Mature External References

### Letta

Useful reference:

- core vs archival memory split
- tool-managed retrieval/search/edit path
- archival hits are searched, not silently promoted into always-visible core memory

Absorbed conclusion:

- retrieval use should become structured cards/refs before it can influence maintenance or truth;
- archival/recall search must stay tool-mediated and provenance-bearing.

### Anthropic workflow guidance

Useful reference:

- prefer deterministic workflow/service boundaries around model decisions
- keep orchestration and side effects explicit

Absorbed conclusion:

- writer may decide knowledge is missing, but backend still owns:
  - bounded retrieval loop shape
  - card storage
  - expansion rules
  - usage recording
  - governed promotion

## 4. Rejected Options

Rejected for this pair:

- a second hidden retrieval stack only for writer calls
- direct retrieval-hit-to-Core promotion
- worker-specific write paths that bypass proposal/apply
- widening the public tool family first and only later inventing internal contracts
- raw retrieval dump injection as the long-term writer contract

Reason:

- each one would either duplicate the system, bypass governance, or make traceability weaker.

## 5. Spec Decisions Enabled By This Research

1. `H-min` should materialize broker results into Runtime Workspace cards under full runtime identity.
2. expansion should work over already-returned cards/chunks, not over arbitrary raw hits.
3. usage must record exact card/chunk refs used by writer, not inferred prose heuristics.
4. post-write promotion should consume used refs as source refs into proposal/maintenance, never direct retrieval rows as truth.
5. `E-min` should freeze shared internal worker-facing service contracts first; external DTO exposure can remain partial.
6. worker-facing reads/searches/proposals/refresh requests must carry:
   - `MemoryRuntimeIdentity`
   - `worker_id`
   - `phase`
   - permission decision/profile
   - source refs / trace refs
7. public memory provider boundary remains stable while internal boot worker governance grows stronger.

## 6. Immediate Spec Consequence

The next two backend specs should be:

1. `rp-retrieval-card-usage-promotion-boot-contract.md`
2. `rp-worker-memory-tool-permission-boot-contract.md`

They should be written as incremental extensions over:

- `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
- `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md`
- `.trellis/spec/backend/rp-memory-tool-chain-block-compatibility.md`
- `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md`
- current `RetrievalBroker`, `WritingWorkerExecutionService`, `ProposalWorkflowService`, `ProposalApplyService`, and `MemoryCrudToolProvider`

They should not introduce:

- a new public memory tool family
- a second retrieval engine
- direct retrieval-to-Core writes
- worker-specific raw mutation shortcuts
