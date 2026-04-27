# Main Brain Harness Engineering Research

## Background

This task is dedicated to the "main brain" session.

The immediate goal is not implementation. The goal is to establish a shared understanding of:

1. what "harness engineering" means in current agent-system practice
2. how OpenAI frames harness engineering for Codex / Agents SDK
3. how Anthropic frames harness / scaffold design for Claude / long-running agents / evals
4. what parts of the concept are relevant to `H:/chatboxapp`, especially RP agent, eval, tools, skills, and orchestration design

## Scope

In scope:

- official OpenAI material
- official Anthropic material
- concept clarification
- terminology alignment
- practical takeaways for "main brain" architecture discussion

Out of scope:

- code changes
- full implementation plan
- third-party opinion pieces unless needed as minor supporting context

## Deliverables

1. a research note under `research/`
2. a concise session summary for the user
3. a practical interpretation for future RP agent / eval / harness discussion
4. an evolving brainstorm plan for SetupAgent optimization
5. a development spec focused on SetupAgent loop / ReAct cognition / lifecycle

## Success Criteria

- the task clearly distinguishes `agent harness`, `evaluation harness`, and adjacent ideas like context engineering / tool orchestration
- OpenAI and Anthropic viewpoints are summarized without mixing them together
- the resulting explanation is useful for future "main brain" decision-making in this repository

## Brainstorm: SetupAgent Optimization

### Current Goal

Design the next-stage optimization direction for `SetupAgent` so it follows the harness-engineering paradigm and becomes more "agent-like" without losing setup's deterministic business boundaries.

### What We Already Know

- `SetupAgent` is prestory-only and should converge user discussion/assets into reviewable, committable setup truth.
- Current runtime already has `turn_goal`, `working_plan`, `pending_obligation`, `reflection_ticket`, and `completion_guard`.
- Current setup tools are partially shared and partially split by draft family.
- Shared cognitive/setup tools include `setup.discussion.update_state`, `setup.chunk.upsert`, `setup.truth.write`, `setup.question.raise`, `setup.asset.register`, `setup.proposal.commit`, `setup.read.workspace`, and `setup.read.step_context`.
- Draft-family patch tools include `setup.patch.story_config`, `setup.patch.writing_contract`, `setup.patch.foundation_entry`, and `setup.patch.longform_blueprint`.
- Current `setup_agent` runtime profile exposes the full setup tool set instead of a stage-aware subset.
- Current prompt assembly still embeds longform guidance directly in `SetupAgentPromptService`; runtime skill resources such as `setup-core-skill` and `setup-longform-skill` are not yet implemented as first-class backend assets.
- Setup-time mode profile should exist now, but remain lightweight. Heavy mode differences belong to active story runtime.

### Requirements (Evolving)

- Preserve setup boundaries: `SetupWorkspace` remains business truth, and setup does not mutate active runtime state.
- Treat the agent body as the first-class optimization target: loop semantics, ReAct-style observe/act/recover behavior, context governance, and completion policy come before skills/tool polish.
- Add stage-specific skill design, starting with longform-first setup stages.
- Keep domain knowledge in skills, not in tool descriptions or tool schemas.
- Prefer object-family tools over exploding into one CRUD tool family per micro-stage.
- Introduce a path toward stage-aware visible tool subsets.
- Treat eval as an auxiliary optimization module for prompt/tool/skill/workflow tuning, not as the main runtime capability.
- Skills and tools are harness surfaces, not the agent core. They should be designed after the runtime loop can reliably plan, act, observe, repair, compact context, and decide when to stop.
- Stage transitions should use compacted, structured setup truth instead of carrying raw previous-stage discussion details into the next stage.
- Foundation-stage output should be usable as retrieval-ready or retrieval-friendly chunks: each chunk needs stable title/description/content/metadata so later stages can depend on semantic summaries rather than polluted discussion history.
- The runtime should not rely only on the model "being obedient" when writing draft structure. Draft shape, chunk descriptions, and handoff summaries need validation or repair policies before a stage can be considered cleanly handed off.
- Foundation chunk schema should be tiered to reduce model burden:
  - LLM-authored required fields: title, description, content, chunk_type/tags, open_issues.
  - LLM-authored optional fields: dependencies, aliases, canonical_terms, questions_answered.
  - Runtime-owned fields: chunk_id, parent_id, workspace_id, story_id, mode, stage_id, commit_id, source_basis, version, timestamps, status, token_count, content_hash, embedding_model_version.
  - Retrieval-enrichment fields: extracted_entities, relationship_edges, keyword_terms, retrieval_text, filter_metadata, rerank_summary.
- The retrieval index should distinguish embedded text, filter metadata, and rerank/display payload. Not every field should be embedded, and not every field should be model-authored.

### Open Questions

- What exact stop/continue contract should SetupAgent use when the model produces both user-facing text and tool calls, or when no tool call is produced but the step is still incomplete?
- What context budget and compaction policy should setup use for per-turn messages, tool results, cognitive snapshots, and retrieval fallback?
- Which actions are safe for the runtime to auto-retry, and which must become an explicit user question or hard failure?
- What is the minimum required schema for a stage handoff packet, especially for foundation chunks that will later support retrieval and next-stage context injection?
- Which retrieval enrichment fields are MVP-critical for longform setup, and which should be delayed until retrieval eval shows a recall/precision gap?

### Confirmed Direction

- The next MVP slice is `Agent Loop / ReAct / Context-first`.
- The agent's own while-loop and middleware must become reliable before the outer harness can be made strong.
- This is an optimization and contract-convergence slice over existing SetupAgent loop/cognition/repair/context prototypes, not a rewrite-from-scratch effort.
- Skills, stage-specific tool visibility, and eval tuning remain important, but they are follow-up harness surfaces that should attach to a stronger loop rather than substitute for it.
- The target is not to copy a coding agent wholesale. The target is to extract reusable loop semantics and adapt them to setup's prestory business boundary.
- Stage handoff context should prefer `committed truth + compacted summaries + retrieval-friendly chunk descriptions` over raw prior discussion logs.

### Current Agent Body Assessment

- Current implementation already has a LangGraph-backed finite loop: prepare input, derive turn goal, plan step slice, build model request, call model, inspect model output, execute tools, apply results, assess progress, reflect if needed, and finalize.
- Current implementation has partial ReAct behavior: model emits tool calls, runtime executes tools, tool results are appended back into the message stream, then the graph can loop into another model round.
- Current implementation has runtime-private cognition fields: `turn_goal`, `working_plan`, `pending_obligation`, `last_failure`, `reflection_ticket`, `completion_guard`, `cognitive_state`, and `cognitive_state_summary`.
- Current implementation has basic context governance: `SetupContextBuilder` builds a step-scoped `SetupContextPacket`; `SetupAgentRuntimeStateService` persists compact per-step cognitive snapshots and summarizes them for prompt injection.
- Current implementation is still not a top-tier agent harness: it lacks a first-class explicit ReAct trace model, durable session/event transcript as the source of truth, principled context budget/compaction policy, long-horizon task decomposition, branch/resume semantics, and a richer self-repair loop beyond bounded retry/reflection policies.

### Borrowable References

- Claude Code architecture notes: borrow the two-layer split between session lifecycle and inner query loop, explicit continue sites, withheld recoverable errors, progressive context compression, prompt-cache-aware tool/context assembly, and tool result size governance.
- `pi-mono`: borrow the lightweight `Agent` wrapper plus low-level `agentLoop`, event stream contract, steering/follow-up queues, `transformContext -> convertToLlm` boundary, and before/after tool-call middleware.
- OpenAI Agents SDK: borrow the small primitive set around built-in agent loop, guardrails, sessions, handoffs, tracing, MCP/function tools, and the distinction between owning the loop directly versus using a managed runtime.
- Anthropic agent/eval/harness writing: borrow the vocabulary boundary between agent harness and eval harness, context reset/handoff thinking, generator/evaluator separation, and the principle that harness components should be stress-tested because they encode assumptions about model weakness.
- LangGraph: keep it as the graph execution substrate, but do not let the graph shape hide the agent contract. The semantic loop contract should be explicit above the graph nodes.

### Integrated Design Summary

#### 1. Core Positioning

- The current spec focus should be the agent body itself: loop semantics, runtime cognition, stop/continue policy, repair policy, and stage-to-stage context governance.
- Skills, tool subsets, retrieval enrichment, and eval remain important, but they are secondary harness layers that should attach to a stronger core loop.
- SetupAgent is not a generic long-running coding agent. It is a setup-domain agent whose job is to converge discussion and assets into structured, reviewable setup truth.

#### 2. Agent Loop

- The target design should explicitly separate:
  - outer session/harness lifecycle
  - inner per-turn agent loop
- The inner loop should be treated as a first-class while-loop contract, not just an implementation accident inside LangGraph nodes.
- A canonical setup turn should look like:
  - receive current step input
  - construct bounded context
  - derive turn goal
  - produce working plan
  - call model
  - inspect output
  - execute tool calls if any
  - interpret observations/tool results
  - decide continue / repair / ask user / finalize
- Continue reasons should become explicit runtime states, not just implicit graph routing.

#### 3. Agent Intelligence and ReAct

- Current implementation already has a partial ReAct skeleton, but it is still weakly expressed.
- The desired agent intelligence is not "more prompt cleverness". It is explicit runtime support for:
  - goal formation
  - action selection
  - observation handling
  - repair after failure
  - reflection before invalid completion
  - completion gating
- ReAct should be made first-class in runtime traces:
  - goal
  - plan
  - action
  - observation
  - reflection
  - next decision
- These structures are primarily for runtime policy, tracing, and eval attribution, not for exposing chain-of-thought to users.

#### 4. Error Handling and Self-Repair

- A capable setup agent must repair bounded mistakes inside the same loop instead of collapsing into user-visible failure too early.
- Example target behavior:
  - the model calls a setup tool
  - schema validation reports missing fields
  - runtime classifies the failure
  - runtime records a repair obligation with required fields
  - next loop turn must either emit a corrected tool call or ask a targeted user question
- Repair policy should distinguish at least:
  - auto-repair
  - ask-user
  - continue-discussion
  - block-commit
  - unrecoverable
- This means the runtime must carry structured failure semantics rather than only raw error text.

#### 5. Stop / Continue / Lifecycle Semantics

- "No tool call" must not automatically mean "turn successfully done".
- Pure-text outputs should be normalized into explicit finish reasons such as:
  - awaiting_user_input
  - continue_discussion
  - completed_text
- Step completion and turn completion are different concepts.
- The runtime must guard against pseudo-completion, especially when:
  - a repair obligation remains unresolved
  - commit readiness is blocked
  - the cognitive state is invalidated
  - the current step still has unresolved required information
- Freeze/commit pacing should be user-controlled:
  - the user decides when to attempt freezing the current step
  - agent-initiated review is optional and not required as a formal lifecycle stage
  - the agent may surface readiness hints, missing fields, and blockers
  - user manual commit is always allowed, even if the current step is blank or incomplete
  - runtime readiness checks may produce warnings and unresolved-issue records, but must not block explicit user commit
  - stage progression still requires commit, because the next stage depends on committed summaries/handoff artifacts

#### 6. Context Management Strategy

- Setup should stay setup-local, not memory-first.
- The setup context stack should remain:
  - SetupWorkspace as business truth
  - SetupContextPacket as bounded turn context
  - runtime-private cognitive snapshot/summary
  - retrieval fallback for targeted lookup
- The system should avoid carrying raw old discussion into new stages.
- Stage transitions should prefer:
  - committed truth
  - compacted summaries
  - retrieval-friendly chunk descriptions
  - explicit open issues
- This keeps context cleaner and reduces cross-stage pollution.

#### 7. Stage Handoff Strategy

- Entering a new stage should compact the previous stage into a handoff packet rather than replaying the full discussion transcript.
- For foundation-heavy setup, the next stage should primarily consume:
  - accepted foundation chunks
  - chunk descriptions
  - stage summary / spotlight
  - retrieval hits when needed
- This is a core context-governance design, not a small retrieval optimization.

#### 8. Draft Rules and Structured Truth

- The draft is not just user-facing content. It is the structured truth surface that later stages and retrieval depend on.
- Therefore draft shape must be contract-driven.
- The system should not rely only on the agent being obedient. It should use:
  - pydantic schema
  - validation
  - repair/retry policy
  - commit/readiness guard
- Draft remains user-editable. Manual user edits should be tracked as deltas and should invalidate or reconcile the runtime cognitive state before the agent continues relying on old assumptions.
- The agent may write draft candidates during discussion, but it should not patch after every utterance. It should write after a meaningful partial structure has emerged, unless the user explicitly requests an immediate write.
- For foundation chunks, a tiered schema is preferred:
  - LLM-required fields
  - runtime-owned metadata
  - retrieval enrichment fields
- Not all retrieval metadata should be authored by the model inside the main loop.

#### 9. Retrieval-Friendly Foundation Chunks

- Foundation chunks should be retrieval-friendly by design so later stages can retrieve semantically stable setup truth.
- The recommended split is:
  - model-authored truth fields such as title, description, content, chunk_type, tags, open_issues
  - optional model-authored helper fields such as aliases and questions_answered
  - runtime-owned lineage and filter metadata
  - post-processing enrichment such as entities, keywords, relation edges, retrieval_text
- This reduces model burden while keeping retrieval quality high.

#### 10. Harness Boundary

- The future harness should become stronger, but it should be built on top of a solid loop.
- The right build order is:
  - loop semantics
  - runtime cognition and repair policy
  - context and stage handoff policy
  - tool semantics / stage-aware tool visibility
  - skills and mode-specific prompt resources
  - eval-driven optimization

#### 11. Open Design Pressure

- Confirmed decisions from discussion:
  - pure-text turn endings are allowed because not every setup turn should force a tool mutation
  - however, pure-text ending does not imply step completion; it must resolve into an explicit finish reason
  - setup runtime may auto-repair bounded tool/schema errors with a maximum of three retries, but the quality target remains "avoid even the first error" through prompt/schema/tool/runtime guardrails
  - new stages should avoid inheriting prior-stage raw discussion details and instead use structured truth, compacted summaries, and retrieval-friendly handoff artifacts
  - foundation chunking should start from entity/rule/truth-oriented LLM-guided segmentation rather than naive fixed-length splitting; if one unit is too long, a secondary paragraph/subchunk strategy can be applied underneath the semantic parent
  - review does not need to be a formal agent-initiated lifecycle stage; freezing/commit pacing can be fully user-controlled
  - the agent should provide readiness signals and warnings, not own the pacing decision
  - explicit user commit must be allowed even when content is blank or incomplete
  - draft is user-editable and user edits should be tracked as deltas; those edits invalidate/reconcile setup cognition
  - stage progression must follow the preset setup sequence and must pass through commit; arbitrary stage switching is invalid because the next stage depends on previous-stage summary/handoff data
- Remaining key decisions:
  - exact continue-site taxonomy
  - exact finish-reason taxonomy
  - exact handoff packet schema
  - exact compact/retrieval boundary per stage
  - exact MVP retrieval-enrichment fields for longform-first setup
  - exact warning/unresolved-issue payload emitted on explicit commit when readiness is weak

### Research References

- [`research/harness-engineering-openai-anthropic.md`](research/harness-engineering-openai-anthropic.md) — baseline for OpenAI/Anthropic harness-engineering vocabulary.
- [`research/current-agent-gap-analysis.md`](research/current-agent-gap-analysis.md) — current gap analysis for skills, tools, mode profile, and harness layering.

### Output Artifacts

- [`docs/research/rp-redesign/agent/development-spec/setup-agent-loop-react-lifecycle-development-spec.md`](../../../docs/research/rp-redesign/agent/development-spec/setup-agent-loop-react-lifecycle-development-spec.md) — development spec for the next SetupAgent loop / ReAct / context lifecycle slice.

### Out of Scope (Current Brainstorm)

- Direct implementation.
- Full active story runtime worker redesign.
- Making setup memory-first.
- Splitting every setup stage into completely separate CRUD tool families before the object model proves it is needed.
