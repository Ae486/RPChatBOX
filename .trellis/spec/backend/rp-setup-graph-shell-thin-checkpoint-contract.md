# RP Setup Graph Shell Thin Checkpoint Contract

> Executable contract for keeping the phase-1 SetupGraph shell thin: preserve checkpoint/debug semantics, but remove duplicate pre-model context assembly from the outer graph layer.

## Scenario: SetupGraph Shell Stops Rebuilding SetupContextPacket Before Runtime-V2

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/graphs/setup_graph_runner.py`, `backend/rp/graphs/setup_graph_nodes.py`, `backend/rp/graphs/setup_graph_state.py`, `backend/rp/runtime/rp_runtime_factory.py`, or setup runtime debug/API tests when the change affects what the outer setup graph does before delegating to `SetupAgentExecutionService`.
- Applies only to the phase-1 SetupGraph shell around setup/prestory turns.
- This slice must preserve existing runtime-v2 contracts for context assembly, stage-local governance, loop semantics, and typed SSE. It only narrows the responsibilities of the outer checkpoint shell.

### 2. Signatures

- `SetupGraphState`
  - keep request / checkpoint shell fields:
    - `workspace_id`
    - `mode`
    - `current_step`
    - `target_step`
    - `model_id`
    - `provider_id`
    - `user_prompt`
    - `history`
    - `user_edit_delta_ids`
    - `stream_mode`
    - `status`
    - `assistant_text`
    - `finish_reason`
    - `warnings`
    - `response_payload`
    - `error`
  - remove `context_packet`
- `SetupGraphNodes`
  - remove `SetupContextBuilder` dependency
  - keep:
    - `load_workspace(...) -> SetupGraphState`
    - `run_turn(...) -> SetupGraphState`
    - `finalize_stream(...) -> SetupGraphState`
  - remove `build_context(...) -> SetupGraphState`
- `SetupGraphRunner._compile_graph(...)`
  - route:
    - `START -> load_workspace`
    - `load_workspace -> run_turn` for non-stream mode
    - `load_workspace -> END` for stream preflight mode
- `RpRuntimeFactory.build_setup_graph_runner()`
  - no longer injects `SetupContextBuilder` into `SetupGraphNodes`

### 3. Contracts

#### 3.1 Pre-Model Context Assembly Belongs Only To Runtime-V2

- `SetupContextBuilder.build(...)` for a real setup turn must happen only inside the runtime-v2 execution path owned by `SetupAgentExecutionService`.
- The outer graph shell must not build a second `SetupContextPacket` before calling the execution service.
- This preserves the single-source rule already defined by [RP Setup Agent Pre-Model Context Assembly](./rp-setup-agent-pre-model-context-assembly.md):
  - token budget selection
  - `context_profile`
  - prior-stage handoffs
  - current-step draft snapshot
  - user edit delta selection
  - governed history input

#### 3.2 SetupGraph Shell Owns Checkpoint And Routing, Not Runtime Input Assembly

- The phase-1 SetupGraph shell exists to:
  - validate / load the target workspace
  - resolve `current_step` and effective `target_step`
  - seed a checkpoint thread for debug / resume surfaces
  - delegate the actual turn to `SetupAgentExecutionService`
  - write final stream completion state back into the checkpoint
- The shell must not duplicate runtime-v2 duties such as:
  - building `SetupContextPacket`
  - deciding `context_profile`
  - assembling governed history
  - preparing runtime overlay payloads

#### 3.3 Stream Preflight Must Still Produce A Checkpoint Before External Streaming

- `SetupGraphRunner.run_turn_stream(...)` must continue to do a preflight graph invocation before calling `SetupAgentExecutionService.run_turn_stream(...)`.
- That preflight invocation exists only to:
  - confirm the workspace exists
  - resolve target-step metadata into the checkpoint thread
  - obtain a checkpoint id so the shell can later `aupdate_state(...)` with streamed completion/failure data
- Stream preflight must not build and store a `SetupContextPacket`.

#### 3.4 Debug Surfaces Must Depend On Final Runtime State, Not Shell-Level Context Dumps

- `get_runtime_debug(...)` must continue to derive meaningful state from:
  - `assistant_text`
  - `finish_reason`
  - `warnings`
  - `response_payload`
  - `error`
  - checkpoint history metadata
- Debug output must not rely on a graph-state `context_packet` field being present.
- Any required context/tracing detail should come from runtime-v2 structured payloads rather than a duplicated shell-level packet dump.

#### 3.5 SetupGraphNodes Should Only Carry Data Needed By The Shell

- `load_workspace(...)` may write:
  - `mode`
  - `current_step`
  - effective `target_step`
  - `status = "workspace_loaded"`
- `run_turn(...)` may write:
  - `assistant_text`
  - `status`
  - `finish_reason`
  - `warnings`
  - `response_payload`
  - `error`
- Shell nodes must not materialize extra turn-input artifacts purely for convenience if those artifacts are already recomputed inside runtime-v2.

### 4. Validation & Error Matrix

- non-stream setup turn enters graph shell -> `load_workspace` resolves workspace metadata, then runner delegates directly to `run_turn`
- stream setup turn enters graph shell -> `load_workspace` succeeds, graph exits, checkpoint id is captured, external streaming proceeds, final state is written through `finalize_stream`
- workspace does not exist -> `load_workspace` still sets shell error and execution service is never called
- runtime debug is queried after a completed setup turn -> meaningful checkpoint still exposes `assistant_text`, `response_payload`, and loop trace from runtime-v2
- runtime debug is queried after this slice -> checkpoint state no longer needs or exposes shell-built `context_packet`

### 5. Good / Base / Bad Cases

- Good: the setup graph thread stores workspace/step metadata before execution, the runtime-v2 service builds the only `SetupContextPacket`, and debug reads the final runtime payload from the checkpoint.
- Base: stream preflight creates a checkpoint with `status = workspace_loaded`, then `finalize_stream` updates that checkpoint with the real runtime result after streaming ends.
- Bad: the graph shell builds `SetupContextPacket` with `token_budget=None`, stores it in checkpoint state, and the execution service then rebuilds a second packet with the real runtime-v2 budget/profile.

### 6. Tests Required

- `backend/tests/test_rp_setup_agent_api.py`
  - setup runtime debug coverage must stay green
  - assert checkpoint state no longer exposes shell-level `context_packet`
  - keep stream setup turn coverage green after the graph-shell route change
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - keep governed-history/context-profile assertions green, proving the single real context build still happens inside runtime-v2
- `python -m py_compile`
  - compile:
    - `backend/rp/graphs/setup_graph_runner.py`
    - `backend/rp/graphs/setup_graph_nodes.py`
    - `backend/rp/graphs/setup_graph_state.py`
    - `backend/rp/runtime/rp_runtime_factory.py`
- `git diff --check`
  - ensure graph-shell and spec edits are patch-clean

### 7. Wrong vs Correct

#### Wrong

- Let the outer graph shell prebuild `SetupContextPacket` "for debug convenience".
- Keep `context_packet` in checkpoint state even though runtime-v2 already rebuilds it with the real token budget and governance inputs.
- Treat the phase-1 shell as another context-assembly layer instead of a checkpoint/routing wrapper.

#### Correct

- Keep `SetupContextBuilder.build(...)` single-sourced inside runtime-v2 turn preparation.
- Let the outer SetupGraph shell handle only workspace preflight, checkpoint seeding, routing, and final-state persistence.
- Keep runtime debug grounded in final runtime payloads instead of duplicated shell context dumps.
