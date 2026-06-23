# S3.5 Implementation Review Adjudication

Status: main-brain adjudicated
Owner: main-brain
Date: 2026-06-23

## Review Inputs

- report: `15-implementation-review-report.md`
- fresh reviewer verdicts:
  - `Helmholtz` -> `NO_GO`
  - `Kierkegaard` -> `GO_WITH_FIXES`

## Accepted Findings

### A1. Top-level schema-version reason code is wrong

Accepted.

Current code records schema-version mismatch as a finding but emits
`memory_worker_structured_output_identity_mismatch` as the top-level
`trace_summary.reason_code`. The S3.5 PRD / brief / gate plan explicitly list
`memory_worker_output_schema_version_unsupported` as a required stable reason
code. This must be fixed in code and tests.

### A2. Missing execution-level proof for disabled-runner + disabled-compatibility path

Accepted.

`WorkerExecutionService` contains an explicit branch for
`production runner unavailable` plus
`enable_legacy_longform_memory_worker_specialist_fallback=False`, but the
current test suite does not directly prove that this path returns an explicit
failure/degrade result without calling `LongformSpecialistService.analyze()`.
Add the missing execution-level test.

### A3. System-owned runner metadata must win over model metadata

Accepted.

The production runner currently preserves model-supplied `metadata.runner_mode`
via `setdefault(...)`. That makes a system-owned trace field spoofable by model
output and weakens the review/debug truth surface. The repair slice must make
the authoritative runner metadata system-owned and update tests to assert the
system-owned field.

### A4. Reason-code gate closure still needs explicit ownership notes

Accepted, with narrow scope.

This does **not** authorize broadening S3.5 into a full tool loop or repair
loop. It means the post-fix gate record must explicitly close the remaining
reason-code items as follows:

- `memory_worker_unknown_tool`: first-runner unreachable while tool calls are
  disabled in S3.5;
- `memory_worker_repair_exhausted`: first-runner unreachable because bounded
  repair is not implemented in this slice;
- `memory_worker_stale_base`: owned by downstream governance/apply rejection,
  not by the S3.5 runner/adapter, and already covered by the existing
  downstream regression suite.

## Rejected Or Deferred Findings

### R1. Enforce a full canonical allowlist for every worker-returned failure code

Not accepted as a mandatory repair item.

Current frozen docs require the minimum stable S3.5 runner/adapter reason-code
family, but they do not prove that every worker-returned domain failure code is
forbidden unless it appears in that minimum table. The repair slice should fix
the confirmed top-level schema-version mismatch and system-owned runner/adapter
codes, but it should not invent a broader closed-world failure taxonomy without
additional design authority.

### R2. Implement real timeout enforcement or a repair loop in S3.5

Deferred.

That is scope growth beyond the confirmed review blockers. The current repair
slice may clarify first-runner ownership and unreachable codes, but it should
not expand into a new timeout/repair implementation project.

### R3. Treat the phase-light factory-built normal-path proof as a blocker

Rejected.

The production-path dispatch branch is selected by worker identity and runner
availability, and the existing adapter tests already exercise the common
post-write maintenance shape. This does not block acceptance once A1-A4 are
fixed.

## Gate Decision

Current state:

```text
NO_GO pending bounded repair slice
```

Implementation is **not** accepted yet. The next step is a tightly scoped
implement-worker repair covering only A1-A4 and the directly necessary tests.
