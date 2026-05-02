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

### Dolt and lakeFS

Dolt and lakeFS are stronger references for data branch semantics:

- Dolt exposes Git-like branches over SQL data. Each branch behaves like an isolated database view.
- lakeFS applies Git-like versioning to data lakes. Branch creation is metadata-only / zero-copy; changed objects create new versions.

Implication for RP runtime:

- Branch creation should not copy all memory. It should create a new branch head from an existing turn and share unchanged history.
- Storage grows with divergent writes and materializations, not with every branch creation.
- Branch reads must resolve active branch + shared ancestors, then hide deleted/invalid branches.
- Branch delete should tombstone or purge branch-only data; product semantics can say the deleted branch is gone.

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
   - Branch delete can tombstone immediately and optionally physically purge embeddings asynchronously.

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
