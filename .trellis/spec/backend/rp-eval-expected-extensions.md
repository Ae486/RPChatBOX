# RP Eval Expected Extensions

> Executable contract for the optional `EvalExpected` extension fields that map agent runtime truth onto declarative case-level assertions, replacing ad-hoc JSONPath checks.

## Scenario: Setup eval cases declare stage-aware truth via typed fields rather than JSONPath

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/eval/models.py::EvalExpected`, `backend/rp/eval/graders/deterministic.py::evaluate_diagnostic_expectation_scores`, `backend/rp/eval/reporting.py::build_report`, or case JSONs under `backend/rp/eval/cases/setup/**` when the change introduces or consumes additive scalar / list-shaped diagnostic expectations sourced from runtime trace or runtime result.
- Applies to setup eval (`scope = "setup"`) diagnostic expectation grading only. Retrieval and activation scopes are unchanged.
- This contract is additive on top of `rp-eval-setup-stage-skillpack-assertion-contract.md` (which §2 already reserves `expected_skill_pack_name`). It binds the runtime data sources for the four new fields, the score-name conventions, and the report shape that `attach_diagnostic_expectation_results` produces.

### 2. Signatures

- `EvalExpected` fields (all optional, additive, default `None` / empty list):
  - `expected_skill_pack_name: str | None`
  - `expected_finish_reason: str | None`
  - `expected_tool_calls_contains: list[str]`
  - `expected_tool_calls_excludes: list[str]`
- `evaluate_diagnostic_expectation_scores(...)`
  - emits one `EvalScore` per non-default field
  - score names (string-literal, public surface):
    - `diagnostic.skill_pack_name_alignment`
    - `diagnostic.finish_reason_alignment`
    - `diagnostic.tool_calls_contains_alignment`
    - `diagnostic.tool_calls_excludes_alignment`
- `build_report(...)`
  - adds `report["tool_calls"]: list[str]` derived from `runtime_result["tool_invocations"]` via `normalize_tool_name`
  - leaves all existing fields byte-identical
- `attach_diagnostic_expectation_results(...)`
  - emits one extra key `violations: list[str] | None` per result, sourced from disjoint-grader metadata; `None` for graders that do not produce violations

### 3. Contracts

#### 3.1 Each Field Owns Exactly One Data Source

| Field | Source | Helper |
|---|---|---|
| `expected_skill_pack_name` | `trace_root_attributes["skill_pack_name"]` (already populated by `trace_capture.py:71` per `rp-setup-agent-stage-skill-pack.md` §3.7a) | `_evaluate_expected_value` |
| `expected_finish_reason` | `report["finish_reason"]` (already populated by `reporting.build_report`) | `_evaluate_expected_value` |
| `expected_tool_calls_contains` | `report["tool_calls"]` (normalized, no `rp_setup__` prefix) | `_evaluate_expected_list_subset` |
| `expected_tool_calls_excludes` | `report["tool_calls"]` | `_evaluate_expected_list_disjoint` |

- The grader must not infer SkillPack identity from prompt content, assistant text, or stage id alone — only the trace attribute is authoritative. This is the same anti-inference rule as `rp-eval-setup-stage-skillpack-assertion-contract.md` §3.3.
- Tool names in cases and assertions use the normalized surface (e.g. `setup.truth.write`, `setup.world_background.write_entry`), not the runtime-prefixed `rp_setup__setup.truth.write`. The normalization helper lives in `eval/trace_capture.py::normalize_tool_name` and is imported by `eval/reporting.py`.

#### 3.2 List-Shape Graders Use Different Helpers For Contains vs Excludes

- `_evaluate_expected_list_subset(expected=...)` — passes when every expected tool appears in actual; metadata key `missing`.
- `_evaluate_expected_list_disjoint(forbidden=...)` — passes when no forbidden tool appears in actual; metadata key `violations`.
- Both reuse `_normalize_string_list` so leading/trailing whitespace and non-string entries are handled consistently with existing `expected_reason_codes` / `expected_primary_suspects` graders.

#### 3.3 Field Absence Is Not An Assertion

- When a field is left at its default (`None` for scalars, `[]` for lists), the grader emits no score for it. The score appender uses `is not None` / truthiness checks (consistent with existing `expected_target_stage` / `expected_reason_codes` patterns).
- This keeps the 4 new fields strictly optional and means every existing setup case continues to grade identically when it does not opt in.

#### 3.4 Report Shape Stays Additive

- `build_report` adds `tool_calls` between `finish_reason` and `repair_route`. No field renames, no positional reordering of existing keys. Existing consumers of the report (cli, comparison, langfuse_sync, reporting markdown) read by key and are unaffected.
- `attach_diagnostic_expectation_results` adds `violations` between `mismatches` and `source`. Existing tests must be updated to include `"violations": None` in dict-equality assertions for non-disjoint scores; this is the only intrusive coupling and is intentional (the assertion shape is a contract surface, not an internal).

#### 3.5 No New Grader Class, No New Scoring Subsystem

- All four fields are implemented as additions to `evaluate_diagnostic_expectation_scores` and reuse `_evaluate_expected_value` / `_evaluate_expected_list_subset` / the new `_evaluate_expected_list_disjoint`.
- This contract forbids:
  - new grader classes
  - a parallel SkillPack-only scoring pipeline
  - moving the new fields out of `EvalExpected` into a sub-model
- The forbid list aligns with `rp-eval-setup-stage-skillpack-assertion-contract.md` §3.1.

### 4. Validation & Error Matrix

| Condition | Expected Handling |
| --- | --- |
| field omitted (default) | no score emitted for that field |
| scalar expected matches actual | score status `pass` |
| scalar expected mismatches actual or actual is `None` | score status `fail`, severity `error` |
| `expected_tool_calls_contains` set; every expected tool is in `report["tool_calls"]` | score status `pass`, metadata `missing=[]` |
| `expected_tool_calls_contains` set; some tools missing | score status `fail`, metadata `missing=[…]` |
| `expected_tool_calls_excludes` set; no forbidden tool in `report["tool_calls"]` | score status `pass`, metadata `violations=[]` |
| `expected_tool_calls_excludes` set; one or more forbidden tools present | score status `fail`, metadata `violations=[…]` |
| `runtime_result["tool_invocations"]` missing / malformed | `report["tool_calls"]` is `[]`; downstream graders behave as if no tool was called |
| runtime emitted prefixed `rp_setup__...` tool names | `report["tool_calls"]` strips the prefix; case assertions use the unprefixed names |

### 5. Tests Required

- `backend/rp/tests/test_eval_diagnostics.py`
  - one parametrized test per new field exercising pass + fail + null-actual paths
  - the existing `test_diagnostic_expectation_scores_include_stage_alignment` assertion shape must include `"violations": None` for non-disjoint scores
- `backend/rp/tests/test_eval_trace_capture.py`
  - existing skill_pack_name propagation tests remain valid (already added in skills-builder Slice B)

### 6. Wrong vs Correct

#### Wrong

- Putting tool-name assertions inside `deterministic_assertions` with hand-crafted JSONPath into `runtime_result.tool_invocations` — too brittle, no normalization, and bypasses the explicit field surface.
- Adding the four fields under a nested `EvalExpected.skill_pack: SkillPackExpectation` sub-model — fragments the contract surface; existing graders cannot consume it without a parallel pipeline.
- Inferring `skill_pack_name` from prompt content, assistant text, or stage id when the runtime trace omitted it; this would mask runtime regressions instead of surfacing them.
- Storing the prefixed `rp_setup__setup.truth.write` form in case JSON — locks cases to a runtime-internal detail that may change.

#### Correct

- Use `expected_tool_calls_contains` / `expected_tool_calls_excludes` for tool inclusion / exclusion, with unprefixed names sourced from `eval/trace_capture.normalize_tool_name`.
- Use `expected_skill_pack_name` only when the runtime owns the trace attribute (Slice B onward); for stages without a SkillPack, set `expected_skill_pack_name = None` (or omit; equivalent).
- Use `expected_finish_reason` instead of a generic `equals` JSONPath into `runtime_result.finish_reason`; named field reads cleaner in case JSON and propagates into the diagnostic expectation summary.
