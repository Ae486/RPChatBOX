# Proposal 清单（要有哪些提议？）（Draft）

> 目标：先把系统可能产生的 Proposal（提议/变更单）类型列清楚，再讨论：
> - 哪些需要即时弹窗
> - 哪些进入“待处理队列”
> - 哪些可以静默自动更新（仅记录日志）
>
> 本文不做工程落地映射，只定义“提议类型、触发信号、影响范围、风险等级”。
>
> 最后更新：2026-01-07

---

## 0. 总原则（与你已确认的规则对齐）

1) **写入 Canon 的任何变更必须人类在环**（弹窗允许/拒绝/编辑后允许）。
2) **禁用模块后不产生该模块 Proposal**（并且不可编辑、系统完全忽略）。
3) **Proposal 必须可审计**：理由 + 证据链 + 影响哪些块/条目 + 版本/回滚点。
4) **Proposal 不等于注入**：注入由 Orchestrator 预算编排决定；Proposal 是“对数据/结构的修改建议”。

---

## 0.1 你已确认：Proposal 支持“权限分级”（三档）

你希望所有 Proposal 都能走统一的权限管理（可按模块/类型/模式配置）。三档定义如下：

1) **静默更新（Silent）**
   - 自动应用（通常仅限 Draft‑Only）
   - 只写日志与回滚点（用户默认不被打断）

2) **提醒后直接更新（Notify‑Apply）**
   - 以非阻塞方式提醒（例如角标/通知/队列提示）
   - 仍然自动应用并写日志（用户可回滚/追溯）

3) **提醒且要求用户审查确定（Review‑Required）**
   - 必须用户确认（允许/拒绝/编辑后允许）
   - Canon‑Write 默认必须落在这一档

> 该分级会与模式（Standard/Immersive）叠加：Immersive 可将更多提议降为 Silent/Notify‑Apply，减少打断。

---

## 1. Proposal 的通用结构（概念）

每个 Proposal 建议至少包含：

- `proposal_id`
- `module_id`, `block_id`, `view_id?`
- `scope`：`story`（默认）/ `global`
- `operation`：`create | update | delete | link | unlink | merge | split | reorder | override`
- `target`：目标条目/目标块
- `diff`：要改什么（结构化 patch；支持逐条回滚）
- `reason`：触发原因（短句）
- `evidence[]`：证据链（优先 Key Event / Event Ledger；必要时引用消息片段）
- `risk`：`high | medium | low`
- `permission_tier`：`silent | notify_apply | review_required`（默认建议值，可被模式/用户覆盖）
- `mode_policy`：Standard/Immersive 下默认如何处理（与 permission_tier 的映射）

---

## 2. Proposal 分类（按“改动对象”）

### 2.1 Canon‑Write Proposals（高风险：必弹窗）

这些提议会新增/修改/删除 **Canon Facts**，必须即时弹窗（至少在 Standard/Immersive 都要用户确认）。

1) **Canon：世界/规则更新提议（World Canon Update）**
   - 触发：用户明确声明新设定；剧情明确出现新世界规则；或纠错/改写设定。
   - 影响：`world`（Canon 条目）

2) **Canon：角色设定更新提议（Character Canon/Delta Update）**
   - 触发：外观/身份/能力等变化或纠错；新确定的人际关系事实。
   - 影响：`character`（基准或 Delta；默认写 Delta）

3) **Canon：关键事件写入/纠错提议（Key Event Canonize / Correct）**
   - 触发：系统抽取的关键事件需要被确认；或用户手动标关键/修正。
   - 影响：`timeline`（Key Event 条目本体）

4) **Canon：状态写入提议（State Canonize / Correct）**
   - 触发：关键物品得失、伤势、强约束状态变化被确认。
   - 影响：`state`（关键状态条目）

> 备注：你已确认“关键事件系统判定为主，用户可手动标记/编辑”。这里的 Canon‑write 提议就是把“系统判定”变成“可确认的事实约束”。

---

### 2.2 Draft‑Only Proposals（中/低风险：可队列/可静默）

这些提议只改 **Draft Judgements** 或 **派生/辅助数据**，不直接改写事实约束。它们通常可以进入队列，甚至在 Standard 模式下静默更新（只记日志），以避免打断沉浸。

5) **伏笔关联提议（Foreshadow Link Proposal）**
   - 触发：新 Key Event 出现；用户手动触发“重新关联”。
   - 内容：为某伏笔新增 `ForeshadowEventLink`（relation + delta_evidence/delta_payoff + reason + confidence）。
   - 影响：`foreshadow_hooks`（Linker 关联条目）
   - 风险：中（会影响进度条与注入优先级，但不改事实）

6) **伏笔进度/权重提议（Foreshadow Tracker Update）**
   - 触发：新关联出现；叙事窗口信号出现；用户调整权重。
   - 内容：更新 `progress_evidence/progress_payoff/weights`（注意：可通过 link delta 派生；也可允许权重调整）。
   - 影响：`foreshadow_hooks`（Tracker 字段，Draft）
   - 风险：低‑中

7) **目标/任务更新提议（Goals Update）**
   - 触发：用户意图明显推进/放弃某目标；关键事件导致目标完成/变化。
   - 影响：`goals`
   - 风险：中（会影响叙事方向与注入）

8) **角色主观记忆/误解提议（Character Memory Update）**
   - 触发：角色明确表达认知；或事件导致角色形成误解/印象。
   - 影响：`character`（Character Memory 子块，Draft）
   - 风险：中（影响视角与信息不对称；但不改客观事实）

9) **一致性闸门修正提议（Consistency Gate Fix）**
   - 触发：生成后发现与 Quick Facts/State/Timeline 矛盾。
   - 影响：默认不阻塞输出；主要用于日志记录与后续整理（见你对“冲突不处理、用户会纠正”的偏好）。
   - 风险：中（不改事实，但会影响“后续是否需要整理/修订”）

10) **场景切换提议（Scene Change Proposal）**
   - 触发：地点/时间跳转；在场角色变化；目标完成；用户显式指令。
   - 影响：`scene`
   - 风险：中（切错会破坏沉浸）

11) **摘要/压缩提议（Summarize/Compress Proposal）**
   - 触发：上下文过长；进入新 Scene；用户手动触发整理。
   - 影响：`scene.previously_on` 或 timeline 的摘要视图；或生成“章节/场景摘要条目”（Draft）
   - 风险：中（摘要质量会影响后续一致性）

12) **Style 建议提议（Style Suggestion, Optional）**
   - 触发：用户频繁纠正文风；一致性闸门检测到“风格偏离”；用户主动请求“帮我生成 style 卡片”。
   - 影响：`style`（建议内容，用户采纳后写入）
- 风险：低（你已确认未配置 style 时不强约束）
 - ✅ 你已确认：由用户自行处理（系统不主动推送生成 style 卡片的提议；除非用户主动请求）

13) **用户纠错追踪提议（User Edit Correction Proposal）**
   - 触发：用户在“对话内容编辑”中把某个细节改掉（例如把“蓝发”改为“黑发”）。
   - 内容：将“用户修改的 diff”作为强信号，交给专用 agent 生成：
     - 该修改更可能属于：纠错 / 剧情变化 / 视角差异（需要用户最终确认写入 Canon 还是写入 Delta/角色主观记忆）
     - 对应的修订建议（Proposal）
   - 影响：常见落点为 `character`（外观/设定 Delta）、`state`、`timeline` 或 `foreshadow_hooks`（关联修正）
   - 风险：中（信号强，但仍可能是用户的“文案润色”而非事实纠错；需分类）

---

## 3. 处理策略（先给一个默认，后续你可调）

> 你说“先确定有哪些 proposals”。上面是清单。这里给一个默认建议，便于你快速反馈。

### 3.1 Standard（默认）

- Canon‑Write：`review_required`
- Draft‑Only：按类型配置为 `silent / notify_apply / review_required`
  - 例如：`foreshadow link / tracker / goals / character memory / summarize` 默认 `notify_apply`（不打断、可回滚）
  - `consistency gate fix` 默认 `silent`（只写日志，不阻塞）
  - `user edit correction` 默认 `review_required`（因为它通常是“事实纠错”的强信号）

### 3.2 Immersive

- Canon‑Write：`review_required`（最少打断，但必须确认）
- Draft‑Only：尽量 `silent/notify_apply`；只保留“必须确认”的才弹窗（例如 user edit correction、或你显式手动触发整理）

### 3.3 God/Editor（高级）

- 允许更直接的编辑与批量处理，但仍保留版本与回滚。

---

## 4. 需要你确认的 6 个选择（下一轮讨论建议从这里开始）

1) ✅ 已确认：Proposal 支持三档权限管理（silent / notify_apply / review_required），可按类型与模式配置。
2) ✅ 已确认：冲突通常不阻塞处理（用户会自行纠正）；更重要的是把“纠正信号”变成可追踪的整理输入（见 user edit correction）。
3) ✅ 已确认：Scene Change 按权限管理策略处理（可 silent/notify/review；默认建议 Standard=review_required，Immersive=notify_apply）。
4) ✅ 已确认：Goals Update 采用系统自动维护，用户可回滚/编辑。
5) `negative` 关联（评估后的明确结论）：
   - ✅ 允许存在（用于阻碍/反证 Draft 推测/误导等叙事手法，也能在“真相大白”后成为可用素材）。
   - ✅ 默认 Linker **不自动产出 negative**（只产出 positive/neutral），避免复杂度与误判成本。
   - ✅ 若要出现 negative：必须走 Proposal，默认 `review_required`（用户确认或用户手动添加/修改）。
   - ✅ “真相大白后从 negative 变成可用证据”的处理：优先 **新增一条 reinterpretation 关联**（引用回收事件作为证据），而不是静默翻转历史关联（保证可审计）。
6) ✅ 已确认：Style Suggestion 由用户自行处理（系统不主动推送）。

✅ 你已确认（补充决策）：
- Proposal 统一走“权限分级”（silent / notify_apply / review_required），并可按模块/类型/模式配置。
- Scene Change、Goals Update 等都按权限分级策略处理。
