# Memory Layer Story Runtime Blockers Dev Proposal

> Scope: this document is a memory-layer blocker audit and development proposal for story runtime. It does not propose implementing story runtime scheduling, writer orchestration, UI polish, or retrieval-core rewrite.

## Engineering Implementation Rules

Memory dev must treat the following engineering rules as acceptance constraints, not style preferences:

1. **Contract-first, module-first implementation.** Add stable DTOs, repository interfaces, service boundaries, and tests before wiring story-runtime call sites. Do not hide new behavior inside longform-only branches or compatibility mirrors.
2. **Keep layers decoupled.** Core State, Projection/View, Runtime Workspace, Recall Memory, Archival Knowledge, proposal/apply, retrieval/index, and event/debug surfaces must keep separate truth ownership. Cross-layer work should happen through explicit contracts, refs, events, and lifecycle transitions.
3. **Registry/config driven, not hardcoded.** Domain, block, worker, permission, retrieval policy, and context policy behavior must compile from registry/config into `RuntimeProfileSnapshot`. Adding or disabling a roleplay/TRPG/longform domain or worker should not require editing the core scheduler or memory mutation kernel.
4. **Reusable worker/tool foundation.** Worker-facing memory operations should use shared tool contracts and permission guards. Specific workers may add small mode/domain logic, but they should not each invent a different write path, proposal shape, retrieval path, or trace format.
5. **Maintainable all-mode design.** Implement for story runtime as a whole, not only the current longform MVP. Longform compatibility adapters are allowed, but they must not become the architecture baseline.
6. **Deterministic core services.** Identity resolution, branch visibility, read manifests, Runtime Workspace lifecycle, Projection/View refresh, proposal/apply decisions, and event emission should be deterministic backend logic wherever possible. LLM calls may propose structured changes, but backend services enforce contracts.
7. **No hidden direct writes.** User direct edits, worker writes, brainstorm summary applies, retrieval promotion, and evolution changes must all go through governed mutation/revision/provenance/event/dirty-target paths appropriate to the layer.
8. **Migration-friendly persistence.** New persistent records must include identity, visibility, revision/provenance, actor/source refs, and compatibility strategy where needed. Avoid JSON blobs that block later branch/read/debug/eval queries.
9. **Focused tests per contract.** Each slice should include tests for identity propagation, branch isolation, permission enforcement, stale-base/conflict handling, event emission, and deterministic read output where relevant.

## 0. Conclusion

Current memory layer is directionally correct, but it is still not enough to support the intended story runtime.

The important point is not "memory is absent". The current code already has useful pieces: Core State formal store, projection fallback/read services, proposal/apply governance, RetrievalBroker, Recall/Archival ingestion, MemoryContractRegistry, MemoryRuntimeIdentity, RuntimeWorkspaceMaterial DTOs, and MemoryChangeEvent DTOs.

The blocker is that these pieces are still not wired into one branch-aware, turn-scoped, RuntimeProfileSnapshot-pinned memory contract:

- `MemoryRuntimeIdentity` exists as a model, but `Turn`, `BranchHead`, and `RuntimeProfileSnapshot` are not first-class persistent entities in the current story store, and most memory/retrieval/proposal DTOs and records do not require the identity.
- `Runtime Workspace` has a typed material contract, but `RuntimeWorkspaceMaterialService` is still an in-process store and is not integrated into writer retrieval usage, post-write promotion, debug, branch, or rollback.
- `MemoryChangeEvent` exists, but the event spine is in-process and cannot support persistent trace/debug/eval/invalidation queries.
- `Core State` formal store exists, but important runtime surfaces still depend on `StorySession.current_state_json`, `ChapterWorkspace.builder_snapshot_json`, chapter-scoped projection mirror/fallback, bundle-first projection refresh, and longform allowlists.
- Retrieval/Recall/Archival can ingest and search material, but query identity, active branch visibility, snapshot-pinned retrieval config, writer usage records, and post-write promotion chain are not enforced.
- Registry/config work exists, but it is still bootstrap/read-only. It does not yet provide a durable, configurable domain/block/worker catalog that can support longform, roleplay, and TRPG without hardcoding service branches.

Therefore story runtime should not proceed by "just calling current memory services". Memory dev must first strengthen the memory contract so the runtime has deterministic read surfaces, governed write surfaces, branch/rollback visibility, and durable current-turn material.

## 0.5 Complete Capability Target

This proposal is not only a blocker list. It is the memory-layer completion target required before full story runtime implementation should rely on memory as its foundation.

The answer to "when is memory ready for story runtime?" is not one single gate. It has two bars:

| Bar | Meaning | Required scope |
| --- | --- | --- |
| `runtime boot bar` | Enough for the first story runtime implementation to connect to memory without baking in the wrong architecture. This is not the final memory foundation. | All P0 requirements plus the explicit minimal P1 subset listed below. |
| `full runtime foundation bar` | Enough for memory to be treated as the stable foundation for maintainable longform, roleplay, and TRPG runtime. | All P0 and P1 requirements in this document are implemented, tested, and exposed through stable backend contracts. P2 may remain later product/ops work. |

Memory dev should not interpret P1 items as optional polish. In this project, P1 means "not always needed in full form for the first runtime boot slice, but required for the intended maintainable story runtime across longform, roleplay, and TRPG."

The `runtime boot bar` requires these P1 minimums:

1. Minimal registry/profile compilation: default domain/block/worker/retrieval/context/permission config can compile into `RuntimeProfileSnapshot`, without requiring the full dynamic management UI.
2. Shared Core mutation kernel: user direct Core edit, worker proposal/apply, and brainstorm summary apply cannot use separate hidden write paths.
3. Persistent event record foundation: `MemoryChangeEvent` records must persist identity, actor, layer/domain/block/entry refs, source refs, dirty targets, visibility effect, and metadata. Rich debug/eval query UX may follow later.
4. Minimal user Core edit backend path if direct edit is exposed in the boot UI/API: product can call it `direct edit`, but backend must still use the governed mutation/revision/provenance/event/dirty-target path.
5. Minimal registry/config guardrails: first boot can ship default descriptors, but core services must already be descriptor-driven enough that later roleplay/TRPG domains and workers do not require rewriting the memory mutation/read kernel.

The complete memory capability target is:

1. `Runtime Workspace` is a persistent turn material layer, not an in-process cache.
2. `Turn`, `BranchHead`, and `RuntimeProfileSnapshot` are first-class persistent records and every runtime memory read/write/search/material/proposal/event can be tied to them.
3. Core, Projection/View, Runtime Workspace, Recall, Archival, retrieval/index, proposal/apply, and event reads all respect active branch and rollback visibility.
4. `Core State` fact layer is the only current truth layer; Projection/View is strictly derived from facts and has source revisions/provenance/stale-base checks.
5. User direct Core edit, worker proposal/apply, and brainstorm summary apply share one conflict, dirty-target, invalidation, event, and projection refresh model.
6. Writer-side retrieval is traceable: retrieval cards, expansion, misses, usage records, and post-write promotion all flow through Runtime Workspace and governed memory writes.
7. Worker-facing memory tools are stable contracts carrying identity, worker, phase, domain/block, permission, source refs, and trace.
8. Recall Memory has all-mode branch-aware lifecycle, materialization, search, invalidation, recompute, and review semantics.
9. Archival Knowledge has Evolution edit/version/reindex governance and retrieval/index visibility.
10. MemoryChangeEvent is persistent and queryable enough for debug, eval, invalidation, and turn replay.
11. Deterministic read surfaces exist for context/token assembly: a given identity and profile snapshot can reproduce what memory refs were visible and selected.
12. RuntimeProfileSnapshot compiles domain/block/worker activation, permission levels, retrieval policy, and context policy from registry/config.
13. Domain/block/worker registry is configurable and migration-friendly, so adding roleplay/TRPG workers or domains does not require hardcoding the runtime.
14. User-visible memory inspection/edit backend contracts exist for Core direct edit, Recall review/recompute/invalidation, and Archival Evolution, even if UI polish comes later.

Only after the `full runtime foundation bar` is met should the main story runtime implementation treat memory as a stable base instead of a moving dependency. Before that, story runtime may proceed only against the narrower `runtime boot bar` contracts and must keep adapters explicit.

## 1. Story Runtime Hard Dependencies On Memory Layer

| Dependency | Story runtime needs | Memory-layer contract that must exist |
| --- | --- | --- |
| `Runtime Workspace` persistence | Store writer input/output refs, retrieval cards, expanded chunks, misses, usage records, worker candidates, evidence bundles, packet refs, token usage, and post-write traces per turn | Durable turn material store keyed by `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` |
| `Turn` / `BranchHead` / `RuntimeProfileSnapshot` identity | Every read, search, proposal, projection refresh, retrieval card, and workspace material belongs to one active branch and one turn under one pinned profile | First-class persistent records and mandatory identity propagation |
| branch / rollback visibility | Rollback and branch switch must not leak future turns, invalidated workspace materials, branch-scoped Recall, Archival visibility, or stale index hits | Branch-aware visibility resolver applied by Core, Projection, Workspace, Recall, Archival, and RetrievalBroker |
| `Core State` fact vs `Projection/View` | Writer consumes stable views, but truth stays in authoritative facts | Projection slots must be strictly derived from authoritative revisions with provenance and stale-base checks |
| Three write paths | User direct core edit, worker proposal/apply, and brainstorm summary apply all mutate or refresh memory differently | One conflict/invalidation model over base revisions, dirty targets, projection refresh, candidate invalidation, and trace |
| domain / block / worker registry | Runtime can add, hide, disable, migrate, or replace domain/block/worker per mode | Registry/config-driven domain/block/worker contracts and profile compilation, not service hardcoding |
| worker-facing memory tools | Workers need governed reads/searches/proposals without bypassing memory policy | Stable tool DTOs carrying identity, worker id, phase, permission profile, source refs, and trace |
| `Recall Memory` | Search/review historical material without confusing it with current truth | Branch-aware historical material lifecycle, source refs, invalidation/recompute policy, and promotion rules |
| `Archival Knowledge` + Evolution | Setup/evolution material can be edited, reindexed, and searched safely | Versioned archival source/edit/reindex pipeline with provenance, event emission, and visibility metadata |
| Retrieval cards and writer usage | Retrieval hits entering writing must be inspectable and promotable | Broker results materialized into Runtime Workspace cards; writer usage hook records used refs; post-write promotion consumes those refs |
| Event spine / debug / eval | Runtime decisions must be traceable by turn/branch/domain/layer | Persistent `MemoryChangeEvent` records and query APIs for inspection/debug/eval |
| deterministic read surface | Context/token assembly must be reproducible for a pinned turn | Snapshot-pinned read manifest from Core/Projection/Recall/Archival/Workspace under active identity |
| Permission consistency | Direct edit, proposal/apply, silent/notify/manual policies, and worker tool access must agree | RuntimeProfileSnapshot compiles permission matrix from registry/config and proposal/apply enforces it |
| Multi-mode expansion | longform, roleplay, and TRPG need different active domains, blocks, workers, tools, and refresh policies | Same memory contract, mode/profile overlays, and registry-driven worker/domain/block activation |

### 1.1 Deterministic Read Manifest Contract

The deterministic read surface must become a concrete manifest, not a vague "memory compile" concept.

Every writer packet / scheduler packet build should be able to persist or reconstruct a read manifest with at least:

- `MemoryRuntimeIdentity`: story/session, active branch head, turn, pinned runtime profile snapshot.
- active branch lineage used for visibility resolution.
- pinned `RuntimeProfileSnapshot` ref and relevant policy versions.
- visible refs considered from Core State, Projection/View, Runtime Workspace, Recall Memory, Archival Knowledge, proposal/apply, and retrieval/index surfaces.
- selected refs actually included in the packet.
- packet sections with source refs, source revisions, source hashes or equivalent version checks, and selection reason metadata.
- retrieval card refs, expanded chunk refs, retrieval miss refs, and writer usage refs when present.
- token usage and context policy metadata returned by the upstream model/provider or deterministic packet builder.

The purpose is to answer one product/debug/eval question: "What exactly did this runtime turn make visible to the writer or scheduler?"

## 2. Gap Priority Summary

| Priority | Gap | Why this priority |
| --- | --- | --- |
| P0 | Runtime Workspace is typed but not durable or turn-lifecycle integrated | Writer retrieval usage, post-write promotion, debug, pending workers, and rollback cannot be reliable |
| P0 | `Turn` / `BranchHead` / `RuntimeProfileSnapshot` are not first-class persisted identity and not propagated across memory APIs | Runtime memory operations will continue to mix session, branch, turn, and profile state |
| P0 | branch/rollback visibility is not enforced across Core/Projection/Workspace/Recall/Archival/index | Rollback/fork semantics cannot be correct if memory still reads "latest session" |
| P0 | Core facts and Projection/View derivation are not strict enough for story runtime | Writer may see stale or manually mutated views; worker refresh cannot be generic or branch-aware |
| P0 | Retrieval cards, writer usage hook, and post-write promotion chain are not wired | Retrieved material can influence prose without trace or governed promotion |
| P0 | Worker-facing memory tools and permission enforcement are not complete | Workers cannot safely operate across all modes/domains without bypassing policy |
| P1 | Registry/config-driven domain/block/worker management is still bootstrap/read-only | Adding roleplay/TRPG domains or workers still risks hardcoding |
| P1 | Conflict handling across user direct edit, worker proposal/apply, and brainstorm summary apply is incomplete | Candidate invalidation, projection refresh, and dirty-target recompute are not unified |
| P1 | Recall Memory lifecycle and branch-aware query semantics are underdefined in implementation | Historical memory can be searched, but not yet governed as all-mode branch-aware Recall |
| P1 | Archival Knowledge + Evolution + reindex/rebuild governance is incomplete | Setup ingestion exists, but runtime evolution/edit/reindex visibility is not enough |
| P1 | Memory change event spine is not persistent/queryable | Debug/eval/trace cannot reconstruct runtime memory decisions |
| P1 | Retrieval runtime config is not pinned to `RuntimeProfileSnapshot` | A turn can drift with latest story config instead of the profile it started with |
| P1 | Permission levels and proposal/apply policy are not unified | Registry defaults, worker permissions, and apply decisions can diverge |
| P1 | User-visible memory inspection/edit backend contract is incomplete | Core direct edit, Recall review/recompute, and Archival Evolution edit paths need stable backend contracts before UI can safely expose them |
| P2 | Advanced UI, physical purge, full branch UI, advanced eval runners, graph extraction optimization | Valuable later, but not required before memory can support first story runtime slice |

Readiness interpretation:

- `runtime boot bar` = all P0 rows, plus the P1 minimums from section 0.5. In particular, Slice H needs a minimal retrieval card / usage / promotion chain before the first runtime slice relies on writer-side retrieval, and Slice I needs persistent event records even if rich debug/eval queries are later.
- `full runtime foundation bar` = all P0 and P1 rows. P1 is still required for the intended product architecture; it is only allowed to arrive after the first runtime boot when the missing part is not on the boot critical path.
- P2 remains later product/ops work and must not block the first story runtime memory foundation.

## 3. Detailed Gaps

### P0-1. Runtime Workspace Persistence And Turn Lifecycle

**Current implementation evidence**

- `backend/rp/models/runtime_workspace_material.py` already defines `RuntimeWorkspaceMaterial`, `RuntimeWorkspaceMaterialKind`, lifecycle values, `source_refs`, `payload`, `metadata`, and mandatory `MemoryRuntimeIdentity`.
- `backend/rp/services/runtime_workspace_material_service.py` explicitly describes itself as an "In-process Runtime Workspace material service skeleton".
- `RuntimeWorkspaceMaterialStore` uses process-local dictionaries/lists: `materials_by_identity`, `short_ids_by_identity`, and `events`.
- There is no persistent `RuntimeWorkspaceMaterialRecord` in `backend/models/*`.
- `WritingPacketBuilder`, `WritingWorkerExecutionService`, and `LongformRegressionService` do not currently write or read Runtime Workspace materials as the main turn material surface.

**Why it blocks story runtime**

Story runtime needs `Runtime Workspace` to hold all current-turn temporary material: retrieval cards, expanded chunks, misses, usage records, worker candidates, evidence bundles, packet refs, token usage, and post-write traces. If this stays in process memory:

- cross-request writer/reviewer/debug flows cannot recover material;
- rollback and branch switch cannot invalidate or hide turn materials;
- post-write workers cannot consume writer usage records;
- pending/deferred workers have no durable input refs;
- eval cannot reproduce what the writer or worker saw.

**Recommended strengthening**

- Add durable Runtime Workspace records keyed by full identity: `story_id`, `session_id`, `branch_head_id`, `turn_id`, `runtime_profile_snapshot_id`.
- Preserve the existing typed DTO envelope; do not invent a second material shape.
- Persist lifecycle transitions: `active`, `used`, `unused`, `expanded`, `promoted`, `discarded`, `expired`, `invalidated`.
- Enforce `short_id` uniqueness per identity.
- Emit persistent `MemoryChangeEvent` for create/update/lifecycle transition.
- Expose deterministic query APIs by identity, material kind, domain, lifecycle, source refs, and short id.
- Treat Runtime Workspace as current-turn material only, never as story truth. Promotion to Core/Recall/Archival must go through governed paths.

**Acceptance standards**

- A material created in one service instance can be read by another service instance through persistent storage.
- Materials are isolated by `BranchHead` and `Turn`.
- `short_id` uniqueness is enforced per runtime identity.
- Lifecycle changes create queryable event records.
- Writer retrieval card, writer usage record, and worker candidate can be stored and queried by identity in focused tests.
- Rollback/branch visibility resolver can mark later-turn materials hidden/invalidated without physical deletion.

**Suggested dev slice**

Slice B: `Runtime Workspace Persistent Turn Material Store`.

---

### P0-2. `Turn` / `BranchHead` / `RuntimeProfileSnapshot` First-Class Identity

**Current implementation evidence**

- `backend/rp/models/memory_contract_registry.py` defines `MemoryRuntimeIdentity(story_id, session_id, branch_head_id, turn_id, runtime_profile_snapshot_id)`.
- `backend/models/rp_story_store.py` currently has `StorySessionRecord`, `ChapterWorkspaceRecord`, `StoryArtifactRecord`, `StoryDiscussionEntryRecord`, and `StoryBlockConsumerStateRecord`; it does not define persistent `BranchHeadRecord`, `StoryTurnRecord`, or `RuntimeProfileSnapshotRecord`.
- `StorySessionRecord.current_state_json` and `StorySessionRecord.runtime_story_config_json` still act as compatibility/current state/config holders.
- `ChapterWorkspaceRecord.builder_snapshot_json` still acts as a projection compatibility mirror.
- `backend/rp/models/memory_crud.py` inputs such as `MemoryGetStateInput`, `MemoryGetSummaryInput`, `MemorySearchRecallInput`, `MemorySearchArchivalInput`, `RetrievalQuery`, and `ProposalSubmitInput` do not require `MemoryRuntimeIdentity`.
- `backend/models/rp_core_state_store.py`, `backend/models/rp_memory_store.py`, and most retrieval records are keyed by story/session/chapter or collection, not by branch/turn/profile snapshot.
- `backend/rp/graphs/story_graph_runner.py` still uses a LangGraph thread keyed by `session_id`, which is not enough for memory visibility.

**Why it blocks story runtime**

The confirmed story runtime contract requires every runtime memory operation to bind:

```text
StorySession + active BranchHead + Turn + RuntimeProfileSnapshot
```

Without first-class records and propagation:

- a memory write cannot say which turn produced it;
- a retrieval hit cannot say which profile/config allowed it;
- rollback cannot find all materials after a target turn;
- branch switch cannot separate workspace/proposals/recall/index visibility;
- config changes can affect an in-flight turn because runtime reads latest session config.

**Recommended strengthening**

- Add persistent records for:
  - `BranchHead`: active branch identity, parent branch, parent turn, head turn, visibility status.
  - `StoryTurn`: turn id/sequence/kind/status, branch head, profile snapshot, actor, lifecycle timestamps.
  - `RuntimeProfileSnapshot`: immutable compiled runtime profile including mode, domain/block/worker activation, retrieval profile, packet profile, permission profile.
- Keep first-table schemas thin. Minimum fields:
  - `BranchHead`: `branch_head_id`, `story_id`, `session_id`, `branch_name`, `parent_branch_head_id`, `forked_from_turn_id`, `head_turn_id`, `status`, `visibility_scope`, `created_at`, `updated_at`.
  - `StoryTurn`: `turn_id`, `story_id`, `session_id`, `branch_head_id`, `turn_sequence`, `turn_kind`, `runtime_profile_snapshot_id`, `actor`, `status`, `started_at`, `completed_at`, `rolled_back_at` when applicable.
  - `RuntimeProfileSnapshot`: `runtime_profile_snapshot_id`, `story_id`, `session_id`, `mode`, `source_config_revision`, `compiled_profile_json`, `created_from`, `created_at`, `activated_at`, `superseded_at`.
- Add a deterministic identity allocator/resolver at turn start.
- Keep external APIs allowed to enter by `session_id`, but internal memory/retrieval/proposal/projection/workspace calls must use resolved identity.
- Add identity fields to relevant runtime records, DTOs, events, receipts, and retrieval queries.
- Provide compatibility defaults: existing sessions can get one default branch, one migration/default snapshot, and deterministic synthetic turn creation only where needed.

**Acceptance standards**

- A story runtime turn creates or resolves one `MemoryRuntimeIdentity` before any memory read/search/write.
- Runtime memory DTOs either carry identity or call a resolver that produces identity before hitting stores.
- Proposal records, apply receipts, projection refresh records/events, Runtime Workspace materials, retrieval card records, and memory events are identity-scoped.
- Tests cover missing identity rejection for runtime paths and compatibility resolution for legacy session-only paths.

**Suggested dev slice**

Slice A: `Runtime Identity Persistence And Propagation`.

---

### P0-3. Branch / Rollback Visibility Across Memory Layers And Index

**Current implementation evidence**

- Task docs confirm branch/rollback must keep post-rollback content invisible rather than physically deleted, and workspace/candidates should stay attached to their original `BranchHead`.
- The current store models do not have a first-class `BranchHeadRecord`.
- `backend/models/rp_core_state_store.py` authoritative and projection tables are keyed by `story_id/session_id` and projection `chapter_workspace_id`, not by branch/turn/profile identity.
- `backend/models/rp_memory_store.py` proposal/apply records are keyed by story/session/chapter but not branch/turn/profile.
- `backend/models/rp_retrieval_store.py` `KnowledgeChunkRecord` has story/collection/asset/domain/path/metadata/provenance, but no mandatory branch/turn/profile fields. `MemoryGraphEdgeRecord` has an optional `branch_id`, but that does not enforce retrieval chunk visibility.
- `backend/rp/retrieval/query_preprocessor.py` recognizes `branch_ids` as a filter key, but optional filters are not the same as enforcing active `BranchHead` visibility.
- Recall ingestion services are primarily keyed by story/session/chapter/source workspace.

**Why it blocks story runtime**

Story runtime cannot treat branch/rollback as only a LangGraph checkpoint feature. Memory, retrieval, projection, workspace, proposals, and index visibility must also follow active branch and rollback rules.

If memory continues to read latest session/global material:

- rolled-back future facts can remain visible in writer context;
- branch A can see branch B's workspace candidates or recall summaries;
- proposal/apply receipts cannot be associated with the branch where they happened;
- retrieval can return chunks that should be invisible for the active branch;
- debug/eval cannot explain why a hidden material was or was not available.

**Recommended strengthening**

- Implement a branch visibility resolver used by all memory read/search surfaces.
- Add lineage/visibility metadata to Core revisions, Projection slots/revisions, Runtime Workspace materials, Recall materializations, Archival source/chunk visibility where branch-scoped, proposals, apply receipts, and memory events.
- Define layer defaults explicitly:
  - Core State runtime revisions are branch-aware after activation; fork-before material is shared by lineage, fork-after material belongs to the writing branch.
  - Projection/View follows Core State because it is strictly derived from Core facts.
  - Runtime Workspace is branch-aware and turn-scoped; it must not be carried across branch switches.
  - Recall Memory is branch-aware by default because it records what happened on a branch.
  - Archival Knowledge setup / activation seed is story-global by default. Active Story Evolution writes are branch-scoped by default unless the user explicitly promotes them to selected branches, all existing branches, or story-global.
  - Retrieval index records are derived infrastructure and must inherit the visibility of their source content.
- Define rollback as a visibility transition over records after a target turn for the active branch. Prefer tombstone/visibility state over physical delete.
- Rollback authoritative semantics: rollback should create a branch-head transition plus durable rollback event/visibility records. It should not create fake Core fact revisions unless a layer-specific visibility record is required. In other words, rollback changes what the active line can see; it does not rewrite historical Core facts as if later turns never happened.
- RetrievalBroker must apply active branch visibility by default. Explicit cross-branch reads should be debug/admin-only and traceable.
- Index maintenance must be able to invalidate or hide branch-scoped chunks without requiring immediate physical purge.

**Acceptance standards**

- Given two branches under the same session, a default runtime read/search only returns material visible to the active branch.
- After rollback to turn N, turn N+1 materials are hidden from Core/Projection/Workspace/Recall/RetrievalBroker runtime reads.
- Proposal/apply and memory event queries can filter by branch and turn range.
- Retrieval tests show optional `branch_ids` filters cannot bypass active visibility for runtime reads.

**Suggested dev slice**

Slice C: `Branch/Rollback Visibility Resolver And Lineage Fields`.

---

### P0-4. Core State Facts And Projection/View Derived Contract

**Current implementation evidence**

- `backend/models/rp_core_state_store.py` defines formal Core State authoritative object/revision records and projection slot/revision records.
- The formal store identity dimension is still `story_id/session_id`; projection records also bind `chapter_workspace_id`.
- `backend/rp/services/projection_read_service.py` is explicitly a formal-store read service with mirror fallback.
- `backend/rp/services/projection_state_service.py` still loads and writes `ChapterWorkspace.builder_snapshot_json` compatibility snapshots and dual-writes when available.
- `backend/rp/services/projection_refresh_service.py` main entry is `refresh_from_bundle(chapter, bundle, refresh_request=None)`, still centered on `SpecialistResultBundle`.
- `ProjectionRefreshRequest.identity` is optional; event publishing is skipped if identity is missing.
- `backend/rp/services/story_state_apply_service.py` supports a longform allowlist: `chapter_digest`, `narrative_progress`, `timeline_spine`, `active_threads`, `foreshadow_registry`, `character_state_digest`.
- `backend/rp/services/legacy_state_patch_proposal_builder.py` maps legacy bundle patch fields into a fixed set of domains.

**Why it blocks story runtime**

Story runtime needs a hard split:

- `Core State.authoritative_state` = current truth/facts;
- `Projection/View` = derived writer/UI/runtime view from authoritative facts.

The current implementation is usable for longform MVP, but still permits story runtime to depend on compatibility mirrors, bundle-first refresh, optional identity, and hardcoded longform fields. That blocks:

- all-mode domain expansion;
- deterministic writer context;
- branch-aware projection refresh;
- clear stale-base detection when facts change;
- safe direct edits where projections must be recomputed or invalidated.

**Recommended strengthening**

- Make story runtime read `Core State` and `Projection/View` through formal store surfaces first; compatibility mirror fallback should be legacy/debug only for runtime paths.
- Require projection refresh requests to carry full runtime identity and source authoritative refs/revisions.
- Replace bundle-first projection refresh with worker-first `ProjectionRefreshRequest` contracts. Legacy bundle adapters can remain, but should adapt into the same request shape.
- Store projection provenance: source authoritative refs, source revisions, source turn, worker/domain/block owner, refresh policy, stale-base decision.
- Generalize operation/domain bindings through registry/config rather than hardcoded longform field allowlists.
- Enforce that projection mutation is refresh/derive only; direct user or worker truth changes target authoritative facts, then dirty projections are refreshed or invalidated.

**Acceptance standards**

- Projection refresh without identity is rejected for story runtime paths.
- Projection slots record source authoritative revisions and can detect stale base.
- Direct Core edit marks affected projection slots dirty and either refreshes synchronously for required views or marks them stale.
- A new domain/block projection can be registered and refreshed without editing longform allowlists.
- Existing longform adapters keep working through compatibility adapters, not by being the only path.

**Suggested dev slice**

Slice D: `Core/Projection Contract Hardening And Worker-First Projection Refresh`.

---

### P0-5. Retrieval Cards, Writer Usage Hook, And Post-Write Promotion

**Current implementation evidence**

- `backend/rp/services/retrieval_broker.py` can route `search_recall` and `search_archival`, and returns retrieval results/traces.
- `backend/rp/models/runtime_workspace_material.py` already includes material kinds for retrieval card, expanded chunk, retrieval miss, usage record, post-write trace, worker candidate, evidence, and packet refs.
- `backend/rp/services/writing_packet_builder.py` currently builds a deterministic packet for a "longform story system" from projection sections and runtime writer hints.
- `backend/rp/services/writing_worker_execution_service.py` renders and runs the writer packet but does not implement bounded retrieval loop, card expansion, or usage hook.
- `backend/rp/services/longform_regression_service.py` still performs post-write maintenance through legacy longform bundle/proposal/projection/recall ingestion rather than consuming Runtime Workspace usage records.

**Why it blocks story runtime**

Retrieval should not silently flow into prose. If a worker or writer searches Recall/Archival and uses a hit:

- the hit should be materialized as a Runtime Workspace retrieval card;
- expansion should produce expanded chunk materials;
- misses should be traceable;
- the writer should mark which cards were used;
- post-write workers should promote accepted facts through Core proposal/apply or Recall/Archival ingestion.

Without this chain, story runtime cannot answer:

- what evidence influenced this output;
- which hit was unused and can expire;
- which retrieved material became a Core fact;
- which Recall/Archival source needs reindex or invalidation;
- why a hallucinated fact entered the story.

**Recommended strengthening**

- Make RetrievalBroker able to materialize search results into Runtime Workspace cards under the active identity.
- Add writer/worker usage hook that records used retrieval card ids, expanded chunk ids, and missed queries.
- Ensure post-write workers use material refs and retrieval provenance as source refs when producing proposal/apply inputs, Recall candidates, or Archival evolution actions.
- Keep raw retrieval dumps out of the writer packet. The settled runtime path is: writer decides whether knowledge is missing, calls the unified retrieval tool, retrieval results are materialized as structured Runtime Workspace cards with stable short ids, the writer can request expanded chunks when card summaries are insufficient, and post-write workers later consume the used card/chunk refs. This must not add a separate pre-write LLM digest layer before the writer.
- Add lifecycle transitions: `active -> used/unused -> promoted/expired/invalidated`.
- For the `runtime boot bar`, Slice H may be delivered as a minimal closed loop:
  - retrieval hit becomes a Runtime Workspace card with stable short id and source refs;
  - writer can request expansion for already-returned cards;
  - writer usage records the cards/chunks actually used;
  - post-write scheduling can pass used refs to worker/proposal inputs;
  - no retrieval hit can directly become Core State truth without governed promotion.
  Full advanced debug UI, ranking improvements, and broad worker-side retrieval automation can follow after boot.

**Acceptance standards**

- A Recall/Archival search during a turn creates queryable Runtime Workspace card records.
- Writer usage creates a usage material referencing specific card/chunk ids.
- Post-write proposal source refs include Runtime Workspace material refs when facts come from retrieval.
- Unused cards can expire without becoming facts.
- Debug can show query, card, usage, proposal, apply, and promotion chain for one turn.

**Suggested dev slice**

Slice H: `Retrieval Card / Usage / Promotion Contract`.

---

### P0-6. Worker-Facing Memory Tool Contract And Permission Enforcement

**Current implementation evidence**

- `backend/rp/models/memory_crud.py` provides `memory.get_state`, `memory.get_summary`, Recall/Archival search, and proposal DTOs, but these inputs do not carry full runtime identity.
- `ProposalSubmitInput` has `story_id`, `session_id`, optional `chapter_workspace_id`, `domain`, operations, `base_refs`, and trace fields, but no required worker id, phase, permission profile, branch, turn, or snapshot.
- `backend/rp/services/memory_contract_registry.py` builds permission defaults and mode defaults, but it is still a bootstrap resolver rather than a compiled per-turn permission profile.
- `backend/rp/services/proposal_workflow_service.py` routes proposal submission through validation, persistence, policy, and apply, but policy is not visibly bound to `RuntimeProfileSnapshot` permission rules.
- `backend/rp/services/proposal_apply_service.py` enforces base revision conflicts, but apply receipts/records do not carry the full runtime identity/permission decision.

**Why it blocks story runtime**

Story runtime will have multiple workers across longform, roleplay, and TRPG. They must be able to read/search/propose/refresh through governed tools, not by calling arbitrary services.

If worker-facing tools lack identity and permission context:

- workers can read or propose against domains not enabled for the active profile;
- proposal/apply cannot explain why silent/notify/manual policy was chosen;
- roleplay/TRPG worker expansion requires ad hoc code branches;
- direct memory calls can bypass visibility, permission, and trace.

**Recommended strengthening**

- Define a stable worker-facing memory tool layer over existing services:
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.search_recall`
  - `memory.search_archival`
  - `runtime_workspace.create_material`
  - `runtime_workspace.update_lifecycle`
  - `proposal.submit`
  - `projection.refresh_request`
  - `memory.read_trace`
- For the `runtime boot bar`, freeze the shared internal service contracts and permission guard first. External tool DTOs can expose only the subset needed by boot workers, but they must already adapt to the same internal shapes instead of introducing a second path.
- Every tool call must carry or receive from context:
  - `MemoryRuntimeIdentity`
  - `worker_id`
  - `phase`
  - `domain`
  - `block_id` or block template id when relevant
  - compiled permission profile
  - source refs and trace refs
- Enforce read/search/propose/refresh permissions before store calls.
- Persist permission decisions in proposal/apply/event receipts.

**Acceptance standards**

- Unauthorized worker/domain/layer/tool combinations are rejected before storage mutation.
- Proposal records carry actor/worker/phase/identity/permission decision metadata.
- The same worker can operate in longform/roleplay/TRPG by profile configuration, not by separate service branches.
- Runtime tests prove direct service bypass is not used by worker execution path.

**Suggested dev slice**

Slice E: `Worker-Facing Memory Tools And Permission Integration`.

---

### P1-1. Registry / Config Driven Domain, Block, Worker Management

**Current implementation evidence**

- `MemoryContractRegistryService` is a read-only resolver over `build_bootstrap_memory_contract_registry()`.
- Bootstrap domains include mode defaults and block templates for longform/roleplay/TRPG, but these are static code defaults.
- Task docs require adding/hiding/disabling/migrating worker/domain/block by registry/config and `RuntimeProfileSnapshot`.
- Current story graph is still a fixed longform-oriented chain.

**Why it affects story runtime**

Mode expansion must not require editing scheduler branches, service allowlists, writer packet code, and worker wiring every time a domain/block/worker changes.

Roleplay and TRPG especially need different active domains, blocks, and worker phases. Static bootstrap is a useful skeleton, but it is not enough for user-configurable runtime.

**Recommended strengthening**

- Persist registry/config definitions separately from bootstrap defaults.
- Add descriptors for domain, block template, worker, worker phase policy, tool allowlist, refresh policy, and permission defaults.
- Compile `RuntimeProfileSnapshot` from registry/config at activation or profile publish time.
- Keep bootstrap registry as seed/defaults, not as the only source of truth.
- Add migration/deprecation metadata for domain/block aliases and removed workers.

**Acceptance standards**

- A new domain/block/worker descriptor can be added through config/registry without editing core services.
- RuntimeProfileSnapshot records the effective active domains/blocks/workers/tool policies.
- Disabled or migrated domains are resolved deterministically through registry alias/deprecation rules.

**Suggested dev slice**

Slice J: `Registry/Config Driven Domain-Block-Worker Management`.

---

### P1-2. Conflict Handling Across User Direct Core Edit, Worker Proposal/Apply, And Brainstorm Summary Apply

**Current implementation evidence**

- `ProposalApplyService` enforces base revision conflict checks for proposal targets.
- Current conflict checks are centered on proposal/apply and authoritative refs.
- User direct Core edit, worker candidate/proposal, and brainstorm summary apply are not represented as one shared mutation/invalidation pipeline.
- `MemoryChangeEvent` has dirty targets, but the persistent event/query/invalidation implementation is not complete.

**Why it affects story runtime**

There are three accepted Core write paths:

1. user direct core edit;
2. worker proposal/apply;
3. brainstorm summary apply.

They can conflict with each other. A user edit can invalidate pending worker candidates. A brainstorm summary can supersede existing projection slots. A worker proposal can be based on stale Core revisions. If these paths do not share conflict and dirty-target semantics, writer context can become stale or contradictory.

**Recommended strengthening**

- Introduce one internal Core authoritative mutation envelope for all Core authoritative mutations. The important point is one shared shape and validation path; the implementation does not have to use this exact class name.
- Product may expose this as `direct edit` for users, but backend implementation must not create a user-only raw write channel. User direct edit is an immediate governed apply through the same mutation/revision/provenance/event/dirty-target kernel, with user authority recorded as actor/origin.
- Require base revisions for any mutation that claims to edit existing Core facts.
- Record origin kind: `user_direct_edit`, `worker_proposal_apply`, `brainstorm_summary_apply`, `deterministic_system_refresh`.
- Emit dirty targets for affected projection slots, Runtime Workspace candidates, Recall materializations, and retrieval/index visibility where relevant.
- Define invalidation policy:
  - user direct edit can invalidate pending worker candidates targeting the same refs;
  - worker apply fails or requires rebase when base refs stale;
  - brainstorm summary apply should be a deterministic turn/control event with trace and projection refresh.

**Acceptance standards**

- There is no backend path that mutates Core facts without the shared mutation envelope or equivalent shared validation path.
- Direct edit and proposal/apply against the same stale revision produce deterministic conflict behavior.
- A direct edit creates dirty projection targets and invalidates matching pending candidates.
- Brainstorm summary apply records origin, turn/control context, and refresh effects.
- Inspection APIs can show why a candidate/projection was invalidated.

**Suggested dev slice**

Slice I can carry event/query support; Slice D/E should consume it for projection/proposal. If split separately, call it `Core Write Path Reconciliation`.

---

### P1-3. Recall Memory Lifecycle, Storage, Query, And Relation To Core/Archival

**Current implementation evidence**

- Existing Recall ingestion services cover accepted story segments, scene transcript, continuity notes, character long-history summaries, retired foreshadow summaries, and chapter/section summaries.
- These services primarily use story/session/chapter/source workspace metadata and retrieval ingestion/index jobs.
- RetrievalBroker can search Recall, but `RetrievalQuery` does not require runtime identity.
- Query preprocessing supports filters, but active branch visibility is not enforced by identity.

**Why it affects story runtime**

Recall Memory is not just "some searchable text". It is the layer for what already happened: past scenes, transcripts, accepted prose, historical summaries, continuity notes, and closed/resolved items.

Story runtime needs Recall to be:

- branch-aware;
- domain-tagged;
- queryable through broker under active identity;
- reviewable and recomputable;
- not confused with current Core facts;
- able to feed Runtime Workspace retrieval cards and post-write promotion.

If Recall remains longform/session/chapter-oriented, roleplay and TRPG will lack a reliable historical memory layer for turns, scenes, rules outcomes, inventory history, relationships, and knowledge boundaries.

**Recommended strengthening**

- Define all-mode Recall material lifecycle: create, compact, supersede, invalidate, recompute, hide by branch/rollback.
- Ensure Recall material carries story/session/branch/turn/source refs/domain/materialization kind.
- Keep Recall as historical material. It should not be the authority for current state; current facts belong to Core State.
- Add query rules that require active identity and branch visibility for runtime reads.
- Add recomputation/invalidation hooks from Core edits, rollback, and accepted post-write maintenance.

**Acceptance standards**

- Recall search under active identity only returns visible historical material for the active branch.
- A closed scene/turn can create Recall material with source refs to artifact/workspace/turn.
- Rollback hides or invalidates Recall material after the rollback point.
- Recall material can be recomputed or superseded without deleting audit history.

**Suggested dev slice**

Slice F: `Recall Memory Lifecycle And Branch-Aware Materialization`.

---

### P1-4. Archival Knowledge + Evolution + Retrieval/Index Modification Chain

**Current implementation evidence**

- `MinimalRetrievalIngestionService` can ingest setup/committed archival material into collections, source assets, chunks, and index jobs.
- `RetrievalMaintenanceService` can reindex story/collection/assets and backfill embeddings.
- New architecture docs place setup committed knowledge into `Archival Knowledge` and require Evolution changes to go through ingestion/reindex.
- `KnowledgeChunkRecord` lacks mandatory branch/turn/profile fields; source/chunk visibility is mostly collection/story/metadata-driven.
- There is no complete story evolution edit chain that versions archival source material, emits memory events, and triggers visibility/reindex updates for runtime.

**Why it affects story runtime**

Archival Knowledge is long-term source material. It can be edited through Story Evolution, but because it participates in retrieval/index, edits must be versioned and reindexed.

If archival edit/reindex is not governed:

- old chunks can remain searchable after an evolution edit;
- branch-specific archival changes cannot be isolated;
- Core proposals may cite archival hits whose source version is no longer current;
- runtime cannot explain which archival version informed a writer output.

**Recommended strengthening**

- Add `Story Evolution` archival edit command/receipt contract.
- Version archival source assets and chunks; preserve provenance and previous versions.
- Treat setup / activation archival seed as story-global by default.
- Treat active runtime Story Evolution archival writes as current-branch visible by default, not automatic story-global truth.
- Support explicit archival visibility scopes: current branch, selected branch set, all existing branches, and story-global. Visibility changes must be governed records, not silent metadata overwrites.
- Emit memory change events for archival edits/reindex jobs.
- Make RetrievalBroker respect archival visibility and source version metadata.
- Keep retrieval-core algorithms intact; strengthen governance, provenance, visibility, and rebuild chain around them.

**Acceptance standards**

- Editing an archival source creates a new source/chunk/index version or a traceable supersession record.
- Active runtime archival edits are hidden from other branches unless visibility scope explicitly includes them.
- Reindex jobs are linked to the evolution/edit receipt and memory events.
- Runtime search does not return superseded hidden chunks for active reads.
- A Core proposal derived from Archival hit can trace to source asset/chunk version.

**Suggested dev slice**

Slice G: `Archival Knowledge + Story Evolution Edit/Reindex Governance`.

---

### P1-5. Persistent Memory Change Event Spine, Trace, Debug, And Eval Reads

**Current implementation evidence**

- `backend/rp/models/memory_contract_registry.py` defines `MemoryChangeEvent` with identity, actor, event kind, layer, domain, source refs, dirty targets, visibility effect, and metadata.
- `backend/rp/services/memory_change_event_service.py` is explicitly an in-process event spine.
- Its store uses process-local `events_by_identity` and `event_ids`.
- `MemoryInspectionReadService` exposes current authoritative objects, projection slots, and proposals, but not a full persistent event/workspace/retrieval usage chain.
- Current story runtime debug does not yet expose future Runtime Workspace main materials as first-class trace.

**Why it affects story runtime**

Story runtime will need to answer "why did this happen?" across turns:

- why was a projection refreshed;
- which retrieval hit was used;
- which proposal applied;
- why a candidate was invalidated;
- which branch/rollback hid a material;
- what the writer packet contained;
- which permissions allowed a tool call.

In-process events cannot support this after process restart, cross-request debug, or eval replay.

**Recommended strengthening**

- Persist memory events with indexes by story/session/branch/turn/domain/layer/event kind/source ref/dirty target.
- Emit events from Core mutation, projection refresh, Runtime Workspace material changes, proposal submit/apply, Recall/Archival ingestion/reindex, branch/rollback visibility transitions, and retrieval card usage.
- Add read APIs for debug/eval: turn trace, branch trace, material trace, proposal trace, source ref trace.
- Keep event spine as trace/invalidation infrastructure, not as the truth store.
- For the `runtime boot bar`, the event spine minimum is persistent event records and focused identity queries. Rich debug pages, eval dashboards, and broad trace visualizations can follow after boot.

**Acceptance standards**

- Boot events survive process restart and can be queried by `MemoryRuntimeIdentity`.
- A full turn trace can be queried after process restart.
- Runtime debug can show memory events and workspace materials for one turn.
- Eval can fetch deterministic source refs and memory events for a generated artifact.
- Dirty target queries can drive projection/workspace/retrieval invalidation tests.

**Suggested dev slice**

Slice I: `Persistent Memory Change Event Spine + Inspection/Debug/Eval Reads`.

---

### P1-6. Deterministic Read Surface For Token/Context Orchestration

**Current implementation evidence**

- RetrievalBroker read/search inputs do not require runtime identity.
- `RetrievalRuntimeConfigService.resolve_story_config(story_id=...)` resolves story config by story id, not by immutable runtime profile snapshot.
- `WritingPacketBuilder` consumes projection sections and runtime writer hints but does not build from a pinned memory read manifest.
- Projection read has formal-store fallback behavior and mirror compatibility paths.

**Why it affects story runtime**

Context/token orchestration must be reproducible. For a given turn identity and profile snapshot, the system should know:

- which Core authoritative refs were considered;
- which Projection/View slots were read;
- which Recall/Archival queries ran;
- which Runtime Workspace materials entered packet assembly;
- which policy and token budget selected or dropped items.

Without a deterministic read surface, eval cannot replay a turn and branch/rollback cannot reason about what was visible.

**Recommended strengthening**

- Add a deterministic read manifest for packet/context assembly. The important point is a reproducible list of selected refs, omitted refs, budgets, and source versions; the implementation does not have to introduce this exact model name.
- Require identity and runtime profile snapshot on read/search/context assembly.
- Record selected refs, omitted refs with reasons, token budget decisions, and source service versions.
- Keep this as a read/trace contract, not a new orchestration layer that adds unnecessary scheduler passes.

**Acceptance standards**

- Same identity + same store state + same profile snapshot produces the same read manifest.
- Packet builder can consume manifest refs instead of ad hoc service calls.
- Trace shows token/context selection decisions without exposing private chain-of-thought.

**Suggested dev slice**

Slice H/I boundary: implement after Workspace persistence and event trace exist; do not block Slice A/B/C.

---

### P1-7. Retrieval Runtime Config Snapshot Pinning And Visibility

**Current implementation evidence**

- `RetrievalRuntimeConfigService.resolve_story_config(story_id=...)` reads the current story config / session overlay by story id.
- `RetrievalQuery` has story id, scope, filters, domains, required/optional refs, but no first-class branch/turn/profile snapshot identity.
- Query preprocessing supports filter normalization, but does not enforce active `BranchHead` visibility or profile-pinned retrieval policy by itself.

**Why it affects story runtime**

Retrieval behavior is part of the active runtime profile. If a user changes retrieval config during or after a turn, historical turn replay and eval must still use the config snapshot that was pinned at turn start.

**Recommended strengthening**

- Move runtime retrieval policy into `RuntimeProfileSnapshot`.
- Add identity/profile snapshot id to `RetrievalQuery`.
- RetrievalBroker should resolve retrieval config from the pinned snapshot, not latest story config, for runtime calls.
- Record retrieval config version/profile snapshot id in retrieval traces and Runtime Workspace cards.

**Acceptance standards**

- Changing story retrieval config after turn start does not affect that turn's retrieval behavior.
- Retrieval traces include profile snapshot id and effective search policy.
- Runtime retrieval calls without identity/profile snapshot are rejected or routed through explicit legacy/debug path.

**Suggested dev slice**

Slice A establishes identity and snapshot; Slice H consumes it for retrieval card/usage.

---

### P1-8. Permission Level And Proposal/Apply Consistency

**Current implementation evidence**

- Registry models include `MemoryPermissionDefaults`, mode defaults, and block template permission hints.
- Proposal/apply code persists proposals and receipts, applies base revision conflict checks, and can auto-apply through existing policy flow.
- There is no visible per-turn compiled permission matrix from `RuntimeProfileSnapshot` carried into proposal/apply records.
- Proposal inputs do not require worker id, phase, permission level, or runtime snapshot id.

**Why it affects story runtime**

Permission policy must be consistent across:

- user direct edit;
- worker tool reads/searches;
- worker proposal submission;
- silent/notify/manual apply decisions;
- brainstorm summary apply;
- roleplay/TRPG specialized worker permissions.

If these remain separate conventions, a worker can appear permitted at registry level but be applied by a different policy path, or vice versa.

**Recommended strengthening**

- Compile permission rules into `RuntimeProfileSnapshot`.
- Define permission levels per mode/domain/block/layer/operation/phase.
- Proposal submit should record the permission decision and required apply policy.
- Apply should verify the proposal was authorized under its snapshot and still valid under conflict rules.
- Direct user edit should bypass worker permission but still record actor/origin and trigger invalidation.

**Acceptance standards**

- Proposal/apply receipts show which snapshot and policy allowed or denied the operation.
- A disabled domain/worker cannot submit or auto-apply a proposal.
- Manual/notify/silent behavior is tested per operation/domain/mode.

**Suggested dev slice**

Slice E with Slice A/J prerequisites.

---

### P1-9. User-Visible Memory Inspection And Edit Backend Contract

**Current implementation evidence**

- Task docs confirm memory layers are not black boxes: `Core State`, `Recall Memory`, and `Archival Knowledge` should be visible to users with different edit paths.
- Current backend already has read/inspection pieces such as Core/Projection read services, block-shaped read views, memory inspection, and proposal/apply.
- Current implementation does not yet provide one stable backend contract for:
  - direct user Core fact edit under active identity;
  - Projection/View dirty marking and refresh after user edit;
  - Recall review/recompute/invalidate/supersede actions;
  - Archival Evolution edit/version/reindex flow;
  - branch/turn/profile-aware inspection across all layers.

**Why it affects story runtime**

The confirmed product behavior depends on users being able to inspect and fix memory when story output is wrong. Longform brainstorm, roleplay correction, and TRPG state correction all need this backend capability. If the backend only exposes internal or longform-specific read shapes:

- users cannot safely correct Core facts and then rewrite/continue;
- direct Core edits can leave stale Projection/View slots;
- Recall and Archival corrections may bypass retrieval/index governance;
- branch/rollback cannot explain which visible memory the user edited.

**Recommended strengthening**

- Define user-facing memory operation contracts separately from UI implementation:
  - `Core State` direct edit/apply command;
  - Projection/View refresh or stale marking after Core edit;
  - Recall review/recompute/invalidate/supersede commands;
  - Archival Evolution edit/version/reindex command;
  - branch/turn/profile-aware inspection query.
- Reuse proposal/apply, event spine, visibility resolver, and retrieval/index maintenance where applicable.
- Do not build UI beauty work in memory dev; only provide stable backend APIs/DTOs and tests so UI can safely expose them later.

**Acceptance standards**

- User direct Core edit under active identity records actor/origin/source refs, bumps revision, emits memory event, and refreshes or invalidates affected Projection/View slots.
- Recall and Archival user actions are traceable and branch-aware.
- Inspection API can show visible Core/Projection/Recall/Archival/Workspace material for the active branch without exposing unrelated branch material.
- The same backend contracts can be used by setup draft manual modification, longform runtime, roleplay, and TRPG.

**Suggested dev slice**

Slice K: `User-Visible Memory Inspection/Edit Backend Contracts`.

---

### P1-10. Multi-Mode Domain/Block/Worker Coverage Beyond Longform

**Current implementation evidence**

- Core operation support and legacy patch conversion are longform-oriented.
- Bootstrap registry contains longform/roleplay/TRPG mode defaults, but runtime graph and packet builder are still longform-first.
- Task docs require all-mode design and warn against coding everything as longform behavior.

**Why it affects story runtime**

If memory dev only strengthens longform paths, roleplay and TRPG will later discover the same blockers:

- roleplay needs reactive state, relations, knowledge boundaries, inventory, active scene, and character memory;
- TRPG needs rule state, mechanics state, inventory/resources, adjudication history, and audit-friendly rule outcomes;
- longform needs continuity, threads, foreshadow, synopsis, and chapter/scene structure.

All modes should use the same memory layers and tool contracts, with profile/config differences.

**Recommended strengthening**

- Treat domain/block/worker as registry entries and profile activations, not longform enum branches.
- Keep operation catalog generic: create/update/append/replace/delete/retire/merge/supersede/refresh/invalidate where allowed by block contract.
- Add tests with at least one roleplay-specific and one TRPG-specific domain/block descriptor going through read/proposal/refresh policy without editing longform allowlists.

**Acceptance standards**

- A roleplay/TRPG domain can be registered and read/searched/proposed/refreshed through the same memory tool contracts.
- Longform compatibility paths remain adapters, not the architecture baseline.

**Suggested dev slice**

Slice J and Slice D/E together.

## 4. Suggested Memory Dev Session Slices

### Slice A. Runtime Identity Persistence And Propagation

| Field | Content |
| --- | --- |
| Input | Current `MemoryRuntimeIdentity` model, story session records, task docs confirming `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` |
| Output | `BranchHead`, `StoryTurn`, `RuntimeProfileSnapshot` persistent records; identity allocator/resolver; identity fields on runtime memory DTOs/records where needed |
| Acceptance | Runtime memory ops resolve full identity before store access; missing identity rejected on story-runtime paths; legacy session-only path gets explicit compatibility/default branch/snapshot |
| Impact | rp story store, memory DTOs, proposal records, projection refresh request, retrieval query, workspace materials, event records |

### Slice B. Runtime Workspace Persistent Turn Material Store

| Field | Content |
| --- | --- |
| Input | Existing `RuntimeWorkspaceMaterial` DTO/service skeleton |
| Output | Durable material records/repository/service; lifecycle transitions; material query APIs; event emission |
| Acceptance | Materials survive service restart; isolated by branch/turn; lifecycle events persisted; retrieval card/usage/candidate examples covered by tests |
| Impact | Runtime Workspace service/model/store, debug read surfaces, event spine |

### Slice C. Branch/Rollback Visibility Resolver And Lineage Fields

| Field | Content |
| --- | --- |
| Input | Branch/rollback task decisions, identity records from Slice A |
| Output | Visibility resolver; lineage/visibility fields and filters for Core/Projection/Workspace/Recall/Archival/proposal/event/retrieval |
| Acceptance | Active branch reads exclude other branch/future-turn material; rollback hides post-target-turn material without physical deletion |
| Impact | Core read/write, projection read/refresh, Runtime Workspace, Recall/Archival retrieval metadata, RetrievalBroker, memory inspection |

### Slice D. Core/Projection Contract Hardening And Worker-First Projection Refresh

| Field | Content |
| --- | --- |
| Input | Formal Core State store, projection refresh service, longform bundle adapter |
| Output | Mandatory identity/source refs for projection refresh; worker-first refresh request; stale-base checks; projection provenance |
| Acceptance | Projection refresh without identity fails on runtime path; projection slots point to source authoritative revisions; new domain projection slot can be added by registry/config |
| Impact | ProjectionRefreshService, ProjectionReadService, CoreStateDualWriteService, legacy adapter, tests |

### Slice E. Worker-Facing Memory Tools And Permission Integration

| Field | Content |
| --- | --- |
| Input | Memory CRUD DTOs, proposal workflow/apply services, registry permission defaults |
| Output | WorkerContext-bound tool contracts; permission guard; proposal/apply permission receipt metadata |
| Acceptance | Unauthorized worker/domain/layer ops rejected; proposal records include identity/worker/phase/permission decision; same API works for longform/roleplay/TRPG descriptors |
| Impact | Memory tool provider, RetrievalBroker facade, proposal workflow, registry/profile snapshot |

### Slice F. Recall Memory Lifecycle And Branch-Aware Materialization

| Field | Content |
| --- | --- |
| Input | Existing Recall ingestion services and retrieval store |
| Output | Recall lifecycle model; branch/turn/source refs; invalidation/recompute/supersede rules; broker visibility enforcement |
| Acceptance | Recall search is branch-aware; rollback hides later Recall; closed scene/turn creates queryable historical material with source refs |
| Impact | Recall ingestion, retrieval metadata/query filters, memory events, inspection |

### Slice G. Archival Knowledge + Story Evolution Edit/Reindex Governance

| Field | Content |
| --- | --- |
| Input | Minimal archival ingestion, retrieval maintenance/reindex services |
| Output | Story Evolution archival edit receipt; source versioning/supersession; reindex event linkage; visibility metadata |
| Acceptance | Archival edits create versioned source/chunk/index chain; superseded chunks hidden from runtime search; proposals can trace archival source version |
| Impact | Archival ingestion, retrieval maintenance, source/chunk metadata, event spine |

### Slice H. Retrieval Card / Usage / Promotion Contract

| Field | Content |
| --- | --- |
| Input | RetrievalBroker, Runtime Workspace material model, writer packet/execution services |
| Output | Retrieval results materialized as Workspace cards; expand/miss/usage records; post-write source refs and promotion contract. Boot minimum is card -> optional expansion -> usage -> post-write source refs. |
| Acceptance | Used retrieval cards are traceable from query to writer usage to proposal/promotion; unused cards expire; misses are recorded; retrieval hits cannot directly mutate Core truth |
| Impact | RetrievalBroker, Runtime Workspace, writer usage hook, post-write maintenance interfaces |

### Slice I. Persistent Memory Change Event Spine + Inspection/Debug/Eval Reads

| Field | Content |
| --- | --- |
| Input | Existing `MemoryChangeEvent` DTO and in-process service |
| Output | Persistent event records/repository; event emission integration; trace/debug/eval query APIs. Boot minimum is persistent event records for identity, source refs, dirty targets, visibility effects, and mutation/material lifecycle transitions. |
| Acceptance | Full turn memory trace survives process restart; boot can query focused events by identity; later debug can expand to rich events/materials/proposals/retrieval usage views |
| Impact | Event service/store, MemoryInspectionReadService, debug endpoints, eval harness |

### Slice J. Registry/Config Driven Domain-Block-Worker Management

| Field | Content |
| --- | --- |
| Input | Bootstrap `MemoryContractRegistryService`, mode/domain task docs |
| Output | Persistent/config-backed registry; worker descriptors; block templates; mode/profile overlays; snapshot compiler |
| Acceptance | Add/disable/migrate a domain/block/worker through registry/config without editing story runtime services; snapshot records effective config |
| Impact | Registry service/models, RuntimeProfileSnapshot compiler, worker catalog integration, permission profile |

### Slice K. User-Visible Memory Inspection/Edit Backend Contracts

| Field | Content |
| --- | --- |
| Input | Core/Projection read services, block-shaped read views, memory inspection, proposal/apply, task docs confirming user-visible memory layers |
| Output | Backend contracts for Core direct edit, Recall review/recompute/invalidate/supersede, Archival Evolution edit/version/reindex, and branch-aware inspection. Core direct edit must call the shared governed mutation kernel, not a raw user-only write path. |
| Acceptance | User Core edit emits event and refreshes/invalidates Projection/View through the shared mutation path; Recall/Archival user actions are traceable and branch-aware; setup/runtime use the same backend contracts |
| Impact | Memory inspection/read services, Core mutation path, Projection refresh, Recall/Archival lifecycle, event spine, future UI endpoints |

## 5. Recommended Execution Order

### 5.1 Runtime Boot Bar Order

The first execution target is the `runtime boot bar`, not the full foundation.

1. Slice A: identity persistence and propagation.
2. Slice B: persistent Runtime Workspace.
3. Slice I-min: persistent event record foundation for identity/source refs/dirty targets/visibility effects/material lifecycle.
4. Slice J-min: minimal default registry/profile compiler so `RuntimeProfileSnapshot` is real and pinned before reads/writes.
5. Slice C: branch/rollback visibility resolver and lineage fields.
6. Slice D: Core/Projection hardening plus deterministic read manifest fields for writer/scheduler packets.
7. Slice H-min: retrieval card -> optional expansion -> writer usage -> post-write source refs; no direct retrieval-to-Core writes.
8. Slice E-min: internal worker-facing memory service contracts, permission guard, and proposal/apply enforcement needed by boot workers.
9. P1-2/K-min: shared Core mutation kernel and Core direct edit path if direct edit is exposed during boot.

This order puts minimal H before the first runtime slice depends on writer-side retrieval. It also ensures the event spine exists early enough that later branch visibility, direct edit, retrieval usage, and proposal/apply operations do not need to invent separate trace paths.

### 5.2 Full Runtime Foundation Order

After boot, complete the remaining full-foundation work:

1. Finish Slice E: complete worker-facing tool DTOs, all-mode permissions, and apply receipts.
2. Finish Slice H: richer retrieval usage lifecycle, worker retrieval usage, expiration, promotion trace, and debug surfaces.
3. Finish Slice I: debug/eval/inspection query surfaces over events/materials/proposals/retrieval usage.
4. Slice F: Recall lifecycle.
5. Slice G: Archival Evolution/reindex governance.
6. Slice K: full user-visible memory inspection/edit backend contracts.
7. Finish Slice J: registry/config driven domain-block-worker management for longform, roleplay, and TRPG expansion.

Reasoning: boot needs enough identity, material, visibility, trace, read manifest, retrieval usage, and governed writes to avoid architectural dead ends. The full foundation then broadens the same contracts into user-visible memory management, all-mode Recall/Archival governance, and dynamic domain/block/worker expansion.

## 6. Explicit Non-Goals For This Memory Dev Proposal

Memory dev session should not spend this proposal on:

- UI beautification or full memory management UI.
- Story runtime scheduler / worker orchestration implementation.
- Writer prompt redesign beyond the memory-facing usage hook and source refs.
- Rewriting retrieval-core algorithms, retrievers, embedding strategy, or vector search engine.
- Full roleplay/TRPG active runtime implementation.
- Full branch UI, branch merge UI, or physical purge.
- Making Runtime Workspace into story truth.
- Letting workers directly mutate Core/Recall/Archival stores outside governed tool/proposal/ingestion paths.
- Replacing setup frozen contracts, setup workspace, readiness, typed SSE, or setup review/commit flows.

## 7. Implementation Evidence Coverage Matrix

This section exists so the memory dev session can see exactly which current implementation anchors drove the proposal.

| Area | Files checked | Evidence used in this proposal |
| --- | --- | --- |
| Core State reads | `backend/rp/services/core_state_read_service.py` | Current read surface is useful for authoritative state, but runtime inputs are still session/ref oriented rather than mandatory `MemoryRuntimeIdentity` oriented. It should become part of deterministic read manifest, not a bypass around identity/visibility. |
| Core State formal store | `backend/models/rp_core_state_store.py`, `backend/rp/services/core_state_store_repository.py`, `backend/rp/services/core_state_dual_write_service.py` | Formal authoritative/projection store exists, with revisions and projection slots. Current dimensions are still story/session and projection chapter workspace; branch/turn/profile identity and visibility are not first-class. |
| Projection/View | `backend/rp/services/projection_state_service.py`, `backend/rp/services/projection_refresh_service.py`, `backend/rp/services/projection_read_service.py` | Projection is partly formal-store backed, but compatibility mirror/fallback and `ChapterWorkspace.builder_snapshot_json` remain important. `refresh_from_bundle` is still bundle-first and `ProjectionRefreshRequest.identity` can be absent. |
| proposal/apply | `backend/rp/services/proposal_workflow_service.py`, `backend/rp/services/proposal_apply_service.py`, `backend/models/rp_memory_store.py` | Proposal persistence/apply and base revision checks are real strengths. Missing pieces are branch/turn/profile identity, worker/phase/permission receipt metadata, and unified handling with direct edit / brainstorm apply. |
| Runtime Workspace | `backend/rp/models/runtime_workspace_material.py`, `backend/rp/services/runtime_workspace_material_service.py` | Material DTO is already the right typed envelope for retrieval cards, usage, candidates, packet refs, and traces. Service/store is process-local and not yet durable or integrated into writer/post-write/debug/rollback. |
| RetrievalBroker | `backend/rp/services/retrieval_broker.py`, `backend/rp/retrieval/query_preprocessor.py`, `backend/rp/retrieval/keyword_retriever.py`, `backend/rp/retrieval/semantic_retriever.py`, `backend/rp/services/retrieval_runtime_config_service.py` | Broker/search routes exist, filter normalization includes branch-related keys, but `RetrievalQuery` lacks mandatory identity and retrieval config resolves latest story config rather than pinned `RuntimeProfileSnapshot`. |
| Recall Memory | `backend/rp/services/recall_*_ingestion_service.py`, retrieval store models | Current ingestion covers useful longform historical material. It is still session/chapter/workspace oriented and lacks all-mode turn/branch/profile lifecycle, visibility, recompute, and Runtime Workspace promotion linkage. |
| Archival Knowledge | `backend/rp/services/minimal_retrieval_ingestion_service.py`, `backend/rp/services/retrieval_maintenance_service.py`, `backend/models/rp_retrieval_store.py` | Setup/commit ingestion, collection/chunk/index/reindex exist. Missing is Story Evolution edit/version/reindex governance, branch visibility, event linkage, and source version trace into proposals. |
| Event spine | `backend/rp/models/memory_contract_registry.py`, `backend/rp/services/memory_change_event_service.py` | `MemoryChangeEvent` model has the right identity/source/dirty-target shape, but service is in-process. Persistent trace/debug/eval/invalidation reads are not yet available. |
| Registry/config | `backend/rp/models/memory_contract_registry.py`, `backend/rp/services/memory_contract_registry.py` | Bootstrap domain/block/mode/permission defaults exist and are useful. It is still static/read-only; RuntimeProfileSnapshot compiler and persistent/config-driven domain/block/worker catalog are missing. |
| Story runtime identity | `backend/models/rp_story_store.py`, `backend/rp/graphs/story_graph_runner.py`, task docs | Story store has session/chapter/artifact/discussion/consumer records, but not first-class `BranchHead`, `StoryTurn`, or `RuntimeProfileSnapshot`. Graph thread id is session-based and cannot by itself provide memory branch/rollback semantics. |
| Writer/post-write | `backend/rp/services/writing_packet_builder.py`, `backend/rp/services/writing_worker_execution_service.py`, `backend/rp/services/longform_regression_service.py` | Writer path is longform-oriented and does not yet write retrieval cards, usage records, Runtime Workspace refs, or evidence-driven post-write promotion. Longform regression still uses legacy bundle/patch style. |

## 8. Main Session Follow-Up

No additional user-level architecture decision is required before memory dev can start. Existing task docs already confirm the important principles:

- identity is `StorySession + active BranchHead + Turn + RuntimeProfileSnapshot`;
- `Turn`, `BranchHead`, and `RuntimeProfileSnapshot` should become first-class;
- `Runtime Workspace` must become persistent;
- branch/rollback should use visibility/tombstone semantics first, not physical delete;
- all modes should be registry/config driven, not hardcoded as longform.

Memory dev should treat Slice A through Slice K as the complete memory-layer target for supporting story runtime. Individual commits/batches can be split for safety, but the target is not "finish A+B and stop".

Recommended batching:

1. Boot batch 1: Slice A + Slice B + Slice I-min, with Slice J-min if schema churn is lower when snapshots and profile compiler land together.
2. Boot batch 2: Slice C + Slice D, including deterministic read manifest fields.
3. Boot batch 3: Slice H-min + Slice E-min, so writer-side retrieval and worker/proposal governance are usable without direct retrieval-to-Core writes.
4. Boot batch 4 if direct Core edit is exposed in the first runtime UI/API: P1-2/K-min shared mutation kernel and Core direct edit backend contract.
5. Foundation batch 5: finish Slice E/H/I.
6. Foundation batch 6: Slice F + Slice G + Slice K.
7. Foundation batch 7: finish Slice J before broad roleplay/TRPG runtime implementation relies on dynamic domain/block/worker activation.

These are execution-order decisions. They do not reduce the complete requirement: P0 and P1 together are still the full runtime foundation bar, while the boot batches define the narrower minimum needed for the first story runtime implementation.

## 9. Letta Git Memory Reference Boundary

The Letta source under `docs/research/letta-main` was reviewed because Letta has a Git-like memory history mechanism that looks close to the story runtime branch/rollback requirement.

The conclusion is:

```text
Letta has strong reference value, but it should not replace the RP memory model.
Copy the architectural patterns, not the implementation as-is.
```

Useful Letta implementation evidence:

- `letta/services/block_manager_git.py` switches a block manager into git-backed mode with the `git-memory-enabled` tag.
- In git-backed mode, block writes go to git/MemFS first, then PostgreSQL is updated as the fast read cache.
- `letta/services/memory_repo/memfs_client_base.py` serializes memory blocks as markdown files with frontmatter, supports reads at a git ref, and commits create/update/delete operations.
- `letta/services/memory_repo/git_operations.py` stores a per-agent repo, reads files by `HEAD` / branch / commit ref, creates commits with parent SHA, and serializes commits with a lock.
- `letta/server/rest_api/routers/v1/git_http.py` supports git smart HTTP push/clone through a memfs service and syncs pushed markdown memory back into PostgreSQL cache.
- `letta/services/block_manager.py` + `letta/orm/block_history.py` also provide non-git block checkpoint / undo / redo. That path is linear: creating a new checkpoint after undo truncates future checkpoints.

Patterns RP should copy:

- **Source of truth plus read cache**: branch/revision history must be authoritative; Projection/View, packet inputs, and retrieval indexes should be rebuildable read surfaces.
- **Commit-style audit unit**: every memory mutation should create a durable event/revision with parent/base revision, actor, source refs, changed refs, and reason.
- **Inspectable memory projection**: memory can have stable paths / structured surfaces for user inspection, debug, export, and possible future import.
- **Explicit sync after visible edits**: user/worker-visible edits must trigger deterministic cache/projection/retrieval-index sync rather than relying on hidden mutation.
- **Isolated edit workspaces**: concurrent worker edits should happen as candidates/proposals in Runtime Workspace, then merge/apply through governance.

Why RP should not copy Letta wholesale:

- Letta versions one agent's memory block file tree. RP needs `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` as the runtime identity.
- Letta's git memory does not coordinate Core State, Projection/View, Runtime Workspace, Recall Memory, Archival Knowledge, proposal/apply, retrieval cards, packet/window metadata, and retrieval/index visibility as one branch-aware product contract.
- Letta's agent self-edit model is too permissive for RP. RP must preserve user edit priority, worker permission levels, proposal/apply governance, and mode-specific worker ownership.
- Letta's git smart HTTP / MemFS path adds operational cost and external service assumptions. It is too heavy as the first required RP backend dependency.
- Letta's linear block undo/redo matches RP rollback only in the simple "rewind active line" sense. RP branch switching/deletion needs app-level branch visibility and branch-scoped material isolation.

Recommended implementation stance:

1. Keep LangGraph as the workflow checkpoint/fork substrate.
2. Keep RP application storage as the product truth for Core State, Runtime Workspace, Recall Memory, Archival Knowledge, proposal/apply, retrieval/index visibility, and events.
3. Treat `BranchHead + Turn + MemoryChangeEvent + revision/provenance records` as the RP equivalent of git commits.
4. Use copy-on-write / visibility resolution instead of cloning whole memory repos per branch.
5. Consider a future optional memory export/import or file-projection surface inspired by Letta, but only after branch-aware identity, Runtime Workspace persistence, and layer-wide visibility are implemented.
