# Shared Core Mutation Kernel Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Purpose: lightweight pre-spec technical research for:
> - `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`

## 1. Question

How should RP memory unify:

- user direct Core edit
- worker proposal/apply
- brainstorm summary apply

without creating a second raw mutation path or weakening current proposal/apply governance?

## 2. Existing Repo Wheels To Reuse

### Proposal/apply path

Current repo already has:

- `ProposalService`
- `ProposalWorkflowService`
- `ProposalApplyService`
- proposal persistence
- base revision conflict enforcement

Decision:

- keep proposal/apply as the existing governed mutation backbone;
- extend it with shared mutation envelope/origin metadata instead of inventing a parallel write stack.

### StoryStateApplyService and compatibility mirrors

Current repo still has:

- `StoryStateApplyService`
- compatibility mirror sync
- store-primary / dual-write authoritative mutation path

Decision:

- do not expose `StoryStateApplyService` as a user-facing or worker-facing direct write path;
- treat it as an internal apply helper behind the governed mutation kernel only.

### Existing dirty-target/event direction

Current repo already has:

- persistent event foundation spec
- persistent Workspace spec
- projection refresh/write-hardening specs

Decision:

- direct edit must hook into the same dirty-target / projection refresh / event path family;
- do not create user-only “apply without trace” behavior.

## 3. Mature External References

### Letta

Useful reference:

- user/agent-visible memory editing can be explicit and inspectable

Boundary:

- Letta's direct block editing is too permissive for RP Core truth;
- RP must preserve user priority without bypassing revision/provenance/governance.

Absorbed conclusion:

- product may expose “direct edit”, but backend should still route it through the same governed apply kernel.

### Anthropic workflow guidance

Useful reference:

- backend should own deterministic side effects while models produce structured proposals

Absorbed conclusion:

- brainstorm outputs and worker outputs should become structured change proposals or equivalent shared mutation envelopes, not hidden raw writes.

## 4. Rejected Options

Rejected for this slice:

- user-only raw Core write endpoint
- worker-only direct mutation shortcut because the worker is “trusted”
- separate brainstorm apply path with looser validation
- reusing direct JSON patch against compatibility mirrors as the long-term Core write path

Reason:

- each option breaks conflict handling, provenance, or later branch/read-manifest/event semantics.

## 5. Spec Decisions Enabled By This Research

1. direct edit is a product-level label, not a backend bypass.
2. all authoritative Core write origins should route through one shared mutation envelope/kernel.
3. origin kinds should at least distinguish:
   - `user_direct_edit`
   - `worker_proposal_apply`
   - `brainstorm_summary_apply`
   - `deterministic_system_refresh`
4. base revision/conflict validation remains required whenever existing Core facts are edited.
5. dirty targets, event records, and projection refresh/invalidation are part of the shared mutation outcome, not optional extras.
6. public direct-edit API can be thin as long as it adapts into the shared kernel and records actor/origin/source refs/identity.

## 6. Immediate Spec Consequence

The next backend spec should be:

1. `rp-shared-core-mutation-kernel-direct-edit.md`

It should be written as an incremental extension over:

- `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
- `.trellis/spec/backend/rp-projection-refresh-write-contract.md`
- `.trellis/spec/backend/rp-persistent-memory-event-record-foundation.md`
- `.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md`

It should not introduce:

- a second mutation system
- raw user-only Core writes
- projection refresh as a truth write path
- separate brainstorm mutation semantics outside the shared kernel
