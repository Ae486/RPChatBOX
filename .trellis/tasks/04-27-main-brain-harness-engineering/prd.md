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
- Compact is stage-local context engineering, not a generic state-management layer. Stage transitions already use handoff packets for large context cuts; compact inside this task should focus on one current setup stage.
- SetupAgent compact should borrow mature framework mechanics where they fit, lighten generic coding-agent features, and customize recovery around RP setup drafts:
  - borrow from Claude Code / CC: pre-model context compression, no-tools compact prompt summarization, analysis stripped from retained summary, and post-compact recovery thinking
  - borrow from `pi-mono`: explicit `transformContext -> convertToLlm` style pre-LLM boundary
  - do not copy CC's full coding-agent five-layer stack, file tracking, prompt-cache editing, or full-session coding summary schema
  - add a stage-local draft recovery tool (`setup.read.draft_refs`) so compact summaries can keep refs/hints instead of storing all draft details

### Open Questions

- What exact stop/continue contract should SetupAgent use when the model produces both user-facing text and tool calls, or when no tool call is produced but the step is still incomplete?
- What exact token thresholds should setup use for pre-call token estimation and observed-usage compact pressure after the first compact implementation lands?
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
- The current compact slice should treat `working_digest` and `compact_summary` as separate surfaces: digest is live control state; compact summary is older current-step context carry-forward with draft refs and recovery hints.
- Compact prompt work should be a no-tools helper pass (`SetupStageCompactPrompt`) with strict JSON output, not a second autonomous agent loop.

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
  - stage-local compact is a context-engineering pipeline: context pressure, raw-window retention, tool-outcome pruning, optional compact prompt summary, draft-ref recovery, runtime overlay, and transient context report
  - `setup.read.draft_refs` is required as a stage-local retrieval tool for recovering exact draft details after compaction
  - compact and digest stay separate: compact preserves older context; digest controls current work
- Remaining key decisions:
  - exact continue-site taxonomy
  - exact finish-reason taxonomy
  - exact handoff packet schema
  - exact production thresholds for pre-call token estimates and observed-usage compact pressure
  - exact MVP retrieval-enrichment fields for longform-first setup
  - exact warning/unresolved-issue payload emitted on explicit commit when readiness is weak

### Authoritative Execution Control (2026-04-28)

- Whole main spec is **not** complete. Slice-local green tests must not be treated as proof that the entire development spec is done.
- The current execution-control baseline is:
  - [`research/setup-agent-main-spec-alignment-checklist.md`](research/setup-agent-main-spec-alignment-checklist.md)
- That alignment note freezes:
  - what is already landed
  - what is only partial
  - what has not started
  - what is in hard conflict
- Retry-budget truth is now resolved:
  - schema / tool-argument auto-repair is frozen at `1` bounded retry
- `Context Transform And Stage Handoff Hardening` previously landed as a completed slice:
  - stronger `SetupStageHandoffPacket`
  - prior-stage open issue carry-forward
  - retrieval refs / source basis carry-forward
  - stricter prompt contract around prior-stage handoff usage
- The current next single slice is:
  - `Stage-Local Compact Context Engineering`
- This slice implements:
  - compact as stage-local context engineering
  - compact prompt pass with deterministic fallback
  - draft-ref recovery through `setup.read.draft_refs`
  - message/token/observed-usage context pressure reporting
- Follow-up slice: `Real-Model Compact Recovery Behavior Eval`.
  - Purpose: verify the behavior condition, not a blanket "compact means readback" rule.
  - Trigger condition under test:
    - the current setup task requires exact draft detail
    - that exact detail is absent from visible raw history, prompt summaries, and compact summary prose
    - visible context provides only a recovery handle such as `foundation:magic-law`
  - Expected behavior:
    - the setup agent calls `setup.read.draft_refs` with the relevant ref before using or writing the missing exact detail
    - the post-readback answer/action uses the tool result, not stale raw discussion or guessed summary text
  - Failure behavior:
    - direct answer without readback when exact detail is required
    - hallucinated or guessed detail
    - test invalidation if the exact detail leaked into first-round prompt-visible context
  - Test strategy:
    - keep the existing deterministic harness test as the engineering-closed-loop proof
    - add a behavior/eval-style test that can run against a real configured setup model when available
    - make the real chain interaction-based rather than seed-only: first turn uses the real model to write the exact detail into draft, then a later compact turn asks for that exact detail when only the draft ref/hint is visible
    - keep model/provider-dependent execution opt-in or gracefully skipped when no real setup model config exists
  - Implementation note:
    - the opt-in test supports env-seeded temporary provider/model config, and also supports a manually selected existing local registry model id for developer-run validation
    - real-model execution exposed one runtime compatibility issue: plain assistant responses may contain `tool_calls=null`; runtime must normalize this to no tool call
    - real-model execution also exercised the existing repair loop: the model initially omitted required fields for `setup.truth.write`, then the runtime repaired and completed the draft write before compact recovery
- Deferred out of this slice:
  - `Foundation Chunk Contract And Retrieval-Friendly Truth Surface`
  - explicit user-commit warning payload
  - skills runtime
  - more outer-harness cleanup

### Slim Truth-Write Structured Output Surface (2026-04-30)

- Added executable spec:
  - `.trellis/spec/backend/rp-setup-agent-strict-truth-write-tool-pilot.md`
- Goal:
  - optimize the model-facing `setup.truth.write` surface before expanding structured-output adapters to other setup tools
  - make the common base path strongly constrained even when a model/provider does not support strict tools
  - remove runtime-owned fields from the model burden where safe
  - keep provider-side `SetupTruthWriteInput` and pydantic validation unchanged as final authority
- Implemented behavior:
  - all model families receive a slim `setup.truth.write` schema when runtime defaults are available
  - GPT/Codex-family model names additionally receive `function.strict = true`
  - model-facing required payload is reduced to `truth_write`
  - model supplies `truth_write.payload_json`; runtime parses it back into provider-side `truth_write.payload`
  - runtime injects `workspace_id`, `step_id`, `truth_write.current_step`, `truth_write.block_type`, and `user_edit_delta_ids` before provider execution
  - model-facing `truth_write.target_ref` is a portable string field; `""` means no target and runtime normalizes it to provider-side `None`
  - if runtime defaults are unavailable, runtime falls back to the existing full provider schema without `strict = true`
- Real-model matrix findings:
  - `gpt-4o-mini`: strict write plus compact readback passed
  - `gpt-5`: strict write plus compact readback passed
  - `gpt-5.4`: selected provider rejected the request with `blocked_invalid_request`, so it is an infra/provider result rather than a model capability pass
  - `glm-5`: request reached the model, but it did not emit a real OpenAI tool call for strict write in the dedicated test; in compact recovery it also failed to call `setup.read.draft_refs`
  - `deepseek-ai/DeepSeek-V3`: request reached the model, but it did not emit a real OpenAI tool call for strict write
  - `gemini-2.5-pro`: selected provider returned 403
  - `gemini-2.5-flash-lite`: selected provider returned an HTML/IP block page
  - Bohe `gemini-2.5-flash`: non-strict slim schema path passed after removing the nullable union from `target_ref`
- Resulting decision:
  - do not default `function.strict = true` to every OpenAI-compatible model
  - keep strict flags gated by observed model-family evidence until the model registry grows explicit strict-tool capability metadata
  - keep the slim model-facing schema as the common base path when runtime defaults can be determined
  - keep Pydantic validation and one bounded repair retry active for all models

### Action Decision Policy / Observe-Act Guard (2026-04-30)

- Added executable spec:
  - `.trellis/spec/backend/rp-setup-agent-action-decision-policy.md`
- Added reference note:
  - `.trellis/tasks/04-27-main-brain-harness-engineering/research/setup-agent-action-decision-reference-notes.md`
- Goal:
  - make the existing SetupAgent loop better at deciding when text is enough and when a tool observation is required first
  - keep the implementation lightweight and project-specific
  - avoid a new durable state-management layer or broad semantic planner
- Source synthesis:
  - Claude Code: explicit continue/stop sites and guard-triggered retry
  - Pi mono: small loop hooks and pre-provider context transform boundary
  - LangGraph: graph remains execution substrate, while setup semantics stay explicit above graph routes
  - OpenAI / Anthropic SDK docs: action guardrails and trace surfaces belong around the agent loop rather than inside business truth
- MVP enforcement:
  - when compacted current-step context only exposes draft refs/recovery hints
  - and the user asks for exact/full/concrete draft detail
  - and no same-turn successful `setup.read.draft_refs` observation exists
  - the runtime blocks text-only finalization and mutation tool batches until `setup.read.draft_refs` runs first
- Explicit exclusions:
  - no generic "similar task" classifier
  - no forced tool call for design/opinion questions
  - no persistent `action_expectation`
  - no replacement for existing repair / reflection / completion policies
- Trellis-check result:
  - fixed readback observation parsing so `setup.read.draft_refs` can clear the expectation when the expected ref is present in either structured payloads or nested JSON `content_text`
  - fixed turn-local expectation recomputation so an explicit empty same-turn `tool_results` list does not fall back to older tool history
  - added regression coverage for nested `content_text` readback and mismatched successful readback
  - verification passed for targeted tests, ruff, scoped mypy, and diff whitespace; full `backend/rp/tests` timed out after 10 minutes and was not used as slice evidence

### Incremental Stage Compact Summary (2026-05-01)

- Current slice:
  - implement compact as a light context-engineering transform, not a new state-management layer
  - first compact summarizes the dropped current-stage prefix from the beginning
  - later compacts update the previous compact summary with only newly dropped messages after the previous summary boundary
  - the recent raw window remains prompt-visible and is not duplicated into compact summary
  - exact token usage from LiteLLM/OpenAI-compatible response `usage` remains an observed signal for the next turn; pre-call estimates remain only a safety heuristic because exact usage arrives after model response
- Sources:
  - user-confirmed requirement: compact should summarize prompt context according to a preset compression instruction and hand the result to context engineering
  - LangChain summarization middleware: trigger plus keep-window policy
  - OpenAI Agents SDK sessions/context: pre-model context trimming/compaction boundaries
  - Pi mono: previous-summary update and `transformContext -> convertToLlm`
  - Claude Code: no-tools compact summarization and recent context retained around summary
- Exclusions:
  - no new memory table
  - no new generic middleware framework
  - no cross-stage handoff redesign
  - no Foundation Chunk Contract implementation in this slice
- Implemented behavior:
  - `SetupContextCompactionService` now detects whether an existing `compact_summary` is an exact dropped-prefix match, a valid earlier prefix, or a mismatch
  - exact dropped-prefix match reports `summary_action="reused_existing"`
  - valid earlier prefix reports `summary_action="updated_existing"` and sends only newly compacted current-step messages to the compact prompt pass
  - mismatch reports `summary_action="rebuilt"` and compacts from the full dropped prefix
  - deterministic incremental fallback merges existing summary fields with the newly compacted message summary while preserving source fingerprint/count for the full dropped prefix
  - compact prompt includes dropped-prefix fingerprint metadata and excludes the recent raw window from incremental prompt input
  - `SetupContextGovernanceReport.summary_action` includes `updated_existing`
- Trellis-check result:
  - fixed scoped mypy issue in `SetupContextGovernorService` previous-usage token metadata handling
  - tightened deterministic summary ordering so first compact and rebuild start from the dropped-prefix beginning
  - added focused tests for first compact start, incremental update, prefix mismatch rebuild, and compact prompt delta boundary
  - verification passed for targeted pytest (`23 passed`), ruff, scoped mypy, and diff whitespace

### Compact Prompt Pass And Toolset Audit (2026-05-02)

- Source alignment:
  - user-confirmed direction: compact is context engineering, should be a direct compression prompt pass, and should not introduce another expert/agent layer
  - Claude Code source borrowing: no-tools compact summarization before model-call assembly, with retained summary fields only
  - Pi mono source borrowing: pre-LLM context transform boundary and previous-summary-plus-delta update style
  - project-specific adaptation: exact draft detail recovery remains `setup.read.draft_refs`, not full-detail storage inside `compact_summary`
- Implemented / aligned behavior:
  - executable specs and task research now use `SetupStageCompactPrompt` / `compact_prompt_summary` instead of `SetupStageCompactExpert` / `expert_stage_summary`
  - `SetupContextGovernanceReport.summary_action` includes `updated_existing`
  - compact prompt pass remains no-tools, JSON-only, capped/validated, and falls back to deterministic summary on model/validation failure
  - fixed `SetupAgentExecutionService` / `SetupContextGovernorService` previous-usage typing so `prompt_tokens`, `completion_tokens`, and `total_tokens` remain `int | None` at the boundary while mypy stays clean
  - fixed the opt-in real-model test fixture so an existing local registry model config still re-seeds provider/model entries after per-test registry service reset; this removes full-file `Model not found` cross-test interference without changing the setup agent runtime path
  - Trellis-check tightened the same fixture so full env-seeded provider/model config takes precedence over an existing local registry model id, and incomplete local registry entries cannot re-seed an empty `api_key` or `model_name`
- Toolset audit result:
  - `setup.read.draft_refs` is already registered in `SetupToolProvider`, included in shared setup tool scope, read-only, bounded by `detail` and `max_chars`, and covered by provider tests
  - stage-aware tool scope already narrows only patch-family tools while keeping shared cognitive/read/commit tools visible
  - no extra tool-semantics layer or repair framework is needed in this slice
- Verification:
  - `python -m pytest backend/rp/tests/test_setup_context_governor.py backend/rp/tests/test_setup_agent_execution_service_v2.py -q` -> `24 passed`
  - `python -m pytest backend/rp/tests/test_setup_tool_provider.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py backend/rp/tests/test_setup_agent_real_model_compact_recovery.py -q` -> `61 passed, 3 skipped`
  - `python -m pytest backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_tool_provider.py -q` -> `11 passed`
  - opt-in real-model end-to-end chain with local `gpt-4o-mini` registry entry:
    - `CHATBOX_RUN_REAL_SETUP_AGENT_COMPACT_EVAL=1 ... python -m pytest backend/rp/tests/test_setup_agent_real_model_compact_recovery.py -q` -> `2 passed, 1 skipped`
    - asserted real-model draft write, compact prompt hiding the exact detail, visible `foundation:magic-law` recovery handle, `setup.read.draft_refs` tool-call before using the missing detail, final answer populated from the tool result, and no exact detail leak into `compact_summary`
  - default no-real-env behavior:
    - `python -m pytest backend/rp/tests/test_setup_agent_real_model_compact_recovery.py -q` -> `3 skipped`
  - scoped `ruff`, scoped `mypy --follow-imports=skip`, and `git diff --check` passed

### Light Agent-Body Hardening (2026-05-02)

- Source alignment:
  - existing SetupAgent loop/ReAct trace spec: no-tool text completion is only one guarded loop branch, not proof of step completion
  - Claude Code / Pi mono / OpenAI Agents SDK borrowing: keep stop/continue and trace decisions explicit, but do not introduce another planner or durable state layer
  - existing structured-output schema repair spec and prior strict truth-write pilot: pydantic validation remains the final correctness source; provider/model strictness is only an enhancement
- Implemented behavior:
  - `inspect_model_output` now passes prior assistant questions and `working_digest` into `CompletionGuardPolicy`, matching the existing `assess_progress` branch
  - repeated user-facing questions can no longer bypass the repeated-question guard on the first text-only model response
  - loop trace coverage now proves the bad path: `inspect_model_output -> reflect_if_needed -> finalize_failure` with `max_rounds_exceeded`
  - high-risk non-`setup.truth.write` tools now have provider-level schema repair spot-checks:
    - `setup.patch.foundation_entry`
    - `setup.patch.longform_blueprint`
    - `setup.question.raise`
    - `setup.asset.register`
    - `setup.proposal.commit`
- Explicit exclusions:
  - no new generic repair framework
  - no new state-management layer
  - no change to user draft edit invalidation / recovery; that remains deferred for the user's follow-up explanation
- Verification:
  - `python -m pytest backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py backend/rp/tests/test_setup_tool_provider.py -q` -> `67 passed, 1 warning`
  - `python -m ruff check backend/rp/agent_runtime/executor.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_tool_provider.py` -> passed
  - `python -m mypy --follow-imports=skip backend/rp/agent_runtime/executor.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_tool_provider.py` -> passed

### Research References

- [`research/harness-engineering-openai-anthropic.md`](research/harness-engineering-openai-anthropic.md) — baseline for OpenAI/Anthropic harness-engineering vocabulary.
- [`research/current-agent-gap-analysis.md`](research/current-agent-gap-analysis.md) — current gap analysis for skills, tools, mode profile, and harness layering.
- [`research/setup-agent-main-spec-alignment-checklist.md`](research/setup-agent-main-spec-alignment-checklist.md) — frozen alignment note for main spec vs executable specs vs current implementation, including hard conflicts and next-slice boundary.
- [`research/setup-agent-stage-local-compact-context-engineering-design.md`](research/setup-agent-stage-local-compact-context-engineering-design.md) — source synthesis for compact as stage-local context engineering, including CC/Pi borrowing, RP lightweight boundaries, compact prompt pass, and draft-ref recovery.
- [`research/setup-agent-action-decision-reference-notes.md`](research/setup-agent-action-decision-reference-notes.md) — source synthesis for the lightweight action decision policy and compact readback observe-act guard.
- [`research/word-style-review-editing-framework-comparison.md`](research/word-style-review-editing-framework-comparison.md) — deep comparison for Word-style revision/comment editing across SuperDoc, CKEditor, Tiptap/ProseMirror/Yjs, AppFlowy Editor, SuperEditor, Quill Delta, and DeepDiff fallback.
  - 2026-05-03 user decision note: WebView-backed editor is acceptable for a future quick prototype if scoped to the specialized review editor; Flutter remains the app shell, and SuperDoc is the preferred reference for tracked changes/comments.
- [`research/setup-stage-module-draft-retrieval-contract.md`](research/setup-stage-module-draft-retrieval-contract.md) — task-level spec for canonical setup stage modules, split draft truth surfaces, structured entry/section grammar, post-commit retrieval materialization, and async diagnostics.
- [`research/setup-stage-module-draft-slice-plan.md`](research/setup-stage-module-draft-slice-plan.md) — executable slice plan for stage module / data-driven draft block implementation, with Slice 1 scoped to backend canonical stage + draft block contract.

### Setup Stage Module / Draft Contract Slice (2026-05-04)

- Added executable backend spec:
  - `.trellis/spec/backend/rp-setup-stage-module-draft-foundation-contract.md`
- Implemented slice:
  - Slice 1: backend canonical stage + draft block contract
- Source alignment:
  - user-confirmed requirement: setup lifecycle follows user-facing stages and `foundation` must not mix worldbuilding with character design
  - existing frontend evidence: wizard stages are already world/character/plot/writer/worker/overview/activate
  - existing backend evidence: setup already has JSON draft blocks and accepted commit snapshots, so the first clean slice generalizes that pattern rather than adding a new durable state layer
- Slice 1 behavior:
  - add `SetupStageId`, stage module catalog, longform mode stage plan, `SetupStageDraftBlock`, `SetupDraftEntry`, and `SetupDraftSection`
  - add `current_stage`, `stage_plan`, `stage_states`, and data-driven `draft_blocks` to `SetupWorkspace`
  - keep legacy fixed draft fields as compatibility mirrors
  - add `patch_stage_draft` and `propose_stage_commit`, with stage-in-plan and stored payload/stage mismatch validation at propose and accept boundaries
  - accepting `world_background` freezes that stage and advances canonical `current_stage` to `character_design` while keeping old `current_step=foundation` as a compatibility mirror
  - setup retrieval ingestion can now read canonical stage snapshots such as `snapshot_payload_json["world_background"]`, render entry sections into seed text, and preserve `semantic_path` as retrieval `domain_path`
  - add focused tests proving `world_background` and `character_design` are separate stage/draft units, invalid/mismatched stage payloads are rejected, and stage payload ingestion does not depend on old `foundation` snapshots
- Verification:
  - `python -m pytest backend/rp/tests/test_setup_stage_module_draft_contract.py backend/rp/tests/test_minimal_retrieval_ingestion_service.py backend/rp/tests/test_setup_tool_provider.py backend/tests/test_rp_setup_api.py -q` -> `30 passed, 14 warnings`
  - scoped `ruff` passed
  - scoped `mypy --follow-imports=skip` passed
  - scoped `git diff --check` passed with only Git CRLF warnings
- Deferred:
  - setup tool/context/handoff migration
  - Setup Truth Index
  - retrieval seed materialization from entry/section tree
  - frontend data-driven rendering

### Setup Stage-Aware Context / Handoff / Draft-Ref Read Slice (2026-05-04)

- Implemented slice:
  - Slice 2A: stage-aware context, handoff, draft-ref reads, and tool-scope mapping
- Source alignment:
  - user-confirmed 1A boundary: migrate read/context behavior first, keep model-facing write tools on the existing legacy compatibility path
  - existing Slice 1 code: `SetupWorkspace.current_stage`, `stage_plan`, `stage_states`, and `draft_blocks` are now the canonical lifecycle/draft sources
  - existing SetupAgent context specs: prior-stage truth must come from accepted commits, and compact detail recovery should use `setup.read.draft_refs`
- Slice 2A behavior:
  - `SetupContextPacket` now carries `current_stage` while preserving `current_step`
  - stage-aware context prefers `draft_blocks[current_stage]` for the current draft snapshot
  - prior-stage handoffs for canonical stages are assembled from accepted canonical stage commits in `workspace.stage_plan` order
  - handoff packets keep legacy `from_step` / `to_step` / `step_id` compatibility fields and add canonical `from_stage` / `to_stage` / `stage_id`
  - canonical stage snapshots generate retrieval-friendly chunk refs such as `stage:world_background:race_elf` and `stage:world_background:race_elf:summary`
  - `setup.read.draft_refs` now supports `draft:<stage_id>`, `stage:<stage_id>:<entry_id>`, and `stage:<stage_id>:<entry_id>:<section_id>` while preserving old refs
  - runtime-v2 context metadata now exposes `current_stage`, `stage_state`, `stage_readiness`, and `prior_stage_handoff_stages`
  - stage-aware tool scope maps canonical stages to the existing legacy patch-family tools; no new write tool was introduced
- Verification:
  - `python -m pytest backend/rp/tests/test_setup_stage_module_draft_contract.py backend/rp/tests/test_setup_agent_runtime_state_service.py backend/rp/tests/test_setup_tool_provider.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_execution_service_v2.py -q` -> `52 passed, 1 warning`
  - scoped `ruff check` passed
  - scoped `ruff format --check` passed
  - scoped `mypy --follow-imports=skip --check-untyped-defs` passed
  - `git diff --check` exited 0 with only Git LF/CRLF warnings
- Deferred:
  - Slice 2B stage-native write tool migration (`setup.truth.write` / legacy patch tools)
  - Setup Truth Index
  - retrieval seed materialization from entry/section tree
  - frontend data-driven rendering

### Output Artifacts

- [`docs/research/rp-redesign/agent/development-spec/setup-agent-loop-react-lifecycle-development-spec.md`](../../../docs/research/rp-redesign/agent/development-spec/setup-agent-loop-react-lifecycle-development-spec.md) — development spec for the next SetupAgent loop / ReAct / context lifecycle slice.

### Out of Scope (Current Brainstorm)

- Direct implementation.
- Full active story runtime worker redesign.
- Making setup memory-first.
- Splitting every setup stage into completely separate CRUD tool families before the object model proves it is needed.
