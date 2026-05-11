# Story Runtime Product Wiring / Writer Constraint Closure Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase S / Product Wiring and Writer Constraint Closure
>
> Status: draft-v1

## 1. Purpose

Phase S exists because Phase Q backend acceptance and the first manual product
QA told different stories.

Q proved that many backend runtime contracts exist and can be exercised through
service/API-oriented tests. Manual QA proved that the actual longform product
path is not yet usable enough:

1. The longform frontend does not expose the runtime inspect/debug/read surfaces.
2. Runtime config, branch, mode, job/retrieval, and sidecar state are mostly not
   visible to the user.
3. Review comments and tracked changes can be saved, but `rewrite_pending_segment`
   does not feed them into the writer packet as hard rewrite constraints.
4. `write_next_segment` does not carry a strong chapter progress / previous
   accepted segment / next-beat constraint, so the writer can jump backward in
   the outline or ignore the immediately previous accepted prose.

Phase S must close those gaps before the runtime can be called product-usable.

## 2. Scope

Phase S covers two independent implementation modules plus one final product
acceptance module.

### S1. Backend Writer Constraint Closure

S1 makes the writer input truthful and testable:

1. `rewrite_pending_segment` must read the active review overlay for the target
   draft.
2. Active comments and tracked changes must become `WritingPacket.review_overlay_sections`.
3. If active review constraints exist but cannot be assembled, rewrite must fail
   closed instead of silently becoming a generic rewrite.
4. `write_next_segment` must include a writer-visible chapter progress section:
   accepted segment count, latest accepted segment excerpt, current chapter goal,
   accepted outline digest, and a direct continuity instruction.
5. The writer prompt must make the continuation constraint explicit:
   continue after the latest accepted segment; do not restart or rewrite already
   completed outline material.

### S2. Frontend Runtime Visibility

S2 makes runtime state visible in the product without building a large debug UI:

1. Add a minimal inspect/runtime read entry in the longform page.
2. Show current mode, active branch, selected turn, active snapshot, and warning
   state when available.
3. Expose runtime config history / current snapshot in a small read panel.
4. Show inspect summaries for writer packet, review overlay, chapter bridge,
   job ledger, retrieval, mode sidecars, and branch receipts when available.
5. Clarify candidate selection semantics in UI: viewing/selecting a candidate is
   not adoption; only Accept/Accept & Continue changes the continuation base.

### S3. Product Acceptance Re-run

S3 verifies the product path after S1/S2:

1. User adds a revision comment/tracked change.
2. User triggers rewrite.
3. Writer packet contains the review constraints.
4. Rewrite candidate is visible but not canonical.
5. User accepts one candidate.
6. Next write continues from the accepted candidate and the latest accepted
   segment, not from a stale outline beat.
7. Inspect panel can explain the above without private payload spelunking.

## 3. Non-goals

Phase S does not implement:

1. Full branch tree UI, branch merge, physical purge, or branch comparison UX.
2. Full mode switching or active roleplay/TRPG runtime.
3. SuperDoc/WebView integration.
4. A new debug truth store.
5. A new public mutation command for `accept_and_continue`.
6. A full eval runner or benchmark dashboard.

## 4. Product Rules

1. Backend service existence is not product acceptance.
2. A hidden route is not a product-visible capability.
3. Review UI is not complete until its constraints reach the writer packet.
4. Candidate selection is reversible and local until Accept commits adoption.
5. Inspect/read surfaces must remain read-only.
6. Runtime Workspace, review overlays, jobs, and inspect bundles are evidence,
   not canonical story truth.
7. Old longform MVP behavior can be bypassed when it prevents these rules from
   matching current task specs.

## 5. Required User-visible Outcomes

After Phase S:

1. The longform page has an obvious inspect/runtime read entry.
2. A tester can see enough runtime evidence to explain a write/rewrite/accept
   flow without opening database rows or private backend payloads.
3. A rewrite generated from a comment like "replace term X with term Y" receives
   that exact instruction in writer-visible packet content.
4. A continuation generated after accepting a candidate receives explicit
   previous accepted prose and chapter progress constraints.
5. Manual QA can distinguish:
   - product bug;
   - UI reachability gap;
   - backend contract gap;
   - out-of-scope future branch/mode/SuperDoc work.

## 6. Acceptance Criteria

### Backend

1. A real `rewrite_pending_segment` graph/domain path records or exposes a
   `WritingPacket` whose `review_overlay_sections` include active comments and
   tracked changes for the target draft.
2. The writer prompt rendered by `WritingWorkerExecutionService` includes review
   overlay content.
3. A real `write_next_segment` packet includes a chapter progress / continuity
   section that is not merely `writer_hints`.
4. Tests fail if review constraints exist but the packet omits them.
5. Tests fail if continuation packet has no latest accepted segment / chapter
   progress constraint when accepted segments exist.

### Frontend

1. `BackendStoryService` can fetch runtime inspect/debug/config history.
2. `LongformStoryPage` exposes a small read-only runtime panel.
3. The panel shows active branch, selected turn, active snapshot, mode, key
   warnings, and available inspect evidence.
4. Candidate selector copy makes adoption semantics clear.
5. No frontend action mutates runtime state through inspect/debug reads.

### Product

1. Manual QA can rerun the failing flow and see whether the writer received
   revision constraints.
2. Manual QA can inspect why a continuation used or failed to use the latest
   accepted segment.
3. Phase S does not claim full branch UI, full mode switching, or SuperDoc
   editing as complete.

## 7. Evidence From Manual QA

Manual QA found:

1. No visible inspect entry.
2. No visible branch UI beyond the revision surface.
3. No visible runtime config entry.
4. No mode selector or mode-specific surface.
5. Rewrite candidate generation ignored explicit revision instructions.
6. Continuation jumped backward in outline order and ignored local continuity.

These are blocking product acceptance findings. They override the previous Q2
assumption that no thin product/API wiring was needed.

