# SetupAgent Architecture Grounding Matrix

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 grounding pass before target HLD
>
> Purpose: prove the architecture work is grounded in current SetupAgent evidence and mature references before writing `setup-agent-target-architecture-hld.md`.

## 1. Grounding Rule

Do not write the target HLD until the following mapping is clear:

```text
current SetupAgent problem
  -> evidence in current code/docs
  -> pi-mono / Claude Code / primary-reference lesson
  -> project-specific landing
  -> what not to copy
```

This document is the bridge between architecture discussion and formal HLD/spec writing.

## 2. Reference Use Policy

Confirmed user口径:

- Existing SetupAgent code proves what capabilities the project needs.
- Existing SetupAgent code does not prove the current module boundaries are good.
- If a concern is not a current-product special requirement, mature references can be learned from directly.
- pi-mono is the primary minimal-framework reference.
- Claude Code is the primary mature-agent module/function reference.
- OpenAI, Anthropic, LangGraph, and LangChain primary docs or local source evidence may be used for concrete provider/tool-calling/tracing/eval/graph/framework mechanisms, but concrete claims must be checked against primary/current sources before entering HLD/spec.
- Secondary engineering articles are non-authoritative background and must not settle concrete provider/framework behavior.

Current grounding status:

| Source | Used in this matrix? | Scope |
| --- | --- | --- |
| Current SetupAgent code/docs | Yes | Problem evidence and product requirements |
| pi-mono local source | Yes | Minimal loop/session/context/tool/event architecture |
| Claude Code local source/docs | Yes | Mature agent loop, tool lifecycle, context, transcript, recovery patterns |
| OpenAI / Anthropic / LangGraph / LangChain docs/source evidence | Not yet for concrete claims | To be consulted when HLD/spec reaches provider-specific structured output, tool-calling compatibility, tracing/eval, graph/checkpoint, or framework adoption details |

## 3. Current Problem -> Reference -> Project Landing Matrix

### 3.1 Architecture Language Is Too Tied To Current Execution Shape

| Dimension | Content |
| --- | --- |
| Current problem | LangGraph node names, executor helper names, and policy return dicts currently act as de facto architecture language. This makes the runtime hard to reason about as an agent framework. |
| Current evidence | `backend/rp/agent_runtime/graph.py` exposes graph nodes such as `prepare_input`, `derive_turn_goal`, `plan_step_slice`, `inspect_model_output`, `assess_progress`, and `reflect_if_needed`; `backend/rp/agent_runtime/state.py` stores route and policy fields such as `next_action`, `completion_guard`, `repair_route`, `continue_reason`, and `pseudo_tool_retry_count`. |
| pi-mono lesson | pi-mono uses small stable concepts: `Agent`, `AgentState`, `AgentContext`, `agent_loop`, tools, and events. The architecture is readable without knowing the scheduler implementation. |
| Claude Code lesson | Claude Code separates session/query engine concerns from the core query loop. The loop is described as user input -> context -> model -> tool execution -> result injection -> continue/stop. |
| Project landing | HLD should define SetupAgent using semantic modules: `SetupAgentSession`, `SetupTurnLoop`, `SetupContextPipeline`, `SetupCapabilityPlan`, `ModelGateway`, `OutputInspector`, `SetupToolRuntime`, `SetupEventSink`, and `SetupRuntimeStateStore`. LangGraph remains execution/checkpoint substrate, not the architecture vocabulary. |
| Do not copy | Do not remove LangGraph just because references do not use it. The issue is vocabulary and ownership, not the substrate itself. |

### 3.2 Tool Exposure Has No Single Spine

| Dimension | Content |
| --- | --- |
| Current problem | Tool-related changes require coordinated edits across tool scope constants, adapter scope selection, provider tool schemas/descriptions, prompt hints, runtime allowlist enforcement, and tests. |
| Current evidence | `build_setup_agent_tool_scope(...)` in `profiles.py` decides visible names; `SetupRuntimeAdapter.build_turn_input(...)` chooses `tool_scope_key`; `RuntimeToolExecutor` filters by `visible_tool_names`; `SetupToolProvider.list_tools()` owns schema/description; `SetupAgentPromptService` hardcodes `setup.truth.write` guidance; `test_setup_agent_tool_scope.py` separately asserts exposure behavior. |
| pi-mono lesson | Current tools are part of `AgentContext`; the loop receives the active capability set as part of context rather than discovering it from scattered globals. |
| Claude Code lesson | Tool is a full capability surface: identity, schema, prompt/description, validation, permission/safety semantics, execution, result mapping, and UI/event behavior. Tool pool/active definitions filter what the model sees. |
| Project landing | Introduce `SetupCapabilityPlan` as the stage/step/turn exposure spine. It compiles stage defaults, step overrides, and turn safety filters into model-visible tool selection, runtime allowlist, prompt guidance, candidate exclusion, and snapshot expectations. |
| Do not copy | Do not make CapabilityPlan execute tools or duplicate business schemas. `ToolProvider` / tool definitions remain schema and execution authority. |

### 3.3 Tool Calling Must Stay Standard

| Dimension | Content |
| --- | --- |
| Current problem | A capability-plan layer could be misread as a custom tool invocation protocol. That would make the architecture worse. |
| Current evidence | Current runtime already uses normal model-visible tool definitions, `RuntimeToolCall`, `RuntimeToolExecutor.execute_tool_call(...)`, and provider-side `SetupToolProvider.call_tool(...)`. |
| pi-mono lesson | Model sees tools in context and emits normal tool calls; runtime validates and executes them. |
| Claude Code lesson | Active tool definitions/tool pools change tool visibility, but the execution chain remains `tool_use -> validate/permission/execute -> tool_result`. |
| Project landing | CapabilityPlan only controls exposure and consistency. The model still receives normal tool schemas in prompt/provider request, emits normal tool calls, and receives normal tool results. |
| Do not copy | Do not invent a setup-specific DSL or hidden router for tool calls. |

### 3.4 ToolProvider Is Too Close To Exposure Decisions But Should Stay Execution Authority

| Dimension | Content |
| --- | --- |
| Current problem | `SetupToolProvider` is the strongest deterministic tool owner, but provider registration alone must not imply model exposure. Candidate tools such as `setup.world_background.*` currently exist in disk code but are intentionally hidden from SetupAgent scope. |
| Current evidence | `SetupToolProvider` owns `_schemas`, `list_tools()`, `call_tool()`, pydantic validation, workspace mutation, truth-write lowering, and world_background candidate helpers; `test_setup_agent_tool_scope.py` asserts world_background CRUD tools are not exposed through SetupAgent scope. |
| pi-mono lesson | Each `AgentTool` owns parameters and execution; the agent context decides which tools are currently available. |
| Claude Code lesson | Tool definitions own schema/validation/execution; tool pools and context filters decide active visibility. Fail-closed defaults prevent accidental exposure. |
| Project landing | `SetupToolProvider` owns schema/validation/execution/result/error payloads. `SetupCapabilityPlan` owns whether those tools are exposed to the model and allowed at runtime. Candidate tools stay hidden until a slice accepts them. |
| Do not copy | Do not move business mutation logic into CapabilityPlan. Do not expose every provider-registered tool by default. |

### 3.5 Prompt Guidance Is A Derived Capability Artifact, Not Authority

| Dimension | Content |
| --- | --- |
| Current problem | Prompt guidance can mention a tool independently from schema exposure and runtime allowlist, creating drift. |
| Current evidence | `SetupAgentPromptService.build_system_prompt(...)` includes direct `setup.truth.write` guidance while tool scope is built elsewhere. SkillPack metadata is also stage-local but does not own tool scope. |
| pi-mono lesson | System prompt and tools are both part of the context passed into the loop; their consistency should be prepared before the loop starts. |
| Claude Code lesson | Mature tools can contribute prompt/description, but active tool definitions still control what the model can call. |
| Project landing | CapabilityPlan should derive prompt guidance from the same selected capability package that drives schemas and allowlist. Prompt cannot open a tool by itself. Tests should catch prompt/schema/allowlist mismatch. |
| Do not copy | Do not centralize all prompt prose in CapabilityPlan. Stage SkillPack can remain prompt-layer material, but its content must be checked against the plan. |

### 3.6 TurnLoop Is Patch-Shaped Instead Of State-Machine-Shaped

| Dimension | Content |
| --- | --- |
| Current problem | The loop contains real mechanics, but control flow is hard to reason about because pseudo-tool handling, blocked commit reassessment, action expectation, completion guard, repair ticket, next action, and finish/continue reasons are mixed inside executor helpers and policies. |
| Current evidence | `_inspect_model_output(...)` handles assistant text extraction, pseudo-tool filtering, error routing, blocked commit proposal handling, action expectation violation, real tool-call routing, completion guard assessment, reflection tickets, `next_action`, `finish_reason`, and `continue_reason`. `policies.py` has multiple separate guard/repair policy classes. |
| pi-mono lesson | `_run_loop` has one readable shape: stream assistant response, inspect tool calls, execute tools, append tool results, emit turn end, continue if needed, stop otherwise. |
| Claude Code lesson | The production loop is more sophisticated but still organized around explicit continue sites: next turn after tool use, context recovery, max-output recovery, stop-hook continuation, token-budget continuation, etc. |
| Project landing | A1 should define `SetupTurnLoop` as a state machine / transition controller: build context and capability plan -> call model -> inspect output -> execute tool or finalize or bounded transition -> continue/stop. Existing policies become migration material and small transition helpers only if they fit the new loop contract. |
| Do not copy | Do not add a bigger generic `DecisionPolicy` god object. Do not preserve current guard layers merely because they exist. |

### 3.7 OutputInspector Is Buried Inside Executor

| Dimension | Content |
| --- | --- |
| Current problem | Model output classification is a safety boundary, but currently it is implemented as executor logic and local regex handling. |
| Current evidence | `_inspect_model_output(...)` parses `tool_calls`, stores `assistant_text`, detects pseudo tool text via `_looks_like_pseudo_tool_call_text(...)`, and can either route to tool execution, reflection retry, success, or failure. |
| pi-mono lesson | Assistant message is inspected for tool calls before deciding whether to execute tools or end the loop. |
| Claude Code lesson | Assistant text, tool-use blocks, tool results, thinking/internal stream, and UI rendering are separated. User-visible output is not just raw provider text. |
| Project landing | `OutputInspector` becomes a formal boundary with a typed inspect result: real tool call, normal text, pseudo tool text, malformed tool call, empty output, provider/schema error, mixed output. It produces loop input; it does not directly decide every business transition. |
| Do not copy | Do not treat regex filtering as the architecture. Regex may be one detector under OutputInspector, not the owner. |

### 3.8 EventSink Is Too Thin For Transcript Safety

| Dimension | Content |
| --- | --- |
| Current problem | Typed SSE exists, but the adapter is mostly a JSON serialization layer. It does not express user-visible transcript rules as an architecture boundary. |
| Current evidence | `RuntimeEvent` is a generic `{type, run_id, sequence_no, payload}` model; `TypedSseEventAdapter.to_sse_line(...)` merges event type and payload into SSE JSON. Tool start/result events are emitted in executor. Stream errors can be collected in `SetupGraphRunner`/execution service. |
| pi-mono lesson | Event stream is generated as loop state transitions (`message_*`, `tool_execution_*`, `turn_end`, `agent_end`). |
| Claude Code lesson | UI/transcript consumes structured lifecycle events and separates assistant text from tool use/results and internal stream details. |
| Project landing | `SetupEventSink` should own which runtime facts become user-visible typed SSE events and which stay internal logs/trace/eval. Pseudo tool text, raw provider deltas, repair trace, debug JSON, and raw stack traces must not become assistant content. |
| Do not copy | Do not copy Claude Code terminal UI rendering. SetupAgent needs typed event/transcript rules for app UI, not terminal React components. |

### 3.9 ModelGateway Is Mixed Into The Executor

| Dimension | Content |
| --- | --- |
| Current problem | Provider request construction, stream parsing, tool schema adaptation, provider failure classification, and usage capture live inside the same executor that owns loop routing. |
| Current evidence | `RpAgentRuntimeExecutor` builds model requests, calls non-stream/stream model APIs, merges streamed tool calls, finalizes streamed calls, and sets `finish_reason = upstream_error` on model failures. |
| pi-mono lesson | Streaming provider call is isolated as a `stream_fn` injected through loop config. |
| Claude Code lesson | Provider-specific stream handling, retry, token tracking, tool-use block parsing, and recovery are explicit mechanisms around the loop. |
| Project landing | `ModelGateway` should own request construction, provider schema adaptation, stream normalization, provider error attribution, and usage capture. `SetupTurnLoop` should consume a normalized model result. |
| Do not copy | Do not force a provider abstraction rewrite before A1. First freeze the contract and classification boundaries; extract code only when the slice proves the benefit. |

### 3.10 ContextPipeline Exists But Is Not Named As One Contract

| Dimension | Content |
| --- | --- |
| Current problem | Context assembly is substantial and mostly correct, but it is distributed across builder, runtime state service, governor, compaction, adapter, prompt service, and SkillPack. Without one pipeline contract, packet/governed history/overlay/prompt can drift. |
| Current evidence | `SetupAgentExecutionService._build_runtime_v2_turn_input(...)` orchestrates retained tool outcomes, working digest, compact summary, governed history, context report, and adapter output. `SetupRuntimeAdapter` assembles `context_bundle`, prompt, metadata, and tool scope. |
| pi-mono lesson | `transform_context` and `convert_to_llm` are separate hookable context stages before model call. |
| Claude Code lesson | Context engineering is a pipeline: budget, snip/compact, memory injection, tool result handling, and request assembly. |
| Project landing | Define `SetupContextPipeline`: business truth packet -> governed history -> compact summary/working digest/retained outcomes -> prompt/SkillPack assembly -> model-ready runtime input. |
| Do not copy | Do not turn setup context governance into a generic Memory OS or retrieval system in A1/A2. |

### 3.11 Runtime State Boundaries Need Harder Language

| Dimension | Content |
| --- | --- |
| Current problem | Workspace business truth, persisted runtime governance aids, turn-local loop trace/reasons, and user-visible transcript all exist, but their authority levels must remain distinct. |
| Current evidence | Runtime governance persistence flows through `SetupAgentRuntimeStateService` for `cognitive_state`, `cognitive_state_summary`, `working_digest`, `tool_outcomes`, and `compact_summary`; active loop semantics keep `loop_trace` and `continue_reason` on result/debug/eval surfaces rather than in governance snapshots; business drafts remain in `SetupWorkspace`. |
| pi-mono lesson | `AgentState` is central runtime/session state, but product-specific truth must be provided by application context. |
| Claude Code lesson | Session persistence, transcript, tool results, memory, and UI output are related but distinct surfaces. |
| Project landing | `SetupRuntimeStateStore` owns runtime cognition, trace, digest, and repair/carry-forward data. `SetupWorkspace` remains business truth. Transient trace is not product truth unless a spec explicitly promotes it. |
| Do not copy | Do not collapse everything into one persisted setup state blob. |

### 3.12 Current Tests Prove Behaviors But Not Ownership

| Dimension | Content |
| --- | --- |
| Current problem | Tests assert some tool visibility and failure behavior, but they do not yet enforce architecture ownership across prompt/schema/allowlist/events. |
| Current evidence | `test_setup_agent_tool_scope.py` checks stage tool scope and candidate tool exclusion. Existing eval/test surfaces cover several repair/failure cases, but not a single capability-plan snapshot contract. |
| pi-mono lesson | Minimal loop's small event/tool/state model is easy to test because there are few surfaces. |
| Claude Code lesson | Mature tools and loop decisions have explicit lifecycle boundaries; tests can target tool filtering, validation, result mapping, stream events, and recovery transitions. |
| Project landing | Add ownership tests later: CapabilityPlan snapshots, prompt/schema/allowlist consistency, OutputInspector classification, EventSink visibility, ModelGateway provider error attribution, TurnLoop transition table. |
| Do not copy | Do not make tests only assert implementation file names or graph node names. Test contracts and visible behavior. |

## 4. What Is Clear Enough To Start Target HLD

The following is now clear enough to write `setup-agent-target-architecture-hld.md`:

1. The current project problem is architecture ownership, not missing individual features.
2. Current code should be used as requirement and migration evidence, not as final architecture shape.
3. pi-mono supplies the minimal runtime skeleton: session, state, context, loop, tool execution, event stream, continue/stop.
4. Claude Code supplies mature module design: tool lifecycle, active tool filtering, fail-closed exposure, context pipeline, output/transcript separation, recovery transitions, and observability surfaces.
5. SetupAgent target architecture should preserve product-specific setup truth while replacing accidental framework mechanics with mature reference-shaped mechanics.
6. A1 should target the `SetupTurnLoop` / `OutputInspector` / `EventSink` bottom boundary, not another patch on pseudo-tool text or recursion limits.
7. A2 should target `SetupCapabilityPlan` as the tool exposure spine, not isolated tool-scope cleanup.

## 5. Still Needs `$grill-me` Only If Encountered During HLD

No blocking product/design question remains before HLD. Continue to `$grill-me` only if target-HLD writing encounters one of these:

1. A proposed reference design would alter setup product semantics such as review/commit/readiness or stage handoff.
2. A mature reference pattern conflicts with current executable setup specs.
3. A module boundary could be either project-level runtime core or SetupAgent-only shell and the choice affects future implementation cost.
4. A candidate tool family, especially `setup.world_background.*`, needs to move earlier than the accepted phase.
5. A concrete OpenAI/Anthropic/LangGraph/LangChain pattern is needed and primary docs do not give a clear answer.

## 6. Next Step

Write `setup-agent-target-architecture-hld.md` using this matrix as source material. The HLD must cite this matrix's decisions and must not reintroduce the corrected mistake that a larger standalone `DecisionPolicy` is the goal. The goal is a cleaner `SetupTurnLoop` state machine with small transition rules, not another补丁 layer.
