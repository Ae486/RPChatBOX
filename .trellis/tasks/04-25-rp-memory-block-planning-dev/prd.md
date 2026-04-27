# RP Memory Block Rollout and Full Memory OS Containerization

## Goal

Use the real Trellis workflow to move RP Memory OS from the current Core State-first Block rollout into a complete, tested, and chain-safe Memory OS evolution:

1. finish Core State Block integration and prove it usable;
2. bridge the Block-backed Core State into the public memory layer chain;
3. follow up with a new Block container layer only where current adapters become insufficient;
4. reach full Memory OS containerization without collapsing the project's frozen business boundaries.

## Current Baseline

The active task is `.trellis/tasks/04-25-rp-memory-block-planning-dev`.

Current code and completed slices already provide:

- formal Core State store tables for authoritative current/revision rows and projection current/revision rows;
- read-only Core State Block envelopes via `RpBlockView` / `RpBlockReadService`;
- session-scoped Block consumer registry and dirty/read-side sync state;
- internal Block-backed prompt context / rendering / lazy rebuild for orchestrator and specialist;
- authoritative Block-governed mutation submission via the existing proposal/apply workflow;
- Block-scoped proposal detail / apply visibility for active story authoritative Blocks;
- `RetrievalBroker`-backed `memory.get_state` / `memory.get_summary` Block read fallback for unmapped Core State targets.
- retrieval-backed Block-compatible views inside specialist runtime payloads and retrieval observability top-hit payloads.
- Runtime Workspace Block-compatible views for current-chapter draft artifacts and discussion entries through `/memory/blocks`.
- active-story consumer / prompt-compile wiring explicitly kept Core State-only so Runtime Workspace Block views do not leak into orchestrator/specialist prompt overlays.

This means the task is no longer "should we start Block?" but "how do we finish the rollout and safely extend it to the rest of Memory OS?"

## Frozen Architecture Boundaries

- Preserve the frozen Memory OS hierarchy:
  - `Core State`
    - `authoritative_state`
    - `derived_projection`
  - `Recall Memory`
  - `Archival Knowledge`
  - `Runtime Workspace`
- Treat `Core State` as the first durable Block landing zone.
- Keep `Recall Memory` and `Archival Knowledge` on the existing retrieval-core physical object chain unless a later phase explicitly proves a different physical model is required.
- Keep `WritingPacketBuilder` as the deterministic writer packet boundary.
- Keep setup runtime-private cognition outside durable story Memory OS.
- Keep the frozen external-facing tool family stable:
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.search_recall`
  - `memory.search_archival`
  - `proposal.submit`
  - `memory.list_versions`
  - `memory.read_provenance`
- Keep `proposal.review`, `proposal.apply`, and direct state patching internal unless a later approved phase says otherwise.

## What "Full Memory OS Block Containerization" Means Here

It does **not** mean rebuilding Recall/Archival as one new `rp_blocks` physical store.

It means:

- `Core State.authoritative_state` and `Core State.derived_projection` become first-class containerized runtime objects;
- the memory layer, retrieval bridge, and agent-visible tools can consume a stable container-facing interface without provider-chain breakage;
- Recall / Archival can participate in attach/compile/visibility as Block-compatible views or adapters while still keeping retrieval-core as their physical source of truth;
- Runtime Workspace can use ephemeral or runtime-scoped Block views without being promoted into story durable truth by accident.

## Rollout Phases

### Phase A: Core State complete Block integration and usability gate

Objective: finish the Core State-first Block backbone and prove it is usable from runtime and memory-chain entry points.

Completed or largely completed:

- read-only Block envelope over Core State
- Block consumer registry
- Block-backed internal compile/render/lazy rebuild for orchestrator/specialist
- authoritative Block-governed mutation submit
- Block proposal detail/apply visibility
- `memory.get_state` / `memory.get_summary` Block-backed fallback

Remaining Phase A gate:

- verify that the memory/retrieval/tool chain still behaves correctly after Block-backed Core State reads;
- keep the public tool/provider contract stable while Block metadata becomes real underneath.

### Phase B: Bridge the memory layer chain

Objective: make Block-backed Core State survive the whole memory chain end-to-end.

Key concerns:

- `RetrievalBroker` remains the memory read boundary;
- `MemoryOsService` remains a facade;
- `MemoryCrudToolProvider` and agent-visible tools remain contract-stable;
- retrieval-side and tool-side adaptation failures are detected with focused tests rather than discovered late in runtime.

Expected outputs:

- compatibility gates around provider/tool serialization and routing;
- no direct Block-service bypass from tools;
- stable behavior for `memory.get_state` / `memory.get_summary` after Block-backed enrichment;
- explicit compatibility coverage for `memory.list_versions` / `memory.read_provenance` / `proposal.submit`, not only `memory.get_state` / `memory.get_summary`.

### Phase C: Introduce a new Block container layer only if adapters are no longer enough

Objective: add a new durable/container registry layer only after the Core State Block rollout and chain bridging are proven.

This phase is allowed only if at least one of the following becomes true:

- current `RpBlockView` + formal Core State rows are insufficient to represent shared durable containers;
- attach/consumer/compiler/visibility logic requires a stable container registry beyond Core State rows;
- Story Evolution or other post-activation flows need container-level semantics that cannot be expressed safely through the current adapters.

This phase must not:

- replace retrieval-core physical storage for Recall / Archival;
- erase the existing Core State store without a dual-source bridge;
- widen external-facing tool families by accident.

Current decision for the repo state covered by this task:

- Phase A and Phase B are green enough to evaluate the question;
- current `RpBlockView` plus formal Core State rows already cover the repo's present durable container needs;
- the remaining real gaps are Recall / Archival / Runtime Workspace Block-compatible views, not proof that a new durable registry is required;
- therefore a new durable container layer stays deferred until a later slice proves otherwise.

### Phase D: Full Memory OS containerization and chain completion

Objective: finish the logical Memory OS container story.

Definition of complete:

- Core State is fully container-addressable;
- retrieval-facing memory layers can be attached/compiled/observed through container-compatible views;
- internal agent compile, visibility, and evolution chains are consistent with the container model;
- public tool contracts stay stable or are versioned deliberately;
- end-to-end chain tests cover retrieval, tools, runtime, and proposal governance.

## D4b Close-Out

Completed slice:

> **Phase D4b: Final chain verification and remaining-gap closure after non-Core-State Block views are proven read-only / non-attached**

What was closed in D4b:

- fixed the real governance inconsistency where proposal detail on projection/runtime-workspace Blocks returned `memory_block_proposal_not_found` instead of the same unsupported semantics already used by submit/apply;
- kept active-story compile/consumer attachment Core State-only, with focused regression coverage still green;
- verified the public memory tool chain remains stable for:
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.list_versions`
  - `memory.read_provenance`
  - `proposal.submit`
- verified retrieval/runtime observability still carries additive Block-compatible views without widening mutation/history semantics.

Conclusion:

- the remaining question is no longer "which chain still needs urgent Block wiring";
- for the current repo state, no additional real container wiring is justified after D4b;
- a universal durable container registry remains deferred until a later slice proves current adapters are insufficient.

## Acceptance Criteria

- [x] Task PRD records the rollout beyond the first Block-envelope slice.
- [x] The rollout explicitly keeps frozen boundaries intact.
- [x] The rollout distinguishes "logical containerization" from "one new physical Block table for everything".
- [x] The next recommended slice is identified from actual code state, not only from proposal prose.
- [x] Core State Block rollout has a focused compatibility/usability gate over retrieval + tools.
- [x] Follow-up phases are sequenced so new container storage does not start before chain bridging is proven.
- [x] Phase C explicitly records that the repo does not yet need a new durable container layer.
- [x] Runtime Workspace has read-only Block-compatible views without widening mutation/history semantics.

## Out of Scope

- Replacing retrieval-core tables for Recall / Archival in the current step.
- Replacing `WritingPacketBuilder`.
- Moving setup runtime-private cognition into durable Memory OS.
- Promoting `proposal.apply` into a public external tool family in the current step.
- Jumping straight to a universal `rp_blocks` physical table before chain compatibility is proven.

## Definition of Done

This task is done only when:

- the rollout spec and current task context are updated to the broadened scope;
- each rollout phase is executed as focused Trellis slices;
- every completed slice passes scoped `trellis-check`;
- new durable conventions are reflected in `.trellis/spec/backend/`;
- the repo has a clear handoff point from "Core State Block rollout" to "full Memory OS containerization".

Current status for this task:

- D4b close-out checks passed for the runtime/tool/governance slice.
- The task is ready for finish-work style wrap-up unless a new post-D4b requirement is introduced.

## Post-D4b Recall Detail Slice

User-directed next slice:

> **Recall detail retention for long-context memory quality**

Why this slice first:

- current code can already preserve chapter-level recall summaries, but summary-only retention is not enough for the user's long-context goal;
- accepted prose detail is the next highest-value missing layer for "remember everything without collapsing into only summaries";
- this slice stays within frozen boundaries:
  - Recall still uses retrieval-core physical storage
  - proposal/apply still governs authoritative truth only
  - `WritingPacketBuilder` stays independent

Status on 2026-04-27:

- implemented `RecallDetailIngestionService` to persist accepted `story_segment` artifacts into Recall through the existing retrieval-core asset/document/chunk/embedding chain;
- wired heavy regression to preserve both:
  - chapter-level recall summary text
  - accepted story prose detail
- kept the trigger limited to heavy regression / chapter close;
- kept deterministic accepted-detail asset identity stable across reruns via artifact-derived recall asset ids;
- passed focused quality checks for this slice:
  - `pytest rp/tests/test_recall_detail_ingestion_service.py rp/tests/test_proposal_workflow_service.py -q`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip ...`

Implication:

- the repo now preserves both summary-level recall and accepted-prose recall detail for longform chapter close;
- the next slice should target one of the remaining long-context quality gaps rather than more Core State Block wiring for this specific requirement.

## Post-D4b Memory Temporal Materialization Planning

User-confirmed direction:

- Letta is only a reference for layered implementation mechanics.
- RP requirements decide which layer owns which material, who writes it, when it materializes, and how it is read.
- The next work should keep full-picture Memory OS planning visible instead of doing isolated specs without a shared semantic map.

Active planning spec:

- `.trellis/spec/backend/rp-memory-temporal-materialization.md`

What this spec freezes:

- current structured truth belongs to `Core State.authoritative_state`;
- current hot summary / writer-facing view belongs to `Core State.derived_projection`;
- closed historical story material belongs to `Recall Memory`;
- imported/authored source material belongs to `Archival Knowledge`;
- current-turn scratch, discussion traces, raw hits, drafts, tool outputs, and worker intermediate state belong to `Runtime Workspace`;
- `StoryDiscussionEntry` is not automatically a scene transcript;
- all memory reads still go through `MemoryOsService` / `RetrievalBroker`;
- authoritative mutation still goes through proposal/apply;
- projection refresh, recall ingestion, and archival ingestion are maintenance/ingestion paths rather than authoritative proposal mutations.

Why this is the next total-spec:

- Core State Block and chain compatibility are now sufficiently closed for current repo state.
- Recall detail retention proved the first non-container "memory quality" gap can be solved through the existing layer boundaries.
- Before implementing more retention/promotion slices, the repo needs an explicit temporal materialization map so future work does not confuse current truth, historical recall, source knowledge, and runtime scratch.

## Memory Materialization Metadata + Boundary Enforcement Slice

Status on 2026-04-27:

- implemented formal projection refresh metadata that marks `Core State.derived_projection`, current projection role, maintenance refresh event, and `authoritative_mutation=False`;
- kept projection refresh as maintenance by testing that `StorySession.current_state_json` is not changed by projection refresh;
- added Recall summary/detail materialization metadata on retrieval-core `SourceAsset` and seed sections:
  - Recall layer
  - `longform_story_runtime` source family
  - `heavy_regression.chapter_close` materialization event
  - `chapter_summary` or `accepted_story_segment` materialization kind
  - `materialized_to_recall=True`
- made `RecallSummaryIngestionService` check returned `IndexJob` and raise `recall_summary_ingestion_failed:{asset_id}:{detail}` instead of silently succeeding on retrieval-core failure;
- extended Runtime Workspace draft/discussion Block metadata to mark current-turn scratch, non-Recall materialization, and non-scene-transcript semantics.

Quality gate:

- `trellis-check` found and fixed three issues:
  - projection metadata needed exact `semantic_layer="Core State.derived_projection"` and stronger deep-copy authoritative-state assertion;
  - recall summary metadata needed closer parity with detail metadata plus success-path assertions;
  - runtime draft artifact metadata needed the same non-scene-transcript marker as discussion blocks.
- Focused verification passed:
  - `pytest rp/tests/test_core_state_dual_write_services.py rp/tests/test_proposal_workflow_service.py rp/tests/test_recall_detail_ingestion_service.py rp/tests/test_recall_summary_ingestion_service.py rp/tests/test_rp_block_read_service.py -q`
  - result: `26 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip ...`
  - boundary scan for `rp_blocks`

Implication:

- the repo now has machine-checkable layer/materialization metadata for the first temporal materialization slice;
- later scene transcript, continuity note, long-history summary, or archival import slices can build on these explicit markers instead of inferring layer ownership from ad hoc asset kinds.
