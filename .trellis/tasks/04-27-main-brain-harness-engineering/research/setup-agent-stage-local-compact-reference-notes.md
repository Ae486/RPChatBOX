# SetupAgent Stage-Local Compact Reference Notes

Date: 2026-04-28

## 1. Purpose

This note narrows mature-agent borrowing for the current SetupAgent slice:

- stage-local compact
- pre-model context transform
- retained tool-result policy
- checkpoint / transient-state boundary
- lightweight runtime observability for context decisions

It explicitly excludes:

- retrieval truth-surface redesign
- foundation chunk contract
- broad new state-management layers

## 2. Mature References Reviewed

### Claude Code

Sources reviewed:

- `docs/research/how-claude-code-works-main/docs/02-agent-loop.md`
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/04-tool-system.md`
- `docs/research/how-claude-code-works-main/docs/09-skills-system.md`

Useful patterns:

- session lifecycle and inner query loop are separate
- context is built as a pipeline rather than a dump bucket
- tool-result budget is managed before the next model call
- compact is a first-class operation rather than an invisible side effect
- skills/resources are loaded on demand instead of permanently inflating prompt context

What to borrow now:

- explicit context-governance boundary
- compact as a named runtime decision
- keep outcomes, not historical tool process

What not to copy now:

- full skill runtime
- Claude Code's larger command/plugin/session surface

### pi-mono

Sources reviewed:

- `docs/research/pi-mono-main/packages/agent/src/agent.ts`
- `docs/research/pi-mono-main/packages/agent/src/agent-loop.ts`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts`

Useful patterns:

- outer `Agent` wrapper owns transcript, queues, and lifecycle
- low-level loop only handles model/tool turns
- `transformContext -> convertToLlm` is an explicit pre-LLM boundary
- compaction has:
  - trigger logic
  - cut-point logic
  - previous-summary carry-forward
  - file-operation carry-forward

What to borrow now:

- explicit pre-model transform boundary
- compact trigger / keep-window / summary-action separation

What not to copy now:

- full session manager mechanics
- file-operation tracking as a new durable subsystem

### LangGraph

Sources reviewed:

- official docs via Context7:
  - durable execution
  - interrupts
  - thinking in LangGraph

Useful patterns:

- checkpointer enables durable execution
- interrupt/human-in-loop re-executes the node on resume
- node granularity is a resilience and observability decision
- durable execution works best when node work is deterministic and side effects are idempotent

What to borrow now:

- keep transient-vs-durable boundary explicit in app code
- do not assume the framework will auto-clear per-turn transient fields
- keep context-assembly / compact decisions observable without persisting them as truth

What not to copy now:

- full interrupt/human approval expansion for this slice

### LangChain

Sources reviewed:

- official docs:
  - short-term memory
  - prebuilt middleware
  - context editing / summarization middleware

Useful patterns:

- trim/summarize behavior sits in middleware around the model call
- summarization can use a smaller helper model
- trigger and keep policy are explicit configuration surfaces
- message deletion/trim and summary are separate operations

What to borrow now:

- keep compact trigger explicit
- keep "how much to retain" explicit
- separate summary generation from raw-message deletion

What not to copy now:

- import full LangChain middleware stack
- add generic middleware layers just to look framework-like

### Claude Agent SDK

Sources reviewed:

- official docs:
  - streaming input vs single-message mode
  - MCP integration
  - tool search
  - hooks
  - file checkpointing

Useful patterns:

- long-lived session mode is the preferred agent mode
- allowed-tool narrowing is first-class
- hooks and checkpointing are control/observability surfaces, not product truth
- checkpointing and rewind are explicitly scoped and capability-specific

What to borrow now:

- runtime control surface and durable truth surface should stay separate
- step-aware tool narrowing should remain explicit and small

What not to copy now:

- full hook runtime
- file rewind semantics

## 3. Conclusion For This Slice

The next SetupAgent implementation slice should be:

**Stage-Local Compact And Context Decision Surface**

This means:

1. keep current `working_digest` vs `compact_summary` separation
2. formalize compact as an explicit runtime decision surface
3. expose why the runtime chose full vs compact context
4. expose whether summary was reused vs rebuilt
5. keep the surface transient and observable, not persisted as product truth

## 4. Concrete Implementation Direction

### Do

- keep `SetupContextPacket -> govern_history -> runtime overlay -> final request messages` as the main transform path
- extend current compaction/governor code with explicit decision reporting
- keep deterministic compact summary as the current implementation path
- keep room for a later no-tools compact prompt strategy without redesigning the boundary
- feed context-decision artifacts into runtime result / eval / debug only

### Do Not

- redesign `FoundationEntry`
- redesign commit authority in this slice
- add a new durable state table
- persist compact decision traces into setup cognition snapshots
- replay historical tool retry process as prompt context
