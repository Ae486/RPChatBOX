# Story Runtime Stage W Brainstorm Product Loop Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Stage: W
>
> Scope: W0-W4, Writer Brainstorm Product Loop + Fresh Seed Validation
>
> Status: development-spec-v1

## 1. 结论

Stage W 的第一轮实现目标是把 writer brainstorm 的产品前半段打通：

1. 用 fresh legal longform seed 先验证 Memory direct edit 基线；
2. 让 writer brainstorm 可以真实讨论；
3. 让用户显式点击“总结变更项”后生成一版可编辑表单；
4. 让用户审查、编辑、新增、删除/恢复表单条目；
5. 让用户按 batch 提交处理，并把 batch 冻结为 `pending_processing`；
6. 不在 W1-W4 执行真实 scheduler / worker / memory mutation。

一句话：**Brainstorm 只负责讨论并产出用户可编辑表单；表单是否提交由用户决定；提交后的真实 memory 行为由后续调度层决定。**

## 2. 非目标

W1-W4 不做：

- 不实现真实 scheduler / worker dispatch；
- 不创建真实 scheduler job；
- 不写 `RuntimeWorkflowJobRecord`；
- 不进入 post-write governance ledger；
- 不修改 Core / Recall / Archival；
- 不让 brainstorm 输出 memory routing 字段；
- 不把 brainstorm discussion 或表单注入 writer context；
- 不做完整历史 brainstorm 管理器；
- 不做 legacy session repair / backfill。

W5 才消费 `pending_processing` batch / item，并决定这些用户意图是否能形成
Core State 变更、应由哪个 Core domain owner worker 处理、需要哪些 evidence、以及
冲突怎么处理。

W5 的调度层 / worker 口径必须按 Memory OS 设计理解：

- 调度层不是 Core / Recall / Archival 三层路由器；
- worker 首要管理 Core State 的 `authoritative_state` 和
  `derived_projection`，不是管理 Recall / Archival durable writes；
- Recall Memory / Archival Knowledge 是可通过 Retrieval Broker / 工具召回的
  evidence source；
- Recall / Archival 命中只有经 Core owner worker 判断、permission /
  proposal / apply 治理后，才可能换入 Core State 当前事实；
- Archival source 本体变更仍走 Story Evolution / ingestion / reindex；
- Recall lifecycle 仍走 Recall review / recompute / invalidate / supersede；
- 实现讨论中不得把 W5 问成“worker 要处理哪些 memory layer”。

W5 的详细调度层规格见：

- [story-runtime-stage-w5-scheduler-layer-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-stage-w5-scheduler-layer-development-spec.md)

当前已确认的调度层口径：

- W5 不是 brainstorm-only consumer，而是通用 scheduler / worker foundation
  的第一条产品入口；
- brainstorm `pending_processing` item 是一种 trigger；
- accepted prose 每 `K` 个 confirmed story segment 形成一个维护窗口；
- `K` 不统计大纲、draft、未确认 rewrite candidate、discussion 或 brainstorm；
- branch / rollback 后以 active branch 可见的 accepted segment index 为准；
- chapter close 可 flush 不足 `K` 的尾部窗口；
- scene close 不触发、不截断窗口；
- manual flush 允许，第一版可先作为 internal/debug trigger；
- accepted prose 窗口内用 `1..N` 段落短编号给 orchestrator 使用，工具侧再映射回真实 source refs；
- Scheduler Decision 负责校验和最终裁决，orchestrator 只做结构化提案；
- 调度层必须模块化、registry-driven、可维护，不允许所有逻辑堆在单个 service。

### 2.1 Legacy V4 语义隔离

旧 V4 代码和旧 development spec 里的这些术语不再定义 W1-W4 产品语义：

- `confirmed`
- `rejected`
- `dispatched`
- `pending_review`
- `apply_confirmed`
- `brainstorm_summary_apply`
- `/brainstorm/sessions/{brainstorm_id}/apply`

W1-W4 的用户提交语义只有：

- `batch: draft -> pending_processing`
- `item: active/deleted -> pending_processing`

其中：

- `active` item 随 batch submit 进入 `pending_processing`；
- `deleted` item 保留历史展示，但绝不提交给后续调度；
- `pending_processing` 只是 Brainstorm 自身状态，不代表已创建 scheduler job，也不代表 memory 已变更。

旧 `/apply` 路由不能被小修成 W1-W4 submit。实现时必须新增或等价提供 batch submit 语义；旧 apply 路由要么留作 W5-only 内部/兼容路径，要么从 W1-W4 前端产品路径完全断开。

## 3. 核心边界

### 3.1 Writer

Writer 负责用户可见正文或正文候选：

- `writing` 输出 story segment candidate / visible output；
- `rewrite` 输出 rewrite candidate / review overlay；
- accepted flow 才进入 canonical story body。

Writer context 只能包含当前 branch-visible canonical story state、outline、accepted segments、beat、read manifest、已治理 memory 等。

Writer context **不得包含**：

- 当前 brainstorm raw discussion；
- 未提交的 brainstorm batch；
- `pending_processing` brainstorm item；
- 用户已删除的 brainstorm item；
- 任何未被 scheduler / worker / governed mutation 落地的意图。

### 3.2 Writer Brainstorm

Writer brainstorm 是 writer 的 discussion persona / mode，不是 Memory worker，也不是 Core editor。

它负责：

- 和用户讨论设定、人物、伏笔、章节方向、记忆变更意图；
- 信息不清楚时继续追问用户；
- 用户显式点击“总结变更项”时，把当前 brainstorm context window 总结为一版表单；
- 表单字段只表达用户意图概述。

它不负责：

- 判断 Core / Recall / Archival；
- 产出 field path / operation / old value / new value；
- 决定 memory 能否改；
- 直接提交 proposal / apply；
- 直接刷新 projection；
- 直接产出正文段落。

### 3.3 Context Window Flush

Brainstorm context window 使用两个用户动作作为 flush 边界：

| 用户动作 | 对当前 brainstorm context window 的影响 | 是否产出表单 |
|---|---|---|
| 点击“总结变更项” | flush 当前 brainstorm discussion context | 是，产出一个 batch |
| 点击“续写” | flush 当前 brainstorm discussion context | 否 |

flush 后：

- 已 flush 的 raw discussion 只做历史留痕；
- 默认不进入下一次 brainstorm LLM 输入；
- 不进入 writer context；
- 下一次 brainstorm 使用当前 writer canonical context + 新 active brainstorm window。

### 3.4 Brainstorm Context Window 持久化

实现必须显式区分 active brainstorm context window 与 flushed historical windows。

建议最小字段：

```python
class BrainstormContextWindow(BaseModel):
    window_id: str
    brainstorm_id: str
    session_id: str
    branch_head_id: str
    turn_id: str | None
    runtime_profile_snapshot_id: str | None
    status: Literal["active", "flushed"]
    flush_reason: Literal["summarize", "continue_writing"] | None = None
    flushed_at: datetime | None = None
    source_message_refs: list[str] = Field(default_factory=list)
```

要求：

- active window 是下一次 brainstorm LLM 可见的唯一 brainstorm discussion window；
- summarize 使用当前 active window 生成 batch 后，必须把该 window 标记为 flushed；
- continue-writing 使用当前 active window 时不生成 batch，但同样必须把该 window 标记为 flushed；
- flushed window 可用于历史展示、debug 和 audit，但默认不再进入后续 brainstorm prompt；
- flushed window 不得进入 writer packet。

如果实现选择复用现有 `StoryDiscussionEntry` 承载 brainstorm 气泡，必须给记录加足够明确的 mode/window/flush metadata，并确保 writer packet builder 和普通 discussion view 的读取路径能排除 flushed 或 brainstorm-only 记录。更推荐将 brainstorm discussion 存在 Brainstorm/Runtime Workspace scratch 语义下，避免与普通 writer discussion 混线。

### 3.5 Writer Packet 排除规则

Writer packet / context orchestration 必须 fail closed 排除以下材料：

- active brainstorm raw discussion；
- flushed brainstorm raw discussion；
- draft brainstorm batch；
- deleted brainstorm item；
- `pending_processing` brainstorm item；
- `pending_processing` brainstorm batch；
- 任何未被 W5 scheduler / worker / governed mutation 落地的 brainstorm 意图。

不得通过以下 fallback 把 brainstorm 材料混入 writer context：

- 通用 `StoryDiscussionEntry` recent entries；
- Runtime Workspace sidecar material；
- artifact metadata reverse lookup；
- branch inspect/debug payload；
- read manifest omitted/deferred notes。

测试必须证明：一次 brainstorm discussion 被 summarize 或 continue flush 后，下一次 writer generation / rewrite 的 packet 不包含该 raw discussion、draft batch、deleted item 或 pending_processing item。

## 4. W0 Fresh Seed Validation

目标：确认 Memory direct edit 在 fresh legal longform session 上是否通过。

要求：

- 使用 fresh legal longform seed；
- 只测 fresh session 的 Core memory direct edit；
- 如果通过，把旧手测 session 报错归类为 legacy hand-test 数据问题；
- 如果失败，升级为 Stage W 前置逻辑 bug，先修该 bug；
- 不先做 legacy session repair / backfill。

推荐验证：

```powershell
python -m pytest backend\rp\tests\test_legal_longform_session_seed.py -q --tb=short
```

## 5. W1-W4 产品形态

### 5.1 UI 落点

Brainstorm 对话本身继续放在 `LongformStoryPage` 右侧 `Discussion / Review` 区域。

Brainstorm 产出的表单使用 **常驻入口 + 小窗页面**：

- 入口常驻在 `Discussion / Review` 区域；
- 无条目时显示空态，例如 `Brainstorm 变更项 · 暂无`；
- 有 batch / item 时显示聚合状态；
- 点击入口打开表单小窗；
- 小窗按 batch 展示表单；
- 完成、提交、失败提示复用 `OwuiSnackBars`。

`Memory` panel 不承载 W1-W4 表单。它只在 W5 之后展示 Core governed
mutation、projection refresh、retrieval evidence / deferred reason 等治理结果。

### 5.2 Batch

一次用户点击“总结变更项”产出一个 batch。

Batch 语义：

- batch 是一版表单；
- batch 下挂本次 summarize 产出的 items；
- 用户可在 batch 内新增 item；
- batch 提交前可编辑；
- batch 提交后整体冻结；
- batch 提交后进入 `pending_processing`；
- W1-W4 不把 batch 转换为真实 scheduler job。

建议 batch 状态：

| 状态 | 含义 |
|---|---|
| `draft` | 可编辑，未提交 |
| `pending_processing` | 已提交处理，整体冻结，等待 W5 |
| `completed` | W5 或之后真实处理完成 |
| `failed` | W5 或之后处理失败 |
| `conflict` | W5 或之后发现冲突 |

W1-W4 只需要稳定实现 `draft -> pending_processing`。

### 5.3 Item

Item 是用户意图概述，不是 memory patch。

Item 最小字段：

```python
class BrainstormItemDraft(BaseModel):
    text: str
```

后端固定逻辑补齐：

- `item_id`
- `batch_id`
- `brainstorm_id`
- `session_id`
- `branch_head_id`
- `turn_id`
- `runtime_profile_snapshot_id`
- `source_kind`
- `status`
- `created_at`
- `updated_at`

Item 不允许包含：

- `target_layer`
- `target_domain`
- `operation_kind`
- `intent_labels`
- `field_path`
- `old_value`
- `new_value`
- Core / Recall / Archival routing 字段。

建议 item 状态：

| 状态 | 含义 |
|---|---|
| `active` | 未删除，batch 提交时会进入待处理集合 |
| `deleted` | 用户删除，保留展示但不提交 |
| `pending_processing` | batch 已提交，item 冻结并等待 W5 |
| `completed` | W5 或之后处理完成 |
| `failed` | W5 或之后处理失败 |
| `conflict` | W5 或之后发现冲突 |

没有 `pending_confirmation / confirmed` 状态。用户审查通过编辑、删除/恢复、新增来表达，不需要逐条确认。

### 5.4 删除 / 恢复

删除语义：

- 删除不是硬删除；
- 删除后 item 保留在表单中；
- UI 使用划去 / 减淡展示；
- 删除后 item 不可编辑；
- 删除可恢复；
- 删除 item 绝不能上传到调度层；
- 后端 submit 必须过滤并校验 deleted items，不能只依赖前端。

UI 建议：

- item 默认展示为 `编号 + 可编辑内容`；
- 删除按钮不常驻，item hover / focus / selected 时在右侧浮出 icon button；
- deleted item hover / selected 时显示恢复按钮；
- deleted item 使用 opacity + line-through；
- batch 提交后所有编辑、删除、恢复入口隐藏。

### 5.5 新增

用户可以手动新增 item。

规则：

- 新增 item 默认 `active`；
- `source_kind=user_added` 或等价来源；
- 与 LLM 生成 item 一样参与 batch 提交；
- 用户新增 item 也不能携带 routing / patch 字段。

### 5.6 空 Batch

不允许上传空 batch。

规则：

- submit 前统计 `active` items；
- active item 数量为 0 时，前端禁用提交按钮；
- 后端也必须拒绝空 submit；
- 全部删除的 batch 保留为历史，但不进入 `pending_processing`。

### 5.7 Submit

W1-W4 需要真实后端 submit API，但 submit 不执行 scheduler / worker / memory mutation。

建议 API：

```text
POST /api/rp/story-sessions/{session_id}/brainstorm/sessions/{brainstorm_id}/batches/{batch_id}/submit
```

后端职责：

1. 校验 session / brainstorm / batch 身份；
2. 拒绝已冻结 batch；
3. 过滤 deleted items；
4. active item 为空则拒绝；
5. 将 batch 状态改为 `pending_processing`；
6. 将 active items 改为 `pending_processing`；
7. 保留 deleted items，但不纳入 submitted item ids；
8. 冻结 batch；
9. 返回 receipt，供 UI 用 `OwuiSnackBars` 提示“已提交处理”。

submit 后不做：

- 不创建 scheduler job；
- 不写 RuntimeWorkflowJobRecord；
- 不进入 post-write governance；
- 不尝试 Core direct edit；
- 不尝试 Recall / Archival action。

### 5.8 旧 Apply 路由处理

W1-W4 前端产品路径必须停止调用旧 `/apply`。

旧 `/apply` 若暂时保留，只能满足以下任一目的：

- 兼容旧测试，并在测试名/断言中明确它不是 W1-W4 submit；
- 作为 W5 之后 Core-oriented scheduler / worker / governed apply 的候选内部路径；
- 临时保留但不从 `LongformStoryPage` 触达。

禁止：

- 用旧 `apply_session(...)` 实现 batch submit；
- submit 后返回 `brainstorm_summary_apply`；
- submit 后把 receipt 展示为“已应用”；
- submit 后创建 Core proposal/apply；
- submit 后把 `pending_review` 伪装成 W1-W4 的成功态。

## 6. LLM Tool / Structured Output

Brainstorm LLM 只需要一个结构化能力：总结当前 brainstorm context window 为用户意图条目。

推荐工具 / structured output 语义：

```python
class BrainstormSummarizeOutput(BaseModel):
    items: list[str]
```

要求：

- 每个 string 是一条用户意图概述；
- 不输出 uncertainty / suggested_question；
- 不输出 evidence refs；
- 不输出 routing 字段；
- 不输出 Core patch 字段；
- 如果信息不确定，应在 discussion 阶段追问用户，不应沉淀到表单字段里。

Context 管理模块负责准备 branch-visible writer snapshot 和当前 active brainstorm window。LLM 本身不拥有读取工具。

## 7. Backend Owned Areas

Likely files:

- `backend/api/rp_story.py`
- `backend/rp/models/story_brainstorm.py` or existing brainstorm models
- `backend/rp/services/story_brainstorm_service.py`
- `backend/rp/services/story_session_service.py`
- `backend/rp/services/story_runtime_controller.py`
- `backend/tests/test_rp_story_api.py`
- `backend/rp/tests/test_story_brainstorm_service.py`
- `backend/rp/tests/test_legal_longform_session_seed.py`

Required backend behavior:

- support active brainstorm context window append / flush;
- summarize creates a new batch and flushes the active context window;
- continue-writing path flushes the active brainstorm context window without creating a batch;
- persist context window `status`, `flush_reason`, `flushed_at`, and source message refs or equivalent metadata;
- batch / item state is persisted server-side;
- item edit / add / delete / restore works only while batch is `draft`;
- submit freezes the batch and active items as `pending_processing`;
- deleted items are never included in submitted item ids;
- empty submit fails closed.

## 8. Frontend Owned Areas

Likely files:

- `lib/pages/longform_story_page.dart`
- `lib/services/backend_story_service.dart`
- new or existing brainstorm form dialog/widget under `lib/widgets/`
- `lib/chat_ui/owui/components/owui_snack_bar.dart` only as existing feedback component

Required frontend behavior:

- discussion remains in `Discussion / Review`;
- form entry is always visible;
- form dialog shows batches and items;
- no item-level permanent delete button clutter;
- hover/focus/selected item shows delete / restore action;
- active item content is editable;
- deleted item is dimmed / struck through and read-only;
- user can add item;
- submit button disabled when no active item exists;
- submit shows `OwuiSnackBars.success`;
- failures show `OwuiSnackBars.error`;
- submitted batch is read-only.

## 9. Verification

Backend focused tests:

```powershell
python -m pytest backend\rp\tests\test_legal_longform_session_seed.py -q --tb=short
python -m pytest backend\rp\tests\test_story_brainstorm_service.py -q --tb=short
python -m pytest backend\tests\test_rp_story_api.py -q -k "brainstorm" --tb=short
```

Frontend focused checks:

```powershell
flutter analyze lib\services\backend_story_service.dart lib\pages\longform_story_page.dart
```

Required test cases:

- summarize creates one batch with active items and flushes current brainstorm context window;
- continue-writing flushes current brainstorm context window without batch;
- subsequent brainstorm does not inherit flushed raw discussion by default;
- writer packet excludes brainstorm-only `StoryDiscussionEntry` or equivalent scratch records;
- old `/apply` is not used by the W1-W4 frontend product path;
- batch submit returns `pending_processing`, not `brainstorm_summary_apply` / `pending_review` / applied;
- LLM summary output rejects routing / patch fields;
- user-added item is persisted as active;
- deleted item is persisted, visible as deleted, and restorable;
- deleted item is excluded from submit;
- empty submit is rejected;
- submitted batch freezes edits/deletes/restores;
- submit does not create scheduler job or workflow ledger entry;
- writer context excludes brainstorm raw discussion, draft batch, deleted items, and pending_processing items.

## 10. Implementation Dispatch

Recommended dispatch:

- one implement agent owns W0-W4 end to end;
- do not split W2 / W3 / W4 across different implement owners;
- do not start W5 until W1-W4 batch / item / submit contract is stable;
- after W0-W4 completes, run one module-level `gpt-5.5 xhigh` check.

The implement agent must treat this file as the Stage W source of truth when it conflicts with older V4 wording in `story-runtime-branch-aware-memory-product-foundation-development-spec.md`.
