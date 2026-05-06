# RP Archival Evolution Reindex Governance

## Scenario: Archival Knowledge gains versioned Story Evolution edit/reindex governance, branch-aware visibility, and source-version provenance without replacing retrieval-core

### 1. Scope / Trigger

- Trigger: setup/source imports already materialize Archival Knowledge into retrieval-core, and retrieval maintenance can reindex assets, but full runtime foundation still lacks a governed Story Evolution path for editing archival source material. Runtime cannot rely on archival evidence if active edits are invisible to governance, versionless, or leak across branches by default.
- Applies to backend RP memory contract work for:
  - versioned archival source evolution commands/receipts;
  - chunk/source supersession and visibility scope rules;
  - reindex linkage from archival evolution actions;
  - proposal/source provenance to versioned archival refs;
  - focused evolution/reindex visibility tests.
- This slice must not:
  - replace retrieval-core storage or indexing algorithms;
  - turn Archival Knowledge into current canon truth;
  - bypass governed edit receipts with raw source/chunk mutation;
  - require a UI before the backend contract is stable.

### 2. Surfaces

Visibility scopes:

```text
current_branch
selected_branches
all_existing_branches
story_global
```

Evolution request/receipt:

```python
class ArchivalEvolutionRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    source_asset_id: str
    expected_source_version: int | None = None
    visibility_scope: str = "current_branch"
    selected_branch_head_ids: list[str] = Field(default_factory=list)
    replacement_sections: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None


class ArchivalEvolutionReceipt(BaseModel):
    evolution_id: str
    source_asset_id: str
    superseded_source_asset_id: str | None = None
    new_source_version: int
    visibility_scope: str
    reindex_job_ids: list[str]
    event_ids: list[str]
```

Service surface:

```python
class ArchivalEvolutionService:
    def evolve_source(self, request: ArchivalEvolutionRequest) -> ArchivalEvolutionReceipt: ...
```

### 3. Contracts

#### Archival layer contract

- Archival Knowledge is long-term source material and evidence.
- It remains retrieval-backed and distinct from Core current truth.
- A Core proposal may cite Archival material as source evidence, but Archival itself does not become canon without governed Core mutation.

#### Physical-store contract

- Source assets, documents, chunks, embeddings, and index jobs continue to live in retrieval-core.
- Evolution governance strengthens version, visibility, and provenance around that store.
- The storage wheel is reused; this slice is not a storage rewrite.

#### Visibility contract

- Setup / activation seed Archival material is story-global by default.
- Active runtime Story Evolution Archival writes are current-branch-visible by default.
- Broader visibility requires explicit governed scope:
  - `selected_branches`
  - `all_existing_branches`
  - `story_global`
- Visibility changes must be traceable backend records, not silent metadata edits.

#### Versioning contract

- Editing Archival source material must create a new source/chunk/index version or a traceable supersession chain.
- In-place overwrite of the active source/chunk version is not allowed as the authoritative evolution path.
- Old versions may remain for audit/history, but runtime search must not surface hidden or superseded versions for active reads.

#### Reindex contract

- Every Archival evolution action must link to the reindex jobs that rebuild searchable chunks.
- The retrieval maintenance pipeline remains the execution backbone for reindex.
- Evolution receipts must preserve the relation:
  - evolution edit
  - source version
  - chunk version/supersession
  - reindex job
  - memory event

#### Provenance contract

- When later Core proposals cite Archival evidence, the source refs must be able to point to the exact Archival source/chunk version used.
- Runtime debug/eval should be able to answer which Archival version informed a retrieved hit.

#### Compatibility contract

- Existing setup/source ingestion remains valid as the seed path.
- Full-foundation evolution work extends it with versioned edit/reindex semantics rather than replacing the intake contract.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Setup/activation imports archival material | Default visibility is `story_global` and retrieval-core storage stays unchanged |
| Active runtime evolution edits archival material without explicit visibility override | New version is current-branch-visible only |
| Evolution requests `selected_branches` visibility | Only the selected branches see the new version |
| Source edit succeeds | Receipt links new source version, superseded version, reindex jobs, and events |
| Runtime search runs after evolution | Hidden/superseded chunks are not returned for active reads |
| Core proposal cites archival evidence | Source refs can trace to the exact source/chunk version used |

### 5. Good / Base / Bad Cases

- Good: a Story Evolution edit creates source version 4 from version 3, reindexes the replacement chunks, and keeps the old version only for audit.
- Good: a branch-local archival correction stays invisible to sibling branches until the user explicitly promotes scope.
- Good: a later Core mutation can cite `asset:worldbook_v4#chunk:12` instead of a vague story-level archival source.
- Base: setup/imported asset ingestion still uses the existing Archival intake contract and retrieval-core path.
- Bad: mutating source/chunk rows in place and hoping a later reindex makes provenance understandable.
- Bad: returning superseded chunks in active runtime search because they still exist physically.
- Bad: treating runtime-authored Archival edits as story-global by default.

### 6. Tests Required

- Evolution tests cover:
  - version/supersession creation on edit;
  - current-branch default visibility;
  - explicit visibility-scope widening.
- Retrieval integration tests cover:
  - active runtime search excludes hidden/superseded chunks;
  - provenance can identify the versioned source/chunk chain.
- Reindex tests cover:
  - evolution receipts link to reindex jobs;
  - failed reindex remains traceable through the evolution chain rather than disappearing.
- Focused lint/type checks must include the Archival evolution contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
asset.metadata["text"] = new_text
maintenance_service.reindex_asset(story_id=story_id, asset_id=asset.asset_id)
```

This mutates the active source in place and loses a clear source-version provenance chain.

#### Correct

```python
receipt = archival_evolution_service.evolve_source(
    ArchivalEvolutionRequest(
        identity=identity,
        actor=user_id,
        source_asset_id="asset_worldbook_rules",
        expected_source_version=3,
        visibility_scope="current_branch",
        replacement_sections=sections,
    )
)
```

The archival edit is governed, versioned, branch-aware, and linked to the reindex chain that refreshes searchable evidence.
