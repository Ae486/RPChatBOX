# S3 Main-Brain Adjudication

Status: active
Date: 2026-06-23

## Source Review

Standing assistant review:

- `execution/phase-5-implementation/S3/review-record.md`
- Verdict: `PASS_WITH_CONCERNS`

The review did not identify a product/scope blocker. It identified five
planning tightenings required before production implementation.

## Adjudication

| Finding | Main-brain decision | Reason |
| --- | --- | --- |
| C1 full D-S3-03 lock matrix not explicit enough in test plan | Accepted | The PRD states the matrix, but tests need operation-level assertions to prevent a thin blocker implementation. |
| C2 governance mapping still too deferred | Accepted | S3c implementation needs a concrete bridge from W5 terms to current policy/apply behavior. |
| C3 tool / structured-output / failure contract under-specified | Accepted | S3 is the reference path for later workers; worker failure semantics must be clear before coding. |
| C4 legacy_state_patch boundary not executable | Accepted | The new memory-worker path must not be hidden under old-MVP semantics. |
| C5 base_block_revision_id to current base_refs bridge not explicit | Accepted | Frozen S3 stale-base semantics must be preserved while reusing current apply enforcement. |

## Plan Changes Applied

- `02-SDD-and-implementation-plan.md`
  - added normalized tool result and worker result contracts;
  - added structured-output invalid/repair-exhaustion/no-op/failure rules;
  - added governance mapping table;
  - added legacy candidate boundary;
  - added `base_block_revision_id` -> `base_refs` bridge.
- `03-test-and-gate-plan.md`
  - added governance mapping and base-ref unit requirements;
  - added legacy-boundary service requirement;
  - added full D-S3-03 maintenance lock matrix integration coverage;
  - added proposed lock-matrix and legacy-boundary test files.

## Gate Decision

S3 planning remains `PASS_WITH_CONCERNS` until the updated documents are read
back and committed.

After that, the next permitted step is preparing S3a/S3b implementation briefs.
Production code should still wait until the planning-doc commit is complete and
the first implementation assignment is bounded to one coherent spec slice.
