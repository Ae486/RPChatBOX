# S3 Standing Assistant Review

## Verdict

PASS_WITH_CONCERNS

The S3 planning set is directionally faithful to Node-1/module requirements and is close enough for implementation planning to continue, but it needs several explicit plan/test tightenings before production code starts. No product/user裁定 is required at this gate.

YCE note: YCE was invoked from `C:\Users\55473\.codex\skills\yce` with `--cwd "H:\chatboxapp"` as required. Both normal and `YCE_LOCAL_FALLBACK=true` attempts failed before search execution with `spawn EPERM`. I therefore used only direct reads of the brief-listed known documents and code anchors.

## Blockers

- None.

## Concerns

- [C1] The lock matrix is correctly stated in the PRD, but the test plan does not yet spell out the full D-S3-03 matrix. The PRD lists ordinary Core/projection/manual accepted-prose edits, story progression, rollback, branch switch/create, rewrite/regenerate, and chapter complete as blocked, while inspect/debug and proposal review actions remain allowed. The test plan currently names "maintenance lock blocks progression" in the review-required integration path, but it should explicitly enumerate every blocked and allowed operation from D-S3-03.

- [C2] Governance routing is represented, but the W5-to-current-code policy mapping remains too deferred for a coding handoff. Current code routes `REVIEW_REQUIRED`, `NOTIFY_APPLY`, and `SILENT`; the W5 language requires `review_required`, `direct_apply_allowed`, `proposal_required`, and `blocked` / invalid. The PRD says the mapping must be explicit, and the SDD leaves it as a design choice. Before S3c implementation, the plan should contain a concrete mapping table including proposal status, apply behavior, lock behavior, and reason-code outcome.

- [C3] Tool / structured-output / error / failure design is good at the boundary level but still under-specified at the DTO/error level. The SDD names `memory.batch_read_blocks` and `memory.apply_candidate_field_ops`, structured candidate/no-op/failure variants, and fake provider expectations, but it should define the normalized tool error shape, invalid structured-output result, repair/exhaustion behavior, no-op receipt fields, and failure receipt fields before coding the worker adapter.

- [C4] The plan correctly identifies `legacy_state_patch` as migration evidence, but tests should make the old-MVP boundary executable. Current code only accepts `candidate_kind="legacy_state_patch"` in post-write governance. The SDD prefers a normalized S3 memory candidate path and preserving `legacy_state_patch` only as compatibility. Add an explicit S3 test/gate that the new memory-worker path is not exposed as a misleading legacy public contract.

- [C5] Stale base handling is directionally correct, but the plan should explicitly bridge frozen `base_block_revision_id` semantics to the current `ProposalApplyService` `base_refs` enforcement. The SoT makes `base_block_revision_id` authoritative and treats `base_refs` as a non-frozen implementation subset; current apply code enforces `base_refs` missing/conflict errors. The S3 plan should say exactly where the adapter converts `base_block_revision_id` into current apply input and where stale state is surfaced to review/debug.

## Non-blocking Notes

- [N1] Harness/product separation is well stated. The SDD table keeps model/tool/structured-output mechanics in harness core and memory/proposal/apply policy outside it.

- [N2] The PRD and SDD avoid setup-agent reuse and old-MVP semantic authority. They explicitly ban setup executor reuse and treat legacy longform/proposal paths as compatibility or migration evidence.

- [N3] Commit and rollback discipline are present and consistent with main-brain rules: path-level revertability, explicit staging, no unrelated worktree changes, and commit only after a coherent gate.

- [N4] Functional test layering is broadly correct: unit, service, integration, regression, fresh reviewer audit, and optional live-provider smoke are all present. The main gap is specificity, not missing layers.

## Required Plan Changes

- Add a D-S3-03 lock matrix table to `03-test-and-gate-plan.md` covering blocked operations: Core/projection/manual accepted-prose edits, story progression, rollback, branch switch, branch create, rewrite, regenerate, and chapter complete; and allowed operations: inspect/debug plus proposal accept/reject/edit.

- Add a governance mapping table before S3c implementation: W5 term -> current enum/status -> apply behavior -> lock behavior -> readable reason/failure code. Include `blocked` / invalid as a first-class fail-closed outcome, not just "unsupported op raises".

- Add exact structured-output and tool failure contracts to `02-SDD-and-implementation-plan.md`: normalized tool success/error result, invalid schema result, repair exhausted result, no-op receipt, worker failure receipt, and trace fields.

- Add a test/gate that normalized S3 memory candidates do not hide under `legacy_state_patch` as their public semantic contract. If a temporary adapter maps into existing proposal inputs, the boundary must be named and traceable.

- Add an explicit `base_block_revision_id` -> current apply `base_refs` conversion section, with tests for missing base, stale/conflict base, and no model repair prompt/emission.

## Evidence

- Module authority says harness does not own product policy and no LLM role owns governed Core apply: `research/modules/runtime-agent-harness.md:25`, `research/modules/runtime-agent-harness.md:54`.
- Worker/source/base rules are explicit: worker candidates must carry source/base refs and stale base is not a model repair problem: `research/modules/runtime-worker-family.md:51`, `research/modules/runtime-worker-family.md:53`.
- Scheduler/governance requires lock behavior and review/apply semantics: maintenance blocks rollback/branch/rewrite paths while proposal review is allowed, and review-required proposals keep the lock until terminal: `research/modules/runtime-scheduler-governance.md:57`, `research/modules/runtime-scheduler-governance.md:60`, `research/modules/runtime-scheduler-governance.md:64`.
- Frozen SoT sets the key S3 authority: no LLM governed apply (`AUTH-001`), no setup-agent imports (`HAR-003`), `base_block_revision_id` as authoritative stale-check field, and frozen proposal-review semantics with deferred DTO naming: `execution/phase-1-spec-freeze/00-FREEZE-MANIFEST.md:43`, `execution/phase-1-spec-freeze/00-FREEZE-MANIFEST.md:44`, `execution/phase-1-spec-freeze/00-FREEZE-MANIFEST.md:61`, `execution/phase-1-spec-freeze/00-FREEZE-MANIFEST.md:62`.
- S3 acceptance oracles define the exact registry, governed apply, lock matrix, and stale-base criteria: `execution/phase-1-spec-freeze/acceptance-criteria.md:103`, `execution/phase-1-spec-freeze/acceptance-criteria.md:104`, `execution/phase-1-spec-freeze/acceptance-criteria.md:105`, `execution/phase-1-spec-freeze/acceptance-criteria.md:106`.
- Seams reinforce `base_block_revision_id`, candidate items, and candidate overlay materialization: `execution/phase-1-spec-freeze/seams.md:534`, `execution/phase-1-spec-freeze/seams.md:556`, `execution/phase-1-spec-freeze/seams.md:580`, `execution/phase-1-spec-freeze/seams.md:721`.
- Main-brain rules require S3 to prove review/direct/blocked routing and layered tests: `execution/main-brain/implementation-leadership-rules.md:179`, `execution/main-brain/implementation-leadership-rules.md:185`, `execution/main-brain/implementation-leadership-rules.md:203`.
- S3 PRD already states the core product promise, governance paths, lock matrix, and stale-base rule: `execution/phase-5-implementation/S3/01-PRD.md:26`, `execution/phase-5-implementation/S3/01-PRD.md:118`, `execution/phase-5-implementation/S3/01-PRD.md:202`, `execution/phase-5-implementation/S3/01-PRD.md:215`.
- S3 SDD already separates harness/product policy and recognizes current legacy-governance gaps: `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md:26`, `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md:50`, `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md:169`, `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md:341`.
- Current code evidence confirms the plan's identified migration gap: `PostWriteGovernanceService` only accepts `legacy_state_patch`, hardcodes bootstrap permission text, current workflow routes `REVIEW_REQUIRED` / `NOTIFY_APPLY` / `SILENT`, and apply enforces missing/conflicting base revisions through `base_refs`: `backend/rp/services/proposal/post_write_governance_service.py:481`, `backend/rp/services/proposal/post_write_governance_service.py:512`, `backend/rp/services/proposal/workflow_service.py:151`, `backend/rp/services/proposal/workflow_service.py:153`, `backend/rp/services/proposal/workflow_service.py:155`, `backend/rp/services/proposal/apply_service.py:259`, `backend/rp/services/proposal/apply_service.py:276`.
- S3 test plan has the right layers and core paths but needs the full lock matrix and legacy-boundary assertions: `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:49`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:61`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:70`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:76`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:87`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:103`, `execution/phase-5-implementation/S3/03-test-and-gate-plan.md:184`.

## Recommendation

Revise then proceed.

The current S3 PRD/SDD/test plan is not blocked by product ambiguity and does not need user裁定. Main-brain should fold the required plan changes above into the S3 plan before production implementation, then continue with S3a/S3b under the existing standing assistant / fresh reviewer loop.
