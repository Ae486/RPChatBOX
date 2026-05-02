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

## Scenario: Setup Real-Model Behavior Eval Opt-In

### 1. Scope / Trigger
- Trigger: add or edit setup eval tests that call a real model/provider instead of a deterministic fake LLM service.
- Scope: setup behavior eval tests only. Real-model execution must never become a default local or CI dependency.

### 2. Signatures
- Opt-in env:
  - `CHATBOX_RUN_REAL_SETUP_AGENT_COMPACT_EVAL=1`
  - `CHATBOX_REAL_SETUP_EVAL_MODEL_NAME`
  - `CHATBOX_REAL_SETUP_EVAL_API_KEY`
  - optional `CHATBOX_REAL_SETUP_EVAL_PROVIDER_TYPE`, default `openai`
  - optional `CHATBOX_REAL_SETUP_EVAL_API_URL`, default `https://api.openai.com/v1`
  - optional `CHATBOX_REAL_SETUP_EVAL_PROVIDER_ID`
  - optional `CHATBOX_REAL_SETUP_EVAL_MODEL_ID`

### 3. Contracts
- Default local/CI runs must skip the real-model test before any network or paid call.
- The test may seed a temporary provider/model registry from env, but must not require the user's durable app registry.
- For local manual validation, the test may also use an existing durable registry model when `CHATBOX_REAL_SETUP_EVAL_MODEL_ID` is provided. This path is still opt-in and must not run by default.
- When both full env-seeded provider/model config and an existing durable registry model id are available, the full env-seeded config takes precedence and keeps its own `provider_id` / `model_id` values.
- A durable local registry fallback must never re-seed an entry whose `api_key` or `model_name` is empty; those are skip conditions, not safe defaults.
- The seeded model must be marked setup-compatible for tool calling through registry capabilities/profile.
- Real-model assertions must be behavior-level and trace/tool based; do not rely only on subjective answer quality.
- The real behavior chain must include an actual model-driven draft write before recovery:
  - first turn calls a draft-writing setup tool, such as `setup.truth.write`, and the draft contains the exact hidden detail afterward
  - second turn triggers compact with the exact detail absent from prompt-visible messages and compact summary prose
  - second turn requires that exact detail and must call `setup.read.draft_refs` before using it
- A first failed draft-write call followed by runtime schema repair and a successful retry is acceptable and should be observable, because this matches the setup-agent repair contract for missing Pydantic fields.
- Plain assistant responses from OpenAI-compatible providers may serialize `tool_calls` as `null`; runtime must treat that as no tool call rather than crashing.

### 4. Validation & Error Matrix
- Opt-in env disabled -> skip.
- Required model name or API key missing -> skip.
- Existing local registry model id provided and found -> use that model/provider without copying secrets into test code.
- Existing local registry entry exists but its `api_key` or `model_name` is empty -> skip instead of re-seeding blank values.
- Full env-seeded provider/model config provided together with `CHATBOX_REAL_SETUP_EVAL_MODEL_ID` -> prefer the env-seeded config and do not let the durable registry branch override it.
- First-round prompt-visible messages contain the exact hidden detail -> test invalid, fail before model delegation.
- Old trimmed raw-history marker remains prompt-visible -> fail.
- Recovery ref/hint is absent from prompt-visible context -> fail.
- Real-model first interaction does not eventually write the foundation draft -> fail.
- `setup.read.draft_refs` is not called with the expected ref before final use of the detail -> fail.
- Tool result lacks the exact detail or final answer does not use it -> fail.

### 5. Good/Base/Bad Cases
- Good: compact context exposes `foundation:magic-law` and `recovery_hints`, hides the exact detail, the model calls `setup.read.draft_refs(detail="full")`, and the final answer uses the returned detail.
- Good: the first real-model draft write initially omits a required field, the runtime repair loop corrects it, and the final successful tool result writes `foundation:magic-law` before the compact recovery turn.
- Good: a full env-seeded test config can coexist with a durable local registry model id, and the env-seeded config wins without leaking blank registry secrets.
- Base: no real-model env is configured, so the test is reported as skipped with no network call.
- Bad: a real-model test runs by default, uses a checked-in API key, or passes because the exact detail leaked into the first model prompt.

### 6. Tests Required
- The opt-in test must assert case validity before delegating to the real model:
  - exact detail absent from first-round prompt-visible message content
  - old raw-history marker absent
  - recovery ref/hint visible
  - `setup.read.draft_refs` tool schema visible
- The behavior assertion must inspect runtime result tool invocations/results and final assistant text.
- The behavior assertion must inspect both turns:
  - write turn: model invoked a draft-write tool and the workspace draft contains the exact detail afterward
  - recovery turn: model-visible prompt hides the exact detail, exposes only ref/hint, invokes `setup.read.draft_refs`, and final answer uses the readback
- If a durable registry fallback is used, the test should assert that the loaded provider/model config is complete before seeding and that no blank secret fields are written back.

### 7. Wrong vs Correct
#### Wrong
- Add a normal pytest that always reaches a real provider.
- Treat "compact mode" alone as proof that readback happened.
- Seed the hidden draft detail directly and call that a real interaction test.

#### Correct
- Keep deterministic tests as the default engineering proof, and add real-model behavior evals behind explicit env opt-in with trace/tool assertions.
- Exercise the real setup loop with a model-driven draft write before compact recovery.
