# RP Setup Agent Execution Service Outer-Harness Thin Boundary

> Executable contract for keeping `SetupAgentExecutionService` as a thin outer harness: one shared preflight boundary for `run_turn` / `run_turn_stream`, one shared runtime-v2 launch boundary, and no duplicate public-path orchestration drift.

## Scenario: SetupAgentExecutionService Stops Duplicating Turn Launch Between Text And Stream Entry Points

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/services/setup_agent_execution_service.py` or setup runtime tests when the change affects public turn entrypoints, model/provider/workspace preflight, runtime-v2 turn launch assembly, or Langfuse output shaping owned by the execution service.
- Applies only to the execution-service outer harness around setup/prestory runtime-v2 turns.
- This slice is additive cleanup over the current runtime-v2 path. It does not change:
  - `SetupWorkspace` business truth
  - setup context governance policy
  - runtime loop semantics inside `RpAgentRuntimeExecutor`
  - typed SSE event names
  - LangGraph checkpoint shell responsibilities

### 2. Signatures

- `SetupAgentExecutionService.run_turn(request: SetupAgentTurnRequest) -> SetupAgentTurnResponse`
- `SetupAgentExecutionService.run_turn_stream(request: SetupAgentTurnRequest) -> AsyncIterator[str]`
- `_SetupTurnLaunch`
  - `request: SetupAgentTurnRequest`
  - `workspace`
  - `current_step: SetupStepId`
  - `model_name: str`
  - `provider`
- `_PreparedRuntimeV2Launch`
  - `turn_input: RpAgentTurnInput`
  - `context_packet`
  - `profile: RuntimeProfile`
- `SetupAgentExecutionService._prepare_turn_launch(request) -> _SetupTurnLaunch`
- `SetupAgentExecutionService._prepare_runtime_v2_launch(adapter, launch, stream) -> _PreparedRuntimeV2Launch`
- `SetupAgentExecutionService._runtime_v2_observation_output(result: RpAgentTurnResult) -> dict[str, Any]`

### 3. Contracts

#### 3.1 Public Entry Points Share One Outer-Harness Preflight Boundary

- `run_turn(...)` and `run_turn_stream(...)` must both call the same `_prepare_turn_launch(...)`.
- `_prepare_turn_launch(...)` is the only public-path preflight that may:
  - load the workspace
  - resolve the effective `current_step`
  - validate model compatibility
  - resolve provider
  - resolve model name
- Public entrypoints must not each re-implement their own copies of that sequence.

#### 3.2 Runtime-V2 Launch Assembly Is Also Single-Sourced

- `_prepare_runtime_v2_launch(...)` is the only execution-service layer that may:
  - call `_build_runtime_v2_turn_input(...)`
  - set the `stream` flag on `RpAgentTurnInput`
  - build the runtime profile
- `run_turn(...)` and `run_turn_stream(...)` must not each rebuild their own `turn_input + profile` launch sequence inline.

#### 3.3 The Execution Service Remains An Outer Harness, Not A Second Runtime Core

- `SetupAgentExecutionService` may:
  - do outer-harness preflight
  - start outer-harness observations/logging
  - prepare one runtime-v2 launch bundle
  - delegate to `RpAgentRuntimeExecutor`
  - persist post-turn governance
- `SetupAgentExecutionService` must not absorb inner runtime semantics such as:
  - loop routing
  - tool execution policy
  - continue/finish taxonomy derivation
  - message inspection semantics
- Those remain inside runtime-v2 proper.

#### 3.4 Text And Stream Paths May Differ Only At The True Boundary

- After the shared preflight and shared runtime-v2 launch assembly:
  - text path delegates through `runtime_executor.run(...)`
  - stream path delegates through `runtime_executor.run_stream(...)`
- This is the intended boundary.
- Differences before that boundary are drift and must be treated as duplication.

#### 3.5 Langfuse Output Shaping Must Stay Single-Sourced

- `_runtime_v2_observation_output(...)` is the only execution-service helper that shapes observation output fields such as:
  - `finish_reason`
  - `continue_reason`
  - `assistant_text`
  - `warnings`
  - `tool_invocation_count`
  - `tool_result_count`
  - `loop_trace_count`
- Text and stream paths must not keep separate copies of that output dictionary logic.

### 4. Validation & Error Matrix

- workspace missing -> `_prepare_turn_launch(...)` raises `ValueError("SetupWorkspace not found: ...")`
- model incompatible -> `_prepare_turn_launch(...)` raises before any runtime-v2 launch is prepared
- provider/model resolution fails -> `_prepare_turn_launch(...)` raises before delegation
- `stream=False` -> `_prepare_runtime_v2_launch(...)` returns `turn_input.stream is False`
- `stream=True` -> `_prepare_runtime_v2_launch(...)` returns `turn_input.stream is True`
- runtime-v2 result exists -> `_runtime_v2_observation_output(...)` returns stable additive output counts and reasons
- stream path finishes without a final runtime result -> governance persistence is skipped as before; outer-harness helper boundaries do not invent synthetic result state

### 5. Good / Base / Bad Cases

- Good: `run_turn(...)` and `run_turn_stream(...)` both reuse the same preflight object, then diverge only at `runtime_executor.run(...)` vs `runtime_executor.run_stream(...)`.
- Base: a target-step override changes `current_step` once inside `_prepare_turn_launch(...)`, and both text and stream paths inherit the same resolved step.
- Bad: one public path resolves provider/model/step inline while the other path uses a helper, or one path shapes Langfuse output separately and silently drifts.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert `_prepare_turn_launch(...)` resolves workspace, current step, model name, and provider through one shared boundary
  - assert `_prepare_runtime_v2_launch(...)` applies the requested `stream` flag and preserves the expected step-aware tool scope
- Existing setup runtime/API tests must remain green to prove this slice is organizational cleanup rather than semantic behavior change.

### 7. Wrong vs Correct

#### Wrong

- Keep `run_turn(...)` and `run_turn_stream(...)` with parallel copies of workspace/model/provider/step preflight.
- Let text and stream paths each build their own runtime-v2 launch bundle.
- Treat `SetupAgentExecutionService` as another place to accumulate runtime semantics.

#### Correct

- Keep one shared outer-harness preflight boundary.
- Keep one shared runtime-v2 launch boundary.
- Let the execution service stay thin and delegate true loop semantics to runtime-v2.
