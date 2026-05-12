# Context Engineering / Compact-Summary Module Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Scope: cross-runtime common capability, documented from story runtime needs
>
> Status: draft-v1

## 1. Positioning

Context Engineering is the shared pre-model-call capability that decides what a
model sees, in what order, under which budget, and with what trace evidence.

Compact / summary is a child capability of Context Engineering. It compresses
selected source material into a typed business schema when raw material is too
large, too old, or too noisy to keep in the prompt-visible window.

This module is not owned by story runtime implementation. Setup agent should be
the first implementation owner because setup already has the most mature
context pipeline:

- `SetupContextBuilder`
- `SetupContextGovernorService`
- `SetupContextCompactionService`
- `SetupContextPipelineSnapshot`
- `context_report`
- compact summary fingerprint / reuse / update / fallback

Story runtime uses the common module through policy adapters. Story runtime
owns writer / brainstorm / chapter / memory packet policy; it does not own the
generic compact execution kernel.

## 2. Why This Exists

The project now has multiple places that need summary / compact behavior:

| Area | Need | Business truth changed by summary? |
| --- | --- | --- |
| setup stage-local turns | preserve older current-step discussion after raw history is trimmed | no |
| setup stage handoff | carry accepted stage output to later setup stages | yes, but only through existing accepted handoff contracts |
| story writer packet | keep recent prose raw while bounding older context and sidecars | no |
| writer brainstorm | turn discussion into user-editable summary items before scheduler dispatch | no |
| longform chapter bridge | summarize a completed chapter for the next chapter | no, Runtime Workspace sidecar only |
| chapter / session review | produce bounded review material for later writer packets | no |
| post-write memory maintenance | feed workers enough accepted prose and refs to decide derived updates | no direct truth mutation |

The common problem is not "write a summary". The common problem is safe
pre-model context governance:

1. keep business truth outside prompt artifacts;
2. preserve recent raw material when it matters for tone and continuity;
3. compress older material only through typed operations;
4. validate structured output before reuse;
5. record budget, fingerprint, fallback, and usage evidence.

## 3. External Reference Lessons

Mature references support the same direction:

- OpenAI conversation-state guidance treats model-visible messages as an
  explicit input surface that must be bounded and managed by the application.
- OpenAI prompt caching guidance rewards stable prompt prefixes, so volatile
  summaries and raw recent turns should be isolated from stable role and
  contract prompts.
- Anthropic context-management / prompt-caching guidance and Claude Code
  practice separate stable instructions, recent conversation, compacted older
  context, and recovery references.
- Claude Code style compaction uses manual or token-pressure compaction as a
  pre-model context operation, not as business truth.
- LangGraph provides useful checkpointer / state / summarization-node patterns,
  but it should not own RP product truth. RP still owns StorySession, BranchHead,
  Turn, RuntimeProfileSnapshot, MemoryRuntimeIdentity, and Memory OS contracts.

The engineering lesson is: use frameworks and mature projects for mechanics,
not for replacing RP's truth model.

## 4. Ownership Boundary

### 4.1 Common Kernel Owns

The common Context Engineering kernel owns reusable mechanics:

- source item normalization;
- token / character budget estimation;
- deterministic trimming;
- raw recent-window retention;
- source fingerprinting;
- compact prompt invocation;
- strict structured output validation;
- deterministic fallback summary;
- summary reuse / incremental update;
- model usage capture;
- trace / report emission.

### 4.2 Business Adapter Owns

Each runtime owns its policy adapter:

- which source items enter the operation;
- what recent raw window must remain;
- which schema the summary must satisfy;
- whether a summary is user-editable;
- whether the result is only prompt context, a Runtime Workspace sidecar, a
  dispatch request, or an accepted stage handoff;
- which refs are available for detail recovery.

### 4.3 Explicit Non-Ownership

The common module must not:

- mutate Core / Recall / Archival truth;
- accept or reject story drafts;
- choose writer candidates;
- classify brainstorm items into memory layers;
- decide worker routing;
- replace `WritingPacketBuilder` or `ContextOrchestrationService`;
- replace setup `SetupWorkspace` truth or story `RuntimeWorkspaceMaterial`
  truth.

## 5. Core Contracts

### 5.1 Source Item

```python
class ContextSourceItem(BaseModel):
    source_item_id: str
    source_kind: str
    source_ref: str | None = None
    role: Literal["system", "user", "assistant", "tool", "runtime", "artifact"]
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
```

`ContextSourceItem` is the normalized input shape for context operations. It is
not a memory source ref by itself. If a source item represents memory, the
memory ref must remain in `source_ref` / `metadata` and be governed by the
calling runtime.

### 5.2 Operation Request

```python
class ContextEngineeringOperationRequest(BaseModel):
    operation_id: str
    runtime_family: Literal["setup", "story_runtime"]
    operation_kind: str
    policy_id: str
    schema_id: str
    source_items: list[ContextSourceItem]
    existing_summary: dict[str, Any] | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    recent_window_policy: dict[str, Any] = Field(default_factory=dict)
    recovery_ref_policy: dict[str, Any] = Field(default_factory=dict)
    model_policy: dict[str, Any] = Field(default_factory=dict)
```

`operation_kind` examples:

- `setup_stage_local_compact`
- `setup_stage_handoff_summary`
- `story_writer_context_compact`
- `story_writer_brainstorm_summary`
- `story_chapter_bridge_summary`

### 5.3 Operation Result

```python
class ContextEngineeringOperationResult(BaseModel):
    operation_id: str
    status: Literal["not_needed", "reused", "updated", "rebuilt", "fallback", "failed"]
    summary_payload: dict[str, Any] | None = None
    retained_source_item_ids: list[str] = Field(default_factory=list)
    compacted_source_item_ids: list[str] = Field(default_factory=list)
    source_fingerprint: str | None = None
    source_item_count: int = 0
    validation_errors: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
```

The result is an assembly artifact. Business adapters decide whether and where
to store it. It never changes business truth by itself.

## 6. Structured Output Policy

All LLM-produced summaries must use strict structured output.

Required measures:

1. each operation has a named schema id;
2. schema is implemented as a typed model, preferably Pydantic BaseModel on the
   Python side;
3. unknown fields are rejected unless a schema explicitly allows extension;
4. list fields have hard caps;
5. string fields have length caps;
6. source refs are checked against allowed refs from the request;
7. forbidden business fields are rejected;
8. invalid model output falls back to deterministic summary or fails closed.

For story runtime V4, `BrainstormItem` is intentionally memory-layer agnostic.
It must not contain scheduler / worker fields such as `target_layer`,
`target_domain`, `operation_kind`, `operation`, or `intent_labels`.

## 7. Prompt / Message Assembly Rules

Summary and compact prompts are independent operation templates, not ordinary
user chat.

The stable part should contain:

- role of the compact operation;
- schema contract;
- forbidden behavior;
- output-only rule;
- source-ref policy.

The dynamic part should contain:

- bounded source items;
- existing summary if incremental update is allowed;
- recovery refs;
- operation-specific user instruction if any.

The operation should not expose tool schemas unless the specific adapter
explicitly allows a read-only recovery tool. Setup may allow draft-ref recovery;
story runtime brainstorm summary should not use memory mutation tools.

## 8. Story Runtime Adapter Policies

### 8.1 Writer Packet Compact

Story runtime writer packet policy remains in
`story-runtime-context-packet-spec.md`.

The adapter may ask the common module to compact older non-critical material,
but the packet must still preserve:

- stable system / writer contract;
- branch-aware Core view;
- recent raw prose / user turns;
- operation-mode sidecars;
- review overlay when rewriting;
- user instruction.

### 8.2 Writer Brainstorm Summary

Brainstorm is the writer's discussion persona / mode. It sees what writer sees,
plus the user's brainstorm prompt and the brainstorm discussion transcript.

Summary creation is explicit-user-action based in the current product stage.
The summary result is user-editable and confirmable before dispatch.
Ordinary brainstorm discussion does not incrementally create items or dispatch
memory changes.

The output schema is:

```python
class BrainstormSession(BaseModel):
    brainstorm_id: str
    identity: MemoryRuntimeIdentity
    status: Literal["open", "summarized", "reviewing", "dispatched", "closed"]
    items: list[BrainstormItem] = Field(default_factory=list)


class BrainstormItem(BaseModel):
    item_id: str
    summary_text: str
    evidence_text_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    user_edited: bool = False
    status: Literal[
        "proposed",
        "edited",
        "rejected",
        "confirmed",
        "dispatched",
        "applied",
        "pending_review",
        "conflict",
        "failed",
    ]
```

Brainstorm does not know Memory OS layer details. Confirmed items go to the
scheduler / dispatcher. In story runtime V4, only Core-oriented items should be
dispatched to specialized workers; non-Core wishes are returned as
review/redirect material instead of becoming Recall or Archival brainstorm
edits.

The brainstorm summary adapter should keep resource cost low:

- it summarizes user intent only and does not perform Core field reasoning;
- it does not request `reason` text by default;
- it does not require full conversation `source_refs` until discussion message
  ids / transcript anchors are stable;
- downstream worker output should use `source_item_id` to refer back to the
  confirmed `BrainstormItem`;
- backend deterministic code should fill old field values from base revision
  instead of asking an LLM to copy them.

### 8.3 Chapter Bridge Summary

Chapter bridge summary is a Runtime Workspace sidecar. It helps the next
chapter continue from accepted material. It is not Core truth and not Recall /
Archival truth.

The adapter should keep enough refs to recover exact accepted prose, but should
feed writer only bounded chapter goal / continuity / accepted outline /
summary sections.

## 9. Setup Adapter Policy

Setup remains the first implementation owner.

The setup adapter should generalize existing concepts rather than rewrite them:

- `SetupContextCompactionService` maps to compact operation execution;
- `SetupContextGovernorService` maps to policy and recent-window retention;
- `SetupContextGovernanceReport` maps to operation report;
- `SetupContextCompactSummary` remains setup's schema;
- `setup.read.draft_refs` remains setup-specific recovery.

The common module should be extracted only when it reduces duplicated
implementation across setup and story runtime. It must not destabilize the
already-working setup path.

## 10. Validation Matrix

- short source list under budget -> no compact; return `status="not_needed"`;
- existing summary fingerprint matches dropped prefix -> return `status="reused"`;
- existing summary is a valid prefix and new dropped items exist -> update only
  the delta and return `status="updated"`;
- existing summary cannot be trusted -> rebuild from bounded source input;
- compact LLM returns invalid JSON -> deterministic fallback or fail closed;
- compact LLM returns forbidden fields -> reject and fallback;
- source refs in summary are not present in request -> reject and fallback;
- token budget is exceeded before model call -> trim by policy before invoking;
- model call succeeds but usage is missing -> record usage as unavailable, not
  zero;
- compact result is stored by caller -> caller must store trace/fingerprint
  separately from business truth.

## 11. Tests Required For Implementation Owner

Setup dev session should cover the common kernel with tests equivalent to:

- deterministic fingerprint and reuse;
- incremental update from previous summary plus newly compacted items;
- strict schema validation and forbidden-field rejection;
- fallback summary on invalid model output;
- usage and trace reporting;
- stable prompt prefix not polluted by volatile source items;
- adapter-specific schema validation for setup compact and brainstorm summary;
- no business truth mutation from compact operation result.

Story runtime should add adapter tests when it implements consumers:

- writer packet uses branch-aware scoped inputs before compact;
- brainstorm summary output contains memory-agnostic items only;
- confirmed brainstorm items route to scheduler after user confirmation;
- chapter bridge summary stays Runtime Workspace sidecar.

## 12. Open Questions

No product-level grill is required before writing this spec. The remaining
questions are implementation ownership and extraction timing questions for the
setup agent dev session:

1. whether to extract the common kernel before or after setup context tests are
   stable;
2. whether to keep setup service names as wrappers around the common kernel for
   backward readability;
3. which token counter implementation should be the first shared dependency.
