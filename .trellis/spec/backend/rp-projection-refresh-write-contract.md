# RP Projection Refresh Write Contract

## Scenario: Settled projection refresh writes a durable current-view record without mutating authoritative truth

### 1. Scope / Trigger

- Trigger: `ProjectionRefreshService` already refreshes the chapter builder snapshot and formal Core State projection rows. This slice strengthens that write path so refresh records carry source refs, refresh reason, base revision, and dirty markers without becoming authoritative mutation.
- Applies to RP backend memory / Core State code across:
  - `ProjectionRefreshService`
  - `CoreStateDualWriteService` projection sync helpers
  - `CoreStateProjectionSlotRecord` / revision metadata
  - focused projection refresh tests
- This slice must not:
  - mutate `Core State.authoritative_state`
  - change proposal/apply semantics
  - replace `WritingPacketBuilder`
  - add a new durable truth store
  - expose projection refresh as a public memory tool

### 2. Surface

Request contract:

```python
class ProjectionRefreshRequest(BaseModel):
    identity: MemoryRuntimeIdentity | None = None
    refresh_actor: str = "system"
    refresh_reason: str = "bundle_refresh"
    refresh_source_kind: str = "bundle_refresh"
    refresh_source_ref: str | None = None
    base_revision: int | None = None
    source_authoritative_refs: list[ObjectRef] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    dirty_targets: list[MemoryDirtyTarget] = Field(default_factory=list)
```

Service surface:

```python
class ProjectionRefreshService:
    def refresh_from_bundle(
        self,
        *,
        chapter: ChapterWorkspace,
        bundle: SpecialistResultBundle,
        refresh_request: ProjectionRefreshRequest | None = None,
    ) -> ChapterWorkspace: ...
```

Error surface:

```python
class ProjectionRefreshServiceError(ValueError):
    code: str
```

Expected stable error codes:

```text
projection_refresh_base_revision_conflict
projection_refresh_source_revision_missing
projection_refresh_source_revision_conflict
```

### 3. Contracts

#### Derived projection ownership

- Projection refresh remains a maintenance write over `Core State.derived_projection`.
- It must not mutate authoritative truth or proposal/apply receipts.
- It may update the chapter builder mirror, but the mirror remains compatibility state, not truth source.

#### Base revision contract

- `base_revision` is the current projection revision being refreshed from.
- If the formal projection row already exists and its current revision differs from `base_revision`, the refresh must fail closed before mutation.
- If `base_revision` is absent, legacy refresh behavior remains compatible.

#### Source freshness contract

- `source_authoritative_refs` carry the authoritative evidence revisions that informed the refresh.
- When the formal Core State store path is active, the current authoritative revision must match the recorded source revision.
- Missing source revision data fails closed.
- Stale source revisions fail closed.

#### Metadata contract

- Refresh metadata on both current and revision rows must record:
  - `layer_family = "core_state.derived_projection"`
  - `semantic_layer = "Core State.derived_projection"`
  - `projection_role = "current_projection"`
  - `materialization_event = "projection_refresh"`
  - `authoritative_mutation = False`
  - `refresh_actor`
  - `refresh_reason`
  - `base_revision`
  - `source_authoritative_refs`
  - `source_refs`
  - `dirty_targets`
  - `projection_dirty_state`
- `refresh_source_ref` remains available for legacy compatibility, but it does not replace the structured source refs list.

#### Dirty marker contract

- Refresh should record downstream dirty targets for packet/window or other consumer invalidation.
- The projection itself remains the current view; dirty markers describe consumers that must recompute.
- Dirty markers may also be published to the lightweight memory event spine when an identity and event service are available.

#### Change minimization contract

- Identical projection items plus identical refresh metadata should not churn a new revision.
- If items stay the same but refresh metadata changes, that is still a meaningful refresh and should record a new revision.

#### Compatibility contract

- Existing legacy refresh callers with no `ProjectionRefreshRequest` must keep the current builder snapshot and formal projection behavior intact.
- If no identity or event service is supplied, refresh still succeeds and only records metadata.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Refresh called with no request | Legacy behavior remains compatible |
| Refresh called with fresh base revision and matching source refs | Projection revision advances and metadata is recorded |
| Refresh called with stale base revision | Reject before mutation with `projection_refresh_base_revision_conflict` |
| Refresh called with missing source revision | Reject before mutation with `projection_refresh_source_revision_missing` |
| Refresh called with stale source revision | Reject before mutation with `projection_refresh_source_revision_conflict` |
| Refresh metadata changes but projection items do not | New revision is still recorded |
| Refresh metadata and projection items are identical | No redundant rewrite |
| Identity plus event service are injected | A projection refresh event is emitted with dirty targets |
| Identity or event service is absent | Refresh still succeeds and records metadata only |

### 5. Good / Base / Bad Cases

- Good: a writer-facing current projection refresh records source refs, refresh reason, and dirty markers while keeping authoritative truth untouched.
- Good: a worker can inspect the latest projection metadata and see which consumer targets became dirty after refresh.
- Base: the current legacy refresh path still updates builder snapshot and settled projection rows when no new contract input is provided.
- Bad: using projection refresh to overwrite authoritative story truth.
- Bad: treating the chapter builder mirror as the only refresh record.
- Bad: ignoring stale base revision or stale source revision and silently reusing old projection state.

### 6. Tests Required

- Focused tests cover:
  - legacy refresh compatibility with no request;
  - refresh metadata recording on current and revision rows;
  - base revision conflict rejection;
  - source revision freshness rejection;
  - dirty target recording;
  - optional memory event spine emission when identity is supplied.
- Lint, format, and type checks must include the touched service and tests.

### 7. Wrong vs Correct

#### Wrong

```python
snapshot["current_state_digest"] = bundle.current_state_digest
```

This mutates the compatibility mirror without a contract for refresh provenance or consumer dirtiness.

#### Correct

```python
refresh_service.refresh_from_bundle(
    chapter=chapter,
    bundle=bundle,
    refresh_request=ProjectionRefreshRequest(
        base_revision=chapter_projection_revision,
        refresh_reason="post_write",
        source_authoritative_refs=[authoritative_ref],
        dirty_targets=[packet_dirty_target],
    ),
)
```

This keeps projection refresh as a derived current-view maintenance write with explicit freshness and invalidation metadata.
