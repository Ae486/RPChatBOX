# RP Active Story Block Lazy Rebuild

## Scenario: Cached Internal Block Prompt Compile with Lazy Rebuild

### 1. Scope / Trigger

- Trigger: after orchestrator/specialist already have a structured Block-backed prompt context and deterministic overlay, the runtime needs a stable lazy rebuild policy instead of re-rendering the overlay on every call.
- Applies only to active-story internal agent compile for:
  - `story.orchestrator`
  - `story.specialist`
- This stage is still internal-only. It does not change writer packet assembly and does not add a public API route.

### 2. Signatures

Models:

```python
BlockPromptCompileMode = Literal["rebuilt", "reused"]


class RpBlockPromptCompileView(BaseModel):
    context: RpBlockPromptContextView
    prompt_overlay: str
    compile_mode: BlockPromptCompileMode
    compile_reasons: list[str] = Field(default_factory=list)
    compiled_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Service:

```python
class StoryBlockPromptCompileService:
    def compile_consumer_prompt(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockPromptCompileView | None: ...
```

Persisted cache fields on `StoryBlockConsumerStateRecord`:

```python
last_compiled_revisions_json: dict[str, int]
last_compiled_chapter_workspace_id: str | None
last_compiled_prompt_overlay: str | None
last_compiled_at: datetime | None
```

### 3. Contracts

- `StoryBlockPromptCompileService` must compose from:
  - `StoryBlockPromptContextService.build_consumer_context(...)`
  - `StoryBlockPromptRenderService.render_prompt_overlay(...)`
  - `StoryBlockConsumerStateRecord` compile-cache fields
- It must not bypass current Block read / consumer / prompt-context services by re-querying raw session or chapter mirrors directly.
- Compile cache is consumer-scoped and stores only the last compiled Block snapshot + rendered overlay. It does not become a new truth source.
- Reuse is allowed only when all of the following are still true:
  - current attached Block revision map equals `last_compiled_revisions_json`
  - current `chapter_workspace_id` equals `last_compiled_chapter_workspace_id`
  - cached overlay exists
  - the cached overlay is not older than the latest consumer sync snapshot that would change dirty-header rendering
- Because the overlay header renders `dirty`, `dirty_reasons`, and `dirty_block_ids`, a consumer sync-state change may require rebuild even when attached Block revisions did not change.
- Rebuild reason codes for this stage are:
  - `never_compiled`
  - `compiled_block_revision_changed`
  - `compiled_block_detached`
  - `compiled_chapter_workspace_changed`
  - `cached_overlay_missing`
  - `consumer_sync_state_changed`
- Compile service must return the current structured `context` every time, even when the rendered overlay is reused from cache.
- Changes that only affect non-attached layers such as Runtime Workspace draft/discussion Blocks must not invalidate the compile cache for orchestrator/specialist in this stage.
- Orchestrator and specialist may prefer this compile service over direct context + render calls, while still falling back to existing authoritative/projection services if the Block compile path is unavailable.
- This stage does not:
  - replace `WritingPacketBuilder`
  - add eager fan-out or write-time rebuild triggers
  - attach setup runtime-private cognition to story Memory OS
  - create a durable `rp_blocks` table

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Valid session + orchestrator/specialist consumer with no compile cache | Return `compile_mode="rebuilt"` and include `never_compiled` |
| Same Block snapshot + same consumer sync state | Return `compile_mode="reused"` and reuse cached overlay |
| Attached Block revision differs from compiled snapshot | Return `compile_mode="rebuilt"` and include `compiled_block_revision_changed` |
| Previously compiled Block is no longer attached | Return `compile_mode="rebuilt"` and include `compiled_block_detached` |
| Current chapter workspace differs from compiled snapshot | Return `compile_mode="rebuilt"` and include `compiled_chapter_workspace_changed` |
| Cached overlay is absent while compiled snapshot exists | Return `compile_mode="rebuilt"` and include `cached_overlay_missing` |
| Consumer sync snapshot changed after the last compile | Return `compile_mode="rebuilt"` and include `consumer_sync_state_changed` |
| `story.writer_packet` is routed here | Return `None`; writer packet stays on deterministic packet build |

### 5. Good / Base / Bad Cases

- Good: orchestrator compiles once for the current Block snapshot, then reuses the cached overlay on later calls while the Block snapshot and sync state stay unchanged.
- Good: after a successful consume updates consumer sync state, the next compile rebuilds once so the overlay header no longer advertises stale `dirty=true`.
- Good: after an authoritative or projection Block revision changes, the next compile rebuilds and persists the new overlay.
- Good: adding or updating Runtime Workspace draft/discussion Blocks does not force rebuild because they are not attached to the compile context.
- Base: the structured `context` is still rebuilt from current Blocks even when the overlay string is reused from cache.
- Bad: treating compile cache as a new authoritative store.
- Bad: letting writer packet adopt this cache path and bypass `WritingPacketBuilder`.
- Bad: keying rebuild directly off `SetupWorkspace` changes instead of current active-story Block snapshot / consumer sync state.

### 6. Tests Required

- Compile service:
  - asserts first compile is `rebuilt`
  - asserts repeated compile with unchanged snapshot is `reused`
  - asserts authoritative/projection revision changes force rebuild
  - asserts chapter workspace changes force rebuild
  - asserts consumer sync state change forces rebuild so dirty header is refreshed
  - asserts Runtime Workspace-only changes keep the overlay reusable
- Consumer state regression:
  - asserts `mark_consumer_synced(...)` is idempotent when the synced snapshot is unchanged, so compile cache can remain reusable
- Orchestrator / specialist integration:
  - asserts they still include `block_context`
  - asserts they append the cached-or-rebuilt overlay through the compile service
  - asserts fallback to legacy state/projection services remains available when Block compile is absent

### 7. Design Note

This slice is the narrowed version of Letta-style lazy rebuild for the current RP active-story internals. It reuses the current Block envelope and consumer registry, but keeps rebuild policy tied to active durable state plus consumer sync state, not to setup workspace edits or a new universal Block storage layer.
