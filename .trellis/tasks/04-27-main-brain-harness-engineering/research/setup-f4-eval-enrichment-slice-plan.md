# Setup F4 Eval Enrichment Slice Plan

> Status: implementation plan  
> Scope: eval-module follow-up after F1/F2/F3 setup runtime convergence  
> Date: 2026-05-06

## Goal

- Extend the existing setup eval module so it can assert canonical stage identity now, and SkillPack identity later once runtime truth exists.

## Source

- `.trellis/tasks/04-27-main-brain-harness-engineering/research/setup-f4-eval-stage-skillpack-integration.md`
- `.trellis/spec/backend/rp-eval-setup-case-contracts.md`
- `.trellis/spec/backend/rp-setup-target-stage-turn-entry-contract.md`
- current `backend/rp/eval` implementation

## What Is Ready Now

- setup eval already has:
  - stable `EvalCase` / `EvalExpected` / `EvalRun` / `EvalTrace` contracts
  - deterministic path assertions
  - setup diagnostics expectation scoring
  - root-span setup trace attributes
- F1/F2 already expose:
  - `run.metadata.target_stage`
  - root span `attributes.target_stage`
  - root span `attributes.setup_stage`

## What Is Not Ready Yet

- runtime-owned SkillPack truth is not implemented yet:
  - no `setup_stage_skill_packs` runtime package in repo
  - no `skill_pack_name` in runtime metadata / trace
  - no pack-driven tool-scope metadata exposed to eval

## Slice F4A: Stage-Aware Eval Enrichment

Goal:

- Let setup eval cases assert canonical stage intent and effective stage using already available runtime truth.

Implementation:

- extend `EvalExpected` with optional stage-aware expected fields
- extend setup eval grading to score those fields through the existing architecture
- add one or two focused setup eval tests / cases proving stage-aware assertions work

Verification:

- targeted eval loader / trace / deterministic tests

## Slice F4B: SkillPack-Aware Eval Enrichment

Goal:

- Add SkillPack-aware assertions only after runtime-owned SkillPack metadata exists.

Implementation precondition:

- SkillPack runtime slice must first expose:
  - `skill_pack_name`
  - stable prompt/debug marker or equivalent
  - pack-driven tool-scope metadata if that behavior should be asserted

Implementation once ready:

- extend `EvalExpected` with optional SkillPack fields
- mirror runtime-owned SkillPack metadata into setup trace / run metadata
- add the first `backend/rp/eval/cases/setup/skill_pack/<stage_id>/*.json`

Verification:

- targeted setup eval cases for one real SkillPack pilot stage

## Explicit Non-Goals

- no parallel SkillPack-only eval framework
- no prose-style or persona-quality judging before runtime truth exists
- no fake SkillPack assertions derived only from stage id
