# Memory Strengthening Preflight Grill Questions

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-04
>
> Purpose: record the pre-implementation grill-me queue for aligning the Memory Layer Strengthening Proposal with the proposal session before any coding starts.
>
> Status: pending alignment. This document is a question checklist, not an implementation authorization.

## Context

The current memory direction is Letta-inspired, but not a Letta clone. The useful Letta reference points are:

- memory is split into labeled blocks rather than one undifferentiated prompt blob;
- one memory-managing actor can hold multiple blocks;
- memory changes go through tools and then trigger prompt / context rebuild;
- blocks carry metadata such as labels, descriptions, read-only flags, version, and history pointers;
- git-backed memory can treat file storage as source of truth while database rows act as read/cache surfaces.

The RP implementation must adapt those mechanics to project-specific needs:

- story truth is governed by `Core State`, not by arbitrary block text replacement;
- Recall / Archival hits are evidence, not current truth;
- user-visible memory editing must preserve provenance, branch / rollback visibility, and worker conflict handling;
- workers own story domains, while blocks are layer-specific containers or edit surfaces;
- ModeProfile activates domains, workers, retrieval behavior, packet behavior, and permission defaults.

## How To Use This Queue

- Use these questions before starting the memory strengthening implementation.
- Ask one question at a time in the active discussion.
- For each question, align with the proposal session and then record the confirmed direction in the relevant task document.
- Do not re-open already confirmed broad principles unless the proposal session explicitly contradicts them.

## Q1. Letta Borrowing Boundary

Question:

Which Letta mechanisms are we deliberately copying, and which ones must diverge because RP story memory has stronger truth, branch, and user-edit requirements?

Recommended direction:

Copy the mechanics of labeled blocks, read-only flags, versioned edits, tool-mediated memory mutation, multi-block prompt / context compile, and context rebuild after changes. Do not copy "agent edits raw core memory text and that becomes truth" as-is. RP must keep authoritative story truth behind domain schema, permission, proposal/apply or explicit user-edit apply, branch / turn visibility, and provenance.

Why it blocks coding:

Without this boundary, implementation may either overfit Letta's text-block model or overbuild a new system that ignores the proven block/tool pattern.

## Q2. First Slice Boundary

Question:

Should the first implementation slice be `Memory Contract Registry + identity/event skeleton`, rather than Runtime Workspace, worker tools, or branch UI?

Recommended direction:

Yes. Start with a registry and contract slice: domain / block / layer / scope / revision / branch / turn / permission / lifecycle metadata, plus tests proving non-longform domains can be registered without editing unrelated services. This keeps later Runtime Workspace and worker-tool work from hardcoding another longform MVP shape.

Why it blocks coding:

Every later slice needs the same registry vocabulary. If the registry is deferred, each service will invent local allowlists.

## Q3. Registry Form

Question:

Should the first registry be code/declarative-config driven, database-driven, or full user-editable CRUD?

Recommended direction:

Use a versioned declarative registry first, with a narrow service API. It should support active / hidden / retired / migrated states and migration aliases, but not expose full runtime CRUD until governance, UI, and rollback semantics are ready.

Why it blocks coding:

A database-first registry invites premature product CRUD. A hardcoded enum makes future domain/block migration painful.

## Q4. Domain Bootstrap Set

Question:

Is the first implementation bootstrap set frozen as 13 domains: `scene`, `character`, `knowledge_boundary`, `relation`, `goal`, `timeline`, `plot_thread`, `foreshadow`, `world_rule`, `inventory`, `rule_state`, `chapter`, and `narrative_progress`?

Recommended direction:

Yes, as bootstrap data in the registry, not as a permanent scattered enum. `knowledge_boundary` and `rule_state` stay explicit domains. ModeProfile activates different subsets.

Why it blocks coding:

Core State schemas, projection slots, worker ownership, and UI blocks need a shared initial vocabulary.

## Q5. Domain Owner vs Worker Execution Unit

Question:

Does "worker ownership by domain" mean one execution worker per domain, or can one execution worker own multiple related domains?

Recommended direction:

Responsibility is recorded per domain; an execution worker may bind a small set of strongly related domains. For example, `CharacterMemoryWorker` can execute for `character`, `knowledge_boundary`, and possibly `relation`, but outputs must be separated by domain / block and permissions must be checked per target.

Why it blocks coding:

The worker catalog, permission profile, and output schema depend on this distinction.

## Q6. Story Identity Spine

Question:

What is the minimum identity tuple every memory read/write/proposal/retrieval material must carry?

Recommended direction:

Use `StorySession + BranchHead + Turn + RuntimeProfileSnapshot`. The API can still enter through `session_id`, but memory operations must resolve active branch head and turn lineage before reading, writing, filtering retrieval, or refreshing projection.

Why it blocks coding:

Without this spine, rollback and branch isolation cannot be added later without invasive rewrites.

## Q7. Branch / Rollback Minimum

Question:

What must be implemented now for branch / rollback readiness, even if full branch UI is out of scope?

Recommended direction:

Add contract fields or visibility resolver hooks for branch and turn lineage across Core State revisions, projection slots, Runtime Workspace materials, Recall materialization metadata, proposal/apply receipts, and retrieval filters. Do not copy the whole memory store per branch; prefer visibility / lineage / copy-on-write semantics.

Why it blocks coding:

If memory rows remain session-only, rollback will only restore graph state while memory and retrieval continue leaking future facts.

## Q8. Core State Store vs Compatibility Mirror

Question:

For new domain-general Core State work, is the formal Core State store the primary target, with legacy mirror kept only for compatibility?

Recommended direction:

Yes. New domain-general objects should target the formal store and registry. The legacy `StorySession.current_state_json` mirror can remain for existing longform compatibility, but it should not drive new domain semantics.

Why it blocks coding:

Otherwise new domains will be forced back into longform field names such as `chapter_digest` or `active_threads`.

## Q9. Operation Set And Stable Entry Identity

Question:

What is the canonical mutation operation set, and do list-like records require stable entry ids before replace/remove operations are allowed?

Recommended direction:

Support typed operations such as patch fields, upsert record, remove/tombstone record, append event, replace list item by stable id, add/remove relation, set status, and policy-based merge. Any replace/remove inside a list must target a stable item id; otherwise it should route to review or fail validation.

Why it blocks coding:

Without stable entry identity, worker updates and user edits will race over positional arrays.

## Q10. User Edit Apply Path

Question:

Is user editing Core State modeled as proposal/apply, direct governed user edit apply, or both?

Recommended direction:

Support an explicit governed user-edit apply path for Core State, with validation, actor=`user`, base revision, event record, provenance, and consumer invalidation. Proposal/apply remains the worker/default governed path. User edits have highest priority and supersede stale worker candidates.

Why it blocks coding:

The conflict model cannot be enforced if user edits and worker proposals use unrelated paths.

## Q11. Base Revision Conflict Rule

Question:

When a worker candidate or proposal targets a block whose revision changed after the worker read it, what happens?

Recommended direction:

Fail closed: mark stale, invalidate, route to review, or request recalculation. It must never silently overwrite a user edit or newer accepted update.

Why it blocks coding:

The current proposal model can carry `base_refs`, but apply semantics must actually enforce them.

## Q12. Runtime Workspace Data Model

Question:

Should Runtime Workspace get a generic turn-material store with typed material kinds, rather than more ad hoc artifact/discussion tables?

Recommended direction:

Yes. Add a turn-scoped material model with `material_id`, `material_kind`, `domain`, `domain_path`, `source_refs`, `short_id`, `payload`, `lifecycle`, `visibility`, `created_by`, `turn_id`, and optional expiration/materialization refs. It remains temporary and not truth.

Why it blocks coding:

Writer-side retrieval, rule cards, review overlays, evidence bundles, worker candidates, and usage records need one shared lifecycle.

## Q13. Retrieval Card And Usage Hook

Question:

If writer-side retrieval happens, must final output be blocked until a structured usage record exists?

Recommended direction:

Yes. Retrieval results enter Runtime Workspace as cards with turn-scoped short ids. Before final output is accepted, writer must record used cards, expanded cards, unused cards, misses, and knowledge gaps. Missing usage should trigger repair or rejection.

Why it blocks coding:

Without usage, post-write workers cannot know which evidence actually influenced the output.

## Q14. Evidence Promotion Boundary

Question:

What is the only allowed path for Recall / Archival evidence to become Core State current truth?

Recommended direction:

Retrieval hit -> Runtime Workspace card -> writer usage or worker evidence -> domain-owner worker candidate -> governed apply or user review depending on permission / policy -> Core State authoritative update -> projection refresh. Retrieval hits never auto-promote into Core State.

Why it blocks coding:

This prevents search evidence from corrupting current story truth.

## Q15. Projection Refresh Semantics

Question:

Is projection refresh an authoritative proposal, a maintenance operation, or both depending on target?

Recommended direction:

Projection refresh is a governed maintenance operation, not authoritative truth mutation. It must carry projection slot id, target domain, source refs, source turn/evidence refs, base revision, refresh reason, actor, dirty/expired state, and invalidation event. It may be triggered by worker output but writes only derived projection.

Why it blocks coding:

Writer packet quality depends on current views, but projection must not blur into truth.

## Q16. Worker-Facing Tool Surface

Question:

Are worker-facing memory tools internal runtime services first, or public external tool/MCP surfaces?

Recommended direction:

Keep them internal/governed first. Expose stable structured service methods for read/search/propose/refresh/evidence/usage/provenance/permission checks. Do not widen the public external memory tool family until contracts and permission semantics are stable.

Why it blocks coding:

Public tool contracts are harder to change and should not leak unfinished worker internals.

## Q17. Permission Profile Source

Question:

Where does per-worker + per-domain/block permission come from at runtime?

Recommended direction:

Activation compiles ModeProfile and worker configuration into a versioned RuntimeProfileSnapshot. Each turn pins one snapshot version. Permission checks read the pinned snapshot and fail closed when a worker lacks permission.

Why it blocks coding:

If services read setup draft or mutable runtime UI config directly, turns become unreproducible and hot updates can affect in-flight work.

## Q18. Memory Change Event Spine

Question:

Do we add a lightweight memory change event record now?

Recommended direction:

Yes, but not full event sourcing. Record actor, layer, session/branch/turn lineage, affected domain/block/refs, operation kind, downstream invalidation, and source proposal/apply/materialization refs. Keep it as trace/invalidation spine, not as the only source of truth.

Why it blocks coding:

Worker dirty checks, rollback, branch visibility, packet recompute, and UI audit need one shared change signal.

## Q19. UI / Canonical JSON Boundary

Question:

Should canonical JSON / DSL block format be implemented as backend read/write contract before frontend editing UI exists?

Recommended direction:

Yes. Define block metadata, entries with stable ids, editable fields, source refs, provenance, revision, permission, validation errors, and materialization state. Frontend can later render it; workers and user-edit flows can already rely on the same shape.

Why it blocks coding:

If UI editing and worker proposal use different formats, trace and conflict handling will split.

## Q20. Test Gate For The First Memory Session

Question:

What tests are required before saying the memory strengthening session is ready for story runtime construction?

Recommended direction:

At minimum: registry tests for non-longform domains; Core State read/write tests for `knowledge_boundary` and `rule_state`; base revision conflict tests; user edit supersedes worker candidate tests; Runtime Workspace retrieval card/usage/rule-card tests; projection refresh source-ref tests; branch visibility filter tests; Recall/Archival evidence-not-truth tests; permission rejection tests.

Why it blocks coding:

The whole point of the memory session is to remove longform-only hidden assumptions before worker orchestration depends on it.

## First Question To Ask In Discussion

Start with Q1:

> Which Letta mechanisms are we deliberately copying, and which ones must diverge because RP story memory has stronger truth, branch, and user-edit requirements?

This should be asked first because it constrains the level of registry, block, tool, and governance work that follows.

## Main Session Answers - 2026-05-04

These answers are based on the current story runtime design discussion, `memory-layer-strengthening-proposal.md`, `story-runtime-memory-domain-preliminary-design.md`, and the task PRD. No immediate user intervention is required for these 20 questions. They should be treated as aligned implementation direction unless a dev session proposes changing the product semantics.

### A1. Letta Borrowing Boundary

Confirmed.

We deliberately copy Letta's proven mechanics:

- labeled memory blocks;
- one memory actor managing multiple blocks;
- metadata on blocks, including label, description, read-only, version, and history pointer;
- tool-mediated memory operations;
- context / prompt rebuild after memory changes;
- git-like source-of-truth plus database read/cache idea as a reference.

We do not copy Letta's raw text-block truth model directly.

RP story memory must diverge because story truth is stricter:

- `Core State.authoritative_state` is the current truth;
- Recall / Archival hits are evidence, not facts;
- worker changes go through governed proposal/apply or explicit user-edit apply;
- branch / turn visibility must be preserved;
- provenance and user edit priority are mandatory.

Implementation implication:

Use Letta as evidence that "memory actor + multiple blocks + tools" is viable. Do not let worker or writer directly replace arbitrary memory text and call it story truth.

### A2. First Slice Boundary

Confirmed.

The first memory strengthening implementation slice should be:

```text
Memory Contract Registry
  + identity spine
  + lightweight event skeleton
```

Runtime Workspace, worker tools, projection refresh, and branch-ready filtering depend on the same vocabulary. If the registry is delayed, each later service will create its own local allowlist and the system will become longform-hardcoded again.

### A3. Registry Form

Confirmed.

Use a versioned declarative registry first, exposed through a narrow service API.

Do not start with full user-editable registry CRUD. The product does need future domain / block CRUD, but direct runtime CRUD should wait until governance, UI, migration, rollback, and permission semantics are ready.

Required first version:

- registry file or code-backed declarative config;
- registry version;
- active / hidden / retired / migrated lifecycle states;
- aliases / migration mapping;
- mode activation defaults;
- permission defaults;
- block templates;
- service methods to resolve registry entries.

Avoid scattered hardcoded enums as the source of truth.

### A4. Domain Bootstrap Set

Confirmed.

The first bootstrap domain set is:

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

This is a bootstrap set, not a permanent hardcoded list. ModeProfile activates different subsets. Later domain / block additions, hiding, retirement, and migration must go through registry / config, not service-level rewrites.

### A5. Domain Owner vs Worker Execution Unit

Confirmed.

Responsibility is recorded by domain. Execution worker is allowed to bind multiple related domains.

Example:

`CharacterMemoryWorker` may maintain:

- `character`
- `knowledge_boundary`
- possibly `relation`

But output must remain separated by target domain / block:

- separate proposals;
- separate projection refreshes;
- separate traces;
- separate permission checks.

This keeps domain ownership clear without exploding worker count.

### A6. Story Identity Spine

Confirmed.

Every memory read / write / proposal / retrieval material must bind:

```text
StorySession + BranchHead + Turn + RuntimeProfileSnapshot
```

External APIs may still enter with `session_id`, but internal memory operations must resolve active branch and turn lineage before:

- Core State read/write;
- projection refresh;
- Runtime Workspace material write;
- retrieval query/card/usage;
- proposal/apply;
- Recall materialization;
- packet/window metadata update.

### A7. Branch / Rollback Minimum

Confirmed.

Full branch UI is not required in the first memory session, but branch / rollback readiness is required.

Minimum implementation contract:

- branch / turn fields or resolver hooks on Core State revisions;
- projection slots tied to branch / turn lineage;
- Runtime Workspace materials tied to branch / turn;
- Recall materialization visibility metadata;
- proposal/apply receipts carrying branch / turn identity;
- retrieval filters prepared for active branch lineage;
- no full memory copy per branch.

Preferred strategy:

```text
visibility + lineage + copy-on-write
```

not whole-store duplication.

### A8. Core State Store vs Compatibility Mirror

Confirmed.

New domain-general work should target the formal Core State store and registry.

The legacy `StorySession.current_state_json` compatibility mirror can remain for existing longform paths, but it must not define new domain semantics.

Implementation rule:

New domains such as `knowledge_boundary` and `rule_state` should not be forced into fields like `chapter_digest`, `active_threads`, or `character_state_digest`.

### A9. Operation Set And Stable Entry Identity

Confirmed.

Canonical operation set should include:

- patch fields;
- upsert record;
- remove / tombstone record;
- append event;
- replace list item by stable id;
- add relation;
- remove relation;
- set status;
- policy-based merge.

Stable entry ids are required for list-like replace/remove operations.

If an operation targets a list item by position only, it should fail validation or route to review. Positional array mutation is too fragile for user edit conflict, worker candidates, and branch rollback.

### A10. User Edit Apply Path

Confirmed.

Support both:

- worker/default path: proposal/apply;
- user path: direct governed user-edit apply.

Direct user-edit apply does not mean ungoverned database write. It must still include:

- validation;
- actor = user;
- target refs;
- base revision;
- revision increment;
- memory change event;
- provenance;
- dirty / invalidation markers.

User edits have highest priority and supersede stale worker candidates.

### A11. Base Revision Conflict Rule

Confirmed.

Fail closed.

If a worker candidate or proposal targets revision N and current target revision is no longer N:

- do not silently apply;
- mark stale / conflicted;
- invalidate candidate;
- route to review; or
- request recalculation.

Automatic merge is allowed only for explicitly safe operation semantics. User edits always win over stale worker candidates.

### A12. Runtime Workspace Data Model

Confirmed.

Runtime Workspace should become a typed turn-material store, not more ad hoc artifact/discussion tables.

Minimum material envelope:

- `material_id`;
- `material_kind`;
- story / session / branch / turn identity;
- `domain`;
- `domain_path`;
- `source_refs`;
- writer-facing `short_id` when needed;
- `payload`;
- `lifecycle`;
- `visibility`;
- `created_by`;
- optional expiration / materialization refs.

It remains temporary and is not story truth.

Material kinds should include retrieval cards, expanded chunks, retrieval usage, rule cards, review overlays, worker candidates, evidence bundles, packet refs, and token usage metadata.

### A13. Retrieval Card And Usage Hook

Confirmed.

If writer-side retrieval happens, final output acceptance must require a structured usage record.

The usage record must classify:

- used cards;
- expanded and used cards;
- expanded but unused cards;
- unused cards;
- misses;
- low-confidence results;
- remaining knowledge gaps.

Missing usage should trigger repair or rejection, because post-write workers need to know which evidence actually influenced writer output.

### A14. Evidence Promotion Boundary

Confirmed.

Only allowed path:

```text
Retrieval hit
  -> Runtime Workspace card
  -> writer usage record or worker evidence record
  -> domain-owner worker candidate
  -> governed apply or user review depending on permission / policy
  -> Core State authoritative update
  -> projection refresh
```

Recall / Archival hits never auto-promote into Core State.

High-permission worker output can auto-apply without user review, but it must still pass permission checks, base revision checks, provenance recording, and memory change event / dirty tracking.

### A15. Projection Refresh Semantics

Confirmed.

Projection refresh is a governed maintenance operation, not authoritative truth mutation.

It writes only `Core State.derived_projection`.

Required refresh input:

- projection slot id;
- target domain;
- source authoritative refs with revisions;
- Runtime Workspace / Recall / Archival source refs if used;
- base revision;
- refresh reason;
- refresh actor;
- dirty / expired semantics;
- consumer invalidation targets.

If the authoritative source changed after the base revision, stale refresh must recompute or fail.

### A16. Worker-Facing Tool Surface

Confirmed.

Worker-facing memory tools should be internal governed runtime services first, not public external/MCP surfaces.

Initial tool/service surface:

- read Core State;
- read projection;
- search Recall;
- search Archival;
- read Runtime Workspace material;
- submit proposal;
- request projection refresh;
- record evidence;
- record usage;
- read versions / provenance;
- check permission;
- check base revision.

Do not widen public memory tools until contracts and permissions are stable.

### A17. Permission Profile Source

Confirmed.

Runtime permissions come from a pinned `RuntimeProfileSnapshot`.

Chain:

```text
ModeProfile + worker configuration
  -> validate
  -> compile RuntimeProfileSnapshot
  -> turn start pins snapshot
  -> permission checks read pinned snapshot
```

Do not read mutable setup draft or live UI config directly during a turn. Hot updates create a new snapshot and affect the next turn.

Permission checks should fail closed.

### A18. Memory Change Event Spine

Confirmed.

Add lightweight memory change events now, but not full event sourcing.

Event record should include:

- actor;
- layer;
- session / branch / turn lineage;
- affected domain / block / refs;
- operation kind;
- source proposal/apply/materialization refs;
- downstream invalidation;
- dirty targets;
- visibility effect.

Source of truth remains the memory stores. The event spine exists for trace, invalidation, rollback visibility, worker dirty checks, packet recompute, and UI audit.

### A19. UI / Canonical JSON Boundary

Confirmed.

Canonical JSON / DSL block format should be implemented as backend contract before frontend editing UI is complete.

The backend shape should define:

- block metadata;
- entries with stable ids;
- editable fields;
- source refs;
- provenance;
- revision;
- permission;
- validation errors;
- materialization state;
- allowed actions / apply / reindex / recompute entry points.

This prevents UI editing and worker proposals from splitting into incompatible formats.

### A20. Test Gate For The First Memory Session

Confirmed.

Minimum test gate:

- registry tests for non-longform domains;
- add/register domain or block without editing unrelated services;
- Core State read/write tests for `knowledge_boundary`;
- Core State read/write tests for `rule_state`;
- base revision conflict tests;
- user edit supersedes worker candidate tests;
- Runtime Workspace retrieval card tests;
- Runtime Workspace usage record tests;
- Runtime Workspace rule-card tests;
- projection refresh source-ref / stale-source tests;
- branch visibility filter tests;
- Recall / Archival evidence-not-truth tests;
- permission rejection tests;
- hot update does not affect current pinned turn tests.

Passing only longform happy-path tests is not enough.

## Derived Cross-Layer Notes

1. The memory strengthening work should run before story runtime worker implementation depends on these contracts.
2. Story runtime dev should not patch around missing memory capability with longform-only state.
3. Memory dev should not implement full worker orchestration; it should expose the contracts that runtime workers will consume.
4. Runtime, memory, retrieval, setup, and UI sessions must treat `RuntimeProfileSnapshot`, `BranchHead`, `Turn`, and Runtime Workspace material ids as shared contract terms.
5. If a dev session proposes changing any of these confirmed semantics, return that question to the main design discussion instead of hardcoding locally.

## User Intervention Status

No immediate user decision is required for Q1-Q20.

Future user intervention is needed only if a dev session proposes one of these changes:

- changing the 13-domain bootstrap set;
- making domain / block registry full user-editable CRUD before governance is ready;
- letting writer or worker mutate memory outside governed tools;
- treating retrieval hits as current truth without worker + proposal/apply;
- making branch implementation duplicate all memory instead of using visibility / lineage / copy-on-write;
- letting ModeProfile hot updates affect an in-flight turn;
- allowing positional list mutation without stable entry ids;
- exposing worker-facing tools as public external/MCP tools before internal contracts are stable.
