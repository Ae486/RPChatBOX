# Setup Stage Follow-Up Convergence Slice Plan

> Status: implementation plan  
> Scope: post-stage-module cleanup for canonical stage turn ingress, coexistence rules, and remaining migration debt  
> Date: 2026-05-06

## Source And Boundary

This follow-up plan is based on:

- `.trellis/spec/backend/rp-setup-stage-module-draft-foundation-contract.md`
- `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md`
- `.trellis/spec/backend/rp-setup-agent-prior-stage-handoff-context.md`
- `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md`
- current code review of `SetupAgentTurnRequest`, `SetupGraphState`, setup runtime launch, tool provider bridges, and workspace dual-track models

Design source summary:

- User requirement: setup stage selection must remain canonical end-to-end so future SkillPack / stage-specific behavior can target `character_design` distinctly from `world_background`.
- Existing implementation fact: canonical stages already exist in workspace truth, context packets, handoffs, truth writes, truth index, and frontend rendering, but turn ingress still collapses selection into legacy `target_step`.
- Deliberate exclusion: this plan does not create one patch tool per stage. Shared `setup.truth.write` remains the intended stage write surface.

## Triage Summary

Real and priority-worthy:

- `A1` canonical `target_stage` is missing from turn ingress and graph shell
- migration coexistence rules are still implicit rather than codified in one place
- provider/runtime internals still contain legacy step bridges that should be reduced after ingress is fixed
- lifecycle mirror semantics remain dual-track and should be tightened after ingress is fixed

Real but later:

- eval contracts do not yet expose canonical stage/SkillPack-specific assertion keys

Not accepted as current blockers:

- stage-specific patch tool family per canonical stage
- handoff is still purely 4-stage
- frontend/backend wire protocol currently depends on camelCase stage ids

## Slice F1: Target Stage Turn Ingress Convergence

Goal:

- Carry canonical `target_stage` through setup turn request, graph shell, runtime launch, context assembly, tool scope, and traces.

Implementation:

- Add `target_stage` to `SetupAgentTurnRequest` and `SetupGraphState`
- Resolve effective `current_stage` from request before legacy `current_step`
- Keep `current_step` as a compatibility mirror by mapping from `target_stage` only where old code still needs it
- Update frontend request builder to submit canonical snake_case `target_stage`
- Update API/eval/trace payloads and targeted tests

Verification:

- API/runtime tests prove `character_design` does not collapse back to workspace `world_background`
- frontend request path emits snake_case `target_stage`

## Slice F2: Coexistence Authority Spec + Guard Rails

Goal:

- Freeze transition-period rules so new code uses one authority instead of ad hoc local decisions.

Implementation:

- Add one executable backend spec for:
  - `current_stage` as canonical signal when present
  - `current_step` as compatibility mirror
  - allowed mixed request payloads
  - mismatch validation
- Update task PRD and context manifests to point future implement/check agents at this rule

Verification:

- no codepath accepts contradictory `target_stage` / `target_step`
- new tests cover the mismatch rejection path

## Slice F3: Provider Dispatch / Lifecycle Mirror Cleanup

Goal:

- Reduce remaining legacy bridges after canonical turn ingress is fixed.

Implementation:

- review `_legacy_step_for_stage` and `_step_for_truth_block_type` call sites
- replace stage-to-step fallback with explicit canonical stage paths where possible
- tighten lifecycle state updates and comments so stage/step mirror semantics are obvious

Verification:

- targeted provider/lifecycle tests
- no silent fallback that erases canonical stage intent during write/commit paths

## Slice F4: Eval Enrichment For Stage/SkillPack Assertions

Goal:

- Add stage-aware assertion keys only after canonical ingress is stable.

Implementation:

- extend eval contracts with canonical stage identity and optional SkillPack hooks
- keep this separate from setup ingress convergence

Verification:

- eval fixtures can assert stage-aware behavior without relying on legacy step buckets

## Recommended Order

1. `F1` + `F2` together as the next coherent slice
2. `F3` after ingress is proven green
3. `F4` in eval / skills-builder follow-up work

## Explicit Non-Goals

- No one-tool-per-stage patch family
- No rewrite of handoff to a second new abstraction
- No immediate deletion of every legacy 4-step field before coexistence rules are stabilized
