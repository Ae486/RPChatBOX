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
- timeout/cancellation failure shape and trace fields;
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

### FR8. Configuration and assembly contract

S3.5 must not introduce scattered environment flags or adapter-local switches.

The production runner enablement source must be explicit at runtime assembly:

- `RpRuntimeFactory` or its injected runtime configuration owns whether the
  production memory-maintenance runner is constructed;
- tests may inject a fake model gateway / fake structured-output runner through
  the same assembly seam;
- `MemoryMaintenanceWorkerAdapter` must not read process environment or global
  mutable config to decide whether a production runner exists;
- if the runner is disabled or unavailable, fallback may occur only through the
  explicit S3g-b compatibility switch and metadata;
- S4 implementation must see a real production-runner-capable path or a signed
  deferral record. A silent legacy fallback is not an acceptable S4 base.

Default policy:

- test/dev profiles may disable the production runner only when the fallback
  metadata remains explicit;
- the target longform runtime path should prefer the production runner whenever
  the model gateway and required prompt/schema configuration are available.

### FR9. Tool calls are disabled in the first S3.5 runner

S3.5 does not implement the full generic tool loop. The generic runner port
must leave space for tool-call/result support, but the memory-maintenance
production runner for this slice must declare tool calls disabled.

If the provider/model output attempts tool-call behavior or the runner receives
an unknown/disabled tool request, it must fail closed with a stable reason code
instead of executing a private tool protocol.

### FR10. Canonical S3.5 reason codes

S3.5 must use stable reason codes at the runner/adapter boundary.

Minimum required codes:

| Code | Meaning |
| --- | --- |
| `memory_worker_provider_error` | Model/provider call failed. |
| `memory_worker_timeout` | Runner exceeded timeout. |
| `memory_worker_cancelled` | Cancellation was observed before completion. |
| `memory_worker_invalid_structured_output` | Provider output could not be parsed or validated as worker output. |
| `memory_worker_output_schema_version_unsupported` | Worker output schema version is unsupported. |
| `memory_worker_repair_exhausted` | Bounded repair was attempted and exhausted. |
| `memory_worker_context_packet_missing` | Required worker context packet was missing. |
| `memory_worker_source_ref_missing` | Required source refs were missing. |
| `memory_worker_base_ref_missing` | Required base refs were missing. |
| `memory_worker_stale_base` | Candidate base ref is stale or conflicted. |
| `memory_worker_tool_calls_disabled` | Tool calls are not enabled for this runner. |
| `memory_worker_unknown_tool` | A requested tool is not allowlisted. |

Existing S3 adapter reason codes should be reused where they already match. Do
not invent local aliases for scheduler/maintenance lock reason codes.

### FR11. Non-mutation proof

S3.5 tests must prove the runner/adapter layer does not write:

- Core State;
- Projection truth;
- Recall;
- Archival;
- proposal repository rows;
- apply receipts.

The runner may return structured candidate/no-op/failure output only. Proposal
or apply side effects are allowed only through the existing S3 governance/apply
path.

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
- Configuration/assembly contract is explicit and tested.
- Tool calls are either disabled with stable failure behavior or implemented
  through a generic harness contract; for this S3.5 plan they are disabled.
- Canonical reason codes are implemented or mapped.
- Non-mutation assertions prove runner/adapter does not bypass governance.
- Focused tests pass.
- Existing S3g-b tests remain green.
- `ruff` passes for changed files.
- Service-size check has no new S3.5 offender.
- Fresh reviewer audits against Node-1/module docs and this PRD.
- Commit uses explicit paths and excludes unrelated dirty files.
