# Story Runtime LangGraph Branch / Rollback Preflight

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Slice: J - LangGraph Branch / Rollback Preflight
>
> Date: 2026-05-08
>
> Status: complete-preflight

## 1. 结论

LangGraph 适合继续作为 story runtime 的薄执行壳，直接吃它的 checkpoint、state history、replay、fork/update_state 和 debug history 能力；但它不能成为产品级 branch / rollback 真相层，也不能自动同步 Core / Projection / Recall / Archival / Runtime Workspace / retrieval index 等外部 store。

当前项目已经具备应用层 branch / rollback 的主要前置条件：`StorySession / BranchHead / Turn / RuntimeProfileSnapshot` 身份、branch-scoped graph thread、turn-scoped job ledger、rollback visibility transition、Runtime Workspace invalidation、branch-aware read scope 和 debug inspect surface。真正缺口不在“是否能做 branch/rollback”，而在 LangGraph checkpoint pointer 尚未自动、稳定地绑定到 settled `Turn` / `BranchHead`，因此第一阶段不应强造替代时序引擎，也不应把 LangGraph fork 直接等同产品 branch。

适合进入实现，但最小实现 slice 只能是：**Graph checkpoint pointer capture / preflight binding**。它应把每个可回退 settled turn 对应的 LangGraph `thread_id / checkpoint_ns / checkpoint_id / parent_checkpoint_id / captured_after_node / captured_at` 作为技术锚点写入应用层 trace / receipt / metadata，而不是重做 branch UI、physical purge、branch merge 或跨分支 Evolution 管理。

## 2. 官方能力边界

本节基于 2026-05-08 查询到的 LangGraph OSS Python 官方文档：

- Persistence: <https://docs.langchain.com/oss/python/langgraph/persistence>
- Add memory / checkpoint tuple: <https://docs.langchain.com/oss/python/langgraph/add-memory>
- Time travel: <https://docs.langchain.com/oss/python/langgraph/use-time-travel>

| 能力 | LangGraph 官方能力 | 当前项目判断 |
|---|---|---|
| checkpoint | thread 内保存 graph state checkpoint，可通过 `thread_id` 和可选 `checkpoint_id` 读取 state | 可直接采用；当前 `checkpoints.py` 已封装 Postgres/SQLite saver 和 checkpoint config |
| replay | 可从历史 checkpoint config 继续 invoke；checkpoint 前节点不重跑，之后节点重跑 | 可用于 debug / recovery / preflight；不能当作产品 rollback，因为外部 store 副作用不会自动回滚 |
| fork | 官方路径是对历史 checkpoint config 调 `update_state`，生成新的 checkpoint 后继续执行，原历史保留 | 可作为 graph-state 分叉原语；不能直接映射为 `BranchHead`，尤其当前 RP 采用 branch-scoped graph thread |
| 从旧 checkpoint 继续 | 可用旧 checkpoint config invoke/replay；也可 `update_state` 后继续 | 技术可行；产品上必须先确认目标 turn 已 settled，并同步应用层 active branch / visibility / workspace scope |
| graph state | checkpoint 保存 graph state values、metadata、parent config、pending writes 等 | 只能覆盖 graph shell state；不覆盖 Core / Recall / Archival / Runtime Workspace 的应用层持久化真相 |
| 外部 store | LangGraph store 是 cross-thread arbitrary info store，checkpointer 与 store 是两套原语 | 不引入为 story memory truth；RP 已有 Memory OS 分层和 branch visibility，不能再加第二套真相 |

## 3. 可行 / 不可行矩阵

| 问题 | 当前是否可行 | 依据 | 第一阶段处理 |
|---|---:|---|---|
| 用 LangGraph 保存 story turn 执行状态 | 可行 | `StoryGraphRunner` 通过 `open_async_checkpointed_graph` 编译 graph，`build_thread_config` 支持 namespace 和 `checkpoint_id` | 保留现状 |
| 按 branch 隔离 graph thread | 已可行 | `StoryTurnDomainService.resolve_graph_thread_binding()` 以 active `branch_head_id` 构造 `story_session:{session_id}:branch_head:{branch_head_id}` | 保留，并把它写入 preflight 文档/后续 checkpoint pointer 合同 |
| 读取 debug checkpoint history | 已可行 | `StoryGraphRunner.get_runtime_debug()` 调 `get_state` / `get_state_history` 并返回 latest / meaningful checkpoint | 保留为 graph debug route |
| 从旧 checkpoint replay graph | 技术可行，项目未产品化 | 官方支持旧 checkpoint config replay；当前 story runner 只有 debug read，没有产品级 replay/fork facade | 暂不开放产品入口；先补 checkpoint pointer capture |
| 从旧 checkpoint fork graph state | 技术可行，当前接法需专项验证 | 官方 fork 是 `update_state(old_config, values)`；当前 RP 一 branch 一 graph thread，跨 thread seed/copy 不是现成合同 | 只做 preflight / adapter spike，不把 LangGraph fork 等同 branch |
| rollback 当前 branch 到 settled turn | 应用层已可行 | `rollback_to_turn()` 要求目标 turn settled，隐藏 later turns，invalidates later workspace materials，写 branch control receipt | 保持应用层 truth；checkpoint pointer 只能作技术锚点 |
| branch create 后立即 switch | 应用层已可行 | `create_branch_from_turn()` 只允许 settled origin，解析 `fork_base_turn_id`，创建 `BranchHead` 并更新 session active branch | 保持；不复制整套 memory |
| branch switch 与外部 store identity 对齐 | 已具备基础 | branch read scope 使用 `MemoryRuntimeIdentity`，`RuntimeWorkspaceMaterialRecord` / events / jobs 均带 full identity | 继续以应用层 identity 为准 |
| graph checkpoint 自动同步外部 memory/text/workspace | 不可行 | LangGraph checkpoint 不管理 RP 外部 truth；Replay/fork 会重跑节点和副作用 | 必须由 job ledger、idempotency、visibility resolver、material lifecycle 管 |
| physical purge / branch merge / cross-branch evolution | 不适合第一阶段 | task spec 明确暂缓；当前只做 visibility-first | 暂缓 |

## 4. 当前代码锚点

### LangGraph shell

- `backend/rp/graphs/story_graph_runner.py:42-63`：non-stream turn 通过 branch-scoped thread config 执行并读取 final state。
- `backend/rp/graphs/story_graph_runner.py:82-227`：stream path 在 writer 后用 `aupdate_state()` 续跑 artifact persistence、post-write、finalize。
- `backend/rp/graphs/story_graph_runner.py:257-280`：debug route 读取 `get_state` / `get_state_history`。
- `backend/rp/graphs/story_graph_runner.py:283-336`：graph 仍是粗粒度 shell 节点，不是细粒度 worker 时序引擎。
- `backend/rp/graphs/story_graph_runner.py:347-386`：每轮复用 branch thread，显式清空 transient per-turn state。
- `backend/rp/graphs/checkpoints.py:10-47`：Postgres / SQLite checkpoint saver helper。
- `backend/rp/graphs/checkpoints.py:50-87`：`thread_id`、namespace、`checkpoint_id` config 和 snapshot checkpoint helper。
- `backend/rp/graphs/story_graph_state.py:8-40`：graph state 已携带 `runtime_identity / branch_head_id / turn_id / runtime_profile_snapshot_id`。

### 应用层 branch / rollback

- `backend/models/rp_story_store.py:162-222`：`BranchHeadRecord` 与 `BranchControlReceiptRecord`。
- `backend/models/rp_story_store.py:244-278`：`StoryTurnRecord`，含 status、acceptance、visibility、settlement 字段。
- `backend/models/rp_story_store.py:280-330`：`RuntimeWorkflowJobRecord`，turn-scoped job ledger。
- `backend/rp/services/story_runtime_identity_service.py:126-211`：`create_branch_from_turn()`，只从 settled turn 创建分支并立即切 active branch。
- `backend/rp/services/story_runtime_identity_service.py:298-392`：`rollback_to_turn()`，不创建新 turn，写 receipt、隐藏 later turns、invalidates workspace materials、更新 branch head。
- `backend/rp/services/story_runtime_identity_service.py:758-805`：rollback metadata 已允许记录 `checkpoint_binding`，但 `target_checkpoint_id` 仍依赖调用方传入。
- `backend/rp/services/story_runtime_identity_service.py:822-867`：rollback 后对 later turn 的 Runtime Workspace material 做 `invalidated` lifecycle transition。

### 外部 store identity / 可见性

- `backend/rp/services/runtime_read_manifest_service.py:33-98`：`BranchVisibilityResolver.build_runtime_scope()` 生成 active branch lineage / cutoff。
- `backend/rp/services/runtime_read_manifest_service.py:100-180`：`is_visible()` 按 visibility state、hidden turn、lineage、cutoff 判定可见性。
- `backend/rp/services/retrieval_broker.py:106-124`：runtime retrieval 会尝试按 branch scope 过滤 hits；失败时有 identity-only fallback warning。
- `backend/rp/services/runtime_workflow_job_service.py:56-89`：creation-time obligations 注册。
- `backend/rp/services/runtime_workflow_job_service.py:331-386`：turn settlement 由 acceptance + required jobs 判定。
- `backend/rp/services/story_turn_domain_service.py:524-735`：post-write trigger / minimal defer / full schedule 最终调用 `_settle_turn_if_ready()`。
- `backend/rp/services/story_turn_domain_service.py:1325-1364`：writer artifact persist 时登记 creation-time obligations 并把 turn 推到 `post_write_pending`。
- `backend/rp/services/story_runtime_debug_query_service.py:75-243`：runtime-native read-only inspect surface，包含 branch、turn、snapshot、workspace、events、job ledger、branch receipts；同时声明 graph checkpoint debug 是 separate route。

### 合同测试锚点

- `backend/rp/tests/test_story_runtime_identity_service.py:515-625`：rollback 到 settled turn 写 receipt、隐藏后续 turn、invalidates workspace material，并保留 caller-supplied checkpoint binding。
- `backend/rp/tests/test_projection_builder_services.py:1299-1472`：creation-time obligations、post-write minimal defer、settled turn status 相关覆盖。
- `backend/rp/tests/test_projection_builder_services.py:2461-2487`：graph thread binding 已对齐 branch head 和 `last_settled_turn_id`。

## 5. 第一阶段支持边界

第一阶段可以承诺：

1. `StorySession.active_branch_head_id` 是产品 active branch 真相。
2. `BranchHead / StoryTurn / RuntimeProfileSnapshot` 是 runtime identity 真相。
3. LangGraph `thread_id / checkpoint_id` 只是 graph shell 技术锚点。
4. branch create / switch / rollback control actions 不进入正文 `Turn` 时间线，只写 receipt / metadata / trace。
5. rollback 先做 visibility transition，不做 physical purge。
6. Runtime Workspace / jobs / events / retrieval usage 等外部材料以 full identity 隔离，并通过 visibility/lifecycle 参与 rollback。
7. graph debug history 可以读；产品 replay/fork 入口暂不开放。
8. checkpoint pointer 可以在下一实现 slice 中被自动捕获到 turn/branch metadata，但不能替代 settled/job-ledger 判定。

第一阶段不能承诺：

1. LangGraph fork 后外部 memory/text/workspace 自动同步。
2. branch switch 后从旧 branch graph checkpoint 直接恢复所有产品状态。
3. rollback 物理删除 future turns / workspace / recall / index。
4. branch merge / compare / conflict resolution。
5. 跨分支 Story Evolution 自动传播。

## 6. 暂缓项

| 暂缓项 | 原因 |
|---|---|
| 完整 branch UI / 树状消息流 | 当前 slice 只做 backend preflight；PRD 已明确第一阶段不扩大到完整 branch UI |
| physical purge | 当前合同是 visibility-first；物理删除需证明共享历史和派生索引不会被误删 |
| branch merge / conflict resolution | 需要 Core / Projection / Recall / Archival 的跨分支冲突策略，当前无必要 |
| LangGraph store truth 化 | 会引入第二套 memory truth，与 Memory OS 分层冲突 |
| interrupt-based 审批主链 | 会引入节点重跑与外部副作用幂等复杂度，当前 post-write/job ledger 更优先 |
| subgraph-level checkpoint 精细化 | 根图 shell、checkpoint pointer、job ledger 已足够支撑第一阶段 |
| 跨 thread checkpoint copy / seed | 官方 fork 原语在同一 thread checkpoint lineage 内；当前 RP 是 branch-scoped thread，需要专项 spike 证明 |

## 7. 最小实现 slice 建议

适合进入实现。建议只做 **J1: GraphCheckpointPointer capture and binding**。

### J1 目标

让每个 settled turn 可回答：

- 它属于哪个 branch-scoped graph thread。
- 它完成后对应哪个 LangGraph checkpoint。
- parent checkpoint 是哪个。
- checkpoint 是在哪个 node 之后捕获的。
- rollback receipt / branch metadata 里的 checkpoint binding 是否来自后端捕获，而不是调用方手填。

### 推荐落位

最小可选两种实现，优先选更小的一种：

1. `StoryTurnRecord` / `BranchHeadRecord.metadata_json` 中写 `graph_checkpoint_binding`。
2. 若 metadata 写入开始变重，再新增薄 record，例如 `StoryGraphCheckpointPointerRecord`。

推荐最小字段：

```text
graph_thread_id
checkpoint_ns
checkpoint_id
parent_checkpoint_id
captured_after_node
captured_at
turn_id
branch_head_id
runtime_profile_snapshot_id
```

### J1 不做

- 不调用 LangGraph fork 创建产品 branch。
- 不开放 replay/fork API。
- 不改完整 branch UI。
- 不做 physical purge。
- 不做 branch merge。
- 不改 R 模块 rewrite/review 行为。

### J1 测试点

1. non-stream turn finalize 后，turn/branch metadata 有 checkpoint pointer。
2. stream turn finalize 后，turn/branch metadata 有 checkpoint pointer。
3. rollback 时，如果目标 turn 有 checkpoint pointer，receipt metadata 自动带 `target_checkpoint_id`。
4. 没有 checkpoint pointer 时，rollback 仍按应用层 visibility contract 成功，但记录 warning / metadata reason。
5. graph debug route 继续保持 separate route，不成为产品 truth source。

### J1 能力验证矩阵

后续实现 `GraphCheckpointPointer capture / binding` 时，测试不能只验证字段存在，还必须验证 branch / rollback 能力是否按 RP 应用层真相成立。最小能力验证必须覆盖：

1. settled turn 与 graph checkpoint pointer 的绑定
   - non-stream 与 stream finalize 都必须在目标 `Turn` settled 后写入 `graph_checkpoint_binding`。
   - binding 必须携带 `graph_thread_id / checkpoint_ns / checkpoint_id / parent_checkpoint_id / captured_after_node / captured_at / turn_id / branch_head_id / runtime_profile_snapshot_id`。
   - `graph_thread_id` 必须是 branch-scoped thread，不能退回 session-only thread。
   - binding identity 必须与 settled `Turn / BranchHead / RuntimeProfileSnapshot` 一致，不能由调用方手填覆盖。
   - 同一 settled turn 已有有效 binding 后，后续 debug/replay/fork 捕获到的新 checkpoint 不能覆盖该应用层回退锚点。
2. rollback receipt 的 checkpoint binding
   - 目标 turn 已有 checkpoint pointer 时，`rollback_applied` receipt metadata 必须自动带目标 checkpoint binding 或至少稳定的 `target_checkpoint_id`。
   - 目标 turn 缺少 checkpoint pointer 时，rollback 仍按应用层 visibility 成功，但 receipt metadata 必须写明缺失原因，例如 `checkpoint_binding_missing_reason`。
   - receipt 不能只信任调用方传入的 checkpoint id；后端必须从目标 settled turn / branch metadata 解析。
3. branch create / switch 不创建 story turn
   - `branch_created` 与 `branch_switched` 只能写 branch/control receipt 与 trace。
   - 测试必须断言 story turn 数量不因 create / switch 增加。
   - branch create 后必须立即切换 `StorySession.active_branch_head_id`，但仍不复制整套 memory / workspace。
4. rollback 后当前主线不被 later materials 污染
   - rollback 到目标 turn 后，目标 turn 之后的 turns 必须在当前 active branch 线性读中不可见。
   - later turns 产生的 Runtime Workspace materials、draft/rewrite candidates、pending jobs、packet/window metadata 必须被 invalidated、hidden 或被 branch-visible reads 过滤。
   - branch-visible read manifest / debug inspect / writer packet 构建必须以 active branch lineage + cutoff 为准，不能读到 rollback cutoff 之后的材料。
5. LangGraph debug / replay / fork 只能验证技术壳
   - debug / replay / fork 测试只能证明 LangGraph shell 能读取 checkpoint history、从旧 checkpoint replay、或通过 `update_state` 形成 graph-state fork。
   - 这些测试不得把 graph checkpoint / fork 断言为产品 branch / rollback 真相。
   - 产品级 branch、rollback、visibility、workspace lifecycle、Memory OS truth 仍必须以 RP 应用层 `StorySession / BranchHead / Turn / RuntimeProfileSnapshot / Runtime Workspace` 为准。

## 8. 不应强造替代时序引擎

当前项目不需要重写一个自研 graph/replay/fork engine。理由：

1. LangGraph 已经提供足够的 workflow shell：checkpoint、state history、replay、`update_state` fork、debug history。
2. RP 产品真相不在 graph shell，而在应用层 identity / branch visibility / Runtime Workspace / Memory OS。
3. 需要补的是 checkpoint pointer 与应用层 settled turn 的绑定，不是替换 LangGraph。
4. 任何自研时序引擎都会新增第二套 checkpoint / replay / pending write 语义，反而增加与外部 store 同步难度。

因此下一步应沿用 LangGraph shell + RP application truth 的分层：**LangGraph 管执行壳，RP 应用层管故事真相、分支可见性、回退一致性和外部材料生命周期。**
