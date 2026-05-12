# RP Branch Visibility Resolver And Lineage

## Scenario: branch-aware runtime reads before rollback, retrieval visibility, and Workspace isolation can stop leaking latest-session material

### 1. Scope / Trigger

- Trigger: boot-bar identity, persistent Runtime Workspace, and persistent event records are in place or planned, but runtime memory reads are still too session/global oriented. Story runtime cannot safely continue if Core / Projection / Runtime Workspace / Recall / RetrievalBroker keep reading "latest session" instead of active branch lineage.
- Applies to backend RP memory/runtime contract work for:
  - branch visibility lineage metadata;
  - shared runtime read scope construction;
  - exact-identity branch-aware filtering for Core / Projection / Runtime Workspace / Recall / RetrievalBroker runtime calls;
  - rollback visibility semantics;
  - focused branch-isolation tests.
- This slice must not implement:
  - branch UI or branch merge;
  - physical purge as the first behavior;
  - full archival reindex governance;
  - packet assembly or retrieval usage loops;
  - rewriting LangGraph persistence.

### 2. Surfaces

Runtime branch read scope:

```python
class RuntimeBranchReadScope(BaseModel):
    story_id: str
    session_id: str
    active_branch_head_id: str
    active_turn_id: str | None
    visible_branch_head_ids: list[str]
    turn_cutoff_by_branch: dict[str, str | None]
    include_story_global: bool = True
```

Core State as-of manifest contract:

```python
class CoreStateSnapshotManifest(BaseModel):
    snapshot_id: str
    parent_snapshot_id: str | None = None
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
    effective_revision_map: dict[str, str]
    changed_ref_ids: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)


class CoreStateAsOfResolver:
    def resolve_manifest(
        self,
        *,
        scope: RuntimeBranchReadScope,
        selected_turn_id: str | None = None,
    ) -> CoreStateSnapshotManifest: ...

    def resolve_object_revision(
        self,
        *,
        manifest: CoreStateSnapshotManifest,
        object_ref: ObjectRef,
    ) -> CoreStateAuthoritativeRevisionRecord: ...
```

Visibility marker vocabulary:

```text
visibility_scope:
  story_global
  branch_scoped
  selected_branches

visibility_state:
  active
  hidden
  invalidated
```

Resolver surface:

```python
class BranchVisibilityResolver:
    def build_runtime_scope(self, *, identity: MemoryRuntimeIdentity) -> RuntimeBranchReadScope: ...
    def is_visible(
        self,
        *,
        scope: RuntimeBranchReadScope,
        visibility_scope: str,
        visibility_state: str,
        owning_branch_head_id: str | None,
        origin_turn_id: str | None,
        selected_branch_head_ids: list[str] | None = None,
    ) -> bool: ...
```

Minimum metadata fields required on branch-aware records:

```text
owning_branch_head_id
origin_turn_id
visibility_scope
visibility_state
hidden_by_branch_head_id (optional)
hidden_after_turn_id (optional)
selected_branch_head_ids_json (optional)
```

For legacy longform artifact compatibility, `StoryArtifact.metadata` must also carry runtime ownership when the artifact is produced by the runtime:

```text
runtime_session_id
runtime_branch_head_id
runtime_turn_id
runtime_profile_snapshot_id
```

These fields are required because draft/rewrite candidates may exist without being the `visible_output_ref` or `selected_output_ref` of a turn. Runtime product reads must use these explicit `runtime_*` ownership fields as the artifact ownership truth. Output-ref reverse lookup is allowed only inside an explicit migration/repair tool path that marks its repair source; it must not be used by snapshot, writer context, outline progress, rollback, or settlement bridge product read paths.

### 3. Contracts

#### Ownership contract

- Branch visibility is an application-layer read contract.
- LangGraph checkpoints/forks remain workflow-shell primitives only.
- A captured LangGraph checkpoint pointer is a one-time technical anchor for a
  settled `StoryTurn`; replay/fork/debug checkpoints must not overwrite the
  application-layer rollback binding for that turn.
- Runtime memory visibility must be enforced by RP application storage/services across:
  - Core State reads
  - Projection reads
  - Runtime Workspace reads
  - Recall search
  - RetrievalBroker runtime calls
  - proposal/event inspection reads when branch-aware runtime debugging is used

#### Copy-on-write lineage contract

- Branch creation must be metadata-first, not full-store cloning.
- New branch-specific writes produce branch-scoped rows/revisions/materializations.
- Shared pre-fork material stays visible through lineage, not by duplicating every row.
- `visible_branch_head_ids` plus `turn_cutoff_by_branch` is the minimum runtime read contract for boot-bar lineage evaluation.

#### Layer default contract

- `Core State` runtime revisions are branch-aware after activation.
  - pre-fork settled facts remain visible through lineage;
  - post-fork writes belong to the producing branch.
- Core State runtime reads must resolve an as-of manifest before reading object
  payloads. A current/latest authoritative object row is a cache or compatibility
  view, not the runtime branch truth.
- `Projection/View` follows Core visibility because it is strictly derived from Core facts.
- `Runtime Workspace` is branch-aware and turn-scoped.
  - it must never leak across branch switches.
- `Recall Memory` is branch-aware by default.
  - it records what happened on a branch.
- `Archival Knowledge` defaults:
  - setup/activation seed is `story_global`;
  - active Story Evolution writes are `branch_scoped` by default;
  - they become broader only through explicit promotion.
- retrieval/index/chunk/cache rows are derived infrastructure and must inherit source visibility.

#### Rollback contract

- Rollback is first a visibility transition, not a physical delete.
- After rollback to turn `N` on the active branch:
  - later-turn materials become hidden from default runtime reads;
  - Workspace material after `N` is hidden/invalidated for that branch;
  - Recall material after `N` is hidden from runtime search for that branch;
  - derived retrieval/index visibility follows the source content visibility.
- Rollback should create durable branch-head transition/event/visibility records.
- Rollback must not fake historical Core fact rewrites as if later writes never happened.
- Rollback and branch creation must select the Core State manifest bound to the
  target turn. Later Core revisions remain audit-visible, but default runtime
  reads must not select them until the active branch reaches or creates a turn
  whose manifest points at those revisions.

#### Core State as-of manifest contract

- Core State branch reads use copy-on-write snapshot manifests:
  - turn `0` / activation creates the initial Core State manifest;
  - turns without Core mutation reuse the previous visible manifest;
  - a turn with Core mutation creates complete object revision rows for changed
    objects and a new manifest that points unchanged refs at inherited revisions
    and changed refs at new revisions;
  - branch creation from turn `N` inherits the manifest visible at turn `N`;
  - the first Core mutation on the new branch creates branch-scoped revisions
    and a new branch-local manifest.
- `CoreStateAuthoritativeRevisionRecord.data_json` or its replacement must hold
  the complete object payload for that revision. Patch/delta/event rows are for
  audit, diff, dirty-target, and projection refresh; runtime as-of reads must not
  depend on replaying a long delta chain.
- A Core revision created by runtime work must carry or be joinable to:
  - `story_id`;
  - `session_id`;
  - `owning_branch_head_id` / runtime branch head;
  - `origin_turn_id` / runtime turn;
  - `runtime_profile_snapshot_id`;
  - `visibility_scope`;
  - `visibility_state`;
  - `base_revision` or equivalent base ref;
  - `source_event_id` / apply receipt / proposal refs when available.
- Runtime-owned Core reads must fail closed or return an explicit compatibility
  warning when no turn-bound Core manifest can be resolved. They must not silently
  fall back to `StorySession.current_state_json` or a latest current object row
  for writer context.
- Old sessions that lack turn-bound Core revision history may be migrated only
  as compatibility snapshots. The migration must mark historical as-of reads as
  unavailable before the migration anchor instead of fabricating false history.

#### Retrieval visibility contract

- RetrievalBroker runtime calls must apply branch visibility by default.
- Explicit cross-branch reads are debug/admin-only and must be traceable.
- Optional caller filters such as `branch_ids` must not override the active visibility contract for normal runtime reads.

#### Compatibility contract

- Legacy/global reads may remain for admin/debug or old paths temporarily.
- Boot-bar runtime-owned paths must build `RuntimeBranchReadScope` from `MemoryRuntimeIdentity` before reading data.
- Legacy artifact metadata keys such as `turn_id` or `branch_head_id` are not runtime ownership keys. A runtime-owned `story_segment` without matching `runtime_turn_id` and `runtime_branch_head_id` is invisible to product story-body reads and cannot trigger accepted-output settlement. If old data must be recovered, do it through an explicit migration/repair flow that writes canonical `runtime_*` metadata before the artifact becomes product-visible.
- Physical purge can come later after visibility-first behavior is proven.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Two branches share pre-fork material | Both can read shared visible lineage material |
| Branch A writes post-fork Workspace/Recall material | Branch B runtime reads do not see it |
| Runtime read/search omits explicit branch filter | Active branch visibility still applies |
| Rollback to turn N occurs | Turn N+1 runtime materials become hidden from default runtime reads |
| Core changes at turn 3 after turn 1/2 were unchanged | Turn 1/2 manifests still point at the pre-change Core revisions |
| Branch is created from turn 2 after Core changed at turn 3 | New branch inherits the turn 2 manifest and does not read turn 3 Core values |
| New branch mutates a Core object | It creates a branch-scoped object revision and manifest without changing the parent branch manifest |
| Rollback hides a later draft/rewrite candidate | The candidate artifact is absent from active branch snapshots |
| `pending_segment_artifact_id` points to a hidden artifact | Snapshot returns no pending segment pointer |
| Archival seed content exists | Visible as `story_global` unless later branch-local evolution explicitly changes visibility |
| Active Story Evolution creates new archival content | Visible only to the current branch unless explicitly promoted wider |
| Debug/admin path requests cross-branch read | Allowed only through explicit traceable path |

### 5. Good / Base / Bad Cases

- Good: branch creation adds metadata and lineage, but does not clone all Core/Recall/Workspace rows.
- Good: turn 1 and turn 2 both reuse the turn 0 Core manifest when Core State
  does not change, while turn 3 creates a new manifest only for changed object
  revision pointers.
- Good: Runtime Workspace cards created on branch A stay invisible on branch B.
- Good: Recall summaries created after a rollback point are hidden from default runtime retrieval for that branch.
- Good: rewrite candidates produced after a rollback cutoff are hidden even if they were never selected/visible outputs.
- Good: chapter pending pointers are cleared in the returned snapshot when they target hidden artifacts.
- Base: physical purge remains later work; boot behavior relies on visibility-state filtering first.
- Bad: copying all retrieval chunks and embeddings into a new branch at branch creation time.
- Bad: reading `rp_core_state_authoritative_objects.data_json` as runtime truth
  after branching from an earlier turn, because that row represents latest cache
  state rather than selected-turn Core truth.
- Bad: treating LangGraph checkpoint replay as sufficient branch visibility enforcement.
- Bad: allowing a runtime read to bypass active branch visibility because it omitted a branch filter.

### 6. Tests Required

- Resolver tests cover:
  - runtime scope construction from `MemoryRuntimeIdentity`;
  - lineage-based visibility for shared vs post-fork branch material;
  - rollback cutoff behavior.
- Checkpoint pointer tests cover:
  - repeated captures for the same settled turn return the original binding;
  - replay/fork/debug checkpoints do not replace the rollback binding used by
    branch control receipts.
- Integration tests cover:
  - Core / Projection / Runtime Workspace / Recall / RetrievalBroker runtime reads all respect active visibility;
  - optional `branch_ids` style filters do not bypass active visibility for runtime paths.
- Core as-of tests cover:
  - turn 0 creates an initial manifest;
  - turn 1/2 without Core mutation reuse that manifest;
  - turn 3 Core mutation creates a new object revision and new manifest;
  - branch from turn 2 reads the turn 2 manifest, not the latest current row;
  - branch-local mutation creates a branch-scoped revision and does not change
    the parent branch manifest;
  - rollback to turn 2 selects the turn 2 manifest while later revisions remain
    audit-visible but runtime-hidden.
- Snapshot tests cover:
  - `story_segment` visibility uses exact `runtime_turn_id` / `runtime_branch_head_id` metadata and fails closed when either key is missing or mismatched;
  - output-ref reverse lookup is absent from runtime product read paths and reserved for explicit migration/repair;
  - `pending_segment_artifact_id` is cleared from the returned snapshot when the target artifact is hidden.
- Focused lint/type checks must include the resolver contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
row = core_state_store.get_authoritative_object(
    session_id=identity.session_id,
    layer=ref.layer.value,
    scope=ref.scope,
    object_id=ref.object_id,
)
return row.data_json
```

This reads the latest session cache. If a branch is created from turn 2 after the
same Core object changed at turn 5, the new branch can see turn 5 truth.

#### Correct

```python
scope = branch_visibility_resolver.build_runtime_scope(
    identity=identity,
    selected_turn_id=identity.turn_id,
)
manifest = core_state_as_of_resolver.resolve_manifest(scope=scope)
revision = core_state_as_of_resolver.resolve_object_revision(
    manifest=manifest,
    object_ref=ref,
)
return revision.data_json
```

Runtime-owned Core reads select the exact object revision visible at the
selected branch/turn. Latest current rows remain caches or compatibility views.

#### Wrong

```python
artifact_turn_id = artifact.metadata.get("runtime_turn_id") or artifact.metadata.get("turn_id")
```

This lets legacy metadata masquerade as runtime ownership and can settle or render artifacts that were never repaired into the branch runtime model.

#### Correct

```python
artifact_turn_id = artifact.metadata.get("runtime_turn_id")
artifact_branch_id = artifact.metadata.get("runtime_branch_head_id")
```

Runtime product reads fail closed unless both canonical ownership keys match the visible active-lineage turn.

#### Wrong

```python
results = retrieval_service.search_chunks(query)
```

This treats retrieval visibility as global/session-only and allows runtime reads to ignore active branch lineage.

#### Correct

```python
scope = branch_visibility_resolver.build_runtime_scope(identity=identity)
visible = branch_visibility_resolver.is_visible(
    scope=scope,
    visibility_scope="branch_scoped",
    visibility_state="active",
    owning_branch_head_id=row.branch_head_id,
    origin_turn_id=row.turn_id,
)
```

Runtime reads first resolve active branch lineage and then apply visibility as an application-layer contract.

#### Wrong

```python
pending = chapter.pending_segment_artifact_id
```

This trusts a stored chapter pointer even when the target artifact belongs to a future turn hidden by rollback.

#### Correct

```python
artifacts, hidden_artifact_ids = filter_artifacts_by_active_branch(snapshot_artifacts)
if chapter.pending_segment_artifact_id in hidden_artifact_ids:
    chapter = chapter.model_copy(update={"pending_segment_artifact_id": None})
```

Snapshot composition must filter both visible artifact lists and branch-sensitive pointers derived from those artifacts.
