# Setup Agent diagnostics eval contract

## Goal

Continue the SetupAgent diagnostics eval work as an eval-module-only task. The goal is to make offline setup eval cases declare expected diagnostic attribution, then verify, report, compare, and eventually mirror those diagnostics consistently with the online Langfuse setup scores.

## Requirements

* Keep the scope on `backend/rp/eval`, eval cases, eval tests, and Langfuse score alignment surfaces that are directly related to setup eval diagnostics.
* Support case-level diagnostic expectations such as expected reason codes, primary suspects, outcome-chain status, and recommended next action where applicable.
* Ensure deterministic grading can compare generated diagnostics against case expectations without polluting the diagnostics-generation path itself.
* Ensure reports expose diagnostic expectation results in a machine-readable JSON shape and a human-readable summary.
* Ensure compare output can detect diagnostic attribution drift across baseline/current reports.
* Preserve the RAGAS boundary: RAGAS remains retrieval/RAG-specific and must not block SetupAgent first-stage diagnostics.
* Do not modify setup runtime business truth, typed SSE contracts, UI contracts, RP memory/block planning files, or unrelated core-state work.

## Acceptance Criteria

* [ ] Setup bad-path cases can declare expected diagnostics.
* [ ] Deterministic grader emits pass/fail signals for diagnostic expectation alignment.
* [ ] Report output includes diagnostic expectation results without changing the original attribution evidence.
* [ ] Compare output highlights reason-code, primary-suspect, outcome-chain, or recommended-action drift.
* [ ] Relevant eval tests pass.
* [ ] `trellis-check` is run before the task is considered complete.

## Definition of Done

* Eval implementation and tests match `13-setup-agent-diagnostics-and-attribution-development-spec.md`.
* RAGAS import behavior is not changed for this task unless explicitly requested.
* Verification results are recorded in the final handoff.
* Any reusable contract or lesson is captured via `trellis-update-spec` if it should persist beyond this task.

## Technical Approach

Use the existing offline eval pipeline as the source of truth: case models define expected diagnostics, runner captures evidence and builds normal reports, deterministic grading evaluates expectation alignment after diagnostics generation, reporting attaches the result, and comparison tracks drift. Keep runtime-side SetupAgent behavior frozen unless a test exposes an eval-only adapter issue.

## Out of Scope

* Story/runtime prose-quality evaluation.
* Phoenix as a renewed observability direction.
* General eval platform refactor.
* Retrieval sampled traces and RAGAS metrics beyond preserving existing boundaries.
* RP memory block planning or core-state read service changes.

## Technical Notes

* Primary handoff: `docs/research/rp-redesign/agent/agent-eval/codex-setup-agent-diagnostics-eval-handoff-2026-04-24.md`.
* Primary spec: `docs/research/rp-redesign/agent/agent-eval/13-setup-agent-diagnostics-and-attribution-development-spec.md`.
* Current worktree contains unrelated block/memory/core-state changes from another active task; do not revert or include them in this task.
