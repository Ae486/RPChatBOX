# Research: runtime-tech-research-langgraph-shell

- Query: 评估 LangGraph 是否适合作为当前 story runtime 的 runtime shell，并明确它在 branch / rollback / fallback 底座上哪些能力可直接采用、哪些只能做外壳、哪些第一阶段不应引入。
- Scope: mixed
- Date: 2026-05-07

## Findings

### 先给工程结论

LangGraph 适合做当前项目的 **runtime shell**，但只适合做 **workflow checkpoint / replay / fork / resume 外壳**，不适合直接充当产品级 branch / rollback 真相层。

真正能加速的边界只有三类：

1. **turn 执行壳**：已有 `StoryGraphRunner` 已经跑在 LangGraph shell 上，checkpoint 持久化、streaming 后续节点续跑、debug history 这部分可以继续吃现成能力。
2. **故障恢复 / replay / tech preflight**：checkpoint、state history、pending writes、time travel 能明显减少我们自己造执行时序引擎的工作量。
3. **branch preflight 的 graph-state 分叉原语**：可以把 checkpoint fork 当成 graph-state 分叉底座，但它只能服务 graph state，本项目要求的 Core/Projection/Recall/Archival/Runtime Workspace/retrieval 可见性隔离仍必须由应用层实现。

它**不能替代**的部分同样明确：

- 不能替代 `StorySession / BranchHead / Turn` 的产品身份模型。
- 不能替代 active branch 可见性、rollback 后未来 turn 失效、branch delete/purge、retrieval 过滤、外部 memory/materialized state 的同步回退。
- 不能替代“该 turn 是否 settled、是否允许正式回退”的应用层判定，因此也不能替代 turn-scoped job ledger。

结论上，最合理接法是：

- **保留 LangGraph 做薄执行壳**；
- **继续把 branch/rollback 真相放在 RP 应用层**；
- **把 checkpoint_id 变成 BranchHead / Turn 的技术锚点之一，而不是产品真相本身**。

### 项目内现状证据

#### 已有可复用底座

- `StoryGraphRunner` 已经是 story turn 的 LangGraph shell，负责 `pin_runtime_identity -> load_session_and_chapter -> validate_command -> ... -> finalize_turn` 的粗粒度图执行，且 story turn 复用同一个 LangGraph thread。见 `backend/rp/graphs/story_graph_runner.py:30-71`, `backend/rp/graphs/story_graph_runner.py:219-269`, `backend/rp/graphs/story_graph_runner.py:273-280`。
- checkpoint 存储已经抽象成统一 helper，当前支持 Postgres/SQLite saver，thread config 也已经显式带 `checkpoint_id`。见 `backend/rp/graphs/checkpoints.py:11-24`, `backend/rp/graphs/checkpoints.py:30-47`, `backend/rp/graphs/checkpoints.py:50-84`。
- graph state 已预留 `runtime_identity / branch_head_id / turn_id / runtime_profile_snapshot_id` 字段，说明当前壳已经开始向 branch-aware runtime identity 靠拢。见 `backend/rp/graphs/story_graph_state.py:8-13`。
- 应用层已经有持久化的 runtime identity 分配服务：`ensure_default_branch`、`create_turn`、`resolve_runtime_entry_identity`、`update_turn_status`。见 `backend/rp/services/story_runtime_identity_service.py:37-288`。
- 应用层已经有 branch visibility resolver，会按 `visible_branch_head_ids + turn_cutoff_by_branch` 做 lineage 过滤。见 `backend/rp/services/runtime_read_manifest_service.py:31-152`。
- Runtime Workspace 已经有按完整 identity 隔离的持久化 repository/service，而不是只按 session 存 scratch。见 `backend/rp/services/runtime_memory_persistence_repository.py:31-126`, `backend/rp/services/runtime_workspace_material_service.py:55-166`。

#### 当前缺口

- 当前 story graph 的 `post_write_regression` 仍是 `post_write_regression_skipped`，说明 LangGraph 现在只是 turn 执行壳，还没有真正承载 post-write 维护闭环。见 `backend/rp/graphs/story_graph_nodes.py:256-262`。
- 当前 finalize 只更新 turn 成败状态，没有 job-ledger 级“是否 settled、是否允许 rollback”的完成判定。见 `backend/rp/graphs/story_graph_nodes.py:346-351`, `backend/rp/services/story_turn_domain_service.py:219-225`。
- 代码里没有找到 `RuntimeWorkflowJobRecord` 或等价的 turn-scoped workflow job ledger 实现；现有 `job_kind` 命中主要是 retrieval ingestion/reindex，不是 story turn 后处理账本。`rg -n "RuntimeWorkflowJobRecord|required_post_write_analysis|runtime_workspace_finalize" backend/rp` 未命中实现。
- 当前代码也没有找到把 LangGraph `checkpoint_id` 持久化绑定到 `StoryTurn` / `BranchHead` 的实现；现有 checkpoint 主要停留在 graph runtime 内部。

### 规格约束与本次判断的关键边界

- PRD 已明确：rollback 是主线单向回退，branch 是保留多条未来；不能把二者混为一谈。见 `prd.md:437-461`, `prd.md:524-534`。
- PRD 已明确：回退必须同时恢复文本层、Core State、Projection/Views、Recall/Archival materialization、Runtime Workspace、packet/window metadata 的一致状态，因此“只靠 graph checkpoint”不够。见 `prd.md:454-461`。
- PRD 已明确：只有 settled turn 才允许作为正式回退点，且需要 turn-scoped workflow job ledger 做完成判定。见 `prd.md:475-479`。
- coding plan 已明确：`branch/fork` 只能从 `settled` turn 派生，branch control action 不创建新的 story turn。见 `research/story-runtime-spec-coding-plan.md:396-410`。
- coding plan 已明确：第一阶段只做 LangGraph branch/rollback preflight，不做完整 branch UI/branch purge/跨分支 Evolution 管理。见 `research/story-runtime-spec-coding-plan.md:1083-1088`, `research/story-runtime-spec-coding-plan.md:1219-1233`。
- 既有 research 已经给出前置判断：LangGraph 能提供 graph-level checkpoint/fork mechanics，但无法自动让外部 memory store、retrieval index、text artifact 获得 branch-aware 隔离。见 `research/branching-memory-framework-research.md:13-25`, `research/branching-memory-framework-research.md:201-223`。

### LangGraph 官方能力边界

以下判断只基于 2026-05-07 当天访问到的 LangGraph 官方文档。

#### 1. LangGraph 哪些能力可以直接采用

分级：**直接采用**

| 能力 | 官方依据 | 对当前项目的真实价值 |
|---|---|---|
| checkpoint 持久化 | persistence 文档说明：graph 编译时挂 checkpointer，会按 super-step 持久化 checkpoint，thread 是主键，支持 `get_state` / `get_state_history`。<https://docs.langchain.com/oss/python/langgraph/persistence> | 直接承担 runtime shell 的执行历史、debug history、失败恢复基础设施，不必自造图执行日志系统。 |
| replay | 官方明确 replay 会从旧 checkpoint 之后重新执行节点。<https://docs.langchain.com/oss/python/langgraph/persistence> | 可直接用于 turn 级 debug / recovery / preflight，不必自己做 graph-state 回放器。 |
| fork via `update_state` | 官方 time-travel 文档明确：fork 是从过去 checkpoint 通过 `update_state` 创建新 checkpoint，再继续执行；原历史保持不变。<https://docs.langchain.com/oss/python/langgraph/use-time-travel> | 可作为 branch preflight 的 graph-state 分叉原语。 |
| resume / fault tolerance / pending writes | 官方明确：失败后可从最后成功 step 恢复，super-step 内成功节点的 pending writes 可复用。<https://docs.langchain.com/oss/python/langgraph/persistence> | 很适合作为 post-write 后台链的恢复底座，尤其是后续 scheduler/worker 分步化之后。 |
| async saver / Postgres-backed shell | persistence 文档给出 async sqlite/postgres saver，当前项目也已封装。<https://docs.langchain.com/oss/python/langgraph/persistence> | 与现有 `checkpoints.py` 完全同向，几乎零概念迁移成本。 |

直接结论：

- LangGraph 作为 **turn runtime shell** 是成立的。
- 它已经能真实加速：checkpoint persistence、state history、replay、fork preflight、resume/fault tolerance。
- 这部分不是“概念上可用”，而是当前项目已有 `StoryGraphRunner + checkpointer helper` 可以直接继续吃的能力。

#### 2. 哪些只能作为外壳，不能替代应用层实现

分级：**参考模式**

| 能力边界 | 官方依据 | 结论 |
|---|---|---|
| 外部 store 与 checkpoint 是两套原语 | persistence 文档明确：checkpointer 负责 thread state，store 负责 cross-thread arbitrary info。<https://docs.langchain.com/oss/python/langgraph/persistence> | LangGraph 没有把外部 store 自动纳入 branch/rollback 一致性治理；应用层必须自己管命名空间、可见性和同步。 |
| replay/fork 会重跑 checkpoint 之后的节点 | persistence/time-travel 文档都明确：checkpoint 之后的节点、LLM 调用、API 请求、interrupt 都会重新执行。<https://docs.langchain.com/oss/python/langgraph/persistence> <https://docs.langchain.com/oss/python/langgraph/use-time-travel> | 任何外部 side effect 不能假设只执行一次；应用层必须幂等化或把副作用拆到安全边界后。 |
| interrupt/resume 会重跑所在节点 | interrupts 文档明确：interrupt 恢复时节点会重跑，interrupt 前的 side effect 必须幂等。<https://docs.langchain.com/oss/python/langgraph/interrupts> | 若后续用在人工审查/repair/handoff，不可把非幂等外部写放在 interrupt 前。 |
| durable execution 需要 deterministic/replay-safe 边界 | durable execution 文档明确：恢复不是“从同一行继续”，而是从合适起点重放，非确定性/副作用应包进 task。<https://docs.langchain.com/oss/python/langgraph/durable-execution> | 外部 memory/materialization/retrieval 刷新必须有应用层 job ledger、幂等 key 或去重策略。 |
| LangGraph 对 in-flight threads 直接跑最新代码 | backward compatibility 文档明确：最新 graph 会立即作用于已有 threads；删除/改名 node、收紧 state schema 会破坏旧 checkpoint。<https://docs.langchain.com/oss/python/langgraph/backward-compatibility> | story runtime graph 进入生产后，graph/state 变更必须有 versioning/compat 策略，不能随意改 node 名和必填字段。 |

参考模式结论：

- LangGraph **只能做 graph-state shell**。
- 对本项目真正重要的 branch/rollback 语义，仍必须由应用层持有：
  - `BranchHead` 与 active branch 切换；
  - `Turn` settled 判定；
  - rollback 后 external truth 的 hidden/invalidated；
  - retrieval 可见性过滤；
  - branch delete 的 tombstone/purge；
  - Core/Projection/Recall/Archival/Runtime Workspace 的一致性同步。

#### 3. 哪些不应在第一阶段引入

分级：**暂不引入**

1. **不要把 LangGraph store 当成 story memory truth。**
   - 官方只把它定义为 cross-thread arbitrary info store，不是 branch-aware truth store。
   - 当前项目已有更明确的应用层真相分层和 branch visibility 约束，导入 store 只会制造第二套真相。

2. **不要把“LangGraph fork”直接升格成产品 branch。**
   - LangGraph fork 只保证 graph state 分叉，不保证外部 memory/retrieval/index/materialization 同步分叉。
   - 产品 branch 仍需 `BranchHead`、visibility、delete/purge、UI 切换语义。

3. **不要在第一阶段做 interrupt-based 审批流。**
   - interrupt/resume 很强，但会把副作用幂等、节点重放、人工输入恢复复杂度一起带进来。
   - 现阶段 story runtime 还没把 post-write/job ledger 闭环做稳，先不上这层交互式 runtime 复杂度更稳。

4. **不要先做 subgraph-level checkpoint 花活。**
   - time-travel 文档支持 subgraph 自带 checkpointer，但当前项目连根图的 post-write settle/job ledger 还没落稳，过早拆 subgraph checkpoint 只会让兼容面更大。

5. **不要指望 LangGraph 解决 branch delete / physical purge。**
   - 官方文档没有提供可直接映射到“删除某产品分支并同步清理外部 truth/materialization”的能力。

### 分级汇总

#### 直接采用

- LangGraph checkpointer 作为 story runtime shell 的持久化执行底座。
- `get_state` / `get_state_history` 作为 debug / trace / replay 基础设施。
- replay 作为 recovery / debug / preflight 能力。
- `update_state` + checkpoint_id 作为 graph-state fork 原语。
- async Postgres/SQLite saver 与当前 `checkpoints.py` 封装继续沿用。

#### 参考模式

- 用应用层 `BranchHead` 持有 LangGraph checkpoint tip，而不是把 branch 语义交给 LangGraph。
- 用 LangGraph pending writes / resume 模型指导 post-write 恢复，但具体 job completion / retry policy 仍由应用层 job ledger 决定。
- 用 interrupts/human-in-the-loop 作为未来 repair/admin 模式参考，但不是第一阶段主链。
- 用 backward compatibility 的 version-stamp 思路管理 in-flight threads。

#### 暂不引入

- LangGraph store 作为 memory truth。
- “LangGraph fork = 产品 branch”的直接映射。
- interrupt-based branch/rollback 审批主链。
- subgraph checkpoint 细粒度 time travel。
- 依赖 LangGraph 自动同步外部 memory/retrieval/index/materialization。

### 当前项目最适合怎么接

#### 推荐接法

1. **继续保留 `StoryGraphRunner` 作为薄执行壳。**
   - 这层负责 graph 编排、checkpoint、stream/replay/resume。
   - 不负责产品 truth、branch visibility、rollback semantics。

2. **把 `checkpoint_id` 升级为应用层可追踪技术锚点。**
   - 当前项目已经有 `BranchHeadRecord`、`StoryTurnRecord`、`MemoryRuntimeIdentity`，但还没有把 LangGraph `checkpoint_id` 绑定进 turn/branch 追踪链。
   - 推荐至少新增一层 turn receipt / branch head shell pointer，记录：
     - `thread_id`
     - `checkpoint_ns`
     - `checkpoint_id`
     - `parent_checkpoint_id`
     - `captured_at`
     - `captured_after_node`
   - 这样 rollback/fork preflight 才有可复用的 graph-state 锚点。

3. **产品 branch 继续由应用层建模，LangGraph 只提供 checkpoint DAG 原语。**
   - `BranchHead` 记录 active shell pointer。
   - branch switch = 切换应用层 active branch + 对应 checkpoint pointer。
   - rollback = 把 active branch 的 shell pointer 指回旧 settled turn 对应 checkpoint，同时在应用层对 Core/Projection/Recall/Workspace/retrieval 做 visibility 回退。
   - branch fork = 从某 settled turn 创建新 `BranchHead`，新分支 shell pointer 指向源 turn 的 checkpoint；真正分歧在后续 turn 执行时出现。

4. **先补 turn-scoped job ledger，再谈正式 rollback 点。**
   - PRD 已经把 settled turn 与 job ledger 绑定死。
   - LangGraph 只能告诉你 graph shell 到了哪个 checkpoint，不能告诉你外部 memory/materialization/retrieval refresh 是否都到了可回退一致状态。
   - 所以正式 rollback 点必须由应用层 `Turn + job ledger` 判定，而不是“有 checkpoint 就能回退”。

5. **所有外部副作用都按 replay-safe 方式改造。**
   - retrieval usage、Runtime Workspace finalize、proposal/apply、projection refresh、Recall/Archival materialization 都要：
     - 带 turn identity；
     - 幂等或可去重；
     - 能被 job ledger 补跑/重放；
     - 不能把“执行过一次”寄托在 LangGraph 不重跑。

#### 为什么这是当前项目的最佳接法

- 它最大化复用现有资产：
  - 已有 `StoryGraphRunner`；
  - 已有 runtime identity；
  - 已有 branch visibility；
  - 已有 persistent Runtime Workspace。
- 它不让 LangGraph 越界去接管产品真相层。
- 它允许第一阶段只把 **runtime shell + turn identity + post-write/job ledger** 做稳，而不强行提前做完整 branch UI / delete / purge / cross-branch evolution。

### 第一阶段明确不要做什么

1. 不做“完整 branch UI + 复杂树形消息流可视化”。
2. 不做 LangGraph store-based memory repo。
3. 不做依赖 interrupt 的人工审批主流程。
4. 不做 branch delete 的物理 purge。
5. 不做 cross-branch automatic sync / merge。
6. 不做把 rollback 直接等同于 checkpoint replay。
7. 不做“外部 truth 跟着 graph 自动回退”的错误假设。
8. 不做频繁更名 node/state schema 的激进 graph 重构；否则旧 thread checkpoint 会被破坏。

### 直接回答用户要求的四个问题

#### 1. LangGraph 哪些能力可以直接采用

- checkpoint persistence
- async Postgres/SQLite saver
- state history / runtime debug
- replay
- `update_state`-based fork
- resume / pending writes recovery

#### 2. 哪些只能作为外壳，不能替代应用层实现

- branch identity (`BranchHead`)
- active branch visibility
- rollback invalidation semantics
- settled-turn 判定
- turn-scoped job ledger
- Core/Projection/Recall/Archival/Runtime Workspace/retrieval 的一致性回退
- branch delete / purge

#### 3. 当前项目里最适合怎么接

- 保留现有 LangGraph shell。
- 让应用层继续持有 `StorySession / BranchHead / Turn`。
- 新增 checkpoint pointer 持久化，把它挂到 turn/branch trace 上。
- rollback/fork 只从 settled turn 出发。
- 先补 job ledger 与 replay-safe 外部副作用，再逐步接 rollback/branch。

#### 4. 哪些功能第一阶段不要做

- 完整 branch UI
- branch delete purge
- LangGraph store truth 化
- interrupt-based 主链审批
- subgraph checkpoint 细化
- 自动外部 store 同步回退

## Files found

- `backend/rp/graphs/story_graph_runner.py`
  - 当前 story runtime 的 LangGraph shell；复用单 thread，负责 turn graph 编排、stream 后续节点续跑、debug checkpoint 读取。
- `backend/rp/graphs/checkpoints.py`
  - LangGraph checkpoint helper；封装 Postgres/SQLite saver、thread config、checkpoint_id 读取。
- `backend/rp/graphs/story_graph_nodes.py`
  - graph node adapter；当前 `post_write_regression` 仍是跳过状态，说明 shell 未承载完整 post-write。
- `backend/rp/graphs/story_graph_state.py`
  - graph state 已带 runtime identity / branch / turn / snapshot 字段。
- `backend/rp/services/story_runtime_identity_service.py`
  - 应用层 persistent branch/turn identity 分配与 turn 状态更新。
- `backend/rp/services/runtime_read_manifest_service.py`
  - branch visibility resolver；负责 active branch lineage 的可见性判断。
- `backend/rp/services/runtime_memory_persistence_repository.py`
  - Runtime Workspace / memory event 的 identity-scoped 持久化 repository。
- `backend/rp/services/runtime_workspace_material_service.py`
  - Runtime Workspace typed material service；说明当前 scratch/evidence 已向可持久恢复靠拢。
- `.trellis/tasks/04-28-runtime-story-dev-task/prd.md`
  - 冻结了 rollback vs branch、settled turn、job ledger、active branch 的产品语义。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-spec-coding-plan.md`
  - 给出第一阶段 implementation ordering 与 LangGraph preflight 要求。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/branching-memory-framework-research.md`
  - 已有 branch/rollback 外部状态边界判断，与本次 LangGraph shell 结论一致。

## Code patterns

- `backend/rp/graphs/story_graph_runner.py:30-71`
  - `run_turn` / `run_turn_stream` 以 LangGraph checkpointer 作为 story turn shell，并直接读取 snapshot。
- `backend/rp/graphs/story_graph_runner.py:219-269`
  - graph 拓扑已固定为 coarse nodes，说明当前更像 orchestration shell，而不是细粒度 worker engine。
- `backend/rp/graphs/story_graph_runner.py:273-280`
  - 每轮复用同一个 LangGraph thread，并手动清 transient state。
- `backend/rp/graphs/checkpoints.py:50-84`
  - `build_thread_config` 与 `checkpoint_id` helper 已具备后续 checkpoint pointer 化基础。
- `backend/rp/graphs/story_graph_nodes.py:34-51`
  - turn 进入时先 `pin_runtime_identity`，说明 branch/turn/profile 已经是 graph shell 入口的一部分。
- `backend/rp/graphs/story_graph_nodes.py:256-262`
  - `post_write_regression_skipped`，证明 LangGraph 目前尚未承担完整 post-write backend chain。
- `backend/rp/graphs/story_graph_nodes.py:346-351`
  - `finalize_turn` 只做 turn success/failure 结束，不是 settled/job-ledger completion。
- `backend/rp/services/story_runtime_identity_service.py:54-75`
  - 默认 branch 是应用层记录，不是 LangGraph 自带 branch。
- `backend/rp/services/story_runtime_identity_service.py:97-147`
  - 每个 turn 都在应用层持久化 `StoryTurnRecord`。
- `backend/rp/services/story_runtime_identity_service.py:220-276`
  - runtime entry identity 解析会自动选择 branch + snapshot + create turn。
- `backend/rp/services/runtime_read_manifest_service.py:31-74`
  - active branch 读取依赖 lineage + cutoff，而不是 graph checkpoint 自动决定。
- `backend/rp/services/runtime_read_manifest_service.py:77-152`
  - visibility contract 已支持 hidden/invalidated/hidden_by_rollback 语义。
- `backend/rp/services/runtime_memory_persistence_repository.py:31-39`
  - Runtime Workspace 查询已经按完整 identity 过滤，而非 session-only。
- `backend/rp/services/runtime_workspace_material_service.py:55-79`
  - Runtime Workspace 的默认 truth path 已经是 persistent repository-backed storage。

## External references

- LangGraph Persistence
  - URL: <https://docs.langchain.com/oss/python/langgraph/persistence>
  - Notes:
    - checkpoint 保存在 threads 中；
    - 支持 `get_state` / `get_state_history`；
    - replay 从旧 checkpoint 之后重跑；
    - `update_state` 创建新 checkpoint，不会修改旧 checkpoint；
    - checkpointer 与 store 是两套原语。
- LangGraph Use time-travel
  - URL: <https://docs.langchain.com/oss/python/langgraph/use-time-travel>
  - Notes:
    - fork 是从旧 checkpoint 调 `update_state` 建新分支 checkpoint；
    - 原历史保留不变；
    - checkpoint 之后的节点、LLM、API、interrupt 会重跑。
- LangGraph Interrupts
  - URL: <https://docs.langchain.com/oss/python/langgraph/interrupts>
  - Notes:
    - resume 时节点会重跑；
    - interrupt 前副作用必须幂等，或移动到 interrupt 后/拆到独立节点。
- LangGraph Durable execution
  - URL: <https://docs.langchain.com/oss/python/langgraph/durable-execution>
  - Notes:
    - 恢复不是从原代码行继续，而是从可恢复边界重放；
    - 非确定性与副作用需 task 化或幂等化。
- LangGraph Backward compatibility
  - URL: <https://docs.langchain.com/oss/python/langgraph/backward-compatibility>
  - Notes:
    - 最新 graph 会直接作用于已有 threads；
    - node rename/remove、state schema 收紧会破坏 in-flight checkpoints；
    - 需做 flow version / compat 策略。

说明：

- 官方文档页未直接暴露明确 package version；本次按 2026-05-07 实时访问到的当前 OSS Python 文档判断。

## Related specs

- `.trellis/tasks/04-28-runtime-story-dev-task/prd.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-spec-coding-plan.md`
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`
- `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
- `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
- `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`

## Caveats / Not Found

- 没有在当前 `backend/rp` 代码里找到 story turn 级 workflow job ledger 实现；现阶段“能否正式 rollback”还不能由代码真实判定。
- 没有找到把 LangGraph `checkpoint_id` 持久化关联到 `StoryTurn` / `BranchHead` 的现有实现；这意味着当前 shell 还不能作为 branch/rollback 的稳定技术锚点。
- 没有找到任何官方能力能自动把 LangGraph fork/rollback 同步到外部 Core/Projection/Recall/Archival/Runtime Workspace/retrieval store；这一层必须继续由 RP 应用层负责。
