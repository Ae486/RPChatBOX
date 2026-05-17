# Context Engineering Foundation Boundary

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Status: boundary baseline

## 1. Corrected Task Statement

This task is not a cleanup of the current SetupAgent context implementation.

The task is to build a general Context Engineering foundation for RP runtimes and modules. SetupAgent is the first proving ground because it already has real context pressure and a working, if incomplete, implementation surface. SetupAgent is not the authority for the module.

The authority for the common design is mature context-engineering practice: Claude Code's concrete context construction / compaction / memory / skill isolation mechanisms, pi-mono's explicit pre-LLM context boundary, and professional AI company guidance from OpenAI, Anthropic, Google, and comparable agent systems. SetupAgent contributes local workload evidence only.

The target module must be useful beyond SetupAgent:

- SetupAgent stage-local context governance.
- Story Runtime writer packet governance.
- Story Runtime worker packet governance.
- Writer brainstorm summarization.
- Chapter bridge and review sidecars.
- Future module-specific context packets.

## 2. What SetupAgent Proves

SetupAgent gives the common module a concrete proving environment:

- long current-step dialogue;
- raw-window retention pressure;
- compact summary reuse / update / fallback;
- exact detail recovery through refs;
- tool outcome retention;
- runtime state and prompt overlay;
- trace and context report needs.

These are real requirements. They are not proof that the current setup services are the correct final abstraction.

Current setup context services can be optimized, substantially modified, or deleted if they conflict with the common Context Engineering boundary. The proving-ground rule is about validating against a real setup workload, not preserving current setup code.

## 3. What SetupAgent Must Not Export Into The Kernel

The common kernel must not become setup-shaped. The following are setup adapter concerns:

- workspace lookup;
- setup stages and legacy steps;
- setup draft block selection;
- setup-specific refs such as `draft:story_config`;
- `setup.read.draft_refs`;
- `setup.truth_index.search`;
- setup review / commit / readiness;
- setup SkillPack selection;
- setup tool-scope allowlists.

If common contracts need references, they should use generic `source_ref`, `recovery_ref`, or adapter-provided metadata. The kernel should validate refs according to adapter policy, not hard-code setup prefixes.

## 4. Common Kernel Responsibility

The common module should own reusable mechanics:

- normalize context source items;
- apply budget and recent-window policy;
- decide whether an operation is needed;
- compute source fingerprints;
- reuse or incrementally update summaries when possible;
- invoke compact / summary model pass when configured;
- validate structured output through adapter-provided schema rules;
- reject forbidden fields and invalid refs;
- produce deterministic fallback results;
- return trace, usage, and fallback metadata.

## 5. Adapter Responsibility

Each adapter owns runtime semantics:

- source selection;
- schema selection;
- recovery-ref policy;
- section placement;
- summary lifecycle;
- persistence destination;
- failure behavior;
- business truth boundaries.

Setup adapter proves that the common module can serve setup workloads while keeping setup-specific policy outside the kernel. It does not have to preserve the current setup implementation shape. Story Runtime adapter later proves writer/worker/brainstorm/chapter policies.

## 6. First Slice Boundary

First implementation slice should build:

```text
common contracts + common kernel + setup adapter pilot
```

It should not build:

```text
story runtime consumer wiring
full context orchestration service
memory mutation path
setup workspace rewrite
```

The first slice succeeds when the common module is real enough for SetupAgent to use, while remaining clearly reusable by Story Runtime later. If preserving an existing setup service makes the common design weaker, the setup service should change.
