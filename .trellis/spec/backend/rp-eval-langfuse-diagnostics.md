# RP Eval Langfuse Diagnostics

> Offline eval to Langfuse sync contract for setup diagnostics, suite summaries, and comparison drift.

## Scenario: Offline Eval Langfuse Sync

### 1. Scope / Trigger
- Trigger: `backend/rp/eval/langfuse_sync.py` or `backend/rp/observability/langfuse_scores.py` changes for offline replay, suite summary, comparison drift, or setup diagnostic score alignment.
- Scope: internal Langfuse sync metadata, observation output shape, and score names for setup eval diagnostics.

### 2. Signatures
- `emit_setup_trace_scores(observation, *, runtime_result, failure_layer=None, error_code=None, report=None)`
- `sync_suite_bundle_to_langfuse(*, suite_payload, summary, thresholds, comparison=None)`
- `sync_suite_summary_to_langfuse(*, suite_payload, summary, thresholds)`
- `sync_comparison_to_langfuse(*, comparison)`
- `sync_replay_to_langfuse(*, replay_payload)`

### 3. Contracts
- `emit_setup_trace_scores(..., report=...)` may read report-level diagnostic fields when replay sync has richer data than `runtime_result`.
- Supported top-level report fields:
  - `failure_layer`
  - `reason_codes`
  - `primary_suspects`
  - `secondary_suspects`
  - `recommended_next_action`
  - `outcome_chain`
  - `evidence_refs`
- Supported nested report fields:
  - `diagnostics.failure_layer`
  - `diagnostics.reason_codes`
  - `diagnostics.outcome_chain`
  - `diagnostics.recommended_next_action`
  - `diagnostics.attribution.primary_suspects`
  - `diagnostics.attribution.secondary_suspects`
  - `diagnostics.attribution.evidence_refs`
  - `diagnostics.attribution.dimensions`
- Replay sync metadata must preserve offline identity fields when present:
  - `case_id`
  - `run_id`
  - `trace_id`
  - `scope`
  - `workspace_id`
  - `story_id`
  - `source_session_id`
  - `setup_step`
  - `model_id`
  - `provider_id`
- Replay observation output contract:
  - `status`
  - `finish_reason`
  - `identifiers`
  - `diagnostics`
  - `retrieval`
- Setup replay score surface must include:
  - `setup.failure_layer`
  - `setup.commit_blocked`
  - `setup.metric.tokens_per_tool_invocation` when `tool_invocations` is non-empty
  - `setup.reason_codes`
  - `setup.attribution.primary_suspects`
  - `setup.attribution.secondary_suspects`
  - `setup.recommended_next_action`
  - `setup.evidence_refs`
  - `setup.outcome_chain.*`
- Setup replay score surface must also expose turn-quality heuristics for setup-agent decision making:
  - `setup.tool_selection_correct`
  - `setup.tool_selection_correct.numeric`
  - `setup.tool_result_value`
  - `setup.tool_result_value.numeric`
  - `setup.loop.noop_or_repeated_question`
  - `setup.loop.noop_or_repeated_question.numeric`
- These turn-quality heuristics are observability-only scores and must not mutate runtime truth or policy:
  - `setup.tool_selection_correct` grades whether the selected tool family matches `structured_payload.turn_goal`, `structured_payload.working_plan`, and `structured_payload.pending_obligation`
  - `setup.tool_result_value` grades whether tool activity produced durable setup progress, useful recovery information, or a justified clarification-only turn
  - `setup.loop.noop_or_repeated_question` grades whether the turn stalled into repeated follow-up without tool progress or explicit blocking context
- Heuristic inputs for the setup turn-quality scores are limited to existing runtime/report fields:
  - `tool_invocations`
  - `tool_results`
  - `structured_payload.turn_goal`
  - `structured_payload.working_plan`
  - `structured_payload.request_context`
  - `structured_payload.pending_obligation`
  - `structured_payload.completion_guard`
  - `structured_payload.round_no`
  - `finish_reason`
  - `assistant_text`
- `setup.commit_blocked` follows the effective block-commit route, not only the raw warning list:
  - `true` when `repair_route == "block_commit"`
  - `true` when `repair_route` is derived as `block_commit` because warnings contain `commit_proposal_blocked`
  - `true` when `repair_route` is derived as `block_commit` because `pending_obligation.obligation_type == "reassess_commit_readiness"`
- Suite summary Langfuse score surface should expose diagnostic aggregate signals:
  - `eval.suite.diagnostic.reason_codes.top`
  - `eval.suite.diagnostic.primary_suspects.top`
  - `eval.suite.diagnostic.recommended_next_actions.top`
  - `eval.suite.diagnostic.expectation_fail_total`
- Comparison Langfuse score surface must include diagnostic drift lists and counts:
  - `eval.compare.changed_reason_code_case_ids`
  - `eval.compare.changed_primary_suspect_case_ids`
  - `eval.compare.changed_outcome_chain_case_ids`
  - `eval.compare.changed_recommended_next_action_case_ids`
  - `eval.compare.changed_diagnostic_expectation_case_ids`
- `sync_suite_bundle_to_langfuse(...)` is the formal WebUI handoff for offline suite runs:
  - always sync the suite summary first
  - then sync every replay referenced by `suite_payload.items[].replay_path`
  - then sync comparison drift when `comparison` is provided
  - return a machine-readable summary with:
    - `suite_summary_synced`
    - `suite_replay_sync_count`
    - `comparison_synced`
- Replay bundle sync must fail loudly when any suite item is missing `replay_path`; formal WebUI drill-down must not silently skip a case.

### 4. Validation & Error Matrix
- `report` is not a dict -> ignore replay override and fall back to projection from `runtime_result`.
- Report diagnostic field missing -> fall back to nested diagnostic field, then projection field.
- `repair_route` missing but commit-block evidence exists in warnings or pending obligation -> derive `block_commit` before emitting `setup.commit_blocked`.
- No tool is selected during a clear clarification-only turn -> `setup.tool_selection_correct=pass` and `setup.tool_result_value=not_applicable`.
- No tool is selected even though turn goal / working plan implies tool work -> `setup.tool_selection_correct=fail`.
- Tools run but produce no success, no useful structured payload, and no explicit recovery/clarification justification -> `setup.tool_result_value=fail`.
- Round count reaches repair-loop territory (`round_no >= 4`) without successful tool progress -> `setup.loop.noop_or_repeated_question=fail`.
- Counter maps missing or malformed -> emit top aggregate as `none` and expectation total as `0`.
- Replay diagnostics are entirely empty -> `observation.update(output["diagnostics"])` may be `null`.
- Retrieval replay without retrieval sync payload -> keep `output["retrieval"] = null`, do not fabricate fields.
- Suite bundle sync sees missing `replay_path` -> raise instead of silently downgrading to summary-only sync.

### 5. Good/Base/Bad Cases
- Good: setup replay carries `trace_id/workspace_id/story_id` plus `failure_layer + reason_codes + recommended_next_action`, and Langfuse scores mirror the offline report.
- Good: clarification turn with blocking missing-info state emits `setup.tool_selection_correct=pass`, `setup.tool_result_value=not_applicable`, and `setup.loop.noop_or_repeated_question=pass`.
- Good: successful patch / truth-write turn emits the matching tool-family score, positive tool-result value, and `setup.metric.tokens_per_tool_invocation`.
- Base: suite summary has no diagnostic counters; Langfuse still gets core suite metrics and diagnostic aggregate scores degrade to `none`/`0`.
- Bad: patch/write goal skips tool selection and still lands in `completed_text`, so Langfuse shows a false-green setup turn despite no tool progress.
- Bad: report grows new top-level diagnostic fields but replay sync still reads only `runtime_result`, causing Langfuse drill-down to disagree with offline report.

### 6. Tests Required
- `rp/tests/test_langfuse_scores.py`
  - Assert report-aware setup score emission prefers replay report diagnostics when provided.
  - Assert `repair_route=block_commit` (or derived block-commit route) emits `setup.commit_blocked=True`.
  - Assert clarification-only turns mark `setup.tool_selection_correct=pass` and `setup.tool_result_value=not_applicable`.
  - Assert tool-expected turns without tool selection mark `setup.tool_selection_correct=fail`.
  - Assert successful patch/write turns mark `setup.tool_result_value=pass` and emit `setup.metric.tokens_per_tool_invocation`.
  - Assert unresolved repair loops mark `setup.loop.noop_or_repeated_question=fail`.
- `rp/tests/test_eval_langfuse_sync.py`
  - Assert suite summary sync emits diagnostic aggregate scores.
  - Assert missing/malformed `diagnostic_summary` still emits `none`/`0` defaults.
  - Assert comparison sync emits diagnostic drift lists/counts.
  - Assert setup replay sync propagates identifiers and diagnostic output fields.
  - Assert suite bundle sync emits suite, replay, and comparison observations together and returns the sync summary.
- When changing score names, update any compare/report tests that assume the old drift surface.

### 7. Wrong vs Correct
#### Wrong
- Replay sync only sends `case_id/run_id/scope` metadata and relies on `runtime_result` for all setup diagnostics.
- Treat tool-selection quality, tool-result value, and loop risk as runtime truth that changes executor behavior.
- Grade every no-tool turn as failure, even when the runtime explicitly stayed in ask-user clarification mode.
- Comparison sync ignores newly added diagnostic drift lists after compare/reporting is expanded.
- Formal WebUI sync silently skips suite items that have no replay bundle, so Langfuse drill-down looks complete while missing cases.

#### Correct
- Replay sync preserves offline identifiers and passes the replay `report` into setup score emission when available.
- Keep the new setup turn-quality scores heuristic and observational only, driven by existing runtime fields rather than new hidden state.
- Distinguish justified clarification turns from true noop loops, and separately grade tool choice vs tool-result value.
- Suite/comparison sync surfaces new diagnostic aggregates and drift lists as Langfuse scores in the same rollout that adds them offline.
- Formal WebUI sync uses the suite bundle as the single source of truth: suite summary, all replays, and optional comparison are pushed in one command, and missing replay bundles fail fast.
