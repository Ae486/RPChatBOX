# SetupAgent Architecture Optimization Handoff

> Task: `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix`
>
> Intended next owner: a new session dedicated to SetupAgent module architecture optimization.
>
> Status: handoff. Do not treat current implementation changes as completed architecture work until the new session re-plans and re-checks.

## 1. Task Theme

The real task is not a narrow setup tool bugfix. The task should be treated as:

```text
Use pi-mono and Claude Code as references, and optimize SetupAgent architecture according to this project's actual setup/runtime requirements.
```

The original symptoms were:

- SetupAgent displayed pseudo tool code such as `tool_code print(default_api...)` to the user.
- After a real setup tool call, the runtime could continue until `GRAPH_RECURSION_LIMIT`.
- Tool validation failures were not reliably repaired.
- Tool scope, provider registration, prompt guidance, and tests could drift from each other.

These symptoms point to a broader architecture issue: SetupAgent lacks a single clear agent contract spine. The architecture should be discussed and specified before further coding.

## 2. Required Pre-Reading

### pi-mono

- Python version source: `H:\Agent-Learn\pi-mono-python`
- Original/reference repo copy: `H:\chatboxapp\docs\research\pi-mono-main`

Use pi-mono as a minimal complete architecture reference:

- session boundary
- agent loop
- model call
- tool execution
- tool result
- continue/stop
- event stream

Do not copy pi-mono blindly. Use it to keep SetupAgent's core loop small and explicit.

### Claude Code

- Lightweight implementation: `H:\chatboxapp\docs\research\claude-code-from-scratch-main`
- Detailed analysis docs: `H:\chatboxapp\docs\research\how-claude-code-works-main\docs`

Use Claude Code as concrete module/function reference:

- tool lifecycle
- context engineering
- skills/prompt packs
- error repair loop
- output/tool/debug separation
- compact context and readback patterns

Do not copy coding-agent assumptions directly. This project is a creative setup/runtime agent, not a code-editing CLI.

### Current SetupAgent Code

High-signal starting points:

- `backend/rp/graphs/setup_graph_runner.py`
- `backend/rp/graphs/setup_graph_nodes.py`
- `backend/rp/agent_runtime/graph.py`
- `backend/rp/agent_runtime/executor.py`
- `backend/rp/agent_runtime/policies.py`
- `backend/rp/agent_runtime/profiles.py`
- `backend/rp/agent_runtime/tools.py`
- `backend/rp/agent_runtime/contracts.py`
- `backend/rp/services/setup_agent_execution_service.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/services/setup_context_builder.py`
- `backend/rp/services/setup_context_governor.py`
- `backend/rp/services/setup_context_compaction_service.py`
- `backend/rp/services/setup_agent_runtime_state_service.py`
- `backend/rp/tools/setup_tool_provider.py`
- `backend/rp/models/setup_workspace.py`
- `backend/rp/models/setup_stage.py`
- `backend/rp/models/setup_drafts.py`

Focused tests to inspect:

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
- `backend/rp/tests/test_setup_agent_prompt_service.py`
- `backend/rp/tests/test_setup_agent_tool_scope.py`
- `backend/rp/tests/test_setup_tool_provider.py`

Active backend specs to read before implementation:

- `.trellis/spec/backend/rp-setup-agent-loop-semantics-react-trace.md`
- `.trellis/spec/backend/rp-setup-agent-structured-output-schema-repair.md`
- `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md`
- `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md`
- `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md`
- `.trellis/spec/backend/rp-setup-agent-execution-service-outer-harness-thin-boundary.md`
- `.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`
- `.trellis/spec/backend/rp-setup-agent-strict-truth-write-tool-pilot.md`

## 3. Current Understanding

The important architectural issue is broader than tools.

Current contracts are spread across multiple places:

| Contract | Current scattered owners | Problem |
| --- | --- | --- |
| loop stop/continue | executor, graph routes, policy, profile max rounds | successful tool result can fail to stop cleanly |
| model output classification | executor, prompt, stream events | pseudo tool text can leak as assistant text |
| capability/tool exposure | profiles, tool provider, prompt, tests | prompt can point to unavailable tools |
| tool failure repair | provider error, executor, repair policy, prompt | error can become user-visible too early |
| context assembly | context builder, governor, prompt service, executor overlay | exact read obligations can be implicit |
| stage behavior | stage module, skill pack, profiles, prompt, provider | stage-specific behavior can drift |
| event visibility | executor queue, execution service stream, frontend typed SSE | internal/debug/tool text boundaries are fragile |
| runtime state | runtime state service, working digest, compact summary, loop trace | cognition/trace/workspace truth boundaries need hardening |

Recommended target spine:

```text
SetupAgentSession
  -> SetupTurnLoop
      -> SetupContextPipeline
      -> SetupCapabilityPlan
      -> ModelGateway
      -> OutputInspector
      -> SetupToolRuntime
      -> DecisionPolicy
      -> SetupEventSink
      -> SetupRuntimeStateStore
```

The core architecture principle should be:

```text
Each runtime contract has one authoritative source.
Prompt, provider schema, execution allowlist, tests, and event rendering must consume the same contract instead of hardcoding parallel versions.
```

## 4. What Was Completed In This Session

### Documentation / Planning

Created or updated task-local planning documents:

- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/prd.md`
- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/implement.jsonl`
- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-optimization-execution-plan.md`
- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-architecture-spine-spec.md`
- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-current-gap-analysis.md`
- `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-optimization-question-queue.md`

Key documented decisions:

- Current priority should be SetupAgent architecture optimization, not setup retrieval or draft CRUD.
- LangGraph may remain as execution/checkpoint/streaming substrate, but SetupAgent product semantics must live above graph topology.
- Setup lightweight retrieval is setup-owned during prestory editing; retrieval-core only consumes accepted setup truth after materialization.
- Unified draft CRUD is still a later target, but should not be mixed into the first architecture slice.
- SkillPack should remain stage-local prompt/context packaging, not the owner of business contracts.

### Implementation Attempt

An implementation subagent attempted an A1 loop-spine fix and iterated through several checks. The useful behavior direction was:

- filter pseudo tool text from assistant output
- add explicit retry-budget failure for repeated pseudo tool text
- add explicit retry-budget failure for repeated recoverable tool failure
- keep runtime max-rounds above LangGraph recursion as the business stop condition
- preserve typed SSE tool events

However, this implementation path also exposed a larger planning problem:

- Phase B `world_background` CRUD work drifted into A1.
- Tool scope, provider registration, prompt guidance, and tests drifted from each other.
- Multiple checks were needed to chase one tool-exposure inconsistency.

Conclusion: do not continue coding from this state without a fresh architecture plan/spec. Treat current implementation edits as unfinalized working-tree material, not an accepted slice.

## 5. Current Task Docs Worth Reading

Read these in order:

1. `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/prd.md`
2. `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-optimization-execution-plan.md`
3. `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-architecture-spine-spec.md`
4. `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-current-gap-analysis.md`
5. `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-optimization-question-queue.md`

The new session should probably replace or supersede parts of these with a broader SetupAgent module architecture plan.

## 6. Recommended Next Session Plan

Do not start with coding.

Recommended planning documents to create before implementation:

1. `setup-agent-module-prd.md`
   - Reframe the task as SetupAgent module architecture optimization.
2. `setup-agent-current-architecture-audit.md`
   - Current flow diagram, module responsibilities, and failure points.
3. `pi-mono-claude-code-reference-lessons.md`
   - What to borrow and what not to borrow.
4. `setup-agent-target-architecture-hld.md`
   - Target architecture and responsibility boundaries.
5. `setup-agent-contract-spine-spec.md`
   - Loop, context, capability, model gateway, output, tool runtime, decision, event, state contracts.
6. `setup-agent-implementation-slices.md`
   - Explicit phased rollout and ownership.
7. `setup-agent-test-eval-plan.md`
   - Bad-path tests, provider tests, typed SSE tests, live LLM smoke, and eval plan.
8. `setup-agent-question-queue.md`
   - Only real unresolved product/design questions.

Suggested slice order after planning:

```text
A0 Architecture/spec freeze
A1 Loop stop/repair/output boundary
A2 CapabilityPlan: one source for tools, prompt guidance, provider schema, execution allowlist
A3 ContextPipeline: handoff/draft/compact/working digest/SkillPack assembly
A4 ModelGateway + OutputInspector + EventSink hardening
A5 RuntimeStateStore / trace / visible transcript separation
B Draft CRUD migration
C Setup lightweight retrieval roadmap
D SkillPack governance
```

## 7. Constraints For The New Session

- Do not modify runtime-story-dev Q task docs, Q acceptance tests, or runtime-story implementation.
- Treat current dirty worktree carefully; do not revert or overwrite changes without explicit approval.
- Main-brain mode should plan, dispatch, review, and maintain specs. Implementation should be delegated if the same no-direct-code constraint remains active.
- Run module-level check after a coherent spec slice, not after every tiny edit.
- If a small change requires editing prompt, provider, scope, tests, and policy in parallel, treat that as evidence of a missing contract layer and update the architecture plan before coding.

## 8. Current Risk / Caution

The current task name is misleading. It says `setup-stage-tool-call-recursion-bugfix`, but the work has expanded into SetupAgent architecture.

The next session should decide whether to:

- keep this Trellis task but supersede its PRD with a broader SetupAgent architecture PRD; or
- create a new task with a clearer name, then reference this task as the investigation source.

Do not let the old bugfix framing force the next session back into tool-only patches.
