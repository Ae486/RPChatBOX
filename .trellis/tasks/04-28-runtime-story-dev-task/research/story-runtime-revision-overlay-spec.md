# Story Runtime Revision Overlay / Rewrite Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Longform Revision Overlay / Rewrite / SuperDoc Adapter
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- longform 修订前端的模式语义
- `review overlay / comment / tracked change` 的 runtime 语义
- `full rewrite / paragraph rewrite` 的产品动作与输入输出合同
- SuperDoc/Word 风格修订能力与 story runtime 的适配边界
- comment lifecycle / selection / adoption 与 draft candidate 的关系

这份文档不负责：

- `WritingPacket` 的公共字段定义
- `WorkerDescriptor / WorkerExecutionPlan / WorkerResult` 的公共合同
- post-write memory governance 的完整顺序
- branch / rollback 的产品语义本体

## 2. 设计目标

这一层要解决 7 个问题：

1. 为什么修订模块要借用文档修订 substrate，而不是直接靠 markdown 文本交互
2. `discussion` 与 `review/rewrite` 为什么必须严格分流
3. `viewing / editing / suggesting` 三态各自承载什么语义
4. `full rewrite` 和 `paragraph rewrite` 的动作边界是什么
5. comment / tracked change 如何传递给 writer，而不是只停留在 UI 层
6. draft selection 与 draft adoption 为什么不能混成同一个状态
7. rewrite 后 comment 为什么默认保留，而不是自动 resolve

## 3. 与其他规格书的关系

本规格书不是公共合同根文件。它依赖并扩展以下规格：

1. [story-runtime-context-packet-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md)
   - canonical `WritingPacket / PacketSection / RuntimeReadManifestRecord`
   - 本文只定义“修订内容如何进入 writer packet”

2. [story-runtime-writing-worker-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md)
   - canonical `WritingWorkerExecutionRequest / Result`
   - 本文只细化 longform `rewrite` 的产品动作和输入输出形状

3. [story-runtime-workspace-ledger-trace-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-workspace-ledger-trace-spec.md)
   - canonical `Turn / RuntimeWorkspaceMaterial / RuntimeWorkflowJobRecord / Trace`
   - 本文只定义 revision overlay / selection / adoption 作为 turn 子材料的归属关系

4. [story-runtime-postwrite-memory-governance-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-postwrite-memory-governance-spec.md)
   - canonical post-write / settlement / proposal governance
   - 本文只说明 rewrite 结果如何进入后续 turn material 和 adoption 语义

5. [prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md)
   - 若本文与旧 MVP 或第三方默认行为冲突，以 PRD 和 task 讨论为准

## 4. 总体原则

### 4.1 SuperDoc 作为 substrate

当前设计借用 SuperDoc/Word 在以下方面的成熟能力：

- docx/document 视图
- block / node / selection / range 锚点
- comments
- tracked changes
- accept / reject / resolve 心智

但是：

- SuperDoc 不是 runtime 真相 owner
- story runtime 的 `Turn / review overlay / rewrite packet / adoption receipt` 仍由 RP runtime 持有
- 若 SuperDoc 的现成行为与当前 task 需求冲突，以当前 task 文档和讨论结论为准

### 4.2 discussion 与 rewrite 严格分流

冻结口径：

- `discussion / brainstorm`
  - 只承接用户不确定、想讨论、想改设定/方向的内容
  - 输出 `brainstorm summary`
  - 不直接承接明确段落修订

- `review overlay / rewrite`
  - 只承接明确修订、批注、tracked changes、段落改写意图
  - 不进入 discussion

### 4.3 editing 与 suggesting 分流

第一阶段 longform 修订前端冻结三态：

- `viewing`
  - 只读查看当前 draft

- `editing`
  - 用户直接改当前 draft candidate
  - 本次修改本身不默认转成给 LLM 的 rewrite 指令
  - 更接近“用户自己改稿”

- `suggesting`
  - 用户操作形成 tracked changes / comments
  - 这些内容进入 review overlay
  - 后续由用户显式触发 rewrite

## 5. 核心对象

## 5.1 ReviewOverlayRecord

用途：

- 表达当前 turn 下的修订/批注 sidecar
- 供后续 rewrite turn 使用

建议字段：

- `overlay_id: str`
- `turn_id: str`
- `draft_ref: str`
- `mode: str`
  - `viewing`
  - `editing`
  - `suggesting`

- `comment_refs: list[str]`
- `tracked_change_refs: list[str]`
- `selection_refs: list[str]`
- `overlay_status: str`
  - `active`
  - `resolved`
  - `stale`
  - `archived`

- `metadata_json: dict`

关键约束：

- `review overlay` 是 turn material，不是 canonical truth
- 不直接写 `Core State`
- 不自动成为正文

## 5.2 RevisionCommentRecord

建议字段：

- `comment_id: str`
- `turn_id: str`
- `draft_ref: str`
- `anchor_scope: str`
  - `inline`
  - `single_block`
  - `multi_block`

- `anchor_ref: dict`
- `selected_excerpt: str | None`
- `instruction_text: str`
- `status: str`
  - `active`
  - `resolved`
  - `deleted`

- `metadata_json: dict`

关键约束：

- 第一阶段 comment 默认保留 `active`
- rewrite 后不自动 resolve
- 是否已满足由用户显式决定

## 5.3 DraftSelectionReceipt

用途：

- 表达当前暂定选中了哪个 candidate

建议字段：

- `receipt_id: str`
- `turn_id: str`
- `candidate_output_refs: list[str]`
- `selected_output_ref: str`
- `selected_at: datetime`
- `selection_source: str`
  - `user_explicit_select`

- `metadata_json: dict`

关键约束：

- 可逆、可清除
- 不等于 adoption

## 5.4 DraftAdoptionReceipt

用途：

- 表达用户点击 `accept_and_continue / 续写` 时，最终哪一版成为 canonical continuation base

建议字段：

- `receipt_id: str`
- `turn_id: str`
- `adopted_output_ref: str`
- `adopted_at: datetime`
- `adoption_source: str`
  - `accept_and_continue`

- `metadata_json: dict`

关键约束：

- 下一轮 writer / post-write / branch-visible continuation 只认 adoption receipt
- selection receipt 不足以驱动继续写作

## 6. 文档锚点与 block 语义

### 6.1 锚点来源

第一阶段优先借用 SuperDoc/Word 风格的：

- block / node
- selection / range
- comment anchor
- tracked change id

runtime 不直接把 markdown 换行当作 canonical anchor。

### 6.2 writer raw content 与 document substrate

writer 输出仍可保留为 markdown/text 风格内容，但修订链的起点不是 raw string，而是：

```text
writer output text
  -> DraftMaterializationService
  -> canonical draft document
  -> block/node structure
  -> review/comment/selection anchor space
```

因此：

- markdown 可以作为 materialization 的输入格式
- 但 comment / tracked change / paragraph rewrite 的锚点必须绑定在 document block/range 上

### 6.3 第一阶段 block 约束

第一阶段不要求复杂 block tree 语义，只要求：

- 当前 draft 可被物化成稳定 block 序列
- comment / tracked change 可锚定到 block/range
- paragraph rewrite 可按 block 精确替换

## 7. 产品动作

第一阶段修订相关动作只保留：

1. `full rewrite`
2. `paragraph rewrite`
3. `accept_and_continue`
4. `resolve comment`
5. `delete comment`

不做：

- 自动批量 rewrite
- 自动从修订密度判断升级为全文重写
- 同一轮内多处并发 paragraph rewrite

## 8. Full Rewrite

## 8.1 语义

`full rewrite` 是独立产品动作，作用于整篇当前 draft。

## 8.2 输入合同

建议字段：

- `draft_ref: str`
- `rewrite_scope: str`
  - `full`

- `global_instruction: str | None`
- `comment_refs: list[str]`
- `tracked_change_refs: list[str]`
- `current_outline_ref: str | None`
- `chapter_goal_ref: str | None`
- `core_view_refs: list[str]`
- `recent_turn_refs: list[str]`
- `metadata_json: dict`

## 8.3 输入规则

`full rewrite` 只保留一种产品动作，但输入分两种形态：

1. **仅有全文批注，没有额外全文要求**
   - 允许携带旧正文全文
   - 同时携带全文 comment / tracked changes
   - 用于“对整篇已有正文做整体修订”

2. **存在明确全文要求**
   - 不携带旧正文全文
   - 不做逐段对照底稿
   - 只携带：
     - 必要上下文摘要
     - core view / outline / goal
     - 全文 rewrite 要求

## 8.4 输出合同

建议字段：

- `draft_ref: str`
- `rewrite_scope: str`
  - `full`

- `candidate_output_ref: str`
- `full_output_text: str`
- `touched_comment_ids: list[str]`
- `metadata_json: dict`

关键约束：

- 返回新的完整 candidate draft
- 不自动 adopted

## 9. Paragraph Rewrite

## 9.1 语义

`paragraph rewrite` 作用于当前 draft 中的一处局部 block/段落区域。

第一阶段冻结为：

- 一次只 rewrite 一处
- 不做批量 rewrite

## 9.2 输入合同

建议字段：

- `draft_ref: str`
- `rewrite_scope: str`
  - `paragraph`

- `full_draft_text: str`
- `target_block_ids: list[str]`
- `target_range_ref: dict | None`
- `comment_refs: list[str]`
- `tracked_change_refs: list[str]`
- `global_instruction: str | None`
- `metadata_json: dict`

## 9.3 输入规则

- `paragraph rewrite` 允许携带整篇原文作为背景
- 但必须显式标出：
  - `target_block_ids`
  - `comment_refs`
  - `tracked_change_refs`
- writer 必须被约束为“只改 target blocks”

## 9.4 输出合同

建议字段：

- `draft_ref: str`
- `rewrite_scope: str`
  - `paragraph`

- `target_block_ids: list[str]`
- `replacement_blocks: list[ReplacementBlock]`
- `touched_comment_ids: list[str]`
- `metadata_json: dict`

### ReplacementBlock

建议字段：

- `block_id: str`
- `replacement_text: str`
- `order: int`
- `metadata_json: dict`

关键约束：

- 不返回整篇自由文本作为唯一替换依据
- 前端或 deterministic composer 按 `target_block_ids` 精确替换生成新 candidate
- 新 candidate 允许版本切换

## 10. Comment Lifecycle

冻结口径：

- rewrite 后 comment 默认继续保留
- 不自动 resolve
- 不自动删除
- 由用户显式决定：
  - `resolve`
  - 保留
  - 删除

resolved comment：

- 默认从主修订工作视图收起
- 但仍保留留痕、锚点、provenance 和 trace

## 11. 与 writer / packet / post-write 的关系

### 11.1 与 WritingPacket 的关系

本模块不重定义 `WritingPacket`。

它只要求：

- `review_overlay_sections` 作为 writer packet 的一种 mode sidecar
- `full rewrite` 与 `paragraph rewrite` 在 packet metadata 中可区分 scope

### 11.2 与 WritingWorker 的关系

本模块不新增独立 rewrite worker。

冻结口径：

- `discussion / brainstorm`
- `writing / rewrite`

仍由同一个 `WritingWorker` 承接，只通过 operation mode / packet policy / review overlay 区分。

### 11.3 与 post-write 的关系

- revision overlay / selection / adoption receipt 都是 `Turn` 子材料
- rewrite 产生的新 candidate 仍需走统一 turn material / post-write / settlement 语义
- adoption 只有在 `accept_and_continue` 时发生

## 12. SuperDoc Adapter Boundary

SuperDoc 适合承接：

- canonical draft document view
- block / node / selection anchor
- comments
- tracked changes
- accept / reject / resolve 心智
- precise block/range replacement

SuperDoc 不应直接拥有：

- rewrite packet 语义
- draft adoption 语义
- story runtime canonical truth
- `Turn / BranchHead / RuntimeProfileSnapshot / post-write` 真相

实施口径：

- SuperDoc 的源码/文档用于理解和适配其 document mode、comment、tracked change、selection/range 和导出行为。
- 后端 runtime 不以 SuperDoc 的内部 revision/doc state 作为真相；RP 侧必须先持有 `review overlay / comment / tracked change / selection / adoption` 合同。
- SuperDoc 侧 id 只能作为 adapter metadata 保存，不能替代 `Turn / draft_ref / draft_document_id / candidate_output_ref`。
- 第一阶段优先做可见文档修订 substrate 和事件适配；不因为 SuperDoc 存在 Python/Node SDK 就把 R2 后端持久化绑定到它的 SDK。

## 13. 第一阶段不做

- 非连续多区域批量 paragraph rewrite
- 自动把大量局部修订升级为 full rewrite
- comment 自动 resolve
- 复杂树状 diff/review UI
- 富文本样式编辑能力（字体、加粗、链接等作为正式产品能力）

## 14. 测试点

1. `discussion` 与 `review/rewrite` 严格分流
2. `editing` 不自动形成 LLM rewrite 指令
3. `suggesting` 的 comments/tracked changes 能进入 review overlay
4. `full rewrite` 在“仅有全文批注”与“存在明确全文要求”两种输入形态下行为不同
5. `paragraph rewrite` 只替换 target blocks
6. `selection receipt` 不等于 `adoption receipt`
7. 只有 `accept_and_continue` 才产生 adoption
8. rewrite 后 comment 默认保留，不自动 resolve

## 15. 已知风险

1. 如果 paragraph rewrite 最终仍返回整篇自由文本，局部替换合同会重新变脆
2. 如果 block id 在重新物化后不稳定，需额外保留 excerpt/range 兜底
3. 如果后续把批量 paragraph rewrite 直接放开，packet 与 candidate 复杂度会显著上升
