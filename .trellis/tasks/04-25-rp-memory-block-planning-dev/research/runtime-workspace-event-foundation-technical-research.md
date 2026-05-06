# Runtime Workspace Persistence + Event Foundation Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: lightweight pre-spec technical research for:
> - `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
> - `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md`

## 1. Question

For the next boot-bar memory pair, what should be reused for durable turn material and persistent event records, and what should explicitly be avoided?

The target is:

- persistent Runtime Workspace records keyed by full runtime identity
- persistent memory event records keyed by the same identity
- focused queryability for boot runtime paths
- no drift into a second truth store, generic event bus, or git-backed memory repo

## 2. Existing Repo Wheels To Reuse

### SQLModel storage record pattern

Current backend already persists story, proposal/apply, and retrieval records through:

- `backend/models/rp_story_store.py`
- `backend/models/rp_memory_store.py`
- `backend/models/rp_retrieval_store.py`

Common repo pattern:

- first-class indexed identity columns
- JSON fields for complex payload sections
- lightweight compatible-schema helpers for incremental rollout

Decision:

- keep the same pattern for persistent Runtime Workspace and event records;
- make identity and query-critical fields first-class columns;
- keep material payload/source refs/dirty target details as JSON until a later slice proves a normalized subtable is required.

### Existing typed DTOs and services

Current memory strengthening already froze:

- `RuntimeWorkspaceMaterial`
- `RuntimeWorkspaceMaterialReceipt`
- `MemoryChangeEvent`
- `MemorySourceRef`
- `MemoryDirtyTarget`

Decision:

- persistent records should adapt to these DTOs rather than inventing a second envelope;
- current in-process services should gain repository-backed storage rather than being replaced by a new abstraction family.

### Existing proposal/apply and retrieval stores as naming guides

`rp_memory_store.py` and `rp_retrieval_store.py` already show the repo's preferred naming and indexing style for:

- story/session indexes
- status columns
- created/updated timestamps
- JSON metadata and provenance fields

Decision:

- follow the same table naming/indexing style for new persistent Workspace and event records;
- do not introduce document-store style nested storage or opaque serialized blobs for identity/query-critical fields.

## 3. Mature External References

### Letta

Useful reference:

- commit-style audit units
- source-of-truth plus read-cache split
- editable memory projection concepts

Boundary:

- Letta git memory is too file-tree-oriented and too heavy as a direct backend dependency for this slice.
- RP needs branch/turn/profile identity across multiple memory layers, not one block repo.

Decision:

- borrow the “durable audit record plus rebuildable read surfaces” lesson;
- do not use git-backed memory persistence as the Workspace/event implementation.

### Dolt / lakeFS

Useful reference:

- copy-on-write branching
- lineage-aware visibility
- no full clone requirement at branch creation

Boundary:

- these are branch semantics references, not a required storage backend migration.

Decision:

- use them as guidance for future branch visibility and purge semantics;
- keep persistent Workspace/event records in RP application storage.

### Event bus / CQRS / Kafka-style systems

Potential appeal:

- durable event stream
- replay
- downstream consumers

Boundary:

- current boot bar does not need distributed event streaming;
- event spine is explicitly not the truth store and not replay source of truth.

Decision:

- do not introduce Kafka, CQRS/event-store libraries, or distributed message buses for I-min;
- keep persistent event records in the same application storage model.

## 4. Rejected Options

Rejected for this spec pair:

- reusing `StoryArtifactRecord` or `StoryDiscussionEntryRecord` as Runtime Workspace persistence
- storing durable Workspace state back into `ChapterWorkspace.builder_snapshot_json`
- keeping all event records only in process memory and treating debug replay as best-effort
- introducing a generic event-sourcing framework
- storing identity/query-critical material only inside opaque JSON blobs

Reason:

- each option would either blur truth boundaries, break branch/turn queryability, or make later visibility/debug work harder.

## 5. Spec Decisions Enabled By This Research

1. Runtime Workspace persistence should use a dedicated persistent record/repository, not reuse artifact/discussion rows.
2. Query-critical identity fields should be explicit columns:
   - `story_id`
   - `session_id`
   - `branch_head_id`
   - `turn_id`
   - `runtime_profile_snapshot_id`
3. Material-specific payload/source refs/metadata can stay JSON-backed in the boot slice as long as identity/lifecycle/domain/visibility stay queryable columns.
4. Persistent event records should store:
   - full runtime identity
   - actor / layer / domain / kind / operation / visibility
   - structured source refs / dirty targets / metadata in JSON
5. Event persistence should remain an audit/invalidation side store, not a state reconstruction engine.
6. Existing service surfaces should be extended to use repositories or persistent stores rather than replaced wholesale.

## 6. Immediate Spec Consequence

The next two backend specs should be:

1. `rp-runtime-workspace-persistent-turn-material-store.md`
2. `rp-persistent-memory-event-record-foundation.md`

They should be written as incremental extensions over:

- `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
- `.trellis/spec/backend/rp-memory-change-event-spine.md`
- `backend/models/rp_story_store.py`
- `backend/models/rp_memory_store.py`
- `backend/models/rp_retrieval_store.py`

They should not introduce:

- new truth layers
- distributed event infra
- file-based memory repo storage
- branch merge semantics
- full debug UI or eval dashboard surfaces
