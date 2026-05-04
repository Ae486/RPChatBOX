# Story Runtime Memory Block / Domain Preliminary Design

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: provide a first-pass block/domain design for ModeProfile `memory_profile`, worker ownership, and user-visible Memory OS UI.
>
> Last updated: 2026-05-04

## Confirmed Inputs

- All Memory OS layers should be visible to the user.
- `Core State` can be directly edited by the user. User edits have highest priority and must invalidate or supersede stale worker candidates.
- `Recall Memory` mainly preserves already-established facts, accepted prose, transcripts, and historical summaries. It is mostly for review, invalidation, and recomputation rather than routine manual editing.
- `Archival Knowledge` can be modified, but edits must go through Story Evolution / ingestion / reindex because archival content participates in retrieval.
- TRPG `rule_state` / `mechanics_state` can be an independent domain.
- `knowledge_boundary` is an independent domain. It is enabled by default for roleplay / TRPG, optional by default for longform, and can initially be maintained by the `CharacterMemoryWorker` execution unit as long as outputs remain separated by domain / block.

## Design Principle

Use `domain` as the ownership and conflict boundary:

- one domain should have one primary block-owner worker;
- cross-domain effects should be expressed as refs or separate proposals;
- domains should be broad enough to avoid tiny worker explosion, but narrow enough that two workers do not routinely write the same truth object;
- ModeProfile should decide default display / activation / hidden-but-available state per domain, while worker configuration stage decides worker enablement, model/provider, and per-domain permission level.

Worker ownership is defined by `domain`, not by `block`.

`block` is a concrete container for a domain inside one Memory OS layer. For example, the `character` domain can have an authoritative Core State block, a projection block, Recall history blocks, Archival source blocks, and Runtime Workspace candidate blocks. These blocks should not create separate workers by default. The same domain owner worker is responsible for understanding the domain across layers, with layer-specific permissions controlling what it may read, propose, refresh, or mutate.

This means:

- `domain` decides worker responsibility and conflict ownership;
- `block` decides storage / display / editing surface inside a memory layer;
- permission level decides what a worker can do to each block or layer under its domain.

## Current Refinement Under Discussion: Domain Owner vs Worker Execution Unit

The phrase "worker ownership is defined by `domain`" should not be read as "one worker process / one LLM call can only ever handle one domain".

Current recommended split:

- `domain owner`: the responsibility record. Each domain must have exactly one clear primary owner, so conflict resolution and permission checks have a stable target.
- `worker execution unit`: the callable worker implementation. One execution worker may bind multiple strongly related domains when this avoids tiny-worker explosion and the domains usually need to be reasoned about together.

In plain terms: the project can still say "ownership is by domain", while allowing a `CharacterMemoryWorker` execution unit to maintain `character` plus closely related domains such as `knowledge_boundary` or `relation`, if the worker contract lists those owned domains explicitly and emits per-domain / per-block results.

This is still pending user confirmation. If the design instead requires strict one-worker-one-domain, then `knowledge_boundary` should become both an independent domain and an independent worker.

## Letta Reference

Local Letta source under `docs/research/letta-main` supports the idea that one memory-managing actor can handle multiple blocks:

- `letta/orm/block.py`: a `Block` is a section of LLM context with `label`, `description`, `value`, `limit`, `read_only`, `hidden`, `version`, and history pointer fields.
- `letta/orm/blocks_agents.py`: an agent must have one or many blocks to make up core memory, and the same agent has unique block labels.
- `letta/schemas/memory.py`: `Memory.compile()` renders multiple blocks into the agent prompt / memory view.
- `letta/services/tool_executor/core_tool_executor.py`: memory tools edit blocks by label or path and then rebuild / refresh the agent prompt.
- `letta/services/block_manager_git.py`: git-enabled memory writes to git first and syncs PostgreSQL as cache.

Useful lesson for story runtime:

- Letta proves "one memory actor, many blocks" is feasible.
- Letta does not prove "one story worker should own unlimited domains"; its block labels are context sections, while this project's `domain` is also a story-truth responsibility and conflict boundary.
- For this project, a worker may process multiple blocks only through an explicit context packet, permission checks, and structured per-domain / per-block output. It must not receive all blocks by default or emit one undifferentiated natural-language rewrite.

## Candidate Domain Set

First-pass candidate set:

1. `scene`
   - Current place, participants, immediate situation, scene pressure, local objective, current interaction frame.
2. `character`
   - Character profile, current emotional/physical state, stable traits, role-specific facts.
3. `knowledge_boundary`
   - Who knows what, character-local visibility, secrets, misinformation, revealed/unrevealed facts.
   - Independent domain. Default execution owner can be `CharacterMemoryWorker`, but proposal / projection / trace output must remain `knowledge_boundary`-scoped.
4. `relation`
   - Character-to-character or faction-to-faction relationship state, trust, conflict, obligations.
5. `goal`
   - Active goals, intents, user/character objectives, short-term tasks.
6. `timeline`
   - Event spine, chronology, canon sequence, when something happened.
7. `plot_thread`
   - Ongoing arcs, unresolved threads, branch-level story lines.
8. `foreshadow`
   - Seeds, clues, planned payoff, callback obligations.
9. `world_rule`
   - World facts, setting rules, social rules, magic/technology/lore constraints, TRPG rule text references.
10. `inventory`
   - Items, resources, possession, equipment, consumables.
11. `rule_state`
   - TRPG mechanics state, status effects, checks/verdicts, combat/turn state, cooldowns, HP/resource counters, quest/mechanics state.
12. `chapter`
   - Longform chapter plan, chapter boundary, section target, draft/review context.
13. `narrative_progress`
   - Manuscript progress, accepted segment progress, current writing milestone, continuity status.

This expands the previous MVP list by making `knowledge_boundary` and `rule_state` explicit. `knowledge_boundary` is now confirmed as an independent domain, so the first-pass candidate set remains 13 unless another domain is later merged.

## Layer Placement

The same domain can appear in different Memory OS layers:

- `Core State.authoritative_state`: current truth for that domain.
- `Core State.derived_projection`: current writer-facing view for that domain.
- `Recall Memory`: historical records and summaries involving that domain.
- `Archival Knowledge`: long-term source material involving that domain.
- `Runtime Workspace`: current-turn temporary hits, tool results, proposals, and usage records involving that domain.

Example:

```text
[character]
  Core State.authoritative_state: current character state
  Core State.derived_projection: quick facts for writer
  Recall Memory: past scenes involving the character
  Archival Knowledge: imported character card
  Runtime Workspace: this turn's candidate updates
```

## Mode Defaults

### Longform

Default display and activation:

- `chapter`
- `narrative_progress`
- `scene`
- `character`
- `relation`
- `timeline`
- `plot_thread`
- `foreshadow`
- `world_rule`
- `goal`

Hidden or optional:

- `knowledge_boundary` when the story needs character-local knowledge tracking
- `inventory` when item/resource continuity matters
- `rule_state` normally disabled

### Roleplay

Default display and activation:

- `scene`
- `character`
- `knowledge_boundary`
- `relation`
- `goal`
- `timeline`
- `world_rule`

Hidden or optional:

- `plot_thread`
- `foreshadow`
- `narrative_progress`
- `inventory`

Normally disabled:

- `chapter`
- `rule_state`, unless the roleplay mode enables mechanics-like rules

### TRPG

Default display and activation:

- `scene`
- `character`
- `knowledge_boundary`
- `relation`
- `goal`
- `timeline`
- `world_rule`
- `inventory`
- `rule_state`

Hidden or optional:

- `plot_thread`
- `foreshadow`
- `narrative_progress`

Normally disabled:

- `chapter`, unless used as campaign journal / longform recap

## Initial Grill-Me Questions

1. Should `knowledge_boundary` be an independent domain, or a sub-block under `character`?
2. Should `goal` include quests/tasks for TRPG, or should quest-like mechanics live under `rule_state`?
3. Should `narrative_progress` be longform-only, or a shared progress/status domain for roleplay and TRPG as well?
4. Should `world_rule` hold only setting/lore/rule text, while all current mechanical state goes to `rule_state`?
