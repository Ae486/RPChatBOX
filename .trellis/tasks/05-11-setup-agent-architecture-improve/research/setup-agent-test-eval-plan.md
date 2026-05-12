# SetupAgent Architecture Test / Eval Plan

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 verification plan

## 1. Goal

Tests should prove architecture ownership, not just current file names.

The test plan must catch the old failure family:

- pseudo tool text visible as assistant content
- real tool calls leading to recursion-limit failure
- recoverable tool validation errors shown to the user before repair
- prompt/schema/allowlist drift
- candidate tools exposed accidentally
- internal/debug/provider text leaking into typed SSE transcript

## 2. A0 Verification

A0 is docs/spec only.

Required checks:

```powershell
python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve
git diff --check -- .trellis/tasks/05-11-setup-agent-architecture-improve
```

Backend tests:

- not required during A0 because backend implementation files are not modified

## 3. A1 Test Plan: Loop / Output / Repair

Target contracts:

- `SetupTurnLoop`
- `OutputInspector`
- `SetupToolRuntime`
- `SetupEventSink`

Required cases:

| Case | Expected assertion |
| --- | --- |
| model emits pseudo tool text | pseudo text is not assistant content; loop enters repair or terminal budget path |
| repeated pseudo tool text | explicit finish reason before graph recursion limit |
| model emits real setup tool call | tool executes through runtime; result observation is appended |
| successful tool result satisfies obligations | turn stops with business finish reason, not graph recursion |
| recoverable schema/tool error | structured error becomes model observation; user does not see terminal failure immediately |
| retry budget exhausted | structured terminal failure with public-safe event and private diagnostics |
| malformed tool call | bounded repair or structured failure, not raw stack trace |
| empty output | retry/provider failure path, not blank success |

Likely test files:

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
- new focused `test_setup_agent_output_inspector.py` if the contract becomes explicit in code

## 4. A2 Test Plan: CapabilityPlan

Target contracts:

- `SetupCapabilityPlan`
- prompt/schema/allowlist consistency
- candidate tool fail-closed exposure

Required cases:

| Case | Expected assertion |
| --- | --- |
| stage default capability snapshot | active tools, schema modes, allowlist, guidance match expected stage |
| step override narrows tool set | narrowed allowlist and prompt guidance agree |
| turn safety filter disables tool | schema and allowlist both reflect disabled state |
| prompt mentions unavailable tool | test fails |
| schema exposes tool not in allowlist | test fails |
| provider registers candidate tool | hidden from model and runtime unless plan exposes it |
| `setup.world_background.*` candidate tools | remain hidden until a separate product/tool slice accepts them |
| accepted shared/read tools | `setup.truth.write`, setup question/commit/read helpers, and `setup.read.draft_refs` remain visible where active specs require them |

Likely test files:

- `backend/rp/tests/test_setup_agent_tool_scope.py`
- `backend/rp/tests/test_setup_agent_prompt_service.py`
- focused capability snapshot tests

## 5. A3 Test Plan: ContextPipeline

Target contracts:

- `SetupContextPipeline`
- SkillPack prompt-only boundary
- runtime state aids vs business truth

Required cases:

| Case | Expected assertion |
| --- | --- |
| final request message ordering | deterministic packet/history/overlay/prompt order |
| governed history compaction | required draft refs remain available through readback or retained context |
| SkillPack stage overlay | prompt changes, tool scope does not |
| retained tool outcome | enters context as observation/history aid, not workspace truth mutation |
| user draft edit | runtime digest/cognition reconciles or invalidates without overwriting draft truth |
| final prompt assembly | consumes CapabilityPlan guidance and does not mention tools outside active plan |

Likely test files:

- context builder/governor tests
- prompt service tests
- runtime adapter tests

## 6. A4 Test Plan: ModelGateway / EventSink

Target contracts:

- `ModelGateway`
- `OutputInspector`
- `SetupEventSink`

Required cases:

| Case | Expected assertion |
| --- | --- |
| streamed tool-call chunks | reconstructed into normalized tool call before inspection |
| provider schema error | attributed to provider/gateway, not business completion |
| upstream model error | public-safe terminal event, private diagnostics retained |
| raw provider deltas | never emitted as assistant content |
| tool start/result events | remain typed SSE events |
| pseudo/debug text | private only |

Likely test files:

- executor stream tests
- typed SSE adapter tests
- fake provider gateway tests if extracted

## 7. A5 Test Plan: RuntimeStateStore

Target contracts:

- runtime cognition/state
- loop trace
- workspace truth separation

Required cases:

| Case | Expected assertion |
| --- | --- |
| loop trace records repair | trace has reason codes and private diagnostics; transcript does not |
| finish/continue reasons export | reason taxonomy available for result payload, eval, and diagnostics without governance-snapshot persistence |
| user edit invalidates state | runtime aid is invalidated/reconciled; business draft remains user-edited truth |
| compact summary persisted | scoped to setup runtime and not active-story memory |
| runtime governance snapshot | does not grow `loop_trace` or `continue_reason` under current active specs |

Likely test files:

- runtime state service tests
- eval diagnostics tests

## 8. C Test Plan: Setup Lightweight Readback Boundary

Target contracts:

- `SetupLightweightReadback`
- `SetupTruthIndexService`
- setup-owned draft/committed truth readback
- retrieval-core materialization boundary

Required cases:

| Case | Expected assertion |
| --- | --- |
| compact recovery needs draft detail | agent-visible read surface is `setup.read.draft_refs`, not Memory OS / retrieval-core |
| committed truth search | `setup.truth_index.search` returns small lexical/path/filter candidate refs and previews |
| committed truth exact read | `setup.truth_index.read_refs` returns bounded exact payload slices after refs are selected |
| editable draft changed after commit | truth-index search/read ignores uncommitted draft changes |
| accepted setup truth materializes to retrieval | retrieval seed sections preserve setup anchors without becoming setup draft readback |
| retrieval materialization pending/fails | setup stage progression is not blocked and no SetupAgent retrieval tool becomes visible |

Likely test files:

- `backend/rp/tests/test_setup_tool_provider.py`
- `backend/rp/tests/test_setup_truth_index_service.py`
- `backend/rp/tests/test_minimal_retrieval_ingestion_service.py`
- capability/tool-scope tests if a future readback tool becomes model-visible

Current C conclusion:

- No new backend test was required for this roadmap slice because the accepted surfaces already exist and active specs already require their behavior.
- Future code changes in this area must prove they keep setup-owned exact readback separate from retrieval-core semantic/runtime retrieval.

## 9. D Test Plan: SkillPack Governance

Target contracts:

- SkillPack prompt/context packaging
- hard-unload on stage change
- metadata-only `skill_pack_name`
- CapabilityPlan / tool-scope decoupling

Required cases:

| Case | Expected assertion |
| --- | --- |
| registered stage pack | character_design prompt contains the pack marker and specialist preamble |
| other stage / no stage | no pack marker, no preamble, and no pack residue |
| pack active | `metadata.skill_pack_name` and trace root `skill_pack_name` match the runtime-owned value |
| pack unloaded | `skill_pack_name` is `None`; no inference from stage id or assistant prose |
| pack active with tool scope | `SetupCapabilityPlan`, `tool_scope`, runtime allowlist, and `setup.truth.write` injection are unchanged |
| prompt guidance | tool guidance remains sourced from CapabilityPlan and filters inactive tool references |
| context boundaries | `skill_pack_name` and `context_pipeline` remain metadata/debug surfaces and do not enter `context_bundle` or durable setup truth |

Likely test files:

- `backend/rp/tests/test_skill_packs_registry.py`
- `backend/rp/tests/test_setup_agent_prompt_service.py`
- `backend/rp/tests/test_setup_agent_tool_scope.py`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
- `backend/rp/tests/test_eval_trace_capture.py`
- `backend/rp/tests/test_eval_diagnostics.py`

Current D conclusion:

- Existing code/tests already satisfy the governance boundary; this slice only
  records the architecture status and closes D.
- Future SkillPack additions must be content-only unless a separate product/tool
  slice explicitly changes CapabilityPlan or business contracts.

## 10. Offline Eval Plan

Use offline evals only after contract tests prove boundaries.

Eval dimensions:

- pseudo tool leakage
- recoverable tool repair
- stage-aware capability exposure
- truth-write validation recovery
- typed event transcript safety
- finish/continue reason attribution

Expected reporting should separate:

- provider/gateway failure
- model failed to emit real tool call
- model emitted pseudo tool text
- tool schema validation failure
- setup business terminal failure
- successful strict/slim schema path

This separation is required so compatibility failures are not misreported as architecture success/failure.

## 11. Optional Live Model Smoke

Live model smoke is opt-in and should not gate A0.

When used later:

- run a narrow setup turn with a fake or disposable workspace
- verify real tool call path
- verify recoverable error observation path
- verify typed SSE public transcript
- record provider/model/version/date in eval output

Do not use live model smoke as the only proof. Contract tests remain primary.

## 12. Quality Gate Per Slice

Each implementation slice should report:

- changed contracts
- changed files
- focused tests run
- skipped tests and reason
- known residual risk
- whether `.trellis/spec/backend/` needs update

For A0 docs-only work, the quality gate is task validation, diff check, and internal consistency review.
