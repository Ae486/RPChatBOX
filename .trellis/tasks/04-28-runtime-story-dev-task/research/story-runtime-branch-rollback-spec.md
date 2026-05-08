# Story Runtime Branch / Rollback Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Branch / Rollback
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- rollback 语义
- branch create / switch / delete 语义
- branch control receipts
- branch read visibility
- fork 基点规则
- branch 的最小前端表现约束

这份文档不负责：

- LangGraph 内部 checkpoint API 细节
- Runtime Workspace material 模型本体
- post-write job 派发细节
- writer packet 具体内容

## 2. 设计目标

这一层要解决 7 个问题：

1. rollback 和 branch 如何严格区分
2. 为什么 `Turn` 是唯一正文回退锚点
3. branch create / switch / delete 为什么不进入正文时间线
4. 新 branch 从哪一个状态开始
5. branch 切换时为什么旧分支临时材料不能带过来
6. 前端创建 branch 后为什么立即切线
7. branch 删除为什么先隐藏再最终物理删除

## 3. 基础口径

### 3.1 rollback

产品语义：

- 当前主线回到某个旧 `Turn`
- 该 `Turn` 之后的后续内容对当前主线失效 / 不可见
- 之后继续写，会从该点重新长出新的未来

### 3.2 branch

产品语义：

- 从某个历史 turn 开始，保留多条未来
- 两条未来都可以被切换、继续、删除

### 3.3 branch control actions

下列动作都不创建新的 story turn：

- `fork created`
- `branch switched`
- `branch deleted`

它们只写：

- branch/control receipts
- control history
- 必要 trace

### 3.4 统一锚点

- rollback 只认 `Turn`
- branch create 只从 `settled turn` 派生
- 同一 `Turn` 内的内部 revision 都是附属版本，不是独立回退锚点

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/models/runtime_identity.py`
- `backend/rp/services/story_runtime_identity_service.py`
- `backend/rp/services/runtime_memory_persistence_repository.py`
- `backend/rp/services/runtime_read_manifest_service.py`

## 4.2 新增文件建议

- `backend/rp/models/branch_runtime_contracts.py`
- `backend/rp/services/branch_runtime_service.py`
- `backend/rp/services/rollback_runtime_service.py`
- `backend/rp/services/branch_visibility_service.py`

说明：

- LangGraph fork/replay 是底座，不应直接暴露为产品语义
- 产品语义必须通过 branch/runtime 服务统一封装

## 5. 核心对象

## 5.1 BranchHeadRecord

主结构已在 Identity/Profile 规格书中冻结，本规格书只补 branch 语义字段约束：

- `fork_origin_turn_id`
  - 用户点击“从这里分支”的那条历史 turn

- `fork_base_turn_id`
  - 实际 seed 新 branch 的 settled state turn
  - 当前冻结口径：通常是 `fork_origin_turn_id` 开始前的上一条 settled turn

- `head_turn_id`
  - 当前 branch 最新 turn

- `last_settled_turn_id`
  - 当前 branch 最近 settled turn

关键约束：

- `fork_origin_turn_id` 与 `fork_base_turn_id` 必须同时保留
- 后续 debug / branch panel / replay 都需要同时知道“用户从哪条消息点的分支”和“新 branch 实际从哪个状态起步”

## 5.2 BranchControlReceipt

建议新增一类 receipt 记录。

建议字段：

- `receipt_id: str`
- `session_id: str`
- `story_id: str`
- `branch_head_id: str`
- `control_kind: str`
  - `branch_created`
  - `branch_switched`
  - `branch_deleted`
  - `rollback_applied`

- `actor: str`
- `fork_origin_turn_id: str | None`
- `fork_base_turn_id: str | None`
- `from_branch_head_id: str | None`
- `to_branch_head_id: str | None`
- `target_turn_id: str | None`
- `source_ref_ids: list[str]`
- `result_ref_ids: list[str]`
- `trace_refs: list[str]`
- `metadata_json: dict`
- `created_at: datetime`

关键约束：

- receipt 是控制动作记录
- 不是新的正文时间线节点

## 5.3 BranchVisibilitySnapshot

第一阶段不一定单独落表，但读取时需要明确这类概念。

建议最小字段：

- `branch_head_id`
- `visible_lineage_branch_ids`
- `visible_turn_head_id`
- `visible_turn_cutoff_id`
- `visible_story_state_revision_refs`
- `visible_workspace_scope`

用途：

- 统一 branch-aware read
- debug / replay / retrieval filter / packet build 读取同一份可见范围语义

## 6. 运行规则

## 6.1 rollback 规则

1. rollback 目标必须是当前 branch 上某个已完成 `Turn`
2. rollback 不创建新的 branch
3. rollback 不创建新的 story turn
4. rollback 结果是：
   - 当前 `BranchHead.head_turn_id` 回到目标 turn
   - 当前分支在目标 turn 之后的后续消息、workspace、memory materialization、projection、packet metadata 全部失效 / 不可见
5. rollback 不回退 snapshot 和其他控制面配置

## 6.2 branch create 规则

1. 只能从 `settled turn` 派生
2. 语义上是“从这一轮开始改写未来”
3. 因此分支锚点是：
   - `fork_origin_turn_id = 用户点的历史 turn`
   - `fork_base_turn_id = 该 turn 开始前，也就是上一条 settled turn`
4. 创建后立即切换到新 branch
5. 新 branch 创建时：
   - 不复制整套 memory
   - 只创建新的 branch head
   - 共享 fork 前 settled 历史

## 6.3 branch switch 规则

1. branch switch 不创建新的 story turn
2. 切换后：
   - `StorySession.active_branch_head_id` 更新
   - 主聊天区按新 branch 线性重建
3. 不携带原分支 fork 后的：
   - Runtime Workspace materials
   - worker candidates
   - pending jobs
   - unfinished post-write results

## 6.4 branch delete 规则

第一阶段产品语义：

- 分支删除后，对用户不可见

工程实现分两层：

1. 第一阶段可先做 deleted / hidden 标记
2. 最终能力必须支持物理删除 branch-only 数据

物理删除范围只包括：

- fork 后该分支独占的 Runtime Workspace
- worker candidate
- pending records
- branch-specific Core State revision
- projection block views
- Recall / Archival materialization
- packet/window metadata
- retrieval derived records
- 分支专属 trace

禁止删除：

- fork 前共享 settled memory
- story-global Archival Knowledge
- 其他分支仍可见的记录

## 7. 可见性规则

## 7.1 branch-aware reads

所有运行期读都必须绑定：

- `session_id`
- `branch_head_id`
- `turn_id`

读取时按 active branch visibility 过滤：

- memory read
- retrieval filter
- Runtime Workspace read
- packet/window metadata read
- artifact / discussion read

### 7.1.1 artifact / pending candidate visibility

writer 产物和 rewrite candidate 必须带运行时归属 metadata，至少能回答：

- `runtime_session_id`
- `runtime_branch_head_id`
- `runtime_turn_id`
- `runtime_profile_snapshot_id`

原因：

- 并不是所有 candidate 都会同时出现在 `StoryTurnRecord.visible_output_ref / selected_output_ref`。
- rollback 后，仅按 turn output ref 反查 artifact 会漏掉没有成为 visible/selected output 的 rewrite candidate。
- active branch 快照必须能隐藏 fork/rollback cutoff 之后的 candidate artifact。

读取 `ChapterWorkspaceSnapshot` 时必须同时满足：

1. artifact 自身 runtime metadata 指向的 `runtime_turn_id` 在当前 active branch 可见集合内；或
2. artifact 能通过 turn output ref 反查到当前 active branch 可见 turn；或
3. artifact 没有 runtime turn 归属，只能作为旧兼容数据按保守路径展示。

如果 `chapter.pending_segment_artifact_id` 指向的 artifact 被 branch visibility 过滤隐藏，返回给前端的 snapshot 必须把 pending 指针视为 `None`。不能让隐藏 candidate 继续污染 pending candidate selector、rewrite target 或 `accept_and_continue`。

## 7.2 retrieval 规则

retrieval index 是派生产物，不是 story truth。

因此：

- branch create 不复制整套索引
- retrieval 通过 branch/turn visibility 过滤内容真相
- reindex 是后续异步维护，不改变 story truth

## 7.3 Runtime Workspace 规则

- Runtime Workspace 是 branch-scoped
- branch switch 后，原 branch 的临时材料不能进入新 branch 主视图
- 新 branch 只读取：
  - fork 前共享 settled truth
  - 本 branch 自己的 workspace / pending / candidate

## 8. 最小前端约束

## 8.1 主聊天区

第一版主聊天区：

- 只显示当前 active branch 的线性 `Turn` 历史
- 不直接渲染重树状图

## 8.2 分支入口

每条历史消息的操作菜单中提供：

- `从这里分支`

禁止使用：

- “从这里继续”
- 模糊的通用按钮同时表示回退和分支

## 8.3 创建分支后的 UX

冻结口径：

1. 创建后立即切换到新 branch
2. fork 点之后旧分支后续消息从主视图消失
3. 顶部显示当前 branch 标识
4. fork 点处显示轻量提示条
5. branch 面板显示：
   - 当前 branch
   - fork 起点
   - origin branch

## 8.4 回退与分支动作必须分开

第一版产品动作必须强区分：

- `回退到这里`
- `从这里分支`

不能混成：

- “从这里继续”

## 9. 伪代码

## 9.1 创建分支

```python
def create_branch_from_turn(session_id: str, origin_turn_id: str, actor: str):
    session = load_story_session(session_id)
    origin_turn = load_turn(origin_turn_id)
    assert origin_turn.status == "settled"

    base_turn = resolve_previous_settled_turn(origin_turn_id)

    branch = BranchHeadRecord(
        branch_head_id=new_id(),
        session_id=session_id,
        story_id=session.story_id,
        parent_branch_head_id=origin_turn.branch_head_id,
        fork_origin_turn_id=origin_turn.turn_id,
        fork_base_turn_id=base_turn.turn_id if base_turn else None,
        head_turn_id=base_turn.turn_id if base_turn else None,
        last_settled_turn_id=base_turn.turn_id if base_turn else None,
        status="active",
        visibility_state="visible",
    )
    save_branch(branch)
    session.active_branch_head_id = branch.branch_head_id
    save_story_session(session)

    write_branch_control_receipt(
        session_id=session_id,
        branch_head_id=branch.branch_head_id,
        control_kind="branch_created",
        actor=actor,
        fork_origin_turn_id=origin_turn.turn_id,
        fork_base_turn_id=base_turn.turn_id if base_turn else None,
        from_branch_head_id=origin_turn.branch_head_id,
        to_branch_head_id=branch.branch_head_id,
    )
    return branch
```

## 9.2 切换分支

```python
def switch_branch(session_id: str, target_branch_head_id: str, actor: str):
    session = load_story_session(session_id)
    current_branch_id = session.active_branch_head_id
    session.active_branch_head_id = target_branch_head_id
    save_story_session(session)
    write_branch_control_receipt(
        session_id=session_id,
        branch_head_id=target_branch_head_id,
        control_kind="branch_switched",
        actor=actor,
        from_branch_head_id=current_branch_id,
        to_branch_head_id=target_branch_head_id,
    )
```

## 9.3 rollback

```python
def rollback_to_turn(session_id: str, target_turn_id: str, actor: str):
    session = load_story_session(session_id)
    branch = load_branch_head(session.active_branch_head_id)
    target_turn = load_turn(target_turn_id)
    assert target_turn.branch_head_id == branch.branch_head_id
    assert target_turn.status == "settled"

    branch.head_turn_id = target_turn.turn_id
    branch.last_settled_turn_id = target_turn.turn_id
    save_branch(branch)

    hide_branch_results_after_turn(
        branch_head_id=branch.branch_head_id,
        target_turn_id=target_turn.turn_id,
    )

    write_branch_control_receipt(
        session_id=session_id,
        branch_head_id=branch.branch_head_id,
        control_kind="rollback_applied",
        actor=actor,
        target_turn_id=target_turn.turn_id,
    )
```

## 10. 测试点

1. rollback 后当前 branch 只剩目标 turn 之前的线性历史
2. rollback 不改变 active snapshot
3. branch create 后立即切换到新 branch
4. branch switch 不创建新的 story turn
5. fork 前共享 truth 在新旧 branch 都可见
6. fork 后旧 branch 的 pending/workspace 不进入新 branch
7. branch delete 不会删掉共享 settled memory

## 11. 已知风险

1. `fork_base_turn_id` 的恢复逻辑如果只靠前端传参，容易漂移；实现时应由后端 deterministic resolve
2. LangGraph fork 与应用层 branch create 必须明确区分，不要把底层 checkpoint id 直接当产品 branch id
3. rollback 的“失效/不可见”与“最终物理删除”必须分阶段实现，不能一开始就把物理删除和产品语义耦死
