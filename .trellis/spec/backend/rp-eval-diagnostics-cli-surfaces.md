# RP Eval Diagnostics CLI Surfaces

> Executable contract for setup diagnostic reason-code extraction and default CLI text summaries.

## Scenario: Setup Diagnostics Surface Integrity

### 1. Scope / Trigger
- Trigger: `backend/rp/eval/diagnostics.py` or `backend/rp/eval/cli.py` changes that affect setup reason-code extraction or human-readable eval CLI output.
- Scope: setup tool failure code harvesting, reason-code projection, and `run-suite` / `compare` text summary behavior.

### 2. Signatures
- `_setup_tool_error_codes(tool_results: list[Any]) -> list[str]`
- `build_setup_diagnostic_projection(*, runtime_result, failure_layer=None, error_code=None, assertion_fail_total=0, hard_failures=None, subjective_hook_results=None) -> dict[str, Any]`
- `_print_payload(payload: dict, *, as_json: bool) -> None`
- `main(argv: list[str] | None = None) -> int`

### 3. Contracts
- Failed setup `tool_results` may surface error codes from any of these locations, and `_setup_tool_error_codes(...)` must treat them as the same signal family:
  - top-level `tool_results[].error_code`
  - top-level `tool_results[].code`
  - `tool_results[].structured_payload.error.code`
  - `tool_results[].structured_payload.content_payload.error.code`
  - `tool_results[].structured_payload.code`
  - JSON `tool_results[].content_text.error.code`
  - JSON `tool_results[].content_text.code`
- `_setup_reason_codes(...)` must consume the merged failure-code set so that top-level-only tool failures still map to stable setup reason codes such as:
  - `controller.commit_proposal_blocked`
  - `tool_contract.truth_write_target_ref_mismatch`
- `_print_payload(..., as_json=False)` must preserve both text summaries when `run-suite` produces a payload containing both:
  - suite summary (`suite` + `summary` + `thresholds`)
  - comparison summary (`comparison`)
- Default text output order is:
  1. suite summary line
  2. comparison summary line
- Compare-only payload prints only the comparison line; suite-only payload prints only the suite line.
- When suite payload includes `langfuse_sync`, the default suite summary line must surface:
  - `langfuse_replays_synced=<count>`
  - `langfuse_comparison_synced=<bool>`
- `run-suite --sync-all-to-langfuse` is the formal offline-to-WebUI entrypoint:
  - it must sync suite summary, all suite replay bundles, and optional comparison drift
  - it must reject execution when Langfuse is not enabled instead of silently no-oping
- `--sync-suite-to-langfuse`, `--sync-all-to-langfuse`, `--sync-comparison-to-langfuse`, and `--sync-replay-to-langfuse` must fail fast with a clear setup message when Langfuse is disabled.

### 4. Validation & Error Matrix
- Top-level failure code exists but extractor ignores it -> projected `reason_codes` lose stable controller/tool-contract attribution.
- `content_text` is not JSON or cannot be parsed -> ignore that branch and keep any other harvested codes.
- Payload contains both suite summary and comparison but CLI returns after printing compare -> baseline mode hides suite health and threshold context.
- Payload contains only comparison -> do not fabricate suite summary text.
- User explicitly asks for Langfuse sync while Langfuse is disabled -> terminate with a clear configuration error instead of pretending sync happened.

### 5. Good/Base/Bad Cases
- Good: a failed `setup.truth.write` tool result with only top-level `error_code` still produces `controller.commit_proposal_blocked`, and `run-suite --baseline-dir` prints both `suite ...` and `compare ...`.
- Base: a compare-only payload still prints one `compare ...` line with drift counters and no suite text.
- Bad: diagnostics only parse nested payload codes, so a top-level tool failure silently degrades to missing reason codes; or baseline-mode CLI only prints comparison text and hides threshold status.

### 6. Tests Required
- `rp/tests/test_eval_diagnostics.py`
  - Assert `build_setup_diagnostic_projection(...)` reads top-level `tool_results[].error_code` / `code` and surfaces the mapped setup reason codes.
- `rp/tests/test_langfuse_scores.py`
  - Assert Langfuse setup score emission sees the same reason-code output when failure codes are top-level only.
- `rp/tests/test_eval_cli.py`
  - Assert `run-suite --baseline-dir` text output includes both suite summary and comparison summary.
  - Assert suite text output includes Langfuse sync counts when `langfuse_sync` is present.
  - Assert `run-suite --sync-all-to-langfuse` exposes the Langfuse sync summary in default text output.
  - Assert Langfuse sync flags fail early when Langfuse is disabled.

### 7. Wrong vs Correct
#### Wrong
- Assume setup tool failures always store their canonical code inside nested `structured_payload` JSON.
- Return immediately when `_print_payload(...)` sees `comparison`, even if the payload also contains a suite summary.
- Accept `--sync-all-to-langfuse` while Langfuse is disabled and silently print a normal suite success line.

#### Correct
- Merge top-level and nested failure-code locations before mapping setup reason codes.
- In baseline suite mode, print suite health first and comparison drift second so the default CLI output preserves both contexts.
- Treat explicit Langfuse sync flags as operator intent: either sync the requested WebUI artifacts or fail with a clear setup message.
