# Story Runtime Adapter / Debug / Test / Migration Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Adapter / Debug / Test / Migration
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- 旧 longform MVP 到新 runtime 的 adapter 原则
- debug 页面和只读审查入口
- 测试矩阵
- 迁移 / 重写 / 回滚策略

这份文档不负责：

- 主链 DTO 的核心语义
- worker/scheduler/context 的基础合同
- retrieval/post-write 的业务规则

## 2. 设计目标

这一层要解决 6 个问题：

1. 旧实现哪些能复用，哪些必须替换
2. 如何让前端先接到最小 branch / debug 入口
3. 如何给 dev session 提供统一的审查/回放入口
4. 如何验证 contract 不会被旧 MVP 链路污染
5. 如何在迁移时保留回滚空间
6. 为什么这层应该最后收口

## 3. 当前实现判断

当前仓库里与本模块最相关的旧实现包括：

- `story_graph_runner.py`
- `story_graph_nodes.py`
- `story_turn_domain_service.py`
- `longform_orchestrator_service.py`
- `longform_specialist_service.py`
- `writing_packet_builder.py`
- `writing_worker_execution_service.py`
- `longform_regression_service.py`
- `story_runtime.py`
- `writing_runtime.py`

这些文件的处理原则是：

- 行为参考
- 兼容 adapter 候选
- 可迁移素材

不是新 runtime 的硬约束。

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/services/story_runtime_controller.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/runtime_read_manifest_service.py`
- `backend/rp/services/runtime_workspace_material_service.py`
- `backend/rp/services/proposal_repository.py`
- `backend/rp/services/memory_trace_read_service.py`
- `backend/rp/services/version_history_read_service.py`

## 4.2 新增文件建议

- `backend/rp/services/story_runtime_debug_service.py`
- `backend/rp/services/story_runtime_debug_query_service.py`
- `backend/rp/services/story_runtime_adapter_service.py`
- `backend/rp/services/story_runtime_test_fixture_service.py`
- `backend/rp/services/story_runtime_migration_service.py`

## 5. Adapter 规则

## 5.1 总原则

推荐策略：

- 新 runtime 为主
- 旧 MVP 为参考
- 能低成本适配且不污染新合同的，允许 adapter
- 适配复杂度高、语义扭曲、会继续把链路拉回 fixed chain 的，直接重写

## 5.2 可接受 adapter

可接受的 adapter 典型场景：

- `LongformSpecialistService` 作为 `LongformMemoryWorker` 的临时 executor
- `LongformOrchestratorService` 作为旧 orchestrator plan 解析入口
- `WritingPacketBuilder` 作为新 context packet builder 的薄封装
- 旧 command surface 作为产品动作兼容入口

## 5.3 不可接受 adapter

不可接受的情况：

- adapter 反向定义新合同
- 为了兼容旧链路，把 worker/scheduler/context 再做回单链固定顺序
- 在 adapter 里复制一份新的 truth model

## 5.4 适配原则

adapter 只能做：

- 数据映射
- 行为桥接
- 旧命令翻译
- 旧结果翻译

不能做：

- 新语义发明
- 模糊推断
- 重型业务决策

## 6. Debug 规格

## 6.1 目标

debug 页面不是产品特性页面，而是开发期和 eval 接入期的只读审查面。

## 6.2 需要暴露的内容

至少包括：

- 当前 active `StorySession / BranchHead / Turn`
- `RuntimeProfileSnapshot`
- writer packet summary
- worker plan / worker result
- Runtime Workspace materials
- retrieval usage / cards / expanded chunks
- proposal / apply receipts
- memory change events
- branch control receipts
- job ledger 状态

## 6.3 前端最小表现

第一版 debug 页面建议支持：

- 按 session / branch / turn 查询
- 展开一次 turn 的主链记录
- 查看 workspace material refs
- 查看 proposal / apply / event / job 关联
- 看当前 branch visibility 下能读到什么

## 6.4 只读边界

debug 页必须只读：

- 不允许直接改 truth
- 不允许直接触发 branch delete / rollback 除非走正式操作入口
- 不允许绕过权限查看不该看的内容

## 7. 测试规格

## 7.1 合同测试

必须覆盖：

- identity/profile 合同
- workspace/job/trace 合同
- worker/scheduler contract
- context/writing packet boundary
- branch/rollback contract
- retrieval usage hook
- post-write gating

## 7.2 运行链路测试

必须覆盖：

1. longform outline generate
2. brainstorm -> summary -> apply -> next writing
3. write -> retrieval -> usage hook -> post-write trigger
4. accept_and_continue -> next turn
5. branch create -> immediate switch
6. rollback -> later content hidden

## 7.3 回归测试

必须覆盖：

- 旧 single specialist 不再作为硬编码主链
- 旧 command surface 仅作为兼容参考
- snapshot 热更新不影响已 started turn
- branch control actions 不创建 turn
- rollback 后，active branch 快照不会暴露 cutoff 之后的 draft/rewrite candidate artifact
- rollback 后，如果 `chapter.pending_segment_artifact_id` 指向隐藏 artifact，snapshot 中的 pending 指针必须返回 `None`
- rewrite candidate 即使没有进入 `visible_output_ref / selected_output_ref`，也必须通过 artifact runtime metadata 归属到 producing `Turn / BranchHead`

## 7.4 Branch / Rollback / LangGraph 能力验证测试

后续 `GraphCheckpointPointer capture / binding` 与 branch/rollback check 必须做能力验证，而不是只看字段或 mock 返回值。最低验证矩阵：

1. settled turn checkpoint binding
   - non-stream 与 stream finalize 后，settled `Turn` 自动持有 branch-scoped `graph_checkpoint_binding`。
   - binding identity 必须匹配 `Turn / BranchHead / RuntimeProfileSnapshot`，且不能由调用方伪造覆盖。
   - 同一 settled turn 已有 checkpoint binding 后，debug/replay/fork 或重复 finalize 只能幂等返回原 binding，不能覆盖应用层回退锚点。
2. rollback receipt checkpoint binding
   - 目标 turn 有 binding 时，`rollback_applied` receipt 自动携带目标 checkpoint binding 或 `target_checkpoint_id`。
   - 目标 turn 无 binding 时，rollback 仍成功，但 receipt 写入 `checkpoint_binding_missing_reason` 或等价稳定 reason。
3. branch control actions stay out of story turns
   - `branch_created` 与 `branch_switched` 不创建 `StoryTurnRecord`。
   - branch create 后立即更新 active branch，但不复制整套 memory / workspace。
4. rollback visibility integrity
   - rollback cutoff 之后的 turns 不再出现在当前 active branch 线性读中。
   - later Runtime Workspace materials、draft/rewrite candidates、pending jobs、packet/window metadata、branch-visible reads 不再污染当前主线。
5. LangGraph shell boundary
   - debug / replay / fork 相关测试只验证 LangGraph checkpoint shell 可用。
   - 任何产品级 branch / rollback / visibility / Memory OS truth 断言都必须落在 RP 应用层 identity、receipt、read manifest、workspace lifecycle 和 memory visibility 上。

## 7.5 测试夹具

建议新增统一测试夹具：

- `StoryRuntimeFixture`
- `IdentityFixture`
- `WorkspaceFixture`
- `BranchFixture`

目标：

- 降低后续 dev session 写测试时的重复搭建成本
- 保持 contract test 独立于旧 MVP 业务数据

## 8. 迁移 / 重写策略

## 8.1 原则

采用 `runtime-first rebuild with selective reuse`。

## 8.2 迁移顺序

建议顺序：

1. 冻结公共合同
2. 建立最小 longform 主链
3. 接 adapter
4. 接 retrieval
5. 接 post-write
6. 最后再补 branch / debug / product UX

## 8.3 回滚策略

每个 slice 必须可单独回退：

- contract slice
- scheduler slice
- retrieval slice
- post-write slice
- branch slice

回滚时优先回到：

- 上一版可用合同
- 上一版可用 adapter
- 而不是强行恢复旧 longform 固定链

## 8.4 第一阶段支持矩阵

### 必须实现

- rollback 合同
- later-content hidden 语义
- branch visibility 所需字段与 receipts
- 最小 debug/read surfaces
- contract / flow / migration 测试矩阵

### 可以预研或预留

- branch create / switch backend preflight
- 最小 branch 面板
- LangGraph fork/replay 接法验证

### 不要求本阶段完整交付

- 完整 branch UI/tree
- 物理 purge 全功能
- branch diff / compare 体验
- 完整 roleplay/trpg branch 产品面

## 9. 伪代码

## 9.1 Adapter decision

```python
def should_use_adapter(old_service, new_contract):
    if old_service.adds_new_semantics():
        return False
    if old_service.recreates_fixed_chain():
        return False
    if old_service_can_map_cleanly_to(new_contract):
        return True
    return False
```

## 9.2 Debug read

```python
def read_turn_debug(turn_id: str):
    turn = load_turn(turn_id)
    workspace = list_workspace_materials(turn.identity)
    jobs = list_jobs(turn_id)
    events = list_events(turn.identity)
    return {
        "turn": turn,
        "workspace": workspace,
        "jobs": jobs,
        "events": events,
    }
```

## 9.3 Test fixture

```python
def build_runtime_fixture():
    session = create_story_session()
    snapshot = ensure_active_snapshot(session.session_id)
    branch = ensure_branch(session)
    turn = start_turn(session.session_id, "user_input")
    return {
        "session": session,
        "snapshot": snapshot,
        "branch": branch,
        "turn": turn,
    }
```

## 10. 已知风险

1. 如果 adapter 层写太厚，会把新 runtime 又拉回旧 MVP fixed chain
2. 如果 debug 页面允许写操作，会把产品控制面和开发审查面混掉
3. 如果测试夹具直接依赖旧 longform session/model，回归测试会掩盖新合同问题
