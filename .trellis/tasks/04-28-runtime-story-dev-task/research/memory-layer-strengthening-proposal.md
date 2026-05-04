# Memory Layer Strengthening Proposal For Story Runtime

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-04
>
> Purpose: provide a handoff proposal for a dedicated memory development session. The goal is not a minimum viable memory layer, but a sufficiently capable, maintainable, mode-extensible Memory OS foundation for story runtime.

## 1. Conclusion

Current memory implementation is directionally correct and already useful for the existing longform MVP. It has real Core State read surfaces, proposal/apply governance, Recall / Archival retrieval, and Block-shaped read envelopes.

However, it is not yet enough as the long-term foundation for full story runtime across longform, roleplay, and TRPG.

If story runtime now builds worker orchestration, writer-side retrieval, post-write maintenance, rollback, branch isolation, user-edit conflict handling, and ModeProfile-specific runtime behavior directly on the current narrow MVP memory surface, the implementation is likely to become patch-heavy and longform-hardcoded.

Recommended action:

Pause story runtime implementation briefly and run a dedicated memory strengthening session. That session should turn the current memory layer from "longform MVP-capable" into a "domain-first Memory OS foundation" that story runtime can rely on without repeated later rewrites.

## 2. Baseline Assessment

### 2.1 What Is Already Good

The current memory layer should not be discarded.

Existing useful capabilities:

- `Core State` already has real current truth / current projection read paths.
- `RpBlockView` / `RpBlockReadService` already expose Core State and Runtime Workspace as Block-shaped read views.
- `RetrievalBroker` already routes structured state / summary reads and Recall / Archival search.
- `proposal.submit` and `proposal.apply` already form a real governance chain with persisted proposal records, apply receipt, revision, before / after snapshot, and compatibility mirror sync.
- `Recall Memory` already stores more than chapter summary, including accepted story segments, scene transcript, continuity note, character long-history summary, and retired foreshadow summary.
- `Runtime Workspace` already exists as a read-side scratch surface, even though its scope is still narrow.

This means the memory layer follows the Letta-inspired direction:

- split memory into manageable blocks / layers instead of a single prompt blob;
- use tools and controlled services to read / mutate memory;
- keep long-term searchable memory separate from current in-context memory;
- avoid automatic promotion from retrieval hit to current truth.

### 2.2 What Is Not Enough

The current implementation is not yet a sufficient story-runtime foundation because many capabilities remain MVP-shaped or read-side only:

- `block` is mostly a read envelope / adapter, not yet a full stable contract for worker operations.
- Core State write coverage is still tied to longform MVP fields and limited operation types.
- Runtime Workspace cannot yet carry full turn lifecycle materials such as retrieval cards, expanded chunks, rule cards, review overlays, worker candidates, and usage records.
- Worker-facing memory tools are not yet explicit enough. Workers need stable read / propose / refresh / evidence / usage APIs, not direct database writes.
- User-edit priority and worker candidate conflict handling are not yet hard enough.
- Branch / rollback identity is not yet consistently carried through memory reads, writes, materialization, and retrieval visibility.
- Recall / Archival hits do not yet have a full "evidence to Core State" promotion workflow.
- All-mode domain coverage is not yet strong enough; current behavior still leans toward longform.

## 3. Scope

This strengthening proposal is for the memory layer, not for implementing the full story runtime.

The memory session should produce a foundation that supports all runtime modes:

- `longform`: chapter planning, manuscript progress, review overlay, accepted prose, outline / foreshadow / continuity maintenance.
- `roleplay`: current scene, character state, knowledge boundary, relation, user participation, fast post-write maintenance, background preparation for the next user turn.
- `trpg`: rule state, rule card, mechanics state, inventory, encounter / task state, hard rule provenance, and rule-sensitive retrieval.

The goal is not to finish every mode feature, but the memory contracts must not be longform-only. New code should be mode-extensible by construction.

## 4. Non-Goals

The memory session should not:

- replace `WritingPacketBuilder` with a generic memory compile system;
- make writer or worker free to write memory directly without governance;
- build a full Letta clone;
- force Recall / Archival physical storage to become block-native if adapter-backed retrieval remains sufficient;
- create a huge universal durable block table unless a concrete gap proves it is necessary;
- implement the full story runtime scheduler / worker orchestration;
- implement full branch UI;
- implement eval runner, grader, or cases.

## 5. Engineering Constraints

These constraints are mandatory because story runtime will build on this layer.

### 5.1 Contract-First

Memory APIs and DTOs must be treated as contracts, not incidental service return shapes.

Freeze stable contracts for:

- `domain`
- `domain_path`
- `layer`
- `block_id`
- `scope`
- `revision`
- `branch / turn identity`
- `source refs`
- `provenance`
- `permission`
- `base revision`
- `visibility`
- `materialization state`

Implementation code should not infer memory semantics from longform field names such as `chapter_digest` or `active_threads`.

### 5.2 Domain-First, Not Longform-First

Memory ownership must be expressed by domain.

The first-class domain set should include at least:

- `scene`
- `character`
- `knowledge_boundary`
- `relation`
- `goal`
- `timeline`
- `plot_thread`
- `foreshadow`
- `world_rule`
- `inventory`
- `rule_state`
- `chapter`
- `narrative_progress`

ModeProfile can activate different subsets, but the underlying memory system must not assume the active mode is longform.

The first-pass domain set is a bootstrap set, not a permanent hardcoded enum. The memory layer must support later domain / block lifecycle changes:

- add a new domain or block without editing every worker, controller, and storage service;
- disable / hide / retire a domain or block without deleting historical data;
- rename or migrate a domain / block through explicit migration metadata;
- change a domain's default mode activation and UI visibility through registry / config;
- attach new projection slots or Runtime Workspace material types to an existing domain;
- keep old records readable through versioned schema and compatibility mapping.

In implementation terms, the project should prefer a registry-driven domain / block catalog over scattered `if mode == longform` or hardcoded allowlists. Strong typing is still useful at the boundary, but it must be generated from or validated against the registry where practical, rather than becoming an obstacle to future domain/block CRUD.

### 5.3 Modular Services

Avoid a single "god memory service".

Recommended module boundaries:

- contract / schema models;
- Core State authoritative read / write;
- Core State projection read / refresh;
- Runtime Workspace turn-material store;
- Recall materialization and read/search adapter;
- Archival ingestion / reindex adapter;
- proposal / apply governance;
- worker-facing memory tools;
- branch / rollback visibility resolver;
- provenance and trace read surfaces;
- UI block inspection / editing surface.

Each module should have a narrow public interface and tests. Cross-module access should go through service contracts, not direct table peeking.

### 5.4 No Raw Memory Dumping

Workers and writer should not receive raw authoritative JSON, raw retrieval hits, or all blocks by default.

All runtime-facing reads should go through:

- explicit refs;
- domain filters;
- context packets;
- bounded projection slots;
- retrieval cards with stable short ids;
- source refs and provenance.

### 5.5 Governed Mutation

Workers may manage memory, but only through governed tools.

Allowed pattern:

```text
worker reads evidence
  -> worker emits structured candidate / proposal / projection refresh request
  -> deterministic validation / permission / revision check
  -> apply or review depending on permission / policy
  -> version / provenance / trace update
```

Disallowed pattern:

```text
worker produces natural-language rewrite
  -> runtime writes it directly into memory
```

### 5.6 User Edit Priority

User edits to Core State are highest priority.

Worker candidates must carry base revision. If target revision changes before apply, the candidate must be invalidated, revalidated, recalculated, or routed to review. It must never silently overwrite user edits.

High-permission workers may auto-apply without user review when the permission profile allows it, but this still means governed apply. It does not mean raw storage mutation, skipping base revision checks, or skipping provenance / event / dirty tracking.

### 5.7 Branch-Aware By Design

The memory strengthening session does not need to deliver full branch UI, but memory records must be ready for branch / rollback.

Memory reads and writes should be attributable to:

- story session;
- active branch head;
- turn lineage;
- source turn or accepted material ref.

Rollback and branch must not require copying the whole memory store. Prefer visibility / lineage / copy-on-write semantics.

### 5.8 Testability

Every major memory contract must be testable without running the full LLM workflow.

Tests should cover:

- domain-general Core State reads and writes;
- projection refresh by slot;
- Runtime Workspace lifecycle;
- permission rejection;
- base revision conflict;
- user edit superseding worker candidate;
- retrieval evidence not automatically becoming Core State;
- branch / visibility filtering;
- Recall / Archival ingestion and reindex path;
- mode-specific domain activation without longform assumptions.

## 6. Capability Gaps And Proposed Strengthening

### 6.1 Memory Contract Registry

Problem:

Current domain / block / layer semantics exist across docs and read views, but are not yet hard enough as a single contract.

Proposal:

Create a memory contract registry that defines:

- domain ids and descriptions;
- allowed layers per domain;
- domain lifecycle state: active, hidden, retired, migrated;
- default mode activation;
- default UI visibility;
- block templates and block lifecycle state;
- authoritative object ids;
- projection slot ids;
- allowed operations;
- default permission policy;
- branch / turn identity requirements.

This registry should be data-driven or declarative enough to extend. Avoid scattering domain allowlists across services.

The registry should also be the source for future domain / block management:

- adding a domain;
- adding a block under a domain / layer;
- retiring a domain or block;
- migrating old ids to new ids;
- changing mode defaults;
- changing UI visibility;
- changing worker ownership defaults.

Expected benefit:

Story runtime workers can bind to domains consistently, and ModeProfile can activate / hide / configure domains without hardcoding mode-specific branches everywhere.

### 6.2 Core State Domain Coverage

Problem:

Current Core State write path still leans on longform MVP allowlist fields and limited operation types.

Proposal:

Upgrade Core State so every story-runtime domain can have:

- authoritative object identity;
- payload schema reference;
- exact read by ref;
- current revision;
- provenance;
- apply receipt linkage;
- projection slots;
- user-edit path where allowed.

At minimum, support all candidate domains listed in this task's memory domain design. Implementation can seed schemas gradually, but the registry and read/write contract should not be longform-only.

Expected benefit:

Workers can manage `character`, `knowledge_boundary`, `relation`, `rule_state`, and other non-longform domains without inventing side channels.

### 6.3 Authoritative Mutation Operation Set

Problem:

The governance chain exists, but mutation operation coverage is incomplete.

Proposal:

Expand the canonical operation set behind proposal/apply:

- patch fields;
- upsert record;
- remove record;
- append event;
- add relation;
- remove relation;
- set status;
- replace list item by stable id;
- merge structured object by policy;
- tombstone / invalidate record.

Operations should be typed, validated, and mapped through domain schema. Do not let every worker invent its own patch format.

Expected benefit:

Core State becomes generally editable across modes while keeping deterministic governance.

### 6.4 Runtime Workspace As Turn Material Store

Problem:

Runtime Workspace is currently too narrow for full story runtime.

Proposal:

Expand Runtime Workspace into the standard current-turn material store for:

- user input refs;
- writer output refs;
- writer-side retrieval cards;
- retrieval short-id mapping;
- expanded retrieval chunks;
- retrieval miss / gap records;
- retrieval usage record;
- TRPG rule card / state card;
- longform review overlay / tracked change / comment;
- worker candidate updates;
- worker evidence bundles;
- post-write trace;
- packet refs and token usage metadata.

Runtime Workspace remains temporary and not story truth. It must have explicit materialization rules into Core State, Recall, or Archival.

Expected benefit:

Writer retrieval, worker post-write, review overlay, rule cards, and trace can share one turn lifecycle instead of creating separate ad hoc storage.

### 6.5 Worker-Facing Memory Tool Contract

Problem:

Letta's useful idea is that an agent manages memory through tools. In this project, the equivalent actor is the block-owner worker, but worker-facing tools are not yet clear enough.

Proposal:

Define worker-facing memory tools as governed APIs:

- read Core State authoritative object by ref;
- read current projection slot;
- search Recall;
- search Archival;
- read Runtime Workspace material by ref;
- submit Core State proposal;
- request projection refresh;
- record evidence refs;
- record retrieval usage;
- record worker candidate;
- read versions / provenance;
- check permission and base revision.

These tools must be permission-aware and branch-aware. They should return stable structured data, not informal strings.

Expected benefit:

Workers can become memory managers without bypassing governance or coupling directly to storage internals.

### 6.6 Projection Refresh Contract

Problem:

Core State current view is essential for writer packet, but refresh responsibility and source refs need a stronger contract.

Proposal:

Treat projection refresh as a first-class operation:

- projection slot id;
- target domain;
- source authoritative refs;
- source turn / evidence refs;
- refresh reason;
- base revision;
- generated items;
- expiration / dirty state;
- updated by worker / deterministic process.

Projection is not raw summary text. It is a durable current view inside Core State, derived from authoritative state and recent accepted material.

Expected benefit:

Writer packet can consume stable views without each runtime mode rebuilding its own summary logic.

### 6.7 Recall / Archival Evidence Promotion

Problem:

Recall / Archival search hits are evidence. They need a clear path into current truth when they become relevant.

Proposal:

Define a promotion chain:

```text
retrieval hit
  -> Runtime Workspace retrieval card
  -> writer usage record or worker evidence record
  -> block-owner worker candidate
  -> governed apply or review depending on permission / policy
  -> Core State authoritative update
  -> projection refresh
```

Recall and Archival should not automatically write Core State. The worker must decide what becomes current truth and preserve provenance. Whether the resulting change auto-applies or waits for user review is controlled by permission / policy.

Expected benefit:

Retrieval can support long-context continuity without corrupting current state or confusing evidence with truth.

### 6.8 User-Editable Memory Surface

Problem:

The product requires all memory layers to be visible, with different edit paths. The format must support UI, worker proposal, trace, and future rollback.

Proposal:

Freeze canonical JSON / DSL block format for user-visible memory:

- block metadata;
- entries with stable ids;
- display labels;
- editable fields;
- source refs;
- provenance;
- revision;
- permission level;
- validation errors;
- materialization status.

Core State can support direct governed editing. Recall is mostly review / invalidate / recompute. Archival edits must go through Story Evolution / ingestion / reindex.

Expected benefit:

Frontend editing and backend worker operations use the same memory semantics instead of parallel formats.

### 6.9 Branch / Rollback Memory Identity

Problem:

Story runtime needs Git-like rollback and future branch isolation. If memory records are not branch-ready now, later implementation will require invasive rewrites.

Proposal:

Add or standardize branch / turn identity fields across memory-related records:

- Core State authoritative revisions;
- projection slots;
- Runtime Workspace materials;
- Recall materializations;
- Archival edits where branch-scoped;
- retrieval visibility metadata;
- proposal and apply receipts;
- packet/window metadata.

Use copy-on-write / visibility semantics. Branch creation should not duplicate all memory content.

Expected benefit:

Rollback and branch can be implemented on top of memory lineage instead of special-casing every store later.

### 6.10 Memory Context Overview

Problem:

Current system has multiple inspection surfaces, but no single story-runtime view that explains what memory is active, dirty, pending, or blocked.

Proposal:

Add a memory context overview DTO for UI / debug / worker planning:

- active domains;
- active blocks by layer;
- dirty blocks;
- pending proposals;
- pending worker candidates;
- current projection status;
- retrieval cards pending promotion;
- branch / turn identity;
- permission profile;
- warnings and validation issues.

This is a read surface, not a new truth store.

Expected benefit:

Developers, UI, and future eval can inspect the Memory OS state without reading many unrelated endpoints.

## 7. Proposed Development Slices

### Slice A: Contracts And Registry

Deliver:

- Memory domain registry.
- Block / layer / scope / revision / branch identity contract.
- Domain / block lifecycle metadata for active / hidden / retired / migrated states.
- Migration mapping for renamed or retired domains / blocks.
- Mode activation defaults for longform / roleplay / TRPG.
- Contract tests proving no longform-only assumptions and proving a new domain / block can be registered without editing unrelated services.

### Slice B: Core State Generalization

Deliver:

- Domain-general authoritative object read/write.
- Expanded typed operation set.
- Projection slot refresh contract.
- User edit base revision handling.
- Tests for non-longform domains such as `knowledge_boundary` and `rule_state`.

### Slice C: Runtime Workspace Turn Store

Deliver:

- Runtime Workspace materials for retrieval cards, usage records, rule cards, review overlays, worker candidates, evidence bundles, and packet refs.
- Lifecycle rules: temporary, materialized, discarded, promoted, invalidated.
- Tests for writer-side retrieval and TRPG rule card storage without writer / scheduler implementation.

### Slice D: Worker-Facing Memory Tools

Deliver:

- Governed worker tools for read / search / propose / refresh / evidence / usage / provenance.
- Permission and base revision checks.
- Structured output and error contracts.
- Tests proving workers cannot bypass governance.

### Slice E: Branch / Rollback Readiness

Deliver:

- Branch / turn identity propagation through memory records.
- Visibility resolver for active branch lineage.
- Copy-on-write direction documented and tested at contract level.
- Retrieval visibility metadata prepared for branch-aware filtering.

### Slice F: UI / Inspection Surface

Deliver:

- Canonical JSON / DSL memory block format for UI.
- Memory context overview DTO.
- Read endpoints or service methods for all layers.
- Tests covering Core direct edit, Recall invalidate / recompute flag, and Archival edit via ingestion / reindex path.

## 8. Acceptance Criteria For Memory Dev Session

The memory strengthening session is successful only if:

- Memory contracts are domain-first and mode-extensible.
- Longform, roleplay, and TRPG can each activate different domains without changing storage code.
- Core State can support current truth and current projection for all candidate domains.
- Runtime Workspace can store all current-turn temporary materials needed by story runtime.
- Worker-facing tools exist as governed APIs, not direct storage shortcuts.
- User edit priority is enforced through revision conflict handling.
- Recall / Archival hits remain evidence until promoted through worker + proposal/apply.
- Branch / rollback identity is present in memory records or explicitly represented by a visibility resolver.
- Canonical JSON / DSL supports both UI editing and worker proposal trace.
- Tests cover non-longform domains and failure paths, not only happy-path longform.

## 9. Recommended Handoff Summary

Use this one-sentence task for the memory dev session:

> Strengthen RP Memory OS from a longform MVP-capable read/proposal/retrieval foundation into a domain-first, all-mode, worker-ready memory layer with stable contracts, governed mutation, Runtime Workspace turn materials, user-edit conflict handling, branch/rollback readiness, and UI-editable canonical block format.

## 10. Dev Session Gap Response Addendum

This section answers implementation-level gaps raised by the memory dev session. These answers are based on the current story runtime discussion and should be treated as proposal refinements, not separate scope expansion.

### 10.1 Identity Anchor Contract

Gap:

The proposal says memory must be branch / turn aware, but does not define a concrete identity anchor or which DTOs / tables carry it.

Answer:

Every story runtime memory operation must be bound to one pinned runtime identity:

```text
StorySession
  + active BranchHead
  + Turn
  + runtime profile snapshot
```

Plain meaning:

- `StorySession` says which active story runtime this belongs to.
- `BranchHead` says which story branch / timeline is currently active.
- `Turn` says which user / writer / worker cycle produced or consumed the material.
- `runtime profile snapshot` says which mode / worker / retrieval / permission policy was pinned for this turn.

The source of this identity should be the turn-start runtime state. A turn should allocate or resolve this identity before writer generation, retrieval calls, worker candidates, proposal submission, projection refresh, and packet/window metadata writes.

Memory-related DTOs / records should carry the identity when relevant:

- Core State authoritative revisions: `story_id`, `session_id`, `branch_id` or `branch_head_id`, `turn_id` or `turn_seq`, `profile_snapshot_id`.
- Projection slots / refresh records: same identity plus source authoritative refs and source turn refs.
- Runtime Workspace materials: same identity is mandatory.
- Recall materializations: same identity for branch-scoped material; story-global imported material may carry story/global scope plus optional branch visibility metadata.
- Archival edits: story-global by default, branch-scoped only when explicitly created by branch-specific Story Evolution.
- Retrieval queries/cards/usage records: same identity, because retrieval evidence must be attributable to the turn that used it.
- Proposals and apply receipts: same identity plus `base_refs`, `target_refs`, `base_revision`, and source evidence refs.
- Writer packet/window metadata: same identity plus packet version / token usage metadata.

Implementation consequence:

Runtime API may still take `session_id` as the external entry point, but internal memory read/write/search must resolve active branch and turn before work starts. Retrieval indexes remain derived search infrastructure and should filter by active branch lineage / visibility, not become truth records themselves.

### 10.2 Lightweight Memory Change Event Spine

Gap:

The proposal mentions provenance and overview, but does not define the lightweight event spine needed for trace, rollback, branch visibility, worker dirty check, and packet/window recompute.

Answer:

Add a lightweight memory change event record. This is not full event sourcing and does not require rebuilding all memory from events. It is an index / trace spine over committed or candidate memory changes.

Each event should record:

- event id;
- story / session / branch / turn identity;
- actor: user, worker, system, setup activation, story evolution;
- event kind: user edit, proposal submitted, proposal applied, projection refreshed, recall materialized, archival ingested, runtime material created, runtime material promoted, block retired, migration applied;
- affected layer, domain, block id, entry id where relevant;
- before / after revision or base / target revision;
- source refs: turn material, retrieval card, worker candidate, user edit, rule card, review overlay;
- visibility effect: active, hidden, invalidated, branch-only, global;
- dirty targets: affected projection slot, packet/window consumer, retrieval visibility, worker domain.

Expected use:

- trace can show why memory changed;
- rollback / branch can filter by event visibility and affected revisions;
- worker dirty check can know which domains need refresh;
- packet/window recompute can know which context slots are stale;
- UI can show recent memory changes without reading every underlying table.

Boundary:

The event spine records committed and important candidate changes, but low-level storage remains the source for current state. Do not build a heavy event-sourced database unless a later need proves it necessary.

### 10.3 User Edit vs Worker Candidate Conflict Rules

Gap:

`base_refs` are stored, but apply-side hard base revision checks are not specified.

Answer:

User edits have highest priority. Worker candidates must never silently overwrite a user edit.

Required rule:

```text
worker candidate / proposal target has base_revision
  -> apply reads current target revision
  -> if current revision != base_revision
       reject / invalidate / require recalculation / route to review
  -> otherwise apply
```

Default handling:

- If the target changed because of explicit user edit: candidate becomes stale and should not auto-apply.
- If the target changed because another worker applied a compatible update: deterministic merge may be allowed only when operation semantics are explicitly safe.
- If merge safety is unclear: route to review or recompute.
- If the candidate only refreshes a projection slot and authoritative state changed: refresh must recompute from the new authoritative revision, not reuse stale output.

Records needed:

- candidate id / proposal id;
- `base_refs` with revisions;
- target refs;
- actor and submit source;
- conflict status;
- stale reason;
- superseded_by event id or revision;
- optional recompute request id.

This rule applies to Core State authoritative changes and projection refreshes. It also applies to Runtime Workspace candidate promotion if the candidate targets memory state.

### 10.4 Runtime Workspace Data Model

Gap:

The proposal lists Runtime Workspace materials, but does not define the required shape.

Answer:

Runtime Workspace should be a typed turn-material store, not an expanded list of ad hoc rows. Each material should have a stable envelope:

- `material_id`;
- `material_type`;
- short id mapping for writer-facing cards, such as `R1`, `R2`, `RULE1`;
- story / session / branch / turn identity;
- producer: writer tool, worker, rule engine, user edit, system;
- domain / block refs where relevant;
- payload;
- source refs;
- status;
- TTL or lifecycle policy;
- materialization / discard / promotion rule;
- usage record linkage;
- evidence bundle linkage.

Minimum first material types:

- `writer_input_ref`;
- `writer_output_ref`;
- `retrieval_card`;
- `retrieval_expanded_chunk`;
- `retrieval_miss`;
- `retrieval_usage_record`;
- `rule_card`;
- `rule_state_card`;
- `review_overlay`;
- `worker_candidate`;
- `worker_evidence_bundle`;
- `post_write_trace`;
- `packet_ref`;
- `token_usage_metadata`.

Lifecycle states:

- `active`: usable during this turn;
- `used`: explicitly used by writer / worker;
- `unused`: returned but not used;
- `expanded`: full content requested;
- `promoted`: material has been transformed into proposal / Core State / Recall / Archival;
- `discarded`: intentionally not kept;
- `expired`: no longer relevant after turn / TTL;
- `invalidated`: superseded by user edit, rollback, branch switch, or newer revision.

Materialization rules:

- Runtime Workspace is not story truth.
- Retrieval cards and expanded chunks are evidence.
- Worker candidates are not memory changes until proposal/apply or review path accepts them.
- Rule cards can enter writer packet and post-write trace, but rule-state changes still need governed memory update where they affect Core State.

### 10.5 ModeProfile To Runtime Snapshot Closure

Gap:

The proposal says mode activation, but does not define setup draft -> validated runtime snapshot -> turn pinning -> hot update next turn.

Answer:

ModeProfile must compile into a validated runtime snapshot before active runtime uses it.

Required chain:

```text
setup draft / worker config
  -> validate
  -> compile runtime profile snapshot
  -> activation stores snapshot id/version
  -> turn start pins snapshot id/version
  -> hot update creates next snapshot
  -> next turn can use new snapshot
```

The runtime snapshot should include:

- mode identity: longform / roleplay / TRPG / future mode;
- active domains and hidden domains;
- block templates and UI visibility defaults;
- worker catalog and enabled worker execution units;
- worker ownership defaults by domain;
- worker permission profile by domain / layer / block;
- retrieval policy;
- Runtime Workspace material policy;
- projection refresh policy;
- post-write frequency / trigger policy;
- writer tool policy, including bounded retrieval availability;
- provider / model selection where configured;
- latency / budget defaults;
- review / permission defaults.

Hot update rule:

- Active turn uses the pinned snapshot even if the user changes config mid-turn.
- Config change compiles a new snapshot.
- New snapshot takes effect from the next turn unless the user explicitly restarts / reruns current turn.

This prevents worker, retrieval, and apply behavior from changing halfway through one turn.

### 10.6 Projection Refresh Write Contract

Gap:

Projection is currently mostly read / provenance. The proposal should define refresh/write semantics.

Answer:

Projection refresh must be a first-class write operation. It should not be treated as informal summary replacement.

Projection refresh input should include:

- projection slot id;
- domain;
- block id / domain path;
- source authoritative refs with revisions;
- source Runtime Workspace material refs;
- source Recall / Archival evidence refs if used;
- base revision;
- refresh actor: worker, deterministic process, setup activation, user-requested refresh;
- refresh reason: post-write, user edit, retrieval promotion, rule update, scene switch, manual refresh, window overflow;
- generated projection items;
- dirty / expired marker;
- consumer invalidation targets.

Refresh checks:

- if source authoritative revisions changed after base revision, recompute or reject stale refresh;
- if user manually edited the underlying Core State, worker refresh must not overwrite user intent;
- if projection slot is consumed by writer packet, mark packet/window consumer dirty after refresh.

Projection output should record:

- new projection revision;
- provenance refs;
- refresh event id;
- updated consumer dirty markers;
- warnings / validation errors.

Projection remains a durable current view inside Core State. It is derived from truth and evidence, but it is not itself the source of truth.

### 10.7 Retrieval Promotion And Usage Hook Contract

Gap:

Recall / Archival promotion chain is directionally right, but missing handling for misses, low confidence, unused cards, and expanded-unused cards. Writer retrieval usage hook must be a hard gate.

Answer:

Writer-side retrieval should use a mandatory usage record if any retrieval occurred in the turn.

Retrieval flow:

```text
writer detects knowledge gap
  -> calls retrieval tool
  -> Runtime Workspace stores retrieval cards with short ids
  -> writer may request expansion for cards
  -> before final output, writer records usage
  -> post-write only processes usage record + evidence refs
```

Usage record should classify every returned card:

- `used`: directly used in writer output;
- `expanded_used`: full content was expanded and used;
- `expanded_unused`: full content was expanded but not used;
- `unused`: card was returned but not used;
- `low_confidence`: writer judged it unreliable or insufficient;
- `miss`: retrieval did not find enough information;
- `knowledge_gap`: unresolved gap remains after attempts.

Handling rules:

- `used` / `expanded_used`: eligible for worker evidence bundle and possible Core State proposal.
- `expanded_unused`: keep trace for debugging, but do not promote by default.
- `unused`: discard or keep only short trace; do not promote.
- `low_confidence`: do not promote; may trigger review or better query suggestion.
- `miss` / `knowledge_gap`: record in Runtime Workspace and optionally create worker / user-facing gap note; do not invent facts.

Post-write must not process raw retrieval hits blindly. It should process the usage record and only the evidence cards linked from that record.

### 10.8 UI Editable Canonical JSON Governance

Gap:

The proposal says canonical JSON / DSL for UI, but not how it binds to backend governance.

Answer:

User-visible memory must use one canonical block / entry envelope that both UI and backend governance understand.

Each displayed block should include:

- block id;
- domain;
- layer;
- scope;
- branch / turn visibility;
- revision;
- permission level;
- lifecycle state;
- source refs / provenance;
- validation summary;
- editable fields;
- allowed actions;
- apply / reindex / recompute entry points.

Each editable entry should include:

- stable entry id;
- entry type;
- current value;
- editable fields;
- field-level validation rules;
- base revision;
- source refs;
- user edit metadata;
- conflict state;
- last modified actor;
- last modified turn / event id.

Layer-specific edit rules:

- Core State: direct governed edit is allowed; it must create revision, event, provenance, and dirty markers.
- Projection: user normally edits authoritative facts, not projection text directly. Manual projection refresh is allowed.
- Recall: primarily review, invalidate, recompute, or filter; routine direct factual editing is not the default path.
- Archival: edit through Story Evolution / ingestion / reindex so chunk, embedding, provenance, and search visibility remain consistent.
- Runtime Workspace: mostly trace / temporary material; user can inspect, but durable changes must go through promotion / proposal / apply.

This prevents UI from becoming a separate, incompatible memory editor.

## 11. Resulting Memory Dev Priorities

After the dev session gap review, the recommended implementation order becomes stricter:

1. Identity anchor and branch/turn fields first.
2. Domain / block registry and lifecycle metadata.
3. Runtime Workspace typed material store.
4. Memory change event spine.
5. Core State base revision conflict enforcement.
6. Projection refresh write contract.
7. Writer retrieval usage hook and promotion handling.
8. UI canonical JSON governance.

These priorities should be handled before story runtime worker implementation depends on the memory layer.

## 12. Cross-Session Dependency Notes

The memory dev session and story runtime dev session are not independent tracks. They should be treated as coordinated slices over the same RP architecture.

### 12.1 Dependency Direction

Memory dev provides foundations that story runtime should depend on:

- identity anchor: `StorySession + BranchHead + Turn + runtime profile snapshot`;
- domain / block registry and lifecycle;
- Runtime Workspace material model;
- memory change event spine;
- base revision conflict enforcement;
- projection refresh contract;
- retrieval usage / promotion contract;
- UI canonical JSON governance.

Story runtime dev provides requirements that memory dev must not ignore:

- worker ownership is by domain, while execution workers may aggregate related domains;
- writer packet needs Core State current view plus recent raw user/writer turns;
- writer-side retrieval uses Runtime Workspace cards and a mandatory usage hook;
- post-write processing prepares the next writer-facing view;
- roleplay / TRPG need background processing after writer output without blocking user typing;
- longform review overlay and TRPG rule card must enter the same turn-material lifecycle.

### 12.2 Coordination Rule

When a dev session discovers a gap in another layer, it should not silently invent a local workaround.

Required handling:

1. State the missing cross-layer contract in plain language.
2. Decide whether it is already covered by current task docs.
3. If covered, cite the owning document / section.
4. If not covered but answerable from existing direction, add it as a proposal refinement.
5. If product semantics are unclear, return it to the main design discussion instead of hardcoding.

### 12.3 Boundary Rule

Memory dev may implement contracts needed by story runtime, but should not implement full story runtime worker orchestration.

Story runtime dev may consume memory contracts, but should not patch around missing memory capability by adding longform-only storage or hidden ad hoc state.

If a runtime feature requires memory capability that does not exist yet, prefer pausing that runtime slice and adding the missing memory contract first.

### 12.4 Current User Intervention Status

No immediate user decision is required for the eight dev-session gaps addressed above. They are consistent with already confirmed story runtime direction.

Future user decisions may be needed if a dev session proposes:

- changing the first-pass 13-domain bootstrap set;
- making a retired / migrated domain physically deleted instead of hidden / tombstoned;
- making writer or worker directly mutate memory outside governed tools;
- treating retrieval hits as facts without worker + proposal/apply;
- implementing branch behavior by copying all memory instead of visibility / lineage / copy-on-write;
- making ModeProfile hot updates affect the current in-flight turn.
