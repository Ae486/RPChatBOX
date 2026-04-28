# RP Story Segment Accept Metadata Promotion

## Scenario: ACCEPT_PENDING_SEGMENT can promote or override whitelisted structured metadata families on the accepted story segment without creating a new truth-write path

### 1. Scope / Trigger

- Trigger: draft `story_segment` artifacts now have a typed structured metadata sidecar path, but the repo still lacks a stable, review-adjacent producer surface for accepted-segment metadata.
- Applies to RP backend implementation across:
  - `LongformTurnRequest` request contract for story turns;
  - story turn API / graph request propagation;
  - `StoryTurnDomainService.accept_pending_segment(...)`;
  - `StorySessionService.update_artifact(...)` metadata updates on accepted story segments;
  - focused request-validation / accept-flow / chapter-close integration tests.
- This slice does **not** change `WritingWorkerExecutionService` text-only behavior.
- This slice does **not** make artifact metadata itself authoritative truth.
- This slice does **not** add a new mutation surface outside accepted `StoryArtifact.metadata` and the existing chapter-close proposal/apply consumer path.

### 2. Signatures / Surfaces

Turn request surface:

```python
class LongformTurnRequest(BaseModel):
    ...
    story_segment_metadata_patch: StorySegmentStructuredMetadata | None = None
```

Accept request example:

```json
{
  "session_id": "session_123",
  "command_kind": "accept_pending_segment",
  "model_id": "model-story",
  "target_artifact_id": "artifact_pending_123",
  "story_segment_metadata_patch": {
    "foreshadow_status_updates": [
      {
        "foreshadow_id": "envoy_debt",
        "status": "resolved",
        "summary": "bell tower debt",
        "resolution": "Settled at the river gate."
      }
    ]
  }
}
```

Accepted artifact surface after promotion:

```python
StoryArtifact.metadata = {
    "command_kind": "write_next_segment",
    "packet_id": "packet_123",
    "writer_hints": ["keep tension immediate"],
    "foreshadow_status_updates": [
        {
            "foreshadow_id": "envoy_debt",
            "status": "resolved",
            "summary": "bell tower debt",
            "resolution": "Settled at the river gate.",
        }
    ],
}
```

### 3. Contracts

- Producer ownership:
  - `ACCEPT_PENDING_SEGMENT` becomes the stable, review-adjacent producer surface for accepted `story_segment` structured metadata in this slice;
  - draft specialist-authored metadata remains allowed, but an accept-time patch may replace managed families before the segment becomes accepted history input.
- Command scope:
  - `story_segment_metadata_patch` is only valid on `LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT`;
  - sending that field on any other command must fail with a story-turn validation error rather than silently ignoring the payload.
- Narrow family scope:
  - this slice only promotes or overrides the already-frozen `foreshadow_status_updates` family;
  - unsupported top-level structured families must be ignored during normalization and must not widen the accepted artifact metadata schema.
- Merge semantics:
  - runtime-authored base metadata keys (`command_kind`, `packet_id`, `writer_hints`) remain preserved on the accepted artifact;
  - if `story_segment_metadata_patch` is omitted, accept preserves the existing draft family unchanged;
  - if `story_segment_metadata_patch` is provided, the normalized patch becomes the source of truth for managed families on the accepted artifact;
  - if a managed family normalizes to empty during accept-time patching, the accepted artifact must drop that family instead of preserving stale draft values.
- Boundary rules:
  - promoted accepted-segment metadata is still only artifact metadata; authoritative truth remains downstream at chapter close via proposal/apply;
  - this slice must not infer metadata from writer prose;
  - this slice must not change light/heavy regression semantics except by changing what accepted metadata the downstream consumer reads.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `story_segment_metadata_patch` omitted on accept | Preserve the existing draft managed family unchanged |
| `story_segment_metadata_patch` provided on `accept_pending_segment` | Normalize and replace managed family values on the accepted artifact |
| Patch family normalizes to empty | Remove that managed family from accepted artifact metadata |
| Patch contains unsupported top-level family | Ignore it |
| Patch is sent on `write_next_segment`, `rewrite_pending_segment`, `accept_outline`, or `complete_chapter` | Reject the turn with validation failure |
| No pending segment exists | Existing accept error remains unchanged |
| Chapter close later reads the accepted artifact | Existing downstream consumer sees the promoted accepted metadata with no new inference path |

### 5. Good / Base / Bad Cases

- Good: draft segment has no `foreshadow_status_updates`; accept request supplies a typed patch, and the accepted artifact now carries that family for chapter close.
- Good: draft segment has speculative `foreshadow_status_updates`, but accept request supplies a corrected patch; accepted artifact uses the accept-time value.
- Good: accept request supplies an empty `foreshadow_status_updates` list to clear stale draft metadata before acceptance.
- Base: accept request omits the patch; accepted artifact keeps the existing draft family unchanged.
- Bad: send `story_segment_metadata_patch` on `write_next_segment` and hope runtime silently drops it.
- Bad: parse writer prose at accept time and synthesize `foreshadow_status_updates` from text.

### 6. Tests Required

- Request / validation tests:
  - non-accept commands with `story_segment_metadata_patch` fail explicitly;
  - `accept_pending_segment` accepts the typed patch shape.
- Accept-flow tests:
  - accept without patch preserves the draft managed family;
  - accept with patch replaces the managed family on the accepted artifact;
  - accept with empty normalized patch clears stale managed family.
- Integration tests:
  - accept-time-promoted metadata is later consumed unchanged by chapter-close fallback to produce authoritative `foreshadow_registry` updates.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: silently ignore accept-time metadata patches on unrelated commands.
if request.story_segment_metadata_patch:
    pass
```

#### Correct

```python
# Correct: only ACCEPT_PENDING_SEGMENT may consume the patch, and accept-time
# normalized values replace the managed family on the accepted artifact.
if request.command_kind == LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT:
    next_metadata = _apply_story_segment_metadata_patch(
        artifact.metadata,
        request.story_segment_metadata_patch,
    )
```

## Status on 2026-04-28

- This spec creates a stable producer surface closer to reviewed segment content than pre-write specialist output alone.
- The slice stays narrow: one optional request field, one whitelisted family, no new truth-write path, and no prose inference.
