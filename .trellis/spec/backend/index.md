# Backend Code Specs

> Concrete backend implementation contracts for this project.

## Guidelines Index

| Guide | Description | Status |
|---|---|---|
| [Langfuse Runtime Config Surface](./langfuse-runtime-config-surface.md) | Backend-owned Langfuse runtime config, persistence, and safe settings summary contract | Active |
| [RP Eval Langfuse Diagnostics](./rp-eval-langfuse-diagnostics.md) | Offline eval replay/suite/comparison contracts for Langfuse diagnostic sync | Active |
| [RP Eval Diagnostics CLI Surfaces](./rp-eval-diagnostics-cli-surfaces.md) | Setup diagnostic reason-code extraction and default CLI summary contracts | Active |
| [RP Eval Setup Case Contracts](./rp-eval-setup-case-contracts.md) | Setup bad-path eval case contract for expected diagnostics coverage | Active |
| [RP Setup Agent Prior-Stage Handoff Context](./rp-setup-agent-prior-stage-handoff-context.md) | Compact earlier-stage truth handoffs and budget-driven setup context compaction | Active |
| [RP Setup Agent Stage-Local Context Governance](./rp-setup-agent-stage-local-context-governance.md) | Thin working digest, retained tool outcomes, compacted current-step history, and minimal no-progress guards | Active |
| [RP Setup Agent Pre-Model Context Assembly](./rp-setup-agent-pre-model-context-assembly.md) | Deterministic `SetupContextPacket -> governed history -> runtime overlay -> final request messages` contract for setup turns | Active |
| [RP Setup Agent Stage-Aware Tool Scope](./rp-setup-agent-stage-aware-tool-scope.md) | Shared tools plus current-step patch-family narrowing for setup-turn tool visibility | Active |
| [RP Setup Agent Structured Output Schema Repair](./rp-setup-agent-structured-output-schema-repair.md) | Machine-readable pydantic validation errors, one bounded schema repair retry, and deterministic blocking of false-success turn completion | Active |
| [RP Setup Agent Loop Semantics ReAct Trace](./rp-setup-agent-loop-semantics-react-trace.md) | Explicit turn-loop order, continue/finish taxonomy, and thin runtime-authored ReAct trace above the current LangGraph graph | Active |
| [RP Setup Agent Runtime-V2 Only Convergence](./rp-setup-agent-runtime-v2-only-convergence.md) | Remove the transitional setup legacy runtime path and keep every setup entrypoint on the runtime-v2 engine | Active |
| [RP Setup Graph Shell Thin Checkpoint Contract](./rp-setup-graph-shell-thin-checkpoint-contract.md) | Keep the outer SetupGraph shell focused on checkpoint/routing and remove duplicate setup context assembly from the shell layer | Active |
| [RP Setup Agent Execution Service Outer-Harness Thin Boundary](./rp-setup-agent-execution-service-outer-harness-thin-boundary.md) | Keep `SetupAgentExecutionService` on one shared preflight/launch boundary and prevent text/stream public-path drift | Active |
| [RP Core State Block Envelope](./rp-core-state-block-envelope.md) | Read-only Block envelope over RP Core State formal store and compatibility mirrors | Active |
| [RP Authoritative Block Governed Mutation](./rp-authoritative-block-governed-mutation.md) | Block-addressed authoritative mutation entry that normalizes into the existing proposal/apply workflow | Active |
| [RP Authoritative Block Proposal Review Apply Visibility](./rp-authoritative-block-proposal-review-apply-visibility.md) | Block-scoped proposal detail and manual apply continuation over the existing proposal/apply persistence | Active |
| [RP Block Consumer Registry](./rp-block-consumer-registry.md) | Session-scoped active-story block consumer registry with lazy dirty evaluation | Active |
| [RP Active Story Block Prompt Context](./rp-active-story-block-prompt-context.md) | Internal Block-backed compile view for orchestrator and specialist without replacing writer packet | Active |
| [RP Active Story Block Prompt Rendering](./rp-active-story-block-prompt-rendering.md) | Deterministic Block overlay rendering for orchestrator and specialist system prompts | Active |
| [RP Active Story Block Lazy Rebuild](./rp-active-story-block-lazy-rebuild.md) | Cached internal Block prompt compilation with lazy rebuild for orchestrator and specialist | Active |
| [RP Memory Get State Summary Block Read Surface](./rp-memory-get-state-summary-block-read-surface.md) | RetrievalBroker-backed `memory.get_state` / `memory.get_summary` surface that resolves unmapped Core State targets through Block read adapters | Active |
| [RP Memory Visibility Overview](./rp-memory-visibility-overview.md) | Read-only active-story memory overview that exposes layer capabilities, block counts, proposal state, consumer dirty state, and boundary markers | Active |
| [RP Memory Block Capability Metadata](./rp-memory-block-capability-metadata.md) | Machine-checkable Block view capability metadata and read-only mutation guard enforcement across Core State, Runtime Workspace, and retrieval-backed views | Active |
| [RP Memory Materialization Intake Contract](./rp-memory-materialization-intake-contract.md) | Canonical Recall materialization metadata and seed-section intake contract that memory freezes before upstream runtime producers converge | Active |
| [RP Archival Knowledge Intake Contract](./rp-archival-knowledge-intake-contract.md) | Canonical Archival source-material metadata and seed-section intake contract for setup/source imports before upstream producers converge | Active |
| [RP Memory OS Block Rollout](./rp-memory-os-block-rollout.md) | Overall rollout contract from Core State Block integration to full Memory OS containerization | Active |
| [RP Memory Tool Chain Block Compatibility](./rp-memory-tool-chain-block-compatibility.md) | Compatibility gate that keeps the public memory tool chain stable after Core State Block integration | Active |
| [RP Memory Container Gap Inventory](./rp-memory-container-gap-inventory.md) | Phase C decision gate that proves whether a new durable container layer is actually required | Active |
| [RP Recall Detail Retention](./rp-recall-detail-retention.md) | Preserve accepted longform story prose into Recall Memory through retrieval-core so long-context detail remains recoverable | Active |
| [RP Recall Character Long-History Retention](./rp-recall-character-long-history-retention.md) | Materialize chapter-close authoritative `character_state_digest` snapshots into per-character Recall history summaries | Active |
| [RP Recall Retired Foreshadow Retention](./rp-recall-retired-foreshadow-retention.md) | Materialize chapter-close authoritative terminal `foreshadow_registry` snapshots into per-foreshadow Recall history summaries | Active |
| [RP Foreshadow Terminal Snapshot Production](./rp-foreshadow-terminal-snapshot-production.md) | Produce chapter-close authoritative terminal `foreshadow_registry` snapshots from explicit accepted-segment metadata through the existing append-only proposal/apply chain | Active |
| [RP Story Segment Structured Metadata Authoring](./rp-story-segment-structured-metadata-authoring.md) | Freeze the specialist-owned structured metadata sidecar that persists on draft story segments before chapter-close consumers read it | Active |
| [RP Story Segment Accept Metadata Promotion](./rp-story-segment-accept-metadata-promotion.md) | Allow `ACCEPT_PENDING_SEGMENT` to promote or override whitelisted structured metadata families on accepted story segments through a typed request patch | Active |
| [RP Memory Temporal Materialization](./rp-memory-temporal-materialization.md) | RP-specific ownership and materialization rules for current truth, hot projections, history, source knowledge, and runtime scratch | Active |
| [RP Recall Source Family Retrieval Contract](./rp-recall-source-family-retrieval-contract.md) | Preserve Recall materialization source-family metadata through search hits, Block-compatible views, and specialist payloads | Active |
| [RP Recall Continuity Note Retention](./rp-recall-continuity-note-retention.md) | Materialize heavy-regression summary updates into Recall continuity notes without promoting runtime scratch or mutating Core State | Active |
| [RP Recall Source Family Search Filters](./rp-recall-source-family-search-filters.md) | Reuse `memory.search_recall(..., filters=...)` to target specific Recall source families, materialization kinds, and chapter indices | Active |
| [RP Recall Scene Transcript Promotion](./rp-recall-scene-transcript-promotion.md) | Freeze the closed-scene transcript promotion contract so Runtime Workspace discussion never becomes Recall history by accident | Active |
| [RP Runtime Scene Lifecycle](./rp-runtime-scene-lifecycle.md) | Add explicit runtime scene identity and close-trigger scaffolding before transcript promotion or Core State scene materialization | Active |
| [RP Narrative Retrieval Policy Contract](./rp-narrative-retrieval-policy-contract.md) | Freeze the narrative-aware search policy, filters, rerank strategy, scoring trace, context budget, and eval gaps for longform/RP retrieval | Active |
| [RP Retrieval Block-Compatible Views](./rp-retrieval-block-compatible-views.md) | Additive read-only Block-compatible views over recall/archival retrieval hits for runtime payloads | Active |
| [RP Retrieval Block Observability](./rp-retrieval-block-observability.md) | Additive retrieval observability field that exposes top-hit Block-compatible views without changing search results | Active |
| [RP Runtime Workspace Block Views](./rp-runtime-workspace-block-views.md) | Read-only Runtime Workspace Block views over current-chapter draft artifacts and discussion entries | Active |

## Pre-Development Checklist

- [ ] Read the relevant backend code-spec file for the module being changed.
- [ ] If the change touches Langfuse runtime settings or observability enablement, read [Langfuse Runtime Config Surface](./langfuse-runtime-config-surface.md).
- [ ] If the change touches SetupAgent context packet assembly, prior-stage handoffs, or budget-driven setup context compaction, read [RP Setup Agent Prior-Stage Handoff Context](./rp-setup-agent-prior-stage-handoff-context.md).
- [ ] If the change touches SetupAgent current-step context governance, digest/tool-outcome retention, history compaction, or no-progress guards, read [RP Setup Agent Stage-Local Context Governance](./rp-setup-agent-stage-local-context-governance.md).
- [ ] If the change touches SetupAgent pre-model context assembly, runtime overlay insertion, or final request message ordering, read [RP Setup Agent Pre-Model Context Assembly](./rp-setup-agent-pre-model-context-assembly.md).
- [ ] If the change touches SetupAgent per-step tool visibility, narrowed allowed-tool scope, or patch-family exposure, read [RP Setup Agent Stage-Aware Tool Scope](./rp-setup-agent-stage-aware-tool-scope.md).
- [ ] If the change touches SetupAgent pydantic validation payloads, schema repair retry behavior, or false-success blocking after tool validation failure, read [RP Setup Agent Structured Output Schema Repair](./rp-setup-agent-structured-output-schema-repair.md).
- [ ] If the change touches SetupAgent turn-loop order, graph-route meaning, runtime trace, or continue/finish semantics, read [RP Setup Agent Loop Semantics ReAct Trace](./rp-setup-agent-loop-semantics-react-trace.md).
- [ ] If the change touches SetupAgent runtime entrypoint wiring, factory convergence, or removal of the transitional legacy runtime path, read [RP Setup Agent Runtime-V2 Only Convergence](./rp-setup-agent-runtime-v2-only-convergence.md).
- [ ] If the change touches the phase-1 SetupGraph shell, stream checkpoint seeding, or graph-level duplication of setup context assembly, read [RP Setup Graph Shell Thin Checkpoint Contract](./rp-setup-graph-shell-thin-checkpoint-contract.md).
- [ ] If the change touches `SetupAgentExecutionService` public turn entrypoints, shared preflight, or text/stream launch drift, read [RP Setup Agent Execution Service Outer-Harness Thin Boundary](./rp-setup-agent-execution-service-outer-harness-thin-boundary.md).
- [ ] If the change touches RP memory/Core State, read [RP Core State Block Envelope](./rp-core-state-block-envelope.md).
- [ ] If the change adds or modifies block-addressed authoritative mutation, read [RP Authoritative Block Governed Mutation](./rp-authoritative-block-governed-mutation.md).
- [ ] If the change adds or modifies block-scoped proposal review/apply visibility, read [RP Authoritative Block Proposal Review Apply Visibility](./rp-authoritative-block-proposal-review-apply-visibility.md).
- [ ] If the change touches RP block consumers or dirty tracking, read [RP Block Consumer Registry](./rp-block-consumer-registry.md).
- [ ] If the change touches orchestrator/specialist Block-backed internal compile, read [RP Active Story Block Prompt Context](./rp-active-story-block-prompt-context.md).
- [ ] If the change touches Block-backed prompt rendering, read [RP Active Story Block Prompt Rendering](./rp-active-story-block-prompt-rendering.md).
- [ ] If the change touches Block prompt caching or lazy rebuild, read [RP Active Story Block Lazy Rebuild](./rp-active-story-block-lazy-rebuild.md).
- [ ] If the change touches `memory.get_state` / `memory.get_summary` read semantics through `RetrievalBroker`, read [RP Memory Get State Summary Block Read Surface](./rp-memory-get-state-summary-block-read-surface.md).
- [ ] If the change adds or modifies active-story memory overview / capability visibility surfaces, read [RP Memory Visibility Overview](./rp-memory-visibility-overview.md).
- [ ] If the change adds or modifies Block read-only, mutation, history, or proposal capability metadata, read [RP Memory Block Capability Metadata](./rp-memory-block-capability-metadata.md).
- [ ] If the change adds or modifies Recall materialization metadata, seed-section metadata, or memory intake semantics for runtime-produced material, read [RP Memory Materialization Intake Contract](./rp-memory-materialization-intake-contract.md).
- [ ] If the change adds or modifies Archival Knowledge source-material metadata, seed-section metadata, or setup/source import semantics, read [RP Archival Knowledge Intake Contract](./rp-archival-knowledge-intake-contract.md).
- [ ] If the change adjusts overall Memory OS Block sequencing, read [RP Memory OS Block Rollout](./rp-memory-os-block-rollout.md).
- [ ] If the change touches memory tool/provider compatibility after Block integration, read [RP Memory Tool Chain Block Compatibility](./rp-memory-tool-chain-block-compatibility.md).
- [ ] If the change decides whether a new durable Memory OS container layer is needed, read [RP Memory Container Gap Inventory](./rp-memory-container-gap-inventory.md).
- [ ] If the change adds settled-detail retention into Recall Memory, read [RP Recall Detail Retention](./rp-recall-detail-retention.md).
- [ ] If the change adds chapter-close historical character Recall summaries, read [RP Recall Character Long-History Retention](./rp-recall-character-long-history-retention.md).
- [ ] If the change adds chapter-close retired/resolved foreshadow Recall summaries, read [RP Recall Retired Foreshadow Retention](./rp-recall-retired-foreshadow-retention.md).
- [ ] If the change adds chapter-close authoritative foreshadow terminal snapshot production, read [RP Foreshadow Terminal Snapshot Production](./rp-foreshadow-terminal-snapshot-production.md).
- [ ] If the change adds or consumes structured maintenance metadata on `story_segment` artifacts, read [RP Story Segment Structured Metadata Authoring](./rp-story-segment-structured-metadata-authoring.md).
- [ ] If the change adds accept-time promotion or override of structured metadata on accepted story segments, read [RP Story Segment Accept Metadata Promotion](./rp-story-segment-accept-metadata-promotion.md).
- [ ] If the change decides where current, historical, archival, or runtime-scratch memory material belongs, read [RP Memory Temporal Materialization](./rp-memory-temporal-materialization.md).
- [ ] If the change touches Recall search metadata, source-family routing, or specialist payload use of Recall hits, read [RP Recall Source Family Retrieval Contract](./rp-recall-source-family-retrieval-contract.md).
- [ ] If the change materializes `summary_updates` or continuity maintenance output into Recall, read [RP Recall Continuity Note Retention](./rp-recall-continuity-note-retention.md).
- [ ] If the change narrows Recall search by source family or materialization metadata, read [RP Recall Source Family Search Filters](./rp-recall-source-family-search-filters.md).
- [ ] If the change promotes closed-scene transcript history into Recall, read [RP Recall Scene Transcript Promotion](./rp-recall-scene-transcript-promotion.md).
- [ ] If the change adds runtime scene identity, scene-close trigger behavior, or scene refs on runtime rows, read [RP Runtime Scene Lifecycle](./rp-runtime-scene-lifecycle.md).
- [ ] If the change adjusts longform/RP retrieval filters, rerank strategy, narrative scoring, context budget, or retrieval eval quality gates, read [RP Narrative Retrieval Policy Contract](./rp-narrative-retrieval-policy-contract.md).
- [ ] If the change adapts recall/archival retrieval results into Block-compatible runtime views, read [RP Retrieval Block-Compatible Views](./rp-retrieval-block-compatible-views.md).
- [ ] If the change adjusts retrieval observability or Langfuse payloads to expose Block-compatible views, read [RP Retrieval Block Observability](./rp-retrieval-block-observability.md).
- [ ] If the change exposes Runtime Workspace draft/discussion state through `/memory/blocks`, read [RP Runtime Workspace Block Views](./rp-runtime-workspace-block-views.md).
- [ ] Read shared guides:
  - `.trellis/spec/guides/cross-layer-thinking-guide.md`
  - `.trellis/spec/guides/code-reuse-thinking-guide.md`

## Quality Check

- [ ] New backend contracts have focused unit/integration tests.
- [ ] Cross-layer fields preserve existing identity and source metadata.
- [ ] Block-addressed mutation routes normalize into the existing proposal/apply workflow and do not introduce direct state writes.
- [ ] Block-scoped proposal detail/apply routes stay exact-target and session-scoped, and continue to reuse the existing proposal/apply persistence.
- [ ] Migration compatibility mirrors remain intact unless a task explicitly removes them.
- [ ] Block consumer dirty evaluation stays lazy/read-side unless a task explicitly introduces rebuild triggers.
- [ ] Internal Block compile stays limited to orchestrator/specialist and does not replace `WritingPacketBuilder`.
- [ ] Internal Block prompt rendering is deterministic and keeps retrieval separate from Block overlay rendering.
- [ ] Cached Block prompt overlays only reuse when current Block snapshot and consumer sync state still match the compiled snapshot.
- [ ] `memory.get_state` / `memory.get_summary` only use Block read adapters to fill unresolved Core State read gaps; they do not bypass RetrievalBroker or rewrite provider contracts.
- [ ] Memory overview stays read-only, reuses existing read surfaces, and reports adapter/read-only boundaries without adding mutation or retrieval dependencies.
- [ ] Block capability metadata is generated by read adapters, overrides conflicting stored metadata, and read-only Blocks are rejected before mutation normalization.
- [ ] Recall materialization metadata is generated by the memory intake helper, keeps canonical fields on parent assets and seed sections, and prevents upstream metadata from redefining memory-layer ownership.
- [ ] Archival Knowledge intake metadata is generated by the memory intake helper, keeps canonical fields on parent assets and seed sections, and prevents setup/source metadata from redefining memory-layer ownership.
- [ ] Public memory tool/provider contracts remain stable after Block integration unless a spec explicitly widens them.
- [ ] Retrieval-backed Block-compatible views stay additive/read-only and do not replace public search results or active-story Core State `block_context`.
- [ ] Retrieval observability Block fields reuse the canonical retrieval Block adapter and stay additive to existing hit-centric payloads.
- [ ] Runtime Workspace Block views stay read-only/session-scoped and do not widen mutation/history support.
- [ ] Recall detail retention preserves settled prose through retrieval-core without treating drafts as history or replacing chapter summaries.
- [ ] Character long-history retention is rooted in authoritative `character_state_digest` snapshots and does not overload `summary_updates` or runtime scratch.
- [ ] Retired-foreshadow retention is rooted in authoritative terminal `foreshadow_registry` snapshots and does not infer retirement from `summary_updates` or runtime scratch.
- [ ] Foreshadow terminal snapshot production is rooted in explicit accepted-segment metadata, stays append-only through proposal/apply, and does not duplicate identical snapshots on chapter-close rerun.
- [ ] Story-segment structured metadata stays specialist-owned, persists only validated sidecar families onto draft story segments, and does not promote writer prose or `summary_updates` into authoritative truth.
- [ ] Accept-time story-segment metadata promotion stays typed, command-scoped to `ACCEPT_PENDING_SEGMENT`, and only replaces managed artifact metadata families without becoming a new truth-write path.
- [ ] Memory materialization keeps current truth, current projections, historical recall, source archival material, and runtime scratch in their assigned layers.
- [ ] Recall retrieval preserves source-family/materialization metadata through raw hits, Block-compatible views, and specialist payloads.
- [ ] Continuity-note retention materializes only heavy-regression maintenance output and does not treat Runtime Workspace discussion as Recall history.
- [ ] Recall source-family filters reuse the existing `filters` contract and do not fabricate metadata for legacy hits.
- [ ] Scene transcript promotion requires explicit closed-scene identity and filtered source material; raw discussion rows never become Recall history by default.
- [ ] Runtime scene lifecycle seeds deterministic `scene_ref`, rotates only through explicit close behavior, and does not materialize Recall/Core State scene history by accident.
- [ ] Narrative retrieval policy keeps public memory search tools stable, resolves broker rerank strategy explicitly, uses structured filters instead of caller-side post-filtering, and emits ranking/budget trace for longform/RP context composition.
- [ ] SetupAgent loop routing, `continue_reason`, `finish_reason`, and runtime trace stay semantically aligned; `next_action` remains an internal graph-route token rather than a user-facing outcome contract.
- [ ] `SetupAgentExecutionService` text and stream entrypoints reuse the same outer-harness preflight and runtime-v2 launch boundaries; drift is limited to the true run vs run_stream split.
- [ ] Lint/format and relevant scoped type checks pass.
