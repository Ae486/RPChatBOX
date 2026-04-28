# Research: SetupAgent stage-local compact context engineering

- Query: Research and design a lightweight stage-local compact/context-engineering approach for RP SetupAgent, with compact treated as context engineering rather than generic state management.
- Scope: mixed
- Date: 2026-04-28

## Findings

### Sources

Local mature-agent references:

- `docs/research/how-claude-code-works-main/docs/02-agent-loop.md` - Claude Code loop places compression before every API request; the pipeline is Tool Result Budget -> Snip -> Microcompact -> Context Collapse -> Autocompact (`docs/research/how-claude-code-works-main/docs/02-agent-loop.md:197`, `docs/research/how-claude-code-works-main/docs/02-agent-loop.md:218`).
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md` - Context engineering is progressive and cost-aware: local trimming first, projection before irreversible summary, full autocompact last (`docs/research/how-claude-code-works-main/docs/03-context-engineering.md:298`, `docs/research/how-claude-code-works-main/docs/03-context-engineering.md:321`).
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md` - Compact prompt design uses a no-tools summarizer role, lets the model produce analysis plus summary, then strips analysis and keeps only summary (`docs/research/how-claude-code-works-main/docs/03-context-engineering.md:471`, `docs/research/how-claude-code-works-main/docs/03-context-engineering.md:476`, `docs/research/how-claude-code-works-main/docs/03-context-engineering.md:497`).
- `docs/research/how-claude-code-works-main/docs/13-minimal-components.md` - Minimal agent compaction can simply summarize prior history and replace it with a "previous conversation summary" message, with enough reserve for the summary call (`docs/research/how-claude-code-works-main/docs/13-minimal-components.md:455`, `docs/research/how-claude-code-works-main/docs/13-minimal-components.md:467`, `docs/research/how-claude-code-works-main/docs/13-minimal-components.md:475`).
- `docs/research/pi-mono-main/packages/agent/src/agent-loop.ts` - Pi's minimal loop has an explicit pre-LLM boundary: optional `transformContext` first, then `convertToLlm` (`docs/research/pi-mono-main/packages/agent/src/agent-loop.ts:247`, `docs/research/pi-mono-main/packages/agent/src/agent-loop.ts:254`).
- `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts` - Pi compaction prompt is structured around goal, constraints, progress, decisions, next steps, and critical context, with update mode preserving previous summary (`docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts:454`, `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts:487`).

Current SetupAgent implementation and specs:

- `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md` - Current contract separates `working_digest`, `compact_summary`, transient `context_report`, and retained final `tool_outcomes`; it forbids treating compact as durable product truth (`.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md:90`, `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md:92`, `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md:93`).
- `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md` - Current context stack is four layers: `SetupContextPacket`, governed history, runtime adapter bundle, then runtime request messages; each layer has one job (`.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md:81`, `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md:111`).
- `.trellis/spec/backend/rp-setup-agent-prior-stage-handoff-context.md` - Prior-stage context must come only from accepted compact handoff packets, not raw earlier-stage discussion (`.trellis/spec/backend/rp-setup-agent-prior-stage-handoff-context.md:64`, `.trellis/spec/backend/rp-setup-agent-prior-stage-handoff-context.md:110`).
- `backend/rp/services/setup_context_compaction_service.py` - Current compaction is deterministic and thin: keep 6 or 4 recent raw messages, summarize dropped prefix, fingerprint dropped history, reuse existing summary when matching (`backend/rp/services/setup_context_compaction_service.py:19`, `backend/rp/services/setup_context_compaction_service.py:47`, `backend/rp/services/setup_context_compaction_service.py:55`).
- `backend/rp/services/setup_context_governor.py` - Current governor owns raw-history retention, compact summary creation, metadata counts, digest creation, and bounded tool-outcome retention (`backend/rp/services/setup_context_governor.py:32`, `backend/rp/services/setup_context_governor.py:53`, `backend/rp/services/setup_context_governor.py:140`).
- `backend/rp/services/setup_agent_execution_service.py` - Current turn assembly already chooses a token budget, builds `SetupContextPacket`, reconciles cognition, builds digest, governs history, builds `context_report`, and passes all pieces into the runtime adapter (`backend/rp/services/setup_agent_execution_service.py:157`, `backend/rp/services/setup_agent_execution_service.py:419`, `backend/rp/services/setup_agent_execution_service.py:477`, `backend/rp/services/setup_agent_execution_service.py:486`).
- `backend/rp/agent_runtime/contracts.py` - Current contracts already define the needed shape: `SetupWorkingDigest`, `SetupToolOutcome`, `SetupContextCompactSummary`, and `SetupContextGovernanceReport` (`backend/rp/agent_runtime/contracts.py:166`, `backend/rp/agent_runtime/contracts.py:180`, `backend/rp/agent_runtime/contracts.py:203`, `backend/rp/agent_runtime/contracts.py:215`).
- `backend/rp/agent_runtime/executor.py` - Runtime overlay tells the model to treat digest as control state, tool outcomes as outcomes without old process, and compact summary as carry-forward context for trimmed current-step discussion (`backend/rp/agent_runtime/executor.py:1286`, `backend/rp/agent_runtime/executor.py:1295`, `backend/rp/agent_runtime/executor.py:1297`).
- `backend/rp/services/setup_agent_prompt_service.py` - Stable prompt reinforces the same boundary and forbids reconstructing prior-stage raw discussion (`backend/rp/services/setup_agent_prompt_service.py:35`, `backend/rp/services/setup_agent_prompt_service.py:63`, `backend/rp/services/setup_agent_prompt_service.py:75`).
- `backend/rp/agent_runtime/profiles.py` - Current tool boundary is already stage-aware for patch tools while retaining shared setup and read-only memory tools (`backend/rp/agent_runtime/profiles.py:15`, `backend/rp/agent_runtime/profiles.py:26`, `backend/rp/agent_runtime/profiles.py:44`).
- `backend/rp/models/setup_handoff.py` and `backend/rp/services/setup_context_builder.py` - Draft/handoff context is already modeled as current draft snapshot, user edit deltas, and compact prior-stage handoffs (`backend/rp/models/setup_handoff.py:82`, `backend/rp/models/setup_handoff.py:91`, `backend/rp/models/setup_handoff.py:96`, `backend/rp/services/setup_context_builder.py:77`).

Related task artifact:

- `.trellis/tasks/04-27-main-brain-harness-engineering/research/setup-agent-stage-local-compact-reference-notes.md` - Existing reference note already narrows this slice to stage-local compact, pre-model transform, retained tool-result policy, transient-state boundary, and lightweight observability.

### What to borrow

- Borrow Claude Code's ordering principle: compact belongs immediately before model-call assembly, not inside generic memory/state mutation. For RP, this maps to `SetupContextPacket -> govern_history -> runtime overlay -> final request messages`.
- Borrow progressive cost tiers, but compress them into RP's simpler needs: first drop/retain by deterministic caps, then retain final tool outcomes, then summarize only dropped current-step prefix, and only later consider LLM expert compact.
- Borrow the "no tools compact expert" idea. A compact pass must be text/JSON-only and unable to mutate `SetupWorkspace`, call setup tools, or run retrieval.
- Borrow Pi's explicit pre-LLM transform boundary: RP should continue treating context engineering as a transform over turn inputs before provider messages are built.
- Borrow structured update summaries from Pi for any future expert compact: keep previous compact summary, update it with only newly dropped messages, preserve decisions, constraints, exact refs, blockers, and next focus.
- Borrow Claude Code's separation between internal analysis and retained summary: an expert compact prompt may ask for analysis internally, but only validated summary fields should enter `compact_summary`.

### What not to borrow

- Do not copy Claude Code's full five-level compression stack. RP SetupAgent does not need disk-spilled tool results, prompt-cache editing, generic context collapse, or full-session autocompact.
- Do not copy generic session-memory compaction. RP setup compact is stage-local and current-step-local; prior-stage truth comes from accepted handoff packets.
- Do not turn `context_report` into prompt content or durable cognition. It should remain debug/eval/result observability.
- Do not add another durable setup-memory table. The existing `SetupAgentRuntimeStateRecord.snapshot_json` boundary is enough for digest/tool outcomes/compact summary.
- Do not preserve raw tool retry chains. Keep final outcomes, updated refs, error code, relevance, and short summary only.
- Do not use an expert compact model for MVP if deterministic prefix summary is enough. A helper model is useful for quality, but it adds failure mode, cost, latency, and validation needs.

### RP-specific lightweight design

Recommended position: keep current architecture and formalize compact as a named context-engineering decision surface.

Runtime flow:

1. `SetupAgentExecutionService._context_token_budget(...)` selects one profile (`standard` or `compact`) from raw history size and user-edit pressure.
2. `SetupContextBuilder.build(...)` creates truth context only: current draft snapshot, selected user edit deltas, assets, and accepted prior-stage handoffs.
3. `SetupContextGovernorService.govern_history(...)` trims current-step raw discussion to the profile cap and either reuses or rebuilds `SetupContextCompactSummary`.
4. Runtime overlay injects turn-local control facts: goal, plan, obligations, latest failure, cognitive summary, `working_digest`, retained `tool_outcomes`, and `compact_summary`.
5. `context_report` records the decision: profile reasons, kept/compacted counts, summary strategy/action, retained tool-outcome count. It goes to result/debug/eval only.
6. `persist_turn_governance(...)` persists only the stage-local durable pieces already allowed: digest, retained final tool outcomes, and compact summary. It does not persist `context_report` or final request messages.

Boundary rules:

- `working_digest`: live current-step control state.
- `compact_summary`: compressed carry-forward view of older current-step raw discussion removed from prompt-visible history.
- `prior_stage_handoffs`: accepted truth from earlier steps only.
- `tool_outcomes`: final cross-turn outcomes only, never retry process.
- `current_draft_snapshot` and `user_edit_deltas`: draft/edit truth inputs, not compact history.
- `context_report`: transient explanation, not prompt and not product truth.

MVP policy:

- Keep deterministic compact summary as default.
- Add explicit `compact_mode` / `summary_action` observability only if current `context_report` needs clearer downstream naming.
- Add expert compact behind a strategy flag only when eval shows deterministic summaries lose important current-step context.
- If expert compact is added, it should update only `SetupContextCompactSummary` fields or a strict extension of that model; it should not write draft, cognition, handoff, or Memory OS state.

### Compact expert prompt-role recommendations

Role name: `SetupStageCompactExpert`.

Prompt constraints:

- Text/JSON only; no tools, no draft writes, no commit proposals, no memory writes, no retrieval.
- Scope is one current setup stage only. Earlier stages must be represented only by `prior_stage_handoffs`, never by raw logs.
- Input sections should be explicit: dropped current-step messages, previous compact summary, working digest, retained tool outcomes, current draft refs, user edit deltas summary, current step id.
- Output should be strict structured JSON matching either `SetupContextCompactSummary` or a small v2:
  - `summary_lines`
  - `open_threads`
  - `draft_refs`
  - optional `discarded_directions`
  - optional `pending_decisions`
  - optional `must_not_infer`
- Preserve exact refs and user-stated constraints. Do not invent missing facts.
- Prefer conclusions over process. Mention tool outcomes only as final effects or unresolved failures.
- If previous summary exists, update it rather than regenerating from scratch; remove stale items only when directly contradicted by newer dropped messages.
- Allow private analysis inside the helper call, but strip it before persistence and prompt injection. Only validated summary fields survive.

Example role contract:

```text
You are SetupStageCompactExpert. Produce a compact carry-forward summary for older current-step setup discussion. Do not call tools. Do not write drafts. Do not decide readiness or commit. Preserve only facts, decisions, open threads, draft refs, and unresolved blockers needed for the next SetupAgent turn in this same stage. Output JSON only.
```

### Open decisions

- Whether deterministic prefix summary is sufficient for the next implementation slice, or whether a helper-model compact strategy should be introduced now behind a flag.
- Whether `SetupContextCompactSummary` needs v2 fields (`discarded_directions`, `pending_decisions`, `must_not_infer`) or whether these should stay in `working_digest`.
- Whether context budget should remain threshold-based (`history_count`, chars, user-edit count) or add actual token estimation later.
- Whether `context_report` needs a stable public debug/eval schema beyond the current contract fields.
- Whether expert compact should run synchronously in the setup turn or asynchronously after turn completion and be reused next turn.
- How eval should measure compact quality: missing open issues, stale draft refs, hallucinated facts, repeated user questions, or wrong commit readiness.

## Caveats / Not Found

- No web browsing was used. All references are local docs/code in `H:/chatboxapp`.
- Dedicated Codex compact/context-engineering design docs were not found locally. Local Codex hits were mostly RP cooperation notes, relay/provider code, or tests; Pi's minimal agent code was the useful local "minimal agent" reference.
- The current implementation already contains most of this design surface. This artifact is a design consolidation, not evidence that a new code layer is required.
- This research did not run tests because no code was changed.
