# RP Setup Agent Runtime-V2 Only Convergence

> Executable contract for converging SetupAgent execution onto runtime-v2 only: remove the legacy ToolRuntime fallback, delete the rollout flag, and keep all setup entrypoints on one runtime path.

## Scenario: SetupAgent Stops Carrying A Transitional Dual-Runtime Main Path

### 1. Scope / Trigger

- Trigger: add or edit `backend/config.py`, `backend/rp/runtime/rp_runtime_factory.py`, `backend/rp/services/setup_agent_execution_service.py`, `backend/rp/graphs/setup_graph_runner.py`, setup runtime debug surfaces, or setup API/tests when the change affects how SetupAgent turn execution is wired.
- Applies only to setup/prestory turn execution. It does not change `SetupWorkspace` truth, setup tool schemas, stage-local context governance, loop semantics, or typed SSE event names.
- This slice removes a transitional runtime split. It must converge the existing default runtime-v2 path into the only supported path rather than introducing a new execution framework.

### 2. Signatures

- `Settings`
  - remove `rp_setup_agent_runtime_v2_enabled`
  - remove env aliases:
    - `CHATBOX_BACKEND_RP_SETUP_AGENT_RUNTIME_V2_ENABLED`
    - `RP_SETUP_AGENT_RUNTIME_V2_ENABLED`
- `RpRuntimeFactory`
  - remove `_use_setup_runtime_v2() -> bool`
  - `build_setup_agent_execution_service() -> SetupAgentExecutionService`
    - always constructs:
      - `runtime_executor: RpAgentRuntimeExecutor`
      - `adapter: SetupRuntimeAdapter`
      - `runtime_state_service: SetupAgentRuntimeStateService`
  - `build_setup_graph_runner() -> SetupGraphRunner`
    - always injects the same runtime-v2-backed `SetupAgentExecutionService`
- `SetupAgentExecutionService`
  - remove legacy-only helpers:
    - `_SetupToolRuntimeLLMAdapter`
    - `_build_chat_request(...) -> ChatCompletionRequest`
    - `_history_to_chat_messages(...) -> list[ChatMessage]`
  - `run_turn(...) -> SetupAgentTurnResponse`
    - always routes through `_run_turn_v2(...)`
  - `run_turn_stream(...) -> AsyncIterator[str]`
    - always routes through `_run_turn_stream_v2(...)`
  - `_require_runtime_v2_components(...) -> tuple[SetupRuntimeAdapter, RpAgentRuntimeExecutor]`
    - remains the invariant guard for construction bugs
- `RpAgentTurnResult.finish_reason`
  - remove `"legacy_tool_runtime"` from the reachable SetupAgent finish-reason surface

### 3. Contracts

#### 3.1 Runtime-V2 Is The Only SetupAgent Turn Engine

- All setup turn entrypoints must use runtime-v2:
  - direct service execution through `SetupAgentExecutionService`
  - `SetupGraphRunner`
  - setup API turn endpoint
  - setup API stream endpoint
  - runtime debug surfaces backed by setup checkpoints/results
- No setup turn entrypoint may branch between runtime-v2 and a legacy ToolRuntime path at runtime.

#### 3.2 Dual-Track Rollout Flag Must Be Removed, Not Ignored

- `rp_setup_agent_runtime_v2_enabled` and its env aliases must be deleted from settings.
- Factory/service code must not keep dead reads of a removed flag.
- Tests must stop mutating the removed env keys as part of normal setup-agent behavior verification.
- Rollback after this slice is operationally handled by Git/release rollback, not by an in-process runtime switch.

#### 3.3 Factory Wiring Must Stay Single-Sourced

- `RpRuntimeFactory` remains the only place that wires setup runtime-v2 dependencies for production entrypoints.
- `build_setup_agent_execution_service()` and `build_setup_graph_runner()` must both construct:
  - `SetupWorkspaceService`
  - `SetupContextBuilder`
  - `SetupAgentRuntimeStateService`
  - `RpAgentRuntimeExecutor`
  - `SetupRuntimeAdapter`
- The graph runner and the direct execution service must not diverge in runtime engine selection.

#### 3.4 SetupAgentExecutionService Must Only Orchestrate Runtime-V2

- `SetupAgentExecutionService.run_turn(...)` must:
  1. load workspace
  2. validate model compatibility
  3. resolve provider and model name
  4. call `_run_turn_v2(...)`
  5. convert the result through `SetupRuntimeAdapter.to_turn_response(...)`
- `SetupAgentExecutionService.run_turn_stream(...)` must:
  1. load workspace
  2. validate model compatibility
  3. resolve provider and model name
  4. stream from `_run_turn_stream_v2(...)`
- Service code must not build a second chat-request assembly path for setup execution after this slice.
- The existing runtime-v2 services remain authoritative for:
  - pre-model context assembly
  - stage-local context governance persistence
  - loop semantics / `continue_reason` / `finish_reason`
  - Langfuse runtime-v2 observations

#### 3.5 Legacy ToolRuntime Artifacts Must Disappear From SetupAgent Turn Semantics

- The setup-specific legacy ToolRuntime adapter and request-history conversion helpers must be deleted, not left unused.
- `"legacy_tool_runtime"` must stop appearing as a valid setup turn `finish_reason`.
- Setup runtime debug and API tests must assert runtime-v2 finish reasons such as `completed_text`, `awaiting_user_input`, `continue_discussion`, or failure reasons defined by the loop-semantic/runtime policies.

#### 3.6 Boundary With Existing Runtime-V2 Specs Must Stay Clean

- This slice does not redefine:
  - stage-local context governance
  - pre-model context assembly
  - stage-aware tool scope
  - structured-output schema repair
  - loop-semantic continue/finish taxonomy
- This slice only makes those runtime-v2 contracts the sole reachable setup turn path.

### 4. Validation & Error Matrix

- settings are loaded after this slice -> no `rp_setup_agent_runtime_v2_enabled` field or related env alias exists
- `RpRuntimeFactory.build_setup_agent_execution_service()` is called -> returned service always has non-`None` `_runtime_executor` and `_adapter`
- `RpRuntimeFactory.build_setup_graph_runner()` is called -> runner-owned execution service always has non-`None` `_runtime_executor` and `_adapter`
- setup API turn request executes normally -> runtime debug finish reason is one of the runtime-v2 finish reasons, never `"legacy_tool_runtime"`
- setup API stream request executes normally -> stream output still uses typed SSE events from runtime-v2 and runtime governance persists as before
- a developer tries to disable runtime-v2 via env -> no runtime branch exists; behavior stays on runtime-v2
- runtime-v2 components are accidentally constructed as `None` -> `_require_runtime_v2_components(...)` raises a runtime configuration error instead of silently falling back

### 5. Good / Base / Bad Cases

- Good: factory-built setup services and graph runner both execute through runtime-v2, persist governance, emit runtime-v2 finish reasons, and no longer know about a legacy fallback.
- Base: a simple setup turn with no tool call still ends through runtime-v2 as `completed_text` and runtime debug reconstructs the turn from runtime-v2 checkpoints only.
- Bad: leaving the legacy fallback branch in place "just in case", keeping a dead settings flag, or allowing tests/debug surfaces to keep asserting `"legacy_tool_runtime"`.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert factory-built service and graph runner always inject runtime-v2 executor/adapter
  - keep the context-budget and governed-history assertions green after legacy helper removal
- `backend/tests/test_rp_setup_agent_api.py`
  - remove legacy fallback coverage
  - assert default setup turn path still works and debug output reports runtime-v2 finish reasons
  - assert model capability inference path still succeeds without relying on a rollout flag
- `python -m py_compile`
  - compile `backend/config.py`
  - compile `backend/rp/runtime/rp_runtime_factory.py`
  - compile `backend/rp/services/setup_agent_execution_service.py`
- `git diff --check`
  - ensure spec/code/test edits introduce no whitespace or patch-format issues

### 7. Wrong vs Correct

#### Wrong

- Keep the rollout flag but just stop setting it.
- Leave the legacy ToolRuntime codepath in the main service as an "emergency fallback".
- Let graph runner and direct service execution choose different setup runtimes.
- Continue asserting `"legacy_tool_runtime"` in debug or API tests after runtime-v2 has become the only engine.

#### Correct

- Delete the rollout flag and the legacy setup fallback codepath together.
- Keep factory wiring single-sourced so all setup entrypoints share the same runtime-v2 engine.
- Preserve existing runtime-v2 contracts and tests while removing the obsolete branch around them.
- Treat rollback as a release/commit concern, not an in-process dual-runtime switch.
