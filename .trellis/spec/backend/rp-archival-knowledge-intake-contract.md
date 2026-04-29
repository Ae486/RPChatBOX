# RP Archival Knowledge Intake Contract

## Scenario: Memory layer freezes source-material metadata before setup/runtime producers converge

### 1. Scope / Trigger

- Trigger: Recall materialization now uses a shared memory-owned intake helper, but Archival Knowledge setup ingestion still constructed retrieval metadata inline.
- Applies to:
  - setup commit ingestion into Archival Knowledge;
  - retrieval-core `SourceAsset.metadata["seed_sections"][*]["metadata"]`;
  - `memory.search_archival` search hits, retrieval-backed Block-compatible views, and runtime payloads that need source provenance.
- This slice freezes the memory-layer Archival intake metadata contract first. It does not require setup/story runtime producers to implement new authoring behavior.

### 2. Signatures

Shared builders:

```python
def build_archival_source_metadata(
    *,
    source_type: str,
    import_event: str,
    workspace_id: str,
    commit_id: str,
    step_id: str,
    source_ref: str,
    domain: str,
    domain_path: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...

def build_archival_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
    level: int = 1,
) -> dict[str, Any]: ...
```

Canonical Archival metadata fields:

```python
{
    "layer": "archival",
    "source_family": "setup_source",
    "import_event": str,
    "source_type": str,
    "source_origin": "setup_workspace",
    "materialized_to_archival": True,
    "materialized_to_recall": False,
    "authoritative_mutation": False,
    "workspace_id": str,
    "commit_id": str,
    "step_id": str,
    "source_ref": str,
    "domain": str,
    "domain_path": str,
}
```

Currently frozen source types:

```text
foundation_entry
longform_blueprint
imported_asset
```

Currently frozen import event:

```text
setup.commit_ingest
```

### 3. Contracts

- The memory layer owns canonical Archival intake metadata generation.
- Setup/runtime producers may provide source payloads and auxiliary provenance, but they must not decide canonical `layer`, `source_family`, `materialized_to_archival`, `materialized_to_recall`, `authoritative_mutation`, or `source_origin`.
- Every Archival `SourceAsset.metadata` and every seed section metadata must carry the canonical fields.
- Generated canonical fields override conflicting `extra` values so an imported source cannot masquerade as Recall history, Runtime Workspace scratch, or an authoritative Core State mutation.
- `source_type`, `import_event`, `workspace_id`, `commit_id`, `step_id`, `source_ref`, `domain`, and `domain_path` are required and must fail early when blank.
- Family-specific fields are additive:
  - setup job facts: `target_type`, `target_ref`;
  - imported asset facts: `asset_id`, `asset_kind`, `asset_parse_status`, `parsed_payload`;
  - source section facts: `title`, `tags`, `source_refs`, page/image metadata when present.
- Retrieval-core remains the physical store for Archival Knowledge.
- This contract does not create public mutation tools, direct Core State writes, Recall materialization, or a universal durable `rp_blocks` table.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Blank required source field | Raise `ValueError` before writing a `SourceAsset` |
| `extra` contains conflicting memory ownership fields | Generated canonical values win |
| Seed section is built | Section metadata contains canonical parent/source metadata plus normalized tags |
| Setup commit ingests a foundation entry | Asset, seed section, and chunks identify `layer="archival"` and `source_type="foundation_entry"` |
| Setup commit ingests longform blueprint material | Asset and sections identify `source_type="longform_blueprint"` |
| Setup commit ingests imported asset material | Asset and sections identify `source_type="imported_asset"` while preserving asset-specific facts |
| Search reads Archival Knowledge | Existing retrieval-core search path remains unchanged and receives preserved metadata from chunks |
| Source material implies story canon | No direct Core State mutation occurs; canon still requires proposal/apply |

### 5. Good / Base / Bad Cases

- Good: setup foundation entries enter Archival Knowledge with stable `setup_source` metadata and can later be searched through `memory.search_archival`.
- Good: imported asset section metadata may carry page/image/title/tags, but memory-generated ownership fields override conflicts.
- Good: runtime can later align its upstream handoff to these frozen fields without changing retrieval storage.
- Base: a setup commit has no seed sections; existing empty/fallback ingestion behavior remains retrieval-core-specific.
- Bad: Archival setup ingestion hand-builds `layer`, `source_family`, and materialization flags in each section helper.
- Bad: imported source material is marked as Recall history just because it is searchable.
- Bad: setup runtime-private cognition is persisted as durable story Archival Knowledge without an explicit source-material import path.

### 6. Tests Required

- Shared helper tests:
  - canonical Archival metadata fields are generated;
  - conflicting extras cannot override ownership fields;
  - blank required fields raise `ValueError`;
  - seed section metadata preserves canonical metadata and normalized tags.
- Setup ingestion regressions:
  - foundation-entry ingestion writes canonical Archival metadata on parent asset, seed section, and chunks;
  - imported-asset ingestion overrides conflicting source metadata while preserving additive asset/section fields.
- Boundary tests:
  - no new public tool/provider contract is introduced;
  - retrieval-core remains the storage and indexing path.

### 7. Wrong vs Correct

#### Wrong

```python
metadata = {
    "layer": job_payload.get("layer"),
    "source_family": job_payload.get("source_family"),
    "source_type": job.target_type,
}
```

This lets setup/runtime payloads redefine memory-layer ownership.

#### Correct

```python
metadata = build_archival_source_metadata(
    source_type="foundation_entry",
    import_event="setup.commit_ingest",
    workspace_id=workspace_id,
    commit_id=commit_id,
    step_id=step_id,
    source_ref=source_ref,
    domain="world_rule",
    domain_path="foundation.world.magic-law",
    extra={"target_ref": target_ref},
)
```

The source payload contributes facts and provenance; memory owns the canonical Archival intake fields.
