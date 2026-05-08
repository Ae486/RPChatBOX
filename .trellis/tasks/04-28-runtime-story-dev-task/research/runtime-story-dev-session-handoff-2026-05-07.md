# Runtime Story Dev Task Session Handoff (2026-05-07)

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: 给下一 session 一个最短起步路径，快速恢复 story runtime 长线任务的当前状态、真相源、已完成切片、当前阻塞点、以及下一步该做什么。

## 0. 先说结论

当前这条 task 已经不是“继续讨论设计”，而是进入了 **按规格推进实现** 的阶段。

本 session 的主线工作是：

1. 完成 `Phase E2: writer-side bounded retrieval loop`
2. 让真实用户主链 `/api/rp/story-sessions/{session_id}/turn/stream` 不再绕开 E2
3. 对 E2 完成正式 `trellis-check`
4. 同时派只读子代理为下一 slice `F1` 做实现摸底

当前最重要的状态判断：

- `E2` 已完成并已通过正式 `trellis-check`
- 下一 session 的首要任务已经不是收 `E2`，而是：
  - 直接进入 `F1`
  - 但要先读完 `Aquinas` 对 `F1` 的只读摸底结论

## 1. 下一 session 必看文档顺序

不要大面积重读。按下面顺序看，够用了。

### 1.1 第一优先级：执行与总规范

1. [story-runtime-execution-plan.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-execution-plan.md)
   - 看当前切片推进顺序
   - 看主脑规则
   - 看 `Phase E` 当前状态

2. [story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md)
   - 看总模块边界
   - 看并行开发边界
   - 看技术采用矩阵

3. [prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md)
   - 只重点看和 `writer / retrieval / post-write / branch / rollback` 有关的冻结口径

### 1.2 第二优先级：E2 直接相关规格

4. [story-runtime-writing-worker-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md)
5. [story-runtime-retrieval-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-retrieval-spec.md)
6. [story-runtime-context-packet-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md)

### 1.3 第三优先级：下一 slice 预读

7. [story-runtime-postwrite-memory-governance-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-postwrite-memory-governance-spec.md)
8. [story-runtime-workspace-ledger-trace-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-workspace-ledger-trace-spec.md)

## 2. 当前已经明确的工程规则

这一点非常重要，下一 session 不要漂移：

1. 主脑禁止直接编码
   - 只能派发 subagent、收口、审阅、维护 plan、回写文档
   - 业务实现代码和测试代码只能由 subagent 改

2. 同时最多只允许两个正在运行的 subagent

3. 当前已经进入实现阶段，流程固定：
   - `trellis-implement`
   - `trellis-check`
   - `trellis-update-spec`
   - `finish`

4. 每个 coherent spec slice 完成后必须先过 `trellis-check`

5. 用户已经明确允许：
   - 若旧 longform MVP 阻碍新 runtime，可以重写/推翻旧链路
   - 但实现必须按当前 PRD/spec 走，不能再被旧 MVP 反向定义

## 3. E2 已完成状态

### 3.1 E2 要解决的问题

不是 retrieval core 本身，而是：

1. 非流式 `WritingWorkerExecutionService.execute()` 已经具备 bounded retrieval loop
2. 但真实用户主链 `/turn/stream` 仍然会绕开它
3. 如果流式链继续走简化回填 `writing_result`，会丢：
   - `writer_tool_trace_refs`
   - `retrieval_source_ref_bundle`
   - `writer_output_material_id`
   - `token_usage_material_id`
   - 以及其他结构化字段

### 3.2 本 session确认并完成的实现方向

已经和 subagent 对齐过，方向是：

1. 简单 one-shot writer：
   - 继续走原生 `stream_text`

2. 需要 retrieval loop 的流式 turn：
   - 可以接受“先完整执行，再吐 typed SSE”
   - 也就是 buffered stream path

3. 核心要求：
   - 流式主链不再绕开 E2
   - 持久化走完整 `writing_result` 主链
   - 不再依赖简化版 `build_stream_writing_result()` 的字段回填

4. 默认 retrieval allow 已收窄
   - 不能“只要有 identity 就开”
   - 至少应收窄到 `story_segment`
   - 避免把 `chapter_outline` / discussion 默认带进 retrieval loop

### 3.3 当前工作区里已经出现的 E2 相关代码改动

这些文件当前都有改动，下一 session 要重点检查：

1. `backend/rp/services/writing_worker_execution_service.py`
2. `backend/rp/services/story_turn_domain_service.py`
3. `backend/rp/graphs/story_graph_nodes.py`
4. `backend/rp/graphs/story_graph_runner.py`
5. `backend/rp/tests/test_projection_builder_services.py`
6. `backend/tests/test_rp_story_api.py`

### 3.4 已完成的验证

本 session 已经跑过并通过的聚焦验证：

1. `pytest backend/rp/tests/test_projection_builder_services.py -q -k "buffers_when_writer_retrieval_loop_is_enabled or stream_persists_usage_metadata_into_writing_result"`
2. `pytest backend/tests/test_rp_story_api.py -q -k "buffers_writer_retrieval_loop or recovers_after_failed_stream_on_same_thread or runtime_debug_exposes_checkpoint_state"`
3. `ruff check backend/rp/services/writing_worker_execution_service.py backend/rp/services/story_turn_domain_service.py backend/rp/graphs/story_graph_nodes.py backend/rp/graphs/story_graph_runner.py backend/rp/tests/test_projection_builder_services.py backend/tests/test_rp_story_api.py`

另外，`Lorentz` 的正式 `trellis-check` 已给出最终结论：

1. 修正了一个真实问题：
   - 普通 `story_segment` stream 被默认误判为 retrieval-enabled
   - 导致 one-shot non-retrieval stream path 没走 raw streaming
2. 修正方式：
   - `WritingWorkerExecutionService` 默认 `writer_retrieval_allowed=False`
   - `StoryTurnDomainService` 只接受显式 `writer_retrieval_allowed=True`
3. 对应测试也已改为显式开启 retrieval loop，而不是依赖隐式默认

因此：

- `E2` 已正式完成
- 下一 session 不需要再对 `E2` 做收口，只需要在需要时参考这些实现和测试

## 4. 当前 subagent 状态

本 session 后期有两个子代理：

### 4.1 `Lorentz`

- 角色：`trellis-check`
- 模型：`gpt-5.5 xhigh`
- 任务：已完成 `E2` 正式 check

它的最终结论已经体现在本交接文档 `3.4` 中，下一 session 无需再次等待它。

### 4.2 `Aquinas`

- 角色：`explorer`
- 任务：只读摸底下一 slice `F1`

它要回答的问题是：

1. 当前代码里哪些路径已经隐含了 post-write obligations
2. `F1` 的真实锚点文件有哪些
3. creation-time obligations 应该在哪一层登记
4. 哪些测试最接近 `F1`
5. 与 `E2` 的文件重叠风险在哪

下一 session 不要重新做这轮摸底，先等 `Aquinas` 的结果。

### 4.3 `Aquinas` 已返回的核心结论

如果下一 session 读到这份交接文档时，原 thread 已 compact，不必重新等待 `Aquinas`，直接使用下面这些结论：

1. `F1` 目前**没有现成的 obligation ledger 实现**
   - PRD 要求的是 turn-scoped workflow job ledger
   - 但当前 `StoryTurnStatus` 仍只有 `started / completed / failed`
   - `StoryTurnRecord` 也没有 obligation / settlement / deferred 相关字段

2. 当前最接近 `F1 creation-time obligations` 的唯一 owner 边界，是：
   - [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
   - 更具体地说，是 `persist_generated_artifact(...)` 这段 turn-domain 持久化边界
   - 不是 graph node
   - 也不是 `post_write_regression()` 空跳板
   - 也不是 `StoryRuntimeWorkspaceFacade`

3. `E2` 已经把 `F1` 需要消费的最小输入面准备好了
   - `WritingWorkerExecutionResult`
   - `usage_metadata`
   - `retrieval_source_ref_bundle`
   - artifact metadata 里的 retrieval usage bundle
   - Runtime Workspace 的 `WRITER_OUTPUT_REF` / `TOKEN_USAGE_METADATA`

4. 旧的 `LongformRegressionService` 仍然只是参考面
   - 它挂在 accept/complete 流上
   - 不应该直接拿来当通用 post-write orchestrator
   - 更适合作为 `F2` 或 adapter 参考，而不是 `F1 owner`

5. `F1` 与 `E2` 的最高重叠风险文件是：
   - [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
   - [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py)
   - [story_graph_runner.py](H:/chatboxapp/backend/rp/graphs/story_graph_runner.py)
   - [story_runtime_workspace_facade.py](H:/chatboxapp/backend/rp/services/story_runtime_workspace_facade.py)

### 4.4 `Aquinas` 给出的 F1 安全实现边界

下一 session 做 `F1` 时，建议按下面边界控制 scope：

1. **首次登记 creation-time obligations**
   - 放在 `StoryTurnDomainService.persist_generated_artifact(...)`
   - 因为这里只有它同时拥有：
     - artifact 持久化
     - chapter/session 更新
     - surface refs 写入
     - `commit()`

2. **graph 层只负责触发和状态衔接**
   - 不要让 graph node 成为 obligation owner
   - `post_write_regression()` 当前只是空节点，后续可演进为 post-write trigger/dispatch 层

3. **`StoryRuntimeWorkspaceFacade` 继续只做 surface/material write helper**
   - 不要把 turn 真相、status、commit、obligation owner 责任塞进去

4. **F1 的止损边界**
   - 只做：
     - post-write trigger
     - creation-time obligations
     - 与 turn finalization 的衔接
   - 不做：
     - 完整 worker maintenance
     - proposal/projection/recall/archival 实际治理链
   - 那些是 `F2` 的工作

## 5. 下一 session 的推荐起步顺序

严格按这个顺序来，效率最高。

### Step 1

确认当前 task 仍是：

- `.trellis/tasks/04-28-runtime-story-dev-task`

### Step 2

直接读取 `Aquinas` 的只读摸底结果，或直接看本交接文档 `4.3 / 4.4`。

### Step 3

进入 `F1` 前先据此决定：

1. 是否立刻派 `trellis-implement`
2. `F1` 的安全文件边界是什么
3. `F1` 与 `E2` 的重叠修改面如何控制

如果新 session 看不到 `Aquinas` 的原始回包，直接使用本交接文档 `4.3 / 4.4` 的结论即可，不需要重做一次摸底。

## 6. 下一 session 不要做的事

1. 不要重新开一轮大范围设计讨论
2. 不要重新读一遍所有 research 文档
3. 不要主脑自己编码
4. 不要再回头重复收 `E2`，除非新的实现切片明确打破了它
5. 不要同时跑超过两个 subagent

## 7. 最后提醒

当前这条 task 的危险点不是“设计还没想清楚”，而是：

1. 上下文很长
2. 主工作区脏改动很多
3. 很容易把旧 MVP 兼容链和新 runtime 主链混在一起

因此下一 session 的正确做法是：

- 直接进入 `F1`
- 但先用 `Aquinas` 的结论收窄安全实现边界
- 始终只围绕 task 文档和当前 slice 走，不要扩散
