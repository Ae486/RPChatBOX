# RP Active Story Block Prompt Context

## Scenario: Internal Block-Aware Compile for Orchestrator and Specialist

### 1. Scope / Trigger

- Trigger: after Core State Block envelope and active-story consumer registry exist, orchestrator/specialist need a real internal Block-backed compile input instead of only parallel legacy state/projection reads.
- Applies only to active-story internal agent compile for:
  - `story.orchestrator`
  - `story.specialist`
- This stage is internal only. It does not add a new public API route and does not change writer packet compilation.

### 2. Signatures

Models:

```python
class RpBlockPromptContextView(BaseModel):
    consumer_key: BlockConsumerKey
    session_id: str
    chapter_workspace_id: str | None = None
    dirty: bool
    dirty_reasons: list[str] = Field(default_factory=list)
    dirty_block_ids: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    authoritative_state: dict[str, Any] = Field(default_factory=dict)
    projection_state: dict[str, list[str]] = Field(default_factory=dict)
    attached_blocks: list[RpBlockView] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Service:

```python
class StoryBlockPromptContextService:
    def build_consumer_context(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockPromptContextView | None: ...
```

### 3. Contracts

- `StoryBlockPromptContextService` must build from:
  - `StoryBlockConsumerStateService.get_consumer(...)`
  - the Core State Block view owned by `RpBlockReadService`
- It must not re-query raw session/chapter JSON mirrors directly as its primary source.
- The compiled context must preserve raw attached Block payloads in `attached_blocks`.
- `attached_blocks` in this stage remain limited to the current Core State authoritative/projection attachment surface. Retrieval-backed and Runtime Workspace Block views may exist elsewhere in the repo, but they must not enter active-story internal prompt context through this service.
- The compiled context must also expose legacy-compatible migration views:
  - `authoritative_state`: keyed by current runtime-facing backend field names such as `chapter_digest`
  - `projection_state`: keyed by current settled projection slot names such as `current_outline_digest`
- Legacy-compatible state views are derived from existing binding maps:
  - authoritative via `memory_object_mapper`
  - projection via `memory_object_mapper` / settled projection slot mapping
- Unmapped future Blocks are allowed in `attached_blocks`, but they do not have to appear in `authoritative_state` or `projection_state`.
- `projection_state` should preserve the current settled slot shape for orchestrator/specialist compile, including empty slot lists when no attached Block exists for that slot.
- Orchestrator and specialist may fall back to existing business-facing state/projection services if the block prompt context service is absent or returns `None`.
- This stage does not:
  - replace `WritingPacketBuilder`
  - compile retrieval hits into Blocks
  - introduce automatic rebuild or fan-out
  - move setup runtime-private cognition into story Memory OS
  - create a durable `rp_blocks` table

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Valid session + known consumer | Return Block-backed prompt context with dirty metadata and attached Block payloads |
| Unknown consumer | Return `None` |
| Attached Block exists but has no legacy binding | Keep it in `attached_blocks`; omit it from legacy-compatible state maps |
| No projection Block exists for a settled slot | Keep the slot in `projection_state` with `[]` |
| Context service unavailable in orchestrator/specialist wiring | Services fall back to existing `AuthoritativeStateViewService` / `ProjectionStateService` |

### 5. Good / Base / Bad Cases

- Good: orchestrator compile receives `block_context` plus legacy-compatible `authoritative_state` / `projection_snapshot`, both derived from currently attached Core State Blocks.
- Good: specialist compile receives `block_context` plus legacy-compatible `projection_state`, while retrieval hits remain a separate input path.
- Good: Runtime Workspace `/memory/blocks` visibility may expose draft/discussion Blocks, while orchestrator/specialist `block_context` remains Core State-only.
- Base: `story.writer_packet` remains on deterministic packet assembly and is not moved to this internal compile abstraction.
- Bad: using this service to replace `WritingPacketBuilder`.
- Bad: compiling recall/archival storage into durable Block attachments in this stage.
- Bad: treating setup runtime-private cognition as attached story Blocks.

### 6. Tests Required

- Service compile:
  - asserts attached Blocks are preserved with raw `data_json` / `items_json`
  - asserts authoritative Blocks map back to legacy authoritative field names
  - asserts projection Blocks map back to settled projection slot names
  - asserts empty settled projection slots are still present in `projection_state`
  - asserts Runtime Workspace blocks are excluded from `attached_blocks`
- Orchestrator integration:
  - asserts LLM payload includes `block_context`
  - asserts orchestrator still receives legacy-compatible `authoritative_state` / `projection_snapshot`
- Specialist integration:
  - asserts LLM payload includes `block_context`
  - asserts retrieval hits remain separate from `block_context`
  - asserts writer packet path is unchanged

### 7. Design Note

This slice is the narrowed version of “Memory.compile” for active-story internal agents only. It is intentionally structured, Block-backed, and migration-friendly, but it stops before writer packet replacement, fan-out rebuild, or governed Block mutation.
