# S3.5 SDD And Implementation Plan

Status: planning draft for review
Owner: main-brain
Date: 2026-06-23

## Design Objective

Close the S3g-b production-runner gap by adding a narrow production
structured-output runner path for `LongformMemoryWorker`, while preserving the
framework/product boundary.

## Architecture Boundary

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| Harness runner port | model request mechanics, structured-output response normalization, trace, timeout/cancellation, fake gateway surface | memory domain/block rules, proposal policy, Core apply |
| Memory worker runner | prompt assembly from `WorkerExecutionRequest` / `WorkerContextPacket`, schema target, runner metadata | final candidate validation/apply |
| Memory adapter | parse/validate worker output variants and map to `WorkerResult` | direct model gateway mechanics, truth mutation |
| WorkerExecutionService | selected-worker execution routing and fallback policy | prompt/schema details, proposal/apply |
| Governance/apply services | proposal routing and deterministic apply | model/tool execution |

## Proposed Component Shape

### 1. Generic structured-output runner port

Add a generic runner interface in a story-runtime / agent-harness location.

Allowed placement range:

- a new story-runtime harness module under `backend/rp/agent_runtime/` if it is
  setup-free and not inside `agent_runtime/setup/`;
- or a runtime-owned service/contract module under `backend/rp/services/runtime/`
  if the existing package layout makes that the narrower dependency direction.

Do not place the generic port under `writer/` or `setup_agent/`. The memory
runner can live under `writer/` only as a role/worker-specific adapter around
the generic port.

Candidate shape:

```python
class StructuredOutputRunRequest(BaseModel):
    run_id: str
    role: str
    worker_id: str | None
    phase: str | None
    provider_id: str | None
    model_id: str
    schema_name: str
    schema_version: str
    messages: list[RuntimeMessage]
    response_schema: dict[str, Any] | type[BaseModel]
    tool_policy: RuntimeToolPolicy
    timeout_s: float | None
    repair_budget: int
    metadata: dict[str, Any]

class StructuredOutputRunResult(BaseModel):
    status: Literal["completed", "failed", "cancelled", "timeout"]
    structured_output: dict[str, Any] | None
    raw_text: str | None
    stop_reason: str | None
    reason_code: str | None
    message: str | None
    retryable: bool
    repair_attempts: int
    raw_output_visibility: Literal["private_trace", "redacted", "none"]
    trace: dict[str, Any]
```

The names can change. The semantics must not.

For S3.5, `tool_policy` must declare tool calls disabled. The port should be
able to grow into tool-call/result support later, but the memory worker runner
must fail closed on tool calls in this slice.

### 2. Production memory-maintenance runner

Implement a memory-maintenance runner that satisfies the existing
`MemoryMaintenanceStructuredOutputRunner` protocol.

Responsibilities:

- build a model request from `WorkerExecutionRequest`, registration, and
  `WorkerContextPacket`;
- ask the generic runner port for structured output matching
  `MemoryMaintenanceWorkerStructuredOutput`;
- return dict/model output to `MemoryMaintenanceWorkerAdapter`;
- on generic runner failure, return a structured `failure` output or raise a
  runner-owned exception that the adapter normalizes.

### 3. Factory wiring

`rp_runtime_factory.py` should be able to wire:

```text
MemoryMaintenanceWorkerAdapter(
  structured_output_runner=ProductionMemoryMaintenanceStructuredOutputRunner(...)
)
```

Compatibility fallback remains explicit. If the production runner is disabled
or unavailable in a test/dev profile, the existing S3g-b fallback metadata must
remain visible.

Configuration / assembly truth:

- the factory or an injected runtime configuration object owns production runner
  construction;
- no adapter-local environment-variable read is allowed;
- tests must be able to inject a fake model gateway through the same seam that
  production wiring uses;
- production runner unavailable + compatibility enabled means explicit fallback;
- production runner unavailable + compatibility disabled means explicit
  fail/degrade result, not silent legacy execution.

### 4. Trace and reason codes

Trace must show:

- runner mode: production / fake / compatibility fallback;
- worker id and phase;
- output schema name/version;
- context packet ref;
- provider/model id where safe;
- failure reason code;
- retry/repair count if implemented.

Reason codes should be stable and readable. Do not introduce local aliases for
existing maintenance lock or scheduler reason codes.

Minimum S3.5 runner reason codes are defined in `01-PRD.md` FR10. Reuse existing
adapter codes when they already match.

### 5. Setup-agent leakage guard

S3.5 must not introduce imports from setup-agent executor paths in new story
harness or memory-runner modules.

Guard scope:

- forbid `rp.agent_runtime.setup.*` and `rp.services.setup_agent.*` imports in
  new generic runner contracts, production memory runner modules, and their
  direct tests;
- do not fail the whole repository or `rp_runtime_factory.py` solely because
  pre-existing setup factory wiring already imports setup services.

The intent is to block copying setup executor policy into story runtime without
misclassifying pre-existing setup assembly code.

### 6. Non-mutation assertion strategy

S3.5 implementation tests must prove runner/adapter code does not write truth
or proposal/apply persistence directly.

Minimum evidence:

- successful runner output reaches `MemoryMaintenanceWorkerAdapter` and remains
  a `WorkerResult.proposal_candidates` candidate with
  `source_of_truth=False` and `authoritative_mutation=False`;
- runner/adapter tests do not instantiate or call `ProposalRepository`,
  `ProposalApplyService`, Core State write services, Recall write services, or
  Archival write services;
- integration tests that exercise governance must show proposal/apply side
  effects occur only after the existing post-write governance service consumes
  the worker candidate.

## Implementation Sub-Slices

### S3.5a — Planning review

Scope:

- review this PRD/SDD/test plan against `runtime-agent-harness.md`,
  `runtime-worker-family.md`, and current code.

Exit:

- reviewer accepts or issues blockers;
- main-brain adjudicates findings.

### S3.5b — Generic structured-output runner port

Scope:

- add generic runner request/result contracts;
- add fake runner/gateway test surface;
- declare S3.5 tool calls disabled with fail-closed result shape;
- no memory policy inside the generic port.

Gate:

- unit tests prove valid output, invalid output, provider error, timeout/cancel
  shape, disabled-tool behavior, trace redaction/visibility, and stable reason
  codes.

### S3.5c — Memory-maintenance production runner

Scope:

- implement memory worker runner adapter around the generic port;
- build prompt/messages from worker request/context packet;
- return output through existing `MemoryMaintenanceWorkerAdapter`;
- preserve no direct truth mutation.

Gate:

- fake model returns valid candidate/no-op/failure and adapter receives them;
- invalid model output becomes `WorkerResultStatus.FAILED`;
- missing context/source/base refs map to stable reason codes;
- legacy specialist is not called when production runner is wired.

### S3.5d — Runtime factory wiring and compatibility gate

Scope:

- wire production runner into `RpRuntimeFactory`;
- retain explicit fallback only when runner is disabled/unavailable;
- update tests for both paths.

Gate:

- factory test proves production runner is supplied when enabled;
- fallback test proves compatibility metadata remains when disabled.
- factory-built normal path with fake model gateway proves production runner
  enabled means `LongformSpecialistService.analyze()` is not called.

### S3.5e — Review and commit

Scope:

- focused pytest/ruff/service-size;
- fresh reviewer;
- main-brain adjudication;
- explicit-path commit.

## Risks

| Risk | Mitigation |
| --- | --- |
| Accidentally copying setup-agent executor policy | Read setup only as anti-pattern/reference; scoped import guard forbids setup imports in new story harness/memory runner modules. |
| Harness core absorbs memory policy | Keep prompt/schema in memory runner and validation/governance in product services. |
| Overbuilding universal executor | Limit S3.5 to structured-output runner port and memory worker consumer. |
| Live provider flakiness | Deterministic fake tests are required; live smoke optional. |
| S4 starts on fallback path | Roadmap forbids S4 implementation until S3.5 lands or explicit deferral exists. |

## Rollback

S3.5 must be committed as one or more small reversible commits:

- contracts/fake runner;
- production memory runner;
- factory wiring/tests;
- docs/check records.

If production runner wiring fails, keep S3g-b compatibility fallback intact and
revert only the S3.5 slice.
