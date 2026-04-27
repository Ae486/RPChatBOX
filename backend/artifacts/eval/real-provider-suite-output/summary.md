# RP Eval Suite Summary

- run_count: 3
- case_count: 3
- failed_run_count: 1
- assertion_fail_total: 3
- assertion_warn_total: 0
- hard_failure_total: 3
- pending_judge_hook_total: 2
- executed_judge_hook_total: 0
- subjective_average_score: None
- threshold_passed: False

## Finish Reasons

- activation_completed: 1
- n/a: 1
- retrieval_completed: 1

## Failure Layers

- infra: 1

## Judge Hooks

- llm_judge: 2

## Judge Status

- skip: 2

## Judge Rubrics

- activation/handoff-quality/v1: total=1 executed=0 pending=1 avg_score=None cases=1
- retrieval/query-quality/v1: total=1 executed=0 pending=1 avg_score=None cases=1

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

- status not_requested: 1
- metric: none

## Repeat Cases

- none

## Thresholds

- breach: assertion_fail_total>0 (actual=3)

## Top Cases

- setup.real_provider_smoke.gemini_flash.v1: runs=1 fails=3 warns=0 pending_judge_hooks=0 finish_reasons=n/a
- activation.bootstrap.ready_workspace_activation.v1: runs=1 fails=0 warns=0 pending_judge_hooks=1 finish_reasons=activation_completed
- retrieval.search.query_trace_and_provenance.v1: runs=1 fails=0 warns=0 pending_judge_hooks=1 finish_reasons=retrieval_completed
