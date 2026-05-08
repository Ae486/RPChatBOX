# RP Eval Setup Stage And SkillPack Assertion Contract

> Executable contract for extending the existing setup eval module with stage-aware assertions now, and SkillPack-aware assertions only after runtime-owned SkillPack truth exists.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/eval/models.py`, `backend/rp/eval/runner.py`, `backend/rp/eval/trace_capture.py`, setup eval deterministic grading, setup eval case JSON under `backend/rp/eval/cases/setup/**`, or tests for setup eval loading / trace capture / deterministic scoring when the change affects setup eval assertions about stage identity or future SkillPack identity.
- Applies only to the existing setup eval module under `backend/rp/eval`.
- This slice must extend the current eval architecture. It must not introduce a parallel “SkillPack eval” subsystem, custom trace format, or separate runner.
- Source:
  - Existing eval architecture already provides `EvalCase`, `EvalExpected`, deterministic path assertions, setup diagnostics scoring, setup root-span attributes, and setup artifacts.
  - F1/F2 already made canonical `target_stage` and effective `setup_stage` visible in setup request handling, runtime metadata, and setup traces.
  - Current repo does not yet implement runtime-owned SkillPack truth such as `skill_pack_name`, pack marker metadata, or pack-driven tool-scope metadata.

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
  - future-only optional fields, not required in this slice:
    - `expected_skill_pack_name: str | None = None`
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

### 3.3 SkillPack Assertions Must Wait For Runtime-Owned Truth

- Eval must not infer SkillPack activation from:
  - assistant prose style
  - guessed prompt content
  - stage id alone
- SkillPack-aware assertions are blocked until runtime exposes real SkillPack truth, such as:
  - `skill_pack_name`
  - stable prompt/debug markers
  - pack-driven tool-scope metadata
- Before that runtime truth exists, F4 must not add setup cases that pretend SkillPack assertions are authoritative.

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

- Immediate F4 coverage should focus on stage-aware setup cases only.
- The first SkillPack-aware case family belongs under:
  - `backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json`
- That family must remain deferred until runtime-owned SkillPack truth is implemented.

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
