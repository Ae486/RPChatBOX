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
| [RP Core State Block Envelope](./rp-core-state-block-envelope.md) | Read-only Block envelope over RP Core State formal store and compatibility mirrors | Active |
| [RP Authoritative Block Governed Mutation](./rp-authoritative-block-governed-mutation.md) | Block-addressed authoritative mutation entry that normalizes into the existing proposal/apply workflow | Active |
| [RP Authoritative Block Proposal Review Apply Visibility](./rp-authoritative-block-proposal-review-apply-visibility.md) | Block-scoped proposal detail and manual apply continuation over the existing proposal/apply persistence | Active |
| [RP Block Consumer Registry](./rp-block-consumer-registry.md) | Session-scoped active-story block consumer registry with lazy dirty evaluation | Active |
| [RP Active Story Block Prompt Context](./rp-active-story-block-prompt-context.md) | Internal Block-backed compile view for orchestrator and specialist without replacing writer packet | Active |
| [RP Active Story Block Prompt Rendering](./rp-active-story-block-prompt-rendering.md) | Deterministic Block overlay rendering for orchestrator and specialist system prompts | Active |
| [RP Active Story Block Lazy Rebuild](./rp-active-story-block-lazy-rebuild.md) | Cached internal Block prompt compilation with lazy rebuild for orchestrator and specialist | Active |
| [RP Memory Get State Summary Block Read Surface](./rp-memory-get-state-summary-block-read-surface.md) | RetrievalBroker-backed `memory.get_state` / `memory.get_summary` surface that resolves unmapped Core State targets through Block read adapters | Active |
| [RP Memory OS Block Rollout](./rp-memory-os-block-rollout.md) | Overall rollout contract from Core State Block integration to full Memory OS containerization | Active |
| [RP Memory Tool Chain Block Compatibility](./rp-memory-tool-chain-block-compatibility.md) | Compatibility gate that keeps the public memory tool chain stable after Core State Block integration | Active |
| [RP Memory Container Gap Inventory](./rp-memory-container-gap-inventory.md) | Phase C decision gate that proves whether a new durable container layer is actually required | Active |
| [RP Recall Detail Retention](./rp-recall-detail-retention.md) | Preserve accepted longform story prose into Recall Memory through retrieval-core so long-context detail remains recoverable | Active |
| [RP Memory Temporal Materialization](./rp-memory-temporal-materialization.md) | RP-specific ownership and materialization rules for current truth, hot projections, history, source knowledge, and runtime scratch | Active |
| [RP Retrieval Block-Compatible Views](./rp-retrieval-block-compatible-views.md) | Additive read-only Block-compatible views over recall/archival retrieval hits for runtime payloads | Active |
| [RP Retrieval Block Observability](./rp-retrieval-block-observability.md) | Additive retrieval observability field that exposes top-hit Block-compatible views without changing search results | Active |
| [RP Runtime Workspace Block Views](./rp-runtime-workspace-block-views.md) | Read-only Runtime Workspace Block views over current-chapter draft artifacts and discussion entries | Active |

## Pre-Development Checklist

- [ ] Read the relevant backend code-spec file for the module being changed.
- [ ] If the change touches Langfuse runtime settings or observability enablement, read [Langfuse Runtime Config Surface](./langfuse-runtime-config-surface.md).
- [ ] If the change touches SetupAgent context packet assembly, prior-stage handoffs, or budget-driven setup context compaction, read [RP Setup Agent Prior-Stage Handoff Context](./rp-setup-agent-prior-stage-handoff-context.md).
- [ ] If the change touches SetupAgent current-step context governance, digest/tool-outcome retention, history compaction, or no-progress guards, read [RP Setup Agent Stage-Local Context Governance](./rp-setup-agent-stage-local-context-governance.md).
- [ ] If the change touches RP memory/Core State, read [RP Core State Block Envelope](./rp-core-state-block-envelope.md).
- [ ] If the change adds or modifies block-addressed authoritative mutation, read [RP Authoritative Block Governed Mutation](./rp-authoritative-block-governed-mutation.md).
- [ ] If the change adds or modifies block-scoped proposal review/apply visibility, read [RP Authoritative Block Proposal Review Apply Visibility](./rp-authoritative-block-proposal-review-apply-visibility.md).
- [ ] If the change touches RP block consumers or dirty tracking, read [RP Block Consumer Registry](./rp-block-consumer-registry.md).
- [ ] If the change touches orchestrator/specialist Block-backed internal compile, read [RP Active Story Block Prompt Context](./rp-active-story-block-prompt-context.md).
- [ ] If the change touches Block-backed prompt rendering, read [RP Active Story Block Prompt Rendering](./rp-active-story-block-prompt-rendering.md).
- [ ] If the change touches Block prompt caching or lazy rebuild, read [RP Active Story Block Lazy Rebuild](./rp-active-story-block-lazy-rebuild.md).
- [ ] If the change touches `memory.get_state` / `memory.get_summary` read semantics through `RetrievalBroker`, read [RP Memory Get State Summary Block Read Surface](./rp-memory-get-state-summary-block-read-surface.md).
- [ ] If the change adjusts overall Memory OS Block sequencing, read [RP Memory OS Block Rollout](./rp-memory-os-block-rollout.md).
- [ ] If the change touches memory tool/provider compatibility after Block integration, read [RP Memory Tool Chain Block Compatibility](./rp-memory-tool-chain-block-compatibility.md).
- [ ] If the change decides whether a new durable Memory OS container layer is needed, read [RP Memory Container Gap Inventory](./rp-memory-container-gap-inventory.md).
- [ ] If the change adds settled-detail retention into Recall Memory, read [RP Recall Detail Retention](./rp-recall-detail-retention.md).
- [ ] If the change decides where current, historical, archival, or runtime-scratch memory material belongs, read [RP Memory Temporal Materialization](./rp-memory-temporal-materialization.md).
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
- [ ] Public memory tool/provider contracts remain stable after Block integration unless a spec explicitly widens them.
- [ ] Retrieval-backed Block-compatible views stay additive/read-only and do not replace public search results or active-story Core State `block_context`.
- [ ] Retrieval observability Block fields reuse the canonical retrieval Block adapter and stay additive to existing hit-centric payloads.
- [ ] Runtime Workspace Block views stay read-only/session-scoped and do not widen mutation/history support.
- [ ] Recall detail retention preserves settled prose through retrieval-core without treating drafts as history or replacing chapter summaries.
- [ ] Memory materialization keeps current truth, current projections, historical recall, source archival material, and runtime scratch in their assigned layers.
- [ ] Lint/format and relevant scoped type checks pass.
