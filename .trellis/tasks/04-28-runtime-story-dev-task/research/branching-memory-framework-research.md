# Branching memory framework research

## Question

Story runtime wants Git-like rollback and branch behavior:

- rollback: current mainline rewinds to an earlier turn; later turns become invalid for the current line.
- branch: multiple futures can coexist from the same earlier turn; branches can be switched or deleted.
- branch memory and context must be isolated.

## Findings

### LangGraph

Official docs confirm LangGraph has persistent checkpoints, time travel, replay, and fork:

- Persistence saves graph state as checkpoints inside threads.
- Time travel can replay from old checkpoints.
- Fork can create an alternative path from a checkpoint, while original history remains intact.

Implication for RP runtime:

- LangGraph can support graph-level checkpoint / fork mechanics.
- LangGraph does not automatically make external stores branch-aware.
- RP memory, text artifacts, retrieval materialization, packet/window metadata, and vector-search visibility must be branch-scoped by our application layer.
- Graph state should store refs and head pointers, not huge memory snapshots.

Sources:

- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/use-time-travel

### Letta

Letta has a memory hierarchy:

- memory blocks: persistent in-context blocks, always visible to the agent.
- archival memory: searchable long-term storage queried by tools.
- context hierarchy: decides whether information belongs in memory blocks, files, archival memory, or external RAG.

Local source review under `docs/research/letta-main` adds more precise implementation detail:

- `letta/orm/block.py`: `Block` is a section of LLM context. It stores `value`, `label`, `description`, `limit`, `read_only`, `hidden`, `version`, and `current_history_entry_id`.
- `letta/orm/block_history.py`: `BlockHistory` stores block snapshots with `sequence_number`, copied block fields, and actor info.
- `letta/services/block_manager.py`: checkpoint / undo / redo is linear. Creating a new checkpoint after undo truncates future checkpoints.
- `letta/functions/function_sets/base.py` and `letta/services/tool_executor/core_tool_executor.py`: core memory, archival memory, and conversation search are exposed as tools. The agent searches or edits memory through tools; the storage layers do not automatically promote archival hits into core memory.
- `letta/agents/letta_agent_v2.py` and `letta/services/summarizer/summarizer.py`: context-window pressure is handled by retaining the system message plus recent messages and summarizing / evicting older messages.

Letta also has MemFS / git memory, a git-backed context repository:

- memory is organized as markdown files with frontmatter.
- important files can be pinned to context, while the full tree supports progressive disclosure.
- memory edits are committed and pushed to save.
- memory subagents use git worktrees for parallel memory edits.
- `letta/services/block_manager_git.py`: when `git-memory-enabled` is set, writes go to git first and PostgreSQL is the read cache.
- `letta/server/rest_api/routers/v1/git_http.py`: a successful git push scans markdown files and syncs them into PostgreSQL block cache.
- `letta/services/memory_repo/git_operations.py`: git refs can be read by commit / branch / HEAD, and commits are serialized with a lock; the main product path still centers on block file history rather than a full story-branch model.

Implication for RP runtime:

- Letta is useful as a design reference for block-based memory, tool-managed memory, progressive disclosure, and source-of-truth plus read-cache separation.
- Letta confirms that "agent manages memory through tools" is a valid architecture. In RP runtime, the equivalent actor is the block-owner worker.
- Letta's Git memory is a useful reference for editable memory text, commit history, and cache sync, but it should not be transplanted wholesale. RP memory is structured Core State + Recall / Archival + Runtime Workspace, and needs story branch isolation, user edit priority, worker permissions, and mode-specific workflow semantics.
- Letta's linear block checkpoint behavior aligns with the current RP rollback direction: rollback rewinds the active line and future content on that line becomes invalid unless preserved as a branch.

Sources:

- https://docs.letta.com/guides/core-concepts/memory/memory-blocks/
- https://docs.letta.com/guides/core-concepts/memory/archival-memory
- https://docs.letta.com/guides/core-concepts/memory/context-hierarchy/
- https://docs.letta.com/letta-code/memory
- https://www.letta.com/blog/context-repositories

### Letta deep-dive conclusion for RP memory rollback

Additional local-source review was performed against:

- `docs/research/letta-main/letta/services/block_manager_git.py`
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py`
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py`
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py`
- `docs/research/letta-main/letta/services/block_manager.py`
- `docs/research/letta-main/letta/orm/block_history.py`

The concrete implementation pattern is:

1. `GitEnabledBlockManager` switches behavior by the `git-memory-enabled` agent tag.
2. When enabled, block writes go to the git-backed memory repo first.
3. PostgreSQL is then updated as the fast read cache.
4. Memory blocks are serialized as markdown files with frontmatter.
5. Historical reads can read a block at a commit SHA, and commit history is first-class.
6. Git HTTP push can update memory files and then sync them back into PostgreSQL block cache.
7. Normal block checkpoint/undo/redo in `BlockHistory` is linear: if a new checkpoint is created after undo, future checkpoints are truncated.

This gives RP several concrete patterns worth copying:

- **source-of-truth + cache split**: authoritative memory history should not be an accidental JSON mirror. If a branch/revision store is authoritative, read caches/projections must be rebuildable.
- **file/tree projection for human and agent editing**: memory can be projected into stable, inspectable paths instead of opaque database blobs. This is useful for Core/Archival inspection and for future debug/export tooling.
- **commit object as audit unit**: every memory mutation should produce a durable revision/event with parent pointer, actor, changed refs, message/reason, and source refs.
- **cache sync after external edit**: if users or workers edit memory through a visible/editable surface, backend cache/projection/index sync must be explicit and testable.
- **worktree/concurrent edit lesson**: isolated worker edits can happen in separate workspaces, but merge/apply must be governed. For RP this maps to worker candidates/proposals, not direct commits into truth.

However, Letta should not be copied wholesale as the RP branch/rollback implementation:

- Letta's git memory versioning is centered on one agent's memory block file tree, not on `StorySession + BranchHead + Turn + RuntimeProfileSnapshot`.
- Letta git repo tracks editable memory files; RP must coordinate Core State, Projection/View, Runtime Workspace, Recall, Archival, proposal/apply, retrieval cards, packet/window metadata, and derived retrieval/index visibility.
- Letta's product path mostly gives block commit history and point-in-time reads. It does not directly solve story branch isolation where two futures can be switched/deleted and all branch-specific temporary materials remain isolated.
- Letta's git smart HTTP / memfs path adds operational complexity. Official docs note local MemFS is API-level only and full git clone/push flow needs a sidecar git HTTP transport; this is too heavy to make the first RP memory backend depend on.
- Letta gives agents broad memory self-edit ability. RP must preserve user edit priority, worker permission levels, proposal/apply governance, and mode-specific worker ownership.

Recommended RP position:

1. **Do not replace the planned RP branch-aware database model with Letta MemFS.**
2. **Adopt Letta's architectural lessons inside our own storage model.**
3. Treat `BranchHead + Turn + MemoryChangeEvent + revision/provenance records` as the RP equivalent of git commits.
4. Treat `Projection/View`, inspection APIs, and optional future export files as the RP equivalent of Letta's memory filesystem projection.
5. Use copy-on-write / visibility resolver for branch reads rather than cloning full memory repos per branch.
6. Keep LangGraph as the workflow checkpoint/fork substrate, but never rely on it or Letta alone for memory rollback semantics.
7. Consider a future optional "memory repo export/import" or "archival source file projection" inspired by Letta, but only after Core/Projection/Workspace/Recall/Archival branch identity is implemented.

Therefore, the best design is hybrid:

- **LangGraph**: graph execution checkpoints, replay, fork primitive.
- **RP application storage**: product truth, branch visibility, turn identity, permission, proposal/apply, retrieval/index visibility.
- **Letta-inspired patterns**: versioned memory assets, source-of-truth/cache separation, path-like memory projection, commit-style audit records, and isolated worker edit workspaces.

### Dolt and lakeFS

Dolt and lakeFS are stronger references for data branch semantics:

- Dolt exposes Git-like branches over SQL data. Each branch behaves like an isolated database view.
- lakeFS applies Git-like versioning to data lakes. Branch creation is metadata-only / zero-copy; changed objects create new versions.

Implication for RP runtime:

- Branch creation should not copy all memory. It should create a new branch head from an existing turn and share unchanged history.
- Storage grows with divergent writes and materializations, not with every branch creation.
- Branch reads must resolve active branch + shared ancestors, then hide deleted/invalid branches.
- Branch delete can tombstone / hide branch-only data in the first version, but final capability must physically purge branch-only data.
- Physical delete must only target records created after the fork for that branch, such as Runtime Workspace materials, worker candidates, pending records, branch-specific Core / Projection / Recall materializations, packet/window metadata, and derived retrieval records. It must not delete shared pre-fork settled memory or story-global Archival Knowledge.

Sources:

- https://docs.dolthub.com/sql-reference/version-control/branches
- https://docs.lakefs.io/v1.70/
- https://docs.lakefs.io/dev/understand/faq/

## Recommended RP architecture direction

1. Treat rollback and branch as different product operations.

   - Rollback is destructive for the active line: later turns become invalid for that line.
   - Branch preserves another future: both paths can be switched, continued, or deleted.

2. Use branch-scoped reads, not full memory copies.

   - Every text / memory / retrieval / packet-window record should be attributable to a turn and branch.
   - Reads must always include the active branch lineage.
   - Shared setup / Archival Knowledge can remain branch-independent unless edited by branch-specific runtime operations.

3. Use copy-on-write semantics.

   - Creating a branch is metadata-only.
   - Only new branch-specific writes create new rows / revisions / materialized retrieval records when needed.
   - Current view / projection block views should resolve from the branch head and shared ancestors.

4. Treat retrieval index as derived search infrastructure, not truth.

   - Core State, projection block views, Recall Memory, Archival Knowledge documents, accepted prose, and summaries are the content that version / branch semantics should protect.
   - Chunks, embeddings, keyword indexes, HNSW indexes, top hits, and retrieval caches are derived from content.
   - Rebuilding or changing the retrieval index must not change story truth.
   - Branch creation should not copy the whole vector store. Search should filter by active branch lineage and visible records, then reindex asynchronously when content changes.

5. Keep retrieval branch-aware.

   - Recall Memory records need branch/turn visibility metadata.
   - Search must filter by active branch lineage and exclude invalid / deleted branch records.
   - Branch delete can tombstone immediately in the first version, but the final design must physically purge branch-only derived records, including embeddings / chunks / caches that exist only for the deleted branch.

6. Do not rely on LangGraph alone.

   - LangGraph handles workflow state checkpoints and forks.
   - RP memory isolation must be implemented in Core State / Recall / Archival / Runtime Workspace storage and read services.

7. Govern retrieval hits before they enter Core State.

   - A Recall / Archival hit can enter the writer packet as cited reference material.
   - It should not automatically become Core State.
   - A block-owner worker must decide whether the hit is now required current truth, then submit the corresponding proposal / apply path according to permission level and user-review policy.

8. Keep writer-side retrieval bounded and card-based.

   - The writer should be allowed to judge that current context is insufficient and call a controlled retrieval tool.
   - Retrieval should return structured cards, summaries, excerpts, and refs, not a free-form explanation that depends on the writer's hidden prompt context.
   - Runtime Workspace should hold card ids, hit refs, expanded content, usage records, missed queries, and trace for the current turn.
   - The writer may request expansion of already-returned cards, but the system should preserve the mapping from short card ids to the real hit / chunk / provenance ids.
   - If retrieval misses, the writer may retry within a bounded attempt limit and then either proceed with a knowledge gap or stop depending on mode and policy.

## Current project conclusion

For this project, LangGraph can satisfy the **workflow shell** part of rollback / branch, but it cannot by itself satisfy the full **product semantics** we want.

More concretely:

- **LangGraph can provide**:
  - checkpoint persistence
  - replay from older checkpoints
  - fork from older checkpoints
  - subgraph-level checkpointing when explicitly enabled

- **LangGraph cannot automatically provide**:
  - Core State / Recall / Archival / Runtime Workspace synchronized rollback
  - branch-aware retrieval visibility
  - branch-scoped proposal / apply / projection refresh governance
  - product-level “rollback invalidates later turns on the current line” semantics
  - physical purge of branch-only materials

Therefore the recommended project strategy stays:

1. use LangGraph as the graph execution and checkpoint/fork substrate;
2. make `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` first-class persistent runtime identity;
3. keep external memory/text/workspace state branch-aware in application storage;
4. treat LangGraph rollback/fork as a lower-layer primitive, not as the whole product feature.
