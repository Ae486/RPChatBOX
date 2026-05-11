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
- `backend/rp/models/memory_contract_registry.py`
- `backend/rp/models/story_runtime.py`

Likely tests:

- `backend/rp/tests/test_memory_lineage_services.py`
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
- runtime product reads reject `accepted_segment_ids_json`, legacy artifact
  metadata, and output-ref reverse lookup as truth fallbacks; exact
  `runtime_turn_id` / `runtime_branch_head_id` ownership remains mandatory for
  runtime-produced story artifacts;
- tests prove no hidden future memory leaks into writer packet/read manifest.

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
class BrainstormItem(BaseModel):
    item_id: str
    target_layer: Literal["core", "recall", "archival"]
    target_domain: str
    suggested_operation: str
    summary_text: str
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    status: Literal["proposed", "edited", "rejected", "confirmed"]


class BrainstormApplyRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    items: list[BrainstormItem]
    reason: str | None = None
```

Completion criteria:

- brainstorm discussion produces structured items, not direct memory writes;
- user can edit/reject/confirm items;
- confirmed Core items apply with `origin_kind=brainstorm_summary_apply`;
- Recall/Archival items route through lifecycle/evolution services;
- receipts are inspectable and traceable back to the brainstorm source refs.

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
- V4 has one deferred grill candidate: whether `BrainstormItem` first version
  should use a small closed enum taxonomy or an extensible label/action
  taxonomy. Resolve this before V4 DTO implementation if existing docs and
  references cannot determine the safer contract.
