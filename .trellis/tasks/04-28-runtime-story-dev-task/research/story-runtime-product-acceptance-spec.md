# Story Runtime Product Acceptance Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase Q / Runtime Product Acceptance / User-facing Integration Gate
>
> Status: draft-v1

## 1. Purpose

Phase Q is the acceptance gate after the runtime foundation work.

It does not start a new feature family. It proves that the capabilities already
implemented in phases A-P can be reached through realistic product paths and can
be debugged when they fail.

The main question for Q is:

> Can a user-facing longform runtime flow exercise the new runtime contracts
> without falling back to old MVP truth, leaking sidecars, losing branch identity,
> or requiring engineers to inspect private payload internals?

## 2. Scope

Q covers:

1. A scenario-based product acceptance matrix for the current longform runtime.
2. Thin API/frontend wiring checks for already implemented runtime surfaces.
3. Debug/read verification that joins runtime config, story evolution, chapter
   bridge, revision overlay, sidecars, read manifests, and branch identity.
4. Regression tests that run through product-like flows rather than only isolated
   service tests.
5. A manual QA checklist that can be reused before entering a larger product
   feature such as full branch UI, SuperDoc/WebView editing, or active RP/TRPG
   runtime.

The acceptance work should reuse existing runtime routes and surfaces whenever
possible. In particular, debug/read checks should bind to the current
`/api/rp/story-sessions/{session_id}/runtime/inspect` route instead of creating
a new debug panel or a second inspection truth store.

Q does not cover:

1. Complete branch tree UI, branch merge, branch physical purge, or branch
   comparison UX.
2. Complete roleplay/TRPG active runtime behavior.
3. SuperDoc/WebView integration or replacing the current minimal Flutter review
   surface.
4. Full eval runner, eval cases, grader, or benchmark dashboards.
5. A new worker catalog marketplace or arbitrary plugin manager.
6. New story truth semantics. Q only validates and lightly wires existing
   contracts.

## 3. Acceptance Scenarios

### Q-A. Longform Write / Review / Rewrite / Adopt / Continue

The scenario must prove:

1. A user write command reaches the writer packet.
2. The writer produces a draft `story_segment`.
3. Draft content is materialized into document blocks.
4. The user can add review overlay data: comments and tracked changes.
5. A rewrite request carries the overlay into writer-visible structured fields.
6. Rewrite candidate creation does not mutate canonical story truth.
7. Selection remains reversible and is not adoption.
8. `accept_and_continue` creates the adoption receipt and updates the canonical
   continuation base.
9. The next write uses the adopted candidate, not an unadopted selected or visible
   candidate.

Automation focus:

| Item | Preferred check style |
|---|---|
| 1-3 | backend/API + fixture-backed assertions |
| 4-7 | backend/API assertions with existing review overlay services |
| 8-9 | backend assertions on existing accept/continue command mapping |

### Q-B. Chapter Completion / Bridge / Next Chapter Packet

The scenario must prove:

1. `complete_chapter` consumes only adopted draft, accepted outline, and chapter
   goal inputs.
2. Pending rewrite candidates without adoption fail closed.
3. Chapter bridge material is stored as branch-scoped Runtime Workspace material.
4. The next chapter packet reads the matching active-branch bridge for the target
   chapter.
5. Sibling branch pending revision or chapter bridge material does not leak.

Automation focus:

| Item | Preferred check style |
|---|---|
| 1-5 | backend service/API assertions |

### Q-C. Runtime Config Hot Update

The scenario must prove:

1. Runtime config patch publishes a new immutable `RuntimeProfileSnapshot`.
2. Control history links previous and published snapshot ids.
3. Existing turn/job snapshot pins do not drift.
4. New snapshot affects only future turns.
5. Story rollback does not revert runtime config control history.

Automation focus:

| Item | Preferred check style |
|---|---|
| 1-5 | backend/service/API assertions |

### Q-D. Story Evolution / Retrieval Visibility

The scenario must prove:

1. Archival evolution creates version/supersession/reindex evidence.
2. Default visibility is current branch.
3. Selected branches reject unknown or cross-story branch ids.
4. Retrieval excludes hidden or superseded evolved chunks.
5. Debug/read surfaces expose evolution receipts, memory events, dirty targets,
   reindex jobs, and source refs without treating those traces as story truth.

Automation focus:

| Item | Preferred check style |
|---|---|
| 1-4 | backend service assertions |
| 5 | `/runtime/inspect` assertions |

### Q-E. Mode Sidecar / Rule Card Isolation

The scenario must prove:

1. Roleplay/TRPG mode descriptors compile into the pinned snapshot.
2. `RULE_CARD` and `RULE_STATE_CARD` are Runtime Workspace sidecars, not Core,
   Recall, or Archival truth.
3. A packet without explicit `context_requirements.sidecar_slot_ids` has empty
   `sidecar_refs`.
4. Rule cards do not leak through generic `workspace_refs`.
5. Debug/read manifest classifies mode sidecars only through stable
   `section_family`, `source_kind`, or `section_id`, never through labels.

Automation focus:

| Item | Preferred check style |
|---|---|
| 1-5 | backend packet/debug assertions |

### Q-F. Debug Bundle / Read Surface

The scenario must prove:

1. A single inspect/debug bundle can answer what happened in the flow.
2. The bundle includes, when applicable:
   - runtime config control history;
   - story evolution items;
   - chapter bridge materials;
   - mode sidecars;
   - writer packet summary;
   - read manifests;
   - runtime workspace materials;
   - branch/head/turn/profile identity.
3. Reads remain exact-identity or explicitly branch scoped.
4. The read surface is read-only and does not create new truth.

Acceptance route:

- `GET /api/rp/story-sessions/{session_id}/runtime/inspect`
- no new debug panel in Q

## 4. Product Boundary

Q is intentionally a gate before larger product work.

If Q passes, the project may choose the next product direction from:

1. SuperDoc/WebView revision editor integration.
2. Full branch UI and branch management.
3. Active roleplay/TRPG runtime behavior.
4. Eval runner integration over the existing debug/read surfaces.

If Q fails, the next work should fix the acceptance gap before adding a larger
feature family.

## 5. Required Evidence

Q is not complete until it has:

1. An automated acceptance/regression test or test group for the scenarios that
   can be automated cheaply.
2. A manual QA checklist for product paths that require UI interaction or visual
   confirmation.
3. A debug/read evidence sample or assertion set showing that the runtime can be
   inspected without private payload spelunking.
4. Updated execution plan status.

## 6. Resolved Boundaries

- Q does not add a new user-facing debug panel.
- Q does not add a new public mutation command.
- `accept_and_continue` is the semantic acceptance name and maps to the existing
  `accept_pending_segment` / Accept & Continue flow.
- Q1 product-like backend acceptance should prefer API/controller paths when a
  route already exists. Service fixtures are allowed only for contracts that do
  not yet have a complete product/UI path, such as sidecar isolation.
- Q-C does not require product rollback UI.
- Q-E does not require active RP/TRPG roleplay or rule execution.
- Q-F is the existing `/runtime/inspect` route. Missing read-only fields may be
  added to that route; a second debug truth store must not be created.
- Q3 manual QA is required for Q completion.

## 7. Deferred Grill Candidates

These questions are intentionally deferred until after Q acceptance:

1. Should the next product feature after Q be SuperDoc/WebView revision editing,
   full branch UI, or active RP/TRPG runtime?
2. If a future product debug panel is needed, should it live in the longform page,
   a separate developer tool, or the memory inspection surface?
