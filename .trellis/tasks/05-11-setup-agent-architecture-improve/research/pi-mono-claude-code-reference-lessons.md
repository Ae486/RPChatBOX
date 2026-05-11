# pi-mono / Claude Code Reference Lessons For SetupAgent

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 reference extraction
>
> Purpose: extract only the architecture lessons that should shape SetupAgent module boundaries. This is not a source-code porting plan.

## 1. User Clarification Captured

The original SetupAgent work already used Claude Code as a design inspiration. The current problem is not that Claude Code is a poor reference. The problem is that this project's implementation has accumulated unclear layering, weak module ownership, and maintainability friction.

The clearest symptom is the tool surface. A tool-related change can require coordinated edits across profile constants, runtime adapter scope, provider registration, prompt hints, execution filtering, and tests. That means the feature exists, but the architecture does not yet provide a single ownership spine for it.

Therefore, this task uses the references with different roles:

| Reference | Primary value for this task | Not the goal |
| --- | --- | --- |
| pi-mono | Minimal and clean agent framework layering. Use it to recover the smallest understandable skeleton: session state, loop, context transform, model stream, tool execution, events, continue/stop. | Do not replace SetupAgent with pi-mono or copy its generic coding-agent assumptions. |
| Claude Code | Mature feature/module design. Use it to learn concrete designs for tools, permissions, context compression, output separation, memory/skills, subagents, retries, and observability. | Do not assume that copying Claude Code-style feature richness will fix this project's ownership drift. |
| Current SetupAgent | Product truth and migration truth. Use specs/code/tests to preserve setup drafts, review/commit/readiness, typed SSE, runtime cognition, and stage lifecycle. | Do not let external references override frozen RP setup contracts silently. |

Additional user clarification: for concerns that are not current-product special requirements, mature reference designs and implementations are allowed to be adapted directly. pi-mono and Claude Code are primary local references; OpenAI, Anthropic, LangGraph, and LangChain primary docs or local source evidence may also be used where they provide clear implementation guidance. The project should not preserve a weaker local implementation merely because it already exists.

Reference guard: secondary engineering articles are non-authoritative background. Do not use them to settle concrete provider, tool-calling, streaming, structured-output, graph, or framework behavior.

## 2. pi-mono Lessons: Minimal Agent Architecture

Source files reviewed:

- `H:/Agent-Learn/pi-mono-python/packages/agent/src/pi_agent/agent.py`
- `H:/Agent-Learn/pi-mono-python/packages/agent/src/pi_agent/agent_loop.py`
- `H:/Agent-Learn/pi-mono-python/packages/agent/src/pi_agent/types.py`

pi-mono's useful lesson is not the amount of functionality. It is the small number of concepts that explain the whole runtime.

### 2.1 Stateful Session Wrapper Is Separate From Loop Logic

`Agent` owns session state, public commands, queues, cancellation, event subscription, and state mutation. It does not inline the model/tool loop. The loop lives in `agent_loop(...)`, `agent_loop_continue(...)`, and `_run_loop(...)`.

SetupAgent equivalent:

| pi-mono concept | SetupAgent target role | Current SetupAgent owner |
| --- | --- | --- |
| `Agent` | `SetupAgentSession` | `SetupGraphRunner` + `SetupAgentExecutionService` |
| `AgentState` | public runtime/session state | `SetupGraphState` + runtime structured payload |
| `agent_loop` / `_run_loop` | `SetupTurnLoop` | `RpAgentRuntimeExecutor` + runtime graph nodes |
| `AgentContext` | loop-local model context | `RpAgentTurnInput` + runtime adapter bundle |
| `AgentEvent` | runtime event stream | `RuntimeEvent` + `TypedSseEventAdapter` |

Target implication: SetupAgent should keep the outer setup lifecycle separate from the inner model/tool loop. The outer layer prepares workspace, request, model/provider, and stream boundary. The inner layer owns model calls, tool calls, repair, observation, continue, and stop.

### 2.2 The Loop Has One Readable Shape

pi-mono's loop can be summarized as:

```text
pending messages
  -> stream assistant response
  -> inspect stop reason
  -> execute tool calls if present
  -> append tool results
  -> emit turn end
  -> consume steering/follow-up messages
  -> stop when no tools and no pending follow-up
```

This shape is the architecture asset. It gives every turn one obvious place for:

- context transformation before the model call
- model request/stream conversion
- assistant output inspection
- tool execution
- tool result observation
- stop/continue decision
- event emission

SetupAgent already has most of these mechanics, but they are harder to reason about because the conceptual names are buried under graph node names, executor helper names, and policy-specific return dictionaries.

Target implication: A0 should document the SetupAgent turn loop using semantic responsibilities, not only LangGraph node names.

### 2.3 Event Types Are A Contract, Not UI Decoration

pi-mono defines a small event vocabulary:

- `agent_start`
- `turn_start`
- `message_start`
- `message_update`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `turn_end`
- `agent_end`

SetupAgent has typed SSE already. The useful lesson is that events should be emitted by the loop as state transitions, then adapted to UI transport. Event naming must not be an afterthought inside the frontend stream adapter.

Target implication: `SetupEventSink` should explicitly own which runtime facts become typed user-visible events and which facts stay internal debug/eval data.

### 2.4 Context Conversion Is A Hookable Pipeline

pi-mono has two separate steps:

- `transform_context`: modify/compact application messages before model conversion
- `convert_to_llm`: produce model-compatible messages

This is the minimal version of SetupAgent's heavier context pipeline:

```text
SetupContextBuilder
  -> SetupContextGovernorService
  -> SetupContextCompactionService
  -> SetupRuntimeAdapter
  -> SetupAgentPromptService
  -> RpAgentTurnInput messages
```

Target implication: SetupAgent does not need fewer context pieces. It needs one named `SetupContextPipeline` contract that states input, output, invariants, and ownership. Without that, draft truth, compact summaries, working digest, and SkillPack prose can drift.

### 2.5 Minimal Framework Boundary For SetupAgent

The minimal SetupAgent framework should be explainable as:

```text
SetupAgentSession
  owns setup request/session boundary, workspace preflight, stream boundary

SetupTurnLoop
  owns one or more model/tool/observation cycles for a user turn

SetupContextPipeline
  owns all pre-model context assembly and model-message conversion

SetupCapabilityPlan
  owns model-visible capabilities for this turn

ModelGateway
  owns provider request/stream/schema adaptation

OutputInspector
  owns assistant output classification before user visibility

SetupToolRuntime
  owns deterministic tool validation/execution/result conversion

SetupTurnLoop transition rules
  own repair/continue/finish decisions inside the loop state machine

SetupEventSink
  owns runtime event emission and typed SSE adaptation

SetupRuntimeStateStore
  owns runtime cognition/state persistence boundaries
```

That is the pi-mono lesson applied to this project: small architecture vocabulary first, implementation extraction second.

## 3. Claude Code Lessons: Mature Module And Feature Design

Sources reviewed:

- `docs/research/claude-code-from-scratch-main/src/agent.ts`
- `docs/research/claude-code-from-scratch-main/src/tools.ts`
- `docs/research/claude-code-from-scratch-main/src/session.ts`
- `docs/research/claude-code-from-scratch-main/src/prompt.ts`
- `docs/research/claude-code-from-scratch-main/src/skills.ts`
- `docs/research/claude-code-from-scratch-main/src/memory.ts`
- `docs/research/how-claude-code-works-main/docs/02-agent-loop.md`
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/04-tool-system.md`
- `docs/research/how-claude-code-works-main/docs/13-minimal-components.md`

Claude Code's useful lesson is mature feature ownership. It shows how agent features become maintainable when each concern has an explicit pipeline and extension point.

### 3.1 Tool Is A Full Product Surface, Not Just A Callable

Claude Code treats a tool as a bundled unit of:

- identity and aliases
- model-facing description
- input schema
- runtime validation
- permission and safety semantics
- concurrency semantics
- execution
- progress events
- result mapping
- UI rendering
- max result sizing
- prompt guidance
- optional deferred loading/search

The current SetupAgent tool surface is weaker as an architecture because equivalent concerns are spread across several owners:

| Concern | Current SetupAgent location |
| --- | --- |
| visible tool names | `profiles.py` |
| model-visible schema | MCP/local provider definitions through `RuntimeToolRegistryView` |
| turn allowlist | `SetupRuntimeAdapter` / `RuntimeToolExecutor` |
| deterministic execution | `SetupToolProvider` |
| model prompt guidance | `SetupAgentPromptService` / SkillPack |
| tool scope tests | `test_setup_agent_tool_scope.py` and focused provider tests |
| typed tool events | executor events + `TypedSseEventAdapter` |

Target implication: `SetupCapabilityPlan` must become the explicit ownership spine for tools. It does not need to execute tools itself, but it must be the single contract that binds schema, allowlist, prompt guidance, execution eligibility, event expectations, and tests.

### 3.2 Tool Defaults Should Fail Closed

Claude Code's tool defaults are conservative: not concurrency safe unless declared, not read-only unless declared, not auto-approved unless declared. This is directly relevant to SetupAgent's staged setup tools.

SetupAgent adaptation:

- new setup tools are hidden from SetupAgent until `SetupCapabilityPlan` exposes them
- model-facing prompt guidance must not mention a tool that the provider schema/allowlist does not expose
- provider registration alone must not make a tool visible to the model
- test snapshots must fail if prompt guidance, schema visibility, and execution allowlist diverge
- candidate tools such as `setup.world_background.*` remain Phase B until accepted by capability planning

### 3.3 Separate Model-Facing Tool Schema From Runtime Authority

Claude Code validates tool input structurally, then applies semantic validation and permission checks before execution. SetupAgent needs the same distinction:

```text
model-facing schema
  -> runtime argument parsing
  -> deterministic validation
  -> business permission/scope check
  -> workspace mutation or read
  -> structured result/error
```

This aligns with the existing SetupAgent direction: slim `setup.truth.write` may be model-facing, but `SetupToolProvider` remains the deterministic authority for IDs, schemas, stage rules, merge behavior, and structured errors.

Target implication: A2 should define one contract for model-facing schema versus provider-side authority. This prevents prompt-only tool fixes from becoming accepted architecture.

### 3.4 Output Separation Is A First-Class Boundary

Claude Code separates assistant text, tool-use blocks, tool results, thinking/internal stream blocks, and UI rendering. SetupAgent needs the same conceptual split, adapted to typed SSE:

- natural assistant text may be shown as assistant content
- real tool calls become typed tool events and tool observations
- pseudo tool code emitted as text is not user-facing assistant text
- raw provider deltas and internal repair/debug data are not user-facing assistant content
- structured errors are machine-readable observations before they become user explanations

Target implication: `OutputInspector` and `SetupEventSink` are A1 core modules. They should own the boundary between provider output and user-visible transcript.

### 3.5 Compression And Memory Are Pipelines, Not Random Prompt Patches

Claude Code treats context pressure through layered compression, memory prefetch/injection, and large tool result persistence. SetupAgent already has stage-local governance and compact summaries.

SetupAgent adaptation:

- do not turn setup context governance into a generic memory subsystem in A1/A2
- keep `SetupWorkspace` and stage drafts as business truth
- keep compact summaries as current-stage/local-step aids
- make the context pipeline contract explicit before adding retrieval or dialogue persistence

### 3.6 Subagents Are A Capability Pattern, Not Immediate Scope

Claude Code's subagent design is mature: agent definition lookup, model selection, isolation, tool pool filtering, prompt rendering, synchronous/asynchronous return. This is valuable later, but it is not the immediate SetupAgent architecture fix.

SetupAgent adaptation:

- use the pattern later if setup decomposes into specialist background agents
- do not add subagent capability in A1/A2
- keep current priority on one reliable setup loop and one coherent capability plan

## 4. What SetupAgent Should Not Copy

| Reference feature | Why not copy directly now |
| --- | --- |
| Claude Code file-editing permissions | SetupAgent edits structured RP setup drafts, not arbitrary filesystem state. Permission semantics must be setup-stage/business aware. |
| Claude Code full tool count and deferred tool catalog | SetupAgent has a narrow stage-scoped tool surface. Adding tool breadth would worsen drift before `SetupCapabilityPlan` exists. |
| Claude Code terminal UI rendering per tool | SetupAgent transport is typed SSE and app UI. It needs event contracts, not terminal React components. |
| Claude Code subagent/task management | Useful later, but the current issue is the primary setup loop's maintainability. |
| pi-mono generic state/message model | SetupAgent has `SetupWorkspace`, draft truth, stage handoff, review/commit/readiness, and runtime cognition contracts that must remain project-specific. |
| pi-mono loop without business policies | SetupAgent needs explicit repair, completion guard, stage-local context, tool validation, and typed SSE behavior. |

## 5. Direct Architecture Consequences

The reference extraction changes the SetupAgent plan in five concrete ways.

### 5.1 The Main Architecture Fix Is Ownership, Not More Features

Current SetupAgent already has many pieces. The work should reduce the number of places that must be changed for one conceptual feature.

Acceptance question for every target module:

```text
If I change this concern, can I name the one owner contract and the small set of expected implementation files?
```

If the answer is no, the architecture is still too implicit.

### 5.2 `SetupCapabilityPlan` Is The Tool-Surface Spine

Because tool changes are the clearest maintainability pain, `SetupCapabilityPlan` should be the first explicit cross-file contract after A1.

It should define:

- stage and step identity
- model-visible tool list
- execution allowlist
- prompt/tool guidance bundle
- provider schema adaptation mode
- candidate tool exclusion rules
- test snapshot expectations

It should not own:

- actual workspace mutation logic
- pydantic business validation internals
- UI rendering
- registry-wide MCP truth

### 5.3 `OutputInspector` Belongs Before Tool Runtime

The old recursion/pseudo-tool bug family is a boundary failure:

```text
provider output
  -> output classification failed or was too implicit
  -> pseudo tool text leaked / repair or stop path did not trigger clearly
```

A1 must make the order explicit:

```text
ModelGateway result
  -> OutputInspector classification
  -> SetupTurnLoop transition route
  -> SetupToolRuntime only for real tool calls
  -> SetupEventSink visible events
```

### 5.4 `SetupContextPipeline` Should Remain Layered But Named

Setup context is not simple enough to collapse into one file. The improvement is to name the pipeline and define its packet boundaries:

```text
business truth packet
  -> governed history
  -> compact summary / working digest / retained outcomes
  -> prompt and skill-pack assembly
  -> model-ready runtime input
```

This preserves existing work while making ownership reviewable.

### 5.5 Implementation Slices Should Follow Risk

Recommended order remains:

```text
A1 Loop stop / repair / output boundary
A2 CapabilityPlan as the one source for tool surface
A3 ContextPipeline contract consolidation
A4 ModelGateway + EventSink hardening
A5 RuntimeStateStore / trace / visible transcript separation
B  Draft CRUD migration
```

The user's latest clarification strengthens A2's importance, but it does not move A2 before A1. A1 still closes the failure class from the old handoff: pseudo tool output, bounded repair, and deterministic stop before recursion-limit failure.

## 6. Reference-To-SetupAgent Mapping

| SetupAgent target role | pi-mono lesson | Claude Code lesson | SetupAgent migration direction |
| --- | --- | --- | --- |
| `SetupAgentSession` | `Agent` owns public session API and state | session save/restore and top-level agent options | keep graph/runner thin; document request/session boundary |
| `SetupTurnLoop` | `_run_loop` owns model/tool/turn end cycle | agent loop handles budgets, retries, compression, tool result reinjection | keep executor as loop owner; make semantic loop phases explicit |
| `SetupContextPipeline` | `transform_context` then `convert_to_llm` | compression, memory injection, context window governance | document layered setup context assembly as one pipeline |
| `SetupCapabilityPlan` | tools are part of `AgentContext` | tool registry, active tool filtering, fail-closed defaults | create a single stage-aware tool-surface contract |
| `ModelGateway` | stream function wraps provider transport | provider-specific streaming, retry, thinking, tool schema adaptation | isolate provider compatibility from policy/prompt folklore |
| `OutputInspector` | assistant message inspected for tool calls/error | text/tool/thinking/result separation | classify pseudo tool text, empty output, malformed tool calls before visibility |
| `SetupToolRuntime` | `_execute_tool_calls` validates and returns tool results | validation, permissions, result sizing, hooks | keep provider deterministic; make error payload contract explicit |
| `SetupTurnLoop` transition rules | loop stop when no tools/follow-up | budget, retry, denial tracking, context break | unify finish/continue/repair taxonomy inside the loop, without a larger god-object policy layer |
| `SetupEventSink` | event stream is generated by loop | UI rendering consumes structured lifecycle events | typed SSE adapts runtime events; no debug text leakage |
| `SetupRuntimeStateStore` | `AgentState` is central session state | session persistence/memory surfaces are separated | keep workspace truth vs runtime cognition vs transient trace distinct |

## 7. A0 Planning Impact

This document should feed the next A0 documents:

- `setup-agent-target-architecture-hld.md`: use the minimal spine and mapping.
- `setup-agent-contract-spine-spec.md`: freeze module contracts and ownership rules.
- `setup-agent-implementation-slices.md`: make A2 capability plan a full coherent slice, not a scattered tool cleanup.
- `setup-agent-question-queue.md`: ask only questions that cannot be answered from code/docs/reference material.

The immediate unresolved design question is whether `SetupCapabilityPlan` should become an explicit code object in A2 or remain a documented contract first with implementation consolidated behind existing `profiles.py` / adapter / tool-provider boundaries.
