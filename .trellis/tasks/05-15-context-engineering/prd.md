# Context Engineering PRD

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Status: planning baseline
>
> User correction: SetupAgent is the proving ground, not the authority or complete form. The task is to build a generally useful Context Engineering module first, guided by professional agent systems such as Claude Code, pi-mono, OpenAI, Anthropic, Google, and other mature AI engineering references, then prove it through SetupAgent and later Story Runtime adapters.

## 1. Problem

The project now has multiple runtime surfaces that need context governance before model calls:

- SetupAgent long setup-stage discussions, draft recovery, tool outcomes, working digest, and compact summaries.
- Story Runtime writer packets that need bounded context without losing branch-visible continuity.
- Writer brainstorm sessions that need explicit user-triggered summarization into editable items.
- Chapter bridge, chapter review, session review, and post-write maintenance paths that need summaries or packet sidecars without becoming memory truth.

The current SetupAgent implementation is valuable because it exposes real pressure points: token budget, recent raw history, compact summary, exact detail recovery, runtime state, trace/reporting, and prompt assembly. However, SetupAgent is not the finished Context Engineering architecture and is not the authority for the common module. Treating the current setup services as "good enough" and merely extracting code from them would freeze setup-specific assumptions into what should be a cross-runtime module.

The design authority for this task is professional context-engineering practice: Claude Code's concrete context construction / compaction / memory / skill isolation design, pi-mono's explicit pre-LLM context boundary ideas, and current technical guidance from OpenAI, Anthropic, Google, and comparable mature AI-agent systems. SetupAgent supplies local pressure tests only. Its current code can be optimized, substantially modified, or deleted when that is the correct way to converge on the common design.

The real problem is to create a general pre-model context governance capability that can be used by multiple modules while preserving each module's business truth and policy boundary.

## 2. Goal

Design and implement a common Context Engineering module that owns reusable mechanics:

- normalized source item contracts;
- operation request/result contracts;
- budget and recent-window policy;
- deterministic trimming and retention;
- source fingerprinting;
- compact / summary prompt invocation;
- structured output validation;
- forbidden-field and source-ref validation;
- deterministic fallback;
- usage, trace, and governance reporting.

SetupAgent will be the first proving ground for this module. The first implementation must show that SetupAgent can use the common module through a setup adapter without letting setup-specific concepts pollute the common kernel.

## 3. Core Positioning

Context Engineering is a pre-model-call capability. It decides what a model sees, in what order, under which budget, with which recovery refs, and with which trace evidence.

It is not a memory writer, not a setup draft writer, not a Story Runtime truth writer, and not a replacement for business-domain services.

Important correction for this task:

```text
SetupAgent is a proving ground.
SetupAgent is not the authority.
SetupAgent is not the complete target architecture.
Existing setup code is evidence of local pressure and failure modes, not the final module boundary.
Existing setup code may be optimized, replaced, or removed if it conflicts with the common Context Engineering design.
```

## 4. Architecture Direction

The target shape is:

```text
common Context Engineering kernel
  -> setup adapter / setup policy
      -> SetupAgent context pipeline
  -> story runtime adapter / packet policy
      -> writer packet / worker packet / brainstorm / chapter bridge consumers
  -> future module adapters
      -> module-specific source selection, schema, and placement policy
```

The common kernel should not import or depend on `SetupWorkspace`, setup draft models, Story Runtime Core State, Memory OS mutation services, or UI contracts.

Runtime adapters own business-specific choices:

- which source items enter an operation;
- what recent raw window must remain;
- which schema validates the output;
- whether a summary is prompt-only, runtime sidecar, or accepted handoff;
- what recovery refs are allowed;
- where the result is placed;
- whether a failed operation falls back, fails closed, or skips the section.

## 5. SetupAgent Proving-Ground Boundary

SetupAgent is still the first integration target because it has the richest current context-governance pressure. In this task, setup should prove the common module can support real workloads, not constrain the module to its current shape:

- stage-local history pressure detection;
- recent raw history retention;
- compact summary fingerprint / reuse / incremental update;
- setup-specific draft-ref recovery through adapter policy;
- deterministic fallback when compact prompt output is invalid;
- trace and context report surfaces;
- no business truth mutation from compact output.

Setup-specific concepts must stay outside the common kernel:

- `SetupWorkspace`;
- setup stages and steps;
- setup draft refs and truth-index refs;
- setup review / commit / readiness;
- setup tool names and runtime allowlists;
- setup SkillPack prompt packaging.

These belong to setup adapter, setup policy, or existing setup services.

The setup adapter is allowed to be a migration layer, not a preservation layer. If a setup service encodes the wrong abstraction, it should be changed or retired rather than protected as legacy authority.

## 6. Story Runtime Future Consumer Boundary

Story Runtime should consume the common module later through its own adapters and policies. It should not build a second generic compact engine.

Future Story Runtime consumers include:

- writer packet older-context compaction;
- writer brainstorm summary;
- chapter bridge summary;
- chapter/session review summary;
- worker packet sidecar compaction if needed.

Story Runtime policy must still enforce:

- branch-aware source scope before compact;
- recent raw turn / accepted prose retention;
- writer packet and worker packet separation;
- no compact summary as Core / Recall / Archival / Runtime Workspace truth;
- user-review lifecycle for brainstorm summaries.

## 7. Non-Goals For The First Coherent Slice

- Do not claim SetupAgent context governance is already complete.
- Do not treat SetupAgent or its current services as the design authority.
- Do not mechanically extract `SetupContextCompactionService` and call that the common module.
- Do not wire Story Runtime consumers in the first slice.
- Do not modify `SetupWorkspace` business truth semantics.
- Do not make compact / summary write Core, Recall, Archival, setup draft, or accepted story truth.
- Do not let setup-specific refs or tool names become common-kernel primitives.
- Do not perform a broad runtime rewrite before the common contract is explicit.

## 8. First Coherent Slice

First slice name:

```text
Common Context Engineering Kernel + Setup Adapter Pilot
```

Expected deliverables:

1. Common contracts for source items, operation request, operation result, budget/window policy, validation report, fallback report, and trace metadata.
2. Common kernel implementation for mechanics that are truly reusable across runtimes.
3. Setup adapter that maps current setup history, digest, retained outcomes, compact summary schema, and draft-ref recovery policy onto the common contracts.
4. Setup path migration that keeps externally required setup product boundaries intact while allowing internal setup context services to be optimized, replaced, or deleted.
5. Focused tests proving common mechanics and setup adapter behavior.

This slice is complete only when the setup path still works and the common module is independently understandable as a cross-runtime capability.

## 9. Required Pre-Reading

- `.trellis/tasks/04-28-runtime-story-dev-task/research/context-engineering-compact-summary-development-handoff.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/context-engineering-compact-summary-module-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md`
- `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md`
- `.trellis/spec/backend/rp-setup-agent-pre-model-context-assembly.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-target-architecture-hld.md`
- `.trellis/tasks/05-11-setup-agent-architecture-improve/research/setup-agent-architecture-completion-handoff.md`

## 10. Acceptance Criteria

- The PRD clearly states that SetupAgent is a proving ground, not the complete form.
- The PRD clearly states that SetupAgent is not the authority and existing setup context code may be optimized, replaced, or removed.
- The common module is defined as the primary target of the task.
- The authority sources are external mature context-engineering implementations and professional AI-agent technical guidance, not the current setup implementation.
- SetupAgent and Story Runtime responsibilities are separated through adapter/policy boundaries.
- The first slice is scoped narrowly enough to implement and check before moving to broader consumers.
- Future implementation must run `trellis-check` after the coherent slice is complete.
