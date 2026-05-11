# SetupAgent Module Architecture Improve PRD

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 planning / spec freeze
>
> User decision: start with this controller PRD, then split into architecture audit, reference lessons, target HLD, contract spine, implementation slices, and test/eval plan.

## 1. Problem

SetupAgent has grown enough real runtime pieces to be useful, but its module architecture is still too implicit. The recent setup-stage tool-call recursion investigation exposed architecture-level symptoms:

- pseudo tool code can leak as visible assistant text instead of becoming a real tool call, repair path, or failure path
- successful setup tool calls can continue until LangGraph recursion limits instead of stopping through business-level loop policy
- provider/tool validation errors can be explained to the user before bounded repair is attempted
- prompt guidance, tool provider registration, runtime allowlist, policy, and tests can drift from each other
- current code has many strong local modules, but no single architecture document defines the authoritative contract spine

User clarification for this task: the original SetupAgent was already designed with Claude Code as one important inspiration. The current gap is not lack of Claude Code influence. The gap is engineering architecture: layering is too implicit, module ownership is unclear, and maintainability suffers when one conceptual change, especially a tool-related change, requires edits across multiple files and concerns.

This task reframes the old narrow bugfix into a SetupAgent module architecture improvement task.

## 2. Goal

Produce and then implement a contract-first SetupAgent architecture where every runtime responsibility has one authoritative owner:

```text
SetupAgentSession
  -> SetupTurnLoop
      -> SetupContextPipeline
      -> SetupCapabilityPlan
      -> ModelGateway
      -> OutputInspector
      -> SetupToolRuntime
      -> turn transition rules
      -> SetupEventSink
      -> SetupRuntimeStateStore
```

`turn transition rules` are small rules owned by `SetupTurnLoop`, not a larger standalone `DecisionPolicy` layer. This correction prevents the architecture work from becoming another patch-shaped policy object.

The architecture must make SetupAgent reliable enough to serve as the reference creative-agent loop for setup and later RP runtime agents.

## 3. Reference Source Roles

| Source | Role in this task | What to avoid |
| --- | --- | --- |
| `H:/Agent-Learn/pi-mono-python` and `docs/research/pi-mono-main` | Learn the optimal minimal agent layering: session, state, events, loop, model stream, tool execution, tool result, continue/stop | Do not copy coding-agent-specific features or replace the current runtime stack |
| `docs/research/claude-code-from-scratch-main` and `docs/research/how-claude-code-works-main/docs` | Learn mature module/function design: tool lifecycle, permissions, context compression, memory/skills, subagents, transcript and output separation, repair and retry behavior | Do not transfer file-editing CLI assumptions directly into a creative setup agent |
| OpenAI / Anthropic / LangGraph / LangChain primary docs and local source evidence | Learn mature provider, tool-calling, tracing, eval, structured-output, graph/checkpoint, and agent-loop implementation patterns when they are relevant to this task | Do not rely on memory, blog paraphrase, or non-primary engineering articles for concrete claims; use official/current primary sources or local source evidence before writing specific architecture decisions |
| Current SetupAgent specs and code | Requirement truth for project behavior, product contracts, setup drafts, review/commit/readiness, typed SSE, runtime cognition, context governance, and stage lifecycle | Do not let external references override frozen project contracts silently |

## 4. Authority Order

When sources disagree, use this order:

1. Current user decisions in this task.
2. Active executable setup specs under `.trellis/spec/backend/`.
3. Current SetupAgent implementation and tests as requirement/migration evidence, not automatic architecture authority.
4. Old `05-09` task docs as investigation input, not final authority.
5. Claude Code as mature function/module reference.
6. pi-mono as minimal architecture layering reference.
7. OpenAI / Anthropic / LangGraph / LangChain primary docs or local source evidence for provider, tracing, eval, structured output, graph, and agent-loop mechanisms.

Reference adoption rule: if a concern is not a current-product special requirement and pi-mono, Claude Code, or other mature primary references point to a clear implementation pattern, prefer learning/adapting that mature pattern over preserving the current accidental SetupAgent shape. Current code proves the project needs a capability; it does not prove the current implementation is the right module boundary.

External-reference rule: A0 does not require network research. If local task docs, current code/specs, `pi-mono`, and local Claude Code references answer a question, prefer those sources. Use network only when a future implementation spec depends on concrete provider/framework behavior that local evidence cannot answer, and then cite primary/current docs rather than secondary articles.

Any change that would alter `SetupWorkspace`, review/commit/readiness, typed SSE event taxonomy, stage handoff truth, or setup draft write semantics must become an explicit spec decision before implementation.

## 5. Non-Goals

- Do not modify runtime-story Q docs, Q acceptance tests, or runtime-story implementation in this task.
- Do not start by coding over the old `05-09` implementation attempt.
- Do not rewrite SetupAgent into pi-mono, Claude Code, LangGraph-free architecture, or a new framework.
- Do not expand setup retrieval, full draft CRUD migration, SkillPack governance, model config sync, or dialogue persistence until the architecture spine plan says they are in-scope for a later slice.
- Do not treat prompt-only tuning as the durable fix for tool-call, repair, or stop-policy failures.

## 6. Current Frozen Project Contracts

The new architecture must preserve and explain these existing contracts:

- Outer setup harness and inner turn loop remain separate.
- LangGraph may remain the execution/checkpoint/streaming substrate, but graph node names are not the product architecture.
- `SetupWorkspace` remains business truth.
- Runtime cognition, `loop_trace`, `continue_reason`, and `context_report` remain transient unless an explicit spec changes that.
- `SetupAgentExecutionService` stays a thin outer harness, not a second runtime core.
- Pre-model context assembly stays layered: context packet, governed history, runtime adapter bundle, runtime request assembly.
- Context compaction is stage-local and does not replace draft truth.
- Tool scope is turn-level allowlist state, not MCP registry truth.
- SkillPack is stage-local prompt prose and does not own tool scope or business contracts.
- Structured tool validation errors stay machine-readable and bounded repair remains deterministic.
- Typed SSE tool events remain visible; internal debug/pseudo tool text must not become assistant content.

## 7. A0 Deliverables

A0 is complete only when these planning documents exist and agree with each other:

1. `setup-agent-module-prd.md`
   - this controller PRD
   - defines task scope, source roles, authority order, non-goals, and A0 acceptance
2. `research/setup-agent-current-architecture-audit.md`
   - current flow diagram
   - module responsibility map
   - failure points and drift points
3. `research/pi-mono-claude-code-reference-lessons.md`
   - pi-mono minimal layering lessons
   - Claude Code mature module/function lessons
   - what this project should not copy
4. `research/setup-agent-architecture-grill-decisions.md`
   - persisted `$grill-me` architecture decisions
   - confirmed boundaries for runtime core vs setup shell, CapabilityPlan, ToolProvider, OutputInspector, EventSink, and TurnLoop
   - corrected direction that A1 should rebuild the SetupTurnLoop state-machine boundary instead of adding another patch policy layer
5. `research/setup-agent-architecture-grounding-matrix.md`
   - current problem -> reference design -> project landing matrix
   - proves target HLD is grounded in current SetupAgent code and pi-mono / Claude Code references
   - identifies when future `$grill-me` or primary external docs are required
6. `research/setup-agent-target-architecture-hld.md`
   - target architecture
   - module boundaries
   - data/control/event flow
7. `research/setup-agent-contract-spine-spec.md`
   - loop, context, capability, model gateway, output inspector, tool runtime, decision, event, and state contracts
8. `research/setup-agent-implementation-slices.md`
   - phased rollout from A1 onward
   - owned files, forbidden files, tests, and check cadence per slice
9. `research/setup-agent-test-eval-plan.md`
   - bad-path tests
   - provider/gateway tests
   - typed SSE tests
   - opt-in live model smoke and eval plan
10. `research/setup-agent-question-queue.md`
   - only real product/design questions that cannot be answered from code/docs/reference projects

## 8. Implementation Slice Direction

Expected order after A0:

```text
A1 Loop stop / repair / output boundary
A2 CapabilityPlan: one source for tools, prompt guidance, provider schema, execution allowlist
A3 ContextPipeline: handoff, draft, compact, working digest, SkillPack assembly
A4 ModelGateway + OutputInspector + EventSink hardening
A5 RuntimeStateStore / trace / visible transcript separation
B  Draft CRUD migration
C  Setup lightweight retrieval roadmap
D  SkillPack governance
```

Each slice must be coherent enough to verify end-to-end, then run module-level `trellis-check` before the next slice starts.

## 9. A0 Acceptance Criteria

- The task has a controller PRD and curated implement/check context.
- The new task clearly supersedes the old bugfix framing without deleting or rewriting old `05-09` evidence.
- The architecture plan distinguishes:
  - minimal framework lessons from pi-mono
  - mature module/function lessons from Claude Code
  - project-specific setup requirements from current specs/code
- Every proposed target module maps to current code or a justified new boundary.
- All unresolved product/design questions are either answered from evidence or placed into the question queue for one-at-a-time `$grill-me`.
- No backend/frontend implementation code is changed during A0 planning.

## 10. Current A0 Status

A0 planning docs are now expected to be complete when all files listed in section 7 exist and are registered in `implement.jsonl` / `check.jsonl`.

Before backend/frontend implementation starts:

1. validate the task context
2. run a docs-slice `trellis-check`
3. confirm no blocking `$grill-me` item remains in `research/setup-agent-question-queue.md`
4. start A1 from `research/setup-agent-implementation-slices.md`
