# RP Eval Setup Case Contracts

> Executable contract for setup bad-path eval cases and their diagnostic expectations.

## Scenario: Setup Bad-Path Case Expectations

### 1. Scope / Trigger
- Trigger: add or edit files under `backend/rp/eval/cases/setup/**` or tests that execute setup eval cases.
- Scope: setup offline eval case JSON contract, especially `expected.*` diagnostic fields used by deterministic attribution grading.

### 2. Signatures
- Case file location: `backend/rp/eval/cases/setup/<family>/*.json`
- Contract fields inside `expected`:
  - `deterministic_assertions: []`
  - `subjective_hooks: []`
  - `expected_reason_codes: [str]`
  - `expected_primary_suspects: [str]`
  - `expected_outcome_chain: {stage: status}`
  - `expected_recommended_next_action: str | null`

### 3. Contracts
- Every setup bad-path case must define:
  - non-empty `expected_reason_codes`
  - non-empty `expected_outcome_chain`
  - non-empty `expected_recommended_next_action`
- `expected_primary_suspects` is optional for assertion purposes:
  - use a non-empty list when the case has a stable primary suspect
  - leave it empty when the current contract intentionally does not lock primary suspect attribution
- Expected diagnostics should assert stable, high-signal fields:
  - use the distinctive reason code(s), not necessarily every reported reason code
  - use key `outcome_chain` stages, not necessarily the full chain
  - prefer the remediation string actually used by diagnostics output
- Repair-success cases still count as bad-path coverage if the run first goes through repair or contract failure before recovery.

### 4. Validation & Error Matrix
- Missing `expected_reason_codes` -> static coverage test fails before runtime drift hides the omission.
- Missing `expected_outcome_chain` -> static coverage test fails.
- Missing `expected_recommended_next_action` -> static coverage test fails.
- Wrong expected value -> runtime case execution fails because `diagnostic_expectation_results` adds assertion failures.
- Unstable primary suspect -> keep `expected_primary_suspects` empty instead of locking a flaky attribution guess.

### 5. Good/Base/Bad Cases
- Good: a commit-blocked case asserts `controller.commit_proposal_blocked`, `readiness_status=warn`, and `tighten_commit_readiness_checks_and_review_block_messages`.
- Base: a cognitive invalidation case asserts only the stable cognition reason code, key chain stages, and the remediation action; it leaves primary suspects empty.
- Bad: a setup case only keeps deterministic assertions and omits diagnostic expectations, so compare/report can show diagnostics but the case never checks them.

### 6. Tests Required
- `rp/tests/test_eval_setup_cognitive_cases.py`
  - static coverage test must assert every setup case defines reason code, outcome chain, and next-action expectations
  - runtime parametrized cases must still pass with `assertion_summary.fail == 0`
- `rp/tests/test_eval_diagnostics.py`
  - update expectation-score assertions when a case gains a new expected diagnostic dimension such as recommended next action

### 7. Wrong vs Correct
#### Wrong
- Add a new setup case with only `deterministic_assertions`, assuming the report output is enough.
- Lock `expected_primary_suspects` for a case whose current attribution is intentionally left flexible.

#### Correct
- Add stable `expected_reason_codes`, `expected_outcome_chain`, and `expected_recommended_next_action` for every setup bad-path case.
- Only assert `expected_primary_suspects` when the case has a stable, intended attribution surface.
