# RP Setup Agent Structured Output Schema Repair

> Executable contract for SetupAgent runtime-v2 structured-output and pydantic schema repair: machine-readable validation errors, one bounded auto-repair retry, and deterministic blocking of false-success turn completion.

## Scenario: SetupAgent Repairs Missing Draft Tool Fields Once, Then Fails Deterministically

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/tools/setup_tool_provider.py`, `backend/rp/agent_runtime/policies.py`, `backend/rp/agent_runtime/executor.py`, setup eval diagnostics/cases, or setup runtime tests when the change affects structured tool-call validation, pydantic field extraction, schema retry behavior, or repair-obligation completion blocking.
- Applies only to setup/prestory runtime-v2 tool-call schema validation and the immediate repair loop after validation failure.
- This slice is intentionally narrow:
  - focus on real observed bad path: draft/write/patch tool calls with missing fields
  - keep the current bounded repair loop
  - do not introduce a broader repair subsystem, semantic stall detector, or tool-metadata framework
- This slice must preserve the current multi-layer contract:
  - upstream tool schema is exposed as structured tool definition
  - provider-side pydantic validation produces machine-readable failure payloads
  - runtime derives `required_fields` from those payloads
  - runtime permits one bounded correction attempt
  - unresolved repair must not finalize as ordinary text success

### 2. Signatures

- `SetupToolProvider._validation_error_details(...) -> dict[str, Any]`
  - required output fields:
    - `tool_name`
    - `failure_origin = "validation"`
    - `repair_strategy = "auto_repair"`
    - `required_fields: list[str]`
    - `errors: list[dict[str, Any]]`
    - `provided_fields: list[str]`
- `SetupToolProvider._required_fields_from_errors(...) -> list[str]`
- `ToolFailureClassifier.error_payload(...) -> dict[str, Any]`
- `ToolFailureClassifier.missing_required_fields(...) -> list[str]`
- `RepairDecisionPolicy.assess(...) -> dict[str, Any]`
  - schema-repair relevant outputs:
    - `schema_retry_count`
    - `pending_obligation`
    - `last_failure`
    - `warnings`
    - `finish_reason`
- `CompletionGuardPolicy.assess(...) -> dict[str, Any]`
- `ReflectionTriggerPolicy.assess(...) -> dict[str, Any]`
- `SetupPendingObligation`
  - `obligation_type = "repair_tool_call"`
  - `tool_name`
  - `required_fields: list[str]`

### 3. Contracts

#### 3.1 Pydantic Validation Failure Must Stay Machine-Readable

- When a setup tool input model fails pydantic validation, provider output must use:
  - `error_code = "SCHEMA_VALIDATION_FAILED"`
  - payload `code = "schema_validation_failed"`
  - payload `details.repair_strategy = "auto_repair"`
- Validation details must carry enough structure for deterministic runtime repair:
  - missing-field paths in `required_fields`
  - raw pydantic `errors`
  - flat `provided_fields`
- The provider must not collapse schema validation into free-form prose only.

#### 3.2 Missing Fields Must Derive From Deterministic Paths

- `SetupToolProvider._required_fields_from_errors(...)` must extract only missing-field paths from pydantic errors.
- `ToolFailureClassifier.missing_required_fields(...)` must prefer `details.required_fields` when present.
- If `required_fields` is absent, it must derive the paths from `details.errors`.
- Field extraction rules:
  - remove wrapper path elements such as `body` and `arguments`
  - keep nested paths such as `patch.style_rules` or `truth_write.payload.content`
  - preserve stable order of first appearance
  - do not include non-missing validation errors

#### 3.3 Auto-Repair Budget For Schema Failure Is Exactly One Retry

- First schema validation failure for a tool call:
  - classify as `auto_repair` unless the payload explicitly says `ask_user`
  - set `pending_obligation.obligation_type = "repair_tool_call"`
  - copy `required_fields` into the obligation
  - append warning `tool_schema_validation_retry`
  - continue the turn
- Second schema validation failure in the same repair chain:
  - do not permit a second normal retry loop
  - finalize with `finish_reason = "tool_schema_validation_failed"`
- This slice freezes the retry budget at `1` correction attempt.

#### 3.4 False Success Must Stay Blocked Until A Corrected Tool Call Happens

- While `pending_obligation.obligation_type == "repair_tool_call"` remains unresolved:
  - plain explanatory text must not finalize the turn
  - `CompletionGuardPolicy` must return `allow_finalize = False`
  - the runtime must route through reflection/retry handling
- If the assistant still fails to issue a corrected tool call after the allowed repair opportunity:
  - `ReflectionTriggerPolicy` must finalize with `finish_reason = "repair_obligation_unfulfilled"`
- This keeps "I know what is wrong" from being treated as success when the required tool mutation never happened.

#### 3.5 Ask-User Remains A Separate Structured Branch

- `SCHEMA_VALIDATION_FAILED` does not always mean auto-repair.
- If the tool failure payload explicitly marks:
  - `details.ask_user = true`, or
  - `details.repair_strategy = "ask_user"`
  then the runtime must:
  - create `ask_user_for_missing_info`
  - require a targeted user-facing question before finalize
- This branch is part of the same structured-output contract, not a separate ad hoc behavior.

### 4. Validation & Error Matrix

- pydantic missing field on `setup.patch.story_config` with only `workspace_id` provided -> provider emits `SCHEMA_VALIDATION_FAILED`, `repair_strategy = auto_repair`, `required_fields` includes `patch`, and `provided_fields` includes `workspace_id`
- structured payload already contains `details.required_fields` -> runtime uses that list directly
- structured payload omits `required_fields` but keeps raw `errors` -> runtime derives nested field paths from `errors`
- first schema validation failure in one turn -> warning `tool_schema_validation_retry`, `pending_obligation = repair_tool_call`, turn continues
- second schema validation failure after one repair attempt -> finalize with `tool_schema_validation_failed`
- assistant emits explanatory text while `repair_tool_call` is unresolved -> completion blocked with `repair_obligation_unresolved`
- assistant asks a targeted question after `ask_user_for_missing_info` -> finalize with `awaiting_user_input`

### 5. Good / Base / Bad Cases

- Good: the model omits `patch` on the first `setup.patch.story_config` call, the provider returns machine-readable required fields, the runtime raises one repair obligation, the model retries with corrected arguments, and the turn completes normally.
- Base: the model omits a field twice, the runtime allows only one correction attempt, then fails deterministically with `tool_schema_validation_failed`.
- Bad: the provider returns only prose, the runtime cannot recover `required_fields`, or the assistant explains the failure in text and the turn still finalizes as normal success.

### 6. Tests Required

- `backend/rp/tests/test_setup_tool_provider.py`
  - assert schema validation payload contains `repair_strategy = auto_repair`
  - assert `required_fields` includes the missing path
  - assert `provided_fields` reflects what the model actually supplied
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
  - assert `missing_required_fields(...)` can derive nested field paths from raw `errors` when `required_fields` is absent
  - assert second schema retry attempt finalizes with `tool_schema_validation_failed`
  - assert `ask_user` schema branch still maps to `ask_user_for_missing_info`
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert one schema retry may succeed
  - assert unresolved repair obligation blocks false-success finalize

### 7. Wrong vs Correct

#### Wrong

- Treat pydantic validation failures as opaque prose and hope the model guesses the right fix.
- Allow unlimited schema repair retries.
- Drop nested missing-field paths such as `patch.style_rules`.
- Let a turn finish successfully with explanation text while the required corrected tool call never happened.

#### Correct

- Keep validation failures machine-readable and path-aware.
- Permit one bounded auto-repair retry, then fail deterministically.
- Carry `required_fields` and `provided_fields` through the repair surface.
- Block false-success completion until the corrected tool call actually happens or the runtime terminates with the appropriate failure reason.
