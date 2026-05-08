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

These fields are required because draft/rewrite candidates may exist without being the `visible_output_ref` or `selected_output_ref` of a turn. Branch-aware artifact reads must consult artifact runtime ownership metadata before falling back to output-ref lookup.

### 3. Contracts

#### Ownership contract

- Branch visibility is an application-layer read contract.
- LangGraph checkpoints/forks remain workflow-shell primitives only.
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

#### Retrieval visibility contract

- RetrievalBroker runtime calls must apply branch visibility by default.
- Explicit cross-branch reads are debug/admin-only and must be traceable.
- Optional caller filters such as `branch_ids` must not override the active visibility contract for normal runtime reads.

#### Compatibility contract

- Legacy/global reads may remain for admin/debug or old paths temporarily.
- Boot-bar runtime-owned paths must build `RuntimeBranchReadScope` from `MemoryRuntimeIdentity` before reading data.
- Physical purge can come later after visibility-first behavior is proven.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Two branches share pre-fork material | Both can read shared visible lineage material |
| Branch A writes post-fork Workspace/Recall material | Branch B runtime reads do not see it |
| Runtime read/search omits explicit branch filter | Active branch visibility still applies |
| Rollback to turn N occurs | Turn N+1 runtime materials become hidden from default runtime reads |
| Rollback hides a later draft/rewrite candidate | The candidate artifact is absent from active branch snapshots |
| `pending_segment_artifact_id` points to a hidden artifact | Snapshot returns no pending segment pointer |
| Archival seed content exists | Visible as `story_global` unless later branch-local evolution explicitly changes visibility |
| Active Story Evolution creates new archival content | Visible only to the current branch unless explicitly promoted wider |
| Debug/admin path requests cross-branch read | Allowed only through explicit traceable path |

### 5. Good / Base / Bad Cases

- Good: branch creation adds metadata and lineage, but does not clone all Core/Recall/Workspace rows.
- Good: Runtime Workspace cards created on branch A stay invisible on branch B.
- Good: Recall summaries created after a rollback point are hidden from default runtime retrieval for that branch.
- Good: rewrite candidates produced after a rollback cutoff are hidden even if they were never selected/visible outputs.
- Good: chapter pending pointers are cleared in the returned snapshot when they target hidden artifacts.
- Base: physical purge remains later work; boot behavior relies on visibility-state filtering first.
- Bad: copying all retrieval chunks and embeddings into a new branch at branch creation time.
- Bad: treating LangGraph checkpoint replay as sufficient branch visibility enforcement.
- Bad: allowing a runtime read to bypass active branch visibility because it omitted a branch filter.

### 6. Tests Required

- Resolver tests cover:
  - runtime scope construction from `MemoryRuntimeIdentity`;
  - lineage-based visibility for shared vs post-fork branch material;
  - rollback cutoff behavior.
- Integration tests cover:
  - Core / Projection / Runtime Workspace / Recall / RetrievalBroker runtime reads all respect active visibility;
  - optional `branch_ids` style filters do not bypass active visibility for runtime paths.
- Snapshot tests cover:
  - artifact visibility uses `runtime_turn_id` / `runtime_branch_head_id` metadata when output-ref lookup is insufficient;
  - `pending_segment_artifact_id` is cleared from the returned snapshot when the target artifact is hidden.
- Focused lint/type checks must include the resolver contract and tests.

### 7. Wrong vs Correct

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
