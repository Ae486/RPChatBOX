# 技术实现映射（Draft）

> 目标：将架构设计（19/20）映射到 Flutter/Hive 技术栈的具体实现方案。
>
> 本文档为 Claude + Codex 迭代讨论的结果汇总。
>
> 最后更新：2026-01-07

---

## 0. 技术栈现状

### 0.1 当前架构

| 组件 | 技术 | 现状 |
|------|------|------|
| 框架 | Flutter | 跨平台 UI |
| 持久化 | Hive | 本地 NoSQL |
| 消息模型 | ConversationThread + threadJson | 支持消息树 |
| 角色系统 | RolePreset + CustomRole | 8 个预设 |
| AI 集成 | Provider 抽象层 | OpenAI 兼容，流式输出 |
| 上下文 | contextLength + systemPrompt | 最近 N 条消息 |

### 0.2 扩展目标

在不破坏现有功能的前提下，新增：
- 记忆模块系统（Block/Entry/View）
- 版本控制与回滚（Operation/Snapshot）
- 后台 Agent 任务（Worker Isolate）
- 上下文编译器（Budget Broker + RTCO）

---

## 1. Hive 数据模型

### 1.1 TypeId 分配

保留现有 TypeId（0..10），为 Roleplay Memory 分配新段：

```
已占用：0..10（Conversation/Message/附件等）
预留段：50..79 核心持久化对象
扩展段：80..89 日志/统计/缓存
```

### 1.2 Box 结构（Hybrid 方案）

**推荐方案 C：元数据 + 内容/日志分离**

```
┌─────────────────────────────────────────────────────────────────┐
│  rp_story_meta (key=storyId)                                    │
│  - 活跃分支、heads、模块启用状态、dirty 标记                      │
│  - 模块配置 JSON                                                 │
├─────────────────────────────────────────────────────────────────┤
│  rp_entry_blobs (key=blobId)                                    │
│  - 不可变条目 blob（COW）                                        │
│  - 包含 logicalId、domain、scope、status、content                │
├─────────────────────────────────────────────────────────────────┤
│  rp_ops (key=$storyId|$scope|$branchId|$rev)                    │
│  - Append-only 操作日志                                          │
│  - 每个 op 包含 EntryChange 列表                                 │
├─────────────────────────────────────────────────────────────────┤
│  rp_snapshots (key=$storyId|$scope|$branchId|$rev)              │
│  - 指针集合（logicalId → blobId）                                │
│  - 可选 byDomain 索引                                            │
├─────────────────────────────────────────────────────────────────┤
│  rp_proposals (key=proposalId)                                  │
│  - 待处理提议 + 决策记录                                         │
├─────────────────────────────────────────────────────────────────┤
│  rp_logs (key=logId)                                            │
│  - 预算丢弃、闸门违规、调度决策、任务追踪                          │
└─────────────────────────────────────────────────────────────────┘
```

**为什么不选其他方案**：
- (A) 单 box 嵌套 JSON：每轮重写巨大 JSON，性能差
- (B) 每块一个 box：box 数量爆炸，迁移复杂

### 1.3 核心数据模型定义

#### 1.3.1 枚举定义

```dart
enum RpScope { foundation, story }
enum RpStatus { confirmed, draft }
enum RpPolicyTier { silent, notifyApply, reviewRequired }

enum RpProposalKind {
  confirmedWrite,
  draftUpdate,
  linkUpdate,
  sceneTransition,
  compressionUpdate,
  outputFix,
  userEditInterpretation,
}

enum RpProposalDecision { pending, applied, rejected, superseded }
```

#### 1.3.2 StoryMeta（typeId: 50-52）

```dart
@HiveType(typeId: 50)
class RpStoryMeta extends HiveObject {
  @HiveField(0) final String storyId;
  @HiveField(1) final int schemaVersion;
  @HiveField(2) final String activeBranchId;
  @HiveField(3) final int sourceRev;
  @HiveField(4) final List<RpHead> heads;
  @HiveField(5) final List<RpModuleState> modules;
  @HiveField(6) final Map<String, String> moduleConfigJson;
  @HiveField(7) final int updatedAtMs;
}

@HiveType(typeId: 51)
class RpHead {
  @HiveField(0) final int scopeIndex;
  @HiveField(1) final String branchId;
  @HiveField(2) final int rev;
  @HiveField(3) final int lastSnapshotRev;
}

@HiveType(typeId: 52)
class RpModuleState {
  @HiveField(0) final String moduleId;
  @HiveField(1) final bool enabled;
  @HiveField(2) final int lastDerivedSourceRev;
  @HiveField(3) final bool dirty;
  @HiveField(4) final int dirtySinceSourceRev;
  @HiveField(5) final String? dirtyFromMessageId;
  @HiveField(6) final int updatedAtMs;
}
```

#### 1.3.3 EntryBlob（typeId: 53-54）

```dart
@HiveType(typeId: 53)
class RpEntryBlob {
  @HiveField(0) final String blobId;
  @HiveField(1) final String storyId;
  @HiveField(2) final String logicalId;
  @HiveField(3) final int scopeIndex;
  @HiveField(4) final String branchId;
  @HiveField(5) final int statusIndex;
  @HiveField(6) final String domain;
  @HiveField(7) final String entryType;
  @HiveField(8) final Uint8List contentJsonUtf8;
  @HiveField(9) final String? preview;
  @HiveField(10) final List<String> tags;
  @HiveField(11) final List<RpEvidenceRef> evidence;
  @HiveField(12) final int createdAtMs;
  @HiveField(13) final int sourceRev;
  @HiveField(14) final int? approxTokens;
}

@HiveType(typeId: 54)
class RpEvidenceRef {
  @HiveField(0) final String type;
  @HiveField(1) final String refId;
  @HiveField(2) final int? start;
  @HiveField(3) final int? end;
  @HiveField(4) final String? note;
}
```

#### 1.3.4 Operation（typeId: 55-56）

```dart
@HiveType(typeId: 55)
class RpOperation {
  @HiveField(0) final String storyId;
  @HiveField(1) final int scopeIndex;
  @HiveField(2) final String branchId;
  @HiveField(3) final int rev;
  @HiveField(4) final int createdAtMs;
  @HiveField(5) final int sourceRev;
  @HiveField(6) final String? agent;
  @HiveField(7) final String? jobId;
  @HiveField(8) final List<RpEntryChange> changes;
}

@HiveType(typeId: 56)
class RpEntryChange {
  @HiveField(0) final String logicalId;
  @HiveField(1) final String domain;
  @HiveField(2) final String? beforeBlobId;
  @HiveField(3) final String? afterBlobId;
  @HiveField(4) final int reasonKindIndex;
  @HiveField(5) final List<RpEvidenceRef> evidence;
  @HiveField(6) final String? note;
}
```

#### 1.3.5 Snapshot（typeId: 57）

```dart
@HiveType(typeId: 57)
class RpSnapshot {
  @HiveField(0) final String storyId;
  @HiveField(1) final int scopeIndex;
  @HiveField(2) final String branchId;
  @HiveField(3) final int rev;
  @HiveField(4) final int createdAtMs;
  @HiveField(5) final int sourceRev;
  @HiveField(6) final Map<String, String> pointers;
  @HiveField(7) final Map<String, List<String>> byDomain;
}
```

#### 1.3.6 Proposal（typeId: 58-59）

```dart
@HiveType(typeId: 58)
class RpProposal {
  @HiveField(0) final String proposalId;
  @HiveField(1) final String storyId;
  @HiveField(2) final String branchId;
  @HiveField(3) final int createdAtMs;
  @HiveField(4) final int kindIndex;
  @HiveField(5) final String domain;
  @HiveField(6) final int policyTierIndex;
  @HiveField(7) final RpProposalTarget target;
  @HiveField(8) final Uint8List payloadJsonUtf8;
  @HiveField(9) final List<RpEvidenceRef> evidence;
  @HiveField(10) final String reason;
  @HiveField(11) final int sourceRev;
  @HiveField(12) final int expectedFoundationRev;
  @HiveField(13) final int expectedStoryRev;
  @HiveField(14) final int decisionIndex;
  @HiveField(15) final int? decidedAtMs;
  @HiveField(16) final String? decidedBy;
  @HiveField(17) final String? decisionNote;
}

@HiveType(typeId: 59)
class RpProposalTarget {
  @HiveField(0) final int scopeIndex;
  @HiveField(1) final String branchId;
  @HiveField(2) final int statusIndex;
  @HiveField(3) final String logicalId;
}
```

---

## 2. logicalId 命名规范

### 2.1 格式模式

```
rp:v1:<domainCode>:<entityKey>:<entryType>[:<subKey>]
```

- `rp:v1` 固定前缀（迁移友好）
- `domainCode` 短代码
- `entityKey` 稳定内部 ID（ULID/UUID）
- `entryType` 点分路径描述条目类型
- `subKey` 可选消歧符

**允许字符集**：`[a-z0-9._:-]`
**最大长度**：`< 160 chars`

### 2.2 Domain Codes

| Domain | Code | 说明 |
|--------|------|------|
| Character | `ch` | 角色 |
| World | `w` | 世界书 |
| Scene | `sc` | 场景 |
| Timeline | `tl` | 时间线 |
| Goals | `g` | 目标 |
| Foreshadow_Hooks | `fh` | 伏笔 |
| State | `st` | 状态 |
| Style | `sty` | 文风 |
| Mechanics | `mech` | 机制 |
| Mod 扩展 | `x-<vendor>` | 第三方模块 |

### 2.3 Entry Types（按 Domain）

**Character (`ch`)**
- `card.base` - 基础角色卡（foundation）
- `card.delta` - 剧情修订层（story）
- `appearance` - 外观结构化
- `voice` - 语音/风格约束
- `relations` - 关系
- `memory.subjective` - 主观记忆
- `knowledge` - 知识/秘密

**World (`w`)**
- `place.base` / `place.delta` - 地点
- `faction.base` / `faction.delta` - 组织
- `item.base` / `item.delta` - 物品
- `lore.note` - 传说笔记
- `rules` - 规则/物理

**Scene (`sc`)**
- `state` - 当前场景状态
- `card` - 场景历史卡
- `constraints` - 场景约束

**Timeline (`tl`)**
- `event` - 关键事件
- `summary` - 摘要
- `summary.chapter` - 章节摘要

**Goals (`g`)**
- `goal` - 目标条目
- `rollup.active` - 活跃目标汇总

**Foreshadow (`fh`)**
- `hook` - 伏笔条目（含 tracker）
- `tracker` - 独立 tracker
- `link` - 关联边

**State (`st`)**
- `flags` - 标志集
- `injury` - 伤势
- `inventory` - 物品栏
- `inventory.item` - 单个物品
- `counter` - 计数器

**Style (`sty`)**
- `card.base` / `card.delta` - 风格卡
- `snippet` - 片段

**Mechanics (`mech`)**
- `ruleset` - 规则集
- `constraints` - 约束
- `tables` - 骰子表

### 2.4 示例

```
角色基础卡：    rp:v1:ch:ent_01j2k...:card.base
角色剧情修订：  rp:v1:ch:ent_01j2k...:card.delta
角色外观：      rp:v1:ch:ent_01j2k...:appearance

世界地点基础：  rp:v1:w:ent_01j30...:place.base
世界地点修订：  rp:v1:w:ent_01j30...:place.delta

当前场景状态：  rp:v1:sc:current:state
场景历史卡：    rp:v1:sc:scene_01j3a...:card

关键事件：      rp:v1:tl:ev_01j3b...:event
时间线摘要：    rp:v1:tl:sum_01j3c...:summary

目标：          rp:v1:g:goal_01j3d...:goal
伏笔：          rp:v1:fh:hook_01j3e...:hook

全局状态标志：  rp:v1:st:global:flags
角色物品栏：    rp:v1:st:ent_01j2k...:inventory
文风基础：      rp:v1:sty:global:card.base
机制规则：      rp:v1:mech:global:ruleset
```

---

## 3. 版本控制实现（COW）

### 3.1 写入顺序（崩溃容错）

Hive 无多 box 原子事务，采用可恢复顺序：

```
1. 写入新 EntryBlob(s) → rp_entry_blobs
2. 写入 Operation → rp_ops（关键一步）
3. 更新 StoryMeta.heads → rp_story_meta
4. 可选：每 N 个 rev 写入 Snapshot → rp_snapshots
5. 追加审计日志 → rp_logs
```

**恢复规则**：`rp_ops` 是权威追加日志；`head` 可通过扫描 ops 重建。

### 3.2 冷启动重建

```
1. 加载 head rev + lastSnapshotRev
2. 加载 snapshot 的 pointer map
3. 应用 ops (snapshotRev+1..headRev) 重建 pointer map
4. 缓存 pointer map 到内存
```

### 3.3 GC 策略

```
1. 标记可达：保留的快照 + 当前 head 链 + 固定 rev
2. 清除未引用的 blobId（rp_entry_blobs）
3. 运行时机：空闲 / sleeptime 维护
```

---

## 4. Worker Isolate 架构

### 4.1 通信模式

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Isolate                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ UI + Streaming + Hive 写入（单一写入者）                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                    SendPort/ReceivePort                         │
│                         JSON UTF-8                              │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                        Worker Isolate                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLM Agents + JSON 解析 + 评分计算                        │   │
│  │ (只读，返回 Proposals)                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 请求/响应协议

```dart
class WorkerRequest {
  final String requestId;
  final String storyId;
  final String branchId;
  final int sourceRev;
  final int foundationRev;
  final int storyRev;
  final List<String> tasks;
  final Map<String, dynamic> inputs;
}

class WorkerResponse {
  final String requestId;
  final bool ok;
  final List<Map<String, dynamic>> proposals;
  final List<Map<String, dynamic>> logs;
  final Map<String, dynamic> metrics;
}
```

### 4.3 任务调度器

```dart
class RpTaskSpec {
  final String taskId;
  final String storyId;
  final String branchId;
  final String dedupeKey;
  final RpTaskPriority priority;
  final int requiredSourceRev;
  final int requiredFoundationRev;
  final int requiredStoryRev;
  final List<String> tasks;
  final int enqueuedAtMs;
}

enum RpTaskPriority { urgent, normal, idle }
```

**调度策略**：
- 优先队列（PriorityQueue）
- 去重合并（相同 dedupeKey 保留更新的）
- 背压处理（优先丢弃 idle，再丢 normal）
- 并发限制（默认 maxInFlight = 1）

**Warm-up 策略**：
- 默认懒加载（首次 enqueue 才启动）
- 可选：进入角色扮演页面时预热

### 4.4 崩溃恢复

```
Worker 崩溃时：
1. onError/onExit 回调触发
2. 标记 inflight requestId 失败
3. 懒重启 Worker
4. 本轮降级：跳过后台 Agent
```

---

## 5. 上下文编译器（ContextCompiler）

### 5.1 Fragment 数据结构

```dart
enum RpPriority { p0, p1, p2 }

class RpFragmentCandidate {
  final String id;
  final String moduleId;
  final String viewId;
  final RpPriority priority;
  final String text;
  final int costTokens;
  final double score;
  final bool required;
  final String? dedupeKey;
  final Map<String, String> attrs;
}

class RpPackedContext {
  final List<RpFragmentCandidate> injectedP0;
  final List<RpFragmentCandidate> injectedP1;
  final List<RpFragmentCandidate> injectedP2;
  final List<RpDroppedFragment> dropped;
  final int totalTokens;
}
```

### 5.2 模块接口（Mod-like）

```dart
abstract class RpModule {
  String get id;
  String get displayName;
  Set<String> get softDependencies;

  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx);
}

class RpFragmentContext {
  final String storyId;
  final String branchId;
  final RpTokenBudget budget;
  final RpMemoryReader memory;
  final RpTokenEstimator tokenEstimator;
  final List<Map<String, dynamic>> recentMessages;
  final Map<String, String> runtimeHints;
}
```

### 5.3 模块注册与编译

```dart
class RpModuleRegistry {
  final Map<String, RpModuleFactory> _factories = {};

  void register(RpModuleFactory factory, {required String moduleId});
  List<RpModule> createEnabledModules(RpStoryMeta meta);
}

class RpContextCompiler {
  final RpModuleRegistry registry;
  final RpBudgetBroker broker;

  Future<RpPackedContext> compile({
    required RpStoryMeta meta,
    required RpFragmentContext ctx,
  });
}
```

### 5.4 Budget Broker 评分公式

**基础权重（按 Domain）**：

| Domain | 权重 |
|--------|------|
| Scene | +100 |
| Character | +90 |
| State | +85 |
| Foreshadow | +75 |
| Goals | +70 |
| World | +55 |
| Style | +40 |
| Mechanics | +40 |
| Timeline | +30 |

**评分因子（0..1）**：

| 因子 | 符号 | 计算方式 |
|------|------|----------|
| 相关性 | R | 0.45×entityMention + 0.25×keywordHit + 0.20×topicMatch + 0.10×userIntent |
| 紧迫性 | U | max(dueSoon, payoffProximity, progress, hardConstraintFlag) |
| 风险 | K | 0.6×recentGateFlags + 0.3×editedRecently + 0.1×fragileTypeBoost |
| 新颖性 | N | 0.7×recentUpdate + 0.3×notShownRecently |
| 冗余惩罚 | D | dedupeHit ? 1 : similarityScore |
| 陈旧惩罚 | S | dirty && depSourceRev < dirtySince ? 1 : 0 |

**最终公式**：

```
utility(f) = priorityBase + domainWeight + 60×R + 50×U + 40×K + 20×N - 50×D - 999×S

packingScore(f) = utility(f) / max(1, costTokens(f))
```

**Per-Module Caps（P1 默认）**：

| Module | Cap |
|--------|-----|
| Scene | 1 |
| Character | 2 |
| State | 2 |
| Foreshadow | 2 |
| Goals | 2 |
| World | 1 |
| Style | 1 |
| Mechanics | 1 |
| Timeline | 0 (P2) |

### 5.5 缓存失效策略

**触发失效的事件**：
- 任何 op 触及该 view 使用的条目
- 分支切换、scope 变化
- 模块启用/禁用
- Token 预算变化
- 时间敏感 view 的 TTL 到期

**Token 估算**：
- 快速路径：`tokens ≈ ceil(charCount / 4)`
- 精确路径：Worker Isolate 计算，缓存 `costTokens` by text hash

**Dirty Window 追踪**：
- `sourceRev` 单调递增
- 每模块记录 `lastDerivedSourceRev`、`dirtySinceSourceRev`
- 编辑旧消息：`sourceRev++`，标记所有派生模块 dirty

---

## 6. Proposal Payload Schema

### 6.1 通用类型

```typescript
type RpScope = "foundation" | "story";
type RpStatus = "confirmed" | "draft";

type EvidenceRef = {
  type: "msg" | "op" | "user_edit" | "external";
  refId: string;
  start?: number;
  end?: number;
  note?: string;
};

type MergeStrategy =
  | { kind: "replace" }
  | { kind: "shallow_merge" }
  | { kind: "json_patch"; ops: JsonPatchOp[] };

type EntryWrite = {
  logicalId: string;
  domain: string;
  entryType: string;
  scope: RpScope;
  status: RpStatus;
  branchId?: string;
  merge: MergeStrategy;
  content: any;
  tags?: string[];
  preview?: string;
  evidence?: EvidenceRef[];
};
```

### 6.2 各 ProposalKind Payload

**CONFIRMED_WRITE**
```typescript
type ConfirmedWritePayload = {
  kind: "CONFIRMED_WRITE";
  writes: EntryWrite[];  // status="confirmed"
  deletes?: EntryDelete[];
  archives?: EntryArchive[];
};
```

**DRAFT_UPDATE**
```typescript
type DraftUpdatePayload = {
  kind: "DRAFT_UPDATE";
  writes: EntryWrite[];  // status="draft"
  deletes?: EntryDelete[];
  draftMeta?: Array<{ logicalId: string; confidence: number; note?: string }>;
};
```

**LINK_UPDATE**
```typescript
type LinkUpdatePayload = {
  kind: "LINK_UPDATE";
  hookId: string;
  linkOps: Array<{
    op: "link" | "unlink" | "update";
    eventId: string;
    polarity?: "positive" | "negative" | "neutral";
    delta?: number;
    note?: string;
  }>;
  trackerDelta?: {
    evidenceAccumulationDelta?: number;
    payoffProximityDelta?: number;
    confidenceDelta?: number;
    set?: Partial<{ evidenceAccumulation: number; payoffProximity: number; confidence: number; status: string }>;
  };
  evidence?: EvidenceRef[];
  reason?: string;
};
```

**SCENE_TRANSITION**
```typescript
type SceneTransitionPayload = {
  kind: "SCENE_TRANSITION";
  fromSceneId?: string;
  toScene: {
    sceneId: string;
    locationEntityKey?: string;
    time?: string;
    presentEntityKeys: string[];
    objective?: string;
    conflict?: string;
    recap: string;
    constraints?: string[];
  };
  writeSceneCard?: boolean;
  evidence?: EvidenceRef[];
  reason?: string;
};
```

**COMPRESSION_UPDATE**
```typescript
type CompressionUpdatePayload = {
  kind: "COMPRESSION_UPDATE";
  writes: EntryWrite[];
  supersedes?: string[];
  archives?: EntryArchive[];
  window?: { fromEventId?: string; toEventId?: string; messageIdRange?: [string, string] };
  evidence?: EvidenceRef[];
  reason?: string;
};
```

**OUTPUT_FIX**
```typescript
type OutputFixPayload = {
  kind: "OUTPUT_FIX";
  severity: "info" | "warn" | "error";
  violations: Array<{
    code: string;
    severity: "info" | "warn" | "error";
    message: string;
    expected?: any;
    found?: any;
    evidence: EvidenceRef[];
    recommended: Array<
      | { action: "PROPOSE_MEMORY_PATCH"; payload: any }
      | { action: "SUGGEST_USER_CORRECTION"; text: string }
      | { action: "SUGGEST_RETRY_GENERATION"; reason: string; constraintsToAdd?: string[] }
    >;
  }>;
  streamingModeHint?: "buffered" | "live_streamed";
};
```

**USER_EDIT_INTERPRETATION**
```typescript
type UserEditInterpretationPayload = {
  kind: "USER_EDIT_INTERPRETATION";
  editedMessageId: string;
  beforeText: string;
  afterText: string;
  classification: "typo_fix" | "factual_correction" | "retcon" | "style_edit" | "unknown";
  confidence: number;
  impacts: Array<{
    domain: string;
    logicalIdsHint?: string[];
    note?: string;
  }>;
  recommendedPatches?: Array<any>;
  evidence?: EvidenceRef[];
  reason?: string;
};
```

---

## 7. 与现有代码集成

### 7.1 最小侵入策略

**目标**：保持现有 Conversation + Streaming 管线，新增并行记忆子系统。

### 7.2 集成点

```
┌─────────────────────────────────────────────────────────────────┐
│                        现有代码                                  │
├─────────────────────────────────────────────────────────────────┤
│  lib/models/message.dart          → 不改动                       │
│  lib/adapters/                    → 不改动                       │
│  lib/services/                    → 新增 roleplay 服务           │
│  lib/widgets/conversation_view_v2 → 注入编译后上下文              │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 新增服务层

```
lib/services/roleplay/
├── roleplay_memory_repository.dart  # Hive CRUD 封装
├── context_compiler.dart            # Budget Broker + 模块编译
├── proposal_applier.dart            # Proposal → Operation 转换
├── agent_worker_host.dart           # Isolate 管理
└── orchestrator.dart                # 调度逻辑
```

### 7.4 数据流（每轮）

```
┌─────────────────────────────────────────────────────────────────┐
│  Recent Messages                  Memory Pointers + Blobs        │
│  (contextLength)                  (foundation + story heads)     │
└─────────────────────┬─────────────────────────┬─────────────────┘
                      │                         │
                      ▼                         ▼
              ┌───────────────────────────────────────────┐
              │          ContextCompiler + BudgetBroker   │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
              ┌───────────────────────────────────────────┐
              │          Provider Request (Stream)        │
              └─────────────────────┬─────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
        ┌──────────┐         ┌──────────┐         ┌──────────┐
        │ UI 渲染  │         │ 完成后   │         │ Worker   │
        │  tokens  │         │Orchestrator│       │ Agents   │
        └──────────┘         │调度任务  │         └────┬─────┘
                             └────┬─────┘              │
                                  │                    │
                                  ▼                    ▼
              ┌───────────────────────────────────────────┐
              │               ProposalBatch               │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
              ┌───────────────────────────────────────────┐
              │    Policy Tiering (silent/notify/review)  │
              └─────────────────────┬─────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
        ┌──────────┐         ┌──────────┐         ┌──────────┐
        │ Commit   │         │ Store    │         │ UI 弹窗  │
        │Ops+Blobs │         │Proposals │         │(review)  │
        └──────────┘         │  /Logs   │         └──────────┘
                             └──────────┘
```

---

## 8. 待确认问题

### 8.1 性能相关

- [ ] Snapshot 间隔（每 N 个 rev）的默认值？建议 N=20
- [ ] GC 频率与触发条件？
- [ ] 大 Story 的 pointers map 是否需要压缩存储？

### 8.2 迁移相关

- [ ] 现有 Conversation 如何迁移到新系统？
- [ ] TypeId 段是否与其他插件冲突？

### 8.3 测试相关

- [ ] Worker Isolate 的单元测试策略？
- [ ] COW 写入顺序的崩溃恢复测试？

---

## 9. 下一步

1. **Phase 4**：边界情况与开放问题解决
2. **Phase 5**：总结文档 → `22-FINAL-SUMMARY.md`

