# RP Eval Setup Stage And SkillPack Assertion Contract

> Executable contract for extending the existing setup eval module with stage-aware assertions now, and SkillPack-aware assertions only after runtime-owned SkillPack truth exists.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/eval/models.py`, `backend/rp/eval/runner.py`, `backend/rp/eval/trace_capture.py`, setup eval deterministic grading, setup eval case JSON under `backend/rp/eval/cases/setup/**`, or tests for setup eval loading / trace capture / deterministic scoring when the change affects setup eval assertions about stage identity or future SkillPack identity.
- Applies only to the existing setup eval module under `backend/rp/eval`.
- This slice must extend the current eval architecture. It must not introduce a parallel “SkillPack eval” subsystem, custom trace format, or separate runner.
- Source:
  - Existing eval architecture already provides `EvalCase`, `EvalExpected`, deterministic path assertions, setup diagnostics scoring, setup root-span attributes, and setup artifacts.
  - F1/F2 already made canonical `target_stage` and effective `setup_stage` visible in setup request handling, runtime metadata, and setup traces.
  - Earlier F4 planning reserved SkillPack assertions until runtime-owned pack truth existed. The current runtime now exposes `skill_pack_name` as metadata-only truth; pack-driven tool-scope metadata remains out of scope.

## 2. Signatures

- Existing setup eval contract remains:
  - `EvalCase`
  - `EvalInput`
  - `EvalExpected`
  - `EvalTraceHooks`
  - `EvalRun`
  - `EvalTrace`
  - `EvalArtifact`
- F4 additive `EvalExpected` fields:
  - `expected_target_stage: str | None = None`
  - `expected_effective_stage: str | None = None`
  - optional SkillPack field, enabled only because runtime now owns trace truth:
    - `expected_skill_pack_name: str | None = None`
  - future-only optional fields, not required in this slice:
    - `expected_skill_pack_markers: list[str] = []`
    - `expected_stage_tool_scope_contains: list[str] = []`
    - `expected_stage_tool_scope_excludes: list[str] = []`
- Existing setup trace truth surfaces reused:
  - `EvalRun.metadata["target_stage"]`
  - setup root span attributes:
    - `target_stage`
    - `setup_stage`
- Existing deterministic grading reused:
  - generic `deterministic_assertions`
  - setup diagnostics expectation scoring

## 3. Contracts

### 3.1 F4 Lives Inside The Existing Eval Module

- Setup stage / SkillPack evaluation must reuse:
  - the current `EvalCase` JSON structure
  - the current `EvalRun` / `EvalTrace` / `EvalArtifact` model family
  - the current `EvalRunner._run_setup_case(...)`
  - the current deterministic grading pipeline
- Do not add:
  - a separate SkillPack-only runner
  - a second setup trace schema
  - a second assertion language

### 3.2 Stage-Aware Assertions Are Enabled Now

- Because canonical stage truth is already present after F1/F2, setup eval may now assert:
  - ingress stage intent through `run.metadata["target_stage"]`
  - effective stage used by the turn through root-span `attributes["setup_stage"]`
- `expected_target_stage` and `expected_effective_stage` are optional additive fields:
  - they are not mandatory for all existing setup cases
  - they should be populated only when the case is intentionally stage-sensitive

### 3.3 SkillPack Assertions Are Now Authoritative (Slice B Unblocked Runtime Truth)

- Eval must not infer SkillPack activation from:
  - assistant prose style
  - guessed prompt content
  - stage id alone
- Runtime now owns the SkillPack truth surface:
  - `RpAgentTurnResult.structured_payload["skill_pack_name"]` is populated by the runtime executor from `RpAgentTurnInput.metadata["skill_pack_name"]` (set by `SetupRuntimeAdapter` per `rp-setup-agent-stage-skill-pack.md` §3.7a)
  - `EvalTrace` root span `attributes["skill_pack_name"]` is populated by `trace_capture.build_setup_trace` from that structured payload
  - `EvalExpected.expected_skill_pack_name` consumes the trace attribute (see `rp-eval-expected-extensions.md`)
- SkillPack-aware assertions are therefore allowed as of skills-builder Slice B; cases under `backend/rp/eval/cases/setup/skill_pack/<stage>/*.json` may pin `expected_skill_pack_name`.

### 3.3a SkillPack Cases Are Exempt From Diagnostic-Attribution Shape Contract

- Cases with `category == "skill_pack"` test SkillPack persona / forbidden / facilitation alignment via the additive `EvalExpected` field surface and (in Stage 3) `subjective_hooks` rubrics. They do NOT test runtime diagnostic remediation.
- These cases are exempt from the all-cases shape contract (`test_all_setup_case_files_define_diagnostic_expectations`) that requires non-empty `expected_reason_codes`, `expected_outcome_chain`, and `expected_recommended_next_action`. The vocabulary of those fields (`tighten_tool_schema_and_error_messages`, `fix_provider_model_config_and_runtime_connectivity`, etc.) is diagnostic-attribution-shaped and does not apply.
- The exemption is implemented by skipping `category == "skill_pack"` in the validator. It must not be widened to other categories without an explicit spec update.

### 3.4 Reuse Existing Deterministic Assertion Machinery

- New stage-aware checks should prefer the existing deterministic machinery instead of adding a new scoring subsystem.
- Two acceptable implementation patterns:
  - translate `expected_target_stage` / `expected_effective_stage` into internal deterministic value checks
  - or add a small extension to setup diagnostic expectation grading for these scalar fields
- Keep the result shape inside the existing `EvalScore` model and reporting pipeline.

### 3.5 Setup Trace / Metadata Surfaces Stay Additive

- Setup root span attributes may be extended with future SkillPack truth once runtime owns it.
- `EvalRun.metadata` may also mirror future `skill_pack_name`.
- These are additive metadata enrichments only; they do not change the underlying setup runtime result contract.

### 3.6 Case Coverage Strategy

- The first SkillPack-aware case family lives under:
  - `backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json`
- The character_design pilot case (`pack_loaded_on_stage.v1.json`) is the reference fixture for the §3.7 rubrics; its mock assistant reply doubles as the pass-anchor reference.

### 3.7 SkillPack Subjective Rubric Vocabulary

- Three rubrics are registered in `eval/graders/judge_registry._RUBRICS` for SkillPack persona evaluation; all share `judge_family = "llm_judge"`, `prompt_version = "llm-judge/v2"`, `response_schema_version = "judge-response/v2"`, `metadata = {"scope": "setup", "target_type": "assistant_text"}`:
  - `setup/persona-alignment/v1` — judges whether the reply speaks from the SkillPack Specialist hat (e.g. senior dramatist for character_design) instead of a generic AI-assistant voice.
  - `setup/forbidden-compliance/v1` — judges whether the reply triggers any SkillPack `## Forbidden` clause (narrative prose, claim of stage readiness, auto-commit, mutating other-stage drafts).
  - `setup/facilitation-depth/v1` — judges whether clarifications probe deep dimensions named by the SkillPack (e.g. `motivation.real`, `world_fit`, contradiction) rather than surface traits.
- Rubric anchors are calibrated against the D-pilot mock assistant reply (the Stage 2 reference fixture). Authors of future SkillPack cases must keep this anchor convention: each new SkillPack mock reply must remain a coherent pass-anchor for these three rubrics, or new rubrics must be authored with their own concrete reference replies.
- MVP gate (mock-judge): each rubric must produce a structured `EvalScore` with the right band when fed scripted judge payloads (3 positive + 2 negative); see `test_skill_pack_persona_alignment_score_band_assignment`. Real-LLM consistency (≥ 0.85 across N>=5 dialog samples) is a Stretch goal tracked separately and is not blocking for this contract.
- Forbid:
  - introducing a rubric whose anchors are abstract descriptions without at least one concrete reference reply,
  - reusing an existing rubric ref for a new rubric version (use `setup/<rubric>/v2` instead),
  - judging SkillPack compliance via `deterministic_assertions` alone — these rubrics own the subjective surface.

## 4. Validation & Error Matrix

| Condition | Expected Handling |
| --- | --- |
| setup case has no stage-sensitive intent | new stage expectation fields may remain omitted |
| setup case sets `expected_target_stage` | grading checks `run.metadata.target_stage` |
| setup case sets `expected_effective_stage` | grading checks setup trace root-span `attributes.setup_stage` |
| runtime exposes `target_stage` but not `skill_pack_name` | stage-aware assertions allowed; SkillPack assertions remain absent |
| case sets `expected_skill_pack_name` before runtime truth exists | reject in static validation or treat as unsupported for this slice |
| future runtime exposes `skill_pack_name` | extend trace/metadata and then enable SkillPack-aware deterministic checks through the same eval architecture |

## 5. Good / Base / Bad Cases

Good:

- A setup case targeting `character_design` asserts `expected_target_stage="character_design"` and `expected_effective_stage="character_design"` using existing eval run metadata and root-span attributes.

Base:

- Existing setup repair / guard / commit bad-path cases continue to rely only on diagnostics expectations and generic deterministic assertions.

Bad:

- Add a new “SkillPack eval” subsystem that duplicates `EvalCase`, `EvalTrace`, or deterministic scoring.
- Assert that a SkillPack was active purely because the stage was `character_design`.

## 6. Tests Required

- `backend/rp/tests/test_eval_case_loader.py`
  - validate new optional stage-aware fields load correctly
- `backend/rp/tests/test_eval_trace_capture.py`
  - stage-aware trace attributes remain present and readable for setup cases
- setup eval deterministic tests
  - add focused coverage for stage-aware expected-field grading once implemented
- future SkillPack runtime slice
  - only after runtime truth exists, add tests proving `skill_pack_name` or equivalent trace metadata is emitted before enabling SkillPack-aware eval assertions

## 7. Wrong vs Correct

Wrong:

- Build a second eval framework just for SkillPack behavior.
- Add SkillPack assertions before runtime exposes `skill_pack_name` or equivalent truth.
- Force every setup eval case to declare stage expectations even when the case is not stage-sensitive.

Correct:

- Extend the current eval module incrementally.
- Assert canonical stage identity now because the runtime already exposes it.
- Defer SkillPack assertions until runtime-owned SkillPack metadata exists.
