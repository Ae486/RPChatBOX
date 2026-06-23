# S3.5 PRD — Memory Worker Production Structured-Output Runner

Status: planning draft for review
Owner: main-brain
Date: 2026-06-23

## Goal

Land the narrow productionization slice required after S3g-b and before S4:

```text
WorkerExecutionService
  -> MemoryMaintenanceWorkerAdapter
  -> production structured-output runner
  -> generic story-agent harness runner port
  -> structured candidate / no-op / failure
  -> existing S3 governance/apply path
```

This closes the most important S3 residual gap without attempting a broad
writer/orchestrator/brainstorm executor rewrite.

## Problem

S3g-b made the boundary honest but intentionally left normal runtime assembly in
this state:

```text
adapter-ready seam + explicit legacy specialist compatibility fallback
```

That is acceptable for a bounded compatibility commit. It is not acceptable as
the foundation for S4/S5/S6 if left unresolved, because later phases would be
tempted to build on the legacy specialist path rather than the story-agent
harness direction.

## Requirement Authority

- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-scheduler-governance.md`
- `execution/main-brain/S3.5-harness-productionization-decision.md`
- `execution/main-brain/harness-gap-and-completion-plan.md`
- `execution/main-brain/overall-implementation-roadmap.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- S3g-b commit: `51bc53c`

## In Scope

- generic structured-output runner port in story-runtime harness code;
- production memory-maintenance runner implementing
  `MemoryMaintenanceStructuredOutputRunner`;
- fake model/runner parity for deterministic tests;
- provider/parse/schema failure normalization into `WorkerResult` failure;
- timeout/cancellation and trace fields where the local model gateway supports
  them;
- runtime factory wiring that can use the production runner when configured;
- explicit compatibility fallback remains available and traceable;
- focused tests and fresh review.

## Out Of Scope

- universal production migration of writer/orchestrator/brainstorm;
- retrieval implementation;
- chapter-close summary;
- draft review/rewrite;
- external MCP provider support;
- setup-agent executor reuse;
- proposal/apply behavior changes;
- memory domain/block policy changes.

## Functional Requirements

### FR1. Generic runner port

The production memory worker must call through a generic story-agent
structured-output runner port, not through memory-specific model-call code
embedded directly in the adapter.

### FR2. Adapter remains product-specific

`MemoryMaintenanceWorkerAdapter` may own the memory worker output schema,
prompt-facing worker contract, and adapter validation. It must not own generic
model gateway mechanics.

### FR3. Production runner path

Normal runtime assembly must be able to construct a memory-maintenance runner
that satisfies `MemoryMaintenanceStructuredOutputRunner`.

When this runner is present, `WorkerExecutionService` must not call the legacy
specialist service for `LongformMemoryWorker`.

### FR4. Candidate-only authority

The runner may produce:

- candidate batch;
- no-op;
- failure.

It must not directly mutate Core, Projection, Recall, Archival, or proposal/apply
truth.

### FR5. Explicit fallback

Legacy specialist fallback may remain only as a named compatibility mode with:

- `executor_mode="legacy_specialist_compatibility"`;
- `compatibility_reason="memory_worker_structured_output_runner_missing"`;
- `s3_executor_migration_complete=False`.

### FR6. Failure normalization

Provider error, invalid structured output, schema mismatch, timeout, and
runner/cancellation failure must become readable worker failure results with
stable reason codes.

### FR7. Deterministic tests first

Deterministic fake tests are required. Live-provider smoke is optional and may
only be used after deterministic tests pass.

## Non-Functional Requirements

- Keep harness core generic.
- Keep memory/proposal/apply semantics outside harness core.
- Do not copy setup-agent executor code.
- Do not invent a private S3-only runner protocol if a generic port can serve
  later worker/writer/orchestrator roles.
- Keep the slice narrow and revertable.

## Definition Of Done

- PRD/SDD/test plan reviewed before code.
- Production runner port and memory runner are implemented.
- Factory wiring proves normal assembly can use the runner.
- Focused tests pass.
- Existing S3g-b tests remain green.
- `ruff` passes for changed files.
- Service-size check has no new S3.5 offender.
- Fresh reviewer audits against Node-1/module docs and this PRD.
- Commit uses explicit paths and excludes unrelated dirty files.
