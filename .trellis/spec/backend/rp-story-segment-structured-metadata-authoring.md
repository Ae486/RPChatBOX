# RP Story Segment Structured Metadata Authoring

## Scenario: Specialist-owned structured maintenance metadata is persisted on draft story segments without changing writer or authoritative-write boundaries

### 1. Scope / Trigger

- Trigger: chapter-close foreshadow terminal snapshot production now consumes explicit accepted-segment metadata, but the repo still lacks a stable upstream contract for who authors that metadata and when it is persisted.
- Applies to RP backend implementation across:
  - `SpecialistResultBundle` as the structured sidecar returned by `LongformSpecialistService.analyze(...)`;
  - draft `StoryArtifact.metadata` for `StoryArtifactKind.STORY_SEGMENT`;
  - `StoryTurnDomainService._persist_generated_artifact_impl(...)`;
  - the current specialist -> writer -> artifact persistence path for `WRITE_NEXT_SEGMENT` and `REWRITE_PENDING_SEGMENT`;
  - focused bundle-schema / artifact-persistence / chapter-close integration tests.
- This slice does **not** change `WritingWorkerExecutionService.run(...)` text-only output.
- This slice does **not** make `summary_updates[]`, writer prose, Runtime Workspace discussion, or retrieval hits into authoritative truth.
- This slice does **not** add a new public memory tool, new durable store, or generic artifact-mutation API.

### 2. Signatures / Surfaces

Specialist bundle sidecar:

```python
class SpecialistResultBundle(BaseModel):
    ...
    story_segment_metadata: StorySegmentStructuredMetadata = Field(
        default_factory=StorySegmentStructuredMetadata
    )
```

Typed sidecar family in this slice:

```python
class StorySegmentStructuredMetadata(BaseModel):
    foreshadow_status_updates: list[ForeshadowStatusUpdateMetadata] = Field(
        default_factory=list
    )
```

Schema surface requirement:

```python
SpecialistResultBundle.model_json_schema()["$defs"]["StorySegmentStructuredMetadata"][
    "properties"
]["foreshadow_status_updates"]["items"]["$ref"] == (
    "#/$defs/ForeshadowStatusUpdateMetadata"
)
```

Persisted artifact surface:

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

Downstream consumer that remains unchanged:

```python
LongformSpecialistService._fallback_bundle(... COMPLETE_CHAPTER ...)
-> _build_terminal_foreshadow_patch(...)
-> state_patch_proposals["foreshadow_registry"]
-> existing proposal/apply path
```

### 3. Contracts

- Producer ownership:
  - structured maintenance metadata for `story_segment` artifacts is authored by the specialist sidecar, not by writer prose and not by Recall ingestion;
  - in this slice the only stable upstream output surface is `SpecialistResultBundle.story_segment_metadata`;
  - `WRITE_NEXT_SEGMENT` and `REWRITE_PENDING_SEGMENT` are the only turns that may author this sidecar.
- Persistence timing:
  - the sidecar is normalized and persisted when a new draft `StoryArtifactKind.STORY_SEGMENT` artifact is created;
  - `ACCEPT_PENDING_SEGMENT` preserves already-persisted metadata by default, but a later accept-time promotion slice may replace managed families through an explicit typed patch;
  - `COMPLETE_CHAPTER` is a downstream consumer of accepted-segment metadata, not the authoring step.
- Narrow family scope:
  - this slice only freezes the `foreshadow_status_updates` family;
  - no generic free-form top-level metadata families are introduced in this slice;
  - unsupported top-level structured families are dropped at the persistence boundary.
- `foreshadow_status_updates` shape:
  - must serialize as a list;
  - only `dict` items are eligible;
  - require non-blank `foreshadow_id`;
  - `status` and `state` remain explicit structured fields; terminal interpretation is deferred to the downstream chapter-close consumer contract;
  - optional explanatory fields such as `summary`, `title`, `description`, and `resolution` may pass through when non-blank.
- Normalization rules:
  - runtime-authored artifact metadata keys (`command_kind`, `packet_id`, `writer_hints`) remain the base metadata and must not be removed by the sidecar;
  - within one `foreshadow_status_updates` list, later item wins for the same `foreshadow_id`;
  - blank strings normalize away;
  - entries that become empty after normalization are dropped;
  - if no valid `foreshadow_status_updates` remain, the persisted artifact omits that key.
- Boundary rules:
  - `story_segment_metadata` is durable artifact sidecar metadata, not an authoritative mutation proposal;
  - authoritative truth still flows only through `state_patch_proposals -> proposal/apply`;
  - `writer_hints[]` remain packet guidance only and must not be reclassified as durable metadata;
  - writer output text must stay prose-only and must not embed control DSL that runtime later parses.
- Failure behavior:
  - malformed or unsupported structured metadata must degrade by dropping the invalid sidecar portion rather than failing the whole write turn;
  - typed bundle validation must keep that degradation behavior by normalizing raw list input before item-level validation;
  - fallback specialist bundles for accept/complete remain allowed to return an empty sidecar.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `story_segment_metadata` omitted or empty | Persist only runtime-authored base metadata |
| Output artifact is not `story_segment` | Ignore `story_segment_metadata` in this slice |
| `foreshadow_status_updates` is not a list | Drop the family from persisted metadata |
| List item is not a dict | Skip that item |
| `foreshadow_id` is blank after normalization | Skip that item |
| Same `foreshadow_id` appears multiple times in one sidecar | Persist only the last normalized item |
| Optional fields are blank strings | Drop those fields from the persisted item |
| Specialist returns unsupported top-level structured family | Drop it at persistence; do not widen artifact schema silently |
| Accept pending segment after draft persistence with no patch | Preserve the persisted metadata unchanged |
| Accept pending segment after draft persistence with an explicit typed patch | Hand off to the accept-time promotion contract for managed-family replacement |
| Complete chapter later reads the accepted segment | Existing downstream consumer sees the normalized persisted metadata without any new inference path |

### 5. Good / Base / Bad Cases

- Good: specialist returns `story_segment_metadata.foreshadow_status_updates=[{"foreshadow_id": "envoy_debt", "status": "resolved"}]`; the draft segment persists that metadata, accept preserves it, and chapter close later promotes it through the existing append-only `foreshadow_registry` path.
- Good: specialist returns two updates for the same `foreshadow_id`; only the later normalized update persists on the artifact.
- Base: specialist returns no sidecar metadata; story segment persists only `command_kind`, `packet_id`, and `writer_hints`.
- Bad: writer prose contains “the debt is resolved” and runtime tries to infer `foreshadow_status_updates` from text.
- Bad: `summary_updates[]` are copied into artifact metadata and later treated as authoritative foreshadow input.
- Bad: `COMPLETE_CHAPTER` authors new segment metadata instead of consuming accepted-segment metadata.

### 6. Tests Required

- Bundle / schema tests:
  - specialist JSON schema accepts a typed `story_segment_metadata.foreshadow_status_updates` payload;
  - schema must expose `foreshadow_status_updates.items -> ForeshadowStatusUpdateMetadata`, not generic `object[]`;
  - malformed structured metadata degrades by dropping invalid entries rather than failing the whole write turn.
- Persistence tests:
  - `WRITE_NEXT_SEGMENT` persists normalized `foreshadow_status_updates` onto the draft story segment together with runtime-authored base metadata;
  - `ACCEPT_PENDING_SEGMENT` preserves the stored metadata unchanged.
- Integration tests:
  - real write -> accept -> complete chapter flow proves persisted segment metadata is later consumed by chapter-close fallback to produce authoritative `foreshadow_registry` updates.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: let writer prose become the metadata producer.
if "debt settled" in generated_text.lower():
    artifact_metadata["foreshadow_status_updates"] = [
        {"foreshadow_id": "envoy_debt", "status": "resolved"}
    ]
```

#### Correct

```python
# Correct: only specialist-authored structured sidecar metadata is persisted.
artifact_metadata = {
    "command_kind": request.command_kind.value,
    "packet_id": packet.packet_id,
    "writer_hints": specialist_bundle.writer_hints,
    **normalized_story_segment_metadata,
}
```

## Status on 2026-04-28

- This spec freezes the missing upstream contract behind `foreshadow_status_updates`.
- The next implementation slice should add a typed specialist sidecar and persistence normalization before attempting any broader “smart metadata authoring”.
- Writer, proposal/apply, Recall ingestion, and public memory tool boundaries stay unchanged.
- `trellis-check` later caught one concrete drift that is now part of the contract:
  - the bundle schema must stay explicitly typed at the `ForeshadowStatusUpdateMetadata` item level;
  - malformed sidecar items must still degrade quietly instead of widening the schema back to generic objects or failing the whole bundle.
