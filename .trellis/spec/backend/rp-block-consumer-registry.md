# RP Block Consumer Registry

## Scenario: Session-Scoped Active-Story Block Consumers with Lazy Dirty

### 1. Scope / Trigger

- Trigger: RP Memory OS needs a stable bridge between read-only Block envelopes and active-story consumers without replacing current business builders.
- Applies to active-story consumers that read Core State Block envelopes during the story turn pipeline.
- This spec is not a generic fan-out system yet. It only adds:
  - session-scoped consumer snapshots
  - lazy dirty evaluation from Block revisions
  - read-only visibility of current attachments/dirty state

### 2. Signatures

Consumer key:

```python
BlockConsumerKey = Literal[
    "story.orchestrator",
    "story.specialist",
    "story.writer_packet",
]
```

Models:

```python
class RpBlockConsumerAttachmentView(BaseModel):
    block_id: str
    label: str
    layer: Layer
    domain: Domain
    domain_path: str
    scope: str
    revision: int
    source: BlockSource


class RpBlockConsumerStateView(BaseModel):
    consumer_key: BlockConsumerKey
    session_id: str
    chapter_workspace_id: str | None = None
    dirty: bool
    dirty_reasons: list[str] = Field(default_factory=list)
    dirty_block_ids: list[str] = Field(default_factory=list)
    attached_blocks: list[RpBlockConsumerAttachmentView] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Service:

```python
class StoryBlockConsumerStateService:
    def list_consumers(
        self,
        *,
        session_id: str,
    ) -> list[RpBlockConsumerStateView]: ...

    def get_consumer(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockConsumerStateView | None: ...

    def mark_consumer_synced(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockConsumerStateView | None: ...
```

API:

```http
GET /api/rp/story-sessions/{session_id}/memory/block-consumers
GET /api/rp/story-sessions/{session_id}/memory/block-consumers/{consumer_key}
```

List response:

```python
{
    "session_id": str,
    "items": list[RpBlockConsumerStateView],
}
```

Single response:

```python
{
    "session_id": str,
    "item": RpBlockConsumerStateView,
}
```

### 3. Contracts

- This stage still does not create a durable `rp_blocks` table.
- A new lightweight consumer snapshot table is allowed for active-story runtime bookkeeping. It stores last-synced Block revisions per consumer and does not become a new truth source.
- Consumer attachment resolution must always derive from the Core State view owned by `RpBlockReadService`, not by re-querying raw Core State tables or compatibility mirrors directly.
- Default consumer set for this stage is fixed:
  - `story.orchestrator`
  - `story.specialist`
  - `story.writer_packet`
- Default attachment rules must reflect current code reality:
  - `story.orchestrator` attaches all current authoritative and projection **Core State** Block envelopes visible in the session.
  - `story.specialist` attaches all current authoritative and projection **Core State** Block envelopes visible in the session.
  - `story.writer_packet` attaches only projection Block envelopes that currently have non-empty `items_json`, because `WritingPacketBuilder` only consumes emitted context sections.
- Dirty evaluation is lazy. It is computed by comparing current attached Block identities/revisions against the persisted last-synced snapshot for the consumer.
- This stage does not introduce write-time rebuild triggers, event fan-out, or automatic prompt recompilation.
- `mark_consumer_synced(...)` is allowed only after the corresponding consumer has actually consumed current inputs in the active-story flow.
- `story.writer_packet` remains a tracked consumer, but the registry must not replace `WritingPacketBuilder`, inject raw authoritative Blocks into the writer, or flatten writer packet business structure into generic Memory compilation.
- Dirty tracking in this stage covers only Block-backed inputs plus current `chapter_workspace_id` for chapter-scoped consumers.
- Dirty tracking in this stage explicitly does not cover:
  - setup runtime-private cognition
  - retrieval hits / recall hits / archival hits
  - Runtime Workspace draft artifacts or discussion entries
  - writer hints
  - user prompt
  - accepted outline / pending artifact / target artifact
  - writer contract or other non-Block business inputs
- Setup runtime-private cognition stays outside this registry.
- Unknown `consumer_key` must not silently fall back to a default consumer.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Unknown `session_id` in service | Raise the same session-not-found boundary as other story runtime memory reads |
| Unknown API `session_id` | Return HTTP 404 with `story_session_not_found` |
| Unknown API `consumer_key` for an existing session | Return HTTP 404 with `memory_block_consumer_not_found` |
| Consumer has never been synced | Return `dirty=True` with `dirty_reasons=["never_synced"]` |
| Current chapter workspace differs from stored snapshot | Return `dirty=True` and include `chapter_workspace_changed` in `dirty_reasons` |
| Attached Block revision differs from last-synced snapshot | Return `dirty=True` and include `block_revision_changed` in `dirty_reasons` |
| Previously synced Block is no longer attached | Return `dirty=True` and include `block_detached` in `dirty_reasons` |
| `mark_consumer_synced(...)` is called for a valid consumer | Persist current attached Block revisions and clear dirty state |
| `story.writer_packet` attachments are requested | Return only non-empty projection Blocks |

### 5. Good / Base / Bad Cases

- Good: `story.orchestrator` reads the current session's authoritative + projection Block envelopes, then `mark_consumer_synced(...)` stores the revisions it actually consumed.
- Good: after an authoritative Block revision changes, `story.orchestrator` and `story.specialist` become dirty while `story.writer_packet` stays clean if no projection Block changed.
- Good: after a projection Block changes from empty to non-empty, `story.writer_packet` becomes dirty because a new attached Block has appeared in the emitted packet context.
- Base: before any consumer has synced, the visibility API shows the fixed default consumer set with `dirty=True`.
- Bad: storing consumer dirty state inside `runtime_story_config_json`, which is product/runtime configuration rather than internal consumer bookkeeping.
- Bad: using this registry to replace `WritingPacketBuilder`.
- Bad: pulling setup runtime-private cognition into the active-story consumer registry.
- Bad: pretending retrieval hits are durable attached Blocks in this stage.
- Bad: letting Runtime Workspace Block views dirty orchestrator/specialist attachments after `/memory/blocks` expands beyond Core State.

### 6. Tests Required

- Service defaults:
  - asserts the fixed consumer set exists for a valid session
  - asserts unsynced consumers start dirty
  - asserts writer-packet attachments only include non-empty projection Blocks
- Dirty semantics:
  - asserts `mark_consumer_synced(...)` clears dirty state
  - asserts authoritative revision changes dirty orchestrator/specialist without dirtying writer-packet when projection inputs are unchanged
  - asserts projection changes dirty writer-packet
  - asserts Runtime Workspace block changes do not dirty orchestrator/specialist or appear in their attachments
  - asserts chapter workspace changes dirty chapter-scoped consumers
- Story turn integration:
  - asserts orchestrator path marks `story.orchestrator` synced after planning
  - asserts specialist path marks `story.specialist` synced after analysis
  - asserts packet build path marks `story.writer_packet` synced after packet assembly
- API visibility:
  - asserts list/single routes return serialized consumer states
  - asserts missing session returns `story_session_not_found`
  - asserts missing consumer returns `memory_block_consumer_not_found`

### 7. Design Note

This slice borrows from Letta's Block attachment / prompt-affecting-change thinking, but intentionally stops at lazy dirty + visibility. Automatic rebuild fan-out can be layered later once the consumer registry contract is proven against current RP business boundaries.
