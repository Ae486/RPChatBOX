# RP Eval Suite Summary

- run_count: 1
- case_count: 1
- failed_run_count: 1
- assertion_fail_total: 1
- assertion_warn_total: 0
- hard_failure_total: 1
- pending_judge_hook_total: 0
- executed_judge_hook_total: 0
- subjective_average_score: None
- threshold_passed: False

## Finish Reasons

- runtime_execution_failed: 1

## Failure Layers

- infra: 1

## Judge Hooks

- none

## Judge Status

- none

## Judge Rubrics

- none

## Diagnostics

- primary_suspects: infra_model_provider
- reason_codes: infra.provider_request_failed=1, readiness.blocked_by_open_setup_prerequisites=1
- diagnostic_expectation_failures: none
- outcome_chain:
  - activation_handoff_status: fail=1
  - cognition_status: not_applicable=1
  - readiness_status: warn=1
  - runtime_bootstrap_readiness_status: warn=1
  - transcript_status: not_applicable=1
  - truth_status: not_applicable=1
- recommended_next_actions: fix_provider_model_config_and_runtime_connectivity=1

## RAGAS

- status: none
- metric: none

## Repeat Cases

- none

## Thresholds

- breach: assertion_fail_total>0 (actual=1)

## Top Cases

- setup.real_provider_smoke.gemini_flash.stream.tmp: runs=1 fails=1 warns=0 pending_judge_hooks=0 finish_reasons=runtime_execution_failed
