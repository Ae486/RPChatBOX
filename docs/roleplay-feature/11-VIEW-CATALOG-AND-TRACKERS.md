# View 目录与 Tracker 模式（Draft）

> 目标：把 “Block → View → Entry” 变成可复用的统一模式，并给出各块可默认提供的 View（用于 UI 与注入选择），以及“进度/状态条（Tracker）”可以复用在哪些块上。
>
> 本文不做落地映射（不涉及 Flutter/数据库/LLM 调用细节）。
>
> 最后更新：2026-01-07

---

## 0. 两类 View：UI View vs Injection View

- **UI View**：用户管理用（浏览/筛选/编辑/回滚）。
- **Injection View**：Orchestrator 编排上下文用（挑 top‑N、严格预算、放在 P0/P1/P2）。

同一个 View 可以同时承担两种角色；但设计时要明确其默认用途与预算。

---

## 1. 统一结构：Block → View → Entry（如何应用到所有块）

### 1.1 Block（定义规则与数据）

每个 Block 负责：
- 条目 schema（entry_schema）
- Canon/Draft 策略与冲突处理
- 预算与裁剪策略
- 可观测性（注入/更新/裁剪/回滚日志）

### 1.2 View（定义“在当前情境下挑哪些条目”）

每个 View 负责：
- 过滤条件（match）
- 排序规则（order）
- 数量限制（limit）
- 注入策略（P0/P1/P2、位置、频率；可选）

### 1.3 Entry（最小可回滚单元）

每条 Entry 至少带：
- `entry_id`, `entry_type`, `canonicality(canon|draft)`, `status`
- `content`
- `evidence`（引用消息片段/事件条目/场景 ID）
- `revision`（用于回滚）

> 这套结构的目的：**数据可以很全，但每轮只注入 View 选出来的极少部分**，从而控制 token。

---

## 2. Tracker 模式（进度/状态条）

你提出的“伏笔回收度/置信度状态条”可以抽象成一个通用模式：Tracker。

### 2.1 Tracker 建议字段（概念）

- `progress_evidence`：0–100（证据积累程度：由“关联事件”持续累加/修正）
- `progress_payoff`：0–100（回收接近程度：由“叙事窗口信号”累加/修正）
- `progress`：0–100（综合进度：由权重聚合）
- `weights`：例如 `{evidence: 0.6, payoff: 0.4}`（可配置；默认系统给出，用户可调整）
- `confidence`：0.0–1.0（模型对当前判断的把握）
- `signals`：触发信号列表（例如关联关键事件、目标推进、进入回收场景、阻碍出现等）
- `linked_evidence`：关联证据（优先引用关键事件条目；必要时引用消息片段）
- `last_update_reason`：更新理由（简短、可展示给用户）

### 2.2 Canon/Draft 建议

- Tracker 默认属于 **Draft**（因为它是“模型判断的状态”，不是客观事实）。
- 但 Tracker 所引用的 `linked_evidence` 可以来自 Canon（例如 Timeline 的关键事件）。

---

## 3. 各模块默认 View 目录（v0 建议）

### 3.1 `scene`（Scene State）

- **Injection View：Current Scene**（P0，极短）
  - `location / present_characters / goal_or_conflict / time / previously_on`
- **UI View：Scene History**（按时间线/分支浏览）

### 3.2 `timeline`（Timeline / Event Ledger）

- **Injection View：Key Events (Top‑N)**（P1 或 P2）
  - 只选 `is_key=true` 的事件，按最近/重要性排序，limit 严格（例如 3–5）
- **UI View：By Scene**（按场景分组）
- **UI View：Evidence Browser**（用于 Proposal 弹窗快速引用证据）

> 你已选择：伏笔“到期”单位按 **关键事件** 计数，因此这里的 “Key Events View” 很关键。

### 3.3 `goals`（Goals / Tasks）

- **Injection View：Current Goals (Top‑3)**（P1）
- **UI View：Backlog**（未激活目标）
- **UI View：Completed**（已完成目标）
- **Tracker 可用**：目标完成度（progress）、下一步（可选）

### 3.4 `foreshadow_hooks`（Foreshadow / Hooks）

- **Injection View：High‑Urgency Foreshadows (Top‑2)**（P1，强约束）
  - 说明：“到期”不必是独立字段，而是由 Tracker 派生的“高紧迫”标签。
  - 过滤：`status in {planted,active}` 且 `urgency_score>=阈值`（或 `progress_payoff/progress` 达到阈值）
  - 排序：`urgency_score desc, strength desc`
- **Injection View：Active Hooks (Top‑2)**（P2）
- **UI View：All Threads**（聚合展示：可把 Goals+Foreshadows+Hooks 汇总成 Dashboard；但数据仍在各自模块内）
- **Tracker 强适用**：回收度/置信度（progress/confidence）+ `linked_key_events[]`

### 3.5 `state`（State / Flags）

- **Injection View：Active Constraints (Top‑N)**（P1/P2）
  - 例如重伤/失明/被追踪/关系破裂等强约束状态
- **UI View：Inventory by Character**（角色局部视图）
- **UI View：Relationship Flags**（关系状态标记）
- **Tracker 可用**：状态持续度/风险度（例如中毒加深），但默认仍属 Draft

### 3.6 `world`（World / Lorebook）

- **Injection View：Constant Lore**（P1 或 P2，小段、低频）
- **Injection View：Keyword Hits (Budgeted)**（P1）
- **UI View：By Topic/Location/Org**（按标签分组）
- **Tracker 可选**：某条世界设定“出现频率/重要性”统计（用于优先级，不必暴露给用户）

### 3.7 `character`（Character Card + Character Memory）

- **Injection View：Character Quick Facts**（P0，极短）
  - 只放最容易出错且高价值的硬约束（外观关键点、禁忌、口癖等）
- **Injection View：Active Delta**（P1）
- **UI View：Card Base vs Delta**（对比与回滚）
- **UI View：Character Memory**
  - 子视图：`Known Facts / Misbeliefs / Emotional Impressions`
- **Tracker 可用**：关系亲密度、信任度、恐惧度等（默认 Draft，需证据链）

### 3.8 `style`（Style Card）

- **Injection View：Story Style Card**（P1，按频率注入）
- **UI View：Style Editor**（用户编辑）
- Tracker 一般不需要（除非你想做“风格一致性评分”，建议后置）

### 3.9 `mechanics`（Dice / Rules）

- **Injection View：Recent Rolls**（P2，必要时）
- **UI View：Rule Set**（规则配置）
- **UI View：Roll Log**（可溯源）

---

## 4. 你提出的“关键事件驱动伏笔进度”建议（总结）

可以做，而且很契合你关心的两点：一致性与 token 可控。

建议把流程约束成三条（避免模型乱联想）：
1) **只有“关键事件”才能推进进度条**（普通闲聊不算）
2) **推进必须附带证据链**（事件条目 ID + 触发理由）
3) **进度/置信度默认 Draft**（可回滚；用户可拒绝关联）

并补充你已确认的一点：
4) **关键事件判定由系统为主，用户可手动编辑/标记**（避免系统漏判/误判）

---

## 5. “关键事件”不是“伏笔事件”：需要一个关联层（Linker）

你提到“关键事件是否就是伏笔事件”。建议明确区分两层概念（否则后续很容易误解）：

1) **Key Event（关键事件，Timeline 层）**
   - 定义：故事中客观发生的高价值节点（不要求与伏笔相关）。
   - 作用：
     - 作为“时间推进单位”（你已选：伏笔到期单位按 N 个关键事件）
     - 作为证据源（Proposal/进度条都引用它）

2) **Foreshadow‑Linked Event（伏笔关联事件，Foreshadow 层）**
   - 定义：从 Key Event 中筛选出“与某条伏笔相关”的子集，并记录其对伏笔的影响。
   - 作用：
     - 更新伏笔 Tracker（证据积累 / 回收接近）
     - 展示证据链（你认可的“关联器/Linker”）

> 这样做的好处：Timeline 可以完整稳定，而每条伏笔只挂少量真正相关的事件，token 仍可控。

### 5.1 关联条目（ForeshadowEventLink）建议字段

每次出现新 Key Event（或用户手动触发“重新关联”）时，Linker 产出一个“关联条目”（建议按 Entry 记录，便于回滚与审计）：

- `foreshadow_id`
- `event_id`（指向 Timeline 的 Key Event）
- `relation`：`positive | negative | neutral`
  - `positive`：推进/支持伏笔（大多数情况）
  - `negative`：削弱/阻碍/反证/误导（少数情况，但建议允许）
  - `neutral`：仅旁证或背景，0 影响
- `delta`（允许正负；你提到“影响率/影响量”可落在这里）
  - `delta_evidence`：[-100, +100]
  - `delta_payoff`：[-100, +100]
- `confidence`：0.0–1.0
- `reason`：为什么相关、如何影响（短句）
- `signals[]`：例如 `mentions_same_object / same_location / goal_completed / blocker_introduced / contradiction_detected`
- `manual_override`（可选，用户手动编辑时写入）
  - `manual_delta_evidence`, `manual_delta_payoff`
  - `manual_note`

并补充你已确认的一点：
- 手动编辑采用 **直接给 delta** 的方式（更直观）；并允许在对应页面“询问相关 agent”，由 agent 给出建议 delta（用户可采纳/修改/拒绝）。

### 5.2 正相关 vs 负相关：建议“都支持，但都是 Draft”

你问“关键事件只有正相关还是正负都包含？”建议是：

- **Key Event 本身不分正负**：它只是“发生了什么”。
- **正负发生在关联层**：同一 Key Event 对不同伏笔可以是正相关/负相关/无关。

并且：
- 大多数关联应为 `positive`（符合你的直觉）
- `negative` 建议主要用于三类情形（都必须给证据链与理由，且默认 Draft）：
  1) **阻碍**：关键道具损坏/失去、关键人物离场，短期更难回收
  2) **反证**：事件直接否定某条 Draft 解读（注意：否定的是“推测”，不是改写客观事实）
  3) **误导**：强“假线索/烟雾弹”（写作上很常见），会让回收接近度下降但证据积累可能上升

你要求“给出明确结论”，这里给一个默认策略（可在 God/高级写作中放开）：

- ✅ **允许存在 negative**（它本身也是叙事素材）
- ✅ **默认 Linker 不自动产出 negative**：自动关联只产出 `positive/neutral`，避免误判导致“进度乱跳/故事被系统强行带偏”
- ✅ 若要出现 negative：走 Proposal，默认 `review_required`（用户确认，或用户手动添加/修改）
- ✅ “真相大白后 negative 变成可用证据”：优先 **新增一条 reinterpretation 关联**（引用回收事件作为证据）而不是翻转历史关联（保证可审计、可回滚）

---

## 6. “回收接近（progress_payoff）”是什么？如何可解释地更新？

你已经理解 `progress_evidence`：随着关联事件增多/更强而上升。

`progress_payoff` 回答另一个问题：**从叙事位置上看，现在是不是更适合回收这条伏笔？**  
它不等于“证据多”，而更像“叙事窗口是否打开”。

### 6.1 典型会提升回收接近的信号（建议都能落到事件/状态上）

- **进入回收场景**：关键地点到达、关键人物同场、关键道具到手（Scene/State/Timeline 的变化）
- **目标推进**：某个 Goal 完成或进入最后阶段（Goals 的变化）
- **冲突升级/临界点**：剧情进入对峙/揭示前夜（可由 Orchestrator 产出 Draft 信号）
- **时间推进**：从“埋下”起已发生 N 个关键事件（你选择的 due 单位）

### 6.2 典型会降低回收接近的信号

- **回收条件被破坏**：关键道具丢失、关键人物死亡/远离、地点不可达（State/Timeline）
- **剧情改道**：主线目标转移，暂时离开伏笔相关区域（Goals/Scene）

### 6.3 为什么必须与证据积累分开

- 证据积累在涨，但剧情还不到回收窗口（应当 `progress_evidence ↑`、`progress_payoff ↔`）
- 剧情到了回收窗口，但证据并不多（应当 `progress_payoff ↑`、`progress_evidence ↔`）

> 两轴分离可以避免“只要提到几次就逼着回收”的生硬感，也符合你追求的沉浸与互动性。
