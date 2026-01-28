# M1 Context Compiler Spec

> 版本: 1.0.0
> 创建日期: 2026-01-18
> 完成日期: 2026-01-18
> 状态: ✅ 已完成

---

## 1. 目标

为 Roleplay Feature 实现上下文编译器：
- RpModule 接口定义（模块化架构）
- RpBudgetBroker 实现（优先级分配）
- 核心模块注册（Scene, Character, State）
- 与现有 systemPrompt 集成

---

## 2. 设计决策

### 2.1 模块架构

采用 Mod-like 架构，每个模块独立生成 Fragment 候选：

```
Module → buildFragments() → List<RpFragmentCandidate>
                                    ↓
                            BudgetBroker.pack()
                                    ↓
                            RpPackedContext
```

### 2.2 优先级系统

| 优先级 | 含义 | 预留比例 |
|--------|------|----------|
| P0 | 必须（required） | 60% |
| P1 | 重要 | 30% |
| P2 | 可选 | 10% |

### 2.3 Domain 权重

| Domain | 权重 | 说明 |
|--------|------|------|
| Scene | 100 | 当前场景状态 |
| Character | 90 | 角色卡/外观 |
| State | 85 | 状态/伤势/物品 |

### 2.4 评分公式

```
packingScore = utility / max(1, costTokens)
```

其中：
- `utility = priorityBase + domainWeight + typeBonus + requiredBonus`
- `priorityBase`: P0=1000, P1=500, P2=100

---

## 3. 文件结构

### 3.1 核心组件

```
lib/services/roleplay/context_compiler/
├── rp_fragment.dart          # Fragment 数据结构
├── rp_memory_reader.dart     # 内存读取接口
├── rp_token_estimator.dart   # Token 估算器
├── rp_module.dart            # Module 接口 + Registry
├── rp_budget_broker.dart     # 预算分配器
└── rp_context_compiler.dart  # 主编译器
```

### 3.2 内置模块

```
lib/services/roleplay/modules/
├── scene_module.dart         # Scene (P0, weight=100)
├── character_module.dart     # Character (P0, weight=90)
└── state_module.dart         # State (P0, weight=85)
```

### 3.3 测试文件

```
test/unit/services/roleplay/context_compiler/
├── rp_fragment_test.dart
├── rp_token_estimator_test.dart
├── rp_module_test.dart
└── rp_budget_broker_test.dart
```

---

## 4. 接口定义

### 4.1 RpModule

```dart
abstract class RpModule {
  String get id;
  String get displayName;
  String get domainCode;
  int get domainWeight;
  Set<String> get softDependencies;

  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx);
}
```

### 4.2 RpFragmentCandidate

```dart
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

  double get packingScore => score / (costTokens > 0 ? costTokens : 1);
}
```

### 4.3 RpContextCompiler

```dart
class RpContextCompiler {
  Future<RpCompileResult> compile({
    required String storyId,
    required String branchId,
    required int maxTokensTotal,
  });

  String render(RpPackedContext packed);
}
```

---

## 5. 集成点

### 5.1 streaming.dart 修改

在 `_startAssistantResponse()` 中注入 roleplay 上下文：

```dart
// 条件检查
if (_isRoleplaySession(widget.conversation)) {
  final rpContext = await _compileRoleplayContext(widget.conversation);
  if (rpContext.isNotEmpty) {
    chatMessages.add(ai.ChatMessage(role: 'system', content: rpContext));
  }
}
```

### 5.2 懒初始化模式

```dart
RpMemoryRepository? _rpRepository;
RpContextCompiler? _rpContextCompiler;

Future<RpContextCompiler> _ensureRpCompiler() async {
  if (_rpContextCompiler != null) return _rpContextCompiler!;
  _rpRepository = RpMemoryRepository();
  await _rpRepository!.initialize();
  _rpContextCompiler = RpContextCompiler(repository: _rpRepository!);
  return _rpContextCompiler!;
}
```

---

## 6. 测试覆盖

| 测试文件 | 测试数量 | 覆盖内容 |
|----------|----------|----------|
| rp_fragment_test.dart | 9 | Fragment 创建/属性/packingScore |
| rp_token_estimator_test.dart | 6 | Token 估算逻辑 |
| rp_module_test.dart | 6 | Module 接口/Registry |
| rp_budget_broker_test.dart | 14 | 优先级分配/去重/溢出处理 |

**总计**: 35 个单元测试，全部通过

---

## 7. 待优化项（Backlog）

| 项目 | 优先级 | 说明 |
|------|--------|------|
| Domain 名称匹配 | Low | 确认 "character" vs "ch" 映射 |
| 并行化 await | Medium | Future.wait 替代顺序 await |
| Rev 语义修正 | Low | RpMemoryReaderImpl rev 返回值 |
| Token 精确计算 | Low | 使用实际注入内容计算 |

---

## 8. 进度追踪

| 任务 | 状态 | 完成日期 |
|------|------|----------|
| Spec 文档 | ✅ 完成 | 2026-01-18 |
| rp_fragment.dart | ✅ 完成 | 2026-01-17 |
| rp_memory_reader.dart | ✅ 完成 | 2026-01-17 |
| rp_token_estimator.dart | ✅ 完成 | 2026-01-17 |
| rp_module.dart | ✅ 完成 | 2026-01-17 |
| rp_budget_broker.dart | ✅ 完成 | 2026-01-17 |
| rp_context_compiler.dart | ✅ 完成 | 2026-01-17 |
| scene_module.dart | ✅ 完成 | 2026-01-17 |
| character_module.dart | ✅ 完成 | 2026-01-17 |
| state_module.dart | ✅ 完成 | 2026-01-17 |
| streaming.dart 集成 | ✅ 完成 | 2026-01-17 |
| 单元测试 (35 tests) | ✅ 完成 | 2026-01-17 |
| 多模型 Code Review | ✅ 完成 | 2026-01-17 |
| Critical Bug 修复 | ✅ 完成 | 2026-01-17 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-01-18 | M1 实现完成，创建 Spec 文档 |
