# Story Runtime Development Master Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: 作为 story runtime 模块化开发规格书的总入口，统一术语、模块边界、依赖顺序、并行开发约束和真相源。
>
> Status: draft-v1

## 1. 文档定位

这不是 PRD，也不是设计回顾。

这份文档的职责是：

1. 作为所有 story runtime 开发规格书的总索引
2. 统一工程约束
3. 统一模块依赖顺序
4. 明确哪些模块可以并行，哪些必须先冻结公共合同
5. 为后续 dev session 提供稳定的对接边界

## 2. 真相源

开发规格书编写与实现时，口径优先级固定如下：

1. 当前 task 讨论结论
2. [prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md)
3. [story-runtime-spec-coding-plan.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-spec-coding-plan.md)
4. [story-runtime-module-architecture.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-module-architecture.md)
5. [story-runtime-architecture-question-queue.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-architecture-question-queue.md)
6. 其他 research 文档

若旧文档与 task 讨论冲突，以最新 task 讨论为准。

## 3. 全局工程约束

### 3.1 必须遵守

- `contract-first`
- `registry-driven`
- `plugin-style composition`
- `immutable snapshot`
- `turn-as-anchor`
- `worker-over-ad-hoc`
- `runtime-first rebuild with selective reuse`

### 3.2 明确禁止

- 把 longform MVP 的后端链路、API、SSE、数据模型当成必须兼容的硬约束
- 把 worker 名称、domain 集合、mode 分支散落硬编码到 scheduler 主链
- 让 branch/control actions 进入正文 `Turn` 时间线
- 让 retrieval raw hits、Runtime Workspace 日志或 worker 中间态直接污染 writer packet
- 为了前端适配反向定义后端 runtime 语义

## 4. 仓库内落位原则

开发规格书和后续实现，优先沿用当前 `backend/rp` 目录结构：

### 4.1 models

目录：

- `backend/rp/models`

职责：

- typed contracts
- persistent record models
- enums
- packet/result DTO

当前应优先复用/扩展的文件：

- `runtime_identity.py`
- `runtime_workspace_material.py`
- `memory_contract_registry.py`
- `story_runtime.py`（仅作为旧 MVP 兼容入口，不再作为新 runtime 真相承载面）

### 4.2 services

目录：

- `backend/rp/services`

职责：

- repositories
- domain services
- orchestration helpers
- packet builders
- runtime readers

当前应优先复用/扩展的文件：

- `story_runtime_identity_service.py`
- `runtime_profile_snapshot_service.py`
- `runtime_workspace_material_service.py`
- `runtime_memory_persistence_repository.py`
- `runtime_read_manifest_service.py`
- `worker_memory_service.py`
- `retrieval_broker.py`
- `runtime_retrieval_card_service.py`
- `proposal_workflow_service.py`
- `proposal_apply_service.py`
- `story_llm_gateway.py`
- `story_turn_domain_service.py`

### 4.3 graphs

目录：

- `backend/rp/graphs`

职责：

- runtime graph state / nodes / runner

当前应优先复用/替换的文件：

- `story_graph_state.py`
- `story_graph_nodes.py`
- `story_graph_runner.py`

### 4.4 旧 MVP 文件的处理原则

- `story_runtime.py`
- `writing_runtime.py`
- `longform_orchestrator_service.py`
- `longform_specialist_service.py`
- `writing_packet_builder.py`
- `writing_worker_execution_service.py`

这些文件只作为：

1. 行为参考
2. 兼容 adapter 候选
3. 可迁移素材

不再作为新 runtime 主链的设计约束。

## 4.5 技术采用矩阵

story runtime 的技术调研目标，不是继续找一个更大的框架，而是明确三件事：

1. 哪些现有框架 / 仓库内模块可以直接采用
2. 哪些成熟项目只适合借设计模式
3. 哪些技术虽然强，但第一阶段引入只会拖慢实现

### 4.5.1 直接采用

1. `LangGraph` 作为 runtime shell
   - 直接采用范围：
     - checkpoint persistence
     - replay
     - fork preflight
     - resume / pending writes recovery
     - graph debug history
   - 明确边界：
     - 它只负责 graph shell，不负责产品级 branch / rollback 真相
     - `BranchHead / Turn / RuntimeProfileSnapshot / MemoryRuntimeIdentity` 仍由 RP 应用层持有

2. 仓库内现成 spine / service / gateway
   - 直接复用优先级最高的模块：
     - `MemoryRuntimeIdentity`
     - `StoryRuntimeIdentityService`
     - `RuntimeProfileSnapshotService`
     - `RuntimeWorkspaceMaterialService`
     - `RuntimeMemoryPersistenceRepository`
     - `RuntimeReadManifestService`
     - `WorkerMemoryService`
     - `RetrievalBroker`
     - `RuntimeRetrievalCardService`
     - `ProposalWorkflowService`
     - `ProposalApplyService`
     - `StoryGraphRunner`
     - `StoryLlmGateway`

3. writer / retrieval 的受控工具循环模式
   - 直接采用官方已经验证过的 client-side tool loop 思路：
     - model 输出结构化 tool call
     - 应用侧执行工具
     - tool result 回灌模型
     - bounded retries / attempts
     - final output 前做 usage gate
   - 这部分是模式直接采用，不是引入新的 agent framework

4. `agents-as-tools` 而不是 `handoff`
   - 对当前项目，memory worker、rule worker、scene worker 都是 bounded specialist
   - 最终用户可见输出只允许 `WritingWorker` 负责
   - 不允许让 memory worker / orchestrator 接管前台会话主权

### 4.5.2 仅参考，不直接照搬

1. `Letta`
   - 参考点：
     - memory layering
     - tool-managed memory
     - git-like audit / revision 思维
     - source-of-truth 与 cache/projection 分离
   - 不直接照搬：
     - Letta 的 agent runtime 主体
     - MemFS / git smart HTTP / worktree 整套运行时

2. `Dolt / lakeFS`
   - 参考点：
     - metadata-first branch creation
     - copy-on-write lineage
     - branch-local visibility
   - 在本项目中的映射：
     - `BranchHead + lineage + cutoff + branch visibility resolver`
   - 不直接引入其底层数据库 / 对象存储系统

3. `Nocturne Memory`
   - 参考点：
     - before / after inspection snapshot
     - grouped diff
     - explicit review / rollback UX
   - 仅适合作为 inspection / review 面参考，不作为 story truth foundation

4. `how-claude-code-works` 本地资料
   - 参考点：
     - 显式主循环
     - 上下文分层
     - tool descriptor
     - on-demand context loading
   - 仅借这些工程模式，不迁移其产品/runtime 形态

### 4.5.3 第一阶段明确不引入

1. 不把 `LangGraph store` 当成 memory truth
2. 不把 `LangGraph fork` 直接等同于产品 branch
3. 不引入 `Letta MemFS / git smart HTTP / worktree` 运行时
4. 不引入 `Dolt / lakeFS` 作为 story runtime 主存储
5. 不引入新的重 agent framework 来管理 worker / writer / retrieval
6. 不引入多 agent handoff 会话主链
7. 不做 GraphRAG-first 重写
8. 不做 branch merge / conflict resolution
9. 不让旧 longform fixed chain 反向定义新 runtime 合同

### 4.5.4 工程判断原则

后续任何“引入框架 / 抄成熟项目”的提案，都必须按以下顺序判断：

1. 它解决的是 story runtime 当前的真实 blocker，还是只是提供一种看起来更先进的抽象
2. 它是直接减少实现工作量，还是会引入第二套 truth / 第二套 loop / 第二套配置体系
3. 它是否破坏当前已经冻结的边界：
   - turn-as-anchor
   - immutable snapshot
   - deterministic scheduler
   - governed mutation path
   - projection strictly derived from facts
4. 它能否以 adapter / thin service 形式接入，而不是要求替换主链

只有同时满足“减少工作量”和“不破坏主链边界”，才允许进入第一阶段实现清单。

## 5. 模块规格书清单

## 5.1 公共合同层

1. [story-runtime-identity-profile-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-identity-profile-spec.md)
2. [story-runtime-workspace-ledger-trace-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-workspace-ledger-trace-spec.md)
3. `story-runtime-worker-scheduler-spec.md`
4. [story-runtime-context-packet-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md)
5. [story-runtime-writing-worker-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md)
6. [story-runtime-revision-overlay-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-revision-overlay-spec.md)
7. [story-runtime-revision-overlay-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-revision-overlay-development-spec.md)
8. [story-runtime-retrieval-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-retrieval-spec.md)
9. [story-runtime-postwrite-memory-governance-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-postwrite-memory-governance-spec.md)
10. [story-runtime-branch-rollback-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-rollback-spec.md)
11. [story-runtime-adapter-debug-test-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-adapter-debug-test-spec.md)

公共合同层前三份必须先冻结，再允许其他模块并行扩散。

## 5.2 第一批可并行模块

1. `story-runtime-context-packet-spec.md`
2. `story-runtime-writing-worker-spec.md`
3. `story-runtime-revision-overlay-spec.md`
4. `story-runtime-revision-overlay-development-spec.md`
5. `story-runtime-branch-rollback-spec.md`
6. `story-runtime-worker-scheduler-spec.md`（公共合同冻结后继续细化）

## 5.3 第二批可并行模块

1. `story-runtime-retrieval-spec.md`
2. `story-runtime-adapter-debug-test-spec.md`
3. longform chapter/review adapter 章节
4. roleplay/trpg extension slots 章节

## 5.4 最后收口模块

1. `story-runtime-postwrite-memory-governance-spec.md`
2. integration tests / migration / rewrite strategy

## 6. 公共合同冻结清单

在并行开发前，以下对象必须先冻结：

1. `StorySession`
2. `BranchHead`
3. `Turn`
4. `RuntimeProfileSnapshot`
5. `MemoryRuntimeIdentity`
6. `RuntimeWorkspaceMaterial`
7. `RuntimeWorkflowJobRecord`
8. `WorkerDescriptor`
9. `WorkerExecutionPlan`
10. `WorkerContextPacket`
11. `WorkerResult`
12. `WritingPacket`
13. `PacketSection`
14. `RuntimeReadManifestRecord`

原则：

- 下游模块只能引用这些合同
- 不允许各模块私自增删这些对象的核心字段语义
- 需要调整时，先改主规格书，再回收影响

## 7. 并行开发边界

## 7.1 Group A：核心合同组

负责：

- identity/profile
- turn/workspace/ledger/trace
- worker/scheduler contract

可写范围：

- `backend/rp/models/runtime_identity.py`
- 新增公共 record / DTO 文件
- `runtime_profile_snapshot_service.py`
- `story_runtime_identity_service.py`
- `runtime_workspace_material_service.py`
- `runtime_memory_persistence_repository.py`

不应同时并行修改：

- writing worker 行为细节
- retrieval writer loop
- post-write 治理流程

## 7.2 Group B：编排主链组

负责：

- worker registry / scheduler
- context orchestration
- writing worker

依赖：

- Group A 公共合同冻结

## 7.3 Group C：知识与治理组

负责：

- retrieval
- post-write
- memory governance

依赖：

- Group A
- Group B 的 packet / worker plan / workspace 对接面

## 7.4 Group D：版本与产品组

负责：

- branch / rollback
- longform adapter
- roleplay/trpg extension slots
- debug / test / migration

依赖：

- Group A 的身份、turn、trace 合同

## 7.5 顺序集成文件

以下文件属于顺序集成文件，不应由多组并行直接扩写：

- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/graphs/story_graph_nodes.py`
- `backend/rp/services/runtime_workspace_material_service.py`

规则：

- 必须指定单一 primary owner
- 其他模块通过 facade / contract 调用，不直接继续堆语义

当前建议：

- `story_turn_domain_service.py`
  - owner: turn-domain / finalize / settle 事务边界

- `story_graph_nodes.py`
  - owner: graph shell / runtime node routing

- `runtime_workspace_material_service.py`
  - owner: workspace persistence / lifecycle / short-id / material query

## 8. 规格书最小深度要求

每份模块规格书至少包含：

1. 负责什么
2. 不负责什么
3. 与其他模块的边界
4. 推荐文件结构
5. 数据模型与字段
6. 状态与规则
7. DTO / contract
8. 关键伪代码
9. 测试点
10. 迁移或兼容边界（若需要）

## 9. 问题处理规则

编写规格书时：

- 能从现有文档直接推导的问题，直接定稿
- 无法从现有文档安全推导、且会影响实现的问题，进入 [story-runtime-architecture-question-queue.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-architecture-question-queue.md)
- 继续遵守 FIFO

## 10. 当前推荐编写顺序

1. 本总控文档
2. Identity / Profile
3. Workspace / Ledger / Trace
4. Worker / Scheduler
5. Context / Packet
6. WritingWorker
7. Branch / Rollback
8. Retrieval
9. Post-write / Memory Governance
10. Adapter / Debug / Test / Migration

## 11. 当前完成定义

当前阶段“规格书完成”不等于代码完成。

当前阶段的完成定义是：

1. 主链模块都有开发规格书
2. 公共合同层冻结
3. 并行开发边界清楚
4. 遇到的设计缺陷已修正文档或进入 grill 队列
5. 后续 dev session 可以按模块拿文档直接开发
