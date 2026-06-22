# S3 Implementation Planning Index

Status: planning gate in progress
Task: `.trellis/tasks/04-28-runtime-story-dev-task`
Slice: S3 — Memory domain/block + worker family + proposal/apply

## Purpose

This directory holds the construction documents for S3. S3 is the first
production pressure test for the story-agent harness, memory worker, tool
contract, proposal review, governed apply, and maintenance lock path.

This directory does not replace:

- `research/index.md`
- `research/modules/*`
- `execution/phase-1-spec-freeze/*`
- `execution/phase-3-slicing/slice-plan.md`
- `execution/main-brain/*`

Those files remain the authority. S3 documents translate them into a concrete
implementation plan.

## Document Order

1. `00-preflight-judgment.md` — existing preflight judgment and risk framing.
2. `01-PRD.md` — product and requirement definition for S3 implementation.
3. `02-SDD-and-implementation-plan.md` — system design document and slice plan.
4. `03-test-and-gate-plan.md` — required functional tests and gate commands.
5. `04-standing-assistant-review-brief.md` — brief for the standing reviewer /
   assistant before implementation.
6. `05-main-brain-adjudication.md` — main-brain decisions on reviewer findings.
7. `06-S3a-implementation-brief.md` — bounded implement-worker brief for the
   first registry/candidate-contract slice.
8. `S3a-check-record.md` — fresh reviewer/check record for the S3a slice.
9. `07-S3a-implementation-result.md` — main-brain result and gate record for S3a.
10. `08-S3b-implementation-brief.md` — bounded implement-worker brief for the
    memory worker adapter / fake harness slice.
11. `S3b-check-record.md` — fresh reviewer/check record for the S3b slice.
12. `09-S3b-implementation-result.md` — main-brain result and gate record for
    S3b.
13. `10-S3c-implementation-brief.md` — bounded implement-worker brief for
    governance routing and proposal handoff.
14. `review-record.md` — standing assistant planning review.
15. `worklog.md` — planning and execution trace for this S3 directory.

## Current Gate

Current step:

```text
S3a registry/candidate contracts passed
  -> S3b memory worker adapter passed
  -> S3c governance routing / proposal handoff brief prepared
  -> next: S3c implementation and fresh check
```

S3a and S3b are completed implementation slices. S3c must still be planned as a
bounded slice before code, reviewed against Node-1 grill docs, module docs,
frozen SoT, and current code evidence.

## Non-Negotiable Rules

- Use YCE for codebase search. Do not use ACE.
- Read known docs directly when paths are known.
- Node-1 grill docs are requirement authority.
- Module docs are the implementation-reading layer.
- S3 may improve the harness only for cross-role execution mechanisms.
- Memory/domain/block semantics and proposal/apply policy stay outside harness
  core.
- Tests must prove behavior, not just DTO shape.
- Fresh review is required after each main-brain-defined milestone.
- Each coherent planning or implementation slice must end in a small, readable
  commit after its gate passes. Commit only files belonging to that slice. Since
  `.trellis/tasks/` is ignored locally, use explicit path staging for required
  task documents; never sweep unrelated ignored files into the commit.
