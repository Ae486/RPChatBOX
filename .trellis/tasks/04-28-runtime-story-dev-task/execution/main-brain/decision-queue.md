# Main Brain Decision Queue

Status: active
Task: `.trellis/tasks/04-28-runtime-story-dev-task`

This file tracks user decisions needed to turn the current discussion into PRD,
execution planning, and delegated implementation work. Ask one item at a time.

## Settled

### D9. Autonomous Implementation Leadership Rules

Decision:

```text
The main-brain is authorized to continue S3 and later implementation without
asking the user for confirmation, as long as requirements and engineering
direction can be determined from documents, code evidence, and assistant/reviewer
coordination.
```

Mandatory rules:

- Before production code for a coherent slice, create or update plan / PRD /
  design notes and iterate them with an assistant or reviewer.
- Use Node-1 grill docs as requirement authority and `research/modules/*` as
  the secondary implementation-reading layer.
- Use later execution docs, main-brain docs, decision log, frozen SoT, and slice
  plans as active evidence, not dead notes.
- Use Trellis implement workers for production implementation where practical.
  The main session should mainly lead, plan, verify, review, and gate rather
  than directly editing production code.
- Keep a standing assistant/reviewer lane for S3. Use it to critique plans,
  review implementation direction, and find blind spots.
- After every main-brain-defined phase milestone, dispatch a fresh reviewer that
  did not implement the change and require it to audit the new code/docs against
  Node-1/module/SoT documents.
- Reviewer findings are advisory. The main-brain must weigh them and record
  accepted, rejected, or deferred findings.
- Use glue coding: consult project patterns, `docs/research`, official docs, and
  mature framework examples when needed; borrow ideas only after reconciling
  them to project SoT.
- Use YCE for codebase search and do not use ACE. Subagent briefs must include
  this rule.
- Testing must cover unit, service, integration, regression, and review/audit
  layers as appropriate. Optional DeepSeek/live-provider smoke tests are allowed
  through existing project configuration after deterministic fake tests pass,
  with no secret exposure.
- S3 is the priority and may drive harness improvements, but only true
  cross-role mechanisms move into harness core. Memory/proposal/apply business
  policy stays outside the harness.

Ask the user only if:

- documents conflict in a way the authority order cannot resolve;
- a decision changes product behavior or delivery scope;
- implementation evidence shows a requirement is infeasible as written;
- destructive or high-risk external action is needed.

Status: settled by user instruction on 2026-06-23. Detailed rules are recorded
in `implementation-leadership-rules.md`.

### D8. S3 Remaining User Decisions

Decision:

```text
No additional product/user裁定 is currently required before S3 planning starts.
S3 requirements are sufficiently answered by the module docs and frozen SoT.
The remaining S3 choices are implementation-owned DTO/API/schema placement
decisions that must be made during S3 design and recorded, not bounced back to
the user unless implementation evidence exposes a real document conflict.
```

Basis:

- `research/modules/runtime-memory-domain-block.md`,
  `runtime-worker-family.md`, `runtime-scheduler-governance.md`,
  `runtime-orchestrator.md`, `runtime-agent-harness.md`, and
  `runtime-context-packet.md` all state `Open Questions: None`.
- Frozen acceptance oracles define S3 as:
  `D-S3-01` registry-driven five-domain memory schema,
  `D-S3-02` worker candidate -> governed apply,
  `D-S3-03` maintenance lock matrix, and
  `D-S3-04` stale base rejection.
- Freeze manifest resolves S3-adjacent open seams:
  worker stale-check authority is `base_block_revision_id`;
  proposal-review semantics and `candidate_items[]` are frozen while DTO names
  and exact field types are deferred to S3 implementation;
  `MemoryChangeEventRecord` reuses existing memory event/source/dirty-target
  contracts and is not a new truth schema.
- `seams.md` freezes the common runtime tool interface, worker result/candidate
  contract, proposal review read/write model, memory contract registry,
  writer-facing fact item, derived projection ref mapping, worker memory tool
  interface, and central reason/failure code contract.

Implementation-owned items to settle inside S3 design:

- exact DTO/class names and storage fields for proposal review read/write
  models;
- mapping or renaming between W5 policy language
  (`direct_apply_allowed`, `proposal_required`, `review_required`, `blocked`)
  and existing code enums (`REVIEW_REQUIRED`, `NOTIFY_APPLY`, `SILENT`);
- first-slice target worker/block coverage while still satisfying the full
  registry contract;
- concrete internal memory tools exposed through the common runtime tool
  interface;
- oracle/test matrix for review-required, direct-apply-allowed,
  blocked/invalid, stale base, schema invalid, and no-op.

Status: settled by docs-first audit on 2026-06-23.

### D7. S3 As Reference Implementation For Later Story Agents

Decision:

```text
S3 should act as the reference implementation for reusable story-agent runtime
mechanisms, but only the true cross-role intersection belongs in the shared
harness.
```

What may belong in the shared harness:

- model-call port and streaming normalization;
- structured output validation;
- normalized tool call/result loop;
- bounded repair/retry;
- timeout/cancellation;
- trace/event emission;
- fake model/fake tool testing;
- stable extension ports for role adapters, worker definitions, compiled
  profile, tool providers, and result ingestion.

What must stay outside the harness:

- memory/domain/block semantics;
- proposal review policy;
- Core/projection apply rules;
- writer prose policy;
- brainstorm product semantics;
- role-specific prompts, context packet selection, tool allowlists, output
  schemas, and failure policies.

Basis:

- Node-1 agent-framework docs define a shared runtime-agent harness with role /
  worker definitions and compiled runtime profile deciding enabled mechanisms.
- The same docs state that the thin harness core provides mechanisms while role
  adapters provide product policy and role-specific behavior.
- S3 is the first good proof point because memory maintenance needs structured
  output, tools, source refs, base revision checks, governance handoff, trace,
  and failure injection.

Clarification:

```text
S3 is a template for framework usage, not a reason to put S3 business policy
inside the framework.
```

Status: settled by main-brain from Node-1 agent-framework docs on 2026-06-23.

### D5. S3 First-Slice Tool Provider Scope

Decision:

```text
S3 first slice uses internal project runtime tools only.
External MCP / skill-provided tools are not part of the first memory-maintenance
vertical slice.
```

Basis:

- Node-1/W5 docs describe `MemoryMaintenanceWorker` as using Memory OS /
  retrieval / proposal / workspace tools inside runtime contracts.
- External MCP is mentioned for runtime-context/persona style workers, not as a
  requirement for the first Core memory-maintenance path.
- The first slice should prove the common runtime tool contract before adding
  external providers.

Implications:

- First-slice tools should cover scoped Core/memory reads, handle resolution,
  candidate/proposal creation, validation, and trace/debug evidence.
- MCP/skill provider support remains a later extension behind the same common
  runtime tool interface.

Status: settled by main-brain from Node-1/W5 docs on 2026-06-23.

### D3. S3 First Vertical Slice

Decision:

```text
First S3 business closure:
accepted segment
  -> post-write trigger
  -> optional orchestrator dispatch proposal
  -> scheduler-selected MemoryMaintenanceWorker
  -> internal-tool-produced structured fact/projection candidate
  -> scheduler/governance/review policy
  -> apply/debug/next-packet visibility
```

Basis:

- Node-1/W5 docs define `MemoryMaintenanceWorker` as maintaining Core
  authoritative fact content and derived_projection refs from accepted prose
  windows or brainstorm source units.
- Orchestrator proposes which workers inspect which source units; scheduler
  validates and decides actual worker execution.
- Workers emit structured candidates or no-op findings; WorkerResultIngestion /
  governance validates schema, permissions, source refs, and base revisions
  before proposal review or Core apply.

Clarification:

```text
This is the first business closure, not the full S3 requirement.
Deferred S3 behavior must be named as deferred, not silently removed.
```

Status: settled by main-brain from Node-1/W5 docs on 2026-06-23.

### D2. Minimum Base Before S3

Decision:

```text
S0/S1/S2 are the minimum production gate before S3.
Do not wait for a perfect universal story-agent framework, but do not let S3
run on an under-specified minimal harness without a gap/completion plan.
```

Implications:

- S3 starts after the minimum base is stable: setup-free harness substrate,
  turn identity/settlement/interrupt basics, scheduler/job/worker execution.
- The current harness gap must be documented before S3 implementation planning
  is treated as ready.
- Harness completion work is mandatory; S3 must not silently pile product logic
  onto the current minimal substrate.
- Generic framework mechanisms must stay separate from story-specific product
  policy.

Status: settled by user discussion on 2026-06-23.

### D4. LLM / Tool / Review Boundary

Decision:

```text
Do not over-focus on LLM permissions.
The LLM does not directly mutate external/runtime data because external
interaction is mediated through tools. Tool outputs are candidate/proposal
material that flows through scheduler / governance / review policy.
The real product decision is whether a tool-produced proposal requires human
review or may continue through scheduler/governance automatically.
```

Implications:

- Do not build a heavyweight coding-agent-style permission layer around the LLM
  itself.
- Focus S3 design on tool contracts, structured proposal output, scheduler /
  governance routing, review policy, source refs, base revisions, and trace.
- Treat writing and memory management as the central product concerns; do not
  over-model the runtime as a general-purpose computer-use/coding agent.

Status: settled by user discussion on 2026-06-23.

### D1. Old MVP Chain Position

Decision:

```text
Split old MVP handling by responsibility.
Agent execution and memory truth paths must align with the new runtime design.
Compatible control-plane, state, branch, draft/review/rewrite, and debug
mechanics may be preserved or adapted.
Legacy longform command and specialist surfaces are compatibility/adapters only.
```

Implications:

- Do not continue building new story-agent behavior inside the legacy longform
  chain as the main architecture.
- Replace or reconnect writer / orchestrator / worker / pseudo-brainstorm
  execution through the new harness direction.
- Rework memory/domain/block/proposal/apply around current S3 contracts.
- Preserve branch/checkpoint/turn identity/runtime-profile/debug mechanisms
  when they do not conflict with the new design.

Status: settled by user discussion on 2026-06-23.

### D6. Review / Direct Apply Policy

Decision:

```text
S3 first slice should implement the minimal complete governance routing instead
of only the review-required path.

The first slice must support:
1. review_required: tool/worker proposal is persisted for human/test review;
   explicit accept enters governed apply.
2. direct_apply_allowed: deterministic policy allows the proposal to continue
   through apply automatically after validation.
3. blocked / invalid: unauthorized or invalid proposal is rejected/fails closed
   with trace evidence.
```

Basis:

- Node-1/W5 docs define the permission outcome family as
  `direct_apply_allowed`, `proposal_required`, `review_required`, `blocked`.
- Existing proposal workflow already has the shape for `review_required` and
  automatic apply decisions through policy routing (`REVIEW_REQUIRED`,
  `NOTIFY_APPLY`, `SILENT`).
- Implementing only review-required would create an artificial crippled slice
  and could hide the real policy boundary that later modules need.

Clarification:

```text
This is not a heavyweight LLM permission system.
It is deterministic routing for tool-produced proposals.
```

Implementation note:

```text
Align naming between W5 docs and current code. Current code has
REVIEW_REQUIRED / NOTIFY_APPLY / SILENT; W5 docs use
direct_apply_allowed / proposal_required / review_required / blocked.
The S3 PRD must explicitly map or rename these before implementation.
```

Status: settled by user/main-brain discussion on 2026-06-23.

## Pending

None currently. Add a new item only when indexed docs are missing, conflicting,
or implementation evidence shows a real boundary that cannot be safely decided
by the main-brain.
