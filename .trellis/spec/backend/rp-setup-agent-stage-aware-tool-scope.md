# RP Setup Agent Stage-Aware Tool Scope

> Executable contract for SetupAgent runtime-v2 stage/step-aware tool visibility through `SetupCapabilityPlan`: keep shared setup tools available, expose only accepted stage/step tools by default, keep prompt/schema/runtime allowlist in sync, and fall back conservatively when mapping is unknown.

## Scenario: SetupAgent Sees A Small Tool Set Matched To The Current Setup Step

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/profiles.py`, `backend/rp/agent_runtime/adapters.py`, `backend/rp/agent_runtime/tools.py`, `backend/rp/tools/setup_tool_provider.py`, or setup runtime tests when the change affects which tool schemas are exposed to SetupAgent for one turn.
- Applies only to setup/prestory runtime-v2 tool visibility for the main interactive SetupAgent.
- This slice is a context-and-control optimization. It does not add new setup tools, remove existing tool implementations, change business tool contracts, or introduce a full dynamic tool-search subsystem.
- This slice must stay smaller than a full "tool semantics layer". `SetupCapabilityPlan` is limited to turn-local tool names, schema modes, prompt guidance fragments, candidate exclusions, and snapshot expectations. It does not model cost, parallelism, permissions, destructive write classes, or tool search.

### 2. Signatures

- `SetupCapabilityGuidanceFragment`
  - `fragment_id: str`
  - `tool_names: list[str]`
  - `text: str`
- `SetupCapabilityPlan`
  - `stage_id: str | None`
  - `step_id: str | None`
  - `active_tool_names: list[str]`
  - `model_schema_modes: dict[str, str]`
  - `runtime_allowlist: list[str]`
  - `prompt_guidance_fragments: list[SetupCapabilityGuidanceFragment]`
  - `candidate_exclusions: list[str]`
  - `snapshot_expectations: dict[str, Any]`
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
- canonical stage compatibility is additive during migration:
  - known canonical stages map to no legacy patch-family tools by default
  - stage draft writes go through shared `setup.truth.write`, which remains visible for every known stage
  - legacy `SetupStepId` values still expose their old patch-family tools for compatibility when no canonical `current_stage` is available
  - stage-local CRUD candidates such as `setup.world_background.*` stay hidden until a separate product/tool slice explicitly accepts them
- `SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...]`
  - remains the conservative full-union fallback
- `SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS: tuple[str, ...]`
  - currently includes candidate `setup.world_background.*` tools
- `build_setup_agent_capability_plan(current_step: str | None, *, current_stage: str | None = None) -> SetupCapabilityPlan`
  - accepts a legacy step id plus optional canonical stage id string
  - uses `current_stage` as the scope key when present
  - keeps `step_id` as the legacy/current step mirror even when `stage_id` is present
- `build_setup_agent_tool_scope(current_step: str | None) -> list[str]`
  - accepts either a legacy step id or a canonical stage id string
  - remains a compatibility wrapper over `build_setup_agent_capability_plan(...).runtime_allowlist`
- `build_setup_agent_profile() -> RuntimeProfile`
  - keeps the full-union fallback in `visible_tool_names`
- `SetupRuntimeAdapter.build_turn_input(...)`
  - must build one `SetupCapabilityPlan` from the resolved current stage when available, otherwise from the legacy current step
  - must set `RpAgentTurnInput.tool_scope = capability_plan.runtime_allowlist`
  - must pass the same plan into `SetupAgentPromptService.build_system_prompt(...)`
  - may put a debug/eval snapshot in `RpAgentTurnInput.metadata["capability_plan"]`; this snapshot is not `SetupWorkspace` truth
  - `RpAgentRuntimeExecutor` consumes `metadata["capability_plan"]["model_schema_modes"]` when choosing model-facing schema adapters such as `setup_truth_write_runtime_adapted`

### 3. Contracts

#### 3.1 CapabilityPlan Is The Single Turn-Level Tool Surface

- `SetupCapabilityPlan.active_tool_names`, `runtime_allowlist`, and model-visible schema selection must be derived from the same plan.
- Prompt guidance must be rendered from `prompt_guidance_fragments`, not from an independent hard-coded tool list.
- Prompt rendering must still filter fragments whose `tool_names` are not a subset of `active_tool_names`; this is a fail-closed guard against malformed test fixtures, future manual construction, and partial migrations.
- `model_schema_modes` is the contract for runtime-owned model-facing schema adapters:
  - `setup.truth.write -> setup_truth_write_runtime_adapted` means the executor may expose the slim runtime-adapted schema when runtime defaults are available
  - explicit `provider_default` means the executor must keep the provider/default schema
  - absent capability metadata may keep legacy fallback behavior during migration
- Prompt guidance cannot open a tool. Provider registration cannot expose a tool. The runtime allowlist remains the execution gate.

#### 3.2 Shared Tools Always Stay Visible

- SetupAgent always keeps these tool families visible for mapped setup stages/steps:
  - read-only memory tools from `SETUP_READ_ONLY_MEMORY_TOOLS`
  - shared setup-private tools from `SETUP_SHARED_PRIVATE_TOOLS`
- Reason:
  - read helpers remain available for lookup and verification
  - shared setup tools remain available for discussion state, chunking, truth write, questions, assets, commit proposals, and deterministic step-context reads

#### 3.3 Only The Current-Step Patch Family Is Added By Default

- `story_config` step:
  - add `setup.patch.story_config`
- `writing_contract` step:
  - add `setup.patch.writing_contract`
- `foundation` step:
  - add `setup.patch.foundation_entry`
- `longform_blueprint` step:
  - add `setup.patch.longform_blueprint`
- Other patch families must stay hidden for that turn unless the runtime intentionally falls back to the conservative full set.

#### 3.4 Unknown Steps Fall Back Conservatively

- If `current_step` is absent or not mapped in `SETUP_STEP_PATCH_TOOLS`, `build_setup_agent_tool_scope(...)` must return the full `SETUP_AGENT_VISIBLE_TOOLS`.
- This fallback exists to prevent accidental tool starvation during partial rollout, future step additions, or malformed step state.
- Known-step behavior must stay deterministic and minimal; unknown-step behavior may stay conservative.
- For canonical stages, tool scope must stay stage-native and protocol-driven:
  - known canonical stages do not expose old patch-family tools by default
  - do not remove shared setup tools
  - do not add a new dynamic tool-resolution layer
  - do not expose stage-local CRUD candidates merely because they are registered by the provider
  - shared `setup.truth.write` is the stage write surface unless a future product/tool slice explicitly accepts another model-visible write family

#### 3.5 Tool Scope Is Turn Input State, Not MCP Registry Truth

- `RuntimeToolRegistryView` still resolves tools from the full registry.
- `tool_scope` is the runtime turn-level allowlist applied before tool schemas reach the model and before tool execution is accepted.
- This slice narrows what the model can see/call for the current turn; it does not unregister or delete tools from MCP/local providers.

#### 3.6 This Slice Narrows Context Before A Full Tool-Semantics Layer Exists

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
- `current_step = "world_background"` -> `tool_scope` contains shared tools including `setup.truth.write` and excludes all legacy `setup.patch.*` tools
- `current_step = "character_design"` -> `tool_scope` contains shared tools including `setup.truth.write` and excludes all legacy `setup.patch.*` tools
- `current_step` is unknown or missing -> `tool_scope` falls back to full `SETUP_AGENT_VISIBLE_TOOLS`
- narrowing happens for one turn only -> MCP/local tool registry contents remain unchanged
- a shared tool such as `setup.proposal.commit` is needed during any known step -> it remains visible because it is part of `SETUP_SHARED_PRIVATE_TOOLS`
- canonical stage plan for `current_step = foundation`, `current_stage = world_background` -> `stage_id = "world_background"` and `step_id = "foundation"`
- `SetupCapabilityPlan.runtime_allowlist` differs from `active_tool_names` -> invalid; tests must fail
- prompt guidance fragment references a tool absent from `active_tool_names` -> fragment is not rendered
- `model_schema_modes["setup.truth.write"] = "setup_truth_write_runtime_adapted"` -> executor may expose the runtime-adapted slim schema when defaults are available
- `model_schema_modes["setup.truth.write"] = "provider_default"` -> executor must keep the provider/default schema for that tool

### 5. Good / Base / Bad Cases

- Good: during `story_config`, the model can still read workspace state, update discussion state, write truth, raise questions, and commit, but it no longer sees `setup.patch.foundation_entry` or `setup.patch.longform_blueprint`.
- Good: during `world_background`, the model sees `setup.truth.write` guidance and schema mode from the same capability plan that also powers `tool_scope`; `setup.world_background.write_entry` stays hidden even if registered by the provider.
- Base: during an unknown future setup step, the runtime falls back to the full tool union so rollout does not break.
- Bad: always exposing every patch-family tool regardless of step, removing shared tools so narrowly that the agent cannot ask questions/read context/propose commit, or allowing prompt guidance to mention inactive candidate tools.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_tool_scope.py`
  - assert each known step gets shared tools plus only its mapped patch tool
  - assert canonical stages get shared tools, `setup.truth.write`, and no legacy patch-family tools
  - assert unknown step falls back to `SETUP_AGENT_VISIBLE_TOOLS`
  - assert capability snapshots include both stage and step identity when canonical stage context exists
  - assert `prompt_guidance_fragments[*].tool_names` are subsets of `active_tool_names`
  - assert provider-registered candidate tools remain absent from schema-visible tools when filtered by `runtime_allowlist`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert runtime-v2 turn input for a known step uses the narrowed `tool_scope`
  - assert current-step compaction/governance behavior still works with the narrowed tool scope
  - assert adapter metadata carries the capability-plan snapshot used to build the prompt and `tool_scope`
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert visible tool schema count reflects the narrowed scope when `tool_scope` is provided
  - assert `setup.truth.write` model-facing schema mode is read from `SetupCapabilityPlan.model_schema_modes`
  - assert explicit provider-default schema mode disables the runtime-adapted slim schema
- `backend/rp/tests/test_setup_agent_prompt_service.py`
  - assert prompt mentions only active capability tools
  - assert malformed/injected guidance for inactive tools is filtered before rendering

### 7. Wrong vs Correct

#### Wrong

- Keep all setup patch tools visible for every setup step forever.
- Encode step-aware tool visibility only in prompt prose while still exposing the full tool list to the model.
- Replace the MCP/local registry with a filtered registry as if tool removal were global system truth.
- Expand this slice into a full metadata-heavy tool semantics framework before the minimal narrowing is landed.
- Let prompt service hard-code tool guidance independently from `SetupCapabilityPlan`.
- Let executor hard-code runtime-adapted schema selection without consulting `SetupCapabilityPlan.model_schema_modes`.

#### Correct

- Keep shared setup tools visible, then add only the current-step patch family by default.
- Apply narrowing at the runtime turn input boundary through `tool_scope`.
- Use a conservative full-union fallback for unknown steps.
- Treat this as a small context-engineering improvement, not as a grand tool-system rewrite.
- Build one `SetupCapabilityPlan` per turn and consume it for prompt guidance, runtime allowlist, and schema mode selection.
- Keep `SetupToolProvider` as the authority for pydantic validation, deterministic business validation, workspace mutation, and structured tool result/error payloads.
