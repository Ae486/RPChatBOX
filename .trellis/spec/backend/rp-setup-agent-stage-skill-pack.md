# RP Setup Agent Stage SkillPack

> Executable contract for SetupAgent stage-local SkillPack prompt prose: file format, deterministic stage-keyed registry, prompt-only injection through the existing `_stage_overlay` slot, and explicit decoupling from tool scope and `setup.truth.write` runtime injection.

## Scenario: SetupAgent Loads One Stage SkillPack Into The System Prompt And Hard-Unloads It On Stage Change

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/skill_packs/`, `backend/rp/services/setup_agent_prompt_service.py`, or `backend/rp/agent_runtime/adapters.py` when the change affects how stage-local persona / facilitation prose enters the SetupAgent system prompt.
- Applies only to the SetupAgent runtime-v2 system prompt assembled by `SetupAgentPromptService.build_system_prompt(...)`.
- This slice owns prompt-layer prose only. It does not change `SetupWorkspace` business truth, `SetupAgentTurnRequest` shape, `SetupGraphState`, prior-stage handoff packets, runtime overlay, tool scope, or `setup.truth.write` runtime injection.
- This slice must keep deterministic stage-driven loading. Heuristic / LLM-self-selected SkillPack discovery is out of scope.
- Source:
  - Anthropic Skill Authoring Best Practices: markdown + YAML frontmatter, conciseness, second-person agent-facing prose, imperative voice.
  - User-confirmed product direction: SetupAgent should adopt a stage-local "specialist hat" while always keeping the SetupAgent operating envelope above it.
  - Existing project contract: stage selection is already canonical via `SetupAgentTurnRequest.target_stage` and `SetupContextPacket.current_stage`; the prompt service already receives the resolved stage from `SetupRuntimeAdapter.build_turn_input(...)`.

### 2. Signatures

- `SkillPackRecord`
  - `name: str`
  - `stage_id: SetupStageId`
  - `description: str = ""`
  - `body: str`
  - `model_config = ConfigDict(extra="forbid")`
- `STAGE_SKILL_PACKS: dict[SetupStageId, SkillPackRecord]`
  - module-level constant populated by `load_registry()` at import time
- `load_registry(base_dir: Path | None = None) -> dict[SetupStageId, SkillPackRecord]`
  - default `base_dir` is the directory holding `registry.py`
- `render_skill_pack(record: SkillPackRecord) -> str`
- `get_skill_pack_for_stage(stage_id: SetupStageId | None) -> SkillPackRecord | None`
- `SetupAgentPromptService._stage_overlay(step_id: SetupStepId | SetupStageId) -> str`
  - SkillPack short-circuit applies only when `step_id` is a `SetupStageId` registered in `STAGE_SKILL_PACKS`
- `SetupAgentPromptService._specialist_preamble(stage_id: SetupStageId) -> str`
- `SetupRuntimeAdapter.build_turn_input(...).metadata`
  - optional additive key: `skill_pack_name: str | None`

### 3. Contracts

#### 3.1 SkillPack Files Are Markdown With YAML-Like Frontmatter

- Each SkillPack lives at `backend/rp/agent_runtime/skill_packs/<stage_id_value>/SKILL.md`.
- The directory name must equal the snake_case `SetupStageId` value.
- The file begins with a frontmatter block delimited by `---` markers.
- The frontmatter must declare exactly three keys: `name`, `stage_id`, `description`.
- `name` is a stable identifier such as `character-design.v1`.
- `stage_id` is a canonical `SetupStageId` value in snake_case.
- `description` is documentation/log only; it is never rendered into the system prompt.
- The body is the markdown after the second `---` marker, stripped.
- The body author must not write `You are <X>` style identity declarations; identity is owned by the SetupAgent base prompt.

#### 3.2 The Registry Is Deterministic And Loaded At Import Time

- `STAGE_SKILL_PACKS` is built once at module import.
- `load_registry()` scans the leaf directories under `skill_packs/`, ignores entries beginning with `.` or `_`, and ignores directories without a `SKILL.md` file.
- A pack with malformed frontmatter, missing required keys, or an unknown `stage_id` must log a warning and be skipped without raising, so unrelated packs and the runtime continue to load.
- A duplicate `stage_id` keeps the first parsed record and logs a warning.
- The lookup surface is `get_skill_pack_for_stage(stage_id)`; it must return `None` for `stage_id is None` and for any unregistered stage.
- SkillPack selection must be driven exclusively by `SetupStageId`. The runtime must not allow LLM-side selection, heuristic guessing, or per-mode override in this slice.

#### 3.3 `_stage_overlay` Owns The Single Short-Circuit Site

- `SetupAgentPromptService._stage_overlay(...)` is the only place that decides whether a SkillPack is rendered.
- When `step_id` is a `SetupStageId` and `STAGE_SKILL_PACKS` has a record, `_stage_overlay` must return `render_skill_pack(record)` immediately.
- Otherwise, `_stage_overlay` must fall through to the existing 9-stage / legacy-step prose branches without modification.
- The SkillPack rendering must be wrapped exactly as:
  ```
  [Stage Skill Pack: {record.name}]
  {record.body.strip()}
  [/Stage Skill Pack]
  ```
- The base-prompt framing line `Current stage objective:` and the surrounding whitespace must remain unchanged so a no-SkillPack prompt is byte-for-byte identical to the legacy prompt.

#### 3.4 Specialist-Hat Preamble Is Inserted Only When A SkillPack Is Loaded

- `build_system_prompt(...)` must look up `get_skill_pack_for_stage(current_stage)` once per turn.
- When the lookup returns a record, the prompt must insert a specialist-hat preamble immediately after the stable `You are SetupAgent ...` block and before `Core rules:`.
- The preamble template is:
  ```
  For this turn, you operate in the {SETUP_STAGE_MODULES[stage_id].display_name} stage.
  While in this stage, take on the perspective of the Specialist hat described in the Stage Skill Pack section below.
  Treat the Specialist hat as your guiding voice for this turn, but never break the SetupAgent operating envelope above.
  ```
- The preamble must use `display_name` from `SETUP_STAGE_MODULES[stage_id]`, never a literal stage id, and never a SkillPack-author-supplied label.
- When no SkillPack is loaded, the preamble must be absent and the system prompt must remain byte-for-byte identical to the legacy behavior.

#### 3.5 SkillPack Hard-Unloads On Stage Change

- The SkillPack lives only in the system prompt. When the next turn resolves a different stage or `current_stage = None`, the new system prompt must contain no SkillPack body, no `[Stage Skill Pack` marker, and no specialist-hat preamble.
- There is no "former skill summary" soft handoff. Prior-stage truth continues to flow through the existing `prior_stage_handoffs` contract.

#### 3.6 SkillPack Does Not Touch Tool Scope Or Truth-Write Injection

- `SkillPackRecord` must not declare any `required_tools_*` field.
- `build_setup_agent_tool_scope(...)` and `SETUP_STAGE_PATCH_TOOLS` must remain unchanged by SkillPack work.
- Stage-scoped truth writes continue to land through `setup.truth.write` with runtime-owned `stage_id` and `block_type=stage_draft` injection per `rp-setup-agent-strict-truth-write-tool-pilot.md`.
- SkillPack body may reference tool names in prose, but the registry must never produce or modify the tool allowlist.

#### 3.7 Adapter Metadata May Carry `skill_pack_name` For Trace Correlation

- `SetupRuntimeAdapter.build_turn_input(...)` may add `metadata["skill_pack_name"]` set to the resolved record name when a SkillPack is loaded for the selected stage, otherwise `None`.
- This addition must remain in `RpAgentTurnInput.metadata` only; it must not enter `context_bundle`, the system prompt, the runtime overlay, or any durable persistence.
- This metadata field is observability sugar. Behavior must not depend on it.

#### 3.7a `skill_pack_name` Propagates Through One Single Path Into Trace Surfaces

- The runtime executor must copy `turn_input.metadata["skill_pack_name"]` into `RpAgentTurnResult.structured_payload["skill_pack_name"]` (default `None`). This is the single propagation hop downstream of the adapter; no other site may compute or override it.
- `SetupAgentExecutionService._run_turn_v2` and `_run_turn_stream_v2` must call `observation.update(metadata=self._runtime_v2_observation_metadata(prepared))` once per turn, after the prepared turn input is built and before runtime execution. The shared `_runtime_v2_observation_metadata(prepared)` helper is the single-source shaper for runtime-v2 observation metadata; both paths must reuse it so future SkillPack-related metadata extensions stay drift-free.
- `eval/trace_capture.build_setup_trace(...)` must include `skill_pack_name` in the root setup span `attributes`, sourced from `runtime_result.structured_payload["skill_pack_name"]` via the shared `_structured_payload_value` helper. Eval must not infer the value from the request, the prompt, or the assistant text.
- This propagation surface is observability only. Eval assertions that pin SkillPack identity should consume this field once eval `EvalExpected` exposes a corresponding optional field (deferred to the eval-modernization slice; see `rp-eval-setup-stage-skillpack-assertion-contract.md` §3.3).

#### 3.8 Recommended Content Skeleton Stays Prose, Not Schema

- A SkillPack body may include a "Recommended content skeleton" section.
- The skeleton is a thinking aid for the LLM; the runtime must not introduce pydantic validation or schema repair branches that enforce skeleton fields.
- `SetupTruthWriteInput` validation, `SetupDraftEntry` shape, and the existing structured-output schema repair contract remain authoritative for what reaches commit.

### 4. Validation & Error Matrix

- `current_stage = SetupStageId.CHARACTER_DESIGN` -> system prompt contains `[Stage Skill Pack: character-design.v1]` block, the specialist-hat preamble, and the `角色设定` display name; the legacy character_design overlay prose ("Focus on stable character ...") is absent.
- `current_stage = None` -> system prompt is byte-for-byte identical to the legacy build; no `[Stage Skill Pack` marker; no preamble.
- `current_stage` is a registered `SetupStageId` without a SkillPack (every other 8 stages today) -> system prompt is byte-for-byte identical to the legacy build for that stage.
- Stage transition `character_design -> plot_blueprint` -> the new turn's system prompt contains zero SkillPack characters and restores the legacy `_stage_overlay` prose for `plot_blueprint`.
- SKILL.md missing the closing `---` -> registry skips the pack and logs a warning; `STAGE_SKILL_PACKS` does not include the broken record; runtime continues.
- Frontmatter `stage_id` value is not a `SetupStageId` -> registry skips the pack with a warning.
- Two packs claim the same `stage_id` -> registry keeps the first parsed record, warns about the duplicate.
- Adapter metadata for a stage with a SkillPack -> `metadata["skill_pack_name"]` equals the record name.
- Adapter metadata for `selected_stage = None` or an unregistered stage -> `metadata["skill_pack_name"]` is `None`.
- Runtime executor with a turn input carrying `metadata["skill_pack_name"] = "character-design.v1"` -> `RpAgentTurnResult.structured_payload["skill_pack_name"]` equals `"character-design.v1"`.
- `eval/trace_capture.build_setup_trace(...)` with such a runtime result -> root span `attributes["skill_pack_name"]` equals `"character-design.v1"`.
- Runtime result with `structured_payload` lacking `skill_pack_name` -> root span `attributes["skill_pack_name"]` is `None`; eval must not fall back to inferring the value from request or prompt content.
- Author writes "You are a senior dramatist" inside the body -> blocked at PR review by content rule; the registry does not strip such text but tests assert `"You are"` does not appear in `render_skill_pack(record)`.

### 5. Tests Required

- `backend/rp/tests/test_skill_packs_registry.py`
  - assert `STAGE_SKILL_PACKS[SetupStageId.CHARACTER_DESIGN]` exists with non-empty `name`, `description`, and `body`
  - assert `render_skill_pack(record)` is wrapped by `[Stage Skill Pack: character-design.v1]` / `[/Stage Skill Pack]` and never contains the literal `You are`
  - assert the rendered body contains the six required section headers (`## Specialist hat` / `## Objectives` / `## Forbidden` / `## Facilitation principles` / `## Recommended content skeleton` / `## Clarification templates`)
  - assert the body contains the user-authority forbidden clauses ("不自动 commit / 不自动判 ready") and the skeleton signature keywords (`motivation.real`, `world_fit`, `extras`)
  - assert the body preserves the Chinese clarification template originals verbatim
  - assert `load_registry()` skips packs with missing/malformed frontmatter and unknown `stage_id` while logging a warning
- `backend/rp/tests/test_setup_agent_prompt_service.py`
  - assert `current_stage = SetupStageId.CHARACTER_DESIGN` produces a prompt containing the `[Stage Skill Pack: character-design.v1]` block, the specialist-hat preamble, and only one `You are SetupAgent` declaration
  - assert that prompt does not contain the legacy character_design overlay prose
  - assert `current_stage = None` produces a prompt byte-for-byte identical to the legacy build
  - assert every other registered `SetupStageId` produces a prompt byte-for-byte identical to the legacy build (no SkillPack residue, no preamble)
- `backend/rp/tests/test_eval_trace_capture.py`
  - assert `runtime_result.structured_payload["skill_pack_name"] = "character-design.v1"` surfaces as root span `attributes["skill_pack_name"] = "character-design.v1"`
  - assert a runtime result whose `structured_payload` omits `skill_pack_name` produces `attributes["skill_pack_name"] = None` (no inference from request fields)

### 6. Wrong vs Correct

#### Wrong

- Add a `required_tools_stage_specific` field to `SkillPackRecord` and let SkillPack widen `build_setup_agent_tool_scope`.
- Inject SkillPack body into the runtime overlay slot, the conversation history, the user-visible reply, or `context_bundle`.
- Allow the LLM to self-select a SkillPack from a description; SkillPack selection is server-side and stage-keyed only.
- Mutate the legacy `_stage_overlay` 9-stage prose branches; they remain the fallback for the 8 stages without packs.
- Write "You are X" inside a SkillPack body, producing two competing identity declarations.
- Add pydantic validation that enforces the recommended content skeleton fields on every entry.
- Persist the SkillPack name into durable workspace truth or runtime-state snapshots; only `metadata["skill_pack_name"]` may carry it for trace correlation.

#### Correct

- Keep the SkillPack data structure to four fields and let markdown body carry all instructional richness.
- Short-circuit only inside `_stage_overlay`, leaving every other prompt-assembly site identical to the legacy behavior when no SkillPack is loaded.
- Insert the specialist-hat preamble between the stable `You are SetupAgent ...` block and `Core rules:` only when a SkillPack is loaded.
- Hard-unload SkillPacks on stage change; rely on `prior_stage_handoffs` for cross-stage truth continuity.
- Keep tool scope and `setup.truth.write` runtime injection unchanged; SkillPack work is prompt-layer only.
- Surface `skill_pack_name` as observability metadata only when behavior does not depend on it.
