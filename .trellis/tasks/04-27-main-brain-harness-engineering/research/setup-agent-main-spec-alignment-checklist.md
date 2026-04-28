# SetupAgent Main Spec Alignment Checklist

Date: 2026-04-28

## 1. Purpose

This note freezes the current alignment between:

1. the main development spec
2. the executable Trellis backend specs
3. the current backend implementation

Its job is to prevent a repeated failure mode:

- a few setup-agent slices are implemented and tested
- those slice-local greens are then mistaken for "the whole main spec is done"

This file is the current execution-control baseline for the next SetupAgent turn-loop/context work.

## 2. Source Precedence

Authority order for future work on this task:

1. **Main development spec**
   - Product direction, scope, slice order, and acceptance goals.
   - Primary source:
     - `docs/research/rp-redesign/agent/development-spec/setup-agent-loop-react-lifecycle-development-spec.md`
2. **Executable Trellis specs**
   - Concrete slice contracts and testable boundaries.
   - Primary source:
     - `.trellis/spec/backend/rp-setup-agent-*.md`
3. **Current implementation**
   - Proves what exists today, not what the target truth should be.
   - Primary source:
     - `backend/rp/agent_runtime/*`
     - `backend/rp/services/*`
     - `backend/rp/models/*`
4. **Workflow rule**
   - If 1 and 2 conflict, stop coding and resolve the conflict before the next implementation slice.
   - Source:
     - Trellis workflow rule: Execute can roll back to Plan when a PRD/spec defect is exposed

## 3. Status Matrix

| Main-spec area | Primary source | Current executable / code evidence | Status | Current reading |
|---|---|---|---|---|
| Slice 1: loop taxonomy and ReAct trace | Main spec slice 1; Claude Code / pi-mono loop borrowing | `.trellis/spec/backend/rp-setup-agent-loop-semantics-react-trace.md`; `backend/rp/agent_runtime/contracts.py`; `backend/rp/agent_runtime/executor.py`; `backend/rp/agent_runtime/state.py` | Mostly landed | `continue_reason`, `finish_reason`, `loop_trace`, and `SetupReActTraceFrame` exist. This is real progress, but it does not prove later slices are complete. |
| Slice 2: repair policy hardening | Main spec slice 2; observed setup bad path for missing fields | `.trellis/spec/backend/rp-setup-agent-structured-output-schema-repair.md`; `backend/rp/agent_runtime/policies.py`; `backend/rp/agent_runtime/executor.py` | Resolved | The task now freezes schema / tool-argument auto-repair at exactly one bounded retry, matching executable spec and code. |
| Stage-local context governance | Main spec section 9; Claude Code context-governance ideas | `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md`; `backend/rp/services/setup_context_governor.py`; `backend/rp/services/setup_context_compaction_service.py`; `backend/rp/services/setup_agent_runtime_state_service.py` | Partial | `working_digest`, `tool_outcomes`, and `compact_summary` are already separated. Historical tool-call process is not retained in prompt context, only final outcomes. Remaining gap is that compact still behaves like an internal helper rather than a first-class decision surface with explicit trigger reasons, summary action, and non-persistent observability. |
| Pre-model context assembly | Main spec section 9; pi-mono `transformContext -> convertToLlm` boundary | `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md`; `backend/rp/services/setup_context_builder.py`; `backend/rp/agent_runtime/adapters.py`; `backend/rp/services/setup_agent_execution_service.py` | Partial | One deterministic path exists from context packet to governed history to runtime overlay to final request messages. Remaining gap is that the runtime still lacks an explicit context-decision surface explaining why this turn stayed full vs compact, whether summary was reused vs rebuilt, and what raw-history/tool-retention budget decisions were made. |
| Slice 3: prior-stage handoff / no raw previous discussion in new stage | Main spec slice 3; user requirement on stage context hygiene | `.trellis/spec/backend/rp-setup-agent-prior-stage-handoff-context.md`; `backend/rp/models/setup_handoff.py`; `backend/rp/services/setup_context_builder.py`; `backend/rp/services/setup_agent_prompt_service.py` | Mostly landed | Prior-stage context still comes only from accepted commits, raw previous discussion is still excluded, and the handoff packet now carries stage-scoped summary tiers, open issues, retrieval refs, warnings, and source basis. Remaining gap is the later foundation-chunk contract, not the basic handoff packet. |
| User-edit invalidation / reconcile | Main spec section 10 | `backend/rp/services/setup_agent_runtime_state_service.py`; `backend/rp/agent_runtime/executor.py`; `backend/rp/tests/test_setup_agent_runtime_state_service.py` | Mostly landed | User edit deltas can invalidate setup cognition and route the loop through `reconcile_after_user_edit`. |
| Slice 4: foundation chunk contract | Main spec slice 4; retrieval-friendly truth-unit chunking | `backend/rp/models/setup_drafts.py` | Deferred | Current `FoundationEntry` is still the older `entry_id/domain/path/title/tags/source_refs/content` shape. The tiered chunk contract from the main spec is not implemented, but this is intentionally deferred because the current phase is focused on agent-body capabilities rather than retrieval/truth-surface redesign. |
| Slice 5: explicit user commit always allowed + warning payload | Main spec slice 5; user commit authority requirement | Current flow centered on `setup.proposal.commit`, `SetupRuntimeController`, and `SetupWorkspaceService` | Not landed | There is no `CommitWarningPayload` contract yet. Runtime still contains `block_commit` / `reassess_commit_readiness` semantics around commit proposal. |
| Slice 5: preset stage progression through commit + handoff | Main spec slice 5; setup lifecycle requirement | `backend/rp/services/setup_workspace_service.py` (`_STEP_ORDER`, `accept_commit`, `_advance_current_step`) | Partial | Preset progression already exists as a workflow skeleton, but it is not yet fused with the new warning-payload and handoff-packet contract. |
| Stage-aware tool visibility | Main spec section 13; mature tool-governance practice | `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md`; `backend/rp/agent_runtime/profiles.py`; `backend/rp/agent_runtime/adapters.py` | Landed (minimal) | Shared setup tools plus current-step patch-family narrowing is in place. |
| Runtime-v2 only convergence | Main spec priority item 9; cleanup of transitional runtime split | `.trellis/spec/backend/rp-setup-agent-runtime-v2-only-convergence.md`; `backend/rp/services/setup_agent_execution_service.py`; `backend/rp/runtime/rp_runtime_factory.py` | Mostly landed | The legacy main-path split is removed, but this is outer-harness cleanup, not proof that the core main spec is done. |
| Graph shell thin boundary | Main spec priority item 9; harness boundary cleanup | `.trellis/spec/backend/rp-setup-graph-shell-thin-checkpoint-contract.md`; `backend/rp/graphs/setup_graph_runner.py`; `backend/rp/graphs/setup_graph_nodes.py` | Mostly landed | Shell-vs-runtime context duplication was thinned. This is valid work, but not the highest-leverage remaining gap. |
| Execution-service thin public boundary | Main spec priority item 9; service entrypoint cleanup | `.trellis/spec/backend/rp-setup-agent-execution-service-outer-harness-thin-boundary.md`; `backend/rp/services/setup_agent_execution_service.py` | Mostly landed | `run_turn` and `run_turn_stream` now share one outer launch boundary. This should be treated as a completed cleanup slice, not as the whole task. |

## 4. Hard Conflicts And Gaps

These items must be treated as live execution-control issues, not as optional cleanup.

### 4.1 Retry Budget Truth Is Resolved

- User decision: `1A`
- Frozen truth:
  - schema / tool-argument auto-repair uses exactly one bounded retry
- Source alignment:
  - main development spec must match the executable spec and current code
  - `RepairDecisionPolicy.assess(...)` remains the current runtime anchor

### 4.2 Continue / Finish Taxonomy Needs One Truth Table

- Main spec currently presents a higher-level conceptual continue taxonomy.
- Executable loop spec has already frozen the runtime-local taxonomy used by code and tests.

This is not necessarily a bug, but it is dual truth.

Required follow-up:

- either update the main spec taxonomy to match executable runtime semantics
- or add an explicit mapping table between conceptual reasons and runtime reasons

### 4.3 Commit Authority Contract Is Still Behind The Main Spec

Main spec requires:

- explicit user commit is always allowed
- weak readiness only yields warnings / unresolved issue payload
- stage progression still happens through commit + handoff

Current implementation still centers on:

- commit proposal
- readiness reflection
- `block_commit` / `reassess_commit_readiness` semantics

This is not yet the main-spec commit contract.

### 4.4 Handoff Packet Authority Is Now Good Enough For The Next Slice

The current handoff packet now carries the minimum authority surface needed for setup-stage context hardening:

- `workspace_id`
- `from_step`
- `to_step`
- active `summary`
- `summary_tier_0`
- `summary_tier_1`
- `committed_refs`
- `spotlights`
- `chunk_descriptions`
- `open_issues`
- `retrieval_refs`
- `warnings`
- `source_basis`

That means the remaining high-value gap has moved down one layer:

- the underlying foundation truth-unit / chunk contract is still the old draft shape
- handoff transport is no longer the main blocker

## 5. Recommended Next Slice

### 5.1 Name

**Stage-Local Compact And Context Decision Surface**

### 5.2 Why This Slice Goes Next

Source of this recommendation:

- User priority: current phase only improves agent-body capabilities such as loop, context engineering, and ReAct; do not expand into truth-surface redesign
- Mature reference borrowing:
  - Claude Code: compact is a first-class session operation with explicit trigger, keep-window, and post-compact summary handling
  - pi-mono: `transformContext -> convertToLlm` is an explicit pre-LLM boundary, and compaction belongs in that boundary rather than hidden inside business truth
  - LangChain/LangGraph: trim/summarize behavior is modeled as middleware/checkpoint-aware context management rather than a new durable state system
  - Claude Agent SDK: long-lived session control, allowed-tool narrowing, and checkpoint/hook surfaces show that observability and runtime control should stay separate from durable product truth

Why before other open gaps:

- stage handoff transport is already good enough for the current phase
- the most important remaining agent-body gap is stage-local compact behavior and context-decision transparency
- this slice improves the highest-frequency path of the agent without widening product truth or retrieval contracts

### 5.3 In Scope

- Keep `working_digest` and `compact_summary` separate and formalize compact as a first-class stage-local context operation rather than a hidden helper.
- Add a non-persistent context-decision surface that explains:
  - why the turn used `standard` vs `compact`
  - how much raw history was kept vs compacted
  - whether the summary was reused vs rebuilt
  - how many retained tool outcomes and prior-stage handoffs participated in the turn
- Keep the current deterministic compact path, but make its strategy/action explicit so later expert-compact work can plug in without rewriting the boundary.
- Keep historical tool information limited to retained final outcomes; never promote retry/process trace back into prompt history.
- Align:
  - setup compaction/governor service contracts
  - runtime-v2 turn-input assembly
  - runtime result / debug / eval surfaces
  - persistence boundary tests proving the new context-decision surface stays transient

### 5.4 Out Of Scope

- Foundation chunk contract / retrieval-friendly truth surface
- Explicit user-commit warning payload
- Skills runtime / lazy skill resource loader beyond a narrow placeholder boundary
- Additional outer-harness cleanup beyond the already landed thin-boundary work
- Full setup commit-authority redesign

## 6. Pre-Coding Gate

Before the next implementation slice starts:

1. Use this alignment note as the task's execution-control baseline.
2. Treat one bounded schema/tool-argument auto-repair retry as the frozen truth.
3. Keep implementation scope limited to one coherent slice.
4. Run `trellis-check` immediately after that slice is implemented.

Until then, "some setup-agent tests are green" must not be used as shorthand for "the whole main spec is done."
