# RP Setup Agent Stage-Aware Tool Scope

> Executable contract for SetupAgent runtime-v2 stage/step-aware tool visibility through `SetupCapabilityPlan`: expose the current `setup.stage_entry.*` draft CRUD surface for canonical draft stages, keep setup-owned memory readback tools available, and keep provider registration, runtime allowlist, prompt guidance, and model schemas in sync.

## Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/profiles.py`, `backend/rp/agent_runtime/adapters.py`, `backend/rp/agent_runtime/tools.py`, `backend/rp/tools/setup_tool_provider.py`, prompt service, execution service, or setup runtime tests when the change affects which setup tools are exposed to SetupAgent for one turn.
- Applies only to setup/prestory runtime-v2 tool visibility for the main interactive SetupAgent.
- This contract removes confirmed-obsolete agent tool chains from the provider/model surface. It does not delete lower-level UI/backend service capabilities.

## Current Tool Surface

`SetupCapabilityPlan` is the single turn-level source for:

- `active_tool_names`
- `runtime_allowlist`
- prompt guidance fragments
- provider-visible schema filtering through `RpAgentTurnInput.tool_scope`

The retained setup tools are:

- `setup.stage_entry.list`
- `setup.stage_entry.read`
- `setup.stage_entry.write`
- `setup.stage_entry.edit`
- `setup.stage_entry.delete`
- `setup.asset.register`
- `setup.memory.search`
- `setup.memory.open`
- `setup.memory.read_refs`

The removed agent tools must not appear in provider registry/list/schema/handler maps, SetupAgent visible tools, runtime allowlists, model requests, or prompt guidance:

- `setup.proposal.commit`
- `setup.question.raise`
- `setup.discussion.update_state`
- `setup.chunk.upsert`
- `setup.world_background.*`
- `setup.truth.write`
- `setup.patch.story_config`
- `setup.patch.writing_contract`
- `setup.patch.foundation_entry`
- `setup.patch.longform_blueprint`
- old read/index public tools:
  - `setup.read.workspace`
  - `setup.read.step_context`
  - `setup.read.draft_refs`
  - `setup.truth_index.search`
  - `setup.truth_index.read_refs`
- external Memory OS read-only tools:
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.search_recall`
  - `memory.search_archival`
  - `memory.list_versions`
  - `memory.read_provenance`

## Stage Rules

- `world_background` exposes `setup.stage_entry.*` and writes only `workspace.draft_blocks["world_background"]`.
- `character_design` exposes `setup.stage_entry.*` and writes only `workspace.draft_blocks["character_design"]`.
- `plot_blueprint` exposes `setup.stage_entry.*` and writes only `workspace.draft_blocks["plot_blueprint"]`.
- The model must not provide `stage_id`; current stage is backend/runtime-owned.
- SetupAgent memory lookups use setup-owned `setup.memory.search` and `setup.memory.open` as the agent-facing recall workflow; `setup.memory.read_refs` may remain registered or allowlisted only as a compatibility/internal readback path. External Memory OS tools are not exposed to SetupAgent.
- Legacy `SetupStepId` mirrors may still exist for compatibility, but they must not reintroduce `setup.truth.write` or `setup.patch.*` as SetupAgent tools.
- Unknown or unmapped stages may fall back to the conservative retained visible-tool union, but the removed tools above remain absent.

## Contracts

- Prompt guidance cannot open a tool. Provider registration cannot expose a tool to the model. Runtime allowlist remains the execution gate.
- `SetupCapabilityPlan.active_tool_names`, `runtime_allowlist`, and prompt guidance must be derived together.
- Prompt rendering must filter any guidance fragment whose `tool_names` are not a subset of `active_tool_names`.
- `model_schema_modes` no longer carries a `setup.truth.write` runtime adapter mode. If stale metadata includes that key, the executor ignores it because the tool is not exposed.
- Provider deletion-protection tests may mention removed tool names only as negative assertions.

## Validation Matrix

- `current_stage = "world_background"` -> scope contains `setup.stage_entry.*`, `setup.memory.search`, `setup.memory.open`, compatibility `setup.memory.read_refs` where still required, and excludes all removed tools.
- `current_stage = "character_design"` -> scope contains `setup.stage_entry.*`, `setup.memory.search`, `setup.memory.open`, compatibility `setup.memory.read_refs` where still required, and excludes all removed tools.
- `current_stage = "plot_blueprint"` -> scope contains `setup.stage_entry.*`, `setup.memory.search`, `setup.memory.open`, compatibility `setup.memory.read_refs` where still required, and excludes all removed tools.
- `current_step = "story_config"`, `writing_contract`, `foundation`, or `longform_blueprint` -> scope may keep `setup.memory.search`, `setup.memory.open`, compatibility `setup.memory.read_refs`, and `setup.asset.register`, but must not expose old read/index, `setup.truth.write`, or `setup.patch.*`.
- every SetupAgent scope/model request/prompt -> contains no external Memory OS tools, while `setup.memory.search` and `setup.memory.open` remain available as the main workflow.
- provider registry/list/schema/handler maps do not contain removed tools.
- model request tools match `tool_scope`; removed tools do not appear in request schemas.
- prompt guidance mentions only active tools.

## Tests Required

- `backend/rp/tests/test_setup_agent_tool_scope.py`
  - assert stage-entry tools are visible for `world_background`, `character_design`, and `plot_blueprint`
  - assert removed tools are absent from SetupAgent scope
  - assert capability guidance only references active tools
- `backend/rp/tests/test_setup_tool_provider.py`
  - assert provider registry/schema/handler/list order stay aligned
  - assert removed tools return `UNKNOWN_TOOL`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert turn input scope excludes removed tools
  - assert capability-plan metadata and prompt guidance stay aligned
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert model requests only include retained scoped tools
  - assert stale removed-tool schema-mode metadata does not reintroduce schemas
- `backend/rp/tests/test_setup_agent_prompt_service.py`
  - assert prompt mentions only active capability tools

## Wrong vs Correct

Wrong:

- Reintroduce old draft CRUD tools as a fallback.
- Keep old patch/truth-write names in prompt guidance while hiding them in schema.
- Let model input include `stage_id`.

Correct:

- Use `setup.stage_entry.*` as the sole model-facing draft CRUD surface for the canonical draft stages.
- Use `setup.memory.search` and `setup.memory.open` as the sole recommended model-facing setup recall workflow; keep `setup.memory.read_refs` only for compatibility/internal readback while the transition is incomplete.
- Keep lower-level services decoupled from model tools.
- Treat deleted tool names in current tests as negative deletion-protection only.
