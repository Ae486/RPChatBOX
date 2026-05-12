# SetupAgent Contract Spine Spec

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 contract spine
>
> Source HLD: `research/setup-agent-target-architecture-hld.md`

## 1. Purpose

This spec turns the target architecture into explicit contracts. It is the bridge between architecture discussion and implementation.

The core rule:

```text
Every agent runtime concern has one authoritative owner.
Adjacent layers may consume the contract, but they must not redefine it.
```

The current SetupAgent code remains requirement evidence. If the current code has many local fallbacks, extract the product requirement first, then put it under the correct contract owner.

## 2. Cross-Contract Invariants

These invariants apply to every implementation slice:

1. `SetupWorkspace` is the business truth owner.
2. Runtime state, cognition, digest, trace, and provider diagnostics are not business truth by default.
3. Tool calls remain standard provider/model tool calls.
4. Prompt prose is never a permission source.
5. Provider registration is never model exposure by itself.
6. Model output must be classified before it enters tool runtime or user-visible transcript.
7. Recoverable tool failures become structured observations before user-visible terminal failure.
8. Typed SSE is a transcript boundary, not a raw JSON/debug pipe.
9. LangGraph remains a substrate; graph node names are not architecture vocabulary.
10. Every bounded repair/retry transition must carry a reason code, budget key, and terminal behavior.

## 3. Contract C1: SetupAgentSession

Owner:

- `SetupGraphRunner`
- `SetupGraphNodes`
- `SetupAgentExecutionService`

Owns:

- setup request entrypoint
- workspace/model/provider preflight
- stream vs non-stream public path boundary
- current stage/step resolution handoff
- launch of context pipeline, capability plan, and turn loop

Must not own:

- model output classification
- tool execution details
- prompt/tool exposure drift fixes
- inner loop repair decisions
- setup draft mutation except through setup tools/services already responsible for business truth

Required input:

- `SetupAgentTurnRequest`
- resolved workspace
- provider/model config
- stream mode

Required output:

- `SetupAgentTurnResponse` or typed SSE stream
- runtime launch metadata
- persisted runtime governance result after loop completion

Tests/checks:

- text and stream paths share the same preflight/launch contract
- outer harness does not duplicate context assembly
- failure from inner runtime is surfaced as structured setup response/event, not raw stack trace

## 4. Contract C2: SetupContextPipeline

Owner:

- `SetupContextBuilder`
- `SetupContextGovernorService`
- `SetupContextCompactionService`
- `SetupRuntimeAdapter`
- `SetupAgentPromptService`
- stage `SkillPack` prompt assembly

Owns:

- business truth packet
- governed history
- compact summary
- working digest
- retained tool outcomes
- prompt and SkillPack assembly
- final model-ready runtime context

Must not own:

- model-visible tool permission
- runtime allowlist
- provider schema compatibility
- tool execution

Pipeline:

```text
SetupWorkspace truth
  -> SetupContextPacket
  -> governed history
  -> compact summary / working digest / retained tool outcomes
  -> consume CapabilityPlan prompt guidance fragments
  -> prompt + SkillPack + runtime overlay
  -> RpAgentTurnInput context bundle
```

Invariants:

- Prompt guidance must be checked against `SetupCapabilityPlan`.
- Final prompt assembly consumes `SetupCapabilityPlan` guidance; it must not independently open or imply a tool.
- SkillPack remains prompt-layer material and observability metadata only.
- Compaction can summarize context, but cannot replace setup draft truth.
- Retained tool outcomes are observations, not direct workspace mutations.

Tests/checks:

- final request message ordering stays deterministic
- compacted history and runtime overlay do not erase required draft refs
- prompt text does not mention tools absent from the active capability plan

## 4D. Contract C2D: SkillPack Governance

Owner:

- `SetupContextPipeline`
- `SetupAgentPromptService`
- `backend/rp/agent_runtime/skill_packs/registry.py`

Owns:

- deterministic stage-keyed SkillPack lookup from resolved `SetupStageId`
- stable prompt-layer Specialist hat prose
- prompt assembly audit metadata
- transient `skill_pack_name` observability metadata

Must not own:

- `SetupCapabilityPlan`
- model-visible tool permission
- runtime allowlist / `tool_scope`
- provider schema compatibility
- `setup.truth.write` runtime-owned argument injection
- `SetupWorkspace` business truth
- runtime overlay content
- `context_bundle`
- durable runtime cognition/state

Pipeline:

```text
resolved SetupStageId
  -> get_skill_pack_for_stage(...)
  -> SetupAgentPromptService stable system prompt
  -> SetupRuntimeAdapter metadata.skill_pack_name
  -> RpAgentTurnResult.structured_payload.skill_pack_name
  -> eval trace root attributes.skill_pack_name
```

Invariants:

- Selection is server-side and stage-keyed. No LLM self-selection, heuristic
  matching, per-mode override, or user-visible pack chooser participates in this
  slice.
- SkillPack content may shape prose and facilitation style only inside the
  stable prompt layer.
- Hard-unload is achieved by rebuilding the next prompt from the newly resolved
  stage. There is no former-pack carry-forward outside prior-stage handoff
  truth.
- `skill_pack_name` is metadata only. Behavior, tool scope, truth-write
  injection, and durable state must not depend on it.
- Capability guidance continues to come from
  `SetupCapabilityPlan.prompt_guidance_fragments`; SkillPack prose cannot open
  or imply inactive tools.

Tests/checks:

- `test_skill_packs_registry.py` proves registry shape, deterministic parsing,
  and no tool-authority fields.
- `test_setup_agent_prompt_service.py` proves SkillPack prompt insertion,
  hard-unload for other stages, and CapabilityPlan prompt filtering.
- `test_setup_agent_tool_scope.py` proves character-design SkillPack activation
  does not alter tool scope.
- `test_setup_agent_execution_service_v2.py` proves metadata stays outside
  `context_bundle` and capability plan / tool scope stay unchanged.
- `test_eval_trace_capture.py` and `test_eval_diagnostics.py` prove
  `skill_pack_name` is consumed only from runtime-owned trace metadata.

## 4A. Contract C2A: SetupLightweightReadback

Owner:

- `SetupContextPipeline`
- `SetupToolRuntime`
- `SetupToolProvider`
- `SetupTruthIndexService`

Owns:

- exact current editable setup draft ref recovery
- compact-summary recovery hint readback
- prior-stage handoff ref use
- lexical/path/filter search over accepted setup truth
- bounded exact reads from accepted setup truth refs

Accepted surfaces:

- `setup.read.draft_refs`
- `setup.truth_index.search`
- `setup.truth_index.read_refs`
- `SetupTruthIndexService`

Must not own:

- semantic/vector retrieval
- hybrid search and reranking
- Recall / Memory OS retrieval
- active-story runtime retrieval policy
- retrieval-core chunk/index/embedding storage

Boundary:

```text
current editable setup draft
  -> setup.read.draft_refs

accepted setup commit snapshot
  -> SetupTruthIndexService
  -> setup.truth_index.search / setup.truth_index.read_refs

accepted setup commit snapshot
  -> deterministic retrieval seed materialization
  -> retrieval-core chunk/index/embedding/hybrid/rerank/runtime retrieval
```

Invariants:

- Setup draft truth is recovered through setup-owned readback, not Memory OS or retrieval-core.
- Committed setup truth lookup is deterministic lexical/path/filter search plus exact read, not semantic retrieval.
- Search returns candidate refs and previews; read returns bounded exact payload only after refs are selected.
- Retrieval-core starts after accepted setup truth is materialized into seed sections.
- Retrieval materialization readiness is not a setup-stage commit gate.
- The agent never writes retrieval index rows directly.

Tests/checks:

- `setup.read.draft_refs` remains visible where context governance requires draft recovery.
- `setup.truth_index.search` and `setup.truth_index.read_refs` remain read-only setup tools.
- truth-index reads ignore uncommitted draft changes and raw setup discussion.
- retrieval seed materialization preserves setup anchors but does not feed back into editable setup draft readback.

## 5. Contract C3: SetupCapabilityPlan

Owner:

- target conceptual owner for stage/step/turn capability exposure
- initially migrated from `profiles.py`, runtime adapter scope selection, registry filtering, prompt guidance, and scope tests

Owns:

- active tool names
- model-visible schema selection
- runtime execution allowlist
- prompt guidance fragments for active capabilities
- stage default capability package
- step overrides
- turn/runtime safety filters
- candidate tool exclusion
- snapshot-test expectations

Must not own:

- pydantic business schema definitions
- tool execution
- workspace mutation
- provider registry truth

Assembly:

```text
stage defaults
  -> step overrides
  -> turn/runtime safety filters
  -> final capability package
```

Required final package:

```text
stage_id
step_id
active_tool_names
model_schema_modes
runtime_allowlist
prompt_guidance_fragments
candidate_exclusions
snapshot_expectations
```

Invariants:

- prompt mentions without schema exposure are invalid
- schema exposure without runtime allowlist is invalid
- provider-registered candidate tools remain hidden unless explicitly accepted by a slice
- `setup.world_background.*` stays candidate-only until a separate product/tool slice explicitly accepts it
- accepted active-spec tools remain visible unless a slice explicitly changes that spec-backed contract:
  - shared setup-private tools such as `setup.truth.write`, `setup.question.raise`, `setup.proposal.commit`, `setup.read.workspace`, and `setup.read.step_context`
  - stage-local recovery/read tools required by context governance, including `setup.read.draft_refs`
  - the current legacy patch-family tool only where the active stage-aware tool-scope spec still allows it

Tests/checks:

- capability snapshot per stage/step
- prompt/schema/allowlist consistency test
- candidate tool fail-closed test
- provider registration does not imply exposure
- active shared/read tool retention test, including `setup.read.draft_refs`

## 6. Contract C4: ModelGateway

Owner:

- target conceptual owner inside or around `RpAgentRuntimeExecutor`

Owns:

- provider request construction
- active tool schema conversion
- slim/full/provider-compatible schema adaptation
- non-stream and stream call normalization
- streamed tool-call reconstruction
- provider error classification
- usage capture
- provider tracing metadata

Must not own:

- setup business transition decisions
- prompt authority
- tool execution
- user-visible transcript finalization

Normalized output should distinguish:

- completed assistant message
- tool call blocks
- stream parse/provider failure
- usage metadata
- provider finish reason

Tests/checks:

- fake provider stream can reconstruct tool call blocks
- provider/tool-schema error is attributed as provider/gateway failure
- loop does not treat provider failure as setup business completion

Primary-doc rule:

- Concrete OpenAI / Anthropic behavior must be checked against current official docs before implementation specs cite exact request/response fields.

## 7. Contract C5: OutputInspector

Owner:

- target explicit contract currently buried in `_inspect_model_output(...)`

Owns:

- classification of normalized model output before tool runtime or transcript visibility

Classifications:

- `real_tool_call`
- `normal_text`
- `pseudo_tool_text`
- `malformed_tool_call`
- `empty_output`
- `provider_schema_error`
- `mixed_text_and_tool_call`

Typed result fields:

```text
classification
public_text_candidate
tool_calls
repair_observation
private_diagnostics
continue_reason_candidate
finish_reason_candidate
```

Must not own:

- tool execution
- workspace mutation
- final user-visible event rendering
- broad business policy

Invariants:

- pseudo tool text cannot become assistant content
- malformed calls enter bounded repair or structured failure
- mixed text plus tool call must not double-emit unsafe text
- empty output cannot be silently treated as successful completion

Tests/checks:

- pseudo tool text classification
- mixed text/tool-call classification
- malformed arguments classification
- empty output failure route

## 8. Contract C6: SetupTurnLoop

Owner:

- `RpAgentRuntimeExecutor`
- runtime graph/state as substrate

Owns:

- user-turn state machine
- model call / inspect / tool / observation / continue / stop order
- transition rules
- retry budget consumption
- `continue_reason`
- `finish_reason`
- loop trace frame production

Must not own:

- `SetupWorkspace` business truth directly
- provider transport internals after ModelGateway extraction
- tool schema authority
- raw SSE serialization

State-machine shape:

```text
START_TURN
  -> BUILD_INPUT
  -> CALL_MODEL
  -> INSPECT_OUTPUT
  -> EXECUTE_TOOL | FINALIZE_TEXT | REPAIR_OUTPUT | ASK_USER | FAIL_STRUCTURED
  -> OBSERVE_TOOL_RESULT
  -> CALL_MODEL | FINALIZE_TEXT | FAIL_STRUCTURED
  -> END_TURN
```

Transition rules:

- small and loop-owned
- may reuse existing policy classes only if they fit the state-machine contract
- must not grow into a separate god-object policy layer

Recoverable tool failure rule:

```text
structured tool error
  -> if retryable and budget remains:
       append observation
       continue loop
  -> if user input required:
       ask user with public-safe summary
  -> if budget exhausted or non-recoverable:
       structured terminal failure
```

Tests/checks:

- real tool call receives tool result observation and can stop normally
- recoverable tool failure retries before user-visible terminal failure
- repeated pseudo tool text exhausts explicit budget before graph recursion limit
- finish/continue reason taxonomy is deterministic

## 9. Contract C7: SetupToolRuntime

Owner:

- `RuntimeToolExecutor`
- `RuntimeToolRegistryView`
- `SetupToolProvider`

Owns:

- runtime allowlist enforcement
- provider lookup
- pydantic validation handoff
- deterministic business validation
- workspace read/mutation through tool provider
- structured result/error observation

Must not own:

- model-visible tool exposure policy
- prompt guidance authority
- stage capability package assembly

Structured error requirements:

```text
code
message
retryable
failure_origin
repair_strategy
required_fields / blocked_values
public_safe_summary
private_details
```

Invariants:

- all tool failures are machine-readable
- deterministic validation remains provider/tool authority
- result/error payloads are observations to the loop first
- user-visible failure only occurs after loop transition says terminal or user-required

Tests/checks:

- provider validation error includes repair metadata
- unknown/disallowed tool remains structured
- candidate provider tools remain inaccessible through SetupAgent capability plan

## 10. Contract C8: SetupEventSink

Owner:

- `RuntimeEvent`
- `TypedSseEventAdapter`
- executor event emission surface
- execution-service stream path

Owns:

- typed runtime event vocabulary
- public/private visibility boundary
- user-visible transcript safety
- mapping runtime lifecycle to SSE payloads

Must not own:

- model output classification
- business transition decisions
- workspace truth

Public:

- finalized assistant text
- typed tool activity
- public-safe warnings
- final state metadata

Private:

- pseudo tool code
- raw provider deltas
- raw validation stack traces
- debug JSON
- repair trace not intended for user
- LangGraph recursion/internal errors

Tests/checks:

- pseudo tool text never appears as assistant content
- tool start/result events remain typed
- terminal failure event is public-safe
- raw provider/debug fields stay private

## 11. Contract C9: SetupRuntimeStateStore

Owner:

- `SetupAgentRuntimeStateService`
- runtime structured payload

Owns:

- runtime cognition
- working digest
- compact summary
- retained tool outcomes
- repair/carry-forward metadata

Exposes but does not persist as governance snapshot under current loop specs:

- turn-local `loop_trace`
- turn-local `continue_reason`
- turn-local `finish_reason`

Must not own:

- setup draft truth
- review/commit truth
- activation truth

Invariants:

- runtime state can guide the next turn
- runtime state can be invalidated/rebuilt
- runtime state cannot silently overwrite business truth
- transient trace is not persisted as product truth or setup governance snapshot unless a future spec explicitly promotes it

Tests/checks:

- user draft edits invalidate/reconcile runtime aids without losing business truth
- loop trace captures reason codes without exposing private diagnostics as transcript
- runtime state persistence remains scoped to setup runtime, not active-story memory
- persisted runtime-governance snapshots do not grow `loop_trace` or `continue_reason` fields under the current active loop semantics spec

## 12. Contract Spine Acceptance

The architecture slice is ready for implementation only when:

- A1 can name the contract owner for every changed behavior.
- A2 can add/change a tool by starting from CapabilityPlan.
- Existing specs and HLD agree that transition rules live inside `SetupTurnLoop`.
- Prompt/schema/allowlist/event drift has a planned test failure surface.
- No implementation slice requires accepting `setup.world_background.*` earlier than planned.
