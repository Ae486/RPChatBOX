# RP Setup Agent Structured Output Schema Repair

> Executable contract for SetupAgent runtime-v2 structured-output and pydantic schema repair: machine-readable validation errors, one bounded auto-repair retry, and deterministic blocking of false-success turn completion.

## Scope / Trigger

- Trigger: add or edit `backend/rp/tools/setup_tool_provider.py`, `backend/rp/agent_runtime/policies.py`, `backend/rp/agent_runtime/executor.py`, setup eval diagnostics/cases, or setup runtime tests when the change affects tool-call validation, pydantic field extraction, schema retry behavior, or repair-obligation completion blocking.
- Applies to current setup provider tools. Deleted agent tools such as `setup.truth.write`, `setup.patch.*`, `setup.question.raise`, and `setup.proposal.commit` are covered by deletion-protection tests, not positive schema-repair tests.
- This slice keeps the current bounded repair loop and does not introduce a broader semantic repair subsystem.

## Signatures

- `SetupToolProvider._validation_error_details(...) -> dict[str, Any]`
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
- `CompletionGuardPolicy.assess(...) -> dict[str, Any]`
- `ReflectionTriggerPolicy.assess(...) -> dict[str, Any]`
- `SetupPendingObligation`
  - `obligation_type = "repair_tool_call"`
  - `tool_name`
  - `required_fields: list[str]`

## Contracts

### Machine-Readable Provider Errors

When a retained setup tool input model fails pydantic validation, provider output must use:

- `error_code = "SCHEMA_VALIDATION_FAILED"`
- payload `code = "schema_validation_failed"`
- payload `details.repair_strategy = "auto_repair"`

Validation details must include enough structure for deterministic runtime repair:

- missing-field paths in `required_fields`
- raw pydantic `errors`
- flat `provided_fields`

### Missing Field Extraction

- `SetupToolProvider._required_fields_from_errors(...)` extracts only missing-field paths.
- `ToolFailureClassifier.missing_required_fields(...)` prefers `details.required_fields`.
- If `required_fields` is absent, it derives paths from `details.errors`.
- Wrapper path elements such as `body` and `arguments` are removed.
- Nested paths are preserved.
- Stable first-seen order is preserved.

### One Retry Budget

- First schema validation failure for a tool call creates a `repair_tool_call` obligation, appends `tool_schema_validation_retry`, and continues the turn.
- A second schema validation failure in the same repair chain finalizes with `tool_schema_validation_failed`.
- Plain explanatory text cannot finalize the turn while a `repair_tool_call` obligation is unresolved.

### Ask-User Branch

If a retained tool failure payload marks `details.ask_user = true` or `details.repair_strategy = "ask_user"`, runtime creates an `ask_user_for_missing_info` branch and requires a targeted user-facing question before finalizing with `awaiting_user_input`.

## Validation Matrix

- missing required field on `setup.stage_entry.write` -> provider emits `SCHEMA_VALIDATION_FAILED`, `repair_strategy = auto_repair`, and required field names such as `entry_type`, `title`, or `sections`
- missing `source_ref` on `setup.asset.register` -> same machine-readable schema error shape
- structured payload already contains `details.required_fields` -> runtime uses that list directly
- structured payload omits `required_fields` but keeps raw `errors` -> runtime derives paths from `errors`
- first schema validation failure in one turn -> warning `tool_schema_validation_retry`, `pending_obligation = repair_tool_call`, turn continues
- second schema validation failure after one repair attempt -> finalize with `tool_schema_validation_failed`
- assistant emits explanatory text while `repair_tool_call` is unresolved -> completion blocked with `repair_obligation_unresolved`
- assistant asks a targeted question after `ask_user_for_missing_info` -> finalize with `awaiting_user_input`

## Good / Base / Bad Cases

- Good: the model omits `title` on the first `setup.stage_entry.write` call, provider returns machine-readable required fields, runtime raises one repair obligation, the model retries with corrected arguments, and the turn completes normally.
- Base: the model omits a field twice, runtime allows only one correction attempt, then fails deterministically with `tool_schema_validation_failed`.
- Bad: a deleted tool is kept in a positive repair test, or the provider returns only prose and the runtime cannot recover `required_fields`.

## Tests Required

- `backend/rp/tests/test_setup_tool_provider.py`
  - assert schema validation payload contains `repair_strategy = auto_repair`
  - assert `required_fields` includes the missing path
  - assert `provided_fields` reflects what the model actually supplied
  - assert removed tools return `UNKNOWN_TOOL`
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
  - assert `missing_required_fields(...)` can derive nested paths from raw `errors`
  - assert second schema retry attempt finalizes with `tool_schema_validation_failed`
  - assert `ask_user` schema branch maps to `ask_user_for_missing_info`
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert one schema retry may succeed on retained tools
  - assert unresolved repair obligation blocks false-success finalize

## Wrong vs Correct

Wrong:

- Use deleted `setup.truth.write` or `setup.patch.*` tools as current repair examples.
- Allow unlimited schema repair retries.
- Let a turn finish successfully with explanation text while the required corrected tool call never happened.

Correct:

- Keep validation failures machine-readable and path-aware for retained tools.
- Permit one bounded auto-repair retry, then fail deterministically.
- Treat deleted tool names as negative deletion-protection only.
