# eval-modernization: align eval module with stage-native tool surface and SkillPack truth

## Goal

The `backend/rp/eval/` module is a mature, contract-bounded eval framework but its **content** (case JSONs, EvalExpected fields, judge rubrics) has drifted out of sync with the agent runtime:

1. After the `world_background` stage-native tool simplification, 9 cognitive cases + 2 suite_runner tests call tools that no longer appear in the resolved scope. These are currently `xfail` (deferred from skills-builder). They need redesign against the new tool surface.
2. After 9-stage migration and SkillPack pilot, `EvalExpected` exposes only `expected_target_stage` / `expected_effective_stage`; assertions on `skill_pack_name`, tool-call inclusion/exclusion, and explicit `finish_reason` still require ad-hoc JSONPath. Slice B of skills-builder unlocked the runtime-owned `skill_pack_name` truth — eval can now consume it.
3. `judge_registry` carries 3 rubrics covering clarification / query / handoff quality. SkillPack-specific evaluation dimensions (persona alignment, forbidden compliance, facilitation depth) have no rubric yet.

This task brings the eval **content** up to speed **without modifying the module's contract surface** — every change is an additive extension at a documented extension point.

## What I already know

- Eval module structure is stable and spec-bounded by `.trellis/spec/backend/rp-eval-setup-stage-skillpack-assertion-contract.md` §3.1 ("F4 Lives Inside The Existing Eval Module").
- Open extension points already enumerated in spec §2 and verified in code:
  - `EvalExpected` is a pydantic open class with `expected_target_stage` / `expected_effective_stage` already; spec §2 reserves `expected_skill_pack_name: str | None = None` as future-only.
  - `judge_registry._RUBRICS` is a plain dict at `backend/rp/eval/graders/judge_registry.py:34` — adding entries is the documented pattern.
  - `cases/setup/skill_pack/<stage_id>/*.json` path is reserved by spec §3.6.
  - `runner._apply_setup_seed:963-989` already iterates seed dict and is the natural place to honor a new `current_stage` seed field.
- 11 obsolete `xfail` cases land in three groups:
  - Group A (story_config / writing_contract / longform_blueprint legacy patch tool): `case0` only.
  - Group B (truth.write semantics tests): `case1, case8, case9, case10` — these mocks call `setup.truth.write` which is **not** in the world_background scope (the auto-seeded current_stage); explicit non-world_background `target_stage` should fix.
  - Group C (commit / discussion / proposal): `case3, case4, case5` — same root cause as Group B.
  - case2 (`_ExplainInsteadOfRepairSetupLLMService`) calls no tool, fails for a different reason — needs separate root-cause check.
- The two suite_runner xfails point at the same legacy `case0` file path; they will be unblocked by case0's redesign.
- Runtime data flow for `skill_pack_name` was wired in skills-builder Slice B:
  - `adapters.py:233` → `RpAgentTurnInput.metadata`
  - `executor.py:1674` → `RpAgentTurnResult.structured_payload`
  - `setup_agent_execution_service` → Langfuse observation metadata via `_runtime_v2_observation_metadata`
  - `trace_capture.py:71` → eval root span `attributes["skill_pack_name"]`

## Assumptions (temporary)

- world_background CRUD tools (`setup.world_background.*`) are stable enough for case mocks to call directly without further runtime changes.
- `setup.truth.write` is in scope for every non-world_background canonical stage (verified by `test_setup_agent_tool_scope.py` parametrize loop).
- LLM judge rubrics should target the same `prompt_version=llm-judge/v2` / `response_schema_version=judge-response/v2` already used by the 3 existing rubrics — no judge protocol changes.

## Open Questions

(none yet — to be filled by Q&A loop)

## Requirements (evolving)

(to be filled after Q&A)

## Acceptance Criteria (evolving)

- [ ] `pytest rp/tests/test_eval_*` migration rate: case0 (legacy patch) is deleted; the remaining truth.write / discussion / commit cases that drift on runtime classifier semantics may stay `xfail` as long as a single follow-up task (`05-11-runtime-classifier-drift`) owns the cluster and is referenced by the xfail reason. `skip` is not an acceptable substitute (it loses the "expected-to-pass-but-broken" signal).
- [ ] `EvalExpected` exposes new optional fields `expected_skill_pack_name`, `expected_tool_calls_contains`, `expected_tool_calls_excludes`, `expected_finish_reason` — each documented in `models.py` and each used in at least 1 case.
- [ ] `cases/setup/skill_pack/character_design/` contains at least 2 cases:
  - one pinning `expected_skill_pack_name = "character-design.v1"` when `target_stage = character_design`,
  - one verifying hard-unload when `target_stage` switches to a non-pack stage (e.g. `plot_blueprint`).
- [ ] `judge_registry._RUBRICS` exposes 3 new rubrics: `setup/persona-alignment/v1`, `setup/forbidden-compliance/v1`, `setup/facilitation-depth/v1`. Each has `prompt_version=llm-judge/v2` and is reachable via `list_judge_rubrics()`.
- [ ] At least 1 SkillPack case wires `subjective_hooks` to one of the new rubrics (smoke-tested via mock judge so CI does not require an actual LLM round-trip).
- [ ] `rp-eval-expected-extensions.md` spec exists and defines the 4 new field semantics, including their relationship to the existing `deterministic_assertions` JSONPath path.
- [ ] `rp-eval-setup-stage-skillpack-assertion-contract.md` §3.3 updated to remove the "blocked until runtime-owned SkillPack truth exists" caveat (Slice B unblocked it).
- [ ] `rp-setup-agent-stage-skill-pack.md` §3.7a remains aligned with `trace_capture.py:71` propagation path (no contract drift).

## Definition of Done

- Tests added/updated (unit/integration where appropriate).
- Lint (ruff) / typecheck / pytest green; no new xfail introduced.
- Specs updated where required (see Acceptance Criteria).
- Module contract surface unchanged: no new runner, no second trace schema, no second assertion language, no parallel SkillPack subsystem.

## Out of Scope (explicit, hard boundaries)

These items are **not** allowed in this task:

1. ❌ New SkillPack-only runner or second `_run_setup_case` path.
2. ❌ Second setup trace schema or second assertion language alongside `EvalCase` / `deterministic_assertions` / `subjective_hooks`.
3. ❌ Removing or renaming required fields on `EvalCase` / `EvalRun` / `EvalTrace` / `EvalArtifact`.
4. ❌ Changing `langfuse_sync` payload schema or `ragas_*` adapters.
5. ❌ Adding new case directories outside `backend/rp/eval/cases/`.
6. ❌ Modifying `trace_capture` root span attributes set (except spec-aligned additive extensions — already covered for `skill_pack_name`).
7. ❌ Net-new SkillPack content (e.g., second SkillPack for another stage). Only `character_design` pack remains in scope.
8. ❌ Designing eval-grade quality scoring (e.g. averaging across cohorts, regression bands). The task only adds judge rubrics; cohort analytics is a future task.
9. ❌ RAGAS coverage for setup eval. RAGAS stays confined to retrieval eval.

## Technical Approach

5-stage interleaved sequence (chosen over linear C→D→E→F to anchor LLM-judge rubrics on real mock outputs rather than abstract descriptions).

```
Stage 1: C            → field foundation (4 EvalExpected fields)
Stage 2: D-pilot      → 1 SkillPack pilot case whose mock LLM output exemplifies persona-aligned + forbidden-compliant behavior
Stage 3: E            → 3 rubrics calibrated against D-pilot's mock output as the concrete pass anchor
Stage 4: D-rest       → 9 xfail cases migrated to pass + 1 hard-unload SkillPack case
Stage 5: F (optional) → runner stage-only seed extension, only if Stage 4 surfaces the need
```

Each stage = one coherent spec slice = one `trellis-check` pass. Five checks total, not eleven (rules out per-edit checking) and not one (rules out a single end-of-task check that loses granularity).

### Stage 1 — `EvalExpected` field extension (~0.5d)

- `models.py`: add 4 optional fields (`expected_skill_pack_name`, `expected_tool_calls_contains`, `expected_tool_calls_excludes`, `expected_finish_reason`) with `None` / empty-list defaults.
- `runner.py` / `graders/deterministic.py`: thread the fields into the existing deterministic grading pipeline as additional `EvalAssertionSpec` instances (no new grader class, no new scoring path).
- Tests: 1 case per field demonstrating pass + fail.
- `trellis-check` gate: ruff / pytest / spec sync.

### Stage 2 — D-pilot: 1 SkillPack case (~0.3d)

- `cases/setup/skill_pack/character_design/pack_loaded_on_stage.v1.json`:
  - `target_stage = character_design`
  - `expected_skill_pack_name = "character-design.v1"`
  - `expected_target_stage = "character_design"` / `expected_effective_stage = "character_design"`
  - `expected_tool_calls_excludes = ["setup.patch.story_config", "setup.proposal.commit"]` (forbidden auto-commit)
- Mock LLM: assistant reply must (a) probe motivation depth (the SkillPack `## Clarification templates` direction), (b) reference `world_fit` or `motivation.real` dimension, (c) NOT contain narrative prose / scene writing.
- This mock reply text becomes the **concrete reference anchor** for Stage 3's `setup/persona-alignment/v1` and `setup/facilitation-depth/v1` rubrics.

### Stage 3 — Judge rubrics calibrated on D-pilot output (~1d)

3 new entries in `graders/judge_registry._RUBRICS`:

| Rubric | What it judges | Reference anchor |
|---|---|---|
| `setup/persona-alignment/v1` | reply tone / framing matches `## Specialist hat` (dramatist voice, not generic helper) | D-pilot mock reply (pass anchor) + a contrived "narrative scene writing" reply (fail anchor) |
| `setup/forbidden-compliance/v1` | reply + tool_calls do not trigger any `## Forbidden` clause (auto-commit, narrative prose, mutating other drafts, claiming "ready") | D-pilot mock reply (pass) + a contrived "I've locked this in, proposing commit" reply (fail) |
| `setup/facilitation-depth/v1` | clarification probes deep dimensions (`motivation.real` / `world_fit` / contradiction) rather than surface traits | D-pilot mock reply (pass) + a "what's the character's name?" reply (fail) |

- `test_eval_subjective_hooks.py`: 1 end-to-end mock-judge case wiring D-pilot's `subjective_hooks` to one of the rubrics.
- Acceptance: mock-judge in test passes 3 positive + 2 negative scripted assistant replies with 100% correct band assignment.

### Stage 4 — D-rest: case migration + hard-unload (~1d)

Split into two batches by complexity:

- **Batch 4a (simple, ~2h)**: 4 truth.write cases (`_TruthWriteAskUserLLMService`, `_TruthWriteTargetRefAutoRepairLLMService`, `_TruthWriteCreateConflictLLMService`, `_TruthWriteReplaceMissingLLMService`) — add explicit `target_stage = writer_config` (matches `_LEGACY_STEP_FOR_STAGE[WRITER_CONFIG] = WRITING_CONTRACT`); verify scope now includes `setup.truth.write`; un-xfail in parametrize.
- **Batch 4b (complex, ~3h)**: 5 cases (`_ExplainInsteadOfRepairSetupLLMService`, `_CommitBlockedQuestionLLMService` ×2, `_RejectedProposalDiscussionLLMService`, plus delete `_SchemaAutoRepairSetupLLMService` per D2). Each needs targeted debugging — case2 (Explain...) failed for a different reason than tool scope; root-cause first.
- **Hard-unload SkillPack case**: `cases/setup/skill_pack/character_design/pack_unloaded_on_other_stage.v1.json` — `target_stage = plot_blueprint`; assert `expected_skill_pack_name = None`.
- Suite_runner: switch from deleted `story_config_schema_auto_repair_success.v1.json` to `truth_write_target_ref_auto_repair_success.v1.json` (already exists); rewrite the locally-redeclared `_SchemaAutoRepairSetupLLMService` to a `setup.truth.write` mock; un-xfail both suite_runner tests.
- Acceptance: zero xfail in `rp/tests/test_eval_*`.

### Stage 5 — F (conditional)

Only triggered if Stage 4 surfaces a case that needs stage-only seeding (no `current_step` in seed). Defer; revisit at end of Stage 4.

## Decision (ADR-lite)

**Context**: After skills-builder, 11 eval cases drift from new agent tool surface; SkillPack truth is now runtime-owned but eval has no native assertion field for it. Need to modernize without breaking module contract.

**Decision**: 5-stage interleaved sequence (C → D-pilot → E → D-rest → F-conditional) instead of strict linear C→D→E→F. Rationale: LLM-judge rubric quality depends critically on calibration against concrete reference outputs; pulling 1 SkillPack pilot case ahead of rubric design gives rubric authors a concrete pass anchor instead of forcing abstract description.

**Consequences**:
- Pro: rubric anchors written against real mock data (data-anchored anchors, established LLM-judge best practice); 5 natural `trellis-check` gates; D-rest can use stabilized rubrics and field set without rework.
- Con: D is split (2 + 4 work units instead of 1 monolith); slightly more bookkeeping.
- Risk: D-pilot mock output quality determines rubric anchor quality → mitigated by mandating that the mock reply explicitly references the SkillPack body's `## Specialist hat` / `## Forbidden` / `## Facilitation principles` sections rather than being authored by intuition.
- Risk: real-LLM rubric consistency could still be poor even with mock-judge passing → mitigated by making real-LLM consistency a Stretch goal, not MVP gate; MVP gate is mock-judge 100% on 3 positive + 2 negative scripted replies.

## Research References

(none required — task is internal eval module extension; no external library decisions.)

## Technical Notes

- Spec contracts:
  - `.trellis/spec/backend/rp-eval-setup-stage-skillpack-assertion-contract.md` (especially §3.3 and §3.5)
  - `.trellis/spec/backend/rp-setup-agent-stage-skill-pack.md` §3.7a (trace propagation)
- Existing eval surface inspected during skills-builder audit:
  - `models.py` line 82 (`EvalExpected`)
  - `runner.py` line 963 (`_apply_setup_seed`)
  - `graders/judge_registry.py` line 34 (`_RUBRICS`)
  - `trace_capture.py` line 71 (`skill_pack_name` already wired)
  - `cases/setup/cognitive/*` `cases/setup/repair/*` `cases/setup/commit/*` `cases/setup/guard/*`
- Related skills-builder commits: `97dea1e` (archive) + `66068c9 runtime banch` (skill_pack_name plumbing).
