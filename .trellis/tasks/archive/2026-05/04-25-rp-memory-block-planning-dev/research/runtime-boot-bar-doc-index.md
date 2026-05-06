# Runtime Boot Bar Doc Index

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: one entrypoint for the current memory boot-bar / full-foundation spec work, so research, planning, and backend specs do not get mixed together.

## 1. Read This First

Use this file as the single entrypoint for the current memory-task documentation set.

Reading order:

1. This file
2. `.trellis/tasks/04-25-rp-memory-block-planning-dev/prd.md`
3. `.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-boot-bar-memory-spec-plan.md`
4. `.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-identity-profile-compiler-technical-research.md`
5. The specific backend spec you are about to write or implement

## 2. One Doc, One Job

To avoid document drift or crossing responsibilities:

- `prd.md`
  - task history, completed slices, and current planning milestones
- `runtime-boot-bar-doc-index.md`
  - single entrypoint and read order
- `runtime-boot-bar-memory-spec-plan.md`
  - ordered spec suite and proposal-to-spec coverage map
- `*-technical-research.md`
  - lightweight pre-spec wheel/framework/project research
- `.trellis/spec/backend/*.md`
  - executable backend contracts only

Do not put implementation planning tables into backend spec files when they belong in the task research area.
Do not put stable backend contracts only inside research docs when they belong in `.trellis/spec/backend/`.

## 3. Current Control Docs

Primary control docs for this task:

- [PRD](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/prd.md>)
- [Runtime Boot Bar Memory Spec Plan](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-boot-bar-memory-spec-plan.md>)
- [Runtime Identity + Profile Compiler Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-identity-profile-compiler-technical-research.md>)
- [Runtime Workspace + Event Foundation Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-workspace-event-foundation-technical-research.md>)
- [Runtime Branch Visibility + Read Manifest Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/runtime-branch-read-manifest-technical-research.md>)
- [Retrieval Card Loop + Worker Governance Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/retrieval-worker-governance-technical-research.md>)
- [Shared Core Mutation Kernel Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/shared-mutation-kernel-technical-research.md>)
- [Recall Branch-Aware Lifecycle Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/recall-branch-aware-lifecycle-technical-research.md>)
- [Archival Evolution Reindex Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/archival-evolution-reindex-technical-research.md>)
- [Memory Event Debug Eval Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/memory-event-debug-eval-technical-research.md>)
- [Registry Profile Snapshot Full Management Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/registry-profile-snapshot-full-management-technical-research.md>)
- [Memory Inspection Edit Backend Technical Research](</H:/chatboxapp/.trellis/tasks/04-25-rp-memory-block-planning-dev/research/memory-inspection-edit-backend-technical-research.md>)

## 4. Requirement Input Docs

These are input requirements, not the execution task owner:

- [Memory Layer Story Runtime Blockers Dev Proposal](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md>)
- [Memory Layer Strengthening Proposal](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md>)
- [Story Runtime Spec Coding Plan](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-spec-coding-plan.md>)
- [Branching Memory Framework Research](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md>)
- [Story Runtime Technical Research And Pseudocode](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-technical-research-and-pseudocode.md>)
- [Story Runtime Dependency Readiness Audit](</H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-dependency-readiness-audit.md>)

Rule:

- these documents define constraints and required capability;
- implementation still stays under `rp-memory-block-planning-dev`.

## 5. Existing Memory Baseline Specs

Read these before writing later boot-bar/full-foundation specs:

- [RP Memory Contract Registry Identity Event Skeleton](</H:/chatboxapp/.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md>)
- [RP Runtime Workspace Turn Material Store](</H:/chatboxapp/.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md>)
- [RP Memory Change Event Spine](</H:/chatboxapp/.trellis/spec/backend/rp-memory-change-event-spine.md>)
- [RP Core State Base Revision Conflict Enforcement](</H:/chatboxapp/.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md>)
- [RP Projection Refresh Write Contract](</H:/chatboxapp/.trellis/spec/backend/rp-projection-refresh-write-contract.md>)
- [RP Memory Temporal Materialization](</H:/chatboxapp/.trellis/spec/backend/rp-memory-temporal-materialization.md>)

## 6. Boot Bar Spec Index

Current ordered boot-bar suite:

1. [RP Runtime Identity Persistence And Propagation](</H:/chatboxapp/.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md>) - written
2. [RP Runtime Profile Snapshot Minimal Compiler](</H:/chatboxapp/.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md>) - written
3. [RP Runtime Workspace Persistent Turn Material Store](</H:/chatboxapp/.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md>) - written
4. [RP Persistent Memory Event Record Foundation](</H:/chatboxapp/.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md>) - written
5. [RP Branch Visibility Resolver And Lineage](</H:/chatboxapp/.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md>) - written
6. [RP Core Projection And Read Manifest Hardening](</H:/chatboxapp/.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md>) - written
7. [RP Retrieval Card Usage And Promotion Boot Contract](</H:/chatboxapp/.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md>) - written
8. [RP Worker Memory Tool And Permission Boot Contract](</H:/chatboxapp/.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md>) - written
9. [RP Shared Core Mutation Kernel And Direct Edit](</H:/chatboxapp/.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md>) - written

## 7. Full Foundation Spec Index

Current full-foundation suite:

1. [RP Recall Branch-Aware Lifecycle](</H:/chatboxapp/.trellis/spec/backend/rp-recall-branch-aware-lifecycle.md>) - written
2. [RP Archival Evolution Reindex Governance](</H:/chatboxapp/.trellis/spec/backend/rp-archival-evolution-reindex-governance.md>) - written
3. [RP Memory Event Debug Eval Read Surfaces](</H:/chatboxapp/.trellis/spec/backend/rp-memory-event-debug-eval-read-surfaces.md>) - written
4. [RP Registry Profile Snapshot Full Management](</H:/chatboxapp/.trellis/spec/backend/rp-registry-profile-snapshot-full-management.md>) - written
5. [RP User-Visible Memory Inspection Edit Backend Contracts](</H:/chatboxapp/.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md>) - written

## 8. Anti-Crossing Rules

- Do not write runtime scheduler or worker orchestration specs into this memory boot-bar set.
- Do not treat runtime-story research docs as the task owner; they are requirement sources only.
- Do not duplicate the same acceptance rule in both a research doc and a backend spec unless the research doc is explicitly the source input and the backend spec is the executable contract.
- When a later spec extends an earlier one, link back to the earlier spec instead of rewriting the entire contract history.
