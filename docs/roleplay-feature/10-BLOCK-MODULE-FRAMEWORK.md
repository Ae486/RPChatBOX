# 块级模块框架（Mod/创意工坊式）（Draft）

> 目标：让“角色卡/世界书/记忆/伏笔/状态/文风/机制…”这些块级结构，像游戏 Mod 一样 **可启用/可禁用/可扩展**，并且具备统一的规则约束与审计能力。
>
> 本文只定义“模块契约与边界”，不做 Flutter/数据库/LLM 调用的落地映射。
>
> 最后更新：2026-01-07

---

## 0. 设计原则（与你的诉求对齐）

1) **统一框架**：所有块遵循同一套元数据/预算/更新/日志规范，便于管理与替换。
2) **可拆卸**：某些故事不需要某块（例如 Mechanics），应能单独禁用而不影响其他块。
3) **可拓展**：后续可以新增块（“创意工坊”式），并与现有块共存。
4) **默认安全**：Canon 只允许明确事实；任何写入 Canon 的更新都必须人类在环。
5) **token 可控**：模块再多，也必须由 Orchestrator 进行预算编排与优雅降级。
6) **模块非必要**：每个模块/卡片（含 Style 卡片）都应可不启用；未启用时系统应能正常对话，只是缺失对应能力。
7) **只用软依赖**：模块之间如存在依赖关系，采用 `suggests` + 降级路径；不使用 `requires`（硬依赖）。

---

## 1. 模块（Module）与块（Block）的关系

- **Module（模块）**：可安装/可禁用的“能力包”。一个模块可以提供一个或多个 Block。
- **Block（块/板块）**：用户可见的一级结构（角色、世界、Threads、State、Style…）。
- **Entry（条目）**：块内最小单元，必须可版本化、可引用证据、可回滚。
- **View（局部视图/子块）**：Block 内的“筛选/分组/聚合视图”（不一定是独立数据源），用于 UI 与注入选择。

> 例：`state` 模块提供 `State/Flags` 块；同时它也能在“角色块”里提供一个“局部视图”（不新增数据源，只是呈现过滤结果）。

### 1.1 为什么推荐“Block → View → Entry”适用于所有块

你提出的结构可以推广到所有块，并且对 token 控制很关键：

- **Block**：负责定义规则与数据（schema/冲突/预算/注入策略）
- **View**：负责“在特定情境下挑哪些条目”（例如“到期伏笔”“当前目标”“某角色持有物品”“本 Scene 相关事件”）
- **Entry**：负责最小可回滚单元（带证据与版本）

这能让我们做到“数据很全，但每轮只注入视图选出来的很少一部分”。

---

## 2. 模块契约（统一规则约束）

### 2.1 Module Manifest（模块清单）

每个模块需要声明（概念字段，后续可映射为 JSON/YAML）：

- `module_id`：全局唯一、稳定（未来多端同步/导入导出靠它识别）
- `version`：语义化版本（用于迁移）
- `name/description`
- `scope`：`story`（仅当前故事）/ `global`（跨故事复用）
- `suggests`：软依赖（缺失则降级运行；v0 只使用软依赖，不使用硬依赖）
- `capabilities`：
  - `inject_context`：是否能产出注入片段
  - `propose_updates`：是否能产出 Proposal
  - `apply_patch`：是否支持条目级 patch/merge
  - `ui_views`：是否提供独立页面/局部视图
- `budgets`：默认预算与上限（token/字符/条目数）
- `log_events`：必须记录哪些事件（注入清单、更新提议、冲突、回滚…）

### 2.2 Block Contract（块的统一字段）

每个 Block 至少要有：

- `block_id`（模块内唯一即可，但建议全局唯一：`module_id:block_id`）
- `label` / `description`（向模型解释“这块是什么、怎么用”）
- `canon_policy`：
  - `canon_write_mode = human_confirmed_only`（默认）
  - `draft_allowed = true`
- `entry_schema`（条目结构：最小字段 + 可扩展字段）
- `conflict_policy`（与 Canon 冲突时：必须进入 Proposal 弹窗，用户选“纠错/剧情变化/拒绝/编辑”）
- `injection_policy`：
  - `position`（system / before history / @depth / author_note）
  - `frequency`（每轮/每 N 轮/仅命中/仅切场景/手动）
  - `selector`（当条目很多时，如何选 top-N：重要性/到期/匹配/最近）
- `budget_policy`：本块预算、单条预算、裁剪策略（截断/摘要/降级为不注入）
- `observability`：注入/更新/裁剪必须可审计（写日志）

### 2.3 View Contract（局部视图契约）

每个 View 至少声明：

- `view_id`：模块内唯一（建议 `module_id:block_id:view_id`）
- `label/description`
- `selector`：选择规则（过滤 + 排序 + top-N），例如：
  - `match = current_scene` / `match = current_characters`
  - `status in {active,due}`
  - `order by urgency desc, importance desc`
  - `limit = 2`
- `injection_profile`（可选）：该 View 默认注入到 P0/P1/P2 哪一层、频率、位置
- `ui_profile`（可选）：是否默认展示、是否可折叠、是否允许快速编辑/回滚

> 关键点：View 不要求引入新数据源；它只是“同一块数据”的不同切片与呈现方式。

---

## 3. 条目统一外壳（Entry Envelope）

为了让不同模块“装得下、拆得掉、能互相引用”，建议所有条目至少带一个统一外壳：

- `entry_id`：稳定 ID
- `entry_type`：例如 `foreshadow/goal/event/state/style_rule/...`
- `canonicality`：`canon | draft`
- `status`：例如 `active/resolved/archived`（由各模块扩展）
- `content`：人类可读内容（允许结构化字段并行存在）
- `evidence`：证据引用（可指向消息片段/事件条目/场景 ID）
- `created_at/updated_at`
- `revision`：版本号或变更 hash（用于回滚）
- `tags`：用于过滤、检索、UI 分组

> 关键：**证据与解读分离**。证据（“文本里确实出现过”）可以进 Canon；解读/预期回收方式通常先留在 Draft。

---

## 4. Orchestrator 与模块的协作方式（概念）

你提出“指挥官常驻、专用 agent 按需启动”非常适合控制 token：

1) Orchestrator 收集信号（本轮输入、Scene 变化、预算、冲突风险…）
2) 选择要运行的模块任务：
   - `Scene`：是否需要提议切场景/更新 Scene State
   - `Timeline`：是否需要抽取关键事件
   - `Threads`：是否产生新伏笔/目标，或触发“到期提醒”
   - `State`：是否发生状态变化（物品、伤势、关系）
   - `Style`：是否需要按频率注入风格规则
3) 编排注入：按 P0/P1/P2 选最小集合
4) 产生日志：token、注入清单、裁剪原因、Proposal 详情

模块不应“自行无限工作”；所有模块的运行都应被 Orchestrator 的预算与节奏约束。

---

## 5. 禁用（Disable）语义（你已确认的规则）

你已确认：**禁用 = 停止注入与后台维护，数据保留，随时再启用**；禁用后 Orchestrator 与后台系统应完全忽略该模块。

### 5.1 实际逻辑如何保证“被完全忽略”

建议用“硬门禁（hard gate）+ 统一入口”来实现，而不是靠每个模块自觉：

1) **统一事实源：ModuleRegistry**
   - 读取 `enabled_modules`（按 story 作用域）
   - 所有 pipeline（注入/维护/检索/冲突检查）都必须先询问 ModuleRegistry
2) **调度门禁：Orchestrator 只枚举启用模块**
   - 触发器（Scene 变化/轮数/预算）只对启用模块生效
   - 禁用模块不会被派发“提议更新/摘要/压缩/检索”等任务
3) **注入门禁：Context Compiler 只收集启用模块的 fragments**
   - 禁用模块即使有数据，也不会进入 prompt
4) **后台门禁：Job Queue/定时任务在出队时二次检查**
   - 防止“先启用后禁用”导致旧任务继续跑
5) **Proposal 门禁：禁用模块不产出新 Proposal**
   - 已生成但未处理的 Proposal：保留在“待处理”页，但不再自动刷新/合并
6) **日志：记录‘被跳过’原因**
   - 便于你要的可溯源（例如：某条矛盾未被检测，是因为相关模块被禁用）

> 这套设计的目的：禁用模块后，不仅“不注入”，也不消耗 token，不占用 Orchestrator 的注意力。

### 5.2 你已补充确认：禁用后禁止编辑

- 禁用模块后，该模块对应的 Block/View 在 UI 中应被隐藏或锁定为不可编辑（你选择：**禁止编辑，需启用后才可编辑**）。
- 禁用模块期间：
  - 不新增/不更新该模块条目
  - 不生成该模块 Proposal
  - 不允许用户在该模块界面修改条目（避免“禁用但仍在变更”的语义冲突）

---

## 6. 模块依赖（举例：哪些模块/视图会互相依赖？）

你希望“所有模块都非必要”，所以建议尽量用 `suggests`（软依赖）+ 降级路径，避免 `requires`（硬依赖）。下面是一些常见依赖关系与可选降级：

1) `foreshadow_hooks` →（建议）`timeline`
   - 用途：伏笔条目引用“关键事件条目”作为证据，比直接引用原始聊天更稳定。
   - 降级：没有 timeline 时，证据引用改为引用“消息片段”（message span）。

2) `foreshadow_hooks` →（建议）`scene`
   - 用途：判断“到期/相关性”时更准确（按 Scene 变化、在场角色变化）。
   - 降级：没有 scene 时，到期单位可退化为“轮数/消息数”。

3) `state` →（建议）`character`
   - 用途：提供“某角色局部视图”（该角色的物品/状态）。
   - 降级：没有 character 时，只提供“全局状态列表视图”。

4) `world` →（建议）`scene`
   - 用途：根据场景地点/在场角色筛选世界书条目，降低 token 与噪声。
   - 降级：没有 scene 时，world 只能用关键词触发与 scan depth 来过滤。

5) `goals` ↔（建议）`foreshadow_hooks`
   - 用途：Goal 完成可能意味着某伏笔被回收；两个模块需要能互相引用（而不是互相强依赖）。
   - 降级：只做“弱联动”：Goal 完成时生成一个 Proposal，提示用户去回收伏笔（不自动跨模块改动）。

6) `character`（角色记忆/认知）→（建议）`timeline` / `scene`
   - 用途：把“客观事件”转为“角色已知/未知/误解/情绪印象”，需要引用事件证据与发生情境。
   - 降级：没有 timeline/scene 时，角色记忆只记录“对话中明确说过的认知”，不做事件映射。

7) `style` →（建议）`scene`（后续可选）
   - 用途：某些 View 可能希望在特定 Scene 临时增强/抑制某类风格约束（例如战斗短句、梦境二人称）。
   - 降级：没有 scene 时，style 只按频率注入故事级规则（你当前的默认策略）。

> 建议：依赖关系更多发生在“View 层”（选择/排序/引用证据）而不是“数据层”，这样更容易做到可拆卸。

---

## 7. 导出/导入格式（创意工坊的基础）

你已确认支持导出；当前决定 **暂定仅 JSON**（先把“分享/备份”跑通，后续再升级到 zip/分片等格式）。

### 7.1 只导出配置（轻量）

- `modpack.json`（单文件，便于分享/复制）
  - module manifests（启用列表、预算、注入策略、view 配置）
  - 不含具体条目数据（或只含极少示例）

### 7.2 导出配置 + 数据（完整备份/分享）

- `modpack.json`（仍是单文件，但包含 `entries`）
  - `schema_version`
  - `modules[]`：manifest + blocks + views + entries
  - 注：如果数据量变大，后续可升级为 zip + JSONL；但当前先不引入。

> 关键：导出必须带 `schema_version`，未来迁移/兼容才不会失控。

---

## 8. 建议的“官方内置模块”清单（v0）

- `character`：角色卡（基准+Delta）+ 角色记忆/知识（可选）
- `world`：世界书（关键词触发、预算裁剪）
- `scene`：场景状态（短注入、切场景提议）
- `timeline`：事件台账（关键节点证据源）
- `goals`：目标与任务（独立块）
- `foreshadow_hooks`：伏笔与钩子（独立块）
- `state`：状态与约束（独立块 + 角色局部视图）
- `style`：文风与叙事规则（用户可编辑，按频率注入）
- `mechanics`：骰子/检定/规则（可选模块，低频也可存在）

---

## 9. 我需要你再确认的几个问题（用于把“Mod 框架”落成稳定需求）

1) **模块作用域**：模块配置（例如 Style 规则）是“每个故事独立”，还是允许“全局模板一键套用”？
   - 例：你有一套常用文风模板（第一人称、现在时、心理描写、禁用总结句），想在新故事里一键套用。
2) **Style 的覆写粒度**：Style 规则是否需要支持“故事级默认 + 角色级覆写 + Scene 级临时覆写”？
   - 例（角色级）：某 NPC 说话总带古风腔；但叙事主体文风是现代口语。
   - 例（Scene 级）：梦境/回忆/战斗场景希望临时切换为更短句、更强节奏，结束后自动恢复。
3) **禁用后的可见性**：✅ 已确认：禁用后禁止编辑，需启用后再编辑；禁用后全方面无视对应模块/视图。
4) **模块依赖策略**：✅ 已确认：只用软依赖（`suggests`）+ 降级路径，不使用硬依赖。
5) **导出范围**：导出时是否允许选择：
   - 仅配置（轻量）
   - 配置+数据（完整）
   - 配置+数据+资源（含头像/插图）
