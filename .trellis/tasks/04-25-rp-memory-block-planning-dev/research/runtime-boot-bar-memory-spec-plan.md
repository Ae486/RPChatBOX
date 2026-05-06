# Runtime Boot Bar Memory Spec Plan

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: turn the repaired story-runtime memory blocker proposal into an ordered backend spec suite for the memory task, without losing any boot-bar or full-foundation requirement.

## 1. Planning Rules

- This remains a **memory task**. Documents under `.trellis/tasks/04-28-runtime-story-dev-task/research/` are requirement inputs, not a task switch.
- Use `.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-boot-bar-doc-index.md` as the single entrypoint for this documentation set.
- Every new spec is written only after a lightweight technical research pass:
  - check existing repo patterns first;
  - reuse mature frameworks/projects when they fit the frozen boundaries;
  - record why a wheel is reused or rejected.
- Existing memory strengthening specs remain valid foundation docs. New specs extend them; they do not replace them.
- The spec suite must cover both:
  - `runtime boot bar`: enough for the first story runtime implementation to connect to memory without writing the wrong architecture;
  - `full runtime foundation bar`: enough for memory to become the stable longform/roleplay/TRPG runtime base.

## 2. Inputs Used

Primary requirement inputs:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-spec-coding-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-technical-research-and-pseudocode.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-dependency-readiness-audit.md`

Existing backend spec baseline that must be reused:

- `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`
- `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
- `.trellis/spec/backend/rp-memory-change-event-spine.md`
- `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
- `.trellis/spec/backend/rp-projection-refresh-write-contract.md`
- `.trellis/spec/backend/rp-memory-temporal-materialization.md`

## 3. Existing Baseline vs New Spec Work

Already frozen well enough:

- registry vocabulary and bootstrap domain defaults
- `MemoryRuntimeIdentity` DTO skeleton
- in-process Runtime Workspace typed material contract
- in-process lightweight memory change event spine
- authoritative base revision conflict checks
- derived projection refresh freshness metadata
- memory layer ownership over Core / Projection / Recall / Archival / Runtime Workspace

Still missing as backend specs:

- persistent `BranchHead` / `StoryTurn` runtime identity
- minimal `RuntimeProfileSnapshot` compiler and pinning rules
- persistent Runtime Workspace records
- persistent event record foundation
- branch/rollback visibility resolver
- deterministic read manifest contract
- retrieval card / usage / promotion boot loop
- worker-facing permission/governance boot contract
- shared Core mutation kernel + direct-edit boot path
- later Recall / Archival / inspection / full registry completion specs

## 4. Ordered Backend Spec Suite

### 4.1 Runtime Boot Bar

| Order | Spec file | Status | Why now | Research anchors |
|---|---|---|---|---|
| 1 | `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md` | Write now | Persistent `BranchHead` / `StoryTurn` is the root anchor for every later read/write/search/material record. | LangGraph persistence boundary, Dolt/lakeFS copy-on-write semantics, current `rp_story_store.py` |
| 2 | `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md` | Write now | Turn-start pinning, retrieval policy pinning, permission/profile compilation must exist before runtime reads/writes depend on latest session config. | Current registry skeleton, retrieval runtime config service, Anthropic workflow guidance |
| 3 | `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md` | Written | Extends the current typed in-process material store into durable turn-scoped storage. | Existing Runtime Workspace spec, current service skeleton, SQLModel persistence pattern |
| 4 | `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md` | Written | Extends the current in-process event spine into persistent identity-scoped records needed by boot. | Existing event spine spec, Letta commit-style audit lesson |
| 5 | `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md` | Written | Makes Core / Projection / Workspace / Recall / Retrieval branch-aware by read contract. | LangGraph time-travel limit, Dolt/lakeFS lineage model, Letta git boundary |
| 6 | `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md` | Written | Freezes strict fact/view separation and deterministic read manifest fields for packets. | Current projection refresh/base-revision specs, writer packet boundary, read-manifest proposal |
| 7 | `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md` | Written | Gives writer retrieval a bounded boot loop without direct retrieval-to-Core writes. | Existing retrieval core, Runtime Workspace material kinds, story-runtime technical research |
| 8 | `.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md` | Written | Freezes the shared worker-facing memory service/permission path before workers touch Core. | Proposal/apply governance, registry defaults, profile compiler |
| 9 | `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md` | Written | Ensures user direct edit and worker mutation share one governed apply kernel. | Proposal/apply, base revision checks, direct-edit policy from blocker proposal |

### 4.2 Full Runtime Foundation

| Order | Spec file | Status | Why later |
|---|---|---|---|
| 10 | `.trellis/spec/backend/rp-recall-branch-aware-lifecycle.md` | Written | Recall governance depends on identity, visibility, persistent Workspace refs, and boot retrieval/source-ref contracts. |
| 11 | `.trellis/spec/backend/rp-archival-evolution-reindex-governance.md` | Written | Archival branch-local evolution must build on visibility, event trace, and promotion/source-ref contracts. |
| 12 | `.trellis/spec/backend/rp-memory-event-debug-eval-read-surfaces.md` | Written | Rich query/debug/eval surfaces extend the persistent event foundation after boot. |
| 13 | `.trellis/spec/backend/rp-registry-profile-snapshot-full-management.md` | Written | Full dynamic registry/profile management can follow once the minimal compiler is real and pinned. |
| 14 | `.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md` | Written | Full Core / Recall / Archival inspection/edit backend contracts should widen only after boot contracts are in place. |

## 5. Proposal Requirement Coverage Matrix

| Proposal requirement family | Spec coverage |
|---|---|
| `Turn / BranchHead / RuntimeProfileSnapshot` first-class persistence | `rp-runtime-identity-persistence-propagation.md`, `rp-runtime-profile-snapshot-minimal-compiler.md` |
| Runtime Workspace persistence and turn lifecycle | `rp-runtime-workspace-persistent-turn-material-store.md` |
| Persistent event record foundation | `rp-persistent-memory-event-record-foundation.md` |
| branch / rollback visibility across layers | `rp-branch-visibility-resolver-lineage.md` |
| strict Core fact vs Projection/View separation | existing `rp-core-state-base-revision-conflict-enforcement.md`, existing `rp-projection-refresh-write-contract.md`, plus `rp-core-projection-read-manifest-hardening.md` |
| deterministic read manifest | `rp-core-projection-read-manifest-hardening.md` |
| retrieval card / usage / promotion minimal loop | `rp-retrieval-card-usage-promotion-boot-contract.md` |
| worker-facing memory tools and permission enforcement | `rp-worker-memory-tool-permission-boot-contract.md`, `rp-runtime-profile-snapshot-minimal-compiler.md` |
| shared governed direct-edit mutation path | `rp-shared-core-mutation-kernel-direct-edit.md` |
| Recall branch-aware lifecycle and invalidation | `rp-recall-branch-aware-lifecycle.md` |
| Archival Evolution edit/version/reindex governance | `rp-archival-evolution-reindex-governance.md` |
| persistent event query/debug/eval readbacks | `rp-memory-event-debug-eval-read-surfaces.md` |
| registry/config-driven expansion beyond longform | `rp-runtime-profile-snapshot-minimal-compiler.md`, `rp-registry-profile-snapshot-full-management.md` |
| user-visible memory inspection/edit backend contracts | `rp-user-visible-memory-inspection-edit-backend-contracts.md` |

## 6. Immediate Writing Order

Write now:

1. `A`: `rp-runtime-identity-persistence-propagation.md`
2. `J-min`: `rp-runtime-profile-snapshot-minimal-compiler.md`

Write next after the first pair is reviewed:

Boot-bar and full-foundation spec suites are now fully written.

The next work should return to implementation/check in module order:

1. `A -> J-min`
2. `B -> I-min`
3. `C -> D`
4. `H-min -> E-min`
5. `K-min`
6. then expand into the full-foundation implementation modules `F -> G -> I -> J -> K`

The reason for this order is simple:

- identity and pinned snapshot are still the roots;
- persistent Runtime Workspace and persistent event records are the first durable memory surfaces that runtime depends on;
- branch visibility, strict read manifests, retrieval usage, and shared mutation all build on those roots;
- the remaining full-foundation slices extend the same contracts after boot paths are real.
