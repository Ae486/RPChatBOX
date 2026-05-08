# Research: setup-f4-eval-stage-skillpack-integration

- Query: Research Setup F4 only: eval-module integration for stage-aware / SkillPack-aware setup assertions. Answer five concrete questions using current repo code, especially `backend/rp/eval` and task `04-30-skills-builder`.
- Scope: internal
- Date: 2026-05-06

## Findings

### Files found

- `backend/rp/eval/models.py` - Eval case / run / trace / artifact / score contracts.
- `backend/rp/eval/runner.py` - Setup eval execution path and run-level metadata capture.
- `backend/rp/eval/trace_capture.py` - Setup trace root-span attributes and setup-specific artifacts.
- `backend/rp/eval/graders/deterministic.py` - Existing generic deterministic assertion engine and setup diagnostic expectation grading.
- `backend/rp/eval/diagnostics.py` - Existing setup diagnostics dimensions, reason codes, outcome chain, and recommended next action synthesis.
- `backend/rp/eval/reporting.py` - Existing report projection and diagnostic expectation result attachment.
- `backend/rp/models/setup_agent.py` - Setup turn request already carries `target_stage`.
- `backend/rp/services/setup_agent_execution_service.py` - Canonical stage-first turn selection and validation.
- `backend/rp/graphs/setup_graph_state.py` / `backend/rp/graphs/setup_graph_runner.py` / `backend/rp/graphs/setup_graph_nodes.py` - Graph-shell propagation of `target_stage`.
- `backend/rp/models/setup_handoff.py` - `SetupContextBuilderInput` / `SetupContextPacket` / handoff stage fields.
- `backend/rp/services/setup_context_builder.py` - Context packet and prior-stage handoff selection already resolve canonical stage.
- `backend/rp/agent_runtime/adapters.py` - Runtime turn input assembly, current stage exposure, tool scope selection, metadata payload.
- `backend/rp/agent_runtime/profiles.py` - Current stage-aware tool scope contract; no SkillPack registry hook yet.
- `backend/rp/services/setup_agent_prompt_service.py` - Current prompt still uses `_stage_overlay(current_stage or current_step)`.
- `.trellis/spec/backend/rp-eval-setup-case-contracts.md` - Current setup eval case contract.
- `.trellis/spec/backend/rp-setup-target-stage-turn-entry-contract.md` - F1/F2 stage-ingress contract now codified.
- `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md` - Current tool-scope contract and deferred SkillPack note.
- `.trellis/tasks/04-30-skills-builder/prd.md` - Proposed SkillPack runtime contract and explicit eval follow-up deferral.
- `.trellis/tasks/04-27-main-brain-harness-engineering/research/setup-stage-followup-convergence-slice-plan.md` - F4 was already framed as eval enrichment after ingress stability.

### 1. What exact eval contract fields already exist for setup cases and traces?

Setup case contract already exists and is not setup-stage-specific yet:

- `EvalCase` top-level fields: `case_id`, `title`, `scope`, `category`, `tags`, `runtime_target`, `input`, `preconditions`, `expected`, `trace_hooks`, `repeat`, `baseline`, `metadata` (`backend/rp/eval/models.py:136-149`).
- `EvalInput`: `request`, `workspace_seed`, `env_overrides`, `diagnostic_profile` (`backend/rp/eval/models.py:45-52`).
- `EvalExpected` currently exposes:
  - `deterministic_assertions`
  - `subjective_hooks`
  - `expected_reason_codes`
  - `expected_primary_suspects`
  - `expected_outcome_chain`
  - `expected_recommended_next_action`
  (`backend/rp/eval/models.py:82-110`, `.trellis/spec/backend/rp-eval-setup-case-contracts.md:12-19`)
- `EvalTraceHooks` currently exposes:
  - `capture_runtime_events`
  - `capture_graph_debug`
  - `capture_workspace_before_after`
  - `capture_activation_snapshot`
  - `capture_tool_sequence`
  (`backend/rp/eval/models.py:112-120`)

Setup-specific enforcement already exists only for diagnostics, not for stage / SkillPack identity:

- Setup bad-path cases must provide non-empty `expected_reason_codes`, `expected_outcome_chain`, and `expected_recommended_next_action`; `expected_primary_suspects` remains optional (`.trellis/spec/backend/rp-eval-setup-case-contracts.md:21-40`, `backend/rp/tests/test_eval_setup_cognitive_cases.py:473-477`).
- Deterministic diagnostic grading already checks:
  - `diagnostics.reason_codes`
  - `diagnostics.attribution.primary_suspects`
  - `diagnostics.outcome_chain`
  - `diagnostics.recommended_next_action`
  (`backend/rp/eval/graders/deterministic.py:39-91`)

Trace contract already exists generically plus setup-specific root-span attributes and artifacts:

- Generic trace objects:
  - `EvalRun`: `run_id`, `case_id`, `scope`, `status`, `started_at`, `finished_at`, `runtime_target`, `baseline_tags`, `trace_id`, `failure`, `metadata` (`backend/rp/eval/models.py:164-177`)
  - `EvalSpan`: `span_id`, `trace_id`, `parent_span_id`, `name`, `span_kind`, `status`, `started_at`, `finished_at`, `input`, `output`, `attributes`, `error` (`backend/rp/eval/models.py:191-205`)
  - `EvalArtifact`: `artifact_id`, `run_id`, `kind`, `name`, `content_type`, `payload` (`backend/rp/eval/models.py:208-216`)
  - `EvalTrace`: `trace_id`, `spans`, `events` (`backend/rp/eval/models.py:236-241`)
  - `EvalRunResult`: `case`, `run`, `trace`, `artifacts`, `scores`, `runtime_result`, `report` (`backend/rp/eval/models.py:244-254`)

Setup root span already carries stage-aware fields:

- Root span attributes include `target_step`, `target_stage`, `setup_step`, `setup_stage`, `finish_reason`, `repair_route`, `continue_reason`, `loop_trace_count`, `context_profile`, context-governance counters, and cognitive-state summary booleans/counts (`backend/rp/eval/trace_capture.py:33-106`).
- Tool-call spans already exist as child spans with tool name, raw tool name, call id, source round, input arguments, normalized output, and tool error payload (`backend/rp/eval/trace_capture.py:110-139`).

Setup artifacts already exposed to eval/reporting:

- Always: `runtime_result`
- Optional: `tool_sequence`, `cognitive_state_summary`, `cognitive_state`, `loop_trace`, `context_report`, `workspace_before`, `workspace_after`, `readiness_snapshot`, `graph_debug`, `activation_check`, `activation_handoff_snapshot`
  (`backend/rp/eval/trace_capture.py:141-276`)

Run-level metadata already persists setup-stage ingress signal:

- `EvalRun.metadata` for setup currently includes `workspace_id`, `story_id`, `setup_step`, `target_stage`, `model_id`, `provider_id`, `stream_mode`, `diagnostic_profile` (`backend/rp/eval/runner.py:318-335`).

Important consequence:

- The eval system already has enough structure to record stage-aware truth.
- What it does not have yet is a first-class expected field or setup-specific scorer for stage / SkillPack assertions.

### 2. What stage-aware truth is already available after F1/F2?

After F1/F2, canonical stage truth is already available across request, graph shell, launch resolution, context assembly, runtime input, and eval traces.

Ingress / request:

- `SetupAgentTurnRequest` already carries both `target_step` and canonical `target_stage` (`backend/rp/models/setup_agent.py:21-31`).
- The backend spec now defines `target_stage` as canonical interactive selection and `target_step` as compatibility mirror (`.trellis/spec/backend/rp-setup-target-stage-turn-entry-contract.md:15-35`, `:39-79`).

Graph shell:

- `SetupGraphState` already has `target_stage: str | None` (`backend/rp/graphs/setup_graph_state.py:7-12`).
- `SetupGraphRunner._initial_state` copies `request.target_stage` into graph state (`backend/rp/graphs/setup_graph_runner.py:155-162`).
- `SetupGraphNodes._request_from_state` reconstructs `SetupAgentTurnRequest.target_stage` from graph state (`backend/rp/graphs/setup_graph_nodes.py:78-90`).

Turn launch / validation:

- `SetupAgentExecutionService._resolve_turn_selection(...)` validates:
  - `target_stage` must belong to `workspace.stage_plan`
  - `target_stage` and `target_step` must match legacy mapping when both are present
  - effective `current_stage` resolves stage-first
  - effective `current_step` maps from stage when needed
  (`backend/rp/services/setup_agent_execution_service.py:184-210`)
- Tests already prove:
  - default `current_stage` comes from workspace (`backend/rp/tests/test_setup_agent_execution_service_v2.py` case `uses_current_stage_metadata`)
  - `target_stage` overrides workspace stage (`...uses_target_stage_override`)
  - mismatched `target_stage` / `target_step` is rejected
  - out-of-plan `target_stage` is rejected
  (`backend/rp/tests/test_setup_agent_execution_service_v2.py:759-863`, `:923-1023`)

Context packet / handoff:

- `SetupContextBuilderInput` includes `current_stage`
- `SetupContextPacket` includes `current_stage`
- `SetupStageHandoffPacket` includes `from_stage`, `to_stage`, `stage_id`
  (`backend/rp/models/setup_handoff.py:21-29`, `:53-72`, `:76-88`)
- `SetupContextBuilder` resolves canonical stage, uses it when collecting prior-stage handoffs, and writes it into the context packet (`backend/rp/services/setup_context_builder.py:28-48`, `:87-98`, `:137-215`).

Runtime turn input:

- `SetupRuntimeAdapter` computes `selected_stage` from `request.target_stage` first, else from packet/workspace compatibility (`backend/rp/agent_runtime/adapters.py:67-80`).
- `RpAgentTurnInput.context_bundle` already exposes:
  - `current_step`
  - `current_stage`
  - `step_state`
  - `stage_state`
  - `step_readiness`
  - `stage_readiness`
  - `prior_stage_handoff_steps`
  - `prior_stage_handoff_stages`
  (`backend/rp/agent_runtime/adapters.py:131-227`)
- `tool_scope` already keys off stage when stage is available (`backend/rp/agent_runtime/adapters.py:112-117`, `:227`).

Eval-visible truth:

- Setup trace root span already records `target_stage` and `setup_stage` (`backend/rp/eval/trace_capture.py:51-61`).
- Setup run metadata already records `target_stage` (`backend/rp/eval/runner.py:321-328`).

Bottom line:

- F1/F2 already delivered the canonical stage truth F4 needs.
- F4 does not need to invent a new stage-observability path; it only needs to assert against existing surfaces.

### 3. Does runtime already expose any SkillPack truth? If not, where would it need to surface from?

Short answer: no implemented SkillPack runtime truth is present in current backend code.

What is present today:

- Tool scope has a canonical-stage hook point, but `SETUP_STAGE_PATCH_TOOLS` is still an all-empty map, and `build_setup_agent_tool_scope(...)` has no SkillPack lookup (`backend/rp/agent_runtime/profiles.py:38-70`).
- Prompt assembly still only uses `_stage_overlay(current_stage or current_step)`; there is no SkillPack render slot, no `[Stage Skill Pack: ...]` marker, and no specialist-hat injection (`backend/rp/services/setup_agent_prompt_service.py:15-23`, `:71`, `:86`).
- `RpAgentTurnInput.metadata` currently only contains `model_name` and `provider`; no `stage_id`, no `skill_pack_name`, no prompt marker metadata (`backend/rp/agent_runtime/adapters.py:228-231`).
- Repo search found no `backend/rp/services/setup_stage_skill_packs` directory and no `.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`. Both are still absent on disk as of this research.

What exists only as PRD / planned truth:

- Task `04-30-skills-builder` proposes `backend/rp/services/setup_stage_skill_packs/registry.py` plus per-stage `SKILL.md` files and a `SkillPackRecord` with `name`, `stage_id`, `description`, `body`, `required_tools_stage_specific` (`.trellis/tasks/04-30-skills-builder/prd.md:138-213`, `:285-290`).
- The PRD explicitly proposes surfacing `stage_id` and `skill_pack_name` in `RpAgentTurnInput.metadata` for trace/eval (`.trellis/tasks/04-30-skills-builder/prd.md:298-305`, `:433`).
- The PRD also explicitly defers SkillPack eval cases to a later task under `backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json` (`.trellis/tasks/04-30-skills-builder/prd.md:415`).

Therefore, if SkillPack truth is to become assertable, it should surface from these concrete runtime-owned places, in this order:

1. `setup_stage_skill_packs` registry:
   - source of truth for pack identity (`name`) and tool whitelist (`required_tools_stage_specific`)
2. `SetupAgentPromptService.build_system_prompt(...)`:
   - inject a deterministic pack marker into system prompt or a parallel prompt-debug field
3. `build_setup_agent_tool_scope(...)`:
   - choose stage-specific tool scope from pack metadata
4. `SetupRuntimeAdapter.build_turn_input(...)`:
   - write `stage_id` and `skill_pack_name` into `RpAgentTurnInput.metadata`
   - optionally copy a cheap `skill_pack_applied: bool` / `skill_pack_tools` hint into `context_bundle` for debugging
5. Trace capture / runner metadata:
   - root span attributes and `EvalRun.metadata` should mirror `skill_pack_name` if present

Important boundary:

- SkillPack truth must come from runtime-owned assembly, not from a second eval-only inference layer.
- Eval should read the same runtime truth the model actually saw, not try to guess SkillPack activation after the fact.

### 4. What is the minimal, additive F4 design that fits the existing eval architecture instead of creating a parallel system?

Minimal F4 should reuse the existing eval architecture in two layers, not add a new “SkillPack eval subsystem”.

#### F4-A: stage-aware assertions now, using existing sources and scorers

This can land immediately because stage truth already exists.

Recommended minimal additions:

- Keep `EvalExpected` and the current report/trace object model intact.
- Add only optional setup-specific expected keys for common stable stage checks, for example:
  - `expected_target_stage: str | None`
  - `expected_effective_stage: str | None`
- Grade them in the existing `evaluate_diagnostic_expectation_scores(...)` path or, even smaller, lower them into generated deterministic assertions against existing paths.

Why this is additive and cheap:

- Existing deterministic assertions already support path-based checks against `runtime_result`, `runtime_events`, `workspace_truth`, `workspace_before`, and `graph_debug` (`backend/rp/eval/graders/deterministic.py:19-36`, `:312-327`).
- Existing traces already expose `run.metadata.target_stage` and root-span `attributes.target_stage/setup_stage`.
- No new trace type, no new artifact family, no new separate runner is needed.

Recommended assertion source of truth preference:

1. `run.metadata.target_stage` for ingress intent
2. root span `attributes.setup_stage` for effective stage used by the turn
3. optional deterministic assertions against `runtime_result.structured_payload.request_context.current_stage` only if runtime already exposes it stably

#### F4-B: SkillPack-aware assertions later, but still inside existing architecture

Once runtime truth exists, add only optional expected keys, for example:

- `expected_skill_pack_name: str | None`
- `expected_prompt_markers: list[str]`
- `expected_stage_tool_scope_contains: list[str]`
- `expected_stage_tool_scope_excludes: list[str]`

These should still grade through the existing machinery:

- path-based deterministic assertions for prompt/debug/tool-scope surfaces
- or one small extension to `evaluate_diagnostic_expectation_scores(...)` for common stable scalar/list fields

What not to do:

- do not create a separate SkillPack-specific runner
- do not create a parallel trace format
- do not add a second eval artifact tree that duplicates `EvalTrace` / `EvalArtifact`
- do not make eval infer SkillPack activation from assistant prose alone

Concrete recommended implementation shape:

1. Extend `EvalExpected` with optional stage/SkillPack expectation fields only.
2. Extend static coverage tests only for fields that should be mandatory. For F4, none of the new fields should be mandatory globally.
3. In runner/trace/reporting, keep existing objects; only mirror newly available runtime metadata.
4. In grading, either:
   - translate new fields into deterministic path assertions internally, or
   - add 2-4 more expectation checks next to reason code / outcome chain alignment.

This preserves the current architecture:

- one case contract
- one runner
- one trace model
- one generic deterministic engine
- one setup-diagnostic expectation layer

### 5. What should be deferred until SkillPack runtime truth exists?

These items should be explicitly deferred:

- Any `expected_skill_pack_name` assertion before runtime really emits `skill_pack_name`.
- Any prompt-marker assertion before prompt assembly has a deterministic, stable SkillPack marker or debug surface.
- Any tool-scope assertion that depends on `required_tools_stage_specific` before the SkillPack registry actually drives `build_setup_agent_tool_scope(...)`.
- Any eval case family under `backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json` before a real SkillPack can be applied by runtime.
- Any subjective or RAGAS-style “did the persona feel like character-design.v1” judging. That is strictly later than deterministic runtime-truth exposure.
- Any “SkillPack unload” assertion before runtime can surface old/new pack identity across adjacent turns.
- Any mode × stage matrix assertions before the PRD’s future `mode × stage` registry actually exists (`04-30` PRD explicitly says Pilot stays single-keyed by `SetupStageId`).

Practical sequencing recommendation:

1. F4 now: stage-aware eval enrichment only, using current `target_stage` / `setup_stage` truth.
2. SkillPack runtime slice: registry + prompt injection + tool-scope hook + adapter metadata + trace metadata.
3. F4 follow-up: add optional SkillPack expectation keys and the first `setup/skill_pack/character_design` cases.

### Minimal recommendation summary

- Current eval architecture is already sufficient for F4.
- Canonical stage truth is already present end-to-end after F1/F2.
- SkillPack truth is not implemented yet; only PRD-level design exists.
- Therefore the smallest correct F4 is:
  - assert stage-aware setup behavior now using existing trace/run metadata
  - reserve SkillPack assertions as optional additive fields once runtime surfaces real `skill_pack_name` and pack-driven prompt/tool-scope truth
  - do not create any parallel eval system

## Caveats / Not Found

- No implemented `setup_stage_skill_packs` runtime package was found in the current repo.
- No backend spec file for stage SkillPack runtime (`.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`) was found.
- No current eval cases under `backend/rp/eval/cases/setup/skill_pack/**` were found.
- Current setup eval contracts do not yet contain first-class stage or SkillPack expectation keys; only generic deterministic assertions plus diagnostics expectations exist.
