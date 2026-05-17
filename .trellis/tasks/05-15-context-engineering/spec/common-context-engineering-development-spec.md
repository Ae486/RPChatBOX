# Common Context Engineering Development Spec

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Implements: `Common Context Engineering Kernel + Setup Adapter Pilot`
>
> Status: development-spec-v1
>
> Source spec:
> `.trellis/tasks/05-15-context-engineering/spec/common-context-engineering-kernel-setup-adapter-spec.md`

## 1. Development Goal

Build a common, runtime-agnostic Context Engineering kernel and prove it through
the current SetupAgent workload.

This development spec turns the architectural spec into executable engineering
instructions: files, public APIs, implementation order, tests, migration
guards, and review gates.

SetupAgent is still only the proving ground. The common kernel must not encode
setup stages, draft refs, setup tool names, setup cognition, setup readiness,
or `SetupWorkspace` truth as common concepts.

## 2. Work Boundaries

### 2.1 In Scope

- Add `backend/rp/context_engineering/` as a new common package.
- Implement common contracts, deterministic selection, token estimation,
  fingerprinting, validation, fallback, trace/read-manifest, compact operation,
  and overflow signal modeling.
- Add `backend/rp/context_engineering/adapters/setup.py` as the first adapter.
- Keep existing SetupAgent public behavior compatible while allowing internal
  setup context governance to call the common kernel.
- Add focused tests for common mechanics, setup adapter behavior, and setup
  regression boundaries.

### 2.2 Out Of Scope

- Story Runtime adapter wiring.
- Provider-specific tokenizer dependency.
- Provider-managed conversation state.
- Provider overflow retry integration.
- New setup runtime persistence table.
- Any compact output that writes setup draft, Core, Recall, Archival, accepted
  story truth, or Memory OS truth.
- Broad rewrite of `WritingPacketBuilder`, `ContextOrchestrationService`, or
  setup product semantics.

## 3. Required Package Layout

Create:

```text
backend/rp/context_engineering/
  __init__.py
  contracts.py
  policies.py
  estimation.py
  selection.py
  fingerprinting.py
  validation.py
  compaction.py
  serialization.py
  tracing.py
  overflow.py
  adapters/
    __init__.py
    setup.py
```

Add tests:

```text
backend/rp/tests/test_context_engineering_contracts.py
backend/rp/tests/test_context_engineering_estimation.py
backend/rp/tests/test_context_engineering_selection.py
backend/rp/tests/test_context_engineering_fingerprinting.py
backend/rp/tests/test_context_engineering_validation.py
backend/rp/tests/test_context_engineering_compaction.py
backend/rp/tests/test_context_engineering_overflow.py
backend/rp/tests/test_context_engineering_setup_adapter.py
```

Existing setup tests must continue to pass where relevant:

```text
backend/rp/tests/test_setup_context_governor.py
backend/rp/tests/test_setup_agent_execution_service_v2.py
backend/rp/tests/test_setup_agent_prompt_service.py
backend/rp/tests/test_setup_agent_runtime_executor.py
backend/rp/tests/test_setup_agent_runtime_state_service.py
```

## 4. Dependency Rules

Allowed:

```text
setup services -> context_engineering.adapters.setup -> context_engineering kernel
future story services -> future story adapters -> context_engineering kernel
context_engineering kernel -> pydantic / stdlib only
```

Forbidden inside `backend/rp/context_engineering/` except under
`adapters/setup.py`:

- `SetupWorkspace`
- setup stage/step model imports
- setup draft model imports
- setup tool provider imports
- Story Runtime Core mutation services
- Memory OS writer services
- UI/SSE contracts

The common kernel can carry opaque strings such as `source_scope`,
`source_ref`, and `recovery_refs`, but it must not interpret setup-specific or
story-specific semantics.

## 5. Contract Implementation Details

Use Pydantic v2 style:

```python
from pydantic import BaseModel, ConfigDict, Field

class SomeContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Contracts that intentionally allow arbitrary adapter metadata may use:

```python
metadata: dict[str, Any] = Field(default_factory=dict)
payload: dict[str, Any] = Field(default_factory=dict)
```

Do not use mutable default literals.

### 5.1 `contracts.py`

Define all common literals and models in one file first. Later refactors can
split the file only after tests stabilize.

Required literals:

```python
ContextSourceFamily = Literal[
    "system_instruction",
    "developer_instruction",
    "user_turn",
    "assistant_turn",
    "tool_outcome",
    "workspace_truth",
    "runtime_state",
    "retrieval_card",
    "sidecar",
    "compact_artifact",
    "debug_trace",
]

ContextVisibility = Literal[
    "model_visible",
    "metadata_only",
    "hidden",
    "forbidden",
]

ContextStability = Literal[
    "stable_prefix",
    "semi_stable",
    "volatile",
    "ephemeral",
]

ContextSerializationFamily = Literal[
    "system_section",
    "runtime_overlay",
    "conversation_message",
    "tool_observation",
    "compact_section",
    "retrieval_section",
    "metadata",
]

ContextOperationKind = Literal[
    "packet_build",
    "trim",
    "compact",
    "summarize",
    "trace_only",
]

ContextOperationStatus = Literal[
    "not_needed",
    "selected",
    "reused",
    "updated",
    "rebuilt",
    "fallback",
    "failed",
]
```

Required models:

- `ContextSourceItem`
- `ContextBudgetPolicy`
- `ContextPlacementPolicy`
- `ContextValidationPolicy`
- `ContextFallbackPolicy`
- `ContextProviderProfile`
- `ContextOverflowSignal`
- `ContextValidationIssue`
- `ContextValidationReport`
- `ContextFallbackReport`
- `ContextSection`
- `ContextSelectionResult`
- `ContextArtifact`
- `ContextManifestItem`
- `ContextReadManifest`
- `ContextBudgetDecision`
- `ContextTrace`
- `ContextOperationRequest`
- `ContextOperationResult`
- `ContextCompactPromptRequest`

#### `ContextSourceItem`

Required fields:

```python
source_item_id: str
source_family: ContextSourceFamily
source_scope: str | None = None
sequence_index: int | None = None
atomic_group_id: str | None = None
must_keep_with: list[str] = Field(default_factory=list)
visibility: ContextVisibility = "model_visible"
stability: ContextStability = "volatile"
serialization_family: ContextSerializationFamily
source_ref: str | None = None
recovery_refs: list[str] = Field(default_factory=list)
text: str | None = None
payload: dict[str, Any] = Field(default_factory=dict)
estimated_tokens: int | None = None
created_at: datetime | None = None
metadata: dict[str, Any] = Field(default_factory=dict)
```

Rules:

- `source_item_id` must be non-empty after stripping.
- `sequence_index` is optional, but if present it is the primary ordering field.
- `created_at` is a fallback ordering field only.
- `atomic_group_id` links peer items.
- `must_keep_with` lists explicit peer `source_item_id` values.
- Empty `text` is allowed if `payload` carries structured content.

#### `ContextManifestItem`

Required fields:

```python
source_item_id: str
source_family: ContextSourceFamily
source_scope: str | None = None
source_ref: str | None = None
visibility: ContextVisibility
decision: Literal["selected", "omitted", "hidden", "forbidden", "metadata_only"]
reason: str
slot: str | None = None
estimated_tokens: int | None = None
atomic_group_id: str | None = None
metadata: dict[str, Any] = Field(default_factory=dict)
```

`ContextReadManifest` groups:

```python
selected: list[ContextManifestItem]
omitted: list[ContextManifestItem]
hidden: list[ContextManifestItem]
forbidden: list[ContextManifestItem]
metadata_only: list[ContextManifestItem]
```

The manifest is evidence of what the model could see. It must not include raw
hidden content.

#### `ContextTrace`

Required fields:

```python
operation_id: str
operation_kind: ContextOperationKind
runtime_family: str
estimate_method: str
input_source_count: int
selected_source_count: int
omitted_source_count: int
hidden_source_count: int
forbidden_source_count: int
metadata_only_source_count: int
estimated_input_tokens: int
selected_tokens: int
budget_decisions: list[ContextBudgetDecision] = Field(default_factory=list)
source_counts_by_family: dict[str, int] = Field(default_factory=dict)
selected_counts_by_family: dict[str, int] = Field(default_factory=dict)
summary_action: str | None = None
fallback_reason: str | None = None
cache_stability_notes: list[str] = Field(default_factory=list)
provider_usage: dict[str, Any] = Field(default_factory=dict)
metadata: dict[str, Any] = Field(default_factory=dict)
```

Trace is transient debug/eval data. Setup migration must not persist it into
durable setup cognition snapshots.

#### `ContextArtifact`

`ContextArtifact.payload` may contain setup-specific schema data only when the
artifact is produced by the setup adapter. The common kernel treats payload as
opaque after validation.

`previous_artifact` is operation state. It must never be copied into
`ContextOperationRequest.source_items` for the same compact operation.

#### `ContextSelectionResult`

Required fields:

```python
selected_items: list[ContextSourceItem] = Field(default_factory=list)
recent_raw_items: list[ContextSourceItem] = Field(default_factory=list)
compactable_dropped_items: list[ContextSourceItem] = Field(default_factory=list)
sections: list[ContextSection] = Field(default_factory=list)
read_manifest: ContextReadManifest
trace: ContextTrace
```

Rules:

- `selected_items` are model-visible source items that survived selection.
- `recent_raw_items` are selected raw conversation items protected by recent
  window policy.
- `compactable_dropped_items` is the only normal handoff from selection to
  compaction. It may contain only model-visible raw conversation items omitted
  because they are older than the recent window or replaced by compact artifact
  policy.
- `compactable_dropped_items` must not include `runtime_state`, tool outcomes,
  hidden items, forbidden items, metadata-only items, sidecars, or previous
  compact artifacts.
- Setup migration must fingerprint only `compactable_dropped_items`, preserving
  the existing setup rule that compact source equals the full dropped-history
  prefix.

### 5.2 `policies.py`

Implement small policy builders and constants, not business logic.

Required constants:

```python
DEFAULT_CONTEXT_ESTIMATE_CHARS_PER_TOKEN = 4
DEFAULT_FALLBACK_SUMMARY_LINE_LIMIT = 6
DEFAULT_SECTION_TITLE = "Context"
```

Required helpers:

```python
def default_budget_policy(...) -> ContextBudgetPolicy: ...
def default_placement_policy(...) -> ContextPlacementPolicy: ...
def default_validation_policy(...) -> ContextValidationPolicy: ...
def default_fallback_policy(...) -> ContextFallbackPolicy: ...
```

These helpers must not know setup or story semantics.

## 6. Deterministic Kernel APIs

### 6.1 `estimation.py`

Required API:

```python
def estimate_text_tokens(text: str | None, *, chars_per_token: int = 4) -> int: ...
def estimate_payload_tokens(payload: Mapping[str, Any], *, chars_per_token: int = 4) -> int: ...
def estimate_source_item_tokens(item: ContextSourceItem) -> int: ...
def estimate_source_items_tokens(items: Sequence[ContextSourceItem]) -> int: ...
```

Rules:

- `estimated_tokens` on `ContextSourceItem` wins if it is not `None`.
- Negative estimates are invalid and should be treated as `0` only after a
  validation issue is recorded by the caller.
- Payload JSON must be serialized with sorted keys for deterministic estimates.
- The estimator is approximate. It must label trace `estimate_method` as
  `approx_chars_div_4` unless adapter provides another method in metadata.

### 6.2 `fingerprinting.py`

Required API:

```python
def canonical_source_item_payload(item: ContextSourceItem) -> dict[str, Any]: ...
def fingerprint_source_items(items: Sequence[ContextSourceItem]) -> str: ...
def is_valid_prefix_artifact(
    *,
    previous_artifact: ContextArtifact,
    dropped_items: Sequence[ContextSourceItem],
) -> bool: ...
```

Fingerprint input must include:

- `source_item_id`
- `source_family`
- `source_scope`
- `sequence_index`
- `source_ref`
- normalized text
- canonical payload JSON
- recovery refs

Fingerprint input must not include:

- estimated token counts
- trace metadata
- created timestamp
- previous compact artifact payload

### 6.3 `selection.py`

Required API:

```python
def select_context_sections(
    request: ContextOperationRequest,
) -> ContextSelectionResult: ...
```

Selection algorithm:

1. Normalize estimates for all source items.
2. Split items by visibility:
   - `forbidden` -> manifest only;
   - `hidden` -> manifest only;
   - `metadata_only` -> manifest only;
   - `model_visible` -> candidate list.
3. Sort candidates by:
   - placement slot order;
   - `source_scope`;
   - `sequence_index`;
   - `created_at`;
   - `source_item_id`.
4. Resolve atomic groups:
   - collect all items with the same `atomic_group_id`;
   - include any `must_keep_with` peers;
   - if one item in a non-breakable group is omitted by budget, omit the whole
     group with `atomic_group_omitted`;
   - if policy explicitly breaks the group, record `atomic_group_broken_by_policy`.
5. Apply family item caps.
6. Apply family token caps.
7. Preserve recent raw window by item count or token cap for conversation items.
8. Apply operation token budget.
9. Build provider-neutral `ContextSection` objects in slot order.
10. Build `selected_items`, `recent_raw_items`, `compactable_dropped_items`,
    read manifest, and trace as one `ContextSelectionResult`.

Recent raw policy:

- Conversation items are `user_turn`, `assistant_turn`, and future tool-call
  message items if added.
- Recent window selection uses highest `sequence_index` first within scope.
- Recent items are protected from older-item omission where possible.
- Recent protection does not override `forbidden` or `hidden`.
- Only omitted raw conversation items can enter `compactable_dropped_items`.
  Adapter code must not reconstruct compact inputs by scanning all omitted
  manifest entries.

### 6.4 `serialization.py`

Required API:

```python
def serialize_source_item_content(item: ContextSourceItem) -> str: ...
def build_section_for_items(
    *,
    section_id: str,
    slot: str,
    title: str,
    items: Sequence[ContextSourceItem],
    stability: ContextStability,
) -> ContextSection: ...
```

Rules:

- Prefer `text` when present.
- If only `payload` exists, serialize sorted JSON.
- Do not serialize hidden, forbidden, or metadata-only payloads into sections.
- Section content must be deterministic.

### 6.5 `validation.py`

Required API:

```python
def validate_payload_against_policy(
    *,
    payload: Mapping[str, Any],
    policy: ContextValidationPolicy,
) -> ContextValidationReport: ...

def filter_allowed_recovery_refs(
    *,
    refs: Sequence[str],
    policy: ContextValidationPolicy,
) -> tuple[list[str], list[ContextValidationIssue]]: ...
```

Validation rules:

- Reject unknown fields when `reject_unknown_fields=True` and the policy
  defines allowed fields through `metadata["allowed_payload_fields"]`.
- Reject any field in `forbidden_payload_fields`.
- Enforce `max_list_lengths`.
- Enforce `max_string_lengths`.
- Reject recovery refs outside `allowed_recovery_ref_prefixes`.
- Reject `source_ref` values outside `allowed_source_refs` when the list is
  non-empty.

Validation must return reports; compact operation decides fallback/fail-closed.

### 6.6 `tracing.py`

Required API:

```python
def build_manifest_item(...) -> ContextManifestItem: ...
def empty_read_manifest() -> ContextReadManifest: ...
def build_trace(...) -> ContextTrace: ...
def merge_trace_metadata(trace: ContextTrace, metadata: Mapping[str, Any]) -> ContextTrace: ...
```

Trace must not contain hidden raw content.

### 6.7 `overflow.py`

Required API:

```python
def classify_overflow_signal(
    *,
    provider_name: str,
    raw_message: str | None,
    known_signals: Sequence[str] = (),
) -> ContextOverflowSignal: ...
```

First slice behavior:

- Classify obvious context length messages.
- Return `unknown` when unsure.
- Do not wire retries.
- Do not mutate operation requests.

## 7. Compact Operation API

### 7.1 `compaction.py`

Required protocol:

```python
class CompactPromptRunner(Protocol):
    async def run_compact_prompt(
        self,
        request: ContextCompactPromptRequest,
    ) -> dict[str, Any]: ...
```

Required API:

```python
def decide_compaction_action(
    *,
    dropped_items: Sequence[ContextSourceItem],
    previous_artifact: ContextArtifact | None,
) -> Literal["not_needed", "reused", "updated", "rebuilt"]: ...

async def run_compact_operation(
    *,
    request: ContextOperationRequest,
    dropped_items: Sequence[ContextSourceItem],
    first_kept_source_item_id: str | None,
    compact_prompt_runner: CompactPromptRunner | None = None,
) -> ContextOperationResult: ...
```

Action rules:

- No dropped items -> `not_needed`.
- Previous artifact fingerprint matches dropped items -> `reused`.
- Previous artifact source count is a valid prefix of dropped items -> `updated`.
- Otherwise -> `rebuilt`.

Model prompt rules:

- `updated` sends previous artifact payload plus only newly dropped items.
- `rebuilt` sends the full dropped item set.
- Prompt data is serialized as data, not as chat history to continue.
- No tools are exposed by this layer.
- Output must be strict JSON.

Fallback rules:

- If no runner exists and fallback mode is deterministic -> build deterministic
  fallback artifact.
- If runner raises or returns invalid payload and fallback mode is deterministic
  -> build fallback artifact and record reason.
- If fallback mode is `skip_section` -> return no artifact with fallback report.
- If fallback mode is `fail_closed` -> return `status="failed"` and no sections.

Deterministic fallback artifact:

- Uses the first non-empty source item texts in source order.
- Caps lines by `fallback_summary_line_limit`.
- Carries only allowed recovery refs.
- Sets `created_by="deterministic"`.

## 8. Setup Adapter Development Details

### 8.1 File

Implement:

```text
backend/rp/context_engineering/adapters/setup.py
```

This file may import setup contracts:

- `SetupAgentDialogueMessage`
- `SetupWorkingDigest`
- `SetupToolOutcome`
- `SetupContextCompactSummary`
- `SetupCompactRecoveryHint`
- `SetupContextGovernanceReport`

It must not import `SetupWorkspace` or setup tool providers.

### 8.2 Public Class

```python
class SetupContextEngineeringAdapter:
    def build_stage_local_compact_request(
        self,
        *,
        history: Sequence[SetupAgentDialogueMessage],
        retained_tool_outcomes: Sequence[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: Literal["standard", "compact"],
        current_step: str,
        current_stage: str | None = None,
        estimated_input_tokens: int | None,
        previous_usage: Mapping[str, int | None] | None,
    ) -> ContextOperationRequest: ...

    def to_context_artifact(
        self,
        summary: SetupContextCompactSummary | None,
    ) -> ContextArtifact | None: ...

    def to_setup_compact_summary(
        self,
        artifact: ContextArtifact | None,
    ) -> SetupContextCompactSummary | None: ...

    def to_setup_governance_metadata(
        self,
        result: ContextOperationResult,
    ) -> dict[str, Any]: ...

    def to_setup_context_report(
        self,
        *,
        result: ContextOperationResult,
        raw_history_count: int,
        raw_history_chars: int,
        user_edit_delta_count: int,
        prior_stage_handoff_count: int,
        context_profile: Literal["standard", "compact"],
        profile_reasons: Sequence[str],
    ) -> SetupContextGovernanceReport: ...
```

### 8.3 Setup Mapping Rules

History:

- `source_scope` is adapter-owned opaque scope:
  - if `current_stage` is present, use `setup_stage:{current_stage}`;
  - otherwise use `setup_step:{current_step}`;
- `sequence_index = history index`
- user message -> `source_family="user_turn"`
- assistant message -> `source_family="assistant_turn"`
- `serialization_family="conversation_message"`
- `source_ref = f"setup:{current_step}:history:{index}"`

Tool outcomes:

- `source_family="tool_outcome"`
- `serialization_family="tool_observation"`
- `source_scope` uses the same setup stage/step scope as history.
- `sequence_index` after history items
- `source_ref = f"setup:{current_step}:tool_outcome:{index}"`
- setup `tool_name`, `success`, `error_code`, and `relevance` stay in payload or
  metadata, not common enums.

Working digest:

- `source_family="runtime_state"`
- `serialization_family="runtime_overlay"`
- `visibility="model_visible"`
- `source_scope` uses the same setup stage/step scope as history.
- not part of dropped-history fingerprint for compacting old conversation.

Existing summary:

- maps only to `ContextOperationRequest.previous_artifact`;
- does not become a `ContextSourceItem`;
- does not participate in dropped-source fingerprint.

Draft refs:

- stay adapter policy data;
- allowed prefixes initially match current setup governance:
  `draft:`, `foundation:`, `stage:`;
- unsupported refs are validation issues and should trigger fallback when model
  output contains them.

### 8.4 Setup Policy Mapping

For the first migration keep existing setup thresholds as adapter inputs:

```text
standard raw history window = 6 messages
compact raw history window = 4 messages
compact prompt max tokens = 1200
standard token budget = 2400
compact token budget = 600
```

Budget policy:

- `operation_budget_tokens` = selected setup token budget.
- `recent_window_items` = 6 or 4 based on `context_profile`.
- `compact_trigger_items` / `compact_trigger_tokens` may carry setup threshold
  metadata for trace but must not re-decide profile inside the kernel.

Placement policy:

- stable prefix is not used by setup adapter compact operation.
- recent raw conversation goes to `recent_raw`.
- retained tool outcomes go to `tool_outcomes`.
- working digest goes to `runtime_overlay`.
- compact artifact goes to `compact_artifact`.
- context report/pipeline stays metadata-only.

Validation policy:

- `schema_id = "setup_context_compact_summary.v1"`.
- `metadata["allowed_payload_fields"]` must exactly list setup compact payload
  fields:
  - `source_fingerprint`
  - `source_message_count`
  - `summary_lines`
  - `confirmed_points`
  - `open_threads`
  - `rejected_directions`
  - `draft_refs`
  - `recovery_hints`
  - `must_not_infer`
- forbidden payload fields include:
  - `tool_calls`
  - `draft_writes`
  - `workspace_patch`
  - `prior_stage_raw_discussion`
  - `analysis`
  - `scratchpad`
- list caps match setup compact summary caps:
  - `summary_lines`: 6
  - `confirmed_points`: 8
  - `open_threads`: 4
  - `rejected_directions`: 4
  - `draft_refs`: 6
  - `recovery_hints`: 6
  - `must_not_infer`: 4

## 9. Setup Migration Plan

### 9.1 Checkpoint A: T1-T4, No Production Setup Migration

Implement common package and setup adapter tests first.

Do not modify:

- `SetupContextGovernorService`
- `SetupContextCompactionService`
- `SetupAgentExecutionService`

Checkpoint A is complete when:

- common tests pass;
- setup adapter tests pass;
- no existing setup behavior has been changed.

### 9.2 Checkpoint B: T5, Setup Internals Use Common Kernel

Modify setup internals after Checkpoint A.

Preferred migration:

1. Inject `SetupContextEngineeringAdapter` into `SetupContextGovernorService`
   with a default instance.
2. Keep public signature of `govern_history(...)` and `govern_history_async(...)`
   stable.
3. Inside governor, build common operation request through setup adapter.
4. Use common selection to decide kept/dropped history.
5. Pass only `ContextSelectionResult.compactable_dropped_items` into common
   compaction for reuse/update/rebuild/fallback.
6. Convert result back to `SetupContextCompactSummary` and existing
   `governance_metadata`.
7. Keep `SetupAgentExecutionService._build_context_report(...)` compatible,
   but prefer data derived from common trace/read manifest when available.

Do not change:

- `SetupContextBuilder` truth packet responsibility.
- `SetupAgentPromptService` stable prompt boundary.
- final request message ordering.
- durable runtime state field allowlist.

### 9.3 Checkpoint C: Trellis Check

After Checkpoint B:

- run focused common tests;
- run focused setup regression tests;
- run lint/type checks for touched files;
- run `trellis-check` per workflow before moving to Story Runtime.

## 10. Required Tests

### 10.1 Common Contract Tests

`backend/rp/tests/test_context_engineering_contracts.py`

Assert:

- minimal `ContextOperationRequest` validates;
- unknown fields are rejected for policy/result models;
- `ContextSourceItem` preserves `source_scope`, `sequence_index`,
  `atomic_group_id`, and `must_keep_with`;
- `ContextReadManifest` separates selected/omitted/hidden/forbidden/
  metadata-only items;
- `previous_artifact` is accepted on request and is not a source item.

### 10.2 Estimation Tests

`backend/rp/tests/test_context_engineering_estimation.py`

Assert:

- text estimate uses `ceil(len(text) / 4)`;
- empty text estimates to `0`;
- payload estimate is stable under dict key ordering;
- explicit `estimated_tokens` wins;
- aggregate estimate is sum of item estimates.

### 10.3 Fingerprinting Tests

`backend/rp/tests/test_context_engineering_fingerprinting.py`

Assert:

- fingerprints are stable across dict key ordering;
- changing text changes fingerprint;
- changing `source_scope` or `sequence_index` changes fingerprint;
- changing `created_at` does not change fingerprint;
- previous artifact payload never contributes to source fingerprint.

### 10.4 Selection Tests

`backend/rp/tests/test_context_engineering_selection.py`

Assert:

- forbidden items are excluded and reported;
- hidden items are excluded and reported without raw content leakage;
- metadata-only items are excluded from sections and present in manifest;
- family item cap and family token cap omit deterministically;
- operation budget omits older lower-priority items first;
- recent raw window keeps latest conversation items by `sequence_index`;
- atomic groups are kept together by default;
- explicitly breakable atomic group records `atomic_group_broken_by_policy`;
- section order follows placement policy.
- `compactable_dropped_items` contains only omitted raw conversation items, not
  runtime state, tool outcomes, hidden/forbidden/metadata-only items, or
  previous compact artifacts.

### 10.5 Validation Tests

`backend/rp/tests/test_context_engineering_validation.py`

Assert:

- forbidden payload fields are rejected;
- list caps are enforced;
- string caps are enforced;
- unsupported recovery ref prefixes are rejected;
- allowed source refs are enforced when configured;
- validation report includes all issues, not only first issue.

### 10.6 Compaction Tests

`backend/rp/tests/test_context_engineering_compaction.py`

Assert:

- no dropped items -> `status="not_needed"`;
- matching previous fingerprint -> `status="reused"`;
- previous valid prefix -> `status="updated"`;
- invalid prefix -> `status="rebuilt"`;
- invalid model payload -> deterministic fallback when configured;
- fail-closed policy returns failed result;
- fallback artifact carries only allowed recovery refs;
- `first_kept_source_item_id` is preserved.

### 10.7 Overflow Tests

`backend/rp/tests/test_context_engineering_overflow.py`

Assert:

- obvious context-length messages classify as `context_length_error`;
- unknown messages classify as `unknown`;
- classification returns a recommended action but does not trigger retry or
  mutate the operation request.

### 10.8 Setup Adapter Tests

`backend/rp/tests/test_context_engineering_setup_adapter.py`

Assert:

- setup user/assistant history maps to common user/assistant source families;
- setup source items carry stable `source_scope` and `sequence_index`;
- setup source scope prefers `setup_stage:<current_stage>` when `current_stage`
  exists and falls back to `setup_step:<current_step>`;
- retained setup tool outcomes map to `tool_outcome` without promoting setup
  `relevance` to common enums;
- working digest maps to runtime overlay source;
- previous `SetupContextCompactSummary` maps only to `previous_artifact`;
- setup draft refs are adapter validation policy data;
- result maps back to `SetupContextCompactSummary`;
- setup governance metadata preserves existing keys:
  - `raw_history_limit`
  - `kept_history_count`
  - `compacted_history_count`
  - `estimated_input_tokens`
  - `previous_prompt_tokens`
  - `previous_total_tokens`
  - `summary_strategy`
  - `summary_action`
  - `fallback_reason`

### 10.9 Setup Regression Tests

Run and extend existing tests where needed:

- `backend/rp/tests/test_setup_context_governor.py`
  - existing raw window behavior still holds;
  - existing compact summary reuse/update/rebuild behavior still holds;
  - invalid compact prompt output still falls back.
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - compact profile reasons still include history/token/observed-usage/user-edit
    triggers;
  - observed usage remains scoped by `workspace_id + current_step`;
  - governed history, not raw full history, reaches runtime when compacting.
- `backend/rp/tests/test_setup_agent_prompt_service.py`
  - `context_report`, governed history, working digest, retained outcomes,
    compact summary, loop trace, and raw retry process stay out of stable prompt.
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - final message order remains system prompt -> runtime overlay -> governed
    history -> current user;
  - runtime overlay does not duplicate full context packet.
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
  - common trace/read manifest/context report are not persisted into durable
    snapshot;
  - transient/debug fields are rejected at root.

## 11. Verification Commands

Use focused verification during development:

```powershell
python -m pytest backend/rp/tests/test_context_engineering_contracts.py backend/rp/tests/test_context_engineering_estimation.py backend/rp/tests/test_context_engineering_selection.py backend/rp/tests/test_context_engineering_fingerprinting.py backend/rp/tests/test_context_engineering_validation.py backend/rp/tests/test_context_engineering_compaction.py backend/rp/tests/test_context_engineering_overflow.py backend/rp/tests/test_context_engineering_setup_adapter.py -q
```

After setup migration:

```powershell
python -m pytest backend/rp/tests/test_setup_context_governor.py backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_state_service.py -q
```

Lint/type/diff checks for touched files:

```powershell
python -m ruff check backend/rp/context_engineering backend/rp/tests/test_context_engineering_contracts.py backend/rp/tests/test_context_engineering_estimation.py backend/rp/tests/test_context_engineering_selection.py backend/rp/tests/test_context_engineering_fingerprinting.py backend/rp/tests/test_context_engineering_validation.py backend/rp/tests/test_context_engineering_compaction.py backend/rp/tests/test_context_engineering_overflow.py backend/rp/tests/test_context_engineering_setup_adapter.py
python -m ruff format --check backend/rp/context_engineering backend/rp/tests/test_context_engineering_contracts.py backend/rp/tests/test_context_engineering_estimation.py backend/rp/tests/test_context_engineering_selection.py backend/rp/tests/test_context_engineering_fingerprinting.py backend/rp/tests/test_context_engineering_validation.py backend/rp/tests/test_context_engineering_compaction.py backend/rp/tests/test_context_engineering_overflow.py backend/rp/tests/test_context_engineering_setup_adapter.py
python -m mypy --follow-imports=skip --check-untyped-defs backend/rp/context_engineering backend/rp/tests/test_context_engineering_contracts.py backend/rp/tests/test_context_engineering_estimation.py backend/rp/tests/test_context_engineering_selection.py backend/rp/tests/test_context_engineering_fingerprinting.py backend/rp/tests/test_context_engineering_validation.py backend/rp/tests/test_context_engineering_compaction.py backend/rp/tests/test_context_engineering_overflow.py backend/rp/tests/test_context_engineering_setup_adapter.py
git diff --check -- backend/rp/context_engineering backend/rp/tests/test_context_engineering_contracts.py backend/rp/tests/test_context_engineering_estimation.py backend/rp/tests/test_context_engineering_selection.py backend/rp/tests/test_context_engineering_fingerprinting.py backend/rp/tests/test_context_engineering_validation.py backend/rp/tests/test_context_engineering_compaction.py backend/rp/tests/test_context_engineering_overflow.py backend/rp/tests/test_context_engineering_setup_adapter.py
```

Checkpoint B lint/type/diff must also include every touched setup service file.
At minimum, if modified, include:

```powershell
python -m ruff check backend/rp/services/setup_context_governor.py backend/rp/services/setup_context_compaction_service.py backend/rp/services/setup_agent_execution_service.py
python -m ruff format --check backend/rp/services/setup_context_governor.py backend/rp/services/setup_context_compaction_service.py backend/rp/services/setup_agent_execution_service.py
python -m mypy --follow-imports=skip --check-untyped-defs backend/rp/services/setup_context_governor.py backend/rp/services/setup_context_compaction_service.py backend/rp/services/setup_agent_execution_service.py
git diff --check -- backend/rp/services/setup_context_governor.py backend/rp/services/setup_context_compaction_service.py backend/rp/services/setup_agent_execution_service.py
```

Final workflow gate:

```text
trellis-check
```

## 12. Engineering Review Checklist

Before declaring the implementation complete:

- Common kernel can be explained without mentioning SetupAgent.
- Common kernel imports no setup/story/memory/UI truth services.
- Setup adapter is the only layer that knows setup compact schema and draft ref
  policy.
- Previous compact summary travels through `previous_artifact`, never through
  `source_items`.
- `source_scope`, `sequence_index`, and atomic group fields are covered by tests.
- Read manifest records selected, omitted, hidden, forbidden, and metadata-only
  items with reasons.
- Hidden and forbidden raw content does not leak into trace or manifest.
- Compact output never mutates business truth.
- Setup context report remains transient and out of prompt/durable state.
- Story Runtime remains unwired in this slice.
- Focused tests, lint, type check, diff check, and Trellis check are complete.

## 13. Stop Conditions

Pause and re-plan before continuing if any of these happen:

- The common kernel needs to import `SetupWorkspace`, setup tools, Story Runtime
  mutation services, or Memory OS writers.
- Setup migration requires changing product-visible setup behavior.
- Compact artifact needs to become draft/Core/Recall/Archival truth to pass a
  test.
- Selection behavior can only be explained by adapter metadata conventions that
  the common kernel does not validate or trace.
- Focused setup regression tests fail in prompt assembly, durable snapshot, or
  observed-usage isolation.
