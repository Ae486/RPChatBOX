# RP Setup Agent Slim Truth Write Tool Surface

> Executable contract for the SetupAgent `setup.truth.write` model-facing tool surface: expose a smaller schema by default, inject runtime-owned fields before execution, optionally add strict-tool flags for verified models, and keep provider-side pydantic validation as the final authority.

## Scenario: SetupAgent Uses A Slim Truth-Write Tool Surface With Strict As Enhancement

### 1. Scope / Trigger

- Trigger: add or edit `backend/models/mcp_config.py`, `backend/rp/agent_runtime/tools.py`, `backend/rp/agent_runtime/executor.py`, `backend/rp/tools/setup_tool_provider.py`, or setup runtime tests when the change affects the OpenAI tool definition or execution arguments for `setup.truth.write`.
- Applies only to the SetupAgent runtime-v2 model-facing `setup.truth.write` tool surface.
- This is a focused slice, not a global MCP/tool rewrite:
  - do not enable strict tools for every MCP tool
  - do not change the public/provider-side `SetupTruthWriteInput` contract
  - do not remove pydantic validation or the bounded repair loop
  - do not split setup truth writes into many new tools

### 2. Sources

- OpenAI / New API function-calling docs: `tools[].function.strict = true` means the model should follow the provided JSON schema; strict mode supports only a JSON Schema subset.
- OpenAI strict structured-output constraints: strict schemas need closed object shapes and required fields; optional values should be represented explicitly, usually with nullable types.
- LiteLLM docs and current implementation: top-level `tools` and `tool_choice` are forwarded, but provider/model support and nested `function.strict` behavior must be verified through actual request snapshots and opt-in real-model tests.
- DeepSeek / GLM / Gemini provider evidence in `research/structured-output-provider-notes-2026-04-30.md`: OpenAI-compatible transport does not guarantee identical strict-tool semantics across providers.
- User-confirmed engineering direction: the common structured-output path must itself be strongly constrained; `strict`, `response_format`, and provider-specific parameters are enhancements, not the only source of correctness.
- Existing project contract: `rp-setup-agent-structured-output-schema-repair.md` remains authoritative for provider-side validation failure and one bounded repair retry.

### 3. Signatures

- `SETUP_TRUTH_WRITE_TOOL_NAME = "setup.truth.write"`
- `SETUP_TRUTH_WRITE_QUALIFIED_NAME = "rp_setup__setup.truth.write"`
- `SETUP_TRUTH_WRITE_BLOCK_TYPE_BY_STEP: dict[str, str]`
  - `story_config -> story_config`
  - `writing_contract -> writing_contract`
  - `foundation -> foundation_entry`
  - `longform_blueprint -> longform_blueprint`
- `SETUP_TRUTH_WRITE_STAGE_BLOCK_TYPE = "stage_draft"`
- Runtime-owned `truth_write.stage_id: SetupStageId | None`
  - injected only when the current turn has a canonical `current_stage`
- Runtime model-facing tool schema for `setup.truth.write`:
  - top-level required field: `truth_write`
  - `truth_write.write_id: string`
  - `truth_write.target_ref: string` (`""` means no target)
  - `truth_write.operation: "create" | "merge" | "replace"`
  - `truth_write.payload_json: string`
  - `truth_write.remaining_open_issues: list[str]`
  - `truth_write.ready_for_review: bool`
- Runtime execution normalization:
  - inject `workspace_id` from `RpAgentTurnInput.workspace_id`
  - inject `step_id` from `context_bundle.current_step`
  - inject `truth_write.current_step` from `context_bundle.current_stage` when present, otherwise from `context_bundle.current_step`
  - inject `truth_write.block_type = "stage_draft"` and `truth_write.stage_id = context_bundle.current_stage` when the turn has a canonical current stage
  - otherwise inject `truth_write.block_type` from `SETUP_TRUTH_WRITE_BLOCK_TYPE_BY_STEP[current_step]`
  - parse `truth_write.payload_json` into provider-side `truth_write.payload`
  - inject `user_edit_delta_ids` from current context packet user-edit deltas when available, otherwise `[]`

### 4. Contracts

#### 4.1 Slim Tooling Is The Base Path, Not Provider Truth

- The provider-side `SetupTruthWriteInput` remains unchanged.
- Direct provider calls and deterministic pydantic validation still require:
  - `workspace_id`
  - `step_id`
  - `truth_write.current_step`
  - `truth_write.block_type`
  - `truth_write.operation`
- The runtime should expose a slimmer model-facing schema whenever it can deterministically rehydrate those fields before calling the provider.
- If the runtime cannot determine `workspace_id`, `current_step`, or `block_type`, it must fall back to the normal non-slim tool schema instead of sending a slim schema with incomplete runtime defaults.
- `function.strict = true` is an enhancement on this slim schema, not the condition that makes the slim schema legal.

#### 4.1.1 Canonical Stages Use The Same Hardened Truth-Write Path

- When `current_stage` is available, `setup.truth.write` is still the only model-facing draft write path.
- The runtime must inject `truth_write.block_type = "stage_draft"` and `truth_write.stage_id = current_stage`.
- Provider-side execution must validate the payload as canonical setup draft grammar and write through `SetupWorkspaceService.patch_stage_draft(...)`.
- Valid stage payloads are:
  - one `SetupDraftEntry` payload, merged into the current `SetupStageDraftBlock`
  - one full `SetupStageDraftBlock` payload whose `stage_id` matches the injected stage
- Successful stage-entry writes must return canonical refs such as `stage:world_background:race_elf`.
- Successful full-stage writes must return `draft:world_background`.
- This is intentionally not a new `setup.patch.stage_draft` tool. The design source is the existing structured-output pilot and bounded pydantic repair loop; the project-specific adaptation is to change the truth-write landing target when the turn has canonical stage context.

#### 4.2 Runtime-Owned Fields Must Not Be Model Burden

- The model must not be asked to supply fields already known by the current setup turn:
  - `workspace_id`
  - `step_id`
  - `user_edit_delta_ids`
  - `truth_write.current_step`
  - `truth_write.block_type`
- These fields are runtime-owned for the pilot because `setup.truth.write` is current-step scoped.
- This directly targets the observed real-model failure mode where the model omitted `step_id` and `truth_write.block_type`.

#### 4.3 Dynamic Payload Uses `payload_json` In The Slim Shell

- `truth_write.payload` remains a dynamic dict in provider truth because draft payload shape depends on block type.
- The model-facing slim shell must expose `truth_write.payload_json` as a string containing a JSON object.
- The model-facing slim shell must use provider-portable JSON Schema shapes. For `target_ref`, expose a string and use `""` for no target instead of `["string", "null"]`, because some OpenAI-compatible Gemini gateways reject union-type tool parameters during native schema conversion.
- The runtime must parse `payload_json` and pass the parsed object as provider-side `truth_write.payload`.
- The runtime must normalize `truth_write.target_ref == ""` back to provider-side `None`.
- Invalid `payload_json` must not be silently accepted as success. It should flow into deterministic tool failure/repair rather than being treated as a completed write.

#### 4.4 Strict Is An Optional Enhancement

- The `setup.truth.write` tool definition sent by SetupAgent runtime-v2 should prefer the slim schema whenever runtime defaults are available.
- The slim schema is the common base path for GPT/Codex, Gemini, GLM, DeepSeek, and other OpenAI-compatible models.
- The `function.strict = true` flag is gated by model-family evidence until the model registry has a first-class strict-tool support bit:
  - default enabled for GPT/Codex-family model names verified by the real-chain pilot
  - default disabled for other OpenAI-compatible families after real-chain checks showed some models ignore tool calls, fail at provider gateways, or have provider-specific strict requirements
- Other setup tools and generic MCP tools stay on the existing schema path until they receive their own slim model-facing adapter.
- The slice must include request/schema snapshot tests proving the final model request contains:
  - `rp_setup__setup.truth.write`
  - no model-facing `workspace_id`, `step_id`, `truth_write.current_step`, or `truth_write.block_type`
  - required `truth_write.payload_json`
  - `function.strict = true` only for strict-enabled models
  - no `function.strict` for non-strict-enabled models while still using the slim schema

#### 4.5 Repair Loop Still Owns Bad Paths

- Pydantic and domain validation remain the last line of defense.
- The existing one-retry repair policy remains active after strict-tool failures or payload validation failures.
- Strict tool calling is not allowed to mask invalid payload content, commit-readiness blockers, or semantic validation failures.

### 5. Validation & Error Matrix

- `current_step = foundation` and model calls slim `setup.truth.write` with `payload_json` -> runtime injects `step_id = foundation` and `truth_write.block_type = foundation_entry`
- `current_step = foundation`, `current_stage = world_background`, and model calls slim `setup.truth.write` with one stage entry `payload_json` -> runtime injects `step_id = foundation`, `truth_write.current_step = world_background`, `truth_write.block_type = stage_draft`, and `truth_write.stage_id = world_background`
- `current_step = story_config` -> runtime injects `truth_write.block_type = story_config`
- provider-side stage write with an entry payload -> writes `draft_blocks[current_stage].entries[entry_id]`, returns `stage:<stage_id>:<entry_id>`, and does not mutate `foundation_draft`
- provider-side stage write with a full block whose `stage_id` mismatches the injected stage -> fails with a machine-readable setup tool error and does not mutate the workspace
- final tool definition for `setup.truth.write` uses the slim root object whenever runtime defaults are available
- strict-enabled model family -> slim tool definition also uses `strict = true`
- non-strict-enabled model family such as `glm-5` -> runtime exposes the slim schema without `strict = true`
- final tool definition for non-pilot tools does not gain `strict = true`
- malformed `payload_json` -> the write does not succeed silently
- missing runtime `workspace_id` or unknown current step -> runtime falls back to non-slim schema/arguments rather than guessing
- direct provider call with missing `step_id` or `truth_write.block_type` still returns the existing machine-readable pydantic validation error

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert the final model request exposes slim `setup.truth.write`
  - assert strict-enabled models add `function.strict = true`
  - assert non-strict-enabled models keep the slim schema without `function.strict`
  - assert the runtime rehydrates slim truth-write arguments before tool execution
  - assert canonical stage turns rehydrate slim truth-write arguments to `stage_draft` plus injected `stage_id`
  - assert non-pilot tools stay non-strict
- `backend/rp/tests/test_setup_tool_provider_cognitive_tools.py` or provider-level tests
  - assert provider-side `SetupTruthWriteInput` validation remains unchanged for direct calls
  - assert provider-side `stage_draft` truth writes land in `draft_blocks[stage_id]` and return canonical stage refs
- `backend/rp/tests/test_setup_agent_real_model_compact_recovery.py`
  - extend the opt-in real-model chain to assert the request contains slim `setup.truth.write`
  - for strict-enabled models, assert `function.strict = true`
  - for non-strict-enabled models, assert the slim schema is still used without `function.strict`
  - keep the test skipped by default unless real-model config is explicitly provided

### 7. Wrong vs Correct

#### Wrong

- Add `strict = true` to every MCP tool at once.
- Expose a strict schema that still depends on `additionalProperties: true` dynamic payload objects.
- Remove pydantic validation because strict tools exist.
- Ask the model to fill `workspace_id`, `step_id`, and `block_type` when the runtime already knows them.
- Rewrite the tool family before the pilot proves the model/provider/LiteLLM/New API chain behaves correctly.
- Treat non-strict providers as a reason to fall back to a high-burden full provider schema when runtime-owned fields are available.

#### Correct

- Use the slim model-facing adapter on `setup.truth.write` whenever runtime-owned defaults are available.
- Keep provider truth unchanged behind that adapter.
- Use a strict-compatible shell around the dynamic payload.
- Rehydrate runtime-owned fields deterministically before provider execution.
- For canonical setup stages, reuse the same truth-write shell and change only the injected provider-side landing target to `stage_draft`.
- Add `function.strict = true` only as a verified enhancement.
- Verify with schema snapshots first, then opt-in real-model behavior, then decide whether to expand to other tools.
