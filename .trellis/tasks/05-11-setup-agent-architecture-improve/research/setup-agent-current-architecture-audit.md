# SetupAgent Current Architecture Audit

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 architecture audit
>
> Working-tree policy: audit the current disk implementation, but mark uncommitted implementation as `working-tree candidate`. A candidate is evidence and migration material, not accepted architecture truth.

## 1. Executive Summary

The current SetupAgent implementation already contains most of the pieces needed for a reliable creative-agent loop:

- thin outer setup harness
- inner model/tool/observation loop
- stage-aware tool scope
- pre-model context assembly and compaction
- machine-readable tool validation failures
- bounded repair and completion guard policies
- typed SSE event mapping
- runtime-state governance persistence
- prompt-layer SkillPack injection

The core architecture problem is not missing parts. The problem is that the authoritative contract spine is still implicit and spread across files. The implementation is node-rich and policy-rich, but the top-level responsibilities are not yet documented as one module architecture.

The next architecture work should therefore converge ownership and contracts instead of adding another feature surface.

## 2. Audit Source Policy

This audit uses three evidence classes:

| Evidence class | Meaning |
| --- | --- |
| Accepted specs | Active `.trellis/spec/backend/rp-setup-agent-*.md` contracts. These are authoritative unless explicitly updated. |
| Current disk implementation | Current files under `backend/rp/...`, including uncommitted changes. This describes what is physically present now. |
| Working-tree candidate | Current disk behavior that appears uncommitted, experimental, or not yet reconciled with active specs/tests. Use as migration input, not final truth. |

Notable current candidate surfaces:

- `backend/rp/tools/setup_tool_provider.py` contains `setup.world_background.*` CRUD helper classes and methods.
- `backend/rp/tests/test_setup_world_background_tools.py` exists as a focused candidate test.
- `backend/rp/tests/test_setup_agent_tool_scope.py` still asserts world_background CRUD tools are not exposed through current SetupAgent tool scope.

Interpretation: world_background CRUD is candidate Phase B material, not A1 loop-spine architecture truth.

## 3. Current Flow

```text
Setup API / caller
  -> SetupGraphRunner
      -> SetupGraphNodes.load_workspace
      -> SetupGraphNodes.run_turn
          -> SetupAgentExecutionService
              -> _prepare_turn_launch
              -> _build_runtime_v2_turn_input
                  -> SetupContextBuilder
                  -> SetupAgentRuntimeStateService
                  -> SetupContextGovernorService / SetupContextCompactionService
                  -> SetupRuntimeAdapter
                      -> SetupAgentPromptService
                      -> build_setup_agent_tool_scope
              -> RpAgentRuntimeExecutor
                  -> prepare_input
                  -> derive_turn_goal
                  -> plan_step_slice
                  -> build_model_request
                  -> call_model
                  -> inspect_model_output
                  -> execute_tools
                      -> RuntimeToolExecutor
                          -> SetupToolProvider
                  -> apply_tool_results
                  -> assess_progress
                  -> reflect_if_needed
                  -> finalize_success / finalize_failure
              -> persist runtime governance
      -> typed SSE / response
```

Current layering is broadly correct: setup harness stays outside the inner turn loop, while runtime-v2 owns loop semantics.

## 4. Module Responsibility Map

| Target architecture role | Current owner(s) | Current state | Audit note |
| --- | --- | --- | --- |
| `SetupAgentSession` | `SetupGraphRunner`, `SetupGraphNodes`, `SetupAgentExecutionService` | Split between graph shell and execution service | Needs naming/contract clarity. Existing split is usable. |
| `SetupTurnLoop` | `RpAgentRuntimeExecutor`, `agent_runtime/graph.py`, `agent_runtime/state.py` | Rich LangGraph node loop | Strong implementation, but architecture vocabulary should be model -> inspect -> tool -> observation -> decision. |
| `SetupContextPipeline` | `SetupAgentExecutionService`, `SetupContextBuilder`, `SetupContextGovernorService`, `SetupContextCompactionService`, `SetupRuntimeAdapter`, `SetupAgentPromptService` | Mature but distributed | Needs one documented pipeline contract so packet/governed history/overlay/prompt do not drift. |
| `SetupCapabilityPlan` | `profiles.py`, `SetupRuntimeAdapter`, `RuntimeToolRegistryView`, `RuntimeToolExecutor`, `SetupToolProvider`, prompt prose | Partially present as `tool_scope` and visible tools | This is the weakest ownership boundary. Prompt, schema, allowlist, execution, and tests need a single plan source. |
| `ModelGateway` | `RpAgentRuntimeExecutor._build_model_request`, `_call_model_*`, `_model_facing_tool_definitions`, slim truth-write adapter | Present inside executor | Good candidate to extract conceptually first, possibly code later. Provider compatibility should not be prompt folklore. |
| `OutputInspector` | `RpAgentRuntimeExecutor._inspect_model_output` plus pseudo tool text detection helpers | Present, with candidate pseudo-tool filtering | Should become explicit contract: real tool calls, text, pseudo tool leakage, malformed arguments, provider errors. |
| `SetupToolRuntime` | `RuntimeToolExecutor`, `RuntimeToolRegistryView`, `SetupToolProvider` | Present | Provider validation and workspace mutation are deterministic, but candidate CRUD surfaces must not leak before capability plan accepts them. |
| `DecisionPolicy` | `FinishPolicy`, `ToolFailureClassifier`, `RepairDecisionPolicy`, `ActionDecisionPolicy`, `CompletionGuardPolicy`, `ReflectionTriggerPolicy`, route helpers in executor | Strong policy set | Good substance, but decision surfaces should be unified as one policy layer with clear terminal/continue taxonomy. |
| `SetupEventSink` | `RuntimeEvent`, `TypedSseEventAdapter`, executor `_emit_event`, execution-service stream path | Present | Must preserve typed tool events and keep pseudo/debug/internal text out of assistant content. |
| `SetupRuntimeStateStore` | `SetupAgentRuntimeStateService`, `SetupWorkspace` interaction, runtime structured payload | Present | Boundary must stay clear: workspace truth vs runtime cognition vs transient trace. |

## 5. Accepted Contract Anchors

The current active specs already freeze these architecture facts:

- `SetupAgentExecutionService` is a thin outer harness.
- Inner loop semantics live in runtime-v2 and expose explicit `continue_reason`, `finish_reason`, and `loop_trace`.
- Pre-model context is layered: context packet, governed history, runtime adapter bundle, runtime request assembly.
- Context compaction is current-stage/local-step governance, not a new memory subsystem.
- Tool validation failures are machine-readable and get one bounded repair attempt.
- Tool scope is turn input allowlist behavior, not registry deletion.
- SkillPack is prompt-only and stage-keyed; it does not own tool scope.
- Slim `setup.truth.write` is a model-facing adapter over provider-side validation, not a replacement for pydantic authority.

Any target architecture that contradicts these must update specs explicitly.

## 6. Current Strengths

### 6.1 Thin Outer Harness Exists

`SetupGraphRunner` is already a small LangGraph shell with `load_workspace -> run_turn -> END`. `SetupAgentExecutionService` shares launch preflight between text and stream paths and prepares runtime-v2 inputs before delegation.

This supports the target split:

```text
outer harness: setup lifecycle, workspace/model/provider preflight, stream boundary
inner loop: model/tool/repair/decision semantics
```

### 6.2 Runtime Loop Has Real Decision Surfaces

`RpAgentRuntimeExecutor` already carries:

- semantic node order
- `continue_reason`
- `finish_reason`
- `loop_trace`
- pseudo-tool detection
- tool start/result events
- route safety for invalid next actions
- final structured payload

The missing piece is architectural clarity, not raw mechanics.

### 6.3 Context Pipeline Is Substantial

Current context assembly already includes:

- `SetupContextPacket`
- prior-stage handoffs
- current draft snapshot
- user edit deltas
- stage-local history governance
- compact summary
- retained tool outcomes
- working digest
- context report
- runtime overlay message

This is close to the desired `SetupContextPipeline`; it needs documentation and boundary consolidation.

### 6.4 Tool Provider Owns Deterministic Mutations

`SetupToolProvider` performs pydantic validation, workspace mutations, truth write lowering, draft ref reads, commit target checks, and structured error payloads. This matches the principle that the model supplies semantic content/intent while deterministic code owns IDs, schemas, validation, merge rules, and persistence.

## 7. Current Drift / Failure Points

### 7.1 Capability Plan Is Not A Single Spine

Tool availability is currently distributed across:

- constants in `profiles.py`
- `SetupRuntimeAdapter.build_turn_input(...)`
- runtime registry filtering
- provider tool list in `SetupToolProvider`
- prompt hints in `SetupAgentPromptService`
- tests in `test_setup_agent_tool_scope.py`

This distribution allowed the old bug family: provider registration, prompt guidance, scope, and tests can disagree.

Needed correction: define `SetupCapabilityPlan` as a single conceptual contract first. Later implementation may or may not extract a code object, but the contract must specify the one source for:

- model-visible tool schemas
- execution allowlist
- prompt guidance
- provider fallback behavior
- test snapshots

### 7.2 Output Inspection Is Too Buried In Executor

Pseudo tool text handling exists in `_inspect_model_output`, stream filtering, and tests. That is useful, but the architecture should name this as `OutputInspector` because it is a first-class safety boundary:

- real tool call
- pseudo tool code
- ordinary assistant text
- empty output
- provider/stream failure

Without that named boundary, pseudo-tool fixes risk becoming local regex patches rather than an accepted contract.

### 7.3 Decision Policy Is Strong But Fragmented

Policy classes are real and useful, but final routing still spans:

- policy return dictionaries
- executor update dictionaries
- graph route labels
- finish/continue reason taxonomy
- reflection ticket state

The architecture should explicitly distinguish:

- graph route token
- semantic continue reason
- semantic finish reason
- repair route
- user-visible explanation
- eval/debug trace

### 7.4 Draft Write Direction Is Split Across Accepted And Candidate Paths

Accepted current model-facing path is still `setup.truth.write` with slim runtime-owned defaults and stage-draft injection. Current disk also contains world_background stage-local CRUD candidate tools.

This is not necessarily wrong, but it must be phased:

- A1 should not expose or depend on world_background CRUD.
- B can decide whether unified draft CRUD becomes the model-visible write path.
- CapabilityPlan must prevent candidate tools from leaking through prompt/schema/allowlist before the slice accepts them.

### 7.5 Event Visibility Needs Hard Boundary Language

Typed SSE is present and tested. The architecture still needs a clear rule:

- visible assistant text is natural user-facing text only
- visible tool activity is typed tool events
- internal debug, pseudo tool code, repair trace, and raw provider deltas are not assistant text

This rule belongs in `SetupEventSink` and `OutputInspector`, not in frontend convention alone.

## 8. Working-Tree Candidate Register

| Candidate | Evidence | Status for architecture |
| --- | --- | --- |
| pseudo tool text filtering and retry-budget failure | executor/tests reference `tool_code`, `pseudo_tool_call_text_filtered`, `invalid_tool_output_retry_budget_exhausted` | Candidate A1 behavior. Keep concept, recheck taxonomy against specs before finalizing. |
| repeated recoverable tool failure budget | `RepairDecisionPolicy` has `tool_recovery_budget_exhausted` path | Candidate A1 behavior. Needs spec taxonomy sync if kept. |
| world_background stage-local CRUD tools | `SetupToolProvider` has `setup.world_background.*` models/methods; test file exists | Candidate Phase B. Not A1. Tool scope currently hides these from SetupAgent. |
| slim truth-write stage-draft path | executor/tool-provider functions and active spec | Accepted direction if tests pass; remains provider-validation-backed. |
| SkillPack observability propagation | prompt/spec/execution metadata surfaces | Accepted as observability-only; not behavior authority. |

## 9. Mapping To Target Spine

Recommended target naming can be adopted without immediate code extraction:

```text
SetupAgentSession
  current code: SetupGraphRunner + SetupAgentExecutionService

SetupTurnLoop
  current code: RpAgentRuntimeExecutor + agent_runtime/graph.py/state.py

SetupContextPipeline
  current code: SetupContextBuilder + ContextGovernor + CompactionService + RuntimeAdapter + PromptService

SetupCapabilityPlan
  current code: profiles.py + RuntimeToolRegistryView + SetupToolProvider + prompt hints + tests

ModelGateway
  current code: executor request build/call/stream/tool-schema adaptation

OutputInspector
  current code: executor inspect_model_output + pseudo-tool filters

SetupToolRuntime
  current code: RuntimeToolExecutor + SetupToolProvider

DecisionPolicy
  current code: policies.py + executor route application

SetupEventSink
  current code: RuntimeEvent + TypedSseEventAdapter + stream path

SetupRuntimeStateStore
  current code: SetupAgentRuntimeStateService + structured payload governance
```

## 10. Audit Conclusion

Current SetupAgent should not be rewritten. The right architecture move is to name and freeze the contract spine, then consolidate ownership around it.

The first implementation slice after A0 should remain A1:

```text
Loop stop / repair / output boundary
```

A1 should focus on:

- output inspector contract
- pseudo-tool text handling
- recoverable tool failure observation and bounded repair
- deterministic terminal reasons before graph recursion limits
- typed SSE preservation

A1 should not include:

- world_background CRUD exposure
- full draft CRUD migration
- setup retrieval roadmap
- dialogue persistence
- model config page sync
- SkillPack expansion

## 11. Next Document

Create `pi-mono-claude-code-reference-lessons.md` next, then use it to refine `setup-agent-target-architecture-hld.md`.
