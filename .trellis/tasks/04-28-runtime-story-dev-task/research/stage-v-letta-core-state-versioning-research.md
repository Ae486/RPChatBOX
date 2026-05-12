# Research: Stage V Letta Core State Versioning

- Query: 调研 Letta 的 memory/versioning/git-like memory 实现，并结合 Stage V 需求，判断 RP story runtime 的 Core State branch-aware as-of read 应如何设计。
- Scope: mixed
- Date: 2026-05-12

## Findings

### 0. 结论先行

用户指出的问题成立：当前 V1 只过滤 material / artifact / Recall / Workspace 这类有 branch/turn metadata 的记录还不够。`Core State.authoritative_state` 是“当前事实层”，同一个 `object_id/domain_path` 的 current row 会随 turn 更新；如果 turn2 分支只按 material visibility 过滤，但 Core read 仍读 `rp_core_state_authoritative_objects.data_json` 的 latest current 值，就会把 turn5 的当前事实泄漏进 turn2 分支。

推荐设计不是“每个 turn 拷贝全量 Core State”，也不是“只存 delta 运行时重放”。更合适的是混合方案：

1. `CoreStateObjectRevision` 存每个 Core object 的完整修订 payload，带 branch/turn/profile/provenance/visibility metadata。
2. `CoreStateSnapshotManifest` 或等价绑定表记录每个 turn 可见的 object revision map。Core State 未变化的 turn 复用上一 manifest；发生变化的 turn 创建新 manifest，只替换变化 object 的 revision pointer。
3. `MemoryChangeEvent` / apply receipt / patch delta 保留审计和 diff，但 runtime as-of read 不依赖临时重放 delta；读路径直接从 manifest 指向的 exact revision 取值。
4. `BranchVisibilityResolver` 继续决定 active branch lineage 和 cutoff；新增 `CoreStateAsOfResolver` 在该 scope 下选出 selected turn 对应 Core manifest/revisions。
5. Projection/View 必须绑定 source Core manifest 或 source revision set；如果 Core as-of manifest 变了而 Projection 仍来自旧 source，应返回 stale/omitted/refresh-needed，不得回退到 latest projection。

这正好吸收用户方案的核心：turn0 初始化快照；turn1/2 Core State 不变则复用；turn3 Core State 更新则记录新 Core State 快照；从 turn2 建 branch 时指向 turn2 对应快照。需要补强的是：这里的“快照”不应理解为每 turn 全量 JSON 拷贝，而应是 copy-on-write revision manifest。

### 1. Files Found

- `.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md` — 已有 branch/rollback/Letta/Dolt/lakeFS 调研，结论是 Letta 可借鉴但不能替代 RP branch-aware storage。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/runtime-tech-research-memory-versioning.md` — 已明确 RP 应维护自己的 revisioned truth spine，Letta Git memory 只借 source-of-truth/cache split 和 commit audit。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md` — Stage V 产品规格，V1 要关闭 branch-aware memory resolver，已要求禁止 latest-session projection/digest 进入 runtime writer context。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md` — memory foundation blocker 总表，要求 `Turn / BranchHead / RuntimeProfileSnapshot` first-class，并要求 Core/Projection/Workspace/Recall/Archival/index 全部尊重 branch/rollback visibility。
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md` — 正式 branch visibility contract，规定 metadata-first/copy-on-write、pre-fork lineage visible、post-fork branch-scoped、rollback first as visibility transition。
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md` — Core mutation 必须走 shared governed kernel，保留 base revision/conflict/event/dirty/projection outcomes。
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md` — Core authoritative fact vs Projection derived view 分离，以及 deterministic read manifest 合同。
- `.trellis/spec/backend/rp-memory-temporal-materialization.md` — Core / Projection / Recall / Archival / Runtime Workspace 分层 ownership 和 Letta borrowing boundary。
- `.trellis/spec/backend/rp-recall-branch-aware-lifecycle.md` — Recall 是 branch-aware historical layer，不是 current truth。
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md` — `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` 是 canonical runtime identity。
- `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md` — RuntimeProfileSnapshot 是 immutable turn-start policy/config snapshot，防止运行中读取 latest mutable config。
- `backend/models/rp_core_state_store.py` — 当前 Core authoritative current row + revision row 表；已有 object revision 概念，但 revision uniqueness 和 current read 仍是 session/object 维度。
- `backend/rp/services/core_state_read_service.py` — 当前 `get_state` 默认读取 current authoritative object row；没有按 selected turn / branch as-of 选 revision。
- `backend/rp/services/runtime_read_manifest_service.py` — 已有 `BranchVisibilityResolver`，可作为 Core as-of resolver 的上游 scope 来源。
- `backend/models/rp_story_store.py` — 已有 `BranchHeadRecord` / `StoryTurnRecord` / `RuntimeProfileSnapshotRecord`，可承载 Core snapshot manifest binding。
- `backend/rp/services/version_history_read_service.py` — 当前 version list 可从 revision table / apply receipts 列出版本，但还不是 branch/turn as-of read resolver。
- `backend/models/rp_memory_store.py` — apply receipt 有 before/after snapshot；MemoryChangeEventRecord 已有 branch/turn/profile identity 字段。
- `docs/research/letta-main/letta/orm/block.py` — Letta Block 当前对象字段：value/label/description/limit/read_only/hidden/version/current_history_entry_id。
- `docs/research/letta-main/letta/orm/block_history.py` — Letta BlockHistory 以 block_id + sequence_number 存 copied snapshot fields。
- `docs/research/letta-main/letta/services/block_manager.py` — Letta 标准 block checkpoint/undo/redo 是线性历史，新 checkpoint 会截断 future checkpoints。
- `docs/research/letta-main/letta/services/block_manager_git.py` — Letta git memory path：git 是 source of truth，PostgreSQL 是 read cache。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py` — MemFS 把 block 序列化为 markdown/frontmatter 文件，支持按 git ref 读 block、create/update/delete commit、history。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py` — Git commit/history/head 读写，commit 用 lock 串行化。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py` — git smart HTTP proxy；push 成功后扫描 markdown 并同步 PostgreSQL block cache。

### 2. Code Patterns

#### Letta memory blocks / history / update

- `docs/research/letta-main/letta/orm/block.py:20-61` — `Block` 是 LLM context 的 section，核心字段包括 `label`、`value`、`limit`、`read_only`、`hidden`、`current_history_entry_id`、`version`。`version` 是 SQLAlchemy optimistic locking counter，不是 story branch revision。
- `docs/research/letta-main/letta/orm/block_history.py:12-48` — `BlockHistory` 存单个 Block 的历史状态快照，复制 `description/label/value/limit/metadata_`，并带 `actor_type/actor_id` 和 monotonic `sequence_number`。
- `docs/research/letta-main/letta/services/block_manager.py:842-880` — `checkpoint_block_async` 创建 checkpoint 时，如果当前 block 曾 undo 到旧 checkpoint，会删除 current sequence 后面的 future checkpoints，保持严格线性 undo/redo stack。
- `docs/research/letta-main/letta/services/block_manager.py:952-1045` — undo/redo 只移动到相邻 sequence；没有多 branch checkpoint DAG。
- `docs/research/letta-main/letta/services/block_manager_git.py:1-8` — git-enabled block manager 明确写入顺序：先写 git source of truth，再更新 PostgreSQL cache。
- `docs/research/letta-main/letta/services/block_manager_git.py:30-40` — git memory 通过 `git-memory-enabled` tag 启用；未启用时回到普通 BlockManager。
- `docs/research/letta-main/letta/services/block_manager_git.py:216-245` — block update 先 `update_block_async(...)` commit 到 memory repo，再 `_sync_block_to_postgres(...)`。
- `docs/research/letta-main/letta/services/block_manager_git.py:564-595` — 可以从 git blocks 重建 PostgreSQL block cache。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py:66-100` — 创建 repo 时把每个 block 写成 `{label}.md`，frontmatter 中带 description/limit/read_only/metadata。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py:165-187` — `get_block_async(..., ref="HEAD")` 支持按 git ref 读 block。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py:206-258` — block update 生成 file change 并 commit。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py:260-354` — create/delete block 也通过 commit 表达。
- `docs/research/letta-main/letta/services/memory_repo/memfs_client_base.py:360-380` — history API 返回 commit history。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py:330-347` — 可以用 git ref 读取当时所有 tracked files。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py:351-413` — commit 带 branch 参数但默认 `main`，并用 lock 防并发写乱序。
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py:540-628` — history 读出 sha、parent_sha、author、timestamp、message，也能读 HEAD sha。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:1-18` — Git HTTP 是代理到 memfs service；push 后触发 PostgreSQL sync。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:61-80` — `_sync_after_push` 负责把 memfs/git 里的 block 内容同步到 PostgreSQL。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:113-175` — push 后扫描 markdown files，parse frontmatter，并 `_sync_block_to_postgres(...)`；缺失文件会 detach block。
- `docs/research/letta-main/letta/server/rest_api/routers/v1/git_http.py:250-360` — Git HTTP clone/push/pull 需要 `LETTA_MEMFS_SERVICE_URL`；receive-pack 成功后异步触发 sync。

#### RP current implementation evidence

- `backend/models/rp_core_state_store.py:41-61` — current authoritative object row 有 `current_revision` 和 latest `data_json`。如果 runtime read 只读这行，会天然读 latest。
- `backend/models/rp_core_state_store.py:64-101` — authoritative revision row 存 `revision`、`data_json`、`revision_source_kind`、`source_apply_id/source_proposal_id`，但 schema 当前 unique key 仍是 `session_id/layer/scope/object_id/revision`，没有 first-class branch/turn/profile columns。
- `backend/rp/services/core_state_read_service.py:50-75` — `get_state` 解析 ref 后调用 `_current_revision(...)`，再把 effective ref 改为 current revision。
- `backend/rp/services/core_state_read_service.py:90-115` — store enabled 时读取 `get_authoritative_object(...)` current row 并返回 `row.data_json`；没有 selected turn as-of revision 选择。
- `backend/rp/services/core_state_read_service.py:120-135` — store missing 时 fallback 到 adapter payload，同样是 session current payload，不是 branch/turn as-of。
- `backend/rp/services/runtime_read_manifest_service.py:40-101` — `BranchVisibilityResolver.build_runtime_scope(...)` 已能从 active branch 追溯 lineage，并形成 `visible_branch_head_ids` / `turn_cutoff_by_branch` / hidden turn ids。
- `backend/rp/services/runtime_read_manifest_service.py:116-170` — `is_visible(...)` 已按 visibility scope/state/owner/origin turn 判断材料可见性。
- `backend/rp/services/runtime_read_manifest_service.py:310-380` — resolver 已有按 branch 建 turn order 与 cutoff 判断的能力，可复用到 Core snapshot manifest 选择。
- `backend/models/rp_story_store.py:225-241` — `RuntimeProfileSnapshotRecord` 已持久化 immutable compiled profile。
- `backend/models/rp_story_store.py:271-304` — `StoryTurnRecord` 已有 branch/profile/status/visibility/hidden_after_turn_id 字段，适合绑定 Core snapshot manifest id。
- `backend/rp/services/version_history_read_service.py:30-70` — version list 只列 revisions/current_ref，不解决“给定 branch + turn 应读哪一版”。
- `backend/models/rp_memory_store.py:54-83` — apply receipt 已持久化 `revision_after_json`、`before_snapshot_json`、`after_snapshot_json`，适合补充 as-of provenance 和 migration/backfill 线索。
- `backend/models/rp_memory_store.py:176-206` — `MemoryChangeEventRecord` 已包含 session/branch/turn/runtime_profile_snapshot/actor/layer/domain/source_refs/dirty_targets/visibility_effect，可作为 commit/audit spine。
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md:81-137` — 正式要求 branch creation metadata-first、shared pre-fork material through lineage、rollback hides later material、Core State runtime revisions branch-aware after activation。
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md:72-127` — 正式要求 Core authoritative 是唯一 current truth，Projection 是 derived view，writer packet/read manifest 必须记录 visible/selected/omitted refs。
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md:85-135` — Core mutation 不能走 raw direct write，必须有 base revision conflict、event、dirty target、projection refresh/invalidation outcomes。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md:103-145` — V1 要求 writer context、inspection、Recall search、RetrievalBroker、debug/eval 共享 same branch-aware read scope，并禁止 latest-session projection/digest 进入 runtime-owned path。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md:266-271` — 已冻结 copy-on-write，不按 branch clone all memory，使用 `BranchHead + Turn + MemoryChangeEvent + revision/provenance` 作为 application-level commit model。

### 3. Letta 问题回答

#### 3.1 Letta 怎么表示 memory blocks / memory history / update？是否真 git-like？

Letta 有两套需要分开看：

1. 标准 Core memory block path：
   - memory block 是 LLM context section，主要是一个 text `value` 加 label/description/limit/read_only/hidden/metadata。
   - 当前 block row 带 optimistic locking `version` 和 `current_history_entry_id`。
   - `BlockHistory` 是 block-level snapshot history，按 `block_id + sequence_number` 线性增长。
   - checkpoint/undo/redo 是 linear stack；undo 后再 checkpoint 会截断 future checkpoint。
   - 这一套不是 git-like DAG，更不是 story branch model。

2. Letta Code / Git memory / MemFS path：
   - memory block 被投影为 markdown files with frontmatter。
   - git repo 是 source of truth，PostgreSQL 是 fast read cache。
   - 每次 create/update/delete block 都生成 git commit；可以按 HEAD/branch/commit ref 读取文件树；可以读 commit history。
   - 这部分是 git-like，但粒度是“一个 agent 的 memory file tree / markdown block file”，不是 RP 这种 `StorySession + BranchHead + Turn + RuntimeProfileSnapshot` 下多层 memory OS 的 product branch model。

所以结论是：Letta 的 git memory 确实有 git-like source-of-truth/history/cache-sync，但标准 memory block history 只是线性 checkpoint。即便 git memory 可按 commit 读 block，它也没有直接解决 RP 的 Core/Projection/Workspace/Recall/Archival/index 同步 branch visibility。

#### 3.2 Letta 有没有分支、回退、按历史 checkpoint 读 memory？

- 有 block-level undo/redo/checkpoint，但它是线性的。新 checkpoint 会截断 future，这更像 RP rollback 的“当前线 future 失效”，不等于 RP branch 保留多条 future。
- 有 git ref / commit history / HEAD read；MemFS 可按 ref 读 block，GitOperations 可读 commit history/head。
- 有 git branch 参数和 smart HTTP clone/push 能力，但官方代码路径中主产品语义仍围绕 agent memory file tree 和 block cache sync，不是 story branch/fork/rollback 的跨层产品语义。
- 没有发现 Letta 提供等价于 RP 所需的 `active_branch_head_id + selected_turn_id + visible_branch_head_ids + turn_cutoff_by_branch`，也没有发现它对 Core/Recall/Archival/Workspace/retrieval index 做统一 branch-aware as-of read。

仍可借用的理念：

- source-of-truth 与 read cache 分离；
- block/file path projection 让 memory 可被人类检查和编辑；
- commit/event 作为审计单位；
- cache sync after visible edit；
- isolated workspaces 适合并发 worker 编辑，但在 RP 里应映射为 Runtime Workspace candidates/proposals，而不是直接 commit truth；
- linear checkpoint 的 rollback 截断语义可作为“非 branch 的同线回退”参考。

### 4. 用户方案评估

用户方案：

```text
turn0 初始化 Core State 快照
turn1/2 Core State 不变则复用
turn3 Core State 更新则记录新 Core State 快照
回退/分支到某 turn 时指向该 turn 对应快照
```

判断：方向正确，而且是当前 V1 的必要补丁。它解决的是 branch material visibility 之外的 “Core current row as-of” 问题。

需要调整的点：

1. “快照”不应默认是每个 turn 全量 Core JSON copy。
   - Core State 可能包含多 domain/object/path；多数 turn 只改少数对象。
   - 全量 per-turn snapshot 简单但会快速变大，且容易和 authoritative object revision / apply receipt 形成双真值。

2. 应把“turn 指向快照”落成 copy-on-write manifest。
   - `CoreStateSnapshotManifest(snapshot_id, parent_snapshot_id, story_id, session_id, branch_head_id, turn_id, runtime_profile_snapshot_id, effective_revision_map_json, changed_ref_ids_json, source_event_ids_json, created_at)`
   - unchanged turn 可以直接把 `StoryTurnRecord.core_state_snapshot_id` 指向上一 snapshot。
   - changed turn 创建新 snapshot，manifest 中只需要记录完整 effective revision map 或 parent + changed bindings；为读性能建议存完整 map，同时 changed bindings 保留 diff。

3. Core object revision 才是 payload truth。
   - 每个 changed Core object 创建新 revision row，payload 是完整 object value。
   - revision row 带 `owning_branch_head_id`、`origin_turn_id`、`runtime_profile_snapshot_id`、`visibility_scope/state`、`source_apply_id/proposal_id/event_id`。
   - 如果当前 existing `CoreStateAuthoritativeRevisionRecord` 不想立刻扩列，可先建 sidecar binding table，但设计真相必须包含这些字段。

4. delta/event 用于审计和 diff，不应成为 runtime read 的唯一基础。
   - 纯 delta replay 容易在测试、迁移、并发、schema evolution 时变复杂。
   - `MemoryChangeEvent`、apply receipt before/after、patch operations 应保留，但 as-of read 直接读 manifest 指向的 object revisions。

5. Branch creation 是 metadata-first。
   - 从 turn2 fork branch 时，新 branch head 记录 `parent_branch_head_id` 和 `forked_from_turn_id=turn2`。
   - branch 的 first turn 默认 inherited snapshot = turn2 snapshot，不复制全部 Core revisions。
   - branch 上的第一次 Core mutation 才创建 branch-scoped new object revision + new manifest。

6. Rollback 是 visibility transition + head/snapshot pointer transition。
   - rollback 到 turn N 后，active branch default read scope 的 selected turn/cutoff 指向 N。
   - branch current head/snapshot 可以更新到 turn N 对应 snapshot；turn N+1 material/revisions 保留 audit，但 default runtime read hidden。
   - 不能把 later Core facts “物理删除后假装没发生”；除非后续 physical purge 进入独立能力。

### 5. RP 推荐设计

#### 5.1 存储策略：混合方案

推荐的 truth stack：

| 层 | 存什么 | 作用 |
| --- | --- | --- |
| Current pointer/cache | `rp_core_state_authoritative_objects` latest row | 快速 latest read/cache，不作为 branch as-of truth |
| Object revision | `CoreStateAuthoritativeRevisionRecord` 或 sidecar revision table | 每个 object revision 的完整 payload truth |
| Snapshot manifest | 新增 `CoreStateSnapshotManifest` / `CoreStateSnapshotBinding` | turn/branch/profile as-of read anchor，复用 unchanged snapshot |
| Event/apply receipt | `MemoryChangeEventRecord` + apply receipt + patch ops | 审计、diff、debug、dirty/projection/index invalidation |
| Projection source binding | projection slot revision metadata | 说明 derived view 基于哪个 Core manifest/revision set |

为什么不是单一方案：

- 只存完整快照：读简单，但空间膨胀，且和 object revision/proposal apply 双真值。
- 只存 object revision：缺少“某 turn 全局 effective state”指针，as-of read 每次都要按 branch lineage 和时间扫描每个对象最新版，复杂且慢。
- 只存 delta/event：重放成本、schema 演进、回滚/branch cutoff/partial object 更新都更难验证。
- 混合方案：object revision 保真值，manifest 保 read anchor，event/delta 保审计；最贴近 Letta git memory 的 source-of-truth/cache split，也贴近 Dolt/lakeFS 的 metadata-first copy-on-write。

#### 5.2 写流程

Core mutation 必须经过 shared Core mutation kernel：

1. 输入 `CoreMutationEnvelope(identity, operations, base_refs, source_refs, origin_kind, actor, ...)`。
2. 校验 base revision，防 stale overwrite。
3. 使用 `identity.branch_head_id / turn_id / runtime_profile_snapshot_id` 创建或选择 mutation event id。
4. 对 changed Core object 创建完整 payload revision。
5. 基于前一 `CoreStateSnapshotManifest` 创建新 manifest：
   - unchanged object revision pointer 继承；
   - changed object revision pointer 替换；
   - 记录 parent snapshot、changed refs、source events/apply ids。
6. 将当前 `StoryTurnRecord` 绑定到新 manifest；如果 mutation 发生在 post-write worker，可绑定到该 turn 的 final Core snapshot。
7. 更新 current row/cache 与 projection dirty targets。
8. emit `MemoryChangeEventRecord`，记录 dirty targets、visibility effect、source refs。
9. Projection refresh 根据 dirty target 重新计算 derived view，并记录 source manifest/revision set。

没有 Core mutation 的 turn：

- turn start 或 turn settlement 时绑定上一 visible Core snapshot manifest；
- 不创建新 object revision；
- 不创建新 Core snapshot manifest，除非需要记录 policy/profile-only checkpoint；通常不需要。

#### 5.3 读流程

Runtime-owned Core read 不再直接读 latest current row：

1. `BranchVisibilityResolver.build_scope(identity, selected_turn_id)` 得到 branch lineage/cutoff。
2. `CoreStateAsOfResolver.resolve_manifest(scope, selected_turn_id)`：
   - 当前 branch selected turn 有 manifest -> 使用该 manifest；
   - 当前 branch turn 无 Core mutation -> 沿 turn binding 找最近 inherited manifest；
   - fork branch first turn 无 mutation -> 使用 parent branch `forked_from_turn_id` 的 manifest；
   - rollback -> 使用 cutoff turn manifest；
   - 找不到 -> 使用 activation/turn0 initial manifest；仍找不到则 fail closed 或 compatibility-only fallback with warning。
3. 对每个 requested object ref，从 manifest 的 effective revision map 找 exact revision。
4. 读取 revision row payload，而不是 current row payload。
5. 返回 `StateReadResultItem(object_ref=object@revision, data, provenance)`，并在 read manifest 记录 selected/omitted/stale refs。
6. Debug/admin latest read 可以保留，但必须显式标注 `latest_unscoped` 或 compatibility route，不能进入 writer context。

Projection read：

- Projection row/revision 必须带 source Core manifest id 或 source object revision map。
- 如果 writer context selected Core manifest 与 Projection source manifest 不一致：
  - 可同步 rebuild projection；
  - 或返回 stale/omitted reason；
  - 不允许读 latest-session projection 当作当前 branch projection。

#### 5.4 Branch / rollback semantics

Branch from turn2:

- create `BranchHead(parent=main, forked_from_turn_id=turn2)`；
- first branch turn inherited snapshot = turn2 snapshot；
- branch read visible branch lineage = branch + main ancestor cutoff at turn2；
- main turn3/turn5 Core revisions 不进入 branch manifest，除非显式 merge/promotion，当前 Stage V out of scope。

Rollback to turn N:

- update branch control receipt + branch metadata/cutoff；
- hide later Workspace/Recall/retrieval/material/artifacts per existing resolver；
- Core read selected manifest = turn N manifest；
- later Core revisions remain persisted and traceable but hidden from default runtime read。

#### 5.5 Performance

- Snapshot manifest effective revision map 通常比 full Core payload 小得多；Core object 数量一般远小于 material/chunk 数量。
- 如果 Core object map 很大，可拆成 binding rows `(snapshot_id, object_ref, revision_id)` 并缓存 compiled map。
- current latest row 继续作为 cache/compat latest read；as-of read 用 manifest/revision。
- Projection/retrieval/index 是 derived cache，可通过 source manifest id 判断 freshness。
- 可做 periodic materialized full snapshot cache，但它应从 revision manifest rebuild，不是独立 truth。

#### 5.6 Tests

最低测试矩阵：

| Case | Expected |
| --- | --- |
| turn0 creates initial Core snapshot S0 | turn0 manifest points to all initial object revisions |
| turn1/turn2 no Core mutation | both bind/reuse S0 |
| turn3 changes one Core object | creates revision R1 and snapshot S1; unchanged objects still point to S0 revisions |
| branch from turn2 | branch first read uses S0; must not read main turn3/turn5 current row |
| branch turn4 changes Core object | creates branch-scoped revision and S2; main branch still sees its own S1/latest |
| rollback main to turn2 | default main read uses S0; turn3+ material/revisions hidden from runtime reads but still audit-visible |
| stale base direct edit | shared kernel rejects stale base revision |
| projection source mismatch | projection returned as stale/omitted or refreshed from selected manifest, never latest fallback |
| version history read | list_versions can show revisions, but get_state(as_of) returns manifest-selected revision |
| legacy session migration | no historical as-of guarantee unless revision/apply receipts allow backfill; warning explicit |

#### 5.7 Migration risks

- Existing current rows may only know latest state. If old sessions lack turn-level Core revision/apply history, historical as-of cannot be reconstructed exactly.
- Apply receipts have before/after snapshots and `revision_after_json`; they can help backfill object revisions if target refs and apply order are complete, but branch/turn/profile metadata may be absent.
- Migration should be honest:
  - new runtime sessions: create turn0 initial snapshot at activation;
  - legacy sessions with revision history: best-effort backfill manifests from apply receipts/events;
  - legacy sessions without history: seed one compatibility initial snapshot from latest current state and mark `historical_as_of_unavailable_before:<turn_id or migration_time>`。
- Current read services that fall back to adapter/session payload must be fenced off from runtime-owned writer context; otherwise fallback reintroduces latest leakage.

### 6. Requirements Coverage

Already covered:

- Branch lineage / visibility vocabulary and metadata-first branch creation: `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`.
- No full memory clone per branch; use `BranchHead + Turn + MemoryChangeEvent + revision/provenance`: `story-runtime-branch-aware-memory-product-foundation-spec.md`.
- Core authoritative vs Projection derived view: `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`.
- Core mutation governance and stale base checks: `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`.
- Runtime identity and profile snapshot pinning: `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`, `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md`.
- Recall/Archival/Workspace layer boundaries: `.trellis/spec/backend/rp-memory-temporal-materialization.md`, `.trellis/spec/backend/rp-recall-branch-aware-lifecycle.md`.

Not sufficiently covered:

1. `rp-branch-visibility-resolver-lineage.md` says Core State runtime revisions are branch-aware, but does not specify Core State as-of snapshot/manifest selection for same object whose current value changes across turns.
2. `story-runtime-branch-aware-memory-product-foundation-spec.md` says copy-on-write and read resolver, but V1 minimum contract currently focuses on filtering memory refs/materials, not resolving exact Core object revision at selected turn.
3. `rp-core-projection-read-manifest-hardening.md` requires deterministic read manifest, but does not yet require Core read manifest to include `core_state_snapshot_id` / `source_core_revision_map` / `as_of_turn_id`。

Recommended spec/dev-spec updates:

- Add a focused section to `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`:
  - `Core State As-Of Revision Manifest Contract`
  - require turn-bound Core snapshot manifest id or equivalent revision map
  - require branch/fork/rollback reads to resolve exact object revisions, not current row
  - forbid runtime writer context from using latest current row fallback.
- Add a V1 addendum to `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md`:
  - V1.1 `Core State Branch-Aware As-Of Read Closure`
  - acceptance tests: turn0/turn1/turn2 reuse, turn3 mutation, branch from turn2 cannot read turn3+ current Core.
- Add to `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`:
  - `RuntimeReadManifest.core_state_snapshot_id`
  - `source_core_revision_map`
  - `projection_source_manifest_id`
  - stale/omitted reason `core_projection_source_manifest_mismatch`.

### 7. External References

- Letta docs, Memory Blocks: https://docs.letta.com/guides/core-concepts/memory/memory-blocks/
- Letta docs, Archival Memory: https://docs.letta.com/guides/core-concepts/memory/archival-memory
- Letta docs, Context Hierarchy: https://docs.letta.com/guides/core-concepts/memory/context-hierarchy/
- Letta docs, Letta Code Memory / MemFS: https://docs.letta.com/letta-code/memory/
- Letta blog, Context Repositories: https://www.letta.com/blog/context-repositories
- Letta GitHub repository: https://github.com/letta-ai/letta
- Letta source, `letta/orm/block.py`: https://github.com/letta-ai/letta/blob/main/letta/orm/block.py
- Letta source, `letta/orm/block_history.py`: https://github.com/letta-ai/letta/blob/main/letta/orm/block_history.py
- Letta source, `letta/services/block_manager.py`: https://github.com/letta-ai/letta/blob/main/letta/services/block_manager.py
- Letta source, `letta/services/block_manager_git.py`: https://github.com/letta-ai/letta/blob/main/letta/services/block_manager_git.py
- Letta source, `letta/services/memory_repo/memfs_client_base.py`: https://github.com/letta-ai/letta/blob/main/letta/services/memory_repo/memfs_client_base.py
- Letta source, `letta/services/memory_repo/git_operations.py`: https://github.com/letta-ai/letta/blob/main/letta/services/memory_repo/git_operations.py
- Letta source, `letta/server/rest_api/routers/v1/git_http.py`: https://github.com/letta-ai/letta/blob/main/letta/server/rest_api/routers/v1/git_http.py

### 8. Related Specs

- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`
- `.trellis/spec/backend/rp-memory-temporal-materialization.md`
- `.trellis/spec/backend/rp-recall-branch-aware-lifecycle.md`
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-aware-memory-product-foundation-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/runtime-tech-research-memory-versioning.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md`

### 9. Minimal Grill Questions

No blocker question is required to proceed with a spec addendum. Existing requirements already imply branch-aware Core as-of read.

If the main session wants product confirmation before implementation, keep it to these questions:

1. Core as-of granularity: should the first implementation version Core State at object/domain_path level only, or is field-level revision identity required for user-facing diff? Recommendation: object/domain_path revision for truth; field-level patch only for diff/audit.
2. Legacy migration: for old sessions without enough Core revision history, is it acceptable to mark pre-migration as-of unavailable and seed one compatibility snapshot from latest state? Recommendation: yes; do not fabricate false history.
3. Projection freshness UX: when selected Core manifest differs from latest projection source, should writer path synchronously rebuild projection or omit stale projection and continue with authoritative Core? Recommendation: runtime writer path should rebuild if cheap and required; otherwise omit with explicit manifest reason, never read latest.

## Caveats / Not Found

- Letta local source exists under `docs/research/letta-main`; this research used that mirror plus official Letta docs/GitHub links. The local mirror may not equal GitHub HEAD at read time, so implementation agents should re-check if they depend on exact Letta internals.
- I did not find a Letta mechanism equivalent to RP story branch as-of memory reads across Core/Projection/Runtime Workspace/Recall/Archival/retrieval index. Letta Git memory is git-like at memory file tree granularity, not RP product branch semantics.
- Current RP code has object revisions and apply receipts, but current `CoreStateReadService.get_state` evidence shows runtime reads can still resolve latest current row. That code is evidence of the gap, not design truth.
- Historical migration cannot be perfect if the old session never stored turn-bound Core revision/apply events. The spec should require honest compatibility warnings rather than fake reconstruction.
