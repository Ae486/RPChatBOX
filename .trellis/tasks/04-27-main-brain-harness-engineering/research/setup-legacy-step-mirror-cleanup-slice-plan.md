# Setup Legacy Step Mirror Cleanup Slice Plan

> Status: implementation plan  
> Scope: F3 cleanup after canonical target-stage ingress convergence  
> Date: 2026-05-06

## Goal

- Reduce the real dual-track migration debt without widening scope into a full setup redesign.

## Source

- `.trellis/spec/backend/rp-setup-target-stage-turn-entry-contract.md`
- `.trellis/spec/backend/rp-setup-legacy-step-mirror-convergence.md`
- current code review of `SetupWorkspaceService._advance_current_stage(...)`, provider bridge helpers, and canonical-stage context fallback

## Real Problems This Slice Fixes

- `current_step` can become stale after canonical stage progression crosses a legacy step bucket
- stage-to-step bridge logic is duplicated in multiple setup components

## Non-Goals

- no stage-specific patch tool family
- no handoff redesign
- no deletion of legacy draft mirrors / old storage models
- no eval schema widening

## Implementation

- add a single authoritative `legacy_step_for_stage(...)` helper on `SetupWorkspaceService`
- make `_advance_current_stage(...)` also synchronize `workspace.current_step`
- replace local handwritten stage-to-step maps in setup provider / context builder with delegation to the workspace-service authority
- add/adjust targeted tests for lifecycle mirror advancement and shared bridge usage

## Verification

- targeted pytest:
  - `backend/rp/tests/test_setup_stage_module_draft_contract.py`
  - `backend/rp/tests/test_setup_tool_provider.py`
  - other directly affected setup tests if needed
- targeted `ruff check`
- targeted `mypy --follow-imports=skip --check-untyped-defs`
