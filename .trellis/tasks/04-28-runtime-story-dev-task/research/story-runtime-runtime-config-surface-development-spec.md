# Story Runtime Runtime Config Surface Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Runtime Config Surface / Snapshot Publish / Control History
>
> Status: development-spec-v1

## 1. Scope

This spec turns the confirmed runtime config discussion into an implementation-ready slice.

It covers:

- runtime panel edits that change how the system runs;
- compile / publish / activate of a new `RuntimeProfileSnapshot`;
- control history for config changes;
- turn-start snapshot pinning and in-progress job stability;
- minimal frontend/backend API shape for runtime config editing.

It does not cover:

- story content edits;
- Core State / Recall / Archival mutation semantics;
- branch / rollback story visibility;
- full registry marketplace or worker plugin UI;
- Langfuse runtime config.

## 2. Design Rules

Runtime config is a control-plane feature.

- It changes worker enablement, permissions, provider/model selection, retrieval policy, context window, packet/token budget, manual refresh triggers, and scheduling frequency.
- It does not become a story `Turn`.
- It does not participate in story rollback.
- It creates a control-history receipt and publishes a new immutable `RuntimeProfileSnapshot`.
- New snapshots affect future turns only.
- Turns and pending post-write jobs already started continue using the snapshot they pinned at creation.

## 3. Suggested Files

Backend:

- `backend/rp/models/runtime_config_contracts.py`
- `backend/rp/services/runtime_config_control_service.py`
- `backend/rp/services/runtime_profile_snapshot_service.py`
- `backend/rp/services/story_runtime_controller.py`
- `backend/api/rp_story.py`

Frontend:

- runtime config page or panel under the story runtime surface
- typed model next to existing story runtime frontend models

Tests:

- `backend/rp/tests/test_runtime_config_control_service.py`
- existing runtime profile snapshot tests
- API tests under `backend/tests/test_rp_story_api.py`

## 4. DTOs

```python
class RuntimeConfigPatchRequest(BaseModel):
    session_id: str
    actor_id: str | None = None
    expected_active_snapshot_id: str | None = None
    worker_overrides: dict[str, Any] = Field(default_factory=dict)
    permission_overrides: dict[str, Any] = Field(default_factory=dict)
    retrieval_policy_patch: dict[str, Any] = Field(default_factory=dict)
    context_policy_patch: dict[str, Any] = Field(default_factory=dict)
    packet_policy_patch: dict[str, Any] = Field(default_factory=dict)
    model_profile_patch: dict[str, Any] = Field(default_factory=dict)
    scheduling_policy_patch: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
```

```python
class RuntimeConfigControlReceipt(BaseModel):
    receipt_id: str
    session_id: str
    previous_snapshot_id: str | None
    published_snapshot_id: str
    changed_fields: list[str]
    actor_id: str | None
    created_at: datetime
    source: Literal["runtime_config_panel", "migration", "system_default"]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

## 5. Service Contract

```python
class RuntimeConfigControlService:
    def preview_patch(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> RuntimeConfigPreview: ...

    def publish_patch(
        self,
        request: RuntimeConfigPatchRequest,
    ) -> RuntimeConfigControlReceipt: ...

    def list_control_history(
        self,
        *,
        session_id: str,
    ) -> list[RuntimeConfigControlReceipt]: ...
```

`publish_patch()` must:

1. load the current active snapshot;
2. validate optimistic concurrency when `expected_active_snapshot_id` is provided;
3. compile a new snapshot from previous compiled profile plus validated patch inputs;
4. publish / activate the new snapshot atomically for future turns;
5. persist a control-history receipt;
6. return the new snapshot id and changed fields.

## 6. Validation

Reject with stable errors:

- `runtime_config_patch_empty`
- `runtime_config_snapshot_conflict`
- `runtime_config_unknown_worker`
- `runtime_config_unknown_domain`
- `runtime_config_invalid_permission_level`
- `runtime_config_invalid_model_profile`
- `runtime_config_invalid_budget`
- `runtime_config_compile_failed`

Validation must be fail-closed. A malformed patch must not partially publish a snapshot.

## 7. Integration Rules

- `StoryTurnDomainService` and graph runner must continue pinning snapshot at turn start.
- Runtime config publish must not mutate existing `RuntimeProfileSnapshotRecord.compiled_profile_json`.
- Runtime config publish must not rewrite existing `Turn`, `RuntimeWorkspaceMaterial`, worker result, retrieval usage, or graph checkpoint binding records.
- Pending post-write jobs keep the snapshot id captured in their job identity.

## 8. Tests Required

Backend tests:

1. Publishing a patch creates a new snapshot and supersedes the previous active snapshot.
2. Existing snapshot compiled profile remains unchanged after publish.
3. A turn started before publish keeps its original `runtime_profile_snapshot_id`.
4. A pending post-write job created before publish keeps its original snapshot.
5. Unknown worker/domain/permission/model/budget patches reject without publishing.
6. Control history can be read by session and links previous/new snapshot ids.
7. Story rollback does not remove or revert runtime config control history.

Frontend tests:

1. Runtime config panel reads current effective snapshot summary.
2. Save calls publish endpoint and refreshes displayed active snapshot id.
3. Invalid patch surfaces validation error without changing local active snapshot display.

## 9. Out of Scope

- Full registry CRUD UI.
- Worker marketplace.
- Runtime config rollback through story rollback.
- Branch-specific runtime config inheritance rules beyond current active session snapshot publish.

