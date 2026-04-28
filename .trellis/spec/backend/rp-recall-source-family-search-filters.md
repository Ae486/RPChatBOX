# RP Recall Source Family Search Filters

## Scenario: Recall search can target specific source families and materialization kinds without new tool contracts

### 1. Scope / Trigger

- Trigger: Recall now persists multiple source families (`chapter_summary`, `accepted_story_segment`, `continuity_note`) and preserves source-family metadata through search/runtime payloads, but callers still cannot target one family without post-filtering hits themselves.
- Applies to:
  - `MemorySearchRecallInput.filters`
  - retrieval query preprocessing
  - retrieval common filter matching
  - `RetrievalBroker.search_recall`
  - focused retrieval tests
- This slice is read-only. It must not add a new public tool, a new endpoint, or a universal durable `rp_blocks` table.

### 2. Signatures / Surfaces

Existing public surface remains:

```python
class MemorySearchRecallInput(BaseModel):
    query: str
    scope: str | None = None
    domains: list[Domain] = Field(default_factory=list)
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)
```

Supported Recall filter keys after this slice:

```python
filters = {
    "materialization_kinds": list[str],   # e.g. ["chapter_summary", "continuity_note"]
    "source_families": list[str],         # e.g. ["longform_story_runtime"]
    "chapter_indices": list[int],         # e.g. [3, 4]
}
```

### 3. Contracts

- `memory.search_recall` continues to use the same `filters` dictionary contract; this slice only defines additional supported keys.
- `materialization_kinds` filters Recall hits by metadata field `materialization_kind`.
- `source_families` filters Recall hits by metadata field `source_family`.
- `chapter_indices` filters Recall hits by metadata field `chapter_index`.
- Filter matching must use chunk metadata first and asset metadata only as fallback, consistent with Recall source-family metadata preservation.
- When a filter key is present:
  - hits missing the required metadata field do not match;
  - no synthetic metadata may be invented purely to satisfy the filter.
- When none of these keys are present:
  - existing Recall search behavior stays unchanged.
- Multiple supported filter keys combine with AND semantics.
- Multiple values within the same filter key combine with OR semantics.
- `RetrievalBroker.search_archival` is out of scope for this slice.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `filters.materialization_kinds=["continuity_note"]` | Return only Recall hits whose metadata resolves to `materialization_kind="continuity_note"` |
| `filters.source_families=["longform_story_runtime"]` | Return only Recall hits whose metadata resolves to that source family |
| `filters.chapter_indices=[2]` | Return only Recall hits whose metadata resolves to `chapter_index=2` |
| Multiple filter keys supplied | Apply AND semantics across keys |
| Multiple values inside one key | Apply OR semantics within that key |
| Legacy Recall hit lacks `materialization_kind` | It remains searchable normally without that filter, but does not match when `materialization_kinds` filter is present |
| Filter list contains duplicates or blank strings | Preprocessor normalizes and deduplicates them |
| `chapter_indices` contains non-integer junk | Preprocessor drops invalid values rather than crashing retrieval |

### 5. Good / Base / Bad Cases

- Good: searching Recall with `materialization_kinds=["continuity_note"]` returns only continuity notes from chapter-close maintenance.
- Good: searching Recall with `materialization_kinds=["chapter_summary", "accepted_story_segment"]` returns either family, but still excludes continuity notes.
- Good: adding `chapter_indices=[5]` narrows results to chapter 5 only.
- Base: ordinary Recall search without these filters behaves exactly as before.
- Bad: adding a new `memory.search_recall_by_kind` tool instead of using the existing `filters` surface.
- Bad: forcing legacy Recall hits to fake `materialization_kind` just so filtered search can include them.
- Bad: applying these filters to Archival in this slice without a separate contract.

### 6. Tests Required

- Retrieval broker integration:
  - ingest at least `chapter_summary`, `accepted_story_segment`, and `continuity_note` Recall assets;
  - verify `materialization_kinds` returns the requested families only;
  - verify `chapter_indices` narrows results correctly.
- Query preprocessor:
  - deduplicates and normalizes `materialization_kinds` / `source_families`;
  - coerces/deduplicates valid `chapter_indices` and drops invalid values.
- Legacy regression:
  - a Recall hit missing source-family metadata still appears without filters;
  - the same hit is excluded when filtered by a missing field.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: add a new tool/API just to search continuity notes.
memory.search_recall_continuity_notes(...)
```

#### Correct

```python
# Correct: reuse the existing Recall search surface and narrow via filters.
memory.search_recall(
    query="mask oath",
    filters={"materialization_kinds": ["continuity_note"]},
)
```
