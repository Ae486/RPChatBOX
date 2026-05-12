# SetupAgent Target Architecture HLD

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 target architecture draft
>
> Inputs:
>
> - `setup-agent-module-prd.md`
> - `research/setup-agent-current-architecture-audit.md`
> - `research/pi-mono-claude-code-reference-lessons.md`
> - `research/setup-agent-architecture-grill-decisions.md`
> - `research/setup-agent-architecture-grounding-matrix.md`
> - old handoff: `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix/research/setup-agent-architecture-handoff-for-new-session.md`

## 1. Executive Direction

The SetupAgent architecture improvement is not a rewrite and not a narrow bugfix. It is a contract-spine cleanup:

```text
current code proves what the product needs
current code does not prove the current boundaries are good

mature references prove better agent architecture patterns
mature references do not override setup-specific product contracts
```

The target architecture keeps the existing product semantics:

- `SetupWorkspace` remains business truth.
- Setup stages/steps, drafts, review, commit, readiness, and activation handoff stay setup-owned.
- Typed SSE remains the app-visible runtime transport.
- LangGraph may remain the checkpoint/streaming substrate.
- Tool calls remain standard model tool calls, not a custom setup DSL.

The main change is ownership clarity. A future setup-agent change should be able to answer:

```text
What concept is changing?
Which module owns the concept?
Which contract and tests protect it?
Which adjacent layers must not be edited for this change?
```

If a tool-related fix still requires hand-editing prompt prose, profile constants, provider schema, executor routing, allowlist filtering, event visibility, and tests independently, the architecture has not improved.

## 2. Product Semantics Extraction Rule

Existing SetupAgent code can be messy, but it is still the best local evidence for product semantics.

For this task, read current code in two passes:

| Question | Use current code as | Example |
| --- | --- | --- |
| What product behavior must exist? | Requirement evidence | Tool validation failure should become a machine-readable observation that the agent can repair from. |
| Where should that behavior live architecturally? | Migration evidence only | A pile of executor `if` branches does not mean executor should own every future repair rule. |

The user-provided example becomes a target rule:

```text
If a setup tool call fails with a recoverable structured error,
the agent should normally receive the error as an observation and retry within a bounded loop.
It should not immediately explain the internal failure to the user and stop,
unless the bounded repair policy says the failure is terminal or user input is required.
```

That rule is product semantics. The current local implementation may express it through scattered fallback branches. The target architecture expresses it through:

```text
SetupToolRuntime structured error
  -> SetupTurnLoop observation
  -> transition rule: recoverable_tool_failure
  -> ModelGateway next call with observation
  -> OutputInspector
  -> retry / ask user / terminal failure
```

This is the key distinction for the whole task: extract the real requirement from the existing code, then land it in the owner that pi-mono / Claude Code style architecture would use.

## 3. Target Architecture Overview

Target architecture:

```text
SetupAgentSession
  -> SetupContextPipeline
  -> SetupCapabilityPlan
  -> SetupTurnLoop
      -> ModelGateway
      -> OutputInspector
      -> SetupToolRuntime
      -> transition rules
      -> SetupEventSink
      -> SetupRuntimeStateStore
```

Important correction:

```text
SetupTurnLoop owns the state machine.
Small policy/rule helpers may exist, but there should not be a larger standalone DecisionPolicy god object.
```

The old handoff's spine listed `DecisionPolicy` as a module. This HLD refines that into "transition rules inside the loop contract" because the user's concern was correct: another giant policy layer would be another patch surface unless it is subordinate to a clean loop state machine.

## 4. Module Boundaries

| Module | Owns | Must not own | Current landing |
| --- | --- | --- | --- |
| `SetupAgentSession` | Request/session boundary, workspace preflight, provider selection, stream setup, outer setup lifecycle | Inner model/tool repair logic, stage business mutation internals | `SetupGraphRunner`, `SetupGraphNodes`, `SetupAgentExecutionService` |
| `SetupContextPipeline` | Business truth packet -> governed history -> compact summary / working digest / retained tool outcomes -> prompt / SkillPack -> model-ready input | Tool exposure decisions, provider schema compatibility, workspace mutation | `SetupContextBuilder`, governor, compaction service, runtime adapter, prompt service |
| `SetupCapabilityPlan` | Stage/step/turn capability package: model-visible tools, runtime allowlist, prompt guidance, candidate exclusion, snapshot expectations | Tool execution, pydantic business schemas, workspace mutation | `profiles.py`, runtime adapter, tool registry view, prompt service, tool-scope tests |
| `SetupTurnLoop` | One user-turn state machine: model call, inspect output, execute tools, observe results, retry/repair/finalize/stop | Workspace business truth, provider transport internals, typed SSE serialization details | `RpAgentRuntimeExecutor`, `agent_runtime/graph.py`, `agent_runtime/state.py` |
| `ModelGateway` | Provider request construction, schema adaptation, streaming/non-stream normalization, provider error attribution, usage capture | Business repair decisions, stage-specific tool exposure | executor request/call/stream helpers |
| `OutputInspector` | Classify normalized model output before tool runtime or transcript visibility | Tool execution, final business decisions, event serialization | `_inspect_model_output(...)`, pseudo-tool detectors |
| `SetupToolRuntime` | Runtime allowlist enforcement, tool argument validation handoff, deterministic tool execution, structured result/error observation | Model-visible exposure policy, prompt guidance authority | `RuntimeToolExecutor`, `RuntimeToolRegistryView`, `SetupToolProvider` |
| `SetupEventSink` | Runtime event taxonomy and user-visible transcript boundary | Business state mutation, output classification | `RuntimeEvent`, `TypedSseEventAdapter`, executor event queue, stream service |
| `SetupRuntimeStateStore` | Runtime cognition, working digest, retained outcomes, compact summary, loop trace, finish/continue reasons | `SetupWorkspace` business truth | `SetupAgentRuntimeStateService` and structured runtime payload |

## 5. Dependency Direction

Allowed high-level direction:

```text
SetupAgentSession
  depends on SetupContextPipeline, SetupCapabilityPlan, SetupTurnLoop

SetupTurnLoop
  depends on ModelGateway, OutputInspector, SetupToolRuntime, SetupEventSink, SetupRuntimeStateStore

SetupCapabilityPlan
  selects ToolProvider definitions but does not execute them

SetupToolRuntime
  calls SetupToolProvider but does not decide stage visibility

SetupEventSink
  consumes classified loop events but does not classify raw model output
```

Forbidden direction:

```text
Prompt prose opens tools.
Provider registration opens tools.
ToolProvider decides current stage visibility.
Event serialization decides business failure.
Output regex directly mutates workspace truth.
LangGraph node names become product architecture.
Runtime trace becomes business truth by default.
```

## 6. Data And Control Flow

### 6.1 Request / Session Flow

```text
Setup API / caller
  -> SetupAgentSession
      -> resolve workspace and current setup stage/step
      -> resolve provider/model
      -> prepare stream/non-stream boundary
      -> build context pipeline input
      -> build capability plan input
      -> call SetupTurnLoop
```

`SetupAgentSession` is deliberately an outer harness. It should coordinate setup lifecycle and runtime launch, not become a second agent runtime core.

### 6.2 Context And Capability Flow

```text
SetupWorkspace business truth
  -> SetupContextPipeline
      -> context packet
      -> governed history
      -> compact summary
      -> working digest
      -> retained tool outcomes

current stage / step / turn constraints
  -> SetupCapabilityPlan
      -> model-visible tool schemas
      -> prompt guidance fragments
      -> runtime execution allowlist
      -> candidate exclusion
      -> capability snapshot metadata

SetupContextPipeline final assembly
  -> consumes CapabilityPlan prompt guidance fragments
  -> assembles prompt / SkillPack / runtime overlay
  -> emits model-ready context bundle
```

The pipeline and capability plan are adjacent, but they are not the same:

- ContextPipeline says what the model needs to know.
- CapabilityPlan says what the model is allowed and expected to do.
- Final prompt assembly must consume the active CapabilityPlan; it must not independently mention or imply tools outside the plan.

### 6.3 Standard Tool-Calling Flow

Tool calls remain normal provider/model tool calls:

```text
CapabilityPlan selects active tools
  -> ModelGateway injects active tool schemas into provider request
  -> model emits standard tool call
  -> ModelGateway normalizes tool call block
  -> OutputInspector classifies it as real_tool_call
  -> SetupTurnLoop routes to SetupToolRuntime
  -> SetupToolRuntime checks runtime allowlist
  -> SetupToolProvider validates and executes
  -> structured tool result/error becomes observation
  -> SetupTurnLoop continues or stops by transition rule
```

CapabilityPlan does not replace this chain. It only keeps the exposed schema, prompt guidance, allowlist, and tests aligned.

### 6.4 Event And State Flow

```text
SetupTurnLoop transition
  -> SetupEventSink typed event
      -> user-visible SSE if public
      -> internal log/eval/trace if private

SetupTurnLoop transition
  -> SetupRuntimeStateStore
      -> runtime cognition / digest / trace / outcome state
      -> never overwrite SetupWorkspace business truth unless a setup tool did so deterministically
```

## 7. SetupTurnLoop State Machine

The target loop is a state machine, not a collection of scattered post-hoc guards.

```text
START_TURN
  -> BUILD_INPUT
  -> CALL_MODEL
  -> INSPECT_OUTPUT
  -> one of:
       EXECUTE_TOOL
       FINALIZE_TEXT
       REPAIR_OUTPUT
       ASK_USER
       FAIL_STRUCTURED
  -> OBSERVE_TOOL_RESULT
  -> CALL_MODEL or FINALIZE_TEXT or FAIL_STRUCTURED
  -> END_TURN
```

Transition table:

| Inspector / runtime result | Loop transition | User-visible behavior |
| --- | --- | --- |
| `real_tool_call` and tool allowed | execute tool, emit typed tool event, append observation | tool activity event, not raw tool args as assistant prose |
| `real_tool_call` but tool not allowed | structured blocked-tool observation or terminal policy failure | no raw provider stack; possible concise warning if terminal |
| recoverable structured tool error | append error observation and retry within budget | normally no immediate user-facing failure text |
| non-recoverable tool error | terminal structured failure or ask user if user action is required | concise visible explanation only after loop decides terminal/user-required |
| normal assistant text with obligations satisfied | finalize assistant text | natural assistant response |
| normal assistant text but tool/read/write obligation unmet | repair or ask user depending on obligation type | no false completion |
| pseudo tool text | filtered from assistant content, repair transition | no pseudo tool code visible |
| malformed tool call | repair transition if recoverable; else structured failure | no raw validation stack trace visible |
| empty output | retry/repair or structured provider failure | no blank assistant content |
| provider/schema/stream error | ModelGateway-attributed failure, then retry/fail by transition rule | provider failure is not mislabeled as setup business judgment |

Bounded retry is a loop invariant. It is not an excuse for infinite repair:

```text
Every repair transition must carry:
  reason code
  retry budget key
  observation shown to the model if retrying
  public/private event visibility
  terminal finish_reason if exhausted
```

## 8. OutputInspector Boundary

`OutputInspector` is the formal boundary between provider output and all downstream surfaces.

It classifies:

- `real_tool_call`
- `normal_text`
- `pseudo_tool_text`
- `malformed_tool_call`
- `empty_output`
- `provider_schema_error`
- `mixed_text_and_tool_call`

It returns a typed inspect result, not a pile of executor update dictionaries.

Minimum typed result shape:

```text
classification
assistant_text_public_candidate
tool_calls
private_diagnostics
repair_observation
finish_reason_candidate
continue_reason_candidate
```

Ownership rules:

- OutputInspector may detect pseudo tool text using regex or structural heuristics, but regex is not the architecture.
- OutputInspector may mark text as not public, but EventSink decides final event visibility.
- OutputInspector does not execute tools.
- OutputInspector does not write `SetupWorkspace`.
- OutputInspector should not decide every business transition; it produces loop input.

## 9. SetupCapabilityPlan Boundary

`SetupCapabilityPlan` is the single tool-surface spine.

Assembly order:

```text
stage defaults
  -> step overrides
  -> turn/runtime safety filters
  -> final capability package
```

Final capability package includes:

- stage and step identity
- active tool names
- model-visible schema mode per tool
- runtime allowlist
- prompt guidance fragments
- candidate tool exclusions
- expected public event behavior
- snapshot-test metadata

CapabilityPlan owns exposure, not execution:

```text
ToolProvider owns schema/validation/execution/result payloads.
CapabilityPlan selects what is visible and allowed this turn.
```

Drift rules:

| Drift | Expected outcome |
| --- | --- |
| prompt mentions tool not exposed in schema | test failure |
| schema exposed but runtime allowlist rejects in normal path | test failure |
| provider registers candidate tool but plan does not expose it | valid fail-closed state |
| candidate tool appears in prompt/schema/allowlist before accepted slice | test failure |
| stage guidance needs a tool but plan excludes it | check warning or focused test failure |

This directly addresses the tool pain point: changing a tool should first update the capability contract, then the owned implementation surfaces follow that contract.

## 10. SetupToolRuntime Boundary

`SetupToolRuntime` owns deterministic execution.

Flow:

```text
RuntimeToolCall
  -> allowlist check from CapabilityPlan
  -> provider lookup
  -> pydantic/model validation
  -> business validation
  -> workspace read/mutation
  -> structured result/error serialization
  -> loop observation
```

Structured errors are not automatically user-visible failures. They are first model observations and loop transition inputs.

Error shape should support:

- code
- message
- retryable flag
- failure origin
- repair strategy
- required fields or blocked values
- public-safe summary if terminal
- private diagnostics for logs/eval

This matches current `SetupToolProvider` strengths while moving retry/repair ownership out of ad hoc local branches.

## 11. ModelGateway Boundary

`ModelGateway` owns provider compatibility.

It should eventually isolate:

- model message assembly after ContextPipeline output
- active tool schema conversion
- slim/full/provider-compatible schema adaptation
- streaming delta normalization
- tool-call block reconstruction
- provider error classification
- usage accounting
- tracing/span metadata hooks

The immediate A0/A1 requirement is conceptual: provider transport failures and tool schema incompatibilities must not be hidden inside generic loop failure or prompt folklore.

Concrete OpenAI / Anthropic claims should be checked against current primary docs before implementation specs cite exact API behavior.

## 12. SetupEventSink Boundary

`SetupEventSink` owns user-visible transcript safety.

Public surfaces:

- natural assistant text that the loop has finalized
- typed tool activity events
- public-safe warnings
- final state / completion metadata

Private surfaces:

- pseudo tool code
- raw provider deltas
- repair observations not intended for the user
- debug JSON
- raw stack traces
- LangGraph recursion/internal error text
- full validation internals

Private data may go to:

- `loop_trace`
- diagnostics/eval records
- Langfuse spans
- server logs

It must not become assistant content.

This is where Claude Code's output separation maps to this app: do not copy terminal UI rendering, copy the discipline that text, tool use, tool result, internal trace, and UI event are separate surfaces.

## 13. Runtime State And Truth Levels

Truth levels:

| Level | Owner | Example | Persistence meaning |
| --- | --- | --- | --- |
| Business truth | `SetupWorkspace` and setup draft models | draft blocks, review state, commit state, readiness | authoritative product state |
| Runtime cognition | `SetupRuntimeStateStore` | working digest, cognitive summary, retained outcomes | runtime aid, can be invalidated/rebuilt |
| Loop trace | `SetupTurnLoop` result/debug/eval surface | continue reasons, repair attempts, inspector classification | transient diagnostic/eval evidence; not persisted as setup governance snapshot under current specs |
| Event transcript | `SetupEventSink` | assistant text, typed tool events | user-visible communication history |
| Provider diagnostics | `ModelGateway` / logs | raw provider error, stream parse issue | private debugging / observability |

Invariant:

```text
Runtime cognition and trace can explain or guide setup behavior.
They do not become setup truth unless a setup tool or explicit product contract promotes them.
```

## 14. Reference-Derived Vs Project-Specific

| Target choice | Source |
| --- | --- |
| Small session/context/loop/tool/event vocabulary | pi-mono minimal architecture |
| Loop shape: model -> inspect -> tool -> observation -> continue/stop | pi-mono and Claude Code convergence |
| Active tool filtering with fail-closed defaults | Claude Code tool system |
| Tool as full capability surface, not just callable | Claude Code mature module design |
| Output separation before transcript/UI | Claude Code mature transcript/tool-result separation |
| Context as pipeline before model call | pi-mono context transform + Claude Code context engineering |
| `SetupWorkspace`, drafts, review/commit/readiness | current SetupAgent product contract |
| stage/step capability package | current setup product semantics + Claude Code active tools |
| typed SSE app transport | current project contract |
| LangGraph as substrate, not vocabulary | current implementation constraint |

## 15. What Not To Copy

Do not copy:

- pi-mono's generic state model in place of `SetupWorkspace`.
- pi-mono's simpler loop without setup repair/completion/readiness obligations.
- Claude Code's file-editing permission model directly into setup draft mutation.
- Claude Code's terminal UI rendering.
- Claude Code's full tool breadth or subagent system in A1/A2.
- Any provider/framework pattern from memory without checking primary/current docs when it becomes a concrete implementation claim.

Do copy/adapt:

- pi-mono's small readable architecture vocabulary.
- Claude Code's active capability filtering and fail-closed tool defaults.
- Claude Code's separation of assistant text, tool calls, tool results, internal trace, and UI/transcript.
- Mature provider/framework patterns when they solve a local boundary problem and do not erase setup product semantics.

## 16. Current Code Mapping

| Target module | Current code to migrate from | Main problem to fix |
| --- | --- | --- |
| `SetupAgentSession` | `setup_graph_runner.py`, `setup_graph_nodes.py`, `setup_agent_execution_service.py` | Document thin harness boundary and keep inner loop out |
| `SetupContextPipeline` | context builder, governor, compaction, adapter, prompt service | One named pipeline contract for packet/history/digest/prompt |
| `SetupCapabilityPlan` | `profiles.py`, adapter scope key, registry view, prompt hints, tests | Single spine for schema/prompt/allowlist/snapshot |
| `SetupTurnLoop` | `agent_runtime/executor.py`, `agent_runtime/graph.py`, `agent_runtime/state.py` | Replace patch-shaped control with explicit state-machine transitions |
| `ModelGateway` | executor model request/call/stream helpers | Normalize provider output/errors before policy logic |
| `OutputInspector` | `_inspect_model_output(...)`, pseudo-tool helper | Classify output before tool runtime or transcript visibility |
| `SetupToolRuntime` | `RuntimeToolExecutor`, `SetupToolProvider` | Keep deterministic validation/execution; return structured observations |
| `SetupEventSink` | executor event queue, `TypedSseEventAdapter`, execution-service stream path | Make transcript visibility a backend contract |
| `SetupRuntimeStateStore` | runtime state service, structured payload | Keep runtime cognition separate from workspace truth |

## 17. A1 / A2 Implications

### A1: Loop Stop / Repair / Output Boundary

A1 should prove the new loop state-machine contract is real.

A1 may use the existing profile/tool-scope path as the provisional capability source. It should not block on a full `SetupCapabilityPlan` extraction, and it should not change accepted tool exposure except to preserve current active-spec behavior.

In scope:

- `OutputInspector` contract.
- pseudo tool text classification and non-visibility.
- recoverable tool failure as structured observation and bounded retry.
- terminal business stop before graph recursion limit.
- typed event preservation.
- finish/continue reason taxonomy cleanup where required by the loop contract.

Out of scope:

- exposing `setup.world_background.*`
- full draft CRUD migration
- setup retrieval roadmap
- prompt-only fix as final solution
- subagent capability

### A2: CapabilityPlan Tool-Surface Spine

A2 should make tool exposure maintainable.

In scope:

- stage defaults + step overrides + turn safety filters.
- schema/prompt/allowlist snapshot contract.
- candidate tool fail-closed assertions.
- prompt guidance derived from active capability package.
- provider registration separated from model exposure.
- active-spec shared/read tool retention, including `setup.read.draft_refs`.

Out of scope:

- moving business validation into CapabilityPlan.
- duplicating pydantic schemas.
- changing setup product semantics merely to match a reference project.
- dropping active shared/read tools such as `setup.truth.write`, question/commit/read helpers, or `setup.read.draft_refs` without first changing the authoritative backend spec.

### C: Setup Lightweight Retrieval Roadmap

C should freeze ownership, not add RAG to SetupAgent.

In scope:

- setup-owned exact readback for current editable draft refs through `setup.read.draft_refs`;
- compact-summary recovery hints that point to setup draft refs instead of carrying full draft detail in prompt context;
- prior-stage handoff refs as setup-owned accepted-truth pointers;
- committed setup truth lookup through `SetupTruthIndexService`;
- lexical/path/filter candidate search through `setup.truth_index.search`;
- bounded exact committed-truth reads through `setup.truth_index.read_refs`;
- deterministic post-commit handoff from accepted setup truth into retrieval seed sections.

Out of scope:

- semantic/vector retrieval inside SetupAgent;
- Memory OS / Recall retrieval as a draft-recovery mechanism;
- hybrid search, reranking, active-story retrieval policy, or runtime story retrieval;
- new model-visible retrieval tools that bypass `SetupCapabilityPlan`;
- making retrieval-core readiness block setup stage commit/progression.

Architecture boundary:

```text
SetupAgent prestory editing
  owns draft refs, compact recovery, handoff refs, truth-index search/read

Accepted setup commit
  is deterministically materialized into seed sections

Retrieval-core
  owns chunking, indexing, embeddings, hybrid/rerank, Recall/Archival search,
  and active-story runtime retrieval after materialization
```

This follows the reference direction without copying extra feature breadth:

- pi-mono keeps context and tools as selected loop inputs instead of folding every external store into the core loop.
- Claude Code treats context engineering, memory/readback, active tool pools, and tool-result reinjection as explicit boundaries.
- SetupAgent adapts those patterns to the project-specific rule that editable setup draft truth is setup-owned and semantic/runtime retrieval starts after accepted setup truth is materialized.

### D: SkillPack Governance

D closes the remaining prompt-pack boundary after A2 CapabilityPlan and A3
ContextPipeline are already explicit.

In scope:

- treat SkillPack as stage-keyed prompt/context packaging inside
  `SetupContextPipeline` stable prompt assembly;
- select a pack deterministically from the resolved `SetupStageId`;
- hard-unload by rebuilding the next turn prompt from the newly resolved stage;
- surface `skill_pack_name` only as transient observability metadata on turn
  input, runtime result structured payload, observation metadata, and eval trace
  root attributes;
- keep tests proving prompt changes do not change `SetupCapabilityPlan`,
  `tool_scope`, runtime allowlist, or `setup.truth.write` injection.

Out of scope:

- LLM-selected or heuristic SkillPack activation;
- SkillPack-owned tool permission, business validation, setup truth, runtime
  overlay, `context_bundle`, durable runtime state, or stage CRUD semantics;
- expanding the SkillPack content library as part of architecture governance.

Reference rationale:

- pi-mono supports this by keeping context transformation explicit before model
  input assembly instead of letting prompt-pack material leak into loop state.
- Claude Code supports this by making context/skill/memory injection observable
  and bounded, while keeping tool permission semantics on the active tool pool
  side rather than inside skill prose.
- SetupAgent adapts those patterns narrowly: the pack may shape facilitation
  voice and stage-local prose, but capability and business truth remain owned by
  the existing setup contracts.

## 18. Acceptance Questions For Later Specs

The contract spine and implementation slices should be judged by these questions:

1. If a tool is added, is there one capability owner to update first?
2. If a tool fails recoverably, does the model receive a structured observation before the user sees a terminal failure?
3. If the model emits pseudo tool text, can it ever become assistant content?
4. If a provider stream malforms a tool call, is the failure attributed at ModelGateway / OutputInspector rather than business logic?
5. If prompt guidance mentions a tool, can tests prove schema and allowlist agree?
6. If a turn ends, can we distinguish natural final text, ask-user, repair-exhausted, provider failure, and business completion?
7. If runtime cognition drifts, can it be rebuilt without corrupting `SetupWorkspace`?
8. If LangGraph routing changes, does the architecture language still make sense?
9. If setup needs exact detail after compaction, does it use setup-owned readback rather than retrieval-core?
10. If accepted setup truth enters retrieval, is the bridge deterministic post-commit materialization rather than an agent-authored rewrite?
11. If a SkillPack is active, can tests prove it changed only stable prompt
    packaging and observability metadata, not capability, tool scope, truth
    write injection, runtime overlay, context bundle, or durable setup truth?

## 19. Open Design Questions

No blocking `$grill-me` question remains before writing the next A0 documents.

Future legitimate questions:

1. Should `SetupCapabilityPlan` become an explicit code object in A2, or first be consolidated behind existing `profiles.py` / adapter boundaries?
2. What is the smallest A1 code slice that proves the state-machine boundary without premature file reorganization?
3. Which existing policy classes become small transition rules, and which should be removed as patch artifacts?
4. Which tool families remain candidate-only until a separate product/tool slice explicitly accepts them?
5. Which provider-specific schema/tool-call details require OpenAI / Anthropic primary-doc confirmation before implementation?

Reference adoption guard:

- `pi-mono` and Claude Code are local architecture references, not frameworks to import or rewrite into.
- LangGraph remains the current substrate unless an explicit future slice proves a replacement is required.
- LangChain or provider SDK patterns may be adopted only for a concrete local need and only after primary/current docs or source evidence are checked.
- Secondary engineering articles are non-authoritative background; do not use them to settle provider/tool-calling semantics.

## 20. HLD Conclusion

The target architecture is:

```text
SetupAgent-specific product shell
  preserves setup truth, drafts, review, commit, readiness, typed SSE

project-level agent runtime core
  owns loop, model gateway, output inspection, capability exposure,
  tool runtime interface, events, runtime state, and trace contracts
```

The most important implementation discipline is not "move files first". It is:

```text
contract spine first
tests around ownership second
file extraction only where ownership remains scattered
```

This directly addresses the user's core concern: SetupAgent can keep the needed product behaviors found in current code while replacing scattered fallback logic with clear agent-loop, tool-surface, output, and event boundaries learned from pi-mono and Claude Code.
