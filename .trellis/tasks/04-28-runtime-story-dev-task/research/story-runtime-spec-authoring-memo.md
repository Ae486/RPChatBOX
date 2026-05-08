# Story Runtime Spec Authoring Memo

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: 在进入模块化开发规格书编写前，冻结当前的编写规划、并行开发边界和问题处理规则，保证 compact 后仍能继续按同一套方式推进。
>
> Status: active authoring memo

## 1. 目标

当前阶段的目标不是继续扩写 PRD，而是把已经冻结的架构口径整理成一组可直接指导开发的规格书。

这组规格书必须满足：

1. 按模块/功能拆分，而不是堆成一份大杂烩文档。
2. 符合工程开发约束：模块化、解耦、高可维护、registry/config 驱动、可替换、可测试。
3. 能支持多块并行开发，并尽量减少文件和模型冲突。
4. 文档内容必须下沉到开发可执行层：文件结构、模块边界、字段、数据模型、状态、DTO、伪代码、测试点、迁移边界。
5. 编写过程中同步检查设计缺陷；如果发现依据现有需求讨论文档无法解决的问题，进入 FIFO grill 清单，而不是临场拍脑袋定口径。

## 2. 真相源优先级

规格书编写时，口径优先级固定如下：

1. 当前 task 里的讨论结论
2. `prd.md`
3. `story-runtime-spec-coding-plan.md`
4. `story-runtime-module-architecture.md`
5. `story-runtime-architecture-question-queue.md`
6. 其他 research 文档

如果旧文档与 task 讨论冲突，以 task 讨论后的最新口径为准。

## 3. 编写总原则

### 3.1 工程约束

- `contract-first`：先定模型、字段、状态、DTO、边界，再写实现。
- `registry-driven`：worker/domain/block/mode/provider/policy 通过配置和注册表驱动，不在主链里散落硬编码。
- `plugin-style composition`：功能尽量通过模块、provider、descriptor、policy 插拔，不靠长 if/else。
- `immutable snapshot`：`RuntimeProfileSnapshot` 不可变；热更新走新 snapshot。
- `turn-as-anchor`：`Turn` 是正文回退锚点；branch/control actions 不进入正文时间线。
- `worker-over-ad-hoc`：memory 治理、上下文治理、retrieval 后处理、章节维护优先落到 worker/helper/policy，不混成临时逻辑。

### 3.2 规格书写作约束

- 先写“公共合同层”，再写可并行模块。
- 不为了追求完整而把不同深度的内容混在一个章节中。
- 每份规格书必须明确：
  - 负责模块
  - 不负责什么
  - 依赖哪些上游合同
  - 输出哪些下游合同
  - 文件落位建议
  - 数据模型/字段
  - 状态/规则
  - 伪代码
  - 测试重点

### 3.3 缺陷检查约束

编写每份规格书时，必须同步检查：

1. 是否与已冻结口径冲突
2. 是否出现新的硬编码倾向
3. 是否把控制面和正文真相层混了
4. 是否把 branch / rollback / turn 语义混了
5. 是否把 worker / scheduler / context orchestration 职责混了
6. 是否使后续并行开发产生明显文件冲突

发现问题时：

- 若能从现有文档直接推导，直接修正文档。
- 若不能安全推导，加入 `story-runtime-architecture-question-queue.md`，按 FIFO grill me。

## 4. 计划产出的规格书模块

## 4.0 总控文档

建议文件：

- `story-runtime-development-master-spec.md`

职责：

- 作为总入口
- 统一术语和真相源
- 给出模块索引
- 给出模块依赖顺序
- 记录跨模块约束

## 4.1 Runtime Identity / Profile

建议文件：

- `story-runtime-identity-profile-spec.md`

负责：

- `StorySession`
- `BranchHead`
- `Turn`
- `RuntimeProfileSnapshot`
- `MemoryRuntimeIdentity`
- control history / snapshot pinning

## 4.2 Runtime Workspace / Job Ledger / Trace

建议文件：

- `story-runtime-workspace-ledger-trace-spec.md`

负责：

- `Runtime Workspace`
- `StoryTurnRecord`
- `RuntimeWorkflowJobRecord`
- materials / receipts / trace refs
- pending / deferred / settled / failed

## 4.3 Worker Registry / Scheduler / Orchestrator

建议文件：

- `story-runtime-worker-scheduler-spec.md`

负责：

- `WorkerDescriptor`
- `WorkerExecutionPlan`
- `WorkerContextPacket`
- `WorkerResult`
- Scheduler validate / dispatch
- Orchestrator structured plan contract

## 4.4 Context Orchestration / Packet

建议文件：

- `story-runtime-context-packet-spec.md`

负责：

- `WritingPacket`
- `WorkerContextPacket` 的 writer-facing / worker-facing 约束
- packet policy
- recent raw turns / core view / sidecars / retrieval cards 的组装与裁剪

## 4.5 WritingWorker / Longform Action Surface

建议文件：

- `story-runtime-writing-worker-spec.md`

负责：

- `WritingWorker`
- `writing / rewrite / discussion / brainstorm`
- longform action surface
- review overlay 接入
- chapter lifecycle actions

## 4.6 Writer-side Retrieval

建议文件：

- `story-runtime-retrieval-spec.md`

负责：

- retrieval cards
- short ids
- expand tool
- usage hook
- knowledge gaps
- bounded retrieval loop

## 4.7 Post-write / Memory Governance

建议文件：

- `story-runtime-postwrite-memory-governance-spec.md`

负责：

- post-write 主链
- projection refresh
- proposal/apply bridge
- Core State 冲突处理
- Recall / Archival materialization
- retrieval used_cards -> memory 治理链

## 4.8 Branch / Rollback

建议文件：

- `story-runtime-branch-rollback-spec.md`

负责：

- rollback anchor
- branch create / switch / delete
- branch control receipts
- fork semantics
- copy-on-write / visibility 语义
- active branch 线性视图规则

## 4.9 Adapter / Debug / Test / Migration

建议文件：

- `story-runtime-adapter-debug-test-spec.md`

负责：

- 最小 branch 面板和前端 adapter 约束
- debug 页面读取面
- 合同测试 / 主链测试 / branch 测试
- 迁移 / rewrite 策略

## 5. 并行开发规划

## 5.1 不可直接并行的公共合同层

以下内容必须先冻结，再允许并行扩散：

1. `StorySession / BranchHead / Turn / RuntimeProfileSnapshot`
2. `Runtime Workspace / StoryTurnRecord / Job Ledger / Trace`
3. `WorkerDescriptor / WorkerExecutionPlan / WorkerContextPacket / WorkerResult`

原因：

- 这些对象是一切下游模块的共同依赖
- 如果边写边改，后续所有模块都会返工

## 5.2 第一批可并行模块

在公共合同层冻结后，可并行推进：

1. `Worker Registry / Scheduler`
2. `Context Orchestration / Packet`
3. `WritingWorker / Longform Action Surface`
4. `Branch / Rollback`

原因：

- 写入边界可拆开
- 依赖关系清晰
- 对接面主要通过已冻结 DTO 和模型完成

## 5.3 第二批可并行模块

在 Workspace / Packet / Scheduler 稳住后，可并行推进：

1. `Writer-side Retrieval`
2. `Adapter / Debug / Read APIs`
3. `Longform chapter/review adapter`
4. `RP/TRPG extension slots`

## 5.4 最后收口模块

最后统一收口：

1. `Post-write / Memory Governance`
2. `Integration tests / migration`

原因：

- 它们耦合最多
- 会依赖 memory、retrieval、scheduler、workspace、writer 全链路
- 太早并行只会反复修改

## 6. 并行冲突控制规则

### 6.1 公共合同冻结

先出一份公共合同总表。内容至少包括：

- 核心模型
- 核心 DTO
- 状态枚举
- 引用/ref 规范
- ownership 规则

冻结后，下游模块只能引用，不允许各自改动口径。

### 6.2 按写入边界分配模块

每份规格书必须写清楚：

- 本模块拥有的文件/目录
- 可修改的模型
- 只读依赖哪些合同
- 对外暴露哪些合同

### 6.3 跨模块改动回总控

如果某个模块发现必须修改公共模型：

1. 先在总控规格书和相应模块规格书中改口径
2. 再回写影响面
3. 不允许单模块私自扩字段或改状态语义

### 6.4 前端/adapter 不反向定义后端语义

- 前端 branch UX
- debug 页面
- 旧 longform adapter

都只能消费已冻结合同，不能反向决定 runtime 数据模型。

## 7. 编写顺序

当前冻结顺序如下：

1. 先写总控规格书
2. 再写公共合同层：
   - Identity / Profile
   - Workspace / Ledger / Trace
   - Worker / Scheduler
3. 再写可并行模块：
   - Context / Packet
   - WritingWorker
   - Branch / Rollback
4. 再写 Retrieval 与 Adapter/Debug
5. 最后写 Post-write / Memory Governance 与 Test/Migration

## 8. 问题处理规则

如果在规格书编写中遇到问题，按下面规则处理：

### 8.1 可直接解决

如果现有讨论文档、PRD、spec coding plan 已能回答：

- 直接按已冻结口径写入规格书
- 必要时修正旧文档漂移

### 8.2 需要 grill me

如果问题会影响：

- 核心数据模型
- branch / rollback / turn 语义
- memory truth / projection / retrieval 边界
- worker / scheduler / context orchestration 的职责
- 并行开发写入边界

且现有文档无法安全回答：

- 把问题追加到 `story-runtime-architecture-question-queue.md`
- 保持 FIFO
- 先确认口径，再继续该部分规格书编写

## 9. 当前执行口径

从这一刻起：

1. 继续推进 story runtime 的方式，转为“模块化开发规格书编写”
2. 编写过程中同步做设计缺陷检查
3. 发现无法从现有讨论中解决的问题，进入 grill 清单
4. 不因为 compact 丢失当前规划；本 memo 作为后续持续遵循的工作约束
