# RP Story Brainstorm Product Loop

## Scenario: Writer Brainstorm Batch Front Half

### 1. Scope / Trigger

- Trigger: add or edit writer brainstorm APIs, `StoryBrainstormService`, `BrainstormSession` models, `LongformStoryPage` brainstorm UI, writer packet assembly, or the later scheduler consumer for brainstorm batches.
- Applies to story-runtime writer brainstorm, not SetupAgent discussion memory.
- Brainstorm is a discussion persona plus editable intent form producer. It is not a Memory worker, Core editor, Recall writer, Archival editor, scheduler, or story prose writer.
- The front-half contract ends when a user submits a batch and active items become `pending_processing`.
- W5 and later may consume `pending_processing` batches/items, but must not reinterpret deleted or draft items as actionable work.
- W5 and later must treat the scheduler/worker path as Core-oriented Memory OS
  governance: Core owner workers may retrieve Recall / Archival evidence, but
  Recall / Archival are not brainstorm-dispatch mutation targets.

### 2. Signatures

Backend APIs:

```text
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions
GET  /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/messages
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/summarize
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/continue-writing
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/batches/{batch_id}/items
PATCH /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/batches/{batch_id}/items/{item_id}
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/batches/{batch_id}/submit
```

Core model fields:

```python
class BrainstormSummarizeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[str] = Field(default_factory=list, max_length=12)

class BrainstormContextWindow(BaseModel):
    window_id: str
    brainstorm_id: str
    session_id: str
    branch_head_id: str
    turn_id: str | None
    runtime_profile_snapshot_id: str | None
    status: Literal["active", "flushed"]
    flush_reason: Literal["summarize", "continue_writing"] | None = None
    flushed_at: datetime | None = None
    source_message_refs: list[str] = Field(default_factory=list)
    messages: list[BrainstormMessage] = Field(default_factory=list)

class BrainstormBatch(BaseModel):
    status: Literal["draft", "pending_processing", "completed", "failed", "conflict"]
    frozen: bool
    items: list[BrainstormBatchItem]

class BrainstormBatchItem(BaseModel):
    text: str
    source_kind: Literal["summarized", "user_added"]
    status: Literal["active", "deleted", "pending_processing", "completed", "failed", "conflict"]
```

### 3. Contracts

- All brainstorm models carry full `MemoryRuntimeIdentity`: `story_id`, `session_id`, `branch_head_id`, `turn_id`, and `runtime_profile_snapshot_id`.
- Brainstorm discussion messages live in brainstorm Runtime Workspace scratch, not in general writer `StoryDiscussionEntry` recent-turn input.
- `summarize` reads only the current active brainstorm window plus branch-visible writer snapshot prepared by backend context code.
- `summarize` creates exactly one draft batch, creates active items from `items: list[str]`, and flushes the current active window.
- `continue-writing` flushes the current active window without creating a batch.
- After a flush, the next brainstorm discussion must create or use a new active window; flushed raw discussion is historical/debug material only.
- Batch submit changes the batch from `draft` to `pending_processing`, freezes it, and changes only active items to `pending_processing`.
- Deleted items remain visible in the batch history but are excluded from `submitted_item_ids` and from any later scheduler/worker dispatch.
- Submit response uses `brainstorm_batch_submit`, not `brainstorm_summary_apply`, `pending_review`, `confirmed`, or `dispatched`.
- W1-W4 submit does not create `RuntimeWorkflowJobRecord`, worker candidate material, proposal/apply receipt, Core mutation, Recall materialization, Archival evolution, memory event, or projection refresh.
- Writer packet/context builders must fail closed and exclude active/flushed brainstorm raw discussion, draft batches, deleted items, pending batches/items, and any brainstorm intent not yet governed by W5 or later.

### 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Identity session/story mismatches route session | Reject with brainstorm identity mismatch error |
| No active window on summarize | Reject with `brainstorm_summarize_no_active_window` |
| Empty active window on summarize | Reject with `brainstorm_summarize_window_empty` |
| LLM output contains objects/routing/patch fields instead of strings | Reject with `brainstorm_summarize_invalid_output` |
| Batch not found | Reject with `brainstorm_batch_not_found` |
| Item not found | Reject with `brainstorm_item_not_found` |
| Edit/add/delete/restore on frozen or non-draft batch | Reject with `brainstorm_batch_frozen` |
| Text edit on deleted item | Reject with `brainstorm_deleted_item_read_only` |
| Submit with zero active items | Reject with `brainstorm_batch_submit_empty` |
| Deleted item exists during submit | Keep deleted and exclude from submitted item ids |
| Frontend tries old `/apply` path for W1-W4 | Treat as product-path regression |

### 5. Good / Base / Bad Cases

- Good: user discusses intent, clicks summarize, edits items, deletes one item, submits the batch; only active items become `pending_processing`, deleted items remain deleted, no scheduler job exists yet.
- Base: user discusses intent and clicks continue-writing; the active window is flushed, no batch appears, and later brainstorm input starts from writer snapshot plus a new active brainstorm window.
- Bad: model emits `{items: [{target_layer: "core", field_path: "..."}]}`; backend rejects it instead of silently dropping routing fields.
- Bad: writer generation packet includes a brainstorm item or raw brainstorm message after summarize/continue flush; packet builder tests must fail.
- Bad: W5 scheduler consumes deleted, draft, or still-editable items; W5 must consume only active-submitted `pending_processing` items.

### 6. Tests Required

- Service tests:
  - discuss appends user/assistant messages to active window.
  - summarize creates one draft batch and flushes the window.
  - continue-writing flushes without creating a batch and next discussion uses a new active window.
  - user-added item is active and participates in submit.
  - deleted item is restorable while batch is draft.
  - deleted item is read-only and excluded from submit.
  - empty submit fails closed.
  - frozen batch rejects edit/add/delete/restore.
  - submit does not create scheduler job, proposal/apply receipt, memory event, or mutation.
- API tests:
  - all brainstorm routes preserve route/session/identity matching.
  - batch submit returns `pending_processing` and `brainstorm_batch_submit`.
  - old `/apply` is not used by W1-W4 frontend product path.
- Packet tests:
  - writer packet excludes brainstorm raw discussion, draft batch text, deleted item text, and pending item text.
  - read manifest selected refs do not point at brainstorm scratch.
- Frontend checks:
  - always-visible entry shows empty state and aggregate counts.
  - dialog supports edit/add/delete/restore and freezes submitted batches.
  - submit button is disabled when active item count is zero.
  - success/error feedback uses `OwuiSnackBars`.

### 7. Wrong vs Correct

#### Wrong

```python
# Treating a user-reviewed brainstorm batch as an apply request.
await brainstorm_service.apply_session(
    brainstorm_id=brainstorm_id,
    request=BrainstormApplyRequest(
        identity=identity,
        item_ids=confirmed_item_ids,
        core_field_changes=[...],
    ),
)
```

Why it is wrong:

- It reintroduces legacy `confirmed` / `brainstorm_summary_apply` semantics.
- It lets brainstorm decide routing and patch fields.
- It bypasses the W5 scheduler/worker boundary.

#### Correct

```python
session, receipt = brainstorm_service.submit_batch(
    brainstorm_id=brainstorm_id,
    batch_id=batch_id,
    request=BrainstormBatchSubmitRequest(identity=identity, actor=actor),
)
assert receipt.status == "pending_processing"
assert deleted_item_id not in receipt.submitted_item_ids
```

Why it is correct:

- Brainstorm only freezes reviewed user intents.
- Later scheduler/worker logic owns routing, permission checks, governed mutation, and conflict handling.
- Deleted and draft items remain non-actionable.

## W5 Consumer Boundary

W5 may introduce the first real consumer for `pending_processing` brainstorm batches/items. That consumer must:

- read only frozen `pending_processing` batches and their `pending_processing` items;
- ignore `deleted`, `draft`, `active`, `failed`, `completed`, and `conflict` items unless the W5 spec explicitly defines a retry/recovery path;
- preserve the original brainstorm item text as user intent, not as executable patch;
- route through existing scheduler/worker/governance contracts instead of direct writes;
- dispatch work to Core domain owner workers, not to separate Recall/Archival layer writers;
- allow those Core workers to call Retrieval Broker / retrieval tools for Recall or Archival evidence when the user intent needs historical or long-term source material;
- treat Recall / Archival hits as evidence only until a governed Core mutation makes the fact current truth;
- leave Recall lifecycle actions and Archival Story Evolution / ingestion / reindex outside the brainstorm batch consumer unless a future spec explicitly adds a separate product path;
- write explicit receipts/results back to brainstorm state so the UI can distinguish completed, failed, and conflict outcomes;
- keep writer context exclusion in force until the governed memory mutation is actually visible through canonical memory/projection/read-manifest paths.

Do not phrase W5 scope as "which memory layers should the worker process".
The worker manages Core State and current projections; Recall / Archival are
read/search sources used through tools.
