# SetupAgent Architecture Improve Completion Handoff

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Scope: completed architecture task covering A / B / C / D
>
> Audience: next task owner for SetupAgent feature/module optimization
>
> Date: 2026-05-12

## 1. Current Task Completion Status

This task is complete at the planned architecture-slice level.

Completed parts:

```text
[x] A  Architecture spine implementation and validation
[x] B  Tool module integration protocol / canonical draft-write path
[x] C  Setup lightweight retrieval roadmap
[x] D  SkillPack governance
```

No blocking `$grill-me` question remains for this task.

This task did not try to finish every future module cleanup. It established the
architecture contracts, proved the most important boundaries through code/tests,
and wrote the rules that the next feature/module optimization task must follow.

## 2. What A Completed

A is the architecture-spine part. In the execution plan it was implemented as
A0-A5, but for the next task it should be read as one completed architecture
foundation.

Main outcomes:

- A0 froze the PRD, architecture audit, pi-mono / Claude Code lessons, grill
  decisions, target HLD, contract spine, implementation plan, and test/eval
  plan.
- A1 made the loop/output boundary real:
  - `OutputInspector` classifies model output before tool runtime or transcript
    visibility.
  - pseudo tool text cannot become public assistant content.
  - recoverable tool errors become structured observations before terminal user
    failure.
  - loop stop/continue reasons are explicit rather than falling into graph
    recursion behavior.
- A2 made `SetupCapabilityPlan` the single turn-level tool-surface spine:
  - prompt guidance, schema mode, runtime allowlist, active tools, and candidate
    exclusions now come from one plan.
  - provider registration does not expose a tool to the model.
  - `setup.world_background.*` remains candidate-only until a later product/tool
    task explicitly accepts it.
- A3 named and stabilized `SetupContextPipeline`:
  - context packet, governed history, compact summary, working digest, retained
    tool outcomes, prompt assembly, SkillPack layer, and final message order are
    separate surfaces.
  - `context_report` and `context_pipeline` are metadata/debug surfaces, not
    prompt content or durable truth.
- A4 hardened `ModelGateway` / `SetupEventSink` boundaries:
  - provider/stream/schema failures are attributed as model-gateway failures.
  - public SSE is allowlisted and strips private/provider/debug fields.
- A5 hardened runtime state truth levels:
  - durable runtime-state snapshots are root-field allowlisted.
  - transient/debug surfaces such as `loop_trace`, `continue_reason`,
    `output_inspection`, `event_sink`, and `model_gateway_diagnostics` cannot
    accidentally enter durable runtime governance state.

Reference lesson applied:

- pi-mono supplied the minimal vocabulary: session, context, loop, tools, events,
  state, continue/stop.
- Claude Code supplied mature module patterns: active tool filtering,
  output/transcript separation, context engineering, recovery transitions, and
  observability.
- Current SetupAgent code remained product-semantics evidence, not architecture
  authority.

## 3. What B Completed

B did not choose a new concrete CRUD family. It completed the tool integration
protocol.

Main outcomes:

- Tool modules are external capabilities, not hardwired loop internals.
- `SetupCapabilityPlan` owns exposure:
  - model-visible active tools
  - prompt guidance fragments
  - model schema mode
  - runtime allowlist
  - candidate exclusions
- `SetupToolProvider` owns provider-side tool authority:
  - schema validation
  - deterministic business validation
  - workspace reads/mutations
  - structured result/error payloads
- `RpAgentRuntimeExecutor` remains on the generic model tool-call protocol and
  the accepted `setup.truth.write` schema-adapter hook.
- Canonical model-visible draft writes stay on hardened slim `setup.truth.write`
  by default.
- `setup.world_background.*` is registered/provider-callable for future direct
  tests and product slices, but hidden from SetupAgent model scope by
  `SetupCapabilityPlan`.

Important invariant for next task:

```text
Provider registration != model exposure.
Prompt guidance != permission.
CapabilityPlan is the first place to change tool visibility.
ToolProvider is the first place to change deterministic tool execution.
```

## 4. What C Completed

C froze the setup-owned lightweight readback boundary.

Main outcomes:

- C is not "add RAG to SetupAgent".
- SetupAgent owns prestory editing readback:
  - `setup.read.draft_refs`
  - `setup.truth_index.search`
  - `setup.truth_index.read_refs`
  - `SetupTruthIndexService`
- `setup.read.draft_refs` reads exact current editable draft refs for compact
  recovery and current-stage detail recovery.
- `setup.truth_index.search` returns small lexical/path/filter candidate refs
  from accepted setup commits.
- `setup.truth_index.read_refs` reads bounded exact committed setup truth by
  selected refs.
- `SetupTruthIndexService` rebuilds deterministic committed truth rows from
  accepted snapshots only.
- Retrieval-core starts only after accepted setup truth is materialized into
  seed sections.
- Retrieval-core owns chunking, indexing, embeddings, hybrid/rerank,
  Recall/Archival search, and active-story runtime retrieval policy.

Important invariant for next task:

```text
Do not call Memory OS / retrieval-core to recover editable setup draft truth.
Do not make retrieval readiness block setup commit/stage progression.
Do not add model-visible retrieval tools unless a future product/tool task
accepts them through SetupCapabilityPlan.
```

## 5. What D Completed

D froze SkillPack governance.

Main outcomes:

- SkillPack is stage-keyed prompt/context packaging.
- SkillPack is not business authority, not tool-scope authority, and not a
  runtime policy layer.
- Selection is deterministic from resolved `SetupStageId`; the model never
  chooses or activates a SkillPack.
- SkillPack text enters the stable system prompt layer only.
- SkillPack hard-unloads on stage change by rebuilding the prompt from the new
  resolved stage.
- `skill_pack_name` is observability metadata only:
  - adapter metadata
  - runtime result structured payload
  - observation metadata
  - eval trace root attribute
- Eval must not infer SkillPack activation from prompt text, assistant text, or
  stage id alone.
- One small code fix was made in
  `backend/rp/agent_runtime/skill_packs/registry.py` to satisfy scoped mypy for
  multiline frontmatter parsing without changing behavior.

Important invariant for next task:

```text
SkillPack must not modify SetupCapabilityPlan, tool_scope, runtime allowlist,
setup.truth.write runtime injection, SetupWorkspace truth, runtime overlay,
context_bundle, or durable runtime state.
```

## 6. Verification Completed

This task used coherent-slice checks rather than running full repository checks
after every tiny edit.

Task-level / slice-level validation completed:

- A-stage implementation and check completed with focused pytest, ruff,
  py_compile, scoped mypy, task validation, and `trellis-check` per slice.
- B-stage validation:
  - `133 passed, 1 warning`
  - ruff passed
  - py_compile passed
  - scoped mypy passed
  - independent `trellis-check` found no findings after fixes.
- C-stage validation:
  - `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` passed
  - `git diff --check -- <C changed docs/specs>` had no whitespace errors;
    LF/CRLF warnings only
  - independent `trellis-check` found no findings.
- D-stage validation:
  - focused pytest: `103 passed, 1 xfailed, 2 warnings`
  - ruff passed
  - py_compile passed
  - scoped mypy passed
  - task validation passed
  - `git diff --check -- <D changed docs/code/tests>` had no whitespace errors;
    LF/CRLF warnings only
  - independent `trellis-check` found no findings.

Full import-following repository-wide mypy remains out of scope because of
existing repo type debt and missing stubs outside this task. Future tasks should
continue using scoped mypy unless they explicitly accept repo-wide type-debt
cleanup.

## 7. Required Pre-Reading For Next Task

The next feature/module optimization task should read these first.

Task-level architecture docs:

- `.trellis/tasks/05-11-setup-agent-architecture-improve/setup-agent-module-prd.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-target-architecture-hld.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-contract-spine-spec.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-implementation-slices.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-test-eval-plan.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-question-queue.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/pi-mono-claude-code-reference-lessons.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-current-architecture-audit.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-architecture-grounding-matrix.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-architecture-grill-decisions.md`

Active backend specs:

- `.trellis/spec/backend/rp-setup-agent-loop-semantics-react-trace.md`
- `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md`
- `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md`
- `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md`
- `.trellis/spec/backend/rp-setup-agent-structured-output-schema-repair.md`
- `.trellis/spec/backend/rp-setup-agent-strict-truth-write-tool-pilot.md`
- `.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md`
- `.trellis/spec/backend/rp-setup-truth-index-foundation.md`
- `.trellis/spec/backend/rp-setup-retrieval-seed-materialization.md`
- `.trellis/spec/backend/rp-eval-setup-stage-skillpack-assertion-contract.md`
- `.trellis/spec/backend/rp-eval-expected-extensions.md`

Core code:

- `backend/rp/agent_runtime/contracts.py`
- `backend/rp/agent_runtime/profiles.py`
- `backend/rp/agent_runtime/adapters.py`
- `backend/rp/agent_runtime/executor.py`
- `backend/rp/agent_runtime/events.py`
- `backend/rp/agent_runtime/policies.py`
- `backend/rp/agent_runtime/state.py`
- `backend/rp/agent_runtime/tools.py`
- `backend/rp/services/setup_agent_execution_service.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/services/setup_agent_runtime_state_service.py`
- `backend/rp/services/setup_context_builder.py`
- `backend/rp/services/setup_context_governor.py`
- `backend/rp/services/setup_context_compaction_service.py`
- `backend/rp/services/setup_truth_index_service.py`
- `backend/rp/services/minimal_retrieval_ingestion_service.py`
- `backend/rp/tools/setup_tool_provider.py`
- `backend/rp/agent_runtime/skill_packs/registry.py`

Focused tests to study before changing behavior:

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
- `backend/rp/tests/test_setup_agent_tool_scope.py`
- `backend/rp/tests/test_setup_agent_prompt_service.py`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
- `backend/rp/tests/test_setup_tool_provider.py`
- `backend/rp/tests/test_setup_world_background_tools.py`
- `backend/rp/tests/test_skill_packs_registry.py`
- `backend/rp/tests/test_setup_truth_index_service.py`
- `backend/rp/tests/test_minimal_retrieval_ingestion_service.py`
- `backend/rp/tests/test_eval_trace_capture.py`
- `backend/rp/tests/test_eval_diagnostics.py`

## 8. Recommended Next Task Options

The next task should be a separate feature/module optimization task. Do not keep
expanding this architecture task indefinitely.

Good next-task candidates:

1. Tool module/provider modularization
   - Split concrete setup tool families out of the growing provider surface.
   - Preserve the B-stage protocol: `SetupCapabilityPlan` controls exposure,
     `SetupToolProvider` / tool modules own schema/validation/execution.
   - Do not expose candidate tools by registration alone.

2. ModelGateway extraction
   - Move provider request construction, stream reconstruction, provider
     diagnostics, usage capture, and schema compatibility out of the executor
     into a clearer gateway boundary.
   - Preserve A4 failure attribution and EventSink public/private rules.

3. SetupTurnLoop extraction / loop readability
   - Make the loop phases more explicit without creating a large standalone
     `DecisionPolicy` god object.
   - Preserve A1 OutputInspector and bounded repair semantics.

4. ContextPipeline cleanup
   - Improve naming and file boundaries around context packet, governed
     history, compact summary, working digest, retained outcomes, prompt
     assembly, and runtime overlay.
   - Do not mix context truth with tool exposure or runtime state persistence.

5. SkillPack content expansion
   - Add or improve stage SkillPack content after D governance is frozen.
   - Keep SkillPack prompt-only and prove it does not change tool scope.

## 9. Next Task Rules

Next task owners should follow these rules:

- Start with one coherent module/function family, then run `trellis-check`.
- Use existing code as product-semantics evidence, not boundary authority.
- If pi-mono and Claude Code both point to a mature pattern and no current
  product contract forbids it, prefer the mature pattern.
- Do not do broad file moves first. Extract only when a contract owner remains
  scattered after behavior is proven.
- Do not run full repo mypy as a task gate unless that task explicitly accepts
  repo-wide type debt cleanup.
- If a question changes product semantics, stop and `$grill-me`.
- If a question is implementation mechanics and the docs/code/pi/Claude Code
  references answer it, decide and document instead of asking.
- Preserve the current user-confirmed boundaries:
  - prompt guidance is not permission
  - provider registration is not model exposure
  - runtime trace/cognition is not business truth
  - setup readback is not retrieval-core
  - SkillPack is not tool scope

## 10. Dirty Worktree Note

At completion time this repository contains many unrelated dirty files from
other workstreams. Do not treat every dirty file as part of this task.

The current task's relevant changed surfaces are concentrated in:

- `.trellis/tasks/05-11-setup-agent-architecture-improve/**`
- selected setup/eval backend specs under `.trellis/spec/backend/`
- SetupAgent runtime files touched by A/B/D implementation
- focused SetupAgent/eval tests touched by A/B/D implementation

Before committing, review the full git status and stage only files intended for
this task.
