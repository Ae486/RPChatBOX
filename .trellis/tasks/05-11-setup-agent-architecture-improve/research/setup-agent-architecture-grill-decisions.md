# SetupAgent Architecture Grill Decisions

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 architecture discussion record
>
> Purpose: persist the architecture口径 confirmed during `$grill-me` discussion so later implementation does not rely on chat-window memory.

## 1. Why This Document Exists

The首要任务 is to clarify and optimize SetupAgent architecture. Architecture here means stable responsibility boundaries, data/control flow, dependency direction, and invariants. It is not merely directory layout, class naming, or moving files around.

The user explicitly challenged that verbal discussion is not enough. Therefore every confirmed architecture口径 below is task material and must be treated as input for the later HLD, contract spine spec, implementation slices, and check plan.

## 2. Architecture Meaning For This Task

Architecture means the system's skeleton and rules:

- which stable modules exist
- what each module owns
- what each module must not own
- how data and control move between modules
- which invariants must always hold
- where a conceptual change should be made
- which tests should fail when a boundary drifts

For SetupAgent, architecture optimization is successful only if a future change can answer:

```text
What concept am I changing?
Which owner owns that concept?
Which contract or snapshot test should protect it?
Which layers must not be touched?
```

The target is not to make code look漂亮. The target is to stop bug fixes from becoming scattered补丁 across prompt, executor, provider, adapter, policy, event stream, and tests.

## 3. Confirmed High-Level Direction

### 3.1 Agent Runtime Core + SetupAgent Shell

Confirmed direction:

```text
project-level agent runtime core
  + SetupAgent-specific business shell
```

Runtime core owns agent mechanisms:

- turn loop
- model gateway
- output inspection
- tool runtime interface
- capability plan
- event sink
- runtime state / trace contract

SetupAgent shell owns setup business truth:

- `SetupWorkspace`
- setup stage / step
- setup draft truth
- review / commit / readiness
- setup-specific context packet
- setup-specific tools
- setup-specific prompt / SkillPack

Rationale:

- pi-mono separates session wrapper, state, context, loop, tools, and events.
- Claude Code has a mature agent loop, tool lifecycle, context, transcript, and extension-point architecture.
- Current SetupAgent code proves the project needs setup-specific behavior, but current code is not automatically the right architecture.

### 3.2 Existing Code Is Requirement Evidence, Not Architecture Authority

Confirmed direction:

```text
existing code tells us what the project needs
existing code does not prove the current module split is good
```

This task must read current SetupAgent specs/code/tests as requirement truth, while still being willing to optimize module boundaries when the current implementation is messy.

### 3.3 Mature Reference Adoption Policy

Confirmed direction:

```text
If a concern is not a current-product special requirement, mature agent/framework references may be adapted directly.
```

This applies especially to:

- pi-mono minimal agent layering
- Claude Code mature module and tool lifecycle design
- OpenAI / Anthropic primary guidance on tool calling, structured outputs, tracing, evals, and provider behavior
- LangGraph patterns where graph/checkpoint/streaming substrate is appropriate
- LangChain framework components only when they solve a real local need without hiding ownership boundaries

Rules:

- Product-specific setup requirements still win: `SetupWorkspace`, setup drafts, review/commit/readiness, stage handoff, typed SSE product taxonomy, and RP-specific truth semantics cannot be overridden silently.
- Non-product-specific agent mechanics should not be reinvented when pi-mono, Claude Code, or primary provider/framework docs already show a clear mature pattern.
- Current code should be treated as evidence that a capability is needed, not as proof that the current structure should be preserved.
- Concrete claims about OpenAI, Anthropic, LangGraph, or LangChain must be based on primary/current docs or local source evidence before they are written into HLD/spec.
- Reference adoption must be explicit: later docs should say whether a module follows pi-mono, Claude Code, provider docs, LangGraph/LangChain, or a project-specific constraint.

The practical effect is that SetupAgent architecture should not keep a local补丁-shaped design merely because it already exists. If mature references converge on a cleaner agent-loop, tool lifecycle, output boundary, or event/tracing design, the target architecture should learn that design and adapt it to setup-specific product contracts.

## 4. CapabilityPlan Decisions

### 4.1 Standard Tool Calling Must Remain

Confirmed direction:

```text
CapabilityPlan must not replace standard tool calling.
```

The normal chain remains:

```text
prompt / tool schema injection
  -> model emits normal tool call
  -> runtime parses tool call
  -> runtime checks allowlist
  -> tool provider validates and executes
  -> tool result is returned to model
```

CapabilityPlan is an exposure and consistency layer. It is not a parallel tool invocation protocol and must not introduce a custom DSL for calling tools.

Reference mapping:

- pi-mono: `AgentContext.tools` enters the loop; model still emits normal tool calls.
- Claude Code: active tool definitions/tool pool filtering decides what the model can see; tool execution remains standard `tool_use -> tool_result`.

### 4.2 Stage Capability Package, Not Bare Tool List

Confirmed direction:

```text
SetupAgent should be organized around stage capability packages, not bare global tool lists.
```

CapabilityPlan should compile stage-local capabilities into:

- model-visible tool schemas
- runtime execution allowlist
- prompt guidance
- candidate/later-stage tool exclusion
- snapshot-test expectations

This directly addresses the current pain that tool behavior is distributed across `profiles.py`, runtime adapter, provider, prompt service, executor filtering, and tests.

### 4.3 CapabilityPlan Also Controls Prompt Guidance

Confirmed direction:

```text
CapabilityPlan controls prompt guidance, but prompt guidance is not a permission source.
```

Rules:

- prompt may explain only capabilities exposed by the plan
- prompt text cannot open a tool
- prompt mentions without schema injection should fail tests
- schema injection without runtime allowlist should fail tests
- allowlist without essential guidance should produce a check warning or focused test failure

This prevents prompt/schema/allowlist drift.

### 4.4 Stage Is The Main Granularity; Step Is Override

Confirmed direction:

```text
stage defaults are the main source
step overrides narrow or specialize them
turn safety filters apply last
```

Target assembly:

```text
Stage defaults
  -> Step overrides
  -> Turn/runtime safety filters
  -> Final tool schemas + prompt guidance + execution allowlist
```

Rationale:

- pure step-level capability plans would become too fragmented
- pure stage-level plans would be too coarse for review/fix/commit-local behavior
- Claude Code and pi-mono both support context-sensitive tool availability rather than global static availability

### 4.5 CapabilityPlan Owns Exposure; ToolProvider Owns Execution

Confirmed direction:

```text
CapabilityPlan owns exposure.
ToolProvider owns execution.
```

CapabilityPlan owns:

- current stage/step exposed capabilities
- model-visible tool selection
- prompt guidance selection
- execution allowlist
- candidate tool exclusion
- expected test snapshots

ToolProvider owns:

- actual tool execution
- pydantic/schema validation
- workspace mutation
- structured result payloads
- structured error payloads
- deterministic business validation

CapabilityPlan must not become a god object that executes tools. ToolProvider must not decide what the current stage exposes to the model.

### 4.6 CapabilityPlan Does Not Own Business Schema

Confirmed direction:

```text
CapabilityPlan does not copy tool schemas.
ToolDefinition / ToolProvider owns schema.
CapabilityPlan selects and adapts visibility of schemas.
```

CapabilityPlan may decide:

- whether a tool is visible
- whether slim/full/provider-compatible schema mode is used
- whether the tool is disabled for the current stage/step/turn

CapabilityPlan must not define a duplicate business schema that can drift from ToolProvider validation.

Reference mapping:

- Claude Code: each tool owns schema, validation, and execution; tool pool/context filters select availability.
- pi-mono: each `AgentTool` carries parameters and execution; `AgentContext.tools` selects current tools.

## 5. Output / Event / Transcript Decisions

### 5.1 OutputInspector Is A Formal Boundary

Confirmed direction:

```text
OutputInspector is the formal boundary for model output before it enters tool runtime, user transcript, repair, or failure handling.
```

It must classify:

- real tool call
- normal assistant text
- pseudo tool text
- malformed tool call
- empty output
- provider/schema error
- mixed text plus tool call

Rules:

- real tool call goes to SetupToolRuntime
- pseudo tool text must not become visible assistant text
- malformed tool call enters bounded repair or structured failure
- provider errors are attributed to ModelGateway/provider, not hidden as business judgment
- normal assistant text is only final when obligations are satisfied

This should replace ad hoc regex补丁 as the conceptual owner of model-output classification.

### 5.2 EventSink / Typed SSE Is The User-Visible Transcript Boundary

Confirmed direction:

```text
EventSink / typed SSE owns what the user can see and in what event shape.
```

EventSink does not make business decisions, but it must prevent runtime internals from leaking into the user transcript.

User-visible:

- natural assistant text
- typed tool activity events
- necessary warnings
- final state

Internal only:

- pseudo tool code
- raw provider deltas
- repair trace
- debug JSON
- LangGraph recursion/internal error text
- raw validation stack traces

Internal data may go to:

- `loop_trace`
- diagnostics/eval record
- Langfuse span
- server logs

It must not become assistant content.

## 6. TurnLoop Decision Correction

### 6.1 Do Not Just Add A Bigger DecisionPolicy

The earlier discussion proposed an independent `DecisionPolicy` owner. The user correctly challenged this as another possible补丁 layer unless grounded in mature architecture.

Corrected direction:

```text
A1 should rebuild SetupTurnLoop as a clean loop state machine / transition controller.
Do not keep growing RepairPolicy / CompletionGuard / pseudo-tool filter as scattered patch layers.
```

The point is not that SetupAgent is more complex than Claude Code. It is not. Claude Code is much more complex. The point is that Claude Code's complexity is organized by a clean agent loop and tool lifecycle, while SetupAgent currently has too much補丁-style behavior because the underlying loop architecture is unclear.

### 6.2 Target TurnLoop Shape

Target state-machine shape:

```text
build context and capability plan
  -> call model through ModelGateway
  -> classify output through OutputInspector
  -> if real tool call:
       execute through SetupToolRuntime
       append tool observation
       continue loop
  -> if normal final text and obligations satisfied:
       finalize visible assistant text
  -> if malformed / pseudo tool / recoverable provider issue:
       enter bounded transition
  -> if retry/budget exhausted:
       structured failure
```

This aligns with:

- pi-mono: response -> inspect tool calls -> execute tools -> append results -> turn_end -> follow-up/stop
- Claude Code: model response -> collect tool_use -> execute tools -> return tool_result -> continue; no tool_use means stop; budgets/permission/context-break are explicit loop transitions

### 6.3 How Existing Policies Should Be Treated

Existing policy classes may be migration material, but they are not automatically the target architecture.

They should be reviewed as:

- keep if they become small transition rules inside the clean loop
- merge if they duplicate state-machine responsibilities
- delete or shrink if they only compensate for missing output/loop boundaries

Do not preserve current補丁 layers merely because they exist.

## 7. Implementation Rhythm Decisions

### 7.1 Contract Spine Before Big File Reorganization

Confirmed direction:

```text
first establish contract spine and tests
then reorganize files only where the contract shows ownership is still scattered
```

Avoid:

- only writing docs with no effect on maintainability
- large directory/class movement before behavior contracts are stable

The first implementation objective is:

```text
changing one concept should identify one owner and one set of contract tests
```

### 7.2 A1 Must Be Architecture-Bottom Fix, Not Another Bug Patch

A1 should not be framed as:

```text
add pseudo tool regex
add recursion guard
add another repair condition
```

A1 should be framed as:

```text
SetupTurnLoop state-machine boundary
ModelGateway -> OutputInspector -> transition -> ToolRuntime/EventSink
bounded error transitions as part of the normal loop
```

## 8. Open Questions Still Worth Asking

The following questions remain legitimate future `$grill-me` topics because they are architecture口径, not implementation trivia:

1. Should the project-level agent runtime core be designed only for SetupAgent now, or explicitly preserve extension points for future RP runtime agents?
2. What is the minimum acceptable A1 code change that proves the new loop state-machine contract is real?
3. Which existing policy classes are genuine transition rules, and which are补丁 that should be collapsed?
4. What exact snapshot tests prove CapabilityPlan is the single exposure spine?
5. Which current setup tools are accepted in A1/A2, and which remain candidate-only for later phases?

## 9. Required Next Documents

This decision record must feed:

- `setup-agent-target-architecture-hld.md`
- `setup-agent-contract-spine-spec.md`
- `setup-agent-implementation-slices.md`
- `setup-agent-test-eval-plan.md`
- `setup-agent-question-queue.md`

If any later document contradicts this record, it must explicitly say why and whether the user confirmed the change.
