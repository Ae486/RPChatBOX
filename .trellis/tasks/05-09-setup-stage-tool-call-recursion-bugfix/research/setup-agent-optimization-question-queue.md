# SetupAgent Optimization Question Queue

> Task: `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix`
>
> Purpose: Record unresolved requirement/design questions that cannot be safely decided from current discussion, active setup specs, code, or mature framework precedent.
>
> Status: active

## Rules

1. Do not add ordinary implementation uncertainties here.
2. Before adding a question, exhaust:
   - current user discussion constraints
   - active `.trellis/spec/backend/*` setup specs
   - task-local execution plan/spec docs
   - current code
   - pi-mono and Claude Code references
3. Add a question only when the answer affects implementation or verification.
4. Main brain owns routing: answer directly, ask user, or update spec.

## Open Questions

## Q1. Canonical stage draft write surface

- Status: answered
- Raised by: main-brain + Harvey review + user direction
- Module: Phase B / stage draft tools
- Blocking: implementation that hides, replaces, or demotes `setup.truth.write`
- Context:
  - Active specs currently define `setup.truth.write` as the canonical stage draft write path.
  - User direction favors content-first deterministic stage-native CRUD tools where the model fills simple parameters and fixed code owns draft structure.
  - The previous high-burden truth-write payload had very poor real-model success rate.
- Options:
  - A. Keep `setup.truth.write` model-visible, but simplify its model-facing schema further and route to deterministic draft CRUD internally.
  - B. Replace model-visible stage writes with stage-native tools such as `setup.world_background.write_entry/edit_entry/delete_entry`, backed by a shared draft CRUD service.
  - C. Support both temporarily, but expose only one canonical write surface per stage to the model.
- Current recommendation:
  - Prefer a single shared draft CRUD core with stage-local exposure via SkillPack. The model should see a unified CRUD surface, while stage-specific prompt packs can shape which subset/overrides are exposed per stage. Old conflicting tools may be retired after the new tool set proves stable in tests.
- Decision:
  - User decided to migrate to the new unified draft CRUD contract if the new tool set passes testing. Old tools can be retired.
- Follow-up:
  - Update setup specs to reflect unified draft CRUD + stage-local SkillPack exposure, and retire old tool contracts after validation.

## Q2. Scope of model config sync and dialogue persistence

- Status: deferred
- Raised by: Harvey review + user clarification
- Module: deferred Phase D/E
- Blocking: none for architecture-spine planning
- Context:
  - Setup model page drift and dialogue non-persistence are real product issues.
  - User clarified current focus is agent architecture optimization.
- Options:
  - A. Include in this task after loop spine.
  - B. Split into follow-up tasks.
- Current recommendation:
  - Defer unless architecture-spine tests require minimal transcript persistence.
- Decision:
  - Deferred from current architecture-spine slice.
- Follow-up:
  - Reopen after Phase A/B check if still needed.

## Q3. SkillPack stage expansion

- Status: deferred
- Raised by: Harvey review + user clarification
- Module: Phase F
- Blocking: none for loop/tool repair
- Context:
  - Current SkillPack demo/spec is character-stage oriented.
  - User is considering whether every stage should have corresponding skills.
- Options:
  - A. Keep current character demo only.
  - B. Add world_background SkillPack pilot.
  - C. Define a general SkillPack authoring contract before expanding stages.
- Current recommendation:
  - Keep current character demo for now; do not expand SkillPack during loop/tool repair.
- Decision:
  - Deferred.
- Follow-up:
  - Create a separate SkillPack governance slice after tool/write surface settles.

## Q4. Stage-local entry type registry location

- Status: answered
- Raised by: user direction
- Module: Phase B / draft CRUD
- Blocking: stage-native CRUD contract details
- Context:
  - User wants `entry_type` chosen by model and then reused consistently during draft editing.
  - User does not want this to enter long-term memory; it is draft-editing-period state.
  - Current generic draft schema has `SetupStageDraftSchemaMetadata.entry_types`.
- Options:
  - A. Store registered entry types in stage draft schema metadata.
  - B. Store in workspace transient runtime state.
  - C. Store only in prompt/digest memory.
- Current recommendation:
  - A, because it is visible to draft tools, persisted with the draft, retrieval-adjacent, and not Memory OS. It can later be excluded from retrieval materialization if needed.
- Decision:
  - Store registered entry types in stage draft schema metadata. This is setup draft editing state, not archival memory. It remains available to setup draft tools and can be used by setup truth index / seed materialization after commit.
- Follow-up:
  - If accepted, include in stage CRUD tool spec and tests.

## Q5. Setup lightweight retrieval ownership

- Status: answered
- Raised by: user direction
- Module: Phase A/B / setup context pipeline and setup truth index
- Blocking: architecture boundary for setup search/read tooling
- Context:
  - User describes setup stage flow as discussion plus draft edits, with occasional lookup of prior committed draft entries when proper nouns or compact hints lack detail.
  - Existing code already has setup-owned `setup.read.draft_refs` and `setup.truth_index.search/read_refs`.
  - Existing retrieval layer is primarily Memory OS / Recall / Archival retrieval infrastructure through `RetrievalBroker`, not the owner of editable setup draft truth.
- Options:
  - A. Keep setup lightweight retrieval inside setup as context/truth-index capability, and only hand accepted seed material to retrieval-core after commit.
  - B. Move setup draft search/read into retrieval-core.
  - C. Duplicate both paths and let tools decide.
- Current recommendation:
  - A. Setup owns editing-time draft refs, compact recovery, prior-stage handoffs, committed setup truth index, and exact setup reads. Retrieval-core owns downstream chunk/index/embedding/hybrid/rerank/runtime retrieval after accepted setup truth is materialized.
- Decision:
  - Adopt setup-owned lightweight retrieval. Do not call Memory OS retrieval to recover setup draft truth. Use setup-to-retrieval materialization as the boundary after accepted commit.
- Follow-up:
  - Architecture spine spec now records the `Setup Lightweight Retrieval Contract`.
  - Implementation specs should test `setup.read.draft_refs`, `setup.truth_index.search/read_refs`, and retrieval seed materialization boundaries without changing runtime-story Q files.

## Q6. Setup search selector strength

- Status: open
- Raised by: main-brain
- Module: Phase A/B / setup truth index and context pipeline
- Blocking: whether first implementation needs an LLM side-query selector
- Context:
  - Claude Code style retrieval often uses cheap deterministic search plus exact read, and sometimes a side-query over small candidate summaries.
  - Current `SetupTruthIndexService.search` is lexical/path/filter scoring over committed setup truth rows.
  - Setup should stay lightweight and avoid heavy RAG during editable setup.
- Options:
  - A. Keep first implementation deterministic only: lexical/path/filter search plus exact read, no LLM selector.
  - B. Add a bounded side-query selector over candidate previews when lexical search returns too many plausible refs.
  - C. Add embedding/hybrid search now through retrieval-core.
- Current recommendation:
  - A for the first architecture/tool repair slice. B can be added later as an optimization if evals show poor candidate selection. C is too heavy for setup editing-time recovery and blurs retrieval ownership.
- Decision:
  - Pending user confirmation.
- Follow-up:
  - If A is accepted, initial dev scope focuses on tool boundaries, loop repair, and deterministic setup reads/searches.
