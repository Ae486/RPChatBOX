# Projection Refresh Write Contract Slice Plan

## Objective

Strengthen `ProjectionRefreshService` from a mirror/snapshot updater into a first-class derived projection write path.

The slice must keep projection as `Core State.derived_projection` maintenance. It must not mutate `Core State.authoritative_state`, rewrite proposal/apply, add a public tool, or create a new durable truth store.

## Existing Code Anchors

- `backend/rp/services/projection_refresh_service.py`
- `backend/rp/services/core_state_dual_write_service.py`
- `backend/models/rp_core_state_store.py`
- `backend/rp/tests/test_core_state_dual_write_services.py`
- `backend/rp/services/memory_change_event_service.py`

## Implementation Steps

1. Add a small `ProjectionRefreshRequest` DTO and stable `ProjectionRefreshServiceError`.
2. Thread the request through `ProjectionRefreshService.refresh_from_bundle`.
3. Validate stale projection base revision before any mirror/formal write.
4. Validate supplied authoritative source refs against current formal Core State revision.
5. Store refresh actor, reason, base revision, source refs, dirty targets, and dirty state in projection current/revision `metadata_json`.
6. Publish a lightweight `projection_refreshed` event only when identity and event service are supplied.
7. Preserve legacy no-request behavior.

## Validation

Focused module tests should prove:

- no-request legacy refresh remains valid;
- metadata persists on current and revision rows;
- stale base revision is rejected before write;
- stale authoritative source revision is rejected before write;
- optional event spine publication carries dirty targets.

Module-level tests must stay hermetic and must not start retrieval / embedding / optional eval dependencies. End-to-end tests may start the full stack separately.
