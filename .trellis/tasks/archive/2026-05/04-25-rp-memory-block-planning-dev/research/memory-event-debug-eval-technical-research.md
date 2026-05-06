# Memory Event Debug Eval Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Goal: lock the useful design decisions for full-foundation memory trace/debug/eval reads before writing the backend spec.

## 1. Current Repo Evidence

Current code and spec anchors:

- `backend/rp/services/memory_change_event_service.py`
- `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md`
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`
- `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
- `backend/rp/services/proposal_repository.py`
- `backend/rp/services/provenance_read_service.py`
- `backend/rp/services/memory_inspection_read_service.py`

What is already strong enough to reuse:

1. event DTO shape is already correct: identity, source refs, dirty targets, visibility effect.
2. boot-bar planning already splits “persistent event store” from “debug/eval read surfaces”.
3. persistent Runtime Workspace materials, proposal receipts, and read manifests are already the right evidence sources for trace reads.

What is still missing:

1. one trace bundle that joins events, workspace materials, proposals, and read manifests under exact identity;
2. query surfaces for branch trace, source trace, proposal trace, and material trace;
3. eval-friendly readback that survives process restart.

## 2. Reuse Decision

Keep and extend:

- persistent memory event records as the trace spine;
- persistent Runtime Workspace records as the main turn-material evidence surface;
- proposal/apply receipts and provenance reads as mutation evidence;
- deterministic read manifests as packet/read evidence.

Do not add:

- event replay as a truth-rebuild mechanism;
- trace APIs that only key by `session_id`;
- a second debug store that copies the same evidence again.

Why:

- the evidence is already distributed across the right stores;
- the missing capability is joined readback and exact-identity queryability.

## 3. Mature Wheel / Framework Decision

No external tracing framework is worth adopting for this slice.

Reason:

- OpenTelemetry/Langfuse style runtime traces are useful for model/request observability, but they are not the product truth for memory-layer provenance;
- the required answer is product-grounded trace queries over existing memory evidence, not generic span storage.

## 4. Spec Consequences

The full-foundation trace/debug/eval spec should:

1. define read-only backend services over persisted memory evidence;
2. require exact identity as the primary query key;
3. allow secondary queries by branch, source ref, proposal id, material ref, and generated artifact ref;
4. keep all outputs trace-only and non-authoritative;
5. explicitly join:
   - persistent events
   - Runtime Workspace materials
   - proposal/apply receipts
   - deterministic read manifests
   - retrieval usage records when present

## 5. Rejected Alternatives

Rejected: use generic observability spans as the authoritative memory debug bundle.

- Those spans are useful adjuncts, not the durable product contract.
- They do not naturally model branch visibility or governed mutation provenance.

Rejected: expose only raw event rows and leave joining to callers.

- Eval and future UI would then re-implement the same joining logic repeatedly.
- The backend should provide a stable trace read surface, not only raw tables.
