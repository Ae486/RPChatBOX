# Story Runtime Branch-aware Memory Product Foundation Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Requirement spec:
> `story-runtime-branch-aware-memory-product-foundation-spec.md`
>
> Stage: V
>
> Status: development-spec-v1

## 1. Development Boundary

Stage V is a coherent product-foundation stage. It must be implemented in
ordered slices because later slices depend on the branch-aware memory read
contract.

The implementation order is:

1. V0 evidence lock;
2. V1 branch-aware memory resolver and writer-context scoping;
3. V2 backend memory product contract hardening;
4. V3 frontend Memory product surface;
5. V4 writer brainstorm apply;
6. V5 post-write memory maintenance minimum closure;
7. V6 product acceptance.

Do not split one module's sub-slices across multiple development owners. If V1
has `V1a/V1b/V1c`, one implement agent owns V1 until that module is complete,
then one module-level check agent reviews V1.

## 2. Owned Areas By Slice

### V0. Evidence Lock

Type: no-code / test-planning / manual evidence update.

Owns:

- manual QA checklist update for Stage V baseline;
- inspect evidence expectations;
- failure classification table.

Must not:

- fix implementation bugs;
- broaden old-session compatibility;
- run tests against unimplemented Stage V features.

### V1. Branch-aware Memory Resolver And Writer Context

Likely backend files:

- `backend/rp/services/branch_visibility_resolver.py`
- `backend/rp/services/context_orchestration_service.py`
- `backend/rp/services/memory_inspection_service.py`
- `backend/rp/services/story_runtime_debug_query_service.py`
- `backend/rp/services/story_session_service.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/retrieval_broker.py`
- `backend/rp/services/core_state_read_service.py`
- new or existing Core State as-of resolver / snapshot manifest service files
- `backend/rp/models/memory_contract_registry.py`
- `backend/rp/models/story_runtime.py`
- `backend/models/rp_core_state_store.py`
- `backend/models/rp_story_store.py`

Likely tests:

- `backend/rp/tests/test_memory_lineage_services.py`
- new or existing Core State as-of manifest tests
- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py`
- `backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py`
- `backend/rp/tests/test_projection_builder_services.py`

Completion criteria:

- one branch read scope builder is reused by writer context, Memory inspection,
  runtime inspect, runtime-owned Recall search, RetrievalBroker runtime calls,
  and debug/eval reads;
- branch from turn `N` keeps pre-fork memory visible and excludes source-branch
  post-`N` memory from writer context;
- rollback hides later Workspace/Recall/retrieval material from default runtime
  reads;
- `current_state_digest` / `recent_segment_digest` / projection-like packet
  fields are branch-scoped or explicitly omitted with reason;
- Core State runtime reads use turn-bound snapshot manifests and object
  revisions rather than latest current rows:
  - turn 0 / activation creates an initial manifest;
  - turns without Core mutation reuse the previous manifest;
  - Core-mutating turns create complete changed-object revisions plus a new
    manifest;
  - branch from turn `N` inherits turn `N`'s manifest;
  - branch-local Core mutation creates branch-scoped revisions and a new
    branch-local manifest;
  - old sessions without turn-bound Core history are marked compatibility-only
    for historical as-of reads instead of receiving fabricated history;
- runtime product reads reject `accepted_segment_ids_json`, legacy artifact
  metadata, and output-ref reverse lookup as truth fallbacks; exact
  `runtime_turn_id` / `runtime_branch_head_id` ownership remains mandatory for
  runtime-produced story artifacts;
- tests prove no hidden future memory leaks into writer packet/read manifest;
- tests prove a branch from turn 2 after a turn 3 Core change reads the turn 2
  Core manifest, not the latest Core current row.

### V2. Backend Memory Product Contract

Likely backend files:

- `backend/api/rp_story.py`
- `backend/rp/services/story_runtime_controller.py`
- `backend/rp/services/memory_inspection_service.py`
- `backend/rp/services/story_block_mutation_service.py`
- `backend/rp/services/recall_lifecycle_service.py`
- `backend/rp/services/archival_evolution_service.py`
- `backend/rp/models/memory_inspection.py`
- `backend/rp/models/core_mutation.py`
- `backend/rp/models/recall_lifecycle.py`
- `backend/rp/models/archival_evolution.py`

Likely tests:

- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py`
- `backend/rp/tests/test_memory_inspection_service.py`
- `backend/rp/tests/test_story_evolution_service.py`
- `backend/tests/test_rp_story_api.py`

Completion criteria:

- `/memory/inspection` returns canonical `blocks` / `entries` envelopes for
  Core, Projection, Workspace, Recall, and Archival where available;
- direct Core edit action validates identity/base refs and routes through the
  shared mutation path;
- Recall actions route through lifecycle service and reject cross-story or
  non-visible refs fail-closed;
- Archival evolution routes through version/reindex governance and defaults to
  current-branch visibility;
- API responses include receipts that can refresh the Memory UI and runtime
  inspect surfaces.

### V3. Frontend Memory Product Surface

Likely frontend files:

- `lib/services/backend_story_service.dart`
- `lib/models/story_runtime.dart`
- `lib/pages/longform_story_page.dart`
- new `lib/widgets/story_memory_panel.dart` or equivalent
- existing `lib/widgets/story_runtime_inspection_sheet.dart` only for debug
  references, not as the main product editor.

Completion criteria:

- product UI has an explicit Memory entrypoint;
- users can switch/read Memory layers and domains;
- UI renders canonical block/entry envelopes without inventing ad hoc shapes;
- allowed actions drive visible controls;
- Core edit form sends base revision and operations;
- Recall/Archival actions show receipt and refresh the view;
- branch identity / cutoff turn is visible enough for users to understand which
  line they are editing.

### V4. Writer Brainstorm Apply

Likely backend files:

- new or existing brainstorm model/service files under `backend/rp/models/` and
  `backend/rp/services/`
- `backend/rp/services/worker_scheduler_service.py`
- `backend/rp/services/worker_execution_service.py`
- `backend/rp/services/story_runtime_controller.py`
- `backend/api/rp_story.py`

Likely frontend files:

- `lib/pages/longform_story_page.dart`
- Memory panel / discussion panel widgets.

Contract sketch:

```python
class BrainstormSession(BaseModel):
    brainstorm_id: str
    identity: MemoryRuntimeIdentity
    status: Literal["open", "summarized", "reviewing", "dispatched", "closed"]
    items: list[BrainstormItem] = Field(default_factory=list)


class BrainstormItem(BaseModel):
    item_id: str
    summary_text: str
    evidence_text_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    user_edited: bool = False
    status: Literal[
        "proposed",
        "edited",
        "rejected",
        "confirmed",
        "dispatched",
        "applied",
        "pending_review",
        "conflict",
        "failed",
    ]


class BrainstormApplyRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    items: list[BrainstormItem]
    reason: str | None = None
```

`BrainstormItem` must not contain `target_layer`, `target_domain`,
`operation_kind`, `intent_labels`, or other governed routing fields.
Brainstorm is responsible for summarizing what the user may want to change.
The scheduler/dispatcher is responsible for classifying items and planning
memory-layer work.

Brainstorm summary creation should use the common Context Engineering /
Compact-Summary operation contract once that common module is extracted by the
setup agent dev session. Until then, V4 may implement only the story runtime
adapter contract and must not create a second generic compact engine under
story runtime.

The scheduler output may carry layer/domain/operation routing:

```python
class BrainstormDispatchPlanItem(BaseModel):
    source_item_id: str
    target_layer: Literal["core"]
    target_domain: str
    operation_kind: str
    worker_id: str
    worker_input: dict[str, Any] = Field(default_factory=dict)
```

V4 first version is Core-oriented. Scheduler routing is still kept in the
dispatch layer because the scheduler owns worker/domain planning, but this
brainstorm path must only dispatch Core-oriented work. Non-Core wishes should
return review/redirect material instead of becoming brainstorm edits. Recall
changes normally remain lifecycle review actions, and Archival changes go
through Story Evolution / version / reindex governance.

The Core worker result should use the minimum field-level executable structure:

```python
class BrainstormCoreFieldChange(BaseModel):
    source_item_id: str
    target_ref: str
    base_revision: str
    operation: Literal["replace_field", "set_field", "delete_field"]
    field_path: str
    new_value: Any
    reason: str | None = None
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
```

Rules:

- `source_item_id` is required and points to a confirmed `BrainstormItem`;
- `target_ref`, `base_revision`, `operation`, `field_path`, and `new_value` are
  required because apply / proposal / conflict checks need executable data;
- `old_value` is not produced by the LLM; backend fills it deterministically
  from `base_revision + field_path`;
- `reason` is optional and should not be generated by default unless user text
  already contains a short reason, review/proposal UI needs it, conflict/refusal
  reporting needs it, or debug/eval mode requests it;
- full `source_refs` are optional until brainstorm discussion message ids /
  transcript anchors are stable.

Lifecycle:

- `BrainstormSession` starts when the user sends the first brainstorm prompt;
- ordinary discussion keeps the session open and does not create items;
- if the user returns to writing without changes, close the session as no-op;
- explicit summarize/apply action runs a dedicated `brainstorm_summarize`
  structured prompt over the session discussion;
- generated items are user-editable before dispatch;
- only confirmed items enter scheduler / worker execution.

Completion criteria:

- brainstorm discussion produces structured items, not direct memory writes;
- brainstorm session and item state are persisted with Runtime Workspace
  semantics, not as Core / Recall / Archival truth;
- brainstorm items stay memory-layer agnostic and do not decide Core / Recall /
  Archival routing;
- brainstorm summary output is produced by an explicit summary/apply action,
  not by automatic hidden judgment during ordinary writer discussion;
- user can edit/reject/confirm items;
- confirmed items go to scheduler/dispatcher for classification;
- scheduler/dispatcher routes Core-classified work to the appropriate Core
  memory-domain worker and does not dispatch Recall/Archival brainstorm edits;
- non-Core wishes produce review/redirect receipts rather than memory mutation
  through V4 brainstorm;
- worker-produced Core operations use minimal executable field changes and
  apply with `origin_kind=brainstorm_summary_apply`;
- backend fills `old_value` from base revision and rejects stale-base /
  conflict cases before apply;
- worker permission decides auto-apply / proposal / review receipt behavior;
- receipts are inspectable and traceable back to `brainstorm_id` and
  `source_item_id`.

### V5. Post-write Memory Maintenance Minimum Closure

Likely backend files:

- `backend/rp/services/post_write_governance_service.py`
- `backend/rp/services/worker_memory_service.py`
- `backend/rp/services/projection_refresh_service.py`
- `backend/rp/services/recall_lifecycle_service.py`
- `backend/rp/services/archival_evolution_service.py`
- `backend/rp/services/runtime_workflow_job_service.py`
- `backend/rp/services/context_orchestration_service.py`

Completion criteria:

- `projection.refresh` actually reaches projection refresh service when policy
  and request require it;
- Recall/Archival materialization jobs are no longer silent placeholders for
  the next writer turn;
- deferred jobs include user/debug-visible reason and cannot be read as
  completed memory;
- writer packet/read manifest records completed, omitted, stale, hidden, and
  deferred memory refs distinctly.

## 3. Parallelism Plan

Default: one implement agent at a time for Stage V because V1 is a dependency
for V2/V3/V4/V5.

Allowed parallelism after V1 passes module-level check:

- V2 backend contract and V3 frontend UI may run in parallel only if V2 freezes
  the DTO/action surface first and V3 owns only Dart files against that frozen
  surface.
- V4 brainstorm apply should not start until V2's Core/Recall/Archival action
  contracts are stable.
- V5 post-write maintenance can start in parallel with V3 only if it touches
  backend maintenance services and does not change the Memory UI DTO.

At most two subagents may run at once.

## 4. Verification Plan

Backend focused tests:

```powershell
python -m pytest backend\rp\tests\test_memory_lineage_services.py -q
python -m pytest backend\rp\tests\test_story_runtime_controller_memory_read_side.py -q
python -m pytest backend\rp\tests\test_story_runtime_product_wiring_writer_constraints.py -q
python -m pytest backend\tests\test_rp_story_api.py -q
```

Frontend focused checks:

```powershell
flutter analyze lib\models\story_runtime.dart lib\services\backend_story_service.dart lib\pages\longform_story_page.dart
```

Slice-local lint/type:

```powershell
ruff check <touched backend files>
mypy --follow-imports=skip --check-untyped-defs <touched backend files>
```

Manual QA must be limited to implemented Stage V scope and must record expected
visible behavior, not just API availability.

## 5. Failure Classification

| Failure | Classification | Route |
|---|---|---|
| Writer sees source-branch future memory after fork | V1 bug | Fix resolver/context scoping |
| Branch from turn N sees later-turn Core field values | V1 bug | Fix Core State as-of manifest/revision read |
| Memory panel edits wrong branch | V1/V3 blocker | Fix branch scope before UI acceptance |
| Core edit bypasses event/dirty/projection path | V2 bug | Fix mutation kernel routing |
| Recall action deletes raw chunks | V2 bug | Route through lifecycle service |
| Archival edit overwrites active source in place | V2 bug | Route through Evolution/version/reindex |
| Brainstorm writes Core directly | V4 bug | Route through confirmed summary apply |
| Next writer turn reads deferred materialization as completed | V5 bug | Fix job/read manifest semantics |
| Old session has malformed outline/legacy metadata | Out of Stage V | Do not treat as Stage V blocker unless user reopens migration scope |

## 6. Grill Gate

Implementation may pause for grill only if all are true:

- task docs/specs do not answer the behavior;
- local mature references under `docs/research` do not provide a safe pattern;
- Python/framework ecosystem search does not reveal a suitable reusable
  approach;
- the unresolved point changes product semantics, data contracts, or user
  governance.

Known draft-v1 position:

- no grill blocker before V0/V1;
- no grill blocker before V2 backend contract hardening;
- V4 no longer has a `BrainstormItem` taxonomy grill: brainstorm summary items
  are memory-layer agnostic by contract. If implementation needs a taxonomy
  decision, it belongs to scheduler/dispatcher output, not the brainstorm item.
