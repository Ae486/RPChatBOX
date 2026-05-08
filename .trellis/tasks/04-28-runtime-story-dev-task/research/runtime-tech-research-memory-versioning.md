# Research: runtime tech research memory versioning

- Query: 对 story runtime 的 memory/versioning/branch visibility 底座做技术调研，评估 Letta、Dolt、lakeFS、Git memory、Nocturne Memory 对当前项目的价值，并回答哪些可直接采用、哪些只适合借思想、哪些现在引入过重。
- Scope: mixed
- Date: 2026-05-07

## Findings

### 结论先行

按当前项目的约束，最值得直接吸收的不是某个现成产品，而是三类模式：

1. Dolt / lakeFS 的 `metadata-first + copy-on-write + branch-local visibility`。
2. Letta / Git memory 的 `source-of-truth + rebuildable cache/projection + commit-style audit trail`。
3. Nocturne 的 `before/after 审查快照 + 人工确认回滚`，但仅适合做 inspection / review 面，不适合当 story runtime 真值底座。

对当前 RP story runtime，最佳路径仍然是：

- 真值继续放在 RP 自己的 `Core State / Projection / Runtime Workspace / Recall / Archival` 分层里。
- `BranchHead + Turn + RuntimeProfileSnapshot + MemoryChangeEvent` 成为 RP 自己的“commit spine”。
- branch 采用 metadata-first / lineage-first，不复制全量 memory。
- retrieval/index 继续视为 derived cache，而不是 truth。

### 分级

#### 可直接采用

1. `Dolt / lakeFS` 的 metadata-first branch 创建
   - 对 RP 最直接有用的是“分支创建不复制全量数据，只新建 branch head 指针，后续写入按分歧增长”。
   - 这与当前规格完全同向：`.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:93-98` 已明确要求 branch creation metadata-first、shared pre-fork material 通过 lineage 可见，而不是 clone 全库。

2. `Dolt` 的 branch-as-isolated-head 语义
   - 对 RP 最有帮助的不是 SQL 引擎本身，而是“每个 branch head 都是一个独立可见视图”的心智模型。
   - 这正对应 RP 现在需要的 `active_branch_head_id + visible_branch_head_ids + turn_cutoff_by_branch` 读域模型，见 `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:23-33`。

3. `Letta` 的 memory ownership split
   - Letta 的 memory blocks / archival / external RAG 分层，可以直接拿来支撑 RP 现在已经冻结的 Memory OS 分层认知：当前 truth、当前 projection、历史 recall、源资料 archival、当前 turn scratch。
   - 这与 `.trellis/spec/backend/rp-memory-temporal-materialization.md:82-103` 基本一致，说明这部分不是“新设计”，而是可以放心沿用的外部验证。

4. `Letta BlockHistory` 的“同一 active line 上 rollback 后再写就截断 future”
   - 这适合作为 RP “rollback 不是保留两条未来，而是让当前线后续 turn 失效”的局部语义参考。
   - 本地代码已明确是严格线性 checkpoint：`docs/research/letta-main/letta/services/block_manager.py:842-876,952-1041`。
   - 这与现有 research 里对 rollback vs branch 的区分一致：`.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md:150-165`。

5. `Git memory` 的 source-of-truth + cache split
   - 这不是说要上 Git backend，而是说“真值 revision store”和“读缓存 / 投影视图 / 检索索引”必须分开。
   - Letta GitEnabledBlockManager 已把这个模式做得很清楚：先写 git，再同步 PostgreSQL cache，见 `docs/research/letta-main/letta/services/block_manager_git.py:4-5,30-36,216-242,564-595`。
   - 对 RP 最直接的映射是：Core/Recall/Archival/Workspace 的 revision/provenance 才是 truth；Projection、Block view、retrieval chunk / embedding / observability 都应可重建。

#### 只参考

1. `Letta` 的 tool-managed memory
   - 值得借的是“memory 不是模型直接乱写数据库，而是通过受控工具面写入”。
   - 但 RP 不能照抄 agent self-edit，因为 RP 还有 user priority、worker permission、proposal/apply、mode/domain policy。
   - 当前项目已经把这层约束写死为 governed path，见 `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md:7-17,63-72`。

2. `Git memory` 的 file/tree projection
   - Markdown + frontmatter + stable path projection 很适合 inspection/export/debug，不适合直接当 RP Core truth。
   - 适合未来做“memory repo export / debug view / archival source projection”，不适合先替换现有 typed store。
   - Letta 的相关入口：`docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:16-17,61-70,114-171`，`docs/research/letta-main/letta/services/memory_repo/git_operations.py:351-413,547-622`。

3. `lakeFS` 的 metadata layer over physical storage
   - 借的是“物理对象不动，版本系统维护指针与元数据映射”的思想。
   - 这对 RP 最有用的落点是 Recall/Archival/retrieval-index 这种 derived 或大对象层，而不是 Core State 本体。
   - 特别适合指导“retrieval/index 继承 source visibility，而不是自己成为 truth”，这与 `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:100-125` 和 `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md:119-127` 同向。

4. `Nocturne Memory` 的 review snapshot / universal rollback
   - 借的是“before/after frozen snapshot + grouped diff + explicit rollback”的审查模式。
   - 这很适合作为 user-visible memory inspection / admin rollback UI 的参考，不适合作为 RP branch visibility 的底层真值模型。
   - Nocturne 的 changeset 机制是单池 before/after 覆盖：`docs/research/nocturne_memory-main/backend/db/snapshot.py:2-9,69-78,128-158`。
   - 它的 rollback 是 review API 级的、以 node_uuid 分组的 universal rollback：`docs/research/nocturne_memory-main/backend/api/review.py:2-7,356-383,616-793`。

5. `Nocturne` 的 namespace isolation
   - 只能借“隔离域要显式透传并在所有读写链路默认生效”的思路。
   - 不能直接拿 namespace 替代 RP branch/session/turn/profile identity，因为 RP 的隔离粒度更细，也需要 lineage 与 rollback cutoff。
   - 相关实现：`docs/research/nocturne_memory-main/backend/namespace_middleware.py:1-18,70-85,102-152`，`docs/research/nocturne_memory-main/backend/db/models.py:144-157,182-205`。

#### 暂不引入

1. `Dolt` 作为实际主存储引擎
   - 过重。当前 RP 要解决的是 branch visibility contract，不是把整个 story/memory store 改造成一套 Git-SQL 数据库。
   - 还会把现有 Python 服务、typed DTO、proposal/apply、retrieval-core、compat mirror 全部卷入存储替换。

2. `lakeFS` 作为实际底层对象版本总线
   - 过重。lakeFS 适合大对象/数据湖，不适合当前 RP boot bar 阶段的 story memory foundation。
   - 它更像未来 Recall/Archival 大对象治理或数据导出层的候选，不是现在的 runtime boot blocker 解法。

3. `Letta MemFS / git smart HTTP / worktree` 整套运行时
   - 过重。本地实现已经显示它需要 git-backed repo、memfs sidecar、push 后 cache sync、并发 lock 等整套运维面：`docs/research/letta-main/letta/services/block_manager_git.py:30-36,216-242,359-381,463-481`，`docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:3-17,251-354`。
   - 对 RP 当前阶段，收益主要是“学模式”，不是“抄运行时”。

4. `Nocturne` 的 sovereign-memory 产品哲学
   - 暂不引入。当前 RP 需要的是 narrative runtime 的 governed memory OS，不是把 memory ownership 变成“agent 自我人格记忆系统”。
   - Nocturne 的 disclosure / alias / first-person memory 很强，但更偏 persona-memory 产品，而不是 branch-aware story truth foundation。

5. `Git merge/conflict` 语义进入当前 memory foundation
   - 暂不引入。当前项目规格强调的是 branch visibility、rollback、turn identity、derived visibility、proposal/apply governance，还没有进入“多 branch 双向 merge + conflict resolution”阶段。
   - 现在先把 fork / switch / rollback / hide / purge 边界做对，性价比更高。

### 必答问题

#### 1. 哪些设计可以直接借来

- `metadata-first branch creation + copy-on-write lineage`
- `branch head 作为独立可见视图`
- `rollback 后同线 future 失效，branch 则保留另一条 future`
- `source-of-truth + cache/projection/index split`
- `commit-style audit/event spine`
- `inspection/review 层使用 before/after snapshot`

#### 2. 哪些只能借思想，不能直接抄实现

- Letta 的 tool-managed memory：可借受控写入口，不可照抄 self-edit 宽权限。
- Letta Git memory：可借 git-like revision/audit/path projection，不可直接拿 MemFS 作为 RP backend。
- lakeFS 的 metadata layer：可借“物理内容不动、版本只动指针”，不可照搬其对象存储架构。
- Nocturne 的 namespace / disclosure / alias：可借隔离与触发式召回思路，不可替代 RP 的 branch/turn/profile identity。

#### 3. 对当前 memory OS / branch visibility / source-of-truth + cache split 最有帮助的模式是什么

最有帮助的是一个组合，而不是单一产品：

- `Memory OS`：采用 Letta 验证过的 layer split，但保持 RP 自己的语义边界。
  - 对应当前 spec：`.trellis/spec/backend/rp-memory-temporal-materialization.md:82-189`
- `branch visibility`：采用 Dolt / lakeFS 式 metadata-first + lineage visibility，再由 RP 自己的 resolver 落地。
  - 对应当前 spec：`.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:81-137`
- `source-of-truth + cache split`：采用 Git memory 式 revision truth + rebuildable cache/index。
  - 对应当前 spec：`.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md:72-133`

如果只压缩成一句话：

`RP 自己维护 revisioned truth spine；branch 用 lineage + cutoff 解可见性；projection/retrieval/index 全部当 derived cache。`

#### 4. 哪些东西现在引入会过重

- Dolt / lakeFS 作为底层存储替换
- Letta MemFS + git smart HTTP + worktree 并发编辑整套运行时
- Nocturne 完整 URI graph / sovereign persona memory 体系
- merge/conflict resolution 产品面
- 为了“像 Git”而把所有层都文件化

这些都不是当前 boot bar 缺口。当前真正缺的是：

- first-class `BranchHead / Turn / RuntimeProfileSnapshot`
- persistent `Runtime Workspace`
- persistent `MemoryChangeEvent`
- branch visibility resolver
- deterministic read manifest

这几点在现有 task research 与 backend specs 里已经明确是 blocker：
- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md:25-34,57-72,116-130`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:83-137`
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md:72-145`

### 建议的采用顺序

1. 先按 Dolt / lakeFS 思路把 `BranchHead + lineage + cutoff` 做成 RP 自己的 branch visibility contract。
2. 再按 Git memory 思路把 `revision/provenance/event` 与 `projection/index/cache` 彻底拆开。
3. 再用 Letta 的 layering 经验校准 Memory OS 边界，确保 Core / Projection / Recall / Archival / Workspace 不串层。
4. 最后才考虑 Nocturne 式 inspection/review UI、file projection、repo export 等人类可视化能力。

### Files Found

- `.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md` — 已有 branch/rollback 调研，结论是 LangGraph 只够 workflow shell，不够 memory product semantics。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md` — 当前 story runtime memory blocker 总表，定义了 boot bar 与 full foundation bar。
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md` — 当前项目对 branch lineage、visibility scope、rollback cutoff 的正式合同。
- `.trellis/spec/backend/rp-memory-temporal-materialization.md` — 当前项目对 Core/Projection/Recall/Archival/Workspace 分层的正式合同。
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md` — 当前项目对 fact/view split 与 deterministic read manifest 的正式合同。
- `docs/research/letta-main/letta/orm/block.py` — Letta block 的字段模型，包含 version、read_only、history pointer。
- `docs/research/letta-main/letta/orm/block_history.py` — Letta block snapshot 历史表。
- `docs/research/letta-main/letta/services/block_manager.py` — Letta 线性 checkpoint / undo / redo 逻辑。
- `docs/research/letta-main/letta/services/block_manager_git.py` — Letta git-backed memory 的 source-of-truth + cache split。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py` — Git commit/history/ref/lock 操作。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py` — git push 后同步 PostgreSQL block cache 的桥接层。
- `docs/research/nocturne_memory-main/README.md` — Nocturne 的产品级能力说明，重点是 snapshot/review/namespace/disclosure/alias。
- `docs/research/nocturne_memory-main/backend/db/models.py` — Nocturne 的 Node/Memory/Edge/Path/namespace/version-chain 模型。
- `docs/research/nocturne_memory-main/backend/db/snapshot.py` — Nocturne 的 before/after changeset snapshot 存储。
- `docs/research/nocturne_memory-main/backend/api/review.py` — Nocturne 的 grouped diff / rollback API。
- `docs/research/nocturne_memory-main/backend/namespace_middleware.py` — Nocturne 的 namespace 透传与 SSE 会话恢复机制。

### Code Patterns

- `docs/research/letta-main/letta/orm/block.py:20-61` — block 带 `label/description/limit/read_only/version/current_history_entry_id`，说明 current memory object 本身带版本与历史指针。
- `docs/research/letta-main/letta/orm/block_history.py:12-47` — 历史快照按 `block_id + sequence_number` 线性累积。
- `docs/research/letta-main/letta/services/block_manager.py:842-876` — 新 checkpoint 发生在 undo 之后时，会截断 future checkpoints。
- `docs/research/letta-main/letta/services/block_manager.py:952-1041` — undo/redo 明确围绕线性 checkpoint 栈，不是多分支历史。
- `docs/research/letta-main/letta/services/block_manager_git.py:30-36` — git 为 source of truth，PostgreSQL 为 read cache。
- `docs/research/letta-main/letta/services/block_manager_git.py:216-242` — update path 是先 commit to git，再 sync to Postgres cache。
- `docs/research/letta-main/letta/services/block_manager_git.py:564-595` — 可从 git 重建 Postgres block cache。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py:351-413` — commit 通过 lock 串行化，避免并发写乱序。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:16-17,61-70,114-171` — push 成功后扫描 markdown files 并同步 block cache。
- `docs/research/nocturne_memory-main/backend/db/models.py:94-127` — Memory version chain、Edge 上的 `priority/disclosure`、alias-friendly graph 结构。
- `docs/research/nocturne_memory-main/backend/db/models.py:144-157` — Path 是 materialized URI cache，不是真正结构真值；source of truth 仍是 edges。
- `docs/research/nocturne_memory-main/backend/db/snapshot.py:2-9,128-158` — changeset 记录 frozen `before` + overwritten `after`，天然适合审查/回滚 diff。
- `docs/research/nocturne_memory-main/backend/api/review.py:2-7,616-793` — universal rollback 基于 snapshot + live DB 恢复，不是 branch lineage 系统。
- `docs/research/nocturne_memory-main/backend/namespace_middleware.py:70-85,102-152` — namespace 默认注入所有 downstream read/write，并处理 SSE follow-up request 的 namespace 恢复。
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:23-77` — RP 已定义 `RuntimeBranchReadScope` 与 branch-aware metadata vocabulary。
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:93-125` — RP 已冻结 metadata-first / lineage-first / rollback-as-visibility-transition。
- `.trellis/spec/backend/rp-memory-temporal-materialization.md:82-103` — RP 已冻结 Core/Projection/Recall/Archival/Workspace 五层 ownership。
- `.trellis/spec/backend/rp-memory-temporal-materialization.md:172-189` — 工具读必须走 broker，不允许绕过 layer boundary。
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md:95-127` — read manifest 必须记录 visible/selected/omitted refs 与 retrieval participation，但 retrieval 不自动变真值。

### External References

- Letta Docs, Memory Blocks: https://docs.letta.com/guides/core-concepts/memory/memory-blocks/
- Letta Docs, Archival Memory: https://docs.letta.com/guides/core-concepts/memory/archival-memory/
- Letta Docs, Context Hierarchy: https://docs.letta.com/guides/core-concepts/memory/context-hierarchy/
- Letta Docs, Letta Code Memory / MemFS: https://docs.letta.com/letta-code/memory/
- Letta Blog, Context Repositories: https://www.letta.com/blog/context-repositories
- Dolt Docs, Branch Concept: https://docs.dolthub.com/concepts/dolt/git/branch
- Dolt Docs, Using Branches: https://docs.dolthub.com/reference/sql/branches
- lakeFS Docs, Concepts and Model: https://docs.lakefs.io/latest/understand/model
- lakeFS Docs, Welcome / Versioning overview: https://docs.lakefs.io/latest
- Nocturne Memory GitHub: https://github.com/Dataojitori/nocturne_memory

### Related Specs

- `.trellis/spec/backend/rp-memory-temporal-materialization.md`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`

## Caveats / Not Found

- 本次结论有意把 `Letta core memory` 和 `Letta Git memory / MemFS` 分开评价；两者价值不同，不能混成一个“Letta 方案”。
- `Git memory` 在本调研中被当作“git-backed memory repo / commit-style memory substrate”模式，而不是单指某个独立项目。
- Nocturne 当前材料更强的是 review/snapshot/namespace/disclosure，而不是 branch lineage / multi-future story runtime；因此它对 RP 的价值更偏 inspection 层，而非 truth spine。
- 官方资料里 Dolt 和 lakeFS 都提供 merge / reset / reflog / GC 等更完整能力，但当前 RP boot bar 还没到“多 branch merge”阶段，因此本调研刻意没有把 merge 设计当成近期 blocker。
