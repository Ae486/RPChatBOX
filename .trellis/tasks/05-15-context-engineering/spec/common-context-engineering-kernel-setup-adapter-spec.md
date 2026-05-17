# Common Context Engineering Kernel + Setup Adapter Pilot Spec

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Slice: `Common Context Engineering Kernel + Setup Adapter Pilot`
>
> Status: draft-v1
>
> Important boundary: SetupAgent is the proving ground. It is not the authority
> and not the complete target architecture. Current setup context code is local
> workload evidence and migration material only.

## 1. Decision

Implement the first coherent Context Engineering slice as a common pre-model
governance kernel plus a SetupAgent adapter pilot.

The common kernel must be understandable and testable without SetupAgent. The
setup integration must prove the kernel against a real workload without
promoting setup-specific stages, draft refs, tools, cognition, or workspace
truth into common contracts.

The implementation order is:

1. add common contracts and policy models;
2. add deterministic source selection, budget slicing, validation, fallback,
   fingerprinting, and trace mechanics;
3. add setup adapter mappings around the existing setup workload;
4. migrate the setup context governor / compaction path behind the common
   operation interface while preserving external setup behavior;
5. add focused unit tests for common mechanics and setup adapter behavior;
6. run Trellis check before Story Runtime wiring.

Story Runtime adapters are specified as future consumers only in this slice.

## 2. Authority And Non-Authority

### 2.1 Design Authority

The design authority is mature Context Engineering practice:

- Claude Code / Claude Code from Scratch: deliberate request assembly, memory
  index/content split, skill isolation, compaction as pre-model operation, exact
  recovery refs.
- pi-mono: session persistence separate from model-visible context, compaction
  entries with `firstKeptEntryId`, recent-window retention, tool-call/result
  pairing, branch summaries, provider overflow normalization.
- OpenAI: explicit conversation state, compaction as continuation support,
  prompt caching through stable prefixes, agent sessions separate from runs.
- Anthropic: attention-budget curation, prompt caching blocks, Claude Code
  memory as editable context rather than unverified current truth.
- Google Gemini / Vertex: long-context and context-cache support require token
  counting, stability classification, and application-owned scoping.
- LangChain / Deep Agents / Manus: write/select/compress/isolate context,
  filesystem or sidecar offloading, deterministic serialization, omitted-source
  evidence.

### 2.2 SetupAgent Is Not Authority

SetupAgent proves that the common module can support:

- current-stage long discussions;
- recent raw user wording;
- retained tool outcomes;
- working digest;
- compact summary reuse / update / fallback;
- draft-ref recovery hints;
- context report and eval trace.

SetupAgent does not define common kernel concepts. These stay setup-specific:

- `SetupWorkspace`;
- setup stages and steps;
- setup draft refs and truth-index refs;
- setup review / commit / readiness;
- setup tool names and runtime allowlists;
- setup SkillPack prompt packaging;
- setup cognition and completion guard state.

If an existing setup service encodes the wrong abstraction, the implementation
may optimize, replace, or retire it. Compatibility is required at the product
boundary, not at every internal setup service boundary.

## 3. Package Shape

Create a common package under:

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

Initial implementation may keep setup service names as wrappers, but the
common package must not import setup workspace models, Story Runtime Core
mutation services, Memory OS writers, UI contracts, or tool providers.

Allowed dependency direction:

```text
setup services -> setup adapter -> common context_engineering kernel
story services -> story adapter -> common context_engineering kernel
common kernel -> no RP business truth services
```

## 4. Common Contracts

### 4.1 Source Identity And Visibility

Add these kernel contracts in `contracts.py`:

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
```

`ContextSourceItem`:

```python
class ContextSourceItem(BaseModel):
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

- `source_item_id` must be stable within one operation.
- `source_scope` identifies the adapter-defined visibility scope, such as a
  setup step, story branch, worker packet, brainstorm window, chapter bridge,
  or retrieval batch. The kernel treats it as opaque but must preserve it in
  manifest and trace.
- `sequence_index` is the adapter-provided deterministic order within a scope.
  The kernel must use it before `created_at` when preserving recent windows or
  compact cut points.
- `atomic_group_id` and `must_keep_with` express indivisible context groups,
  such as tool-call/tool-result pairs, split-turn fragments, accepted-prose
  excerpt plus its ref header, or a retrieval card plus citation block.
- `source_ref` identifies the origin; it is not automatically a recovery ref.
- `recovery_refs` must be validated by adapter policy before they can be
  emitted into compact artifacts.
- `visibility="metadata_only"` items may contribute trace but must not enter
  model-visible sections.
- `visibility="forbidden"` items must be reported and excluded.
- Selection must never keep only half of an atomic group unless the placement
  policy explicitly allows breaking that group and records the break reason.

### 4.2 Operation Request

`ContextOperationRequest`:

```python
class ContextOperationRequest(BaseModel):
    operation_id: str
    operation_kind: Literal[
        "packet_build",
        "trim",
        "compact",
        "summarize",
        "trace_only",
    ]
    runtime_family: str
    source_items: list[ContextSourceItem]
    budget_policy: ContextBudgetPolicy
    placement_policy: ContextPlacementPolicy
    validation_policy: ContextValidationPolicy
    fallback_policy: ContextFallbackPolicy
    provider_profile: ContextProviderProfile | None = None
    previous_artifact: ContextArtifact | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Rules:

- Runtime adapters create requests.
- The kernel reads only this request and injected services.
- The request must contain enough policy for deterministic operation; hidden
  global thresholds are not allowed.

### 4.3 Budget Policy

`ContextBudgetPolicy`:

```python
class ContextBudgetPolicy(BaseModel):
    context_window_tokens: int | None = None
    response_reserve_tokens: int = 1024
    operation_budget_tokens: int | None = None
    recent_window_tokens: int | None = None
    recent_window_items: int | None = None
    compact_trigger_tokens: int | None = None
    compact_trigger_items: int | None = None
    source_family_token_caps: dict[str, int] = Field(default_factory=dict)
    source_family_item_caps: dict[str, int] = Field(default_factory=dict)
```

Rules:

- Budget decisions must be traceable.
- Token estimates may start approximate, but estimates and observed usage must
  be recorded separately.
- Provider response reserve must be explicit.
- Family caps prevent one source family from consuming the whole prompt.

### 4.4 Placement Policy

`ContextPlacementPolicy`:

```python
class ContextPlacementPolicy(BaseModel):
    ordered_slots: list[str]
    slot_by_source_family: dict[str, str] = Field(default_factory=dict)
    stable_prefix_slots: list[str] = Field(default_factory=list)
    volatile_suffix_slots: list[str] = Field(default_factory=list)
    metadata_only_slots: list[str] = Field(default_factory=list)
    breakable_atomic_group_ids: list[str] = Field(default_factory=list)
```

Initial standard slots:

```text
stable_prefix
runtime_overlay
compact_artifact
recent_raw
retrieval
tool_outcomes
sidecar
metadata_only
```

Rules:

- Stable prefix must not be polluted by volatile history or compact artifacts.
- Recent raw windows must be placed after stable instructions.
- Trace/debug-only surfaces must stay metadata-only.
- Atomic groups are preserved by default. Breaking a group is exceptional and
  must be listed in `breakable_atomic_group_ids` plus the read manifest.

### 4.5 Validation And Fallback

`ContextValidationPolicy`:

```python
class ContextValidationPolicy(BaseModel):
    schema_id: str | None = None
    allowed_recovery_ref_prefixes: list[str] = Field(default_factory=list)
    allowed_source_refs: list[str] = Field(default_factory=list)
    forbidden_payload_fields: list[str] = Field(default_factory=list)
    max_list_lengths: dict[str, int] = Field(default_factory=dict)
    max_string_lengths: dict[str, int] = Field(default_factory=dict)
    reject_unknown_fields: bool = True
```

`ContextFallbackPolicy`:

```python
class ContextFallbackPolicy(BaseModel):
    mode: Literal["deterministic_fallback", "skip_section", "fail_closed"]
    fallback_summary_line_limit: int = 6
    user_visible_error_code: str | None = None
```

Rules:

- Model-produced compact/summarize output must validate before reuse.
- Unknown fields, forbidden fields, unsupported refs, or oversized fields must
  be rejected.
- Fallback reason must be visible in trace.

### 4.6 Provider Profile And Overflow

`ContextProviderProfile`:

```python
class ContextProviderProfile(BaseModel):
    provider_name: str
    model_name: str | None = None
    context_window_tokens: int | None = None
    supports_prompt_cache: bool = False
    supports_provider_managed_state: bool = False
    thinking_or_reasoning_blocks: bool = False
    tool_result_constraints: dict[str, Any] = Field(default_factory=dict)
    known_overflow_signals: list[str] = Field(default_factory=list)
```

`ContextOverflowSignal`:

```python
class ContextOverflowSignal(BaseModel):
    provider_name: str
    signal_kind: Literal[
        "context_length_error",
        "silent_truncation_risk",
        "tool_result_too_large",
        "unknown",
    ]
    raw_message: str | None = None
    recommended_action: Literal["compact_retry", "trim_retry", "fail_closed"]
```

Rules:

- Provider-managed state is optional convenience, not RP truth.
- Long-context models still require budget, placement, trace, and recovery refs.
- Overflow classification should be provider-aware but output a common signal.

### 4.7 Artifact, Result, Manifest, Trace

`ContextArtifact`:

```python
class ContextArtifact(BaseModel):
    artifact_id: str
    artifact_kind: Literal["compact_summary", "operation_summary"]
    schema_id: str
    schema_version: str
    source_fingerprint: str
    source_item_count: int
    payload: dict[str, Any]
    recovery_refs: list[str] = Field(default_factory=list)
    first_kept_source_item_id: str | None = None
    created_by: Literal["deterministic", "model", "adapter"]
    validation_report: ContextValidationReport
    fallback_report: ContextFallbackReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

`ContextOperationResult`:

```python
class ContextOperationResult(BaseModel):
    operation_id: str
    status: Literal[
        "not_needed",
        "selected",
        "reused",
        "updated",
        "rebuilt",
        "fallback",
        "failed",
    ]
    sections: list[ContextSection] = Field(default_factory=list)
    artifact: ContextArtifact | None = None
    read_manifest: ContextReadManifest
    trace: ContextTrace
    validation_report: ContextValidationReport
    fallback_report: ContextFallbackReport | None = None
```

`ContextReadManifest` must list selected, omitted, hidden, and forbidden source
items with reasons. `ContextTrace` must include token estimates, selected counts
by family, budget decisions, compact/fallback decisions, cache-stability notes,
and provider usage if available.

`ContextSelectionResult` is the handoff between selection and optional
compaction. It must include `selected_items`, `recent_raw_items`,
`compactable_dropped_items`, `sections`, `read_manifest`, and `trace`.
`compactable_dropped_items` may contain only raw model-visible conversation
items omitted because they are older than the recent window or replaced by
compact-artifact policy. It must not include runtime state, tool outcomes,
hidden/forbidden/metadata-only items, sidecars, or previous compact artifacts.

## 5. Kernel Mechanics

### 5.1 Estimation

Implement approximate estimation first:

- text token estimate = `ceil(len(text) / 4)`;
- payload estimate = JSON string length / 4, bounded by a max estimate;
- allow adapter-provided `estimated_tokens` to override when present;
- record `estimate_method` in trace.

Do not block the first slice on provider-specific tokenizer packages.

### 5.2 Selection And Omission

Selection must:

1. remove forbidden and hidden items from model-visible candidates;
2. retain metadata-only items for trace only;
3. group candidates by source family and placement slot;
4. preserve adapter-provided `source_scope` and `sequence_index`;
5. keep atomic groups together unless policy explicitly allows breaking them;
6. enforce family caps;
7. preserve recent raw window by item count or token cap;
8. place compact artifact before recent raw history when available;
9. produce `ContextSelectionResult`, including the narrow
   `compactable_dropped_items` compaction handoff;
10. produce omitted-source reasons.

Omission reasons should include:

```text
forbidden_by_policy
hidden_by_policy
metadata_only
family_item_cap
family_token_cap
operation_budget_exceeded
replaced_by_compact_artifact
empty_content
atomic_group_omitted
atomic_group_broken_by_policy
```

### 5.3 Fingerprinting And Reuse

Fingerprint source items deterministically from:

- `source_item_id`;
- `source_family`;
- `source_scope`;
- `sequence_index`;
- `source_ref`;
- normalized text or canonical payload JSON;
- recovery refs.

Reuse rules:

- if previous artifact fingerprint equals the dropped source prefix, reuse;
- if previous artifact count is a valid prefix of the dropped source prefix,
  update using previous artifact plus newly dropped items;
- otherwise rebuild from the full dropped prefix;
- if no dropped source exists, no compact artifact is needed.

The common artifact should support pi-mono-style `first_kept_source_item_id` so
future Story Runtime branch/session consumers can reason about where raw recent
context resumes.

Previous compact artifacts are operation state, not raw source material. A
`previous_artifact` may be used for reuse/update and may be serialized as
bounded prior-summary data inside a compact prompt, but it must not participate
in the dropped-source fingerprint for the same compact operation.

### 5.4 Compaction

`ContextCompactionService` should accept an injected model summarizer:

```python
class CompactPromptRunner(Protocol):
    async def run_compact_prompt(
        self,
        request: ContextCompactPromptRequest,
    ) -> dict[str, Any]: ...
```

Rules:

- compact prompt is a no-tools model operation;
- compact prompt receives source items as data, not as conversation to
  continue;
- compact prompt output must be strict JSON;
- analysis/scratchpad fields are forbidden;
- adapter supplies schema id and validation policy;
- invalid model output triggers fallback policy.

### 5.5 Serialization

Kernel serialization returns provider-neutral sections:

```python
class ContextSection(BaseModel):
    section_id: str
    slot: str
    title: str
    content: str
    source_item_ids: list[str]
    stability: ContextStability
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Provider-specific chat messages remain outside the common kernel initially.
Setup runtime can keep its current message assembly while consuming kernel
sections through the setup adapter.

## 6. Setup Adapter Pilot

### 6.1 Adapter Inputs

The setup adapter may read or receive:

- `SetupAgentDialogueMessage` history;
- `SetupWorkingDigest`;
- retained `SetupToolOutcome`;
- previous `SetupContextCompactSummary`;
- `context_profile`;
- `current_step`;
- `current_stage` when available;
- estimated input tokens and previous same-step usage;
- setup draft refs allowed for recovery.

The adapter must not expose these setup contracts as kernel primitives.

### 6.2 Mapping To Common Sources

Map setup inputs into common source items:

| Setup input | Common source |
| --- | --- |
| user dialogue message | `source_family="user_turn"`, `serialization_family="conversation_message"` |
| assistant dialogue message | `source_family="assistant_turn"`, `serialization_family="conversation_message"` |
| retained tool outcome | `source_family="tool_outcome"`, `serialization_family="tool_observation"` |
| working digest | `source_family="runtime_state"`, `serialization_family="runtime_overlay"` |
| draft/current truth refs | `source_family="workspace_truth"`, metadata/recovery refs only |
| context report / pipeline | `visibility="metadata_only"` |

Setup-specific fields such as `current_step`, `draft_refs`, `relevance`, and
tool names stay in adapter metadata or setup schema payloads.

Setup `source_scope` should prefer `setup_stage:<current_stage>` when
`current_stage` is available and fall back to `setup_step:<current_step>`.
This keeps setup lifecycle semantics in the adapter while preserving an opaque
common-kernel scope string.

Previous setup compact summary maps to `ContextOperationRequest.previous_artifact`.
It is not a `ContextSourceItem` for the same compact operation and must not be
included in the dropped-history fingerprint. When incremental update is needed,
the adapter may pass its bounded payload to the compact prompt as prior-summary
operation state.

### 6.3 Setup Compact Schema

For the pilot, keep `SetupContextCompactSummary` as the setup adapter schema.
It maps to `ContextArtifact.payload`; it is not a common kernel schema.

Adapter validation must enforce:

- max list lengths already required by setup stage-local governance;
- allowed payload fields exactly matching `SetupContextCompactSummary`:
  `source_fingerprint`, `source_message_count`, `summary_lines`,
  `confirmed_points`, `open_threads`, `rejected_directions`, `draft_refs`,
  `recovery_hints`, and `must_not_infer`;
- allowed setup draft ref prefixes;
- no prior-stage raw discussion reconstruction;
- no tool-use or draft-mutation fields;
- source fingerprint and source message/source item count match the selected
  `compactable_dropped_items` set.

### 6.4 Setup Service Migration

Migration should be conservative at product boundaries:

1. keep `SetupContextBuilder` as setup truth packet builder;
2. replace or wrap `SetupContextGovernorService` internals so it builds a
   `ContextOperationRequest`;
3. replace or wrap `SetupContextCompactionService` internals so it delegates
   fingerprint/reuse/update/validate/fallback mechanics to the common kernel;
4. keep `SetupContextGovernanceReport` externally available, but build it from
   `ContextTrace` and `ContextReadManifest` where possible;
5. keep `SetupAgentPromptService` and runtime message ordering compatible;
6. do not persist common trace/read manifest as durable setup cognition unless
   a later spec explicitly allows it.

The first adapter can be named:

```text
backend/rp/context_engineering/adapters/setup.py
```

Expected public adapter methods:

```python
class SetupContextEngineeringAdapter:
    def build_stage_local_compact_request(...) -> ContextOperationRequest: ...
    def to_setup_compact_summary(...) -> SetupContextCompactSummary | None: ...
    def to_setup_governance_metadata(...) -> dict[str, Any]: ...
    def to_setup_context_report(...) -> SetupContextGovernanceReport: ...
```

## 7. Story Runtime Future Adapters

Do not wire Story Runtime in this slice.

The spec must leave the common kernel ready for future adapters:

- writer packet context compact;
- worker packet sidecar compact;
- brainstorm summarize;
- chapter bridge summary;
- review summary;
- retrieval composition.

Future Story Runtime adapters must preserve:

- branch-aware source scope before compact;
- recent accepted prose and user intent raw retention;
- writer/worker packet separation;
- no compact artifact as Core / Recall / Archival / accepted story truth;
- read manifest and omission evidence.

## 8. Implementation Tasks

### T1 Common Contracts

Files:

- `backend/rp/context_engineering/contracts.py`
- `backend/rp/context_engineering/policies.py`

Deliver:

- all models in sections 4.1 to 4.7;
- `extra="forbid"` for policy/result models unless explicitly documented;
- helper enums/literals grouped near their model use.

Tests:

- instantiate minimal request/result/artifact;
- reject unknown fields for validation-sensitive models;
- verify hidden/forbidden/metadata-only visibility values are supported.
- verify `source_scope`, `sequence_index`, `atomic_group_id`, and
  `must_keep_with` are preserved in manifests/traces.

### T2 Deterministic Kernel Mechanics

Files:

- `estimation.py`
- `selection.py`
- `fingerprinting.py`
- `validation.py`
- `tracing.py`

Deliver:

- token estimate;
- deterministic source fingerprint;
- selection by visibility, placement, recent window, family cap, budget;
- read manifest with selected/omitted/hidden/forbidden reasons;
- validation report and fallback report builders.

Tests:

- forbidden items excluded and reported;
- metadata-only items excluded from model sections but present in manifest;
- recent raw window survives when older items are omitted;
- family caps produce deterministic omission reasons;
- atomic groups are kept together by default;
- explicit breakable atomic groups record `atomic_group_broken_by_policy`;
- fingerprint is stable under dict key ordering.

### T3 Compact Operation

Files:

- `compaction.py`

Deliver:

- reuse / update / rebuild decision;
- no-tools compact prompt request shape;
- strict payload validation against adapter policy;
- deterministic fallback artifact;
- trace fields for summary action and fallback reason.

Tests:

- matching fingerprint reuses previous artifact;
- valid prefix updates from previous artifact plus delta;
- invalid prefix rebuilds;
- invalid model payload falls back or fails closed per policy;
- fallback artifact carries recovery refs allowed by policy only.
- previous compact artifact is passed through `previous_artifact`, not selected
  as a dropped source item.

### T4 Setup Adapter

Files:

- `adapters/setup.py`

Deliver:

- setup history/digest/tool-outcome/source-ref mapping;
- setup compact request builder;
- setup result mapper back to `SetupContextCompactSummary`;
- setup governance metadata/report mapper;
- no setup-specific enum promoted to common kernel.
- previous `SetupContextCompactSummary` maps only to `previous_artifact`.

Tests:

- setup dialogue maps to user/assistant source families;
- setup tool outcomes map to bounded tool outcome sources;
- setup draft refs validate through setup adapter policy;
- previous setup compact summary does not participate in source fingerprint;
- setup report can be built from common trace without entering prompt content.

### T5 Setup Path Migration

Files likely affected:

- `backend/rp/services/setup_context_governor.py`
- `backend/rp/services/setup_context_compaction_service.py`
- `backend/rp/services/setup_agent_execution_service.py`
- focused tests under `backend/rp/tests/`

Deliver:

- current setup public behavior remains compatible;
- internals call common kernel for shared mechanics;
- existing setup thresholds remain adapter policy inputs for now;
- `SetupContextGovernanceReport` remains available;
- `context_report` and read manifest stay transient/debug surfaces.

Tests:

- existing setup context governor tests still pass;
- existing setup execution service context-profile tests still pass;
- new setup adapter tests prove mapping and trace;
- no durable setup snapshot persists common trace/read manifest accidentally.
- `context_report` must stay out of `RpAgentTurnInput.context_bundle`, stable
  prompt, runtime overlay prompt content, and durable runtime snapshot.
- final request ordering must remain `system prompt -> runtime overlay ->
  governed history -> current user`.
- observed usage pressure must remain scoped by `workspace_id + current_step`
  and must not cross-contaminate unrelated setup work.
- durable snapshot root-field allowlist must continue rejecting transient/debug
  fields such as `context_report`, `context_pipeline`, provider deltas, and
  structured result payloads.

### T6 Trellis Check

Run after T1-T5 as one coherent implementation slice:

```text
trellis-check
```

Minimum verification:

- unit tests for common kernel;
- setup adapter tests;
- relevant existing setup context tests;
- JSONL task records valid;
- no Story Runtime wiring in this slice.

Recommended implementation checkpoints inside the same spec slice:

1. T1-T4: common contracts, deterministic mechanics, compact operation, and
   setup adapter pass focused unit tests without production setup migration.
2. T5-T6: migrate setup production path, run existing setup governance tests,
   then run Trellis check.

This keeps one coherent Trellis slice while making failures easier to localize.

## 9. Acceptance Criteria

The slice is accepted when:

- common contracts exist and can be understood without SetupAgent;
- kernel mechanics cover selection, budget slicing, recent raw retention,
  source fingerprinting, compact reuse/update/rebuild, validation, fallback,
  read manifest, and trace;
- SetupAgent uses the common module through a setup adapter or wrapper;
- setup-specific refs, stages, draft truth, tools, cognition, and readiness do
  not enter common contracts;
- setup behavior remains externally compatible;
- compact output remains model-input support unless a separate setup apply path
  accepts it;
- Story Runtime remains unwired but has clear adapter expectations;
- tests prove common behavior and setup pilot behavior;
- Trellis check has been run after the coherent slice.

## 10. Explicit Rejections

Do not implement these in this slice:

- a generic memory writer;
- Story Runtime adapter wiring;
- provider-managed conversation state;
- provider-specific tokenizer dependency;
- provider overflow retry wiring; the first slice may model overflow signals
  only, with retry integration deferred;
- a new setup runtime persistence table;
- compact output writing setup draft or story truth;
- promotion of `SetupContextPacket`, `SetupContextCompactSummary`, setup draft
  refs, or setup tool names into common kernel concepts;
- broad rewrite of `WritingPacketBuilder` or `ContextOrchestrationService`;
- replacing current setup product semantics under the name of context
  extraction.

## 11. Review Questions For Subagent

The spec review should answer:

1. Does the spec keep SetupAgent as proving ground rather than authority?
2. Are the common contracts runtime-agnostic enough for Story Runtime later?
3. Are any setup-specific concepts accidentally promoted into the kernel?
4. Is the implementation slice too broad for one coherent Trellis check?
5. Are test requirements strong enough to prevent regressions in setup context
   governance?
6. Are mature-framework lessons represented as mechanics instead of copied
   product behavior?
