# RP Memory Materialization Intake Contract

## Scenario: Memory layer freezes structured materialization metadata before runtime producers converge

### 1. Scope / Trigger

- Trigger: Recall materialization now has several source families, but metadata construction is spread across ingestion services while upstream runtime producers are still evolving.
- Applies to:
  - Recall ingestion services for chapter summaries, accepted story segments, continuity notes, scene transcripts, character long-history summaries, and retired foreshadow summaries;
  - retrieval-core `SourceAsset.metadata["seed_sections"][*]["metadata"]`;
  - retrieval search metadata preservation and Recall source-family filtering;
  - story-runtime handoff work that must know what metadata to produce or preserve.
- This slice freezes the memory-layer intake metadata contract first. It does not require runtime to already produce every family.

### 2. Signatures

Shared builder:

```python
def build_recall_materialization_metadata(
    *,
    materialization_kind: str,
    materialization_event: str,
    session_id: str,
    chapter_index: int,
    domain_path: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...

def build_recall_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
) -> dict[str, Any]: ...
```

Canonical Recall metadata fields:

```python
{
    "layer": "recall",
    "source_family": "longform_story_runtime",
    "materialization_event": str,
    "materialization_kind": str,
    "materialized_to_recall": True,
    "source_type": str,  # same value as materialization_kind
    "session_id": str,
    "chapter_index": int,
    "domain": "chapter",
    "domain_path": str,
}
```

Currently frozen materialization kinds:

```text
chapter_summary
accepted_story_segment
continuity_note
scene_transcript
character_long_history_summary
retired_foreshadow_summary
```

Currently frozen materialization events:

```text
heavy_regression.chapter_close
scene_close
```

### 3. Contracts

- The memory layer owns canonical materialization metadata generation.
- Runtime may provide structured source payloads, but it must not decide canonical `layer`, `source_family`, `materialized_to_recall`, `source_type`, or Recall `domain`.
- `materialization_kind`, `materialization_event`, `session_id`, `chapter_index`, and `domain_path` are required for every Recall materialization asset and every seed section.
- `seed_sections[*].metadata` must preserve the same canonical fields as the parent `SourceAsset.metadata`.
- Family-specific fields are additive:
  - accepted story segment: `artifact_id`, `artifact_revision`, `artifact_kind`;
  - continuity note: `note_index`;
  - scene transcript: `scene_ref`, transcript source counters;
  - character history: `character_key`, supporting context counters;
  - retired foreshadow: `foreshadow_id`, `terminal_status`, supporting context counters.
- Generated canonical fields override any conflicting `extra` value. This prevents upstream or caller metadata from making Recall look like Runtime Workspace or a different source family.
- Blank required string fields and non-positive `chapter_index` must fail early before retrieval-core ingestion.
- Empty source payloads are still handled by each family-specific ingestion service; the shared builder only validates metadata shape.
- This contract does not create new public memory tools, direct Core State writes, or a universal durable `rp_blocks` table.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Blank `materialization_kind` | Raise `ValueError` before writing a `SourceAsset` |
| Blank `materialization_event` | Raise `ValueError` before writing a `SourceAsset` |
| Blank `session_id` | Raise `ValueError` before writing a `SourceAsset` |
| `chapter_index <= 0` | Raise `ValueError` before writing a `SourceAsset` |
| Blank `domain_path` | Raise `ValueError` before writing a `SourceAsset` |
| `extra` contains `layer`, `source_family`, or `materialized_to_recall` conflicts | Generated canonical values win |
| Seed section is built | Section metadata contains canonical parent metadata plus normalized tags |
| Existing ingestion service receives empty source payload | Existing family-specific skip/dedupe behavior remains unchanged |
| Retrieval-core indexing fails | Family-specific `*_ingestion_failed:{asset_id}:{detail}` error remains visible |

### 5. Good/Base/Bad Cases

- Good: chapter-close `summary_updates` become Recall `continuity_note` assets with the same canonical metadata on asset and seed section.
- Good: `scene_transcript` uses `materialization_event="scene_close"` while still sharing Recall layer/source-family fields with chapter-close families.
- Good: runtime can later produce more structured metadata, but memory still owns canonical source-family and materialization fields.
- Base: a future runtime producer sends only valid source payloads; memory helper fills canonical metadata and ingestion proceeds.
- Bad: each ingestion service hand-builds `layer`, `source_family`, and `materialized_to_recall`, causing drift.
- Bad: upstream metadata overrides `layer` to `runtime_workspace` on a Recall asset.
- Bad: memory infers scene transcript history from raw discussion rows without an explicit closed-scene producer path.

### 6. Tests Required

- Shared helper tests:
  - canonical fields are generated for valid Recall materialization metadata;
  - conflicting extra fields cannot override canonical fields;
  - blank required fields and invalid `chapter_index` raise `ValueError`;
  - seed section metadata preserves canonical parent metadata and normalized tags.
- Ingestion service regressions:
  - existing Recall ingestion tests continue to prove metadata appears on both assets and seed sections;
  - retrieval search still preserves source-family/materialization metadata;
  - failed `IndexJob` behavior stays family-specific and explicit.
- Boundary tests:
  - Runtime Workspace discussion/draft material remains non-Recall unless a dedicated ingestion path calls this contract.

### 7. Wrong vs Correct

#### Wrong

```python
metadata = {
    "layer": upstream_payload.get("layer"),
    "source_family": upstream_payload.get("source_family"),
    "materialization_kind": upstream_payload.get("kind"),
}
```

This lets runtime or worker payloads redefine memory-layer ownership.

#### Correct

```python
metadata = build_recall_materialization_metadata(
    materialization_kind="continuity_note",
    materialization_event="heavy_regression.chapter_close",
    session_id=session_id,
    chapter_index=chapter_index,
    domain_path=section_path,
    extra={"note_index": note_index},
)
```

The source payload contributes family-specific facts, while memory owns canonical materialization fields.
