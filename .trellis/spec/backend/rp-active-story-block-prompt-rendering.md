# RP Active Story Block Prompt Rendering

## Scenario: Deterministic Block Overlay for Active-Story Internal Agents

### 1. Scope / Trigger

- Trigger: after orchestrator/specialist can compile a structured Block-backed prompt context, the internal compile still needs a deterministic rendered memory overlay similar to Letta-style memory injection.
- Applies only to active-story internal agent system prompts for:
  - `story.orchestrator`
  - `story.specialist`
- This stage is still internal-only. It does not change writer packet assembly and does not add a public API route.

### 2. Signatures

Service:

```python
class StoryBlockPromptRenderService:
    def render_prompt_overlay(
        self,
        *,
        context: RpBlockPromptContextView,
    ) -> str: ...
```

### 3. Contracts

- `render_prompt_overlay(...)` must render from `RpBlockPromptContextView`, not by re-reading raw stores itself.
- Render order must be deterministic:
  - sort attached Blocks by `(layer.value, label, block_id)`
- The overlay must include:
  - consumer identity
  - current chapter workspace id
  - dirty flag
  - dirty reasons
  - dirty block ids
  - one rendered section per attached Block
- Each rendered Block section must preserve exact Block identity metadata:
  - `block_id`
  - `label`
  - `layer`
  - `domain`
  - `domain_path`
  - `scope`
  - `revision`
  - `source`
- Authoritative payloads render from raw `data_json`.
- Projection payloads render from raw `items_json`.
- Rendering must be deterministic for dict payloads:
  - use stable JSON field order
- Orchestrator and specialist may append the rendered overlay to their system prompt while continuing to keep legacy-compatible state/projection maps in the user payload during migration.
- This stage does not:
  - replace `WritingPacketBuilder`
  - render retrieval hits into Block sections
  - mutate consumer sync state
  - introduce fan-out or rebuild triggers

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Empty attached Block list | Render overlay header with zero blocks, no fake placeholder Blocks |
| Attached authoritative Block | Render raw `data_json` as deterministic JSON |
| Attached projection Block | Render raw `items_json` as deterministic JSON array |
| Dirty context | Render dirty metadata in the overlay header |
| Clean context | Render `dirty=false` and empty or current dirty lists accordingly |

### 5. Good / Base / Bad Cases

- Good: orchestrator system prompt includes a deterministic Block overlay and user payload still carries `authoritative_state` / `projection_snapshot`.
- Good: specialist system prompt includes the same deterministic Block overlay while retrieval hits remain a separate user-payload field.
- Base: writer packet build still consumes settled projection sections and runtime hints only.
- Bad: replacing writer packet system/context sections with this overlay.
- Bad: flattening retrieval results into fake attached Blocks in this stage.

### 6. Tests Required

- Render service:
  - asserts deterministic ordering by layer/label/block id
  - asserts authoritative payload renders as JSON object text
  - asserts projection payload renders as JSON array text
  - asserts dirty metadata appears in the rendered header
- Orchestrator integration:
  - asserts system prompt contains rendered Block overlay markers and expected block labels
- Specialist integration:
  - asserts system prompt contains rendered Block overlay markers and expected block labels
  - asserts retrieval hits remain in the user payload rather than the overlay

### 7. Design Note

This slice is the first actual Block-to-prompt rendering step for active-story internals. It stays below `WritingPacketBuilder`, keeps retrieval separate, and makes the current Block compile path concrete without yet introducing prompt caching or fan-out rebuild.
