# S3 Implementation Planning Index

Status: S3f closing gate planned
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
14. `S3c-check-record.md` — fresh reviewer/check record for the S3c slice.
15. `11-S3c-implementation-result.md` — main-brain result and gate record for
    S3c.
16. `12-S3d-implementation-brief.md` — bounded implement-worker brief for
    maintenance lock and stale-base integration.
17. `S3d-check-record.md` — fresh reviewer/check record for the S3d slice.
18. `13-S3d-implementation-result.md` — main-brain result and gate record for
    S3d.
19. `14-S3e-implementation-brief.md` — bounded implement brief for wiring the
    maintenance lock into real backend entrypoints.
20. `S3e-check-record.md` — fresh reviewer/check record for the S3e slice.
21. `15-S3e-implementation-result.md` — main-brain result and gate record for
    S3e.
22. `16-S3f-closing-gate-brief.md` — bounded brief for the final S3
    end-to-end memory-maintenance gate.
23. `S3f-planning-review-record.md` — assistant review and main-brain
    adjudication for the S3f brief.
24. `review-record.md` — standing assistant planning review.
25. `worklog.md` — planning and execution trace for this S3 directory.

## Current Gate

Current step:

```text
S3a registry/candidate contracts passed
  -> S3b memory worker adapter passed
  -> S3c implementation and fresh check passed
  -> S3d implementation and fresh check passed
  -> S3e maintenance lock entrypoint wiring passed
  -> S3f closing gate brief reviewed and amended
  -> next: S3f end-to-end implementation/review gate
```

S3a, S3b, S3c, S3d, and S3e are completed implementation slices. S3e is the
first integration slice that wires the S3d lock into real backend entrypoints.
S3f is now planned as the final S3 closing gate because the original SDD's
end-to-end gate was displaced by the necessary S3e maintenance-lock wiring
slice. S3f must prove the connected post-write worker -> governance -> proposal
apply -> lock path.

S3d/S3e/S3f leave one explicit residual gate risk: the global service-size
checker is already red due to pre-existing story baseline drift and
already-committed S3a/S3b/S3c hard function offenders. S3f must not make this
red state worse. A dedicated service-size remediation slice should follow before
S4/S5 depend further on oversized story services.

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
