# 快照级回滚（Snapshot Rollback）技术实现草案（Draft）

> 目标：回答“快照回滚是不是像 Git 回退版本？技术上如何实现？”  
> 本文偏工程语义与数据结构，**不绑定 Flutter/Hive/SQLite**，但足够具体到可直接落地。
>
> 最后更新：2026-01-07

---

## 0. 一句话结论：它很像 Git，但不是 1:1

- **像 Git 的部分**：有“提交点（Snapshot）”、有“指针（Head）”、可在历史中“切换到某一版本（checkout/reset 到某个快照）”，并保留可审计记录。
- **不一样的部分**：
  1) 我们不是一棵文件树，而是多块状态：`source(对话树)` + `draft(分支隔离)` + `canon_story(随剧情演进)` + `proposals/scene` + `foundation(基底)` + `config`。  
  2) **基底（foundation）默认不随剧情回滚**；但 `canon_story` 必须随剧情回滚同步回滚，否则会出现“回到过去但事实仍是未来”的矛盾。  
  3) 还有异步后台任务（agents），必须用版本闸门丢弃“基于旧世界算出来的结果”。

---

## 1. 需要“版本化”的到底是什么？

为了让回滚既准确又不互相污染，建议把可变状态拆成 6 组，并都能被“指针化”：

1) **对话源（Source）**  
   - 消息树结构（parent/children）  
   - 每条消息的 revision（允许编辑历史消息）
   - 当前选择路径（active chain / selected child）

2) **Draft（分支隔离）**  
   - 各模块条目（例如伏笔进度、linker 关联、角色主观记忆、scene 状态等）
   - Proposal 队列（分支语境下生成）

3) **基底（Foundation / Base）**  
   - “基本不变”的底座：初始角色卡基底层、世界书基底层、写作 Style 等  
   - 特点：不随剧情回滚；通常跨分支共享（你也可以允许它被显式编辑，并有独立的撤销/审计）

4) **Canon‑Story（`canon_story`，随剧情演进的已确认事实）**  
   - 例：确认过的关键事件、确认过的状态变化（受伤/获得物品/关系变化）、确认过的“剧情修订层（Delta）”等  
   - 特点：需要像“事实约束”一样强约束模型，但必须随剧情回滚同步回滚（分支/active chain 作用域）

5) **Config/Budget（可选纳入快照）**  
   - 模块启用状态、注入预算、view top‑N、tracker 权重等  
   - *建议作为“可选纳入快照”的一部分*：有时你希望回滚也回滚配置，有时不希望。

6) **日志/审计（不回滚，只追加）**  
   - 回滚本身也要写日志；日志是可溯源底座，不应被回滚抹掉。

---

## 2. 核心原语：Head / Operation / Snapshot（推荐模型）

你可以用 **“指针 + 追加日志”** 来实现快照回滚，避免每次都复制全量数据。

### 2.1 Head：当前状态指针（类似 Git HEAD）

对每个作用域维护一个 head 记录（示意字段）：

- `story_id`
- `branch_id`（仅分支作用域需要：`source/draft/canon_story/proposals/scene`）
- `scope`：`source | draft(module_id) | canon_story(module_id) | foundation(module_id) | proposals | scene | config`
- `rev`：递增版本号（整数或 hash）
- `root_id`：指向“当前状态根”的 ID（不可变对象 / 或序列化 blob 的 key）

> **关键**：更新状态时，不修改旧对象，而是写入新对象并移动 head 指针（copy‑on‑write）。

### 2.2 Operation：一次变更（用于撤销、审计、对比）

每次应用 Proposal / 用户编辑 / 系统维护，都生成一个 operation：

- `operation_id`
- `story_id + branch_id + scope`
- `before`: `{rev, root_id}`
- `after`: `{rev, root_id}`
- `reason`: `proposal_apply | user_edit | maintenance | rollback | snapshot_create ...`
- `payload`（可选）：结构化 patch/diff、关联的 proposal_id、证据链等
- `created_at`

“撤销本次更新”就是找最后一条 operation，把 head 指针从 `after` 切回 `before`（或应用反向 patch）。

### 2.3 Snapshot：检查点（用于快照级回滚）

Snapshot 不需要存全量内容，存“当时的各个 Head 指针集合”即可：

- `snapshot_id`
- `story_id + branch_id`
- `label`（可选）：比如“场景切换前 / 用户手动打点 / 大维护前”
- `created_at`
- `pointers`（一个 map）：
  - `source`: `{rev, root_id}`
  - `draft:*`: `{rev, root_id}`（每个模块一份）
  - `proposals`: `{rev, root_id}`（可选）
  - `scene`: `{rev, root_id}`（可选）
  - `canon_story:*`: `{rev, root_id}`（默认应纳入：随剧情回滚必须同步）
  - `config`: `{rev, root_id}`（可选；更像“设置回滚”，不一定随剧情）
  - `foundation:*`: `{rev, root_id}`（默认不纳入：基底不随剧情回滚；如需也可显式勾选或提供单独回滚入口）

> 快照级回滚 = 把这些 head 指针整体“切换回去”。  
> 注意：这不会删除未来数据，只是把“当前指针”移回历史点。

---

## 3. 版本闸门（Job Safety Gate）怎么配合？

后台任务（异步 agent）在启动时记录它“看到的世界版本”：

- `foundation_rev_at_start`
- `canon_story_rev_at_start`
- `draft_rev_at_start`
- `source_rev_at_start`
- 可选：`enabled_modules_hash`

任务完成准备写入时二次校验：

- 任一 `*_rev` 不匹配当前 head → **stale，丢弃**
- 模块已禁用 → 丢弃

因此：
- **快照回滚后**（head 指针变化 + `rev` 变化），旧任务自然全部失效，不会“写回去污染”。

---

## 4. “像 Git 一样回退”具体怎么做？

### 4.1 快照创建（commit/checkpoint）

触发时机建议：
- 用户手动“打点”（重要节点）
- 关键事件/设定写入 `canon_story` 之前或之后（或少数情况下“提升为 foundation”前后）
- Scene 切换前（或者切换后再打一次）
- 大规模后台维护前（例如重建时间线、重算 linker）
- 批量 silent 更新前（沉浸模式的“紧急刹车”）

实现上就是：
1) 读取当前需要纳入的各 head 指针（`rev + root_id`）
2) 写入一条 Snapshot 记录（追加，不覆盖）

### 4.2 快照级回滚（checkout/reset）

用户选择某个 snapshot 后：
1) 将相关 scope 的 head 指针切换到 snapshot 记录中的 `{rev, root_id}`
2) 写一条 `rollback` operation（记录从哪个 snapshot 回滚而来、原 head 是什么）
3) 触发派生缓存失效（例如 UI 缓存、已组装上下文缓存、token 统计等）

> 建议：回滚是“新操作”，而不是把历史截断。这样日志里能复盘“回滚发生过”。

### 4.3 撤销本次更新（revert）

对单次 Proposal/补丁：
1) 找到最后一条 `scope=...` 的 operation（或按 batch_id）
2) head 指针切回 `before`
3) 记录一条 `rollback` operation（或标记原 operation 已撤销）

---

## 5. “编辑历史消息”怎么纳入同一套体系？

你已确认：Immersive 下也要默认显示编辑入口（因为模型可能抽风）。

建议做法：

1) **消息本身有 revision**  
   - `message_id` 固定  
   - `message_revision_id` 每次编辑生成新对象（旧文本保留）
   - Source 的 head 指向“消息树 + 每条消息当前 revision 的映射”

2) 编辑产生 operation  
   - `scope=source`
   - `before` / `after` 指向不同的 source root

3) 编辑会让派生数据失效  
   - 标记 `timeline/scene/foreshadow_hooks/...` dirty（见文档 17）
   - 重新计算必须通过 Proposal 流程（避免“静默篡改记忆”）

4) 版本闸门天然处理异步竞态  
   - 编辑会改变 `source_rev` → 旧后台任务 stale 丢弃

---

## 6. 数据量与存储成本（为什么不一定会爆）

如果采用“不可变对象 + 指针”的方式：
- 一次更新只会写入“变动的那部分对象” + 移动 head 指针  
  （类似 Git 的对象存储：没变的不复制）
- Snapshot 只是一组指针集合，体积很小

你真正需要控制的是：
- snapshot 数量（保留策略：最近 N 个 + 用户 pin 的）
- operation 日志长度（可归档/压缩，但不建议直接删除）
- 大对象（例如长摘要）的生成频率与预算

---

## 7. 推荐的渐进落地顺序（避免一次做太大）

因为你说“不是很必要，但想法不错”，建议按价值/复杂度分期：

1) **先做 Operation + Undo（最小回滚）**  
   - 能撤销最近一次应用的 Proposal/补丁  
   - 已经能解决大量“抽风/误更新”的痛点

2) **再做 Snapshot（只存指针集合）**  
   - UI 先做“手动打点 + 回到打点”即可  
   - 不急着做自动快照策略

3) **最后做策略化自动快照 + GC**  
   - 场景切换自动打点  
   - 大维护前自动打点  
   - 快照保留策略与导出
