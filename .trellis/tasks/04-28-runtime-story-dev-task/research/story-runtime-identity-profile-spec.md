# Story Runtime Identity / Profile Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Runtime Identity / Profile
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结 story runtime 的身份和配置真相层：

- `StorySession`
- `BranchHead`
- `RuntimeProfileSnapshot`
- `RuntimeControlHistory`
- `MemoryRuntimeIdentity`

这份文档不负责：

- worker/scheduler 细节
- Runtime Workspace child materials
- retrieval cards
- post-write 治理流程
- front-end branch UX 细节

## 2. 设计目标

身份层要解决 5 个问题：

1. 每一轮 runtime 到底属于哪个 session / branch / turn / snapshot
2. 配置热更新如何不污染已开始的 turn
3. branch 创建、切换、删除如何不进入正文时间线
4. 回退为什么只认 `Turn`
5. 多模块如何共享统一 identity，而不是各自拼 `session_id`

## 3. 文件落位建议

## 3.1 复用现有文件

- `backend/rp/models/runtime_identity.py`
  - 继续承载 typed identity contract 和 compiled snapshot contract

- `backend/rp/services/story_runtime_identity_service.py`
  - 继续承载 turn start pin / branch identity resolve

- `backend/rp/services/runtime_profile_snapshot_service.py`
  - 继续承载 snapshot compile / publish / activate

## 3.2 新增文件建议

- `backend/rp/models/story_runtime_records.py`
  - canonical persistent record models

- `backend/rp/services/runtime_control_history_service.py`
  - control history / branch control receipts 写入服务

说明：

- 现有 `backend/rp/models/story_runtime.py` 仍可保留作为 longform MVP adapter，但不再继续扩写为新 runtime 真相模型。

## 4. 核心对象边界

## 4.1 StorySession

产品语义：

- 一个故事运行会话
- 拥有 mode、当前活动分支、当前活动 snapshot、控制面配置入口

不承担：

- 正文回退锚点
- branch 隔离边界
- 当前轮 child materials 真相

## 4.2 BranchHead

产品语义：

- 一条故事未来
- 负责当前 branch 的位置和可见范围

不承担：

- 控制面配置真相
- turn child materials 的直接持久化

## 4.3 RuntimeProfileSnapshot

产品语义：

- 一次发布后的不可变运行配置
- 由 `ModeProfile + worker config + runtime config` 编译而成

不承担：

- 动态草稿配置
- branch 专属正文状态

## 4.4 RuntimeControlHistory

产品语义：

- 记录控制面动作
- 例如 snapshot 发布/激活、branch create/switch/delete、worker 配置更新

关键约束：

- control actions 不创建新的 story turn
- control actions 不进入正文回退锚点

## 4.5 MemoryRuntimeIdentity

产品语义：

- memory / retrieval / workspace / proposal / trace 的统一最小身份包

关键约束：

- 所有运行期 memory 读写都必须拿到完整 identity
- 禁止只靠 `session_id` 读写 runtime 数据

## 5. 数据模型

## 5.1 StorySessionRecord

建议字段：

- `session_id: str`
  - 主键

- `story_id: str`
  - 所属故事

- `source_workspace_id: str`
  - activation 来源工作区

- `mode: str`
  - longform / roleplay / trpg

- `session_state: str`
  - `bootstrapping | active | paused | completed | archived`

- `active_branch_head_id: str`
  - 当前活跃 branch

- `active_runtime_profile_snapshot_id: str`
  - 下一次新 turn 默认要 pin 的 snapshot

- `runtime_story_config_json: dict`
  - 兼容草稿来源，只作为 control plane draft source
  - 不再作为 active runtime 真正执行配置源

- `writer_contract_json: dict`
  - 当前 writer 合同草稿/缓存

- `metadata_json: dict`
  - 扩展位

- `activated_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

约束：

- `StorySession` 拥有当前 active snapshot 和 active branch
- branch 切换会更新 `active_branch_head_id`
- snapshot 激活会更新 `active_runtime_profile_snapshot_id`

## 5.2 BranchHeadRecord

建议字段：

- `branch_head_id: str`
  - 主键

- `session_id: str`
- `story_id: str`

- `parent_branch_head_id: str | None`
  - 从哪条分支 fork

- `fork_origin_turn_id: str | None`
  - 用户点击“从这里分支”的那条历史 turn

- `fork_base_turn_id: str | None`
  - 实际用于 seed 新 branch 的 settled state 对应 turn
  - 根据已冻结口径，通常是 `fork_origin_turn_id` 开始前的上一条 settled turn

- `head_turn_id: str | None`
  - 当前 branch 上最新 turn

- `last_settled_turn_id: str | None`
  - 当前 branch 上最近一个已 settled 的 turn

- `status: str`
  - `active | superseded`

- `visibility_state: str`
  - `visible | hidden | deleted`

- `created_by_control_event_id: str | None`
  - 关联 branch create receipt

- `metadata_json: dict`

- `created_at: datetime`
- `updated_at: datetime`

约束：

- 创建 branch 后立即切换到新 branch
- 主聊天区只展示当前 `active_branch` 的线性 turn 历史
- branch create / switch / delete 都不创建新的 story turn

## 5.3 RuntimeProfileSnapshotRecord

建议字段：

- `runtime_profile_snapshot_id: str`
  - 主键

- `session_id: str`
  - snapshot 属于 session control plane

- `snapshot_version: int`
  - session 内递增

- `status: str`
  - `draft | active | superseded`

- `compiled_profile_json: RuntimeProfileSnapshotCompiledProfile`
  - 使用 typed contract 持久化

- `source_mode: str`
- `source_mode_profile_ref: str | None`
- `source_mode_profile_version: int | None`
- `source_worker_config_ref: str | None`

- `created_by_control_event_id: str | None`

- `metadata_json: dict`

- `created_at: datetime`
- `activated_at: datetime | None`
- `superseded_at: datetime | None`

关键约束：

- snapshot 是 session-scoped，不是 branch-scoped
- rollback / branch switch 不回退 snapshot
- 新 turn 在开始时 pin 当前 session 的 active snapshot
- 已开始 turn 与其 post-write jobs 继续使用旧 snapshot，不中途迁移

### RuntimeProfileSnapshotCompiledProfile 最小 schema

`compiled_profile_json` 不允许继续由不同服务各自猜字段。第一阶段冻结最小 schema：

- `mode_profile`
- `domain_activation`
- `block_activation`
- `worker_activation`
- `permission_profile`
- `retrieval_policy`
- `context_policy`
- `packet_policy`
- `writer_policy`
- `post_write_policy`
- `budget_latency_policy`
- `writer_model_profile`
- `worker_model_profiles`
- `mode_specific_settings`

约束：

- scheduler、packet builder、writer、post-write 只能从已 pin 的 snapshot 读取这些策略
- `StorySession.runtime_story_config_json` 和其他草稿配置只能作为 compile source，不允许被 runtime execution 直接读取

## 5.4 RuntimeControlHistoryRecord

建议字段：

- `control_event_id: str`
  - 主键

- `session_id: str`

- `branch_head_id: str | None`
  - branch control actions 可带

- `control_kind: str`
  - 推荐最小枚举：
    - `runtime_profile_published`
    - `runtime_profile_activated`
    - `worker_config_updated`
    - `branch_created`
    - `branch_switched`
    - `branch_deleted`

- `actor: str`
  - `user` / `system` / `service:<name>`

- `source_ref_ids: list[str]`
- `result_ref_ids: list[str]`

- `payload_json: dict`
- `metadata_json: dict`

- `created_at: datetime`

关键约束：

- 只记录控制面动作
- 不承担正文回退锚点
- 可供 debug / audit / branch panel 读取

## 5.5 MemoryRuntimeIdentity

当前 [memory_contract_registry.py](H:/chatboxapp/backend/rp/models/memory_contract_registry.py) 已有最小结构：

- `story_id`
- `session_id`
- `branch_head_id`
- `turn_id`
- `runtime_profile_snapshot_id`

第一阶段继续沿用，不再缩减。

## 6. 运行规则

## 6.1 Turn start pinning

规则：

1. 读取 `StorySession.active_branch_head_id`
2. 读取 `StorySession.active_runtime_profile_snapshot_id`
3. 创建本轮 `Turn`
4. 生成 `MemoryRuntimeIdentity`
5. 后续 memory / retrieval / workspace / proposal / trace 全部携带该 identity

禁止：

- turn 运行过程中切换 snapshot
- post-write job 自行读取“最新配置”替代 turn 已 pin snapshot

## 6.2 Branch 与 snapshot 的关系

第一阶段冻结口径：

- branch 是正文和 memory 可见状态的分叉
- snapshot 是 session 级控制面配置
- branch create / switch 不会自动切到旧 snapshot
- 从历史位置创建新 branch 后，后续新 turn 使用当前 session 的 active snapshot

这是由“配置侧不参与 story rollback”直接推导出的实现规则。

## 6.3 Branch control actions

以下动作都不创建新的 story turn：

- `branch_created`
- `branch_switched`
- `branch_deleted`

它们只写：

- control history
- branch receipts
- 必要 trace

## 6.4 Rollback 与 identity

rollback 不创建新的 branch control snapshot，也不创建新的 story turn。

rollback 的结果是：

- 当前 `BranchHead` 回到目标 `Turn`
- 目标 `Turn` 之后的消息、workspace、memory materialization、view 更新对当前分支失效/不可见
- snapshot 和控制面配置不回退

## 7. 伪代码

## 7.1 发布新 snapshot

```python
def publish_runtime_profile_snapshot(session_id: str, compiled_profile: dict, actor: str):
    session = load_story_session(session_id)
    next_version = allocate_next_snapshot_version(session_id)
    snapshot = RuntimeProfileSnapshotRecord(
        runtime_profile_snapshot_id=new_id(),
        session_id=session_id,
        snapshot_version=next_version,
        status="draft",
        compiled_profile_json=compiled_profile,
        created_by_control_event_id=None,
    )
    save_snapshot(snapshot)
    event = write_control_history(
        session_id=session_id,
        control_kind="runtime_profile_published",
        actor=actor,
        result_ref_ids=[f"snapshot:{snapshot.runtime_profile_snapshot_id}"],
    )
    attach_control_event(snapshot, event.control_event_id)
    return snapshot
```

## 7.2 激活 snapshot

```python
def activate_runtime_profile_snapshot(session_id: str, snapshot_id: str, actor: str):
    session = load_story_session(session_id)
    snapshot = load_snapshot(snapshot_id)
    mark_old_active_snapshot_superseded(session_id)
    mark_snapshot_active(snapshot_id)
    session.active_runtime_profile_snapshot_id = snapshot_id
    save_story_session(session)
    write_control_history(
        session_id=session_id,
        control_kind="runtime_profile_activated",
        actor=actor,
        result_ref_ids=[f"snapshot:{snapshot_id}"],
    )
```

## 7.3 开始新 turn

```python
def start_turn(session_id: str, command_kind: str) -> MemoryRuntimeIdentity:
    session = load_story_session(session_id)
    branch = load_branch_head(session.active_branch_head_id)
    snapshot = load_snapshot(session.active_runtime_profile_snapshot_id)
    turn = create_story_turn(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        command_kind=command_kind,
    )
    return MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id=branch.branch_head_id,
        turn_id=turn.turn_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
```

## 8. 测试点

1. 新 turn 总是 pin 当前 active snapshot
2. snapshot 热更新后，已开始 turn 继续使用旧 snapshot
3. branch create 后立即切换 active branch
4. branch switch 不创建新的 story turn
5. rollback 不改变 active snapshot
6. `MemoryRuntimeIdentity` 始终包含完整五元组

## 9. 当前已知风险

1. `story_runtime.py` 仍承载大量 longform MVP 模型，后续迁移要避免新合同继续污染旧文件
2. branch create 的 `fork_origin_turn_id` 与 `fork_base_turn_id` 必须同时保留，避免后续实现只记一个字段导致语义丢失
3. snapshot session-scoped 的规则必须在 branch/rollback 实现时保持一致，不能偷偷回滚配置
