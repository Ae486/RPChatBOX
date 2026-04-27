# Current Agent Gap Analysis

Date: 2026-04-27

## Scope

This note answers:

1. how setup-stage skills should relate to setup tools
2. whether current draft tools are shared or split
3. what "tool semantics layer" means
4. what "turn runtime -> thread/session/harness" means
5. where `mode profile` should live during setup-first, longform-first development

## 1. Setup Skills vs Setup Tools

Recommended split:

- skills carry stage/mode knowledge
- tools mutate or read business objects

For setup, this means:

- `worldbuilding` skill should teach the agent how to guide the user
- `character setup` skill should teach collection heuristics and anti-patterns
- tools should stay focused on draft CRUD, read, question, proposal, and asset registration

Do not move domain knowledge into tool descriptions beyond "when to use / not use / target object / important fields".

## 2. Current Tool Split

Current implementation is **partially shared, partially split by draft family**.

Shared cross-step tools:

- `setup.discussion.update_state`
- `setup.chunk.upsert`
- `setup.truth.write`
- `setup.question.raise`
- `setup.asset.register`
- `setup.proposal.commit`
- `setup.read.workspace`
- `setup.read.step_context`

Draft-family-specific patch tools:

- `setup.patch.story_config`
- `setup.patch.writing_contract`
- `setup.patch.foundation_entry`
- `setup.patch.longform_blueprint`

Important nuance:

- current tools are **not one generic "draft.patch"**
- but they are also **not fully split into one tool-set per micro-stage**

The split is by **business object family**, not by every discussion stage.

That means:

- worldbuilding and character setup currently share the `foundation` object family
- they are expected to differ more through `skills`, `step_context`, and `entry semantics`
- not necessarily through completely separate CRUD tool families

This is a good default.

If later worldbuilding and character setup need very different mutation envelopes, then they can split further.

Do not split too early.

## 3. What Tool Semantics Layer Means

This does **not** mean "more tools".

It means every tool should expose runtime-meaningful metadata such as:

- is it read-only
- does it mutate setup truth or only runtime-private state
- is it destructive
- can it run concurrently
- should it be rate-limited or treated as expensive
- is it idempotent
- what failure classes can occur
- should the runtime retry, ask user, continue discussion, or stop
- which mode/stage/object family it applies to

Current setup tools already have decent business error semantics:

- `repair_strategy`
- `block_commit`
- `ask_user`
- `transient_retry`

But the runtime still lacks a broader tool semantics system similar to top-tier coding agents.

## 4. What "Turn Runtime -> Thread/Session/Harness" Means

Current setup runtime is mainly a **single-turn execution engine**:

- prepare input
- derive goal
- plan step slice
- call model
- execute tools
- assess progress
- finalize

That is good and necessary.

But a fuller harness adds:

- session lifecycle
- durable event log
- turn history as a first-class structure
- resumability after interruption
- branching/forking
- compaction/reset strategy
- richer context budget enforcement
- stable interfaces between "brain", "tool hands", and "session state"

In short:

- current code = agent runtime
- target design = agent runtime inside a larger harness

## 5. Where Mode Profile Should Live

The right answer is **two-layer mode profiling**, not one-layer.

### Setup-time mode profile

Must exist now, because setup already depends on mode for:

- step sequence
- visible skills
- target draft families
- readiness heuristics
- stage-specific anti-patterns

Without this, setup cannot stay controlled once RP/TRPG diverge from longform.

### Runtime-story mode profile

Also exists, but this is where heavier differences belong:

- worker mental models
- memory management strategy
- context orchestration strategy
- retrieval emphasis
- proposal / maintenance behavior

So the correct principle is:

- mode matters in setup
- mode matters even more in active runtime

The mistake would be:

- either pushing all mode logic into runtime-story only
- or overloading setup with the full runtime orchestration problem too early

## 6. Practical Design Recommendation

For longform-first development:

1. keep one universal `setup-core-skill`
2. add one `setup-longform-skill`
3. keep shared cognitive tools
4. keep block-family-specific patch tools
5. keep mode profile in setup, but make it lightweight
6. reserve heavy memory/context orchestration differences for active runtime

This gives the system enough mode awareness now without prematurely exploding the setup surface.
