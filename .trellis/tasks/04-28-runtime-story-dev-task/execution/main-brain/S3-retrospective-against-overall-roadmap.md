# S3 Retrospective Against Overall Roadmap

Status: active recovery gate
Task: `04-28-runtime-story-dev-task`
Created: 2026-06-23

## Purpose

This document records the process correction after S3 implementation had
already progressed before a sufficient project-level construction map existed.

It answers three questions:

1. What was the S3 implementation actually driven by?
2. Which completed or pending S3 slices align with the overall roadmap?
3. What must be fixed, recorded, or reviewed before committing S3g-b or
   starting S4?

This is not a replacement for the S3 PRD, SDD, test plan, or per-slice gate
records. It is a retrospective gate that checks whether those local plans fit
the overall runtime direction.

## Process Finding

The user's criticism is valid.

The implementation was not random: it used Node-1 grill documents, module
documents, S3 PRD/SDD/test plan, and per-slice implementation briefs. However,
those are local or requirement-level inputs. They did not provide a complete
project-level construction map before implementation began.

The missing layer was:

- phase ordering across S3/S4/S5/S6/S7;
- dependency and entry/exit criteria;
- old MVP path classification;
- harness versus product-service promotion policy;
- tool contract standard for later phases;
- review/test/commit gates as a single repeatable control plane;
- explicit "do not continue" rules when the plan is incomplete.

Therefore the corrective action is:

```text
pause implementation
  -> upgrade overall roadmap into a mandatory gate
  -> audit S3 against that roadmap
  -> decide S3g-b commit/revision
  -> decide S3.5 harness productionization
  -> only then enter S4 planning
```

## Evidence Used

Primary documents:

- `research/index.md`
- `research/modules/runtime-module-breakdown-index.md`
- `execution/main-brain/overall-implementation-roadmap.md`
- `execution/main-brain/harness-gap-and-completion-plan.md`
- `execution/main-brain/implementation-leadership-rules.md`
- `execution/main-brain/operating-rules.md`
- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/worklog.md`
- S3 per-slice brief/result/check/review documents.

Code and diff review is still required before any pending commit.

## S3 Slice Retrospective

| Slice | Current status | Roadmap judgement | Follow-up |
| --- | --- | --- | --- |
| S3a registry / candidate contracts | Completed and committed. | Aligned with S3 requirement if it exposes fixed memory contract and rejects schema/block creation. | Re-check exact code against `runtime-memory-domain-block.md` during final S3 audit. |
| S3b memory worker adapter / structured output | Completed and committed. | Aligned as first worker path, but may still be partial harness proof rather than full production executor. | Do not claim full harness unification from this slice alone. |
| S3c governance routing / proposal handoff | Completed and committed. | Aligned if new S3 candidate semantics remain visible and are not only hidden as `legacy_state_patch`. | Audit trace/review surfaces for named S3 boundary. |
| S3d lock / stale-base behavior | Completed and committed. | Aligned with maintenance lock and stale-base requirements. | Verify lock matrix against Node-1/module docs, not only local tests. |
| S3e lock entrypoint wiring | Completed and committed. | Compatible if it preserves old route behavior while enforcing new S3 blockers. | Check old MVP path classification: preserve/adapt/quarantine. |
| S3f end-to-end closing gate | Completed and committed. | Aligned as reference vertical slice. | Treat as S3 reference path only, not complete runtime completion. |
| S3g-a service-size cleanup | Completed and committed. | Useful code-health slice, not a functional requirement milestone. | Keep separate from product-completion claims. |
| S3g-b production executor compatibility | Implemented and reviewed, not committed. | Compatible but debt-bearing. It may be a valid compatibility slice, not proof that production structured-output runner is complete. | Do not commit until staged diff is read and roadmap gate classifies it explicitly. |

## Cross-Cutting Findings

### 1. S3 is a reference slice, not the full runtime

S3 proves memory worker output, governance, and deterministic apply. It does
not finish retrieval, chapter close, rewrite/adoption, brainstorm, or complete
harness productionization.

Action:

- keep S3 completion language narrow;
- do not use S3 E2E success as permission to skip later phase PRD/SDD gates.

### 2. Harness completion is still a separate question

S3 uses and improves story-agent mechanics, but the target shared harness still
needs an explicit productionization decision.

Action:

- create S3.5 or equivalent harness productionization plan if S3g-b does not
  fully provide a production structured-output runner;
- promote only generic execution mechanisms;
- keep memory/proposal/apply policy outside harness core.

### 3. Old MVP paths must be classified every time they are touched

The old MVP code can be preserved when compatible, adapted when useful, replaced
when conflicting, or quarantined for compatibility. It must not silently define
the new architecture.

Action:

- every future slice brief must include old path classification;
- pending S3g-b must state whether its fallback is compatibility quarantine.

### 4. Tool design must become a repeatable gate before S4+

S3 has internal adapter/fake-runner mechanics. Later phases will rely more on
retrieval, summary, rewrite, and brainstorm capabilities. Those must not each
invent private tool semantics.

Action:

- every tool-like capability needs structured input/output/error, caller
  allowlist, trace, failure behavior, and governance destination;
- do not enter S4 without this written in the S4 plan.

### 5. Tests passing is necessary but not sufficient

Focused tests and reviewer GO are useful evidence. They do not replace roadmap
alignment, requirement-source coverage, old-path classification, or staged diff
review.

Action:

- require both behavioral tests and architecture/process gates before commit;
- record expected pre-existing failures separately.

## Pending S3g-b Gate

S3g-b may be accepted only if all of the following are true:

- staged diff contains only S3g-b-owned production/test/docs files;
- compatibility fallback is clearly labeled and traceable;
- no code or doc claims that the full production structured-output runner is
  complete if it is not;
- old MVP / legacy specialist path is classified as compatibility quarantine or
  explicit fallback;
- focused tests and ruff gates remain green;
- service-size failure, if any, is recorded as pre-existing or unrelated;
- fresh review findings are adjudicated by the main-brain;
- the commit message reflects compatibility rather than final architecture if
  the runner gap remains.

If any item fails, revise or split S3g-b before commit.

## Mandatory Before S4

Do not start S4 implementation until:

1. S3g-b is either committed as a bounded compatibility slice, revised, or
   explicitly abandoned.
2. S3.5 harness productionization decision is recorded.
3. S4 PRD/SDD/test plan is written from `runtime-retrieval.md`, context packet,
   agent framework, scheduler/governance, and workspace/trace documents.
4. S4 plan includes tool contract, retrieval card/usage record behavior,
   packet/read-manifest behavior, failure cases, and old path classification.
5. A reviewer checks the S4 plan before code.

## Current Decision

Current execution state:

- implementation remains paused for new feature work;
- S3g-b is cleared only as a bounded compatibility slice;
- S4 is not cleared to start;
- the next action is focused verification, explicit staging, and commit of
  S3g-b-owned files only.

This document must be updated again after the S3g-b commit records its exact
commit hash, or if focused verification contradicts this gate decision.

## S3g-b Gate Decision — 2026-06-23

Decision:

```text
accept S3g-b for commit as a bounded compatibility slice
```

Rationale:

- the current code diff matches `21-S3g-b-production-executor-compatibility-brief.md`;
- `MemoryMaintenanceWorkerAdapter.has_structured_output_runner` is only a
  mechanical capability check;
- `WorkerExecutionService` uses the S3 memory adapter when a structured-output
  runner exists and does not call `LongformSpecialistService.analyze()` on that
  path;
- legacy specialist execution remains only behind the explicit
  `enable_legacy_longform_memory_worker_specialist_fallback` flag;
- compatibility results carry stable metadata / trace:
  - `executor_mode="legacy_specialist_compatibility"`;
  - `compatibility_reason="memory_worker_structured_output_runner_missing"`;
  - `s3_executor_migration_complete=False`;
- `rp_runtime_factory.py` wires the adapter and the explicit compatibility
  fallback, so the normal runtime boundary is no longer silent;
- tests cover adapter-runner execution, explicit legacy fallback, and factory
  wiring;
- fresh review returned `GO`;
- no diff in the S3g-b target files changes proposal/apply behavior, truth
  mutation semantics, scheduler selection, or setup-agent dependencies.

Classification:

| Item | Classification | Reason |
| --- | --- | --- |
| S3 adapter runner path | Adapt | It routes the memory worker through the S3 adapter when a runner exists. |
| Legacy specialist path | Quarantine | It remains only as explicit compatibility fallback and is marked incomplete. |
| Production structured-output runner | Gap | It is still not implemented and must not be implied by S3g-b. |
| Runtime factory wiring | Adapt | It makes the adapter/compatibility boundary visible in normal assembly. |

Commit condition:

- stage only S3g-b-owned code/test/docs and main-brain gate documents;
- exclude unrelated dirty files:
  - `.gitignore`;
  - `.trellis/.template-hashes.json`;
  - `backend/services/conversation_source.py`;
  - `backend/tests/test_conversation_source_api.py`;
  - any status-only / line-ending-only files not owned by S3g-b.

Next required decision before S4:

```text
S3.5 must decide whether to implement the production memory-maintenance
structured-output runner before S4, or explicitly defer it with owner, risk,
and next-phase impact.
```
