# RP Memory Hierarchy Planning to Block Development

## Goal

Use the real Trellis workflow to move RP Memory OS from the current Core State migration state toward a Block-container-compatible architecture. The first implementation stage must preserve the already-settled memory hierarchy and business boundaries while giving Core State a stable Block envelope that future compile, attach, dirty/fan-out, and visibility work can build on.

## What I Already Know

- The active Trellis task is `.trellis/tasks/04-25-rp-memory-block-planning-dev`.
- Current `.trellis/spec/` only contains frontend and shared thinking guides; there is no backend or memory-specific Trellis spec yet.
- The authoritative memory hierarchy is:
  - `Core State`
    - `authoritative_state`
    - `derived_projection`
  - `Recall Memory`
  - `Archival Knowledge`
  - `Runtime Workspace`
- `Core State` owns "current truth and current view"; `Recall Memory` owns past history; `Archival Knowledge` owns durable knowledge/source material; `Runtime Workspace` owns turn-local execution material.
- `current_state_json` is the current compatibility mirror for active-story authoritative Core State fields on `StorySession`.
- `builder_snapshot_json` is the current compatibility mirror for settled writer-facing projection slots on `ChapterWorkspace`.
- The formal Core State store already exists:
  - `rp_core_state_authoritative_objects`
  - `rp_core_state_authoritative_revisions`
  - `rp_core_state_projection_slots`
  - `rp_core_state_projection_slot_revisions`
- Existing code already has repository, dual-write, backfill, read-side, version/provenance, inspection, and API metadata support for Core State formal-store migration.
- The Block proposal is directionally useful, but the review/alignment document narrows it:
  - Do not replace `Recall` / `Archival` retrieval-core storage with Block tables.
  - Do not replace `WritingPacketBuilder` with generic `Memory.compile()`.
  - Do not put setup runtime-private cognition into durable Memory OS.
  - Fan-out must be driven by active durable state/block revision and attached-consumer dirty flags, not by `SetupWorkspace` changes directly.

## Requirements

- Preserve the frozen Memory OS hierarchy and its layer responsibilities.
- Treat Core State as the first Block-compatible landing zone.
- Keep `Recall Memory` and `Archival Knowledge` on the existing retrieval-core object chain.
- Keep `WritingPacketBuilder` as the deterministic writer packet boundary.
- Keep setup runtime-private cognition in setup runtime state services, outside durable story Memory OS.
- Provide an implementation path that starts from read-only Block envelope views over existing Core State rows/mirrors before adding new storage or mutation machinery.
- Keep compatibility mirror behavior intact while formal store migration is still guarded by feature flags.
- Record task-specific backend/memory context under this Trellis task because the global Trellis spec does not yet contain it.

## Acceptance Criteria

- [x] `prd.md` captures the agreed Core State first / Block envelope direction.
- [x] `research/current-memory-context.md` records current docs, code anchors, and Block boundary decisions.
- [x] `implement.jsonl` and `check.jsonl` contain real curated context entries, not only seed examples.
- [x] User confirms the first implementation stage boundary before code changes.
- [x] First implementation stage adds a focused Block envelope/read-model slice without new broad storage rewrites.
- [x] Tests prove the new envelope preserves authoritative/projection identity, revision, scope, and route metadata.
- [x] Existing Core State tests still pass.
- [x] `trellis-check` is performed after implementation and before finish/spec update.

## Technical Approach

### Recommended Phase 1: Read-Only Block Envelope over Core State

Add a small backend model/service layer that presents existing Core State authoritative objects and projection slots as typed `RpBlock`-style envelopes. This gives future code a stable container shape while keeping current storage, proposal/apply, retrieval, setup cognition, and writer packet boundaries unchanged.

Expected shape:

- `block_id`: derived from the formal row id when present, or a deterministic compatibility id when reading from mirror fallback.
- `label`: exact object identity such as `chapter.current` or `projection.current_outline_digest`.
- `layer`: existing `Layer` enum value.
- `domain`: existing `Domain` enum value.
- `domain_path`: exact domain path.
- `scope`: `story`, `chapter`, or future scope.
- `revision`: current revision.
- `payload_schema_ref`: pass-through when formal store has it.
- `data_json` or `items_json`: payload preserved without lossy prompt rendering.
- `metadata`: route/source fields such as `core_state_store` or `compatibility_mirror`.

### Later Phases

- Phase 2: Attach/consumer registry and dirty flag design for active story consumers.
- Phase 3: Internal memory compiler for setup/orchestrator/specialist contexts only; keep writer packet independent.
- Phase 4: Governed Block mutation paths that delegate authoritative changes to proposal/apply instead of bypassing it.
- Phase 5: Visibility/API/UI improvements over Block envelopes, versions, provenance, and pending proposals.

## Decision (ADR-lite)

**Context**: Letta shows that Block + compile + attach/fan-out is a useful memory runtime backbone. This project already has a more domain-specific Memory OS design and has recently implemented a formal Core State store.

**Decision**: Start by implementing Block compatibility as a read-only envelope/read model over Core State authoritative/projection objects. Do not introduce a new `rp_blocks` table, Block mutation API, fan-out, or compiler replacement in the first stage.

**Consequences**: The code gains a stable container abstraction without destabilizing current migration flags or business boundaries. More powerful Block behaviors remain possible, but only after the envelope identity and read-side contract are proven.

## Out of Scope

- Replacing retrieval-core tables for Recall/Archival.
- Replacing `WritingPacketBuilder`.
- Moving setup runtime-private cognition into durable Memory OS.
- Creating a new `rp_blocks` durable table in the first implementation stage.
- Adding Block edit tools that bypass proposal/apply.
- Implementing fan-out rebuild in the first implementation stage.
- Changing public UI semantics unless needed for visibility metadata tests.

## Open Questions

- Resolved: Phase 1 is frozen as read-only Block envelope over existing Core State store/mirrors, with no new `rp_blocks` table and no edit/fan-out/compiler replacement.

## Definition of Done

- Requirements and research are persisted in Trellis task files.
- User confirms the Phase 1 scope.
- Implementation follows the PRD and task research context.
- Relevant pytest targets pass.
- Trellis quality check is performed and findings are resolved or documented.
- Any new durable convention is considered for `.trellis/spec/` update.

## Research References

- `research/current-memory-context.md` - current Memory OS docs/code anchors, Core State status, Block boundaries, and implementation recommendation.
