# setup runtime classifier and policy drift audit (recover eval xfail cases)

## Goal

A cluster of setup eval cases that test `setup.truth.write` schema-failure repair semantics still `xfail` after the eval-modernization Stage 4 stage-seed fix. Root cause is **not** tool scope (that was fixed in Stage 4) but a runtime classifier / policy shift in `ToolFailureClassifier` and the schema-retry budget:

- `RuntimeToolPolicies` finalizes failure on the *first* schema retry (`policies.py: schema_retry_count >= 1 -> finalize_failure: tool_schema_validation_failed`); cases were authored expecting the agent to do a bad → good round trip and finish `completed_text`.
- `ToolFailureClassifier.classify` defaults `SCHEMA_VALIDATION_FAILED` to `auto_repair` unconditionally; some cases were authored expecting `continue_discussion` / `ask_user` for empty payloads.

Cases affected (all `xfail` after Stage 4):
- `cases/setup/repair/writing_contract_ask_user_after_semantic_fail.v1.json` (mock: `_TruthWriteAskUserLLMService`)
- `cases/setup/repair/truth_write_target_ref_auto_repair_success.v1.json` (mock: `_TruthWriteTargetRefAutoRepairLLMService`)
- `cases/setup/repair/truth_write_create_requires_empty_target.v1.json` (mock: `_TruthWriteCreateConflictLLMService`)
- `cases/setup/repair/truth_write_replace_requires_existing_target.v1.json` (mock: `_TruthWriteReplaceMissingLLMService`)
- `cases/setup/guard/repair_obligation_false_success_blocked.v1.json` (mock: `_ExplainInsteadOfRepairSetupLLMService`)
- `cases/setup/commit/blocked_truth_write_not_ready.v1.json` (mock: `_CommitBlockedQuestionLLMService`)
- `cases/setup/commit/blocked_truth_write_open_issues.v1.json` (mock: `_CommitBlockedQuestionLLMService`)
- `cases/setup/commit/rejected_proposal_back_to_discussion.v1.json` (mock: `_RejectedProposalDiscussionLLMService`)

Plus 1 test that directly runs `writing_contract_ask_user_after_semantic_fail.v1`:
- `test_eval_diagnostics.py::test_setup_eval_report_includes_capability_and_diagnostic_summary`

## What needs to happen

For each affected case, decide one of:
1. **Update case expected_report** to match current runtime semantics (the runtime change is intentional).
2. **Revert runtime policy** to the original semantics (if the runtime change was unintentional).
3. **Retire the case** (if the runtime semantic no longer exists by design and the case cannot be repurposed).

Each decision requires:
- Reading `policies.py:ToolFailureClassifier` + `RuntimeToolPolicies.next_action` to understand the current decision tree.
- Reading the original PR / spec that introduced each case to recover original intent.
- Cross-checking against `rp-setup-agent-action-decision-policy.md` and `rp-setup-agent-loop-semantics-react-trace.md`.

## Out of Scope

- Eval module field surface changes (covered by `rp-eval-expected-extensions.md`).
- SkillPack rubric / pilot case design (covered by eval-modernization Stage 2 / 3).

## Acceptance

- [ ] Every affected case is decided as (1) updated / (2) reverted via runtime / (3) retired with a documented justification.
- [ ] `pytest rp/tests/test_eval_setup_cognitive_cases.py rp/tests/test_eval_diagnostics.py` shows 0 xfail (or all remaining xfail have a deeper-incident task linked).
- [ ] If runtime policy is reverted: regression tests in `test_setup_agent_runtime_policies.py` cover the new behavior.
- [ ] If cases are updated: each new expected_report shape is documented in the case JSON `metadata.semantic_drift_note` field.

## Technical Notes

- Stage 4 of eval-modernization (commit pending) already added `target_stage` to these case JSONs to unblock tool scope; the remaining failures are pure classifier/policy semantic drift, not scope.
- Trace of investigation: case8 (`truth_write_target_ref_auto_repair_success`) produces `finish_reason=tool_schema_validation_failed` / `repair_route=auto_repair`, expected `finish_reason=completed_text` / `repair_route=continue_discussion`. Root cause: `policies.py: if category == "auto_repair": if schema_retry_count >= 1: finalize_failure` caps retry budget at 1; case mock provides bad-then-good round trip that needs budget ≥ 2.
- Related spec files (read before deciding):
  - `.trellis/spec/backend/rp-setup-agent-action-decision-policy.md`
  - `.trellis/spec/backend/rp-setup-agent-loop-semantics-react-trace.md`
  - `.trellis/spec/backend/rp-setup-agent-strict-truth-write-tool-pilot.md`

## References

- Created during eval-modernization Stage 4 finalization.
- Caller task: `05-11-eval-modernization` (Stage 4 acceptance allows ≤ 2 xfail per PRD; this task absorbs the larger cluster as a single follow-up).
