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

## Recall Source Family Retrieval Contract Slice

Planned next executable slice:

- `.trellis/spec/backend/rp-recall-source-family-retrieval-contract.md`

Objective:

- make Recall materialization metadata visible after retrieval, not only at ingestion time;
- allow runtime workers to distinguish `chapter_summary`, `accepted_story_segment`, and future Recall source families without guessing from excerpt text;
- preserve source-family metadata through:
  - raw `memory.search_recall` hits
  - retrieval-backed `RpBlockView` metadata
  - `LongformSpecialistService` internal payload

Boundaries:

- do not introduce universal durable `rp_blocks`;
- do not replace raw `recall_hits` with Block views;
- do not promote `StoryDiscussionEntry` into Recall or `scene_transcript`;
- do not change public memory tool input contracts.

Status on 2026-04-27:

- implemented `build_chunk_hit` fallback from `SourceAsset.metadata_json` to `RetrievalHit.metadata` for Recall source-family/materialization fields, without overriding explicit chunk metadata;
- kept legacy Recall hits valid when those fields are absent;
- preserved materialization metadata through `RetrievalBlockAdapterService` into `RpBlockView.metadata`, with read-only `data_json` routing summaries for `source_family` and `materialization_kind`;
- added top-level `source_family`, `materialization_kind`, and `materialization_event` fields to specialist raw `recall_hits` payload while keeping `metadata` canonical and preserving additive `recall_block_views`;
- verified Runtime Workspace discussion/draft material does not become Recall search material and `StoryDiscussionEntry` remains runtime trace, not transcript.

Quality gate:

- `trellis-check` found one real test gap and fixed it:
  - legacy Recall chunks without `source_family` / `materialization_*` fields now have direct regression coverage and do not get fabricated metadata.
- Focused verification passed:
  - `pytest rp/tests/test_retrieval_broker.py rp/tests/test_retrieval_block_adapter_service.py rp/tests/test_projection_builder_services.py rp/tests/test_proposal_workflow_service.py -q`
  - result: `32 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip ...`

Implication:

- Recall is now not just searchable, but semantically routable by source family in runtime payloads;
- future `scene_transcript`, `continuity_note`, `character_long_history_summary`, and retired-thread/foreshadow summaries can join Recall as new source families without changing the public memory tool contract.

## Recall Continuity Note Retention Slice

Planned next executable slice:

- `.trellis/spec/backend/rp-recall-continuity-note-retention.md`

Objective:

- materialize `SpecialistResultBundle.summary_updates` from heavy regression / chapter close into Recall as `continuity_note` source-family assets;
- make continuity notes searchable and routable with the same source-family metadata path used by `chapter_summary` and `accepted_story_segment`;
- avoid scene transcript promotion until a separate transcript selection/filtering spec exists.

Boundaries:

- `summary_updates` are maintenance output, not authoritative truth;
- continuity notes do not mutate `Core State.authoritative_state`;
- continuity notes do not become `Core State.derived_projection` slots in this slice;
- Runtime Workspace drafts/discussions remain outside Recall;
- light regression does not materialize continuity notes.

Status on 2026-04-27:

- implemented `RecallContinuityNoteIngestionService`;
- heavy regression now materializes non-empty `summary_updates` as Recall `continuity_note` assets when the service is wired;
- light regression remains outside continuity-note materialization;
- runtime factory wires the continuity-note ingestion service beside summary/detail Recall ingestion;
- continuity-note assets use deterministic identity based on session, chapter, and normalized note text;
- `note_index` is preserved as source metadata but does not participate in asset identity;
- duplicate notes in one bundle are deduplicated;
- repeated runs reindex/reuse the same logical asset;
- retrieval-core failures raise `recall_continuity_note_ingestion_failed:{asset_id}:{detail}`;
- `memory.search_recall` can retrieve continuity notes with source-family/materialization metadata.

Quality gate:

- `trellis-check` found and fixed two test gaps:
  - added direct coverage that changing `note_index` for the same note does not create duplicate assets;
  - strengthened `memory.search_recall` assertions for continuity-note `source_family`, `materialization_event`, `materialized_to_recall`, and `note_index`.
- Focused verification passed:
  - `pytest backend\rp\tests\test_recall_continuity_note_ingestion_service.py backend\rp\tests\test_proposal_workflow_service.py -q`
  - result: `15 passed, 1 warning`
  - broader source-family regression: `38 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`
  - boundary scan for `rp_blocks`

Implication:

- Recall now has three concrete source families in the chapter-close chain:
  - `chapter_summary`
  - `accepted_story_segment`
  - `continuity_note`
- the next source-family slice should either define scene transcript promotion rules or add a more bounded long-history summary family; it should not infer transcripts from raw discussion entries.

## Recall Source Family Search Filters Slice

Planned next executable slice:

- `.trellis/spec/backend/rp-recall-source-family-search-filters.md`

Objective:

- reuse the existing `MemorySearchRecallInput.filters` surface so callers can target Recall hits by:
  - `materialization_kinds`
  - `source_families`
  - `chapter_indices`
- turn Recall source-family metadata from “visible after search” into “usable during search”.

Boundaries:

- no new public tool or API shape;
- no new storage;
- no Archival filter expansion in this slice;
- no fabricated metadata for legacy Recall hits that were ingested before source-family fields existed.

Status on 2026-04-28:

- implemented Recall filter normalization in `DefaultQueryPreprocessor` for:
  - `materialization_kinds`
  - `source_families`
  - `chapter_indices`
- implemented Recall-only metadata filtering in retrieval common matching with:
  - chunk metadata precedence
  - asset metadata fallback only when chunk metadata is missing
  - OR semantics within one filter key
  - AND semantics across multiple filter keys
- kept the public surface unchanged by reusing `MemorySearchRecallInput.filters`;
- preserved legacy Recall behavior:
  - old hits still return without filters;
  - old hits do not fake metadata to satisfy new filters.

Quality gate:

- `trellis-check` found and fixed two real issues:
  - `RetrievalBroker.get_state()` fallback now guards the `refs`/`domain` boundary explicitly instead of dereferencing an optional domain in the degraded path;
  - retrieval broker regression test now asserts `archival.trace is not None` before dereferencing it, so focused `mypy` stays green.
- Focused verification passed:
  - `pytest rp/tests/test_retrieval_broker.py rp/tests/test_retrieval_service.py rp/tests/test_recall_continuity_note_ingestion_service.py rp/tests/test_retrieval_block_adapter_service.py -q`
  - result: `28 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`

Implication:

- Recall source-family metadata is now both visible after search and usable during search;
- the next safe slice is no longer another blind Recall family implementation, but freezing the transcript-promotion boundary so Runtime Workspace discussion never leaks into Recall history by accident.

## Next Slice Decision: Scene Transcript Promotion Rules Freeze

Chosen next slice:

- `.trellis/spec/backend/rp-recall-scene-transcript-promotion.md`

Why this next:

- `scene_transcript` is the next obvious Recall family, but the current repo still has:
  - no explicit scene-close lifecycle;
  - no stable scene identity in the longform runtime models;
  - no safe rule that lets `StoryDiscussionEntry` become historical transcript by default.
- `character_long_history_summary` and `retired_foreshadow_summary` are also valid future Recall families, but the current runtime has no dedicated maintenance producer for them yet.
- Therefore the next correct move is to freeze transcript promotion rules first, not invent a new runtime output contract ad hoc.

What this freeze establishes:

- transcript promotion requires explicit closed-scene identity;
- raw Runtime Workspace discussion is not historical Recall by default;
- chapter close does not imply scene transcript;
- future transcript ingestion must filter/normalize ordered source material before materializing `scene_transcript`.

What remains deferred after this freeze:

- actual transcript ingestion code;
- any new scene-close runtime command or scene identity model;
- long-history summary family implementation until the repo has a real producer rather than a guessed schema.

## Next Executable Slice: Runtime Scene Lifecycle Scaffold

Chosen next implementation slice:

- `.trellis/spec/backend/rp-runtime-scene-lifecycle.md`

Objective:

- add explicit runtime `scene_ref` identity before any transcript promotion exists;
- make scene closure an explicit runtime lifecycle operation instead of something inferred later from timestamps or chapter boundaries;
- keep this slice strictly below Recall/Core State scene materialization.

Boundaries:

- no Recall transcript ingestion yet;
- no new public memory tool family;
- no Core State `scene.current` / `scene.closed.*` authoritative mapping in this slice;
- no transcript generation from `StoryDiscussionEntry`;
- no long-history summary implementation in this slice.

Planned implementation direction:

- seed deterministic `current_scene_ref` on new chapter workspaces;
- persist `scene_ref` on runtime story segments and runtime discussion entries;
- add explicit `close_current_scene(...)` runtime lifecycle helper/surface;
- auto-close any remaining open scene during `complete_chapter(...)` without writing Recall;
- preserve `scene_ref` in Runtime Workspace Block payload/metadata so the later transcript slice can group the correct runtime material.

Why this slice before transcript ingestion:

- transcript promotion spec now requires explicit closed-scene identity;
- current repo state has no scene lifecycle surface, so transcript ingestion would otherwise be forced to guess from chapter-wide runtime traces;
- this slice creates the minimal stable runtime substrate for later `scene_transcript` Recall ingestion.

Status on 2026-04-28:

- implemented runtime scene lifecycle scaffolding without widening into Recall/Core State:
  - `ChapterWorkspace` now carries `current_scene_ref`, `next_scene_index`, `last_closed_scene_ref`, and `closed_scene_refs`;
  - `StoryArtifact` and `StoryDiscussionEntry` now carry explicit `scene_ref`;
  - new chapters seed deterministic runtime scene identity as `chapter:{chapter_index}:scene:1`;
  - `story_segment` artifacts and runtime discussion entries inherit the current open scene by default;
  - `chapter_outline` remains scene-less by default;
  - `StorySessionService.close_current_scene(...)` rotates the open scene explicitly;
  - `StoryRuntimeController.close_current_scene(...)` exposes the runtime lifecycle surface for callers/tests;
  - `complete_chapter(...)` closes any remaining open scene before moving to the next chapter;
  - Runtime Workspace Block views preserve `scene_ref` in both payload and metadata.

Check findings absorbed:

- legacy schema/backfill had to stay conservative:
  - old runtime rows are normalized to implicit `scene 1`;
  - they must not be relabeled to the chapter's later current scene after rotation.
- focused mypy noise on SQLModel `table=True` / field `.asc()/.desc()` was resolved inside the slice so scoped type-check now stays green.

Quality gate:

- `trellis-check` found and fixed the legacy backfill bug plus scoped type-check issues.
- Focused verification passed:
  - `pytest rp/tests/test_runtime_scene_lifecycle.py -q`
  - `pytest rp/tests/test_rp_block_read_service.py -k runtime_workspace -q`
  - `pytest rp/tests/test_story_runtime_controller_memory_read_side.py -k runtime_workspace -q`
  - `pytest tests/test_rp_story_api.py -k memory_block_routes_read_formal_blocks_and_filter_list -q`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`

Implication:

- the repo now has stable runtime scene grouping and a real scene-close trigger surface;
- the next slice no longer needs to guess scene boundaries from chapter-wide traces;
- the natural next implementation slice is actual `scene_transcript` promotion / ingestion into Recall on top of this runtime substrate.

## Scene Transcript Promotion / Ingestion Slice

Chosen implementation slice:

- `.trellis/spec/backend/rp-recall-scene-transcript-promotion.md`

Objective:

- materialize closed-scene transcript history into Recall without turning Runtime Workspace discussion into history by default;
- reuse the existing retrieval-core ingestion chain and keep public memory tools unchanged;
- make transcript identity deterministic per `(session_id, chapter_index, scene_ref)`;
- keep scene transcript history re-runnable when a closed scene later gains an accepted segment.

Status on 2026-04-28:

- implemented `RecallSceneTranscriptIngestionService`;
- transcript promotion now filters and normalizes:
  - ordered non-blank `user` / `assistant` discussion entries;
  - same-scene accepted `story_segment` artifacts only;
  - exclusion of `system`, draft, and superseded inputs;
- explicit triggers now materialize Recall transcript through:
  - `StoryRuntimeController.close_current_scene(...)`
  - `StoryTurnDomainService.complete_chapter(...)`
  - `StoryTurnDomainService.accept_pending_segment(...)` rerun for already closed scenes;
- transcript assets now carry:
  - `materialization_event = "scene_close"`
  - `materialization_kind = "scene_transcript"`
  - `scene_ref`
  - `transcript_source_count`
  - `transcript_includes_discussion`
  - `transcript_includes_accepted_segments`
- direct service calls now reject blank `scene_ref` even when callers bypass the builder helper.

Quality gate:

- focused verification passed:
  - `pytest rp/tests/test_recall_scene_transcript_ingestion_service.py -q`
    - `9 passed, 1 warning`
  - `pytest rp/tests/test_runtime_scene_lifecycle.py rp/tests/test_proposal_workflow_service.py rp/tests/test_story_runtime_controller_memory_read_side.py -q`
    - `19 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`
- focused review found one real boundary gap:
  - blank `scene_ref` could bypass the builder and still ingest malformed transcript input;
  - fixed by validating `ingest_scene_transcript(...)` itself and adding a direct regression test.

Implication:

- Recall now preserves four concrete longform runtime source families:
  - `chapter_summary`
  - `accepted_story_segment`
  - `continuity_note`
  - `scene_transcript`
- the next slice should move to the next real long-context quality gap instead of more scene wiring, most likely:
  - a dedicated long-history summary family with a real producer; or
  - archival/source-material side completion if current runtime now needs that layer more urgently.

## Next Executable Slice: Character Long-History Recall Retention

Chosen next implementation slice:

- `.trellis/spec/backend/rp-recall-character-long-history-retention.md`

Objective:

- add a real `character_long_history_summary` producer without inventing a new public tool family or overloading `summary_updates`;
- use chapter-close authoritative `character_state_digest` snapshots as the producer root;
- keep Recall physical storage on the existing retrieval-core chain;
- preserve deterministic per-character asset identity at chapter-close time.

Planned implementation direction:

- add `RecallCharacterLongHistoryIngestionService`;
- wire it only on heavy regression / chapter close;
- ingest one deterministic Recall asset per non-empty `character_state_digest` entry;
- allow chapter summary / continuity notes / accepted segments only as supporting context/evidence, not as the producer root;
- keep retrieval search surface unchanged so the new family remains reachable through `memory.search_recall`.

Status on 2026-04-28:

- implemented `RecallCharacterLongHistoryIngestionService`;
- heavy regression now materializes one deterministic Recall asset per non-empty `character_state_digest` entry;
- producer root is the post-apply authoritative `updated_session.current_state_json["character_state_digest"]` snapshot, not `summary_updates`;
- chapter summary text, continuity notes, and accepted `story_segment` artifacts are attached only as supporting context/evidence;
- light regression remains outside character-history materialization;
- runtime factory wiring is complete, and public memory tool/search surfaces stay unchanged.

Quality gate:

- focused verification passed:
  - `pytest rp/tests/test_recall_character_long_history_ingestion_service.py rp/tests/test_proposal_workflow_service.py -q`
    - `15 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`
- `trellis-check` found one real scoped issue:
  - test-only fail stub needed an explicit type cast so focused `mypy` accepted the injected ingestion-service substitute;
  - fixed and re-verified.

Implication:

- Recall now preserves five concrete longform runtime source families:
  - `chapter_summary`
  - `accepted_story_segment`
  - `continuity_note`
  - `scene_transcript`
  - `character_long_history_summary`
- `retired_foreshadow_summary` is now implemented as the next chapter-close maintenance slice, rooted in explicit terminal snapshots inside authoritative `foreshadow_registry` rather than `summary_updates` or runtime scratch.

Status on 2026-04-28:

- implemented `RecallRetiredForeshadowIngestionService`;
- heavy regression now materializes one deterministic Recall asset per terminal `foreshadow_id`;
- producer root is the post-apply authoritative `updated_session.current_state_json["foreshadow_registry"]` snapshot list;
- terminal detection stays explicit and conservative in this slice:
  - only non-blank `foreshadow_id`;
  - only `status` / `state` values `resolved`, `retired`, or `closed`;
  - later terminal snapshot wins for the same `foreshadow_id`;
- chapter summary text, continuity notes, and accepted `story_segment` artifacts are attached only as supporting context/evidence;
- light regression remains outside retired-foreshadow materialization;
- runtime factory wiring is complete, and public memory tool/search surfaces stay unchanged.

Quality gate:

- focused verification passed:
  - `pytest rp/tests/test_recall_retired_foreshadow_ingestion_service.py rp/tests/test_proposal_workflow_service.py -q`
    - `15 passed, 1 warning`
  - `ruff check ...`
  - `ruff format --check ...`
  - `mypy --follow-imports=skip --check-untyped-defs ...`

Implication:

- Recall now preserves six concrete longform runtime source families:
  - `chapter_summary`
  - `accepted_story_segment`
  - `continuity_note`
  - `scene_transcript`
  - `character_long_history_summary`
  - `retired_foreshadow_summary`

## Next Executable Slice: Authoritative Foreshadow Terminal Snapshot Production

Chosen next implementation slice:

- `.trellis/spec/backend/rp-foreshadow-terminal-snapshot-production.md`

Objective:

- close the remaining real gap behind `retired_foreshadow_summary`: authoritative terminal foreshadow snapshots still need a grounded producer in the normal chapter-close path;
- keep the producer rooted in explicit structured signal instead of prose inference;
- reuse the existing append-only `foreshadow_registry` proposal/apply chain instead of inventing a new mutation surface.

Planned implementation direction:

- consume explicit `StoryArtifact.metadata["foreshadow_status_updates"]` on accepted `story_segment` artifacts during `COMPLETE_CHAPTER`;
- make `LongformSpecialistService._fallback_bundle(...)` emit `state_patch_proposals["foreshadow_registry"]` from those explicit terminal updates;
- keep the slice conservative:
  - only non-blank `foreshadow_id`;
  - only terminal `status` / `state` values `resolved`, `retired`, `closed`;
  - later accepted-segment update wins per `foreshadow_id`;
  - identical reruns do not re-append the same normalized terminal snapshot.

Status on 2026-04-28:

- implemented chapter-close fallback production for authoritative foreshadow terminal snapshots;
- accepted `story_segment` metadata can now carry explicit `foreshadow_status_updates`, and heavy regression routes them through the existing append-only proposal/apply flow;
- retired-foreshadow Recall retention now has a real upstream authoritative producer when explicit metadata is present;
- chapter-close reruns no longer duplicate identical terminal snapshots already present in `foreshadow_registry`.

Implication:

- the retired-foreshadow path is no longer only a downstream consumer of monkeypatched or out-of-band state;
- the next real gap, if this area needs more power later, is upstream structured authoring of foreshadow updates by writer/specialist tooling rather than Recall retention itself.

## Next Executable Slice: Story Segment Structured Metadata Authoring

Chosen next implementation slice:

- `.trellis/spec/backend/rp-story-segment-structured-metadata-authoring.md`

Objective:

- freeze a real upstream contract for who authors `foreshadow_status_updates` before chapter-close consumers read them;
- keep the producer rooted in specialist-owned structured sidecar metadata rather than writer prose or `summary_updates`;
- persist the sidecar on draft `story_segment` artifacts so accept/complete-chapter can reuse the existing downstream path unchanged.

Planned implementation direction:

- add a narrow typed `story_segment_metadata` sidecar to `SpecialistResultBundle`;
- only freeze the currently real family: `foreshadow_status_updates`;
- normalize and persist that sidecar in `StoryTurnDomainService._persist_generated_artifact_impl(...)` when creating draft `story_segment` artifacts;
- keep `WritingWorkerExecutionService` text-only;
- let `ACCEPT_PENDING_SEGMENT` preserve metadata and let `COMPLETE_CHAPTER` remain a downstream consumer.

Status on 2026-04-28:

- implemented a typed `story_segment_metadata` sidecar on `SpecialistResultBundle`;
- draft `story_segment` persistence now normalizes and stores `foreshadow_status_updates` together with runtime-authored base metadata;
- `ACCEPT_PENDING_SEGMENT` preserves the stored metadata unchanged, and `COMPLETE_CHAPTER` reuses the existing downstream consumer path without any prose inference;
- DSL docs now expose the same sidecar family on `runtime.packet.worker_result_bundle`;
- broader automatic metadata authoring remains out of scope until this typed sidecar path is stable.

Quality gate:

- focused verification passed:
  - `pytest tests/test_rp_story_api.py::test_story_turn_chain_runs_outline_segment_and_complete rp/tests/test_projection_builder_services.py::test_story_segment_structured_metadata_normalizes_latest_foreshadow_update rp/tests/test_projection_builder_services.py::test_orchestrator_and_specialist_include_block_prompt_context -q`
    - `3 passed, 10 warnings`
  - `pytest rp/tests/test_projection_builder_services.py::test_story_segment_structured_metadata_normalizes_latest_foreshadow_update rp/tests/test_projection_builder_services.py::test_orchestrator_and_specialist_include_block_prompt_context -q`
    - `2 passed, 1 warning`
  - `ruff check rp/models/story_runtime.py rp/services/story_turn_domain_service.py rp/services/longform_specialist_service.py rp/tests/test_projection_builder_services.py tests/test_rp_story_api.py`
  - `mypy --follow-imports=skip --check-untyped-defs rp/models/story_runtime.py rp/services/story_turn_domain_service.py rp/services/longform_specialist_service.py rp/tests/test_projection_builder_services.py tests/test_rp_story_api.py`

Post-check learning captured on 2026-04-28:

- formal `trellis-check` found one real spec drift after the initial slice landed:
  - `story_segment_metadata.foreshadow_status_updates` had to remain typed in `model_json_schema()` rather than silently widening to generic `object[]`;
  - malformed items still had to degrade quietly instead of failing the entire specialist bundle;
- this was fixed by keeping typed item models plus pre-validation normalization, and by adding regression coverage for both schema shape and degradation behavior.

## Next Executable Slice: Story Segment Accept Metadata Promotion

Chosen next implementation slice:

- `.trellis/spec/backend/rp-story-segment-accept-metadata-promotion.md`

Objective:

- add a stable, review-adjacent producer surface for accepted-segment structured metadata instead of relying only on pre-write specialist output;
- let `ACCEPT_PENDING_SEGMENT` optionally promote or override the managed `foreshadow_status_updates` family through a typed request patch;
- keep authoritative truth downstream at chapter close via the existing proposal/apply path.

Planned implementation direction:

- extend `LongformTurnRequest` with an optional typed `story_segment_metadata_patch`;
- propagate that field through the story API / graph request path;
- make `StoryTurnDomainService.accept_pending_segment(...)` preserve draft metadata by default, but replace managed families when an explicit normalized patch is supplied;
- reject the patch on non-accept commands so the contract stays command-scoped and explicit;
- add focused request-validation, accept-flow, and chapter-close integration coverage.

Status on 2026-04-28:

- implemented the optional typed `story_segment_metadata_patch` request field and propagated it through the story graph request/state path;
- `StoryTurnDomainService.accept_pending_segment(...)` now preserves draft metadata by default, replaces the managed `foreshadow_status_updates` family when an explicit patch is supplied, and clears that family when the normalized patch is empty;
- non-accept commands now fail explicitly when they send `story_segment_metadata_patch`;
- focused API coverage now locks:
  - preserve-without-patch;
  - replace-with-patch;
  - clear-with-empty-patch;
  - chapter-close downstream consumption of accept-time-promoted metadata.

Quality gate:

- `pytest tests/test_rp_story_api.py::test_story_turn_chain_runs_outline_segment_and_complete tests/test_rp_story_api.py::test_accept_pending_segment_patch_can_override_draft_structured_metadata tests/test_rp_story_api.py::test_accept_pending_segment_empty_patch_clears_draft_structured_metadata tests/test_rp_story_api.py::test_story_turn_rejects_story_segment_metadata_patch_on_non_accept_command -q`
  - result: `4 passed, 22 warnings`
- `ruff check rp/models/story_runtime.py rp/graphs/story_graph_state.py rp/graphs/story_graph_runner.py rp/graphs/story_graph_nodes.py rp/services/story_turn_domain_service.py tests/test_rp_story_api.py`
- `mypy --follow-imports=skip --check-untyped-defs rp/models/story_runtime.py rp/graphs/story_graph_state.py rp/graphs/story_graph_runner.py rp/graphs/story_graph_nodes.py rp/services/story_turn_domain_service.py tests/test_rp_story_api.py`

Post-check learning captured on 2026-04-28:

- no additional spec drift was found after this slice landed;
- scoped verification also cleaned two pre-existing graph-shell static-check issues in touched files so the slice-local lint/type gate is green again.

## Next Executable Slice: Memory Visibility Overview

Chosen next implementation slice:

- `.trellis/spec/backend/rp-memory-visibility-overview.md`

Objective:

- add a memory-layer-only read overview that does not depend on upstream structured metadata producers;
- make current Core State / Runtime Workspace / proposal / consumer state capabilities visible from one active-story memory read surface;
- explicitly report which capabilities are authoritative truth, derived projection, retrieval-backed history/source material, or read-only runtime scratch;
- keep the surface read-only and avoid adding new mutation, retrieval, or durable Block registry dependencies.

Planned implementation direction:

- add `StoryRuntimeController.read_memory_overview(...)`;
- expose `GET /api/rp/story-sessions/{session_id}/memory/overview`;
- aggregate existing `RpBlockReadService`, `MemoryInspectionReadService`, and optional `StoryBlockConsumerStateService` outputs;
- report Recall / Archival as retrieval-backed surfaces without attempting retrieval-core counting in this slice;
- add focused controller and API coverage proving overview counts existing blocks/proposals/consumers and preserves missing-session behavior.

Status on 2026-04-28:

- implemented a read-only active-story memory overview endpoint;
- overview reports block totals by layer/source, layer capability boundaries, proposal counts by status, consumer dirty state, and explicit boundary markers;
- Runtime Workspace is reported as `unsupported_read_only` / `unsupported` history rather than durable truth;
- Recall and Archival are reported as retrieval-core surfaces with item counts intentionally out of scope for this controller surface;
- missing-session handling follows existing memory read routes.

Quality gate:

- `pytest rp/tests/test_story_runtime_controller_memory_read_side.py::test_story_runtime_controller_exposes_memory_read_side tests/test_rp_story_api.py::test_story_memory_block_routes_read_formal_blocks_and_filter_list tests/test_rp_story_api.py::test_story_memory_routes_return_404_for_missing_session -q`
  - result: `3 passed, 13 warnings`
- `ruff check rp/services/story_runtime_controller.py tests/test_rp_story_api.py rp/tests/test_story_runtime_controller_memory_read_side.py api/rp_story.py`
- `mypy --follow-imports=skip --check-untyped-defs rp/services/story_runtime_controller.py tests/test_rp_story_api.py rp/tests/test_story_runtime_controller_memory_read_side.py api/rp_story.py`

Post-check learning captured on 2026-04-28:

- this slice confirms the most useful next memory-layer work is visibility and boundary exposure, not a new durable Block store;
- Recall / Archival counts should stay deferred until the runtime controller deliberately owns a retrieval-core read dependency or a separate broker-backed overview spec is written.

## Next Executable Slice: Memory Block Capability Metadata

Chosen next implementation slice:

- `.trellis/spec/backend/rp-memory-block-capability-metadata.md`

Objective:

- make every current Block-compatible read view expose machine-checkable capability metadata:
  - `read_only`
  - `mutation_mode`
  - `history_mode`
  - `proposal_visibility`
- turn the already-intended read-only boundary for projection, runtime workspace, Recall, and Archival Block views into an explicit mutation guard;
- keep authoritative Core State as the only governed mutable Block family, still routed through proposal/apply;
- avoid any upstream dependency, new durable `rp_blocks` table, or public memory tool widening.

Planned implementation direction:

- add generated capability metadata in `RpBlockReadService` for authoritative, projection, and Runtime Workspace Block views;
- add generated capability metadata in `RetrievalBlockAdapterService` for Recall / Archival retrieval-backed Block views;
- make `StoryBlockMutationService` reject `metadata["read_only"] is True` before operation normalization, then keep the existing authoritative-layer guard as a legacy/malformed Block fallback;
- extend focused controller/API/retrieval adapter tests to lock serialized metadata and unsupported mutation behavior.

Status on 2026-04-28:

- implemented generated capability metadata for:
  - Core State authoritative Blocks: mutable only through governed proposal/apply;
  - Core State projection Blocks: read-only projection read-side;
  - Runtime Workspace Blocks: read-only current-turn scratch;
  - retrieval-backed Recall / Archival Block-compatible views: read-only retrieval-backed views.
- `StoryBlockMutationService` now checks `metadata["read_only"] is True` before operation normalization and keeps the existing authoritative-layer guard as fallback.
- focused tests now prove generated capability metadata overrides conflicting stored or retrieval-hit metadata.
- no new durable storage, public tool family, direct state write path, or upstream runtime producer dependency was introduced.

Quality gate:

- `pytest rp/tests/test_story_runtime_controller_memory_read_side.py::test_story_runtime_controller_exposes_memory_read_side rp/tests/test_story_runtime_controller_memory_read_side.py::test_story_runtime_controller_exposes_runtime_workspace_blocks_as_read_only_views tests/test_rp_story_api.py::test_story_memory_block_routes_read_formal_blocks_and_filter_list tests/test_rp_story_api.py::test_story_memory_block_proposal_submission_is_governed tests/test_rp_story_api.py::test_story_memory_block_proposal_detail_and_apply_errors rp/tests/test_retrieval_block_adapter_service.py -q`
  - result: `7 passed, 17 warnings`
- `ruff check rp/services/rp_block_read_service.py rp/services/retrieval_block_adapter_service.py rp/services/story_block_mutation_service.py rp/tests/test_story_runtime_controller_memory_read_side.py tests/test_rp_story_api.py rp/tests/test_retrieval_block_adapter_service.py`
- `mypy --follow-imports=skip --check-untyped-defs rp/services/rp_block_read_service.py rp/services/retrieval_block_adapter_service.py rp/services/story_block_mutation_service.py rp/tests/test_story_runtime_controller_memory_read_side.py tests/test_rp_story_api.py rp/tests/test_retrieval_block_adapter_service.py`

Post-check learning captured on 2026-04-28:

- `trellis-check` found one real test gap:
  - Core State stored metadata conflict override had to be explicitly tested for service and API read surfaces;
  - fixed by seeding conflicting `read_only` / `mutation_mode` / `history_mode` / `proposal_visibility` values and asserting generated capability metadata wins.

## Next Executable Slice: Memory Materialization Intake Contract

Chosen next implementation slice:

- `.trellis/spec/backend/rp-memory-materialization-intake-contract.md`

Objective:

- freeze the memory-layer intake metadata contract before all runtime producers converge;
- make Recall materialization metadata canonical and generated by the memory layer rather than hand-built in each ingestion service;
- ensure parent `SourceAsset.metadata` and `seed_sections[*].metadata` carry the same required fields;
- prevent upstream/runtime-provided metadata from redefining `layer`, `source_family`, `materialized_to_recall`, `source_type`, or Recall `domain`;
- keep this memory-layer-only: no new public tools, no new durable `rp_blocks`, no direct Core State writes, and no runtime producer implementation.

Planned implementation direction:

- add a shared metadata helper in the memory model layer for:
  - `build_recall_materialization_metadata(...)`;
  - `build_recall_seed_section(...)`;
- route existing Recall ingestion services through the helper for:
  - `chapter_summary`;
  - `accepted_story_segment`;
  - `continuity_note`;
  - `scene_transcript`;
  - `character_long_history_summary`;
  - `retired_foreshadow_summary`;
- add focused tests proving canonical fields are generated, conflicting extras cannot override ownership fields, invalid required fields fail early, and seed-section metadata mirrors the parent metadata.

Status on 2026-04-28:

- added the executable intake spec and registered it in the backend spec index plus task implement/check context;
- added `rp.models.memory_materialization` as the canonical memory-layer helper for Recall materialization metadata and seed sections;
- routed existing Recall ingestion services through the shared helper for:
  - `chapter_summary`;
  - `accepted_story_segment`;
  - `continuity_note`;
  - `scene_transcript`;
  - `character_long_history_summary`;
  - `retired_foreshadow_summary`.
- focused tests now prove canonical metadata generation, upstream-conflict override protection, required-field validation, and seed-section metadata parity;
- no runtime producer, public memory tool, durable `rp_blocks` table, or direct Core State write path was added.

Quality gate:

- `pytest rp/tests/test_memory_materialization_contract.py rp/tests/test_recall_continuity_note_ingestion_service.py rp/tests/test_recall_detail_ingestion_service.py rp/tests/test_recall_summary_ingestion_service.py rp/tests/test_recall_character_long_history_ingestion_service.py rp/tests/test_recall_retired_foreshadow_ingestion_service.py rp/tests/test_recall_scene_transcript_ingestion_service.py -q`
  - result: `42 passed, 1 warning`
- `ruff check rp/models/memory_materialization.py rp/services/recall_summary_ingestion_service.py rp/services/recall_detail_ingestion_service.py rp/services/recall_continuity_note_ingestion_service.py rp/services/recall_character_long_history_ingestion_service.py rp/services/recall_retired_foreshadow_ingestion_service.py rp/services/recall_scene_transcript_ingestion_service.py rp/tests/test_memory_materialization_contract.py`
- `ruff format --check rp/models/memory_materialization.py rp/services/recall_summary_ingestion_service.py rp/services/recall_detail_ingestion_service.py rp/services/recall_continuity_note_ingestion_service.py rp/services/recall_character_long_history_ingestion_service.py rp/services/recall_retired_foreshadow_ingestion_service.py rp/services/recall_scene_transcript_ingestion_service.py rp/tests/test_memory_materialization_contract.py`
- `mypy --follow-imports=skip --check-untyped-defs rp/models/memory_materialization.py rp/services/recall_summary_ingestion_service.py rp/services/recall_detail_ingestion_service.py rp/services/recall_continuity_note_ingestion_service.py rp/services/recall_character_long_history_ingestion_service.py rp/services/recall_retired_foreshadow_ingestion_service.py rp/services/recall_scene_transcript_ingestion_service.py rp/tests/test_memory_materialization_contract.py`

Post-check learning captured on 2026-04-28:

- `ruff format --check` caught one formatting-only issue in `recall_scene_transcript_ingestion_service.py`; fixed with scoped `ruff format` and re-ran the full focused gate.
- No additional spec drift was found: the new spec already freezes the intake contract and the implementation uses that contract as the single source for canonical Recall materialization metadata.
