# RP Setup Agent Stage-Aware Tool Scope

> Executable contract for SetupAgent runtime-v2 step-aware tool visibility: keep shared setup tools available, expose only the current-step patch family by default, and fall back conservatively when step mapping is unknown.

## Scenario: SetupAgent Sees A Small Tool Set Matched To The Current Setup Step

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/profiles.py`, `backend/rp/agent_runtime/adapters.py`, `backend/rp/agent_runtime/tools.py`, `backend/rp/tools/setup_tool_provider.py`, or setup runtime tests when the change affects which tool schemas are exposed to SetupAgent for one turn.
- Applies only to setup/prestory runtime-v2 tool visibility for the main interactive SetupAgent.
- This slice is a context-and-control optimization. It does not add new setup tools, remove existing tool implementations, change business tool contracts, or introduce a full dynamic tool-search subsystem.
- This slice must stay smaller than a full "tool semantics layer". The immediate goal is step-aware allowed-tool narrowing, not a new metadata framework.

### 2. Signatures

- `SETUP_READ_ONLY_MEMORY_TOOLS: tuple[str, ...]`
- `SETUP_SHARED_PRIVATE_TOOLS: tuple[str, ...]`
  - required members:
    - `setup.discussion.update_state`
    - `setup.chunk.upsert`
    - `setup.truth.write`
    - `setup.question.raise`
    - `setup.asset.register`
    - `setup.proposal.commit`
    - `setup.read.workspace`
    - `setup.read.step_context`
- `SETUP_STEP_PATCH_TOOLS: dict[str, tuple[str, ...]]`
  - `story_config -> ("setup.patch.story_config",)`
  - `writing_contract -> ("setup.patch.writing_contract",)`
  - `foundation -> ("setup.patch.foundation_entry",)`
  - `longform_blueprint -> ("setup.patch.longform_blueprint",)`
- `SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...]`
  - remains the conservative full-union fallback
- `build_setup_agent_tool_scope(current_step: str | None) -> list[str]`
- `build_setup_agent_profile() -> RuntimeProfile`
  - keeps the full-union fallback in `visible_tool_names`
- `SetupRuntimeAdapter.build_turn_input(...)`
  - must set `RpAgentTurnInput.tool_scope` from `build_setup_agent_tool_scope(current_step.value)`

### 3. Contracts

#### 3.1 Shared Tools Always Stay Visible

- SetupAgent always keeps these tool families visible:
  - read-only memory tools from `SETUP_READ_ONLY_MEMORY_TOOLS`
  - shared setup-private tools from `SETUP_SHARED_PRIVATE_TOOLS`
- Reason:
  - read helpers remain available for lookup and verification
  - shared setup tools remain available for discussion state, chunking, truth write, questions, assets, commit proposals, and deterministic step-context reads

#### 3.2 Only The Current-Step Patch Family Is Added By Default

- `story_config` step:
  - add `setup.patch.story_config`
- `writing_contract` step:
  - add `setup.patch.writing_contract`
- `foundation` step:
  - add `setup.patch.foundation_entry`
- `longform_blueprint` step:
  - add `setup.patch.longform_blueprint`
- Other patch families must stay hidden for that turn unless the runtime intentionally falls back to the conservative full set.

#### 3.3 Unknown Steps Fall Back Conservatively

- If `current_step` is absent or not mapped in `SETUP_STEP_PATCH_TOOLS`, `build_setup_agent_tool_scope(...)` must return the full `SETUP_AGENT_VISIBLE_TOOLS`.
- This fallback exists to prevent accidental tool starvation during partial rollout, future step additions, or malformed step state.
- Known-step behavior must stay deterministic and minimal; unknown-step behavior may stay conservative.

#### 3.4 Tool Scope Is Turn Input State, Not MCP Registry Truth

- `RuntimeToolRegistryView` still resolves tools from the full registry.
- `tool_scope` is the runtime turn-level allowlist applied before tool schemas reach the model and before tool execution is accepted.
- This slice narrows what the model can see/call for the current turn; it does not unregister or delete tools from MCP/local providers.

#### 3.5 This Slice Narrows Context Before A Full Tool-Semantics Layer Exists

- This slice is intentionally smaller than a full metadata/policy system.
- It does not yet model:
  - parallel-safe vs sequential-only execution
  - expensive vs cheap tools
  - destructive vs non-destructive mutation classes
  - stage-skill-driven temporary tool boosts
- Those belong to later tool-semantics work.
- The current slice only guarantees a smaller, step-matched default tool inventory.

### 4. Validation & Error Matrix

- `current_step = "story_config"` -> `tool_scope` contains shared tools plus `setup.patch.story_config`, and excludes the other three patch tools
- `current_step = "writing_contract"` -> `tool_scope` contains shared tools plus `setup.patch.writing_contract`, and excludes the other three patch tools
- `current_step = "foundation"` -> `tool_scope` contains shared tools plus `setup.patch.foundation_entry`, and excludes the other three patch tools
- `current_step = "longform_blueprint"` -> `tool_scope` contains shared tools plus `setup.patch.longform_blueprint`, and excludes the other three patch tools
- `current_step` is unknown or missing -> `tool_scope` falls back to full `SETUP_AGENT_VISIBLE_TOOLS`
- narrowing happens for one turn only -> MCP/local tool registry contents remain unchanged
- a shared tool such as `setup.proposal.commit` is needed during any known step -> it remains visible because it is part of `SETUP_SHARED_PRIVATE_TOOLS`

### 5. Good / Base / Bad Cases

- Good: during `story_config`, the model can still read workspace state, update discussion state, write truth, raise questions, and commit, but it no longer sees `setup.patch.foundation_entry` or `setup.patch.longform_blueprint`.
- Base: during an unknown future setup step, the runtime falls back to the full tool union so rollout does not break.
- Bad: always exposing every patch-family tool regardless of step, or removing shared tools so narrowly that the agent cannot ask questions, read step context, or propose commit when appropriate.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_tool_scope.py`
  - assert each known step gets shared tools plus only its mapped patch tool
  - assert unknown step falls back to `SETUP_AGENT_VISIBLE_TOOLS`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert runtime-v2 turn input for a known step uses the narrowed `tool_scope`
  - assert current-step compaction/governance behavior still works with the narrowed tool scope
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert visible tool schema count reflects the narrowed scope when `tool_scope` is provided

### 7. Wrong vs Correct

#### Wrong

- Keep all setup patch tools visible for every setup step forever.
- Encode step-aware tool visibility only in prompt prose while still exposing the full tool list to the model.
- Replace the MCP/local registry with a filtered registry as if tool removal were global system truth.
- Expand this slice into a full metadata-heavy tool semantics framework before the minimal narrowing is landed.

#### Correct

- Keep shared setup tools visible, then add only the current-step patch family by default.
- Apply narrowing at the runtime turn input boundary through `tool_scope`.
- Use a conservative full-union fallback for unknown steps.
- Treat this as a small context-engineering improvement, not as a grand tool-system rewrite.
