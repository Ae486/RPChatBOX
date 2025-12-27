# OWUI 树状消息链（多版本回复）实现规范

> 创建时间：2025-12-24  
> 目标：在 V2（`flutter_chat_ui`）中实现“多版本回复 + 树状消息链切换”，并保证“重新生成/重新发送”触发时 UI 立即只显示新回复的 header 占位，不出现旧回复 + 新占位的双消息闪现。

## 实施状态（截至：2025-12-24）
- ✅ **阶段性修复已落地**：V2 的“重新生成/重新发送（模型侧）”已改为使用 **原子 `setMessages` 同步**插入 header-only 占位，避免重生成时短暂出现两条占位消息。
  - 代码位置：`lib/widgets/conversation_view_v2/streaming.dart:_startAssistantResponse()`
  - 判定条件：`assistantMessageId != null`（即 regenerate/resend 复用 assistant id）
  - 验证：`flutter test` 通过（包含 golden / unit / widget）
- ✅ **体验修复已落地**：点击“重新生成”后会先把对应 AI 消息体清空，仅保留 header，然后再开始构建 prompt 并流式填充新内容（避免长历史/高耗时 token 估算期间仍显示旧回复）。
  - 代码位置：`lib/widgets/conversation_view_v2/streaming.dart:_startAssistantResponse()`

---

## 0. 背景与需求摘要

### 0.1 用户期望（强约束）
- **重新生成/重新发送（模型侧）**：保留旧回复，生成新回复作为同一条“用户消息”的另一个版本（同父节点）。  
- **切换入口**：在“该用户消息”的 token 统计下方显示 `"< 1/2 >"` 的切换控件（左右切换）。  
- **切换语义 = 切换消息链（树的活动路径）**：切换后页面展示应切换到对应分支的整条链路，且**后续上下文（发给大模型的历史）必须与展示一致**。
  - 例：当前为 `A,B,C,D2,D2-E2,D2-E2-F1`，在 `D` 处切换到 `D1` 后，展示应为 `A,B,C,D1`（或该分支上次停留的叶子，见 2.3）。
- **阶段性验收**：先完成“重新生成时旧消息立即隐藏（只显示 header 占位）”的修复；然后仅输出本 spec 供评审；评审通过后再进入编码落地。

### 0.2 当前代码现状（结论）
- 当前持久化模型 `Conversation.messages: List<Message>` 是**线性列表**（见 `lib/models/conversation.dart`），不支持树状分支。
- V2 流式输出依赖 `Conversation.messages` 直接构建上下文（见 `lib/widgets/conversation_view_v2/streaming.dart:_startAssistantResponse`），因此要支持树必须先引入“活动链（active path）”抽象。
- `flutter_chat_ui` 仅负责渲染线性消息列表；树状结构必须由应用层维护，并在 UI 渲染时投影成线性列表。

---

## 1. 术语

- **节点（Node）**：一条消息（用户或助手）。
- **父子关系**：用户节点的子节点通常为多个“助手回复版本”；助手节点的子节点通常为用户继续对话。
- **分叉点（Branch Point）**：某节点存在多个子节点可选。
- **活动路径（Active Path）**：当前 UI 展示/上下文使用的那条从根到叶的链路。
- **叶子（Leaf）**：活动路径的末端节点（当前会话的“最新消息”）。
- **版本（Variant）**：同一个父节点下多个同类型子节点（本需求重点：同一用户消息下多个助手回复）。

---

## 2. 设计方案（推荐：ChatGPT 式树结构）

> 目标是“能抄不写”：复用业界成熟的对话树模型（父指针 + children + current/selected path），仅做 Flutter/现有代码适配。

### 2.1 数据结构（推荐）

新增一个“对话树”结构（推荐独立于现有 `Conversation`，避免一次性重写所有旧逻辑；最终可再决定是否把线性 `messages` 迁移为树）。

**ConversationThread（建议新建 Hive 或 JSON 存储）**
- `conversationId: String`
- `nodes: Map<String, ThreadNode>`（key = messageId）
- `rootId: String?`（首条消息 id；兼容旧数据可按时间最早的无 parent 节点推断）
- `selectedChild: Map<String, String>`（parentId -> selectedChildId，用于恢复“上次停留的叶子”）
- `activeLeafId: String?`（当前活动叶子；可从 root 通过 selectedChild 推导，存一份便于修复/回溯）

**ThreadNode**
- `id: String`
- `parentId: String?`
- `message: app.Message`（复用现有模型，降低改动）
- `children: List<String>`（按创建时间排序；用于计算 `1/2`）

> 备注：该结构与 ChatGPT 的 conversation mapping 设计一致（节点映射 + parent/children + current node），利于实现“切换版本=切换活动路径”。

### 2.2 线性投影（给 flutter_chat_ui）

提供一个纯函数：
- `List<app.Message> buildActiveMessageChain(thread)`  
  - 从 `rootId` 开始，按 `selectedChild` 一直走到叶子；若某 parent 未选择 child，默认选 `children.last`（最新）。
  - 结果是线性链，用于：
    - UI：`_syncConversationToChatController()` 的消息来源
    - 上下文：`_startAssistantResponse()` 的历史来源

### 2.3 切换行为（满足示例）

当用户在 `C`（用户消息）下切换到 `D1`（某个助手版本）时：
- 更新 `selectedChild[C] = D1`
- **活动路径会自动“截断/切换”**到 `...C -> D1 ->（沿 D1 分支继续按 selectedChild 深入，若无则停止）`
- UI 展示与上下文发送必须使用该投影链。

> 这满足示例 `A,B,C,D2,...` 切到 `D1` 后显示 `A,B,C,D1`（若 D1 没有后续选中子节点）。

---

## 3. 交互与 UI 规范

### 3.1 “重新生成/重新发送（模型侧）”的 UI 行为（阶段 1 约束延续）

点击后立即：
- UI **不显示旧回复内容**；
- 仅显示“新回复的 header 占位”（modelName/providerName/时间等），body 为空，随后流式填充。

实现要点（与现阶段修复一致的方向）：
- 触发 regenerate 时，先把活动路径切换到“新版本节点”（新 assistant id），然后让 UI 线性投影立即只包含新占位节点。
- 旧版本节点依然保留在树中，但不在活动路径中，因此不会出现在 UI。

### 3.2 版本切换控件（`< 1/2 >`）

渲染位置：
- 放在“对应用户消息”的 token footer 下方（V2：`lib/widgets/conversation_view_v2/user_bubble.dart` 的 `_buildTokenFooter` 下面）。

展示规则：
- 当某用户消息的助手子节点数 `n <= 1`：不展示控件。
- 当 `n >= 2`：
  - 展示：`<` ` i/n ` `>`（i 从 1 开始）
  - 点击 `<` / `>`：循环切换同父节点下的助手版本，并更新活动路径与 UI。

交互细节：
- 切换后自动 `scrollToMessage()` 到该用户消息或其对应助手消息（避免用户“丢位置”）。
- 若正在流式输出：禁用切换并提示（避免状态破坏）。

---

## 4. 与现有功能的兼容点（必须评估）

### 4.1 搜索定位
- 现有搜索应默认基于“活动路径链”搜索（用户期望与当前可见一致）。
- 可选增强：提供“全树搜索”（先不做，避免 UI 复杂度暴涨）。

### 4.2 导出
- 默认导出活动路径。
- 可选增强：导出整棵树（需要定义格式；先不做）。

### 4.3 删除
- 删除活动路径上的节点需定义：
  - 删除节点及其子树？还是仅从活动路径剔除并保留子树？
- 推荐：删除节点 => 删除子树（更符合用户直觉，也避免孤儿节点污染 UI）。

### 4.4 Token 统计
- token footer 仍展示在“可见链”的每条消息下。
- 切换版本后应刷新 token 汇总（只统计活动路径）。

---

## 5. 迁移与落地步骤（评审后执行）

### Phase A：引入树结构与活动路径投影（不改 UI）
1. 新增 `ConversationThread` 存储（Hive box 或 JSON 文件，按现有持久化体系选择）。
2. 启动时：将旧线性 `Conversation.messages` 转换为单链树（每条消息 parent=前一条）。
3. V2 渲染与上下文全部改为使用 `buildActiveMessageChain(thread)`。

### Phase B：实现“多版本助手回复 + 切换控件”
1. regenerate（模型侧）改为：
   - 在同一个 user 节点下新增 assistant 子节点（新 id）
   - `selectedChild[userId] = newAssistantId`
   - activeLeaf 指向该新节点，并以“header-only 占位”开始流式
2. 在用户消息 token footer 下添加版本切换控件；切换时仅更新 `selectedChild` 并刷新 UI。

### Phase C：功能补齐与测试
- 覆盖：搜索/导出/删除/编辑/重新生成/继续对话/重启恢复。
- 增加最小单测：树操作（添加节点、切换、投影链生成）。

---

## 6. 参考资料（后续可补充）

- 业界通用对话树：父指针 + children + current/selected path（ChatGPT 类产品常用）
- OpenWebUI：regenerate 权限/快捷键等交互配置（用于参考交互细节，不直接依赖其实现）  
  - https://docs.openwebui.com/getting-started/env-configuration/
- Vercel AI SDK：`regenerate({ messageId })` 的“替换/重算指定消息”接口形态（用于参考 API 设计）  
  - https://ai-sdk.dev/docs/ai-sdk-ui/chatbot
